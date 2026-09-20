"""LLM 客户端初始化：大语言模型服务。"""

from collections.abc import Generator

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

from app.config.settings import settings


class LLMService:
    """大语言模型服务。"""

    def __init__(self) -> None:
        self._llm: ChatOpenAI = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            streaming=True,
        )

    @property
    def llm(self) -> ChatOpenAI:
        """获取底层 LangChain LLM 实例（供 Agent 使用）。"""
        return self._llm

    def stream_chat(self, messages: list[BaseMessage]) -> Generator[str, None, None]:
        """流式对话，逐 token 产出文本。"""
        for chunk in self._llm.stream(messages):
            content: object = chunk.content
            if isinstance(content, str) and content:
                yield content


llm_service: LLMService = LLMService()
