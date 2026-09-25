"""问答服务：Agentic RAG — LLM 自主决定是否检索知识库。"""

from __future__ import annotations

import logging
from collections.abc import Generator
from typing import Any

from fastapi import HTTPException, status
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from sqlalchemy.orm import Session

from app.agent.agent import ChatAgentBundle, build_initial_messages, create_chat_agent
from app.core.cache import HISTORY_TTL_SECONDS, cache, history_key
from app.models.conversation import Conversation
from app.models.user import User
from app.repository.conversation_repository import ConversationRepository, MessageRepository
from app.schemas.chat import ChatRequest, SourceInfo

logger = logging.getLogger(__name__)

HISTORY_LIMIT: int = 10

# create_agent 生成的图里，主回答由 "model" 节点产出；工具在 "tools" 节点内执行。
# 工具内部自己发起的 LLM 调用（如 search_knowledge 里的查询改写）同样会以
# messages 事件流出，必须按节点名剔除，否则中间产物会被当成回答推给前端。
ANSWER_NODE: str = "model"


class ChatService:
    """问答业务逻辑（Agent 模式）。"""

    def __init__(self, db: Session) -> None:
        self._conversation_repository: ConversationRepository = ConversationRepository(db)
        self._message_repository: MessageRepository = MessageRepository(db)
        self._db: Session = db

    def stream_chat(
        self,
        user: User,
        chat_in: ChatRequest,
    ) -> Generator[dict[str, object], None, None]:
        """流式问答：Agent 自主决定是否检索 → LLM 流式回答 → 保存消息。

        产出事件:
          {"type": "conversation_id", "content": int}
          {"type": "token", "content": str}
          {"type": "sources", "content": list[SourceInfo]}
          {"type": "done"}
        """

        conversation: Conversation = self._get_or_create_conversation(user, chat_in.conversation_id)
        is_new: bool = chat_in.conversation_id is None

        logger.info("chat start, user_id=%s conv_id=%s", user.id, conversation.id)

        # 1. 先取历史，此时本轮提问尚未落库，避免历史里出现重复的当前提问
        history_rows: list[dict[str, str]] = self._load_history_rows(conversation.id)
        history: list[BaseMessage] = self._to_messages(history_rows)

        # 2. 保存用户消息
        self._message_repository.create(conversation.id, "user", chat_in.content)

        # 2.1 更新会话：新对话自动命名 + 所有对话 touch updated_at（置顶用）
        new_title = chat_in.content[:30].strip() or "新对话"
        if is_new or conversation.title == "新对话":
            conversation.title = new_title
        self._db.commit()  # updated_at 由 SQLAlchemy onupdate 自动刷新

        # 3. 构建 Agent（闭包绑定 session + user_id，同时回收结构化检索命中）
        bundle: ChatAgentBundle = create_chat_agent(self._db, user.id)

        # 4. 构建初始 messages（历史 + 当前输入）
        messages = build_initial_messages(chat_in.content, history)

        # 5. Agent 流式执行（混合模式：updates 拿工具轨迹 + messages 拿 token）
        answer_parts: list[str] = []
        tool_calls: list[str] = []
        seen_nodes: set[str] = set()
        yield {"type": "conversation_id", "content": conversation.id}

        for mode, event in bundle.agent.stream(
            {"messages": messages},
            stream_mode=["updates", "messages"],
        ):
            if mode == "updates":
                self._collect_tool_names(event, tool_calls)
            elif mode == "messages":
                chunk = self._extract_token(event, seen_nodes)
                if chunk:
                    answer_parts.append(chunk)
                    yield {"type": "token", "content": chunk}

        # 6. 保存 assistant 消息 + 生成精确引用来源
        answer: str = "".join(answer_parts)
        if not answer:
            logger.warning(
                "chat streamed no token, conv_id=%s nodes=%s",
                conversation.id,
                sorted(seen_nodes),
            )
        sources: list[SourceInfo] = self._dedup_sources(bundle.retrieved_hits)

        self._message_repository.create(
            conversation.id,
            "assistant",
            answer,
            sources=[source.model_dump() for source in sources] if sources else None,
        )

        # 7. 把本轮问答追加进历史缓存，下一轮无需再查库
        self._refresh_history_cache(conversation.id, history_rows, chat_in.content, answer)

        logger.info(
            "chat done, conv_id=%s tokens=%d sources=%d tools=%s",
            conversation.id,
            len(answer_parts),
            len(sources),
            ",".join(tool_calls) if tool_calls else "-",
        )
        if sources:
            yield {"type": "sources", "content": [s.model_dump() for s in sources]}
        yield {"type": "done"}

    # ── 历史缓存 ──────────────────────────────────────────────

    def _load_history_rows(self, conversation_id: int) -> list[dict[str, str]]:
        """读取最近对话历史，优先命中 Redis 缓存，未命中再查库并回填。"""

        key: str = history_key(conversation_id)
        cached: Any = cache.get_json(key)
        if cached is not None:
            logger.info("history cache hit, conv_id=%s", conversation_id)
            return cached

        messages = self._message_repository.list_by_conversation_id(conversation_id)
        rows: list[dict[str, str]] = [
            {"role": message.role, "content": message.content}
            for message in messages[-HISTORY_LIMIT:]
        ]
        cache.set_json(key, rows, HISTORY_TTL_SECONDS)
        return rows

    def _refresh_history_cache(
        self,
        conversation_id: int,
        history_rows: list[dict[str, str]],
        question: str,
        answer: str,
    ) -> None:
        """把本轮问答追加进历史缓存，省去下一轮的历史查询。"""

        updated: list[dict[str, str]] = history_rows + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
        cache.set_json(history_key(conversation_id), updated[-HISTORY_LIMIT:], HISTORY_TTL_SECONDS)

    @staticmethod
    def _to_messages(history_rows: list[dict[str, str]]) -> list[BaseMessage]:
        """把缓存中的角色与内容转换成 LangChain 消息对象。"""

        history: list[BaseMessage] = []
        for row in history_rows:
            if row["role"] == "user":
                history.append(HumanMessage(content=row["content"]))
            elif row["role"] == "assistant":
                history.append(AIMessage(content=row["content"]))
        return history

    # ── 辅助方法 ──────────────────────────────────────────────

    @staticmethod
    def _collect_tool_names(event: dict, tool_calls: list[str]) -> None:
        """从 updates 事件中收集本轮实际调用的工具名，用于链路日志。"""

        for node_name, node_output in event.items():
            if node_name != "tools":
                continue
            for msg in node_output.get("messages", []):
                if isinstance(msg, ToolMessage):
                    tool_calls.append(getattr(msg, "name", "") or "unknown")

    @staticmethod
    def _extract_token(event: tuple[Any, dict[str, Any]], seen_nodes: set[str]) -> str | None:
        """从 messages 事件中提取 token chunk，只保留主回答节点的输出。

        Agent 图内的工具会自己调用 LLM（例如检索前的查询改写），这些调用同样
        以 messages 事件流出。若只按消息类型过滤，工具内部的原始输出会被当成
        回答推给前端，表现为回答开头多出一段 ``​```json [...]`` 中间产物。
        """

        msg, metadata = event

        node: str | None = metadata.get("langgraph_node")
        if node is not None:
            seen_nodes.add(node)
            if node != ANSWER_NODE:
                return None

        is_aimessage = isinstance(msg, (AIMessage, AIMessageChunk))
        if (
            is_aimessage
            and msg.content
            and isinstance(msg.content, str)
            and not getattr(msg, "tool_calls", None)
            and not msg.additional_kwargs.get("tool_calls")
        ):
            return msg.content
        return None

    @staticmethod
    def _dedup_sources(hits: list[SourceInfo]) -> list[SourceInfo]:
        """按文档 ID 与分块序号去重，保留首次命中的顺序。"""

        seen: set[tuple[int, int]] = set()
        sources: list[SourceInfo] = []
        for hit in hits:
            key: tuple[int, int] = (hit.document_id, hit.chunk_index)
            if key in seen:
                continue
            seen.add(key)
            sources.append(hit)
        return sources

    def _get_or_create_conversation(self, user: User, conversation_id: int | None) -> Conversation:
        """获取或创建会话。"""

        if conversation_id is None:
            return self._conversation_repository.create(user.id, "新对话")

        conversation: Conversation | None = self._conversation_repository.get_by_user_id(
            user.id, conversation_id
        )
        if conversation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
        return conversation
