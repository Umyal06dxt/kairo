import asyncio
from dataclasses import replace

import numpy as np
import pytest

from kairo.answer_cache import AnswerCache
from kairo.cache import SemanticCache
from kairo.config import OPTIMIZED, PAPER, Config
from kairo.events import UserUtterance
from kairo.fast_talker import FastTalker
from kairo.providers.fake import FakeLLM, HashEmbedder, InMemoryStore
from kairo.providers.prompts import parse_followups
from kairo.router import MemoryRouter
from kairo.slow_thinker import SlowThinker
from kairo.stream import ConversationStream
from kairo.types import Chunk

DOCS = {
    "price": "pricing plans starter pro enterprise cost per user",
    "disc": "annual billing discount saves twenty percent pricing",
    "api": "api endpoint contacts deals rate limit",
    "sec": "security soc2 encryption audit logs",
}


def unit(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------- config / parsing
def test_paper_config_is_unchanged_and_optimized_differs():
    assert PAPER == Config() and not PAPER.speculative_answers and PAPER.llm_context_chunks == 10
    assert OPTIMIZED.speculative_answers and OPTIMIZED.strategy == "hybrid"
    assert OPTIMIZED.llm_context_chunks == 4 and OPTIMIZED.similarity_threshold == 0.40
    assert OPTIMIZED.verify_hits and OPTIMIZED.lexical_rerank and not PAPER.verify_hits


def test_parse_followups_tolerant():
    txt = 'Sure! [{"topic": "pricing", "question": " How much? "}, "plain topic", {"topic": ""}, 5]'
    assert parse_followups(txt, 5) == [{"topic": "pricing", "question": "How much?"},
                                       {"topic": "plain topic", "question": None}]
    assert parse_followups("nope", 3) == [] and parse_followups("[bad", 3) == []
    assert parse_followups('[{"topic":"a"},{"topic":"b"}]', 1) == [{"topic": "a", "question": None}]


# ---------------------------------------------------------------- answer cache
def test_answer_cache_match_threshold_ttl_and_dedup():
    t = [0.0]
    ac = AnswerCache(dim=3, ttl=100, clock=lambda: t[0])
    assert ac.get(unit(1, 0, 0), 0.8) is None  # empty
    assert ac.put("q1", unit(1, 0, 0), "a1", ["c1"]) is True
    assert ac.put("q1b", unit(1, 0.01, 0), "a1b", ["c1"]) is False  # near-duplicate replaces
    assert len(ac) == 1 and ac.get(unit(1, 0, 0), 0.8)[0].answer == "a1b"
    assert ac.get(unit(0, 1, 0), 0.8) is None  # below threshold
    sim = ac.get(unit(1, 0.2, 0), 0.8)[1]
    assert 0.9 < sim < 1.0
    t[0] = 101
    assert ac.get(unit(1, 0, 0), 0.8) is None and len(ac) == 0


def test_cache_provenance_tags_and_snapshot():
    c = SemanticCache(dim=3)
    c.put(Chunk("a", "text a"), unit(1, 0, 0), tag="predicted")
    c.put(Chunk("a2", "x"), unit(1, 0.01, 0), tag="direct")  # dedup keeps first provenance
    assert len(c) == 1
    got = c.get(unit(1, 0, 0), k=1, tau=0.5)
    assert got[0].tag == "predicted"
    snap = c.snapshot()
    assert snap[0]["tag"] == "predicted" and snap[0]["hits"] == 1 and snap[0]["id"] == "a"


# ---------------------------------------------------------------- slow thinker strategies
async def build_slow(config, llm=None, latency=0.0):
    emb = HashEmbedder(dim=256)
    store = InMemoryStore(emb.dim, latency_s=latency)
    await store.add([Chunk(k, v) for k, v in DOCS.items()], await emb.embed(list(DOCS.values())))
    emb.calls = 0
    cache = SemanticCache(dim=emb.dim)
    answers = AnswerCache(dim=emb.dim) if config.speculative_answers else None
    stream = ConversationStream()
    st = SlowThinker(emb, llm or FakeLLM(), store, cache, stream, config, answers)
    events = []
    st.telemetry.add_sink(lambda k, d: events.append((k, d)))
    return st, emb, store, cache, answers, stream, events


def tags(cache):
    return {e.chunk.id: e.tag for e in cache._entries}


async def test_neighbors_strategy_uses_no_llm_and_no_embed_calls():
    cfg = Config(strategy="neighbors", prefetch_top_k=1, neighbor_seeds=1, neighbor_k=3,
                 rate_limit_s=0.0)
    st, emb, store, cache, *_ = await build_slow(cfg, llm=FakeLLM(topics=["should not be used"]))
    v = (await emb.embed(["pricing plans"]))[0]
    emb.calls = 0
    await st.handle_utterance("pricing plans", embedding=v)
    t = tags(cache)
    assert t["price"] == "direct" and len(t) == 3  # direct hit + 2 neighbours
    assert [x for x in t.values() if x == "neighbor"] and emb.calls == 0


async def test_none_strategy_is_reactive_only():
    cfg = Config(strategy="none", prefetch_top_k=1, rate_limit_s=0.0)
    st, emb, store, cache, *_ = await build_slow(cfg, llm=FakeLLM(topics=["api endpoint"]))
    await st.handle_utterance("pricing plans")
    assert set(tags(cache)) == {"price"}


async def test_followups_prefetch_and_draft_answers():
    cfg = Config(strategy="llm", speculative_answers=True, prefetch_top_k=1, draft_top=1,
                 rate_limit_s=0.0)
    llm = FakeLLM(followups=[("annual billing discount pricing", "Is there an annual discount?"),
                             ("api endpoint rate limit", "What is the API rate limit?")])
    st, emb, store, cache, answers, _, events = await build_slow(cfg, llm)
    await st.handle_utterance("pricing plans")
    embed_calls = emb.calls
    assert tags(cache)["disc"] == "predicted" and tags(cache)["api"] == "predicted"
    assert llm.draft_calls == ["Is there an annual discount?"]  # draft_top=1
    assert len(answers) == 1
    d, _ = answers.get((await emb.embed(["Is there an annual discount?"]))[0], 0.9)
    assert d.answer.startswith("Draft:") and "disc" in d.chunk_ids
    kinds = [k for k, _ in events]
    assert "slow.predicted" in kinds and "slow.drafted" in kinds and "slow.prefetch" in kinds
    assert embed_calls == 2  # direct embed + ONE batch (topics + draft questions)


async def test_no_drafts_when_speculative_answers_disabled():
    cfg = Config(strategy="llm", speculative_answers=False, prefetch_top_k=1, rate_limit_s=0.0)
    llm = FakeLLM(topics=["api endpoint"], followups=[("api endpoint", "What is the limit?")])
    st, emb, store, cache, answers, *_ = await build_slow(cfg, llm)
    await st.handle_utterance("pricing plans")
    assert answers is None and llm.draft_calls == [] and tags(cache)["api"] == "predicted"


async def test_partial_prefetch_ignores_short_text_and_is_cancelled_by_utterance():
    cfg = Config(strategy="none", prefetch_top_k=1, rate_limit_s=0.0)
    st, emb, store, cache, answers, stream, events = await build_slow(cfg, latency=0.1)
    await st.handle_partial("pri")  # shorter than partial_min_chars
    assert len(cache) == 0 and store.search_calls == []
    await st.handle_partial("what are the pricing plans")
    assert tags(cache) == {"price": "partial"}
    # via the event loop: an utterance cancels a partial still in flight
    from kairo.events import PartialUtterance
    task = asyncio.create_task(st.run())
    await stream.publish(PartialUtterance("what is the api rate limit"))
    await asyncio.sleep(0.03)  # embed done, store.search (100 ms) in flight
    await stream.publish(UserUtterance("security audit logs please"))
    await asyncio.sleep(0.4)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "api" not in tags(cache)  # cancelled partial never landed


# ---------------------------------------------------------------- fast talker answer path
async def build_fast(config, draft_chunk_ids=("price",), draft_q="How much does it cost?"):
    emb = HashEmbedder(dim=256)
    store = InMemoryStore(emb.dim)
    texts = list(DOCS.values())
    await store.add([Chunk(k, v) for k, v in DOCS.items()], await emb.embed(texts))
    cache, answers, stream = SemanticCache(emb.dim), AnswerCache(emb.dim), ConversationStream()
    llm = FakeLLM(answer="LLM answer.")
    ft = FastTalker(emb, llm, store, cache, stream, config, answers)
    qv = (await emb.embed([draft_q]))[0]
    answers.put(draft_q, qv, "Pre-drafted answer.", list(draft_chunk_ids))
    return ft, emb, store, cache, answers, llm


async def test_draft_served_instantly_when_matching_and_evidence_present():
    cfg = Config(speculative_answers=True, answer_threshold=0.85, similarity_threshold=0.1)
    ft, emb, store, cache, answers, llm = await build_fast(cfg)
    v = (await emb.embed([DOCS["price"]]))[0]
    cache.put(Chunk("price", DOCS["price"]), v, tag="predicted")  # evidence is in the cache
    toks = []
    r = await ft.answer("How much does it cost?", on_token=toks.append)
    assert r.source == "draft" and r.hit and r.llm_first_token_ms == 0.0
    assert r.answer == "Pre-drafted answer." and "".join(toks).strip() == r.answer
    assert r.draft_sim >= 0.99 and store.search_calls == []
    assert answers.snapshot()[0]["uses"] == 1


async def test_draft_not_served_without_evidence_or_below_threshold():
    cfg = Config(speculative_answers=True, answer_threshold=0.85, similarity_threshold=0.2)
    ft, emb, store, cache, answers, llm = await build_fast(cfg)
    # evidence check: cache holds nothing for this query -> must fall back to the normal path
    r = await ft.answer("How much does it cost?")
    assert r.source == "store" and r.answer.strip() == "LLM answer."
    # similarity check: an unrelated question never matches the draft
    ft2, emb2, store2, cache2, *_ = await build_fast(cfg)
    cache2.put(Chunk("price", DOCS["price"]), (await emb2.embed([DOCS["price"]]))[0])
    r2 = await ft2.answer("Tell me about security encryption")
    assert r2.source != "draft"


async def test_llm_context_is_capped():
    cfg = Config(llm_context_chunks=2, prefetch_top_k=10, similarity_threshold=0.0)
    ft, emb, store, cache, answers, llm = await build_fast(cfg)
    seen = {}

    async def spy(question, context, history):
        seen["n"] = len(context)
        yield "ok"

    llm.stream_answer = spy
    r = await ft.answer("pricing plans cost")
    assert seen["n"] == 2 and len(r.chunk_ids) == 2


# ---------------------------------------------------------------- router
async def test_router_end_to_end_with_speculation_telemetry_and_partial():
    emb = HashEmbedder(dim=256)
    store = InMemoryStore(emb.dim, latency_s=0.02)
    await store.add([Chunk(k, v) for k, v in DOCS.items()], await emb.embed(list(DOCS.values())))
    llm = FakeLLM(answer="LLM.", followups=[("annual billing discount pricing", "annual billing discount")])
    cfg = replace(OPTIMIZED, prefetch_top_k=2, rate_limit_s=0.0, similarity_threshold=0.3,
                  answer_threshold=0.8)
    router = MemoryRouter.create(emb, llm, store, cfg)
    log = []
    router.telemetry.add_sink(lambda k, d: log.append((k, d)))
    await router.warmup()
    await router.start()
    try:
        await router.speculate("what are the pricing plans please")
        await asyncio.sleep(0.2)
        assert "partial" in {e["tag"] for e in router.cache.snapshot()}
        r1 = await router.handle_utterance("what are the pricing plans")
        await asyncio.sleep(0.5)  # slow thinker predicts + drafts
        r2 = await router.handle_utterance("annual billing discount")
    finally:
        await router.stop()
    assert r1.source in ("cache", "store")
    assert r2.source == "draft" and r2.answer == "Draft: annual billing discount"
    turns = [d for k, d in log if k == "turn"]
    assert len(turns) == 2 and turns[1]["source"] == "draft"
    assert router.sources["draft"] == 1


# ---------------------------------------------------------------- lexical rerank
def test_rerank_promotes_exact_token_match_over_slightly_higher_dense_score():
    from kairo.rerank import rerank
    from kairo.types import Retrieved
    e = np.zeros(3, dtype=np.float32)
    a = Retrieved(Chunk("a", "General notes about email synchronization and mailboxes"), e, 0.62)
    b = Retrieved(Chunk("b", "Error EMAIL_401 means the OAuth token expired; reconnect the mailbox"), e, 0.58)
    c = Retrieved(Chunk("c", "Pricing plans and billing"), e, 0.40)
    assert [r.chunk.id for r in rerank("what does EMAIL_401 mean", [a, b, c])][0] == "b"
    assert rerank("x", [a]) == [a] and rerank("x", []) == []
    assert {r.chunk.id for r in rerank("zzz qqq", [a, b, c])} == {"a", "b", "c"}  # no lexical hit


async def test_fast_talker_applies_rerank_only_when_enabled():
    seen = {}

    async def run(flag):
        cfg = Config(lexical_rerank=flag, llm_context_chunks=1, similarity_threshold=0.0)
        emb = HashEmbedder(dim=256)
        store = InMemoryStore(emb.dim)
        texts = ["alpha beta gamma delta", "error code EMAIL_401 token expired", "pricing plans"]
        await store.add([Chunk(str(i), t) for i, t in enumerate(texts)], await emb.embed(texts))
        cache, stream = SemanticCache(emb.dim), ConversationStream()
        llm = FakeLLM()

        async def spy(question, context, history):
            seen[flag] = [c.id for c in context]
            yield "ok"

        llm.stream_answer = spy
        ft = FastTalker(emb, llm, store, cache, stream, cfg)
        await ft.answer("what does EMAIL_401 mean")

    await run(False)
    await run(True)
    assert seen[True] == ["1"]  # the exact-token chunk wins the single LLM context slot


def test_per_embedder_threshold_defaults():
    from kairo.config import DEFAULT_TAU, for_embedder
    assert for_embedder(OPTIMIZED, "local").similarity_threshold == DEFAULT_TAU["local"] == 0.60
    assert for_embedder(PAPER, "openai").similarity_threshold == 0.40  # paper value preserved
    assert for_embedder(PAPER, "unknown").similarity_threshold == 0.40  # unknown keeps the config's
