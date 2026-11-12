import numpy as np

from kairo.cache import SemanticCache
from kairo.config import Config
from kairo.events import PriorityRetrieval
from kairo.fast_talker import FastTalker
from kairo.providers.fake import FakeLLM, HashEmbedder, InMemoryStore
from kairo.stream import ConversationStream
from kairo.types import Chunk

DOCS = ["pricing plans starter pro enterprise", "api endpoint contacts deals"]


class FailingStore:
    async def search(self, vec, k):
        raise RuntimeError("store down")

    async def add(self, chunks, embeddings):
        pass


async def build(store=None, config=Config()):
    emb = HashEmbedder(dim=256)
    if store is None:
        store = InMemoryStore(emb.dim)
        await store.add([Chunk(str(i), d) for i, d in enumerate(DOCS)], await emb.embed(DOCS))
    emb.calls = 0  # don't count seeding
    cache = SemanticCache(dim=emb.dim)
    stream = ConversationStream()
    q = stream.subscribe()
    ft = FastTalker(emb, FakeLLM(answer="Sure thing."), store, cache, stream, config)
    return ft, emb, store, cache, q


async def test_warm_cache_hit_skips_store():
    ft, emb, store, cache, _ = await build()
    v = await emb.embed([DOCS[0]])
    cache.put(Chunk("0", DOCS[0]), v[0])
    r = await ft.answer("pricing plans")
    assert r.hit and r.source == "cache" and store.search_calls == []
    assert r.answer.strip() == "Sure thing."


async def test_cold_miss_falls_back_caches_and_signals():
    ft, emb, store, cache, q = await build()
    r = await ft.answer("pricing plans")
    assert not r.hit and r.source == "store" and len(store.search_calls) == 1
    assert len(cache) > 0
    ev = q.get_nowait()
    assert isinstance(ev, PriorityRetrieval) and ev.query == "pricing plans"
    r2 = await ft.answer("pricing plans")
    assert r2.hit and len(store.search_calls) == 1


async def test_store_failure_still_answers():
    ft, *_ = await build(store=FailingStore())
    r = await ft.answer("pricing plans")
    assert r.store_failed and r.answer.strip() != ""


async def test_blank_question_does_nothing():
    ft, emb, store, cache, q = await build()
    r = await ft.answer("   ")
    assert r.answer == "" and emb.calls == 0 and q.empty() and store.search_calls == []


async def test_on_token_streams():
    ft, *_ = await build()
    toks = []
    await ft.answer("pricing plans", on_token=toks.append)
    assert "".join(toks).strip() == "Sure thing."


async def test_fallback_disabled_does_not_touch_store():
    ft, emb, store, cache, q = await build(config=Config(fallback_to_store=False))
    r = await ft.answer("pricing plans")
    assert not r.hit and store.search_calls == []
