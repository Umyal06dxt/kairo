"""Foreground agent: speculative-answer lookup, cache-first retrieval, streamed LLM answer.

Speculate-then-verify (RaLMSpec-style): on a cache hit the LLM starts immediately with cached
context while the vector-store search runs in parallel. The search (~100 ms) finishes before the
LLM's first token (~1 s), so verification is free on the critical path; if the store's top result
is not in the context we cancel before any token is spoken and regenerate from the right chunks.
Answers then match traditional RAG while verified hits keep the cache's latency."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .answer_cache import AnswerCache
from .cache import SemanticCache
from .config import Config
from .events import PriorityRetrieval
from .providers.base import LLM, Embedder, VectorStore
from .rerank import rerank
from .stream import ConversationStream
from .telemetry import Telemetry
from .types import Retrieved

log = logging.getLogger(__name__)


@dataclass
class TurnResult:
    answer: str
    hit: bool = False
    source: str = "none"  # "draft" (pre-drafted answer) | "cache" | "store" | "none"
    retrieval_ms: float = 0.0
    embed_ms: float = 0.0
    store_failed: bool = False
    llm_first_token_ms: float | None = None  # from LLM call start; 0 for a pre-drafted answer
    chunk_ids: list[str] = field(default_factory=list)  # evidence the answer was built from
    tags: list[str] = field(default_factory=list)  # provenance of cached evidence used
    draft_sim: float | None = None  # question-question similarity for a pre-drafted answer
    verified: bool | None = None  # True/False when speculate-then-verify ran, else None
    corrected: bool = False  # a speculative cache/draft answer was rejected and regenerated


class FastTalker:
    def __init__(self, embedder: Embedder, llm: LLM, store: VectorStore,
                 cache: SemanticCache, stream: ConversationStream, config: Config,
                 answers: AnswerCache | None = None, telemetry: Telemetry | None = None):
        self.embedder, self.llm, self.store = embedder, llm, store
        self.cache, self.stream, self.config = cache, stream, config
        self.answers = answers
        self.telemetry = telemetry or Telemetry()

    async def embed_query(self, question: str) -> tuple[np.ndarray, float]:
        """Embed once; the router shares the vector with the Slow Thinker."""
        t0 = time.perf_counter()
        embed = getattr(self.embedder, "embed_queries", self.embedder.embed)
        vec = (await embed([question]))[0]
        return vec, (time.perf_counter() - t0) * 1000

    async def _search(self, vec: np.ndarray) -> list[Retrieved] | None:
        """Vector-store search; None if the store failed (callers degrade gracefully)."""
        try:
            return await self.store.search(vec, self.config.prefetch_top_k)
        except Exception:
            log.exception("vector store search failed")
            return None

    async def answer(self, question: str, on_token: Callable[[str], None] | None = None,
                     vec: np.ndarray | None = None, embed_ms: float = 0.0) -> TurnResult:
        """`vec`/`embed_ms`: precomputed query embedding (skips the embedding call)."""
        question = question.strip()
        if not question:
            return TurnResult(answer="")
        cfg = self.config
        if vec is None:
            vec, embed_ms = await self.embed_query(question)

        t0 = time.perf_counter()
        found = self.cache.get(vec, k=cfg.max_context_chunks, tau=cfg.similarity_threshold)
        if cfg.lexical_rerank:
            found = rerank(question, found)

        # Speculate-then-verify: kick off the store search now so it overlaps with generation.
        verify_task = (asyncio.create_task(self._search(vec))
                       if cfg.verify_hits and cfg.fallback_to_store and found else None)
        verified: list[Retrieved] | None = None  # store results once awaited

        # 1. Pre-drafted answer for a predicted question: trusted only if the question matches
        #    closely AND the draft's evidence is retrievable (and, if enabled, store-verified).
        if self.answers is not None and cfg.speculative_answers:
            match = self.answers.get(vec, cfg.answer_threshold)
            if match is not None:
                draft, sim = match
                evidence = {r.chunk.id for r in found[: cfg.llm_context_chunks]}
                if evidence & set(draft.chunk_ids):
                    ok = True
                    if verify_task is not None:
                        verified = await verify_task
                        ok = (not verified) or verified[0].chunk.id in draft.chunk_ids
                    if ok:
                        draft.uses += 1
                        if on_token:
                            for w in draft.answer.split(" "):
                                on_token(w + " ")
                        return TurnResult(
                            answer=draft.answer, hit=True, source="draft", embed_ms=embed_ms,
                            retrieval_ms=(time.perf_counter() - t0) * 1000, llm_first_token_ms=0.0,
                            chunk_ids=list(draft.chunk_ids), tags=["draft"], draft_sim=sim,
                            verified=True if verify_task is not None else None)
                    # rejected: the store disagrees with the draft's evidence -> regenerate
                    return await self._corrected(question, on_token, vec, embed_ms, verified, t0)

        # 2. Chunk cache hit, else fall back to the vector store.
        result = TurnResult(answer="", embed_ms=embed_ms)
        if found:
            result.hit, result.source = True, "cache"
        elif cfg.fallback_to_store:
            result.source = "store"
            found = await self._fallback(vec, question, result)
            if cfg.lexical_rerank:
                found = rerank(question, found)
        result.retrieval_ms = (time.perf_counter() - t0) * 1000

        used = found[: cfg.llm_context_chunks]
        result.chunk_ids = [r.chunk.id for r in used]
        result.tags = [r.tag for r in used]
        used_ids = set(result.chunk_ids)

        async def gate() -> bool:  # runs when the first token arrives, before it is emitted
            nonlocal verified
            if verified is None:
                verified = await verify_task
            return (not verified) or verified[0].chunk.id in used_ids

        t1 = time.perf_counter()
        text = await self._stream(question, [r.chunk for r in used], on_token, result, t1,
                                  gate if (verify_task is not None and result.hit) else None)
        if text is not None:
            if verify_task is not None and result.hit:
                result.verified = True
            result.answer = text
            return result
        # Verification failed before any token was spoken: regenerate from the store's chunks.
        return await self._corrected(question, on_token, vec, embed_ms, verified, t0, t1)

    async def _stream(self, question, context, on_token, result: TurnResult, t1: float,
                      gate=None) -> str | None:
        """Stream the LLM answer. If `gate` is given it must approve before the first token is
        emitted; returns None when the gate rejects (the stream is closed, nothing was spoken)."""
        parts: list[str] = []
        agen = self.llm.stream_answer(question, context, self.stream.history())
        try:
            async for tok in agen:
                if not parts:
                    if result.llm_first_token_ms is None:
                        result.llm_first_token_ms = (time.perf_counter() - t1) * 1000
                    if gate is not None and not await gate():
                        return None
                parts.append(tok)
                if on_token:
                    on_token(tok)
        finally:
            aclose = getattr(agen, "aclose", None)
            if aclose is not None:
                await aclose()
        return "".join(parts)

    async def _corrected(self, question, on_token, vec, embed_ms, verified, t0,
                         t1: float | None = None) -> TurnResult:
        """A speculative answer was rejected: answer from the store's chunks (= traditional RAG)."""
        cfg = self.config
        result = TurnResult(answer="", source="store", embed_ms=embed_ms, verified=False,
                            corrected=True)
        found = verified or []
        if cfg.cache_on_miss:
            for r in found:
                self.cache.put(r.chunk, r.embedding, r.score, tag="miss")
        await self.stream.publish(PriorityRetrieval(query=question, embedding=vec))
        if cfg.lexical_rerank:
            found = rerank(question, found)
        used = found[: cfg.llm_context_chunks]
        result.retrieval_ms = (time.perf_counter() - t0) * 1000
        result.chunk_ids = [r.chunk.id for r in used]
        result.tags = [r.tag for r in used]
        t1 = t1 if t1 is not None else time.perf_counter()
        text = await self._stream(question, [r.chunk for r in used], on_token, result, t1)
        result.answer = text or ""
        self.telemetry.emit("fast.corrected", question=question, chunk_ids=result.chunk_ids)
        return result

    async def _fallback(self, vec, question: str, result: TurnResult) -> list[Retrieved]:
        found = await self._search(vec)
        if found is None:
            result.store_failed = True
            return []
        if self.config.cache_on_miss:
            for r in found:
                self.cache.put(r.chunk, r.embedding, r.score, tag="miss")
        await self.stream.publish(PriorityRetrieval(query=question, embedding=vec))
        return found
