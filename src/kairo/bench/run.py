"""Benchmark: traditional RAG vs the dual-agent cache over the 10 scenarios.

Modes
- offline: HashEmbedder + EchoLLM (predicts nothing new), simulated store latency.
  Validates plumbing and measures *reactive* caching only. Hit rates here say
  nothing about the paper's numbers.
- live: OpenAI embeddings + LLM predictions, FAISS/Qdrant store with real or
  injected latency. This is the mode comparable to the paper.
"""

import asyncio
import os
import random
import time
from dataclasses import dataclass, field, replace
from typing import AsyncIterator

from ..config import Config
from ..ingest import chunk_documents
from ..providers.base import LLM, Embedder, VectorStore
from ..providers.fake import DelayedStore, HashEmbedder, InMemoryStore
from ..router import MemoryRouter
from .kb import NOVACRM_DOCS
from .scenarios import SCENARIOS

DEPTH_BINS = [(1, 4), (5, 9), (10, 14), (15, 20)]


@dataclass
class TurnRec:
    scenario: str
    turn: int  # 1-based
    hit: bool
    retrieval_ms: float


@dataclass
class Report:
    mode: str
    tau: float
    baseline_ms: float
    turns: list[TurnRec] = field(default_factory=list)

    def _rate(self, recs: list[TurnRec]) -> float:
        return sum(r.hit for r in recs) / len(recs) if recs else 0.0

    @property
    def hit_rate(self) -> float:
        return self._rate(self.turns)

    @property
    def warm_hit_rate(self) -> float:
        return self._rate([r for r in self.turns if r.turn >= 2])

    @property
    def hit_ms(self) -> float:
        hits = [r.retrieval_ms for r in self.turns if r.hit]
        return sum(hits) / len(hits) if hits else float("nan")

    @property
    def speedup(self) -> float:
        return self.baseline_ms / self.hit_ms if self.hit_ms == self.hit_ms and self.hit_ms > 0 \
            else float("nan")

    @property
    def saved_ms(self) -> float:
        return sum(self.baseline_ms - r.retrieval_ms for r in self.turns if r.hit)

    def by_scenario(self) -> list[tuple[str, float, int, int]]:
        out = []
        for name in SCENARIOS:
            recs = [r for r in self.turns if r.scenario == name]
            out.append((name, self._rate(recs), sum(r.hit for r in recs), len(recs)))
        return sorted(out, key=lambda x: -x[1])

    def by_depth(self) -> list[tuple[str, float, int, int]]:
        out = []
        for lo, hi in DEPTH_BINS:
            recs = [r for r in self.turns if lo <= r.turn <= hi]
            out.append((f"{lo}-{hi}", self._rate(recs), sum(r.hit for r in recs), len(recs)))
        return out


class EchoLLM:
    """Offline stand-in: 'predicts' the latest utterance (no new information), so the
    offline run measures reactive caching only. Answers are empty."""

    async def predict_topics(self, history, n):
        users = [t for r, t in history if r == "user"]
        return users[-1:] if users else []

    async def stream_answer(self, question, context, history) -> AsyncIterator[str]:
        return
        yield  # pragma: no cover  (makes this an async generator)


class AnswerlessLLM:
    """Real predictions, no answer generation: the benchmark's primary metric is
    retrieval, and skipping generation saves cost and removes LLM-latency noise."""

    def __init__(self, inner: LLM):
        self.inner = inner

    async def predict_topics(self, history, n):
        return await self.inner.predict_topics(history, n)

    async def stream_answer(self, question, context, history) -> AsyncIterator[str]:
        return
        yield  # pragma: no cover


async def build_store(embedder: Embedder, store: VectorStore) -> VectorStore:
    chunks = chunk_documents(list(NOVACRM_DOCS.items()))
    for i in range(0, len(chunks), 64):
        part = chunks[i:i + 64]
        await store.add(part, await embedder.embed([c.text for c in part]))
    return store


async def measure_baseline(embedder: Embedder, store: VectorStore, k: int) -> float:
    """Traditional RAG retrieval latency: mean store.search time over all queries."""
    queries = [q for qs in SCENARIOS.values() for q in qs]
    vecs = await embedder.embed(queries)
    total = 0.0
    for v in vecs:
        t0 = time.perf_counter()
        await store.search(v, k)
        total += time.perf_counter() - t0
    return total / len(queries) * 1000


async def _run_scenario(name: str, questions: list[str], embedder, llm, store,
                        config: Config, think_s: tuple[float, float],
                        seed: int) -> list[TurnRec]:
    rng = random.Random(seed)
    router = MemoryRouter.create(embedder, llm, store, config)
    await router.start()
    recs = []
    try:
        for i, q in enumerate(questions, start=1):
            r = await router.handle_utterance(q)
            recs.append(TurnRec(name, i, r.hit, r.retrieval_ms))
            await asyncio.sleep(rng.uniform(*think_s))  # user listens/thinks; Slow Thinker works
    finally:
        await router.stop()
    return recs


