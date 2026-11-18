"""Experiment runner: compare retrieval/answering strategies on a Domain.

Profiles
  baseline   traditional RAG: embed -> vector store -> LLM, every turn
  reactive   chunk cache filled only by misses/direct retrieval (no prediction)
  paper      VoiceAgentRAG as published (LLM topic prediction + chunk cache)
  neighbors  zero-LLM prediction: prefetch chunks near what was just retrieved
  optimized  hybrid prediction + speculative answer cache + smaller LLM context

Metrics beyond hit rate (the paper reports only hit rate and retrieval latency):
  accuracy      answer contains the gold facts (domains with gold only, needs a real LLM)
  evidence      the gold source document was among the chunks the answer used
  fidelity      RaLMSpec-style check: overlap of served top-3 chunks with the vector store's
                exact top-3 -> a *hit that serves the wrong chunks* is not a success
  user_ms       embed + retrieval + LLM first token: the pre-speech wait we can influence
"""

import asyncio
import dataclasses
import os
import random
import time
from dataclasses import asdict, dataclass, field, replace
from typing import AsyncIterator

import numpy as np

from ..config import OPTIMIZED, PAPER, Config, for_embedder
from ..ingest import chunk_documents
from ..providers.base import LLM, Embedder, VectorStore
from ..providers.fake import DelayedStore, ExtractiveLLM, HashEmbedder
from ..router import MemoryRouter
from .domains import Domain, get_domain, score_answer


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    config: Config
    cache: bool = True  # False = traditional RAG


PROFILES: dict[str, Profile] = {p.key: p for p in [
    Profile("baseline", "Traditional RAG (no cache)", PAPER, cache=False),
    Profile("reactive", "Reactive cache (no prediction)", replace(PAPER, strategy="none")),
    Profile("paper", "VoiceAgentRAG (paper)", PAPER),
    Profile("neighbors", "Neighbour prefetch (no LLM)", replace(PAPER, strategy="neighbors")),
    Profile("verified", "Neighbours + verify + rerank (no LLM)",
            replace(PAPER, strategy="neighbors", verify_hits=True, lexical_rerank=True,
                    llm_context_chunks=4)),
    Profile("optimized", "Kairo optimized (verified)", OPTIMIZED),
    Profile("fast", "Kairo fast (unverified)", replace(OPTIMIZED, verify_hits=False)),
]}


@dataclass
class TurnRec:
    scenario: str
    turn: int  # 1-based
    question: str
    source: str  # draft | cache | store | none
    hit: bool
    embed_ms: float
    retrieval_ms: float
    llm_ms: float | None
    answer: str = ""
    chunk_ids: list[str] = field(default_factory=list)
    gold_ok: bool | None = None
    doc_ok: bool | None = None
    fidelity: float | None = None

    @property
    def user_ms(self) -> float:
        return self.embed_ms + self.retrieval_ms + (self.llm_ms or 0.0)


def _pct(xs: list[float], q: float) -> float:
    return float(np.percentile(xs, q)) if xs else float("nan")


def _mean(xs: list[float]) -> float:
    return float(np.mean(xs)) if xs else float("nan")


@dataclass
class Summary:
    n: int
    errors: int
    hit_rate: float
    warm_hit_rate: float
    draft_rate: float
    accuracy: float  # nan when no gold / no generation
    evidence: float
    fidelity: float
    embed_ms: float
    retrieval_ms: float  # mean over all turns
    hit_retrieval_ms: float  # mean over cache/draft hits
    llm_ms: float
    user_p50: float
    user_p90: float

    @classmethod
    def of(cls, all_recs: list[TurnRec]) -> "Summary":
        recs = [r for r in all_recs if r.source != "error"]
        warm = [r for r in recs if r.turn >= 2]
        hits = [r for r in recs if r.hit]
        rate = lambda xs: (sum(1 for x in xs if x) / len(xs)) if xs else float("nan")  # noqa: E731
        return cls(
            n=len(recs), errors=len(all_recs) - len(recs), hit_rate=rate([r.hit for r in recs]),
            warm_hit_rate=rate([r.hit for r in warm]),
            draft_rate=rate([r.source == "draft" for r in recs]),
            accuracy=rate([r.gold_ok for r in recs if r.gold_ok is not None]),
            evidence=rate([r.doc_ok for r in recs if r.doc_ok is not None]),
            fidelity=_mean([r.fidelity for r in hits if r.fidelity is not None]),
            embed_ms=_mean([r.embed_ms for r in recs]),
            retrieval_ms=_mean([r.retrieval_ms for r in recs]),
            hit_retrieval_ms=_mean([r.retrieval_ms for r in hits]),
            llm_ms=_mean([r.llm_ms for r in recs if r.llm_ms is not None]),
            user_p50=_pct([r.user_ms for r in recs], 50),
            user_p90=_pct([r.user_ms for r in recs], 90))


