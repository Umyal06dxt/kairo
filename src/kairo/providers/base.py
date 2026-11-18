from dataclasses import dataclass
from typing import AsyncIterator, Protocol

import numpy as np

from ..types import Chunk, Retrieved

History = list[tuple[str, str]]


@dataclass
class Prediction:
    topic: str  # document-style description (used to prefetch chunks)
    question: str | None = None  # standalone question the user may ask (used to pre-draft an answer)


class Embedder(Protocol):
    dim: int

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) float32 array of L2-normalised vectors."""


class LLM(Protocol):
    async def predict_topics(self, history: History, n: int) -> list[str]:
        """Predict n likely follow-up topics as document-style descriptions."""

    def stream_answer(self, question: str, context: list[Chunk],
                      history: History) -> AsyncIterator[str]:
        """Stream answer tokens grounded in `context`."""

    # Optional (looked up with getattr): predict_followups(history, n) -> list[Prediction],
    # draft_answer(question, context) -> str, warmup() -> None


class VectorStore(Protocol):
    async def search(self, vec: np.ndarray, k: int) -> list[Retrieved]: ...

    async def add(self, chunks: list[Chunk], embeddings: np.ndarray) -> None: ...
