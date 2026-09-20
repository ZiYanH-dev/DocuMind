"""Embedding 客户端初始化：文本向量化服务。"""

from langchain_openai import OpenAIEmbeddings

from app.config.settings import settings


class EmbeddingService:
    """文本向量化服务。"""

    def __init__(self) -> None:
        self._embeddings: OpenAIEmbeddings = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.effective_embedding_api_key,
            base_url=settings.effective_embedding_base_url,
            check_embedding_ctx_length=False,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量向量化文本。"""

        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """向量化查询文本。"""

        return self._embeddings.embed_query(text)


embedding_service: EmbeddingService = EmbeddingService()