async def run_dual(embedder, llm, store, config: Config, think_s, concurrency: int = 10,
                   seed: int = 0) -> list[TurnRec]:
    sem = asyncio.Semaphore(concurrency)

    async def one(i, name, qs):
        async with sem:
            return await _run_scenario(name, qs, embedder, llm, store, config, think_s, seed + i)

    runs = await asyncio.gather(*(one(i, n, q) for i, (n, q) in enumerate(SCENARIOS.items())))
    return [r for run in runs for r in run]


async def run_benchmark(mode: str = "offline", config: Config = Config(),
                        taus: list[float] | None = None, store_latency_s: float | None = None,
                        think_s: tuple[float, float] | None = None, concurrency: int = 10,
                        generate: bool = False, qdrant: bool = False) -> list[Report]:
    """Returns one Report per tau (default: just config.similarity_threshold)."""
    if mode == "offline":
        embedder: Embedder = HashEmbedder(dim=512)
        llm: LLM = EchoLLM()
        latency = 0.01 if store_latency_s is None else store_latency_s
        think_s = think_s or (0.05, 0.15)
        store = await build_store(embedder, InMemoryStore(embedder.dim, latency_s=latency))
    elif mode == "live":
        from ..providers.faiss_store import FaissStore
        from ..providers.openai_ import OpenAIEmbedder, OpenAILLM
        embedder = OpenAIEmbedder()
        real = OpenAILLM(temperature=config.temperature)
        llm = real if generate else AnswerlessLLM(real)
        think_s = think_s or (3.0, 7.0)
        if qdrant:
            from ..providers.qdrant_ import QdrantStore
            store = await build_store(embedder, QdrantStore(
                embedder.dim, "kairo-bench", os.environ["QDRANT_URL"],
                os.environ.get("QDRANT_API_KEY")))
        else:  # local FAISS is ~0.1 ms, so inject the paper's remote-DB latency (~110 ms)
            latency = 0.110 if store_latency_s is None else store_latency_s
            store = DelayedStore(await build_store(embedder, FaissStore(embedder.dim)), latency)
    else:
        raise ValueError(f"unknown mode {mode!r}")

    baseline = await measure_baseline(embedder, store, config.prefetch_top_k)
    reports = []
    for tau in taus or [config.similarity_threshold]:
        recs = await run_dual(embedder, llm, store, replace(config, similarity_threshold=tau),
                              think_s, concurrency)
        reports.append(Report(mode, tau, baseline, recs))
    return reports


def format_report(reports: list[Report]) -> str:
    main = next((r for r in reports if abs(r.tau - Config().similarity_threshold) < 1e-9),
                reports[0])
    n = len(main.turns)
    hits = sum(r.hit for r in main.turns)
    warm = [r for r in main.turns if r.turn >= 2]
    L = [f"# Kairo benchmark — mode: **{main.mode}**, tau={main.tau:.2f}, {n} queries", ""]
    if main.mode == "offline":
        L += ["> OFFLINE: hash embeddings + no-prediction stub. Validates plumbing and measures "
              "reactive caching only; NOT comparable to the paper's numbers.", ""]
    L += ["## Overall", "| Metric | Traditional RAG | Kairo |", "|---|---|---|",
          f"| Retrieval latency (avg) | {main.baseline_ms:.1f} ms | {main.hit_ms:.2f} ms (hits) |",
          f"| Retrieval speedup | 1x | {main.speedup:.0f}x |",
          f"| Cache hit rate (overall) | — | {main.hit_rate:.0%} ({hits}/{n}) |",
          f"| Cache hit rate (warm, turn>=2) | — | {main.warm_hit_rate:.0%} "
          f"({sum(r.hit for r in warm)}/{len(warm)}) |",
          f"| Total retrieval time saved | — | {main.saved_ms:.0f} ms |", "",
          "## By scenario", "| Scenario | Hit rate |", "|---|---|"]
    L += [f"| {nm} | {rate:.0%} ({h}/{t}) |" for nm, rate, h, t in main.by_scenario()]
    L += ["", "## By conversation depth", "| Turns | Hit rate |", "|---|---|"]
    L += [f"| {b} | {rate:.0%} ({h}/{t}) |" for b, rate, h, t in main.by_depth()]
    if len(reports) > 1:
        L += ["", "## Threshold sweep", "| tau | Hit rate |", "|---|---|"]
        L += [f"| {r.tau:.2f} | {r.hit_rate:.0%} |" for r in sorted(reports, key=lambda r: -r.tau)]
    return "\n".join(L)