class AnswerlessLLM:
    """Real predictions/drafts but no answer generation (cheaper; disables accuracy scoring)."""

    def __init__(self, inner: LLM):
        self.inner = inner

    def __getattr__(self, name):  # predict_topics / predict_followups / draft_answer / warmup
        return getattr(self.inner, name)

    async def stream_answer(self, question, context, history) -> AsyncIterator[str]:
        return
        yield  # pragma: no cover


@dataclass
class Env:
    embedder: Embedder
    llm: LLM
    store: VectorStore  # as seen by the agents (with simulated latency, if any)
    raw_store: VectorStore  # undelayed, for exact-top-k verification
    label: str
    gold_scoring: bool
    notes: list[str]


async def _embed_docs(embedder, texts):
    return await embedder.embed(texts)


async def make_env(domain: Domain, embedder: str = "hash", llm: str = "extractive",
                   generate: bool = True, store_latency_s: float = 0.110,
                   qdrant: bool = False, distractors: int = 0, llm_ttft_s: float = 0.4) -> Env:
    notes: list[str] = []
    if embedder == "hash":
        emb: Embedder = HashEmbedder(dim=512)
        notes.append("hash embeddings: retrieval quality is not representative")
    elif embedder == "local":
        from ..providers.local import LocalEmbedder
        emb = LocalEmbedder()
    elif embedder == "openai":
        from ..providers.openai_ import OpenAIEmbedder
        emb = OpenAIEmbedder()
    else:
        raise ValueError(f"unknown embedder {embedder!r}")

    if llm == "extractive":
        model: LLM = ExtractiveLLM(ttft_s=llm_ttft_s)
        notes.append(f"extractive stand-in LLM (simulated {llm_ttft_s * 1000:.0f} ms first token; real GPT measured ~1200 ms): "
                     "no follow-up prediction, so only the none/neighbors strategies are meaningful; "
                     "answers are copied sentences")
    elif llm == "openai":
        from ..providers.openai_ import OpenAILLM
        model = OpenAILLM()
    else:
        raise ValueError(f"unknown llm {llm!r}")
    if not generate:
        model = AnswerlessLLM(model)
        notes.append("answer generation disabled (accuracy not measured)")

    docs = dict(domain.docs)
    if distractors:
        from .distractors import load_distractors
        docs.update(load_distractors(distractors))
        notes.append(f"{distractors} near-domain distractor pages added (GPT-written, same credit union)")
    chunks = chunk_documents(list(docs.items()))
    notes.append(f"{len(chunks)} chunks indexed ({len(domain.docs)} domain docs)")
    if qdrant:
        from ..providers.qdrant_ import QdrantStore
        raw: VectorStore = QdrantStore(emb.dim, f"kairo-{domain.key}", os.environ["QDRANT_URL"],
                                       os.environ.get("QDRANT_API_KEY"))
        notes.append("real Qdrant latency")
        store: VectorStore = raw
    else:
        from ..providers.faiss_store import FaissStore
        raw = FaissStore(emb.dim)
        store = DelayedStore(raw, store_latency_s) if store_latency_s > 0 else raw
        if store_latency_s > 0:
            notes.append(f"vector store latency simulated at {store_latency_s * 1000:.0f} ms")
    vecs = await emb.embed([c.text for c in chunks])
    for i in range(0, len(chunks), 64):
        await raw.add(chunks[i:i + 64], vecs[i:i + 64])
    label = f"embedder={embedder}, llm={llm}{'' if generate else ' (no answers)'}"
    return Env(emb, model, store, raw, label, generate and llm != "extractive", notes)


async def _embed_queries(embedder, texts):
    fn = getattr(embedder, "embed_queries", embedder.embed)
    return await fn(texts)


async def _llm_answer(llm, question, context, history) -> tuple[str, float | None]:
    parts: list[str] = []
    t0 = time.perf_counter()
    first = None
    async for tok in llm.stream_answer(question, context, history):
        if first is None:
            first = (time.perf_counter() - t0) * 1000
        parts.append(tok)
    return "".join(parts), first


def _error_rec(name: str, i: int, q: str) -> TurnRec:
    return TurnRec(name, i, q, "error", False, 0.0, 0.0, None)


async def _run_baseline_scenario(name, turns, env: Env, k: int, max_ctx: int) -> list[TurnRec]:
    recs = []
    for i, t in enumerate(turns, start=1):
        try:
            recs.append(await _baseline_turn(name, i, t, env, k, max_ctx))
        except Exception:  # a transient network/API failure must not abort the whole run
            recs.append(_error_rec(name, i, t.q))
    return recs


