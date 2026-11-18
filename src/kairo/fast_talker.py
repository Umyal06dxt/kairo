"""Foreground agent: cache-first retrieval, then a streamed LLM answer."""

import logging
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .cache import SemanticCache
from .config import Config
from .events import PriorityRetrieval
from .providers.base import LLM, Embedder, VectorStore
from .stream import ConversationStream
from .types import Retrieved

log = logging.getLogger(__name__)


@dataclass
class TurnResult:
    answer: str
    hit: bool = False
    source: str = "none"  # "cache" | "store" | "none"
    retrieval_ms: float = 0.0
    embed_ms: float = 0.0
    store_failed: bool = False
    llm_first_token_ms: float | None = None  # from LLM call start; None if no tokens


class FastTalker:
    def __init__(self, embedder: Embedder, llm: LLM, store: VectorStore,
                 cache: SemanticCache, stream: ConversationStream, config: Config):
        self.embedder, self.llm, self.store = embedder, llm, store
        self.cache, self.stream, self.config = cache, stream, config

    async def embed_query(self, question: str) -> tuple["np.ndarray", float]:
        """Embed once; the router shares the vector with the Slow Thinker."""
        t0 = time.perf_counter()
        vec = (await self.embedder.embed([question]))[0]
        return vec, (time.perf_counter() - t0) * 1000

    async def answer(self, question: str, on_token: Callable[[str], None] | None = None,
                     vec: "np.ndarray | None" = None, embed_ms: float = 0.0) -> TurnResult:
        """`vec`/`embed_ms`: precomputed query embedding (skips the embedding call)."""
        question = question.strip()
        if not question:
            return TurnResult(answer="")
        cfg = self.config

        if vec is None:
            vec, embed_ms = await self.embed_query(question)

        t0 = time.perf_counter()
        found = self.cache.get(vec, k=cfg.max_context_chunks, tau=cfg.similarity_threshold)
        result = TurnResult(answer="", embed_ms=embed_ms)
        if found:
            result.hit, result.source = True, "cache"
        elif cfg.fallback_to_store:
            result.source = "store"
            found = await self._fallback(vec, question, result)
        result.retrieval_ms = (time.perf_counter() - t0) * 1000

        context = [r.chunk for r in found[: cfg.max_context_chunks]]
        parts: list[str] = []
        t0 = time.perf_counter()
        async for tok in self.llm.stream_answer(question, context, self.stream.history()):
            if not parts:
                result.llm_first_token_ms = (time.perf_counter() - t0) * 1000
            parts.append(tok)
            if on_token:
                on_token(tok)
        result.answer = "".join(parts)
        return result

    async def _fallback(self, vec, question: str, result: TurnResult) -> list[Retrieved]:
        try:
            found = await self.store.search(vec, self.config.prefetch_top_k)
        except Exception:
            log.exception("vector store failed on cache miss; answering without context")
            result.store_failed = True
            return []
        if self.config.cache_on_miss:
            for r in found:
                self.cache.put(r.chunk, r.embedding, r.score)
        await self.stream.publish(PriorityRetrieval(query=question, embedding=vec))
        return found
