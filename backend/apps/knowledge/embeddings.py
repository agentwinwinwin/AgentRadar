import hashlib
import math
import re
from typing import Protocol

from django.conf import settings


class EmbeddingClient(Protocol):
    model: str
    version: str
    dimensions: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class LocalHashingEmbeddingClient:
    """Deterministic, local, versioned baseline with no external content disclosure."""

    model = settings.KNOWLEDGE_EMBEDDING_MODEL
    version = settings.KNOWLEDGE_EMBEDDING_VERSION
    dimensions = settings.KNOWLEDGE_EMBEDDING_DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[\w+#.-]+", text.casefold())
        for token in tokens:
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


def embedding_client() -> EmbeddingClient:
    if settings.KNOWLEDGE_EMBEDDING_PROVIDER != "local_hashing":
        raise ValueError("unsupported embedding provider")
    return LocalHashingEmbeddingClient()