async def _baseline_turn(name, i, t, env: Env, k: int, max_ctx: int) -> TurnRec:
    t0 = time.perf_counter()
    vec = (await _embed_queries(env.embedder, [t.q]))[0]
    embed_ms = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    found = await env.store.search(vec, k)
    retrieval_ms = (time.perf_counter() - t0) * 1000
    used = found[:max_ctx]
    answer, first = await _llm_answer(env.llm, t.q, [r.chunk for r in used], [])
    return TurnRec(name, i, t.q, "store", False, embed_ms, retrieval_ms, first, answer,
                   [r.chunk.id for r in used])


async def _run_cached_scenario(name, turns, env: Env, config: Config,
                               think_s: tuple[float, float], seed: int) -> list[TurnRec]:
    rng = random.Random(seed)
    router = MemoryRouter.create(env.embedder, env.llm, env.store, config)
    await router.start()
    recs = []
    try:
        for i, t in enumerate(turns, start=1):
            try:
                r = await router.handle_utterance(t.q)
                recs.append(TurnRec(name, i, t.q, r.source, r.hit, r.embed_ms, r.retrieval_ms,
                                    r.llm_first_token_ms, r.answer, list(r.chunk_ids)))
            except Exception:  # transient failure: record it and keep the conversation going
                recs.append(_error_rec(name, i, t.q))
            await asyncio.sleep(rng.uniform(*think_s))  # user listens/thinks; Slow Thinker works
    finally:
        await router.stop()
    return recs


async def run_profile(domain: Domain, profile: Profile, env: Env, think_s: tuple[float, float],
                      concurrency: int = 8, seed: int = 0) -> list[TurnRec]:
    sem = asyncio.Semaphore(concurrency)
    cfg = profile.config

    async def one(i, name, turns):
        async with sem:
            if not profile.cache:
                return await _run_baseline_scenario(name, turns, env, cfg.prefetch_top_k,
                                                    cfg.llm_context_chunks)
            return await _run_cached_scenario(name, turns, env, cfg, think_s, seed + i)

    runs = await asyncio.gather(*(one(i, n, t) for i, (n, t) in enumerate(domain.scenarios.items())))
    recs = [r for run in runs for r in run]
    await _annotate(domain, env, recs)
    return recs


async def _annotate(domain: Domain, env: Env, recs: list[TurnRec]) -> None:
    """Post-hoc scoring (off the critical path): gold facts, evidence, and fidelity vs exact."""
    gold = {t.q: t for turns in domain.scenarios.values() for t in turns}
    qvecs = await _embed_queries(env.embedder, list({r.question for r in recs}))
    index = {q: v for q, v in zip(list({r.question for r in recs}), qvecs)}
    exact: dict[str, list[str]] = {}
    for q, v in index.items():
        exact[q] = [x.chunk.id for x in await env.raw_store.search(v, 3)]
    for r in recs:
        if r.source == "error":
            continue
        g = gold.get(r.question)
        if g and g.expect and env.gold_scoring:
            r.gold_ok = score_answer(r.answer, g.expect)
        if g and g.doc:
            r.doc_ok = g.doc in {cid.rsplit(":", 1)[0] for cid in r.chunk_ids}
        want = exact[r.question]
        if want:
            r.fidelity = len(set(r.chunk_ids[:3]) & set(want)) / min(3, len(want))


@dataclass
class ProfileResult:
    profile: Profile
    recs: list[TurnRec]
    summary: Summary


@dataclass
class ExperimentResult:
    domain: str
    env_label: str
    notes: list[str]
    think_s: tuple[float, float]
    results: dict[str, ProfileResult]
    sweep: list[tuple[float, Summary]] | None = None

    def to_json(self) -> dict:
        def clean(o):
            if isinstance(o, float) and o != o:
                return None
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items()}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            return o
        return clean({
            "domain": self.domain, "env": self.env_label, "notes": self.notes,
            "think_s": list(self.think_s),
            "profiles": {k: {"label": r.profile.label, "summary": asdict(r.summary)}
                         for k, r in self.results.items()},
            "sweep": [{"tau": t, "summary": asdict(s)} for t, s in (self.sweep or [])],
        })


