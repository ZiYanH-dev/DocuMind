"""Agent 组装 — 把 LLM + tools + system prompt 组合成可调用的 Agent"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.agent.tools import build_tools
from app.config.llm_client import llm_service
from app.schemas.chat import SourceInfo

# ── System Prompt ────────────────────────────────────────────

SYSTEM_PROMPT = """你是 DocuMind，一个基于用户个人知识库的 RAG 智能问答助手。

你可以使用以下工具：
- search_knowledge: 在用户上传的知识库中检索文档
- list_documents: 查看用户上传了哪些文档

行为准则：
1. 如果用户只是打招呼、闲聊或让你自我介绍，不需要调用任何工具，直接回答。
2. 只要问题属于知识类提问，就必须先调用 search_knowledge 检索知识库，再基于检索到的内容组织回答；检索不到相关内容时说明没有找到，然后按通用知识回答。
3. 如果用户提到"我的文档"、"我的知识库"，先调用 list_documents 看看有什么。
4. 回答要简洁、有条理，并标注引用来源（文档名与片段位置）。
5. 如果用户没有上传任何文档，诚实告诉他。"""


# ── 请求级 Agent 上下文 ──────────────────────────────────────


@dataclass
class ChatAgentBundle:
    """一次问答请求的 Agent 与其检索命中收集器。

    retrieved_hits 由 search_knowledge 工具在闭包内写入，
    服务层据此生成带文档 ID 与分块序号的引用来源。
    """

    agent: CompiledStateGraph
    retrieved_hits: list[SourceInfo] = field(default_factory=list)


# ── Agent 工厂 ───────────────────────────────────────────────


def create_chat_agent(session: Session, user_id: int) -> ChatAgentBundle:
    """构建一次请求的聊天 Agent（每次请求新建，因为 tools 闭包绑定了 session）"""

    hits: list[SourceInfo] = []
    tools = build_tools(session, user_id, hits)
    llm = llm_service.llm

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
    return ChatAgentBundle(agent=agent, retrieved_hits=hits)


# ── 便捷调用 ────────────────────────────────────────────────


def build_initial_messages(user_input: str, history: list[Any] | None = None) -> list[Any]:
    """构建传给 agent 的初始 messages 列表"""

    messages: list[Any] = []

    # 历史消息（如果有）
    if history:
        messages.extend(history)

    # 当前用户输入
    messages.append(HumanMessage(content=user_input))
    return messages
