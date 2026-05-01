"""Capa de embeddings — abstrae el provider para poder cambiar a local en el futuro."""
from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from openai import OpenAI

from app.config import get_settings

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072


class EmbeddingProvider(ABC):
    @property
    @abstractmethod
    def dim(self) -> int: ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class OpenAIEmbeddings(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = EMBED_MODEL) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    @property
    def dim(self) -> int:
        return EMBED_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]


@lru_cache(maxsize=1)
def get_embedder() -> EmbeddingProvider:
    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada")
    return OpenAIEmbeddings(api_key=settings.openai_api_key)