async def run_experiment(domain_key: str = "bank", profiles: list[str] | None = None,
                         embedder: str = "hash", llm: str = "extractive", generate: bool = True,
                         think_s: tuple[float, float] | None = None, store_latency_s: float = 0.110,
                         concurrency: int = 8, sweep_profile: str | None = None,
                         taus: list[float] | None = None, qdrant: bool = False,
                         distractors: int = 0, llm_ttft_s: float = 0.4,
                         overrides: dict | None = None, progress=None) -> ExperimentResult:
    domain = get_domain(domain_key)
    env = await make_env(domain, embedder, llm, generate, store_latency_s, qdrant, distractors,
                         llm_ttft_s)
    think_s = think_s or ((3.0, 6.0) if llm == "openai" else (0.1, 0.25))
    warm = getattr(env.llm, "warmup", None)
    await asyncio.gather(env.embedder.embed(["warm up"]), warm() if warm else asyncio.sleep(0),
                         return_exceptions=True)
    results: dict[str, ProfileResult] = {}
    for key in profiles or ["baseline", "paper", "optimized"]:
        if progress:
            progress(f"running {PROFILES[key].label}")
        cfg = for_embedder(PROFILES[key].config, embedder)
        if overrides and PROFILES[key].cache:
            cfg = replace(cfg, **overrides)  # e.g. {"llm_context_chunks": 6}
        prof = replace(PROFILES[key], config=cfg)
        recs = await run_profile(domain, prof, env, think_s, concurrency)
        results[key] = ProfileResult(prof, recs, Summary.of(recs))
        if progress:
            sm = results[key].summary
            progress(f"done {PROFILES[key].label}: hit={sm.hit_rate:.0%} acc={_f(sm.accuracy, '.0%')} "
                     f"user_p50={sm.user_p50:.0f}ms errors={sm.errors}")
    sweep = None
    if sweep_profile:
        sweep = []
        base = replace(PROFILES[sweep_profile],
                       config=for_embedder(PROFILES[sweep_profile].config, embedder))
        for tau in taus or [0.55, 0.50, 0.45, 0.40, 0.35, 0.30]:
            if progress:
                progress(f"sweep tau={tau:.2f}")
            p = replace(base, config=replace(base.config, similarity_threshold=tau))
            sweep.append((tau, Summary.of(await run_profile(domain, p, env, think_s, concurrency))))
    return ExperimentResult(domain_key, env.label, env.notes, think_s, results, sweep)


def _f(x: float, fmt: str) -> str:
    return "—" if x != x else format(x, fmt)


def format_experiment(res: ExperimentResult) -> str:
    tau = next(iter(res.results.values())).profile.config.similarity_threshold
    L = [f"# Kairo experiment — domain **{res.domain}** ({res.env_label}, tau={tau:.2f})", ""]
    L += [f"> {n}" for n in res.notes] + [""]
    L += ["| Profile | Hit rate | Warm | Draft | Accuracy | Evidence | Fidelity | "
          "Embed ms | Hit retr. ms | LLM 1st tok ms | **User p50 ms** | p90 ms |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in res.results.values():
        s = r.summary
        L.append(f"| {r.profile.label} | {_f(s.hit_rate, '.0%')} | {_f(s.warm_hit_rate, '.0%')} | "
                 f"{_f(s.draft_rate, '.0%')} | {_f(s.accuracy, '.0%')} | {_f(s.evidence, '.0%')} | "
                 f"{_f(s.fidelity, '.0%')} | {_f(s.embed_ms, '.0f')} | "
                 f"{_f(s.hit_retrieval_ms, '.2f')} | {_f(s.llm_ms, '.0f')} | "
                 f"**{_f(s.user_p50, '.0f')}** | {_f(s.user_p90, '.0f')} |")
    errs = {r.profile.label: r.summary.errors for r in res.results.values() if r.summary.errors}
    if errs:
        L += ["", f"> ⚠ turns that failed (network/API) and are excluded from the metrics: {errs}"]
    L += ["", "_User ms = embed + retrieval + LLM first token (excludes STT/TTS). "
          "Fidelity = overlap of served top-3 chunks with the store's exact top-3 on cache hits._"]
    if res.sweep:
        L += ["", "## Similarity-threshold sweep", "| tau | Hit rate | Evidence | Fidelity |",
              "|---|---|---|---|"]
        for tau, s in sorted(res.sweep, key=lambda x: -x[0]):
            L.append(f"| {tau:.2f} | {_f(s.hit_rate, '.0%')} | {_f(s.evidence, '.0%')} | "
                     f"{_f(s.fidelity, '.0%')} |")
    return "\n".join(L)


def parse_overrides(spec: str) -> dict:
    """'a=1,b=0.5,c=true' -> typed Config overrides (types taken from the dataclass fields)."""
    types = {f.name: f.type for f in dataclasses.fields(Config)}
    out: dict = {}
    for part in filter(None, (p.strip() for p in spec.split(","))):
        k, _, v = part.partition("=")
        if k not in types:
            raise ValueError(f"unknown config field {k!r}; choose from {sorted(types)}")
        t = str(types[k])
        out[k] = (v.lower() in ("1", "true", "yes")) if "bool" in t else int(v) if "int" in t else \
            float(v) if "float" in t else v
    return out
