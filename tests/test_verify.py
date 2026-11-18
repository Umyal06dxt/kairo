"""Speculate-then-verify: cache hits are checked against the store in parallel with the LLM's
first token; a disagreement is corrected before any token is spoken."""
import asyncio

from kairo.answer_cache import AnswerCache
from kairo.cache import SemanticCache
from kairo.config import Config
from kairo.fast_talker import FastTalker
from kairo.providers.fake import FakeLLM, HashEmbedder, InMemoryStore
from kairo.stream import ConversationStream
from kairo.types import Chunk

DOCS = {"price": "enterprise plan pricing per user cost", "decoy": "plan overview enterprise features",
        "api": "api rate limit endpoint"}


class SlowFirstTokenLLM(FakeLLM):
    """Records the context it was called with; first token arrives after `delay`."""

    def __init__(self, delay=0.05):
        super().__init__(answer="spoken answer")
        self.delay, self.contexts, self.cancelled = delay, [], 0

    async def stream_answer(self, question, context, history):
        self.contexts.append([c.id for c in context])
        try:
            await asyncio.sleep(self.delay)
            for tok in ["spoken ", "answer"]:
                yield tok
        except asyncio.CancelledError:
            self.cancelled += 1
            raise


async def build(verify=True, store_latency=0.02, preload=("decoy",), llm=None, spec=False):
    emb = HashEmbedder(dim=256)
    store = InMemoryStore(emb.dim, latency_s=store_latency)
    texts = list(DOCS.values())
    vecs = await emb.embed(texts)
    await store.add([Chunk(k, v) for k, v in DOCS.items()], vecs)
    cache = SemanticCache(emb.dim)
    for i, k in enumerate(DOCS):
        if k in preload:
            cache.put(Chunk(k, DOCS[k]), vecs[i], tag="predicted")
    cfg = Config(verify_hits=verify, similarity_threshold=0.1, llm_context_chunks=2,
                 speculative_answers=spec, answer_threshold=0.8)
    answers = AnswerCache(emb.dim) if spec else None
    llm = llm or SlowFirstTokenLLM()
    ft = FastTalker(emb, llm, store, cache, ConversationStream(), cfg, answers)
    return ft, emb, store, cache, llm, answers


async def test_verified_hit_keeps_cache_latency_and_calls_store_once_in_parallel():
    ft, emb, store, cache, llm, _ = await build(preload=("price", "decoy"))
    toks = []
    r = await ft.answer("enterprise plan pricing per user", on_token=toks.append)
    assert r.hit and r.source == "cache" and r.verified is True and not r.corrected
    assert store.search_calls == [10]  # one verification search
    assert len(llm.contexts) == 1  # LLM started once: speculation was right, no regeneration
    assert "".join(toks) == "spoken answer" and llm.cancelled == 0
    assert r.retrieval_ms < 20  # the 20 ms store search was NOT on the critical path


async def test_wrong_cache_hit_is_corrected_before_any_token_is_spoken():
    # cache holds only a decoy chunk that clears tau; the store's top-1 is a different chunk
    ft, emb, store, cache, llm, _ = await build(preload=("decoy",))
    toks = []
    r = await ft.answer("enterprise plan pricing per user cost", on_token=toks.append)
    assert r.verified is False and r.corrected and not r.hit and r.source == "store"
    assert len(llm.contexts) == 2 and llm.contexts[0] == ["decoy"]  # speculative start
    assert llm.contexts[1][0] == "price"  # regenerated with the store's top chunk
    assert llm.cancelled == 0 or llm.cancelled == 1
    assert "".join(toks) == "spoken answer"  # exactly one answer reached the speaker
    assert "price" in {e["id"] for e in cache.snapshot()}  # the miss primed the cache


async def test_verification_disabled_never_touches_the_store_on_a_hit():
    ft, emb, store, cache, llm, _ = await build(verify=False, preload=("decoy",))
    r = await ft.answer("enterprise plan pricing per user cost")
    assert r.hit and r.verified is None and store.search_calls == []


async def test_store_failure_during_verification_serves_the_cache_hit():
    ft, emb, store, cache, llm, _ = await build(preload=("decoy",))

    async def boom(vec, k):
        raise RuntimeError("store down")

    store.search = boom
    r = await ft.answer("enterprise plan pricing per user cost")
    assert r.hit and r.source == "cache" and not r.corrected and r.answer.strip()


async def test_draft_rejected_when_store_top_chunk_not_in_drafts_evidence():
    ft, emb, store, cache, llm, answers = await build(preload=("decoy",), spec=True)
    q = "enterprise plan pricing per user cost"
    answers.put(q, (await emb.embed([q]))[0], "stale draft", ["decoy"])
    r = await ft.answer(q)
    assert r.corrected and r.source == "store" and r.answer == "spoken answer"  # not "stale draft"
    # and a draft whose evidence the store confirms IS served
    ft2, emb2, store2, cache2, llm2, answers2 = await build(preload=("price",), spec=True)
    answers2.put(q, (await emb2.embed([q]))[0], "good draft", ["price"])
    r2 = await ft2.answer(q)
    assert r2.source == "draft" and r2.answer == "good draft" and r2.verified is True
