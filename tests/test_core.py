import asyncio

import numpy as np

from kairo.cache import SemanticCache
from kairo.config import Config
from kairo.events import UserUtterance
from kairo.providers.fake import HashEmbedder, InMemoryStore
from kairo.stream import ConversationStream
from kairo.types import Chunk


def test_config_defaults_match_paper():
    c = Config()
    assert (c.cache_max_size, c.cache_ttl_s, c.similarity_threshold) == (2000, 300.0, 0.40)
    assert (c.dedup_threshold, c.max_predictions, c.prefetch_top_k) == (0.95, 5, 10)
    assert (c.rate_limit_s, c.max_context_chunks, c.chunk_size, c.chunk_overlap) == (0.5, 10, 512, 50)
    assert (c.stream_window, c.prediction_history_turns, c.temperature) == (10, 6, 0.3)


async def test_stream_fans_out_and_windows():
    s = ConversationStream(window=3)
    a, b = s.subscribe(), s.subscribe()
    await s.publish(UserUtterance("hi"))
    assert (await a.get()).text == "hi" and (await b.get()).text == "hi"
    for i in range(5):
        s.add_turn("user", str(i))
    assert [t for _, t in s.history()] == ["2", "3", "4"]
    assert [t for _, t in s.history(2)] == ["3", "4"]


def vec(*xs):
    v = np.array(xs, dtype=np.float32)
    return v / np.linalg.norm(v)


def chunk(i):
    return Chunk(id=str(i), text=f"c{i}")


def test_cache_empty_get():
    assert SemanticCache(dim=3).get(vec(1, 0, 0)) == []


def test_cache_dedup_and_tau_and_order():
    c = SemanticCache(dim=3)
    assert c.put(chunk(1), vec(1, 0, 0)) is True
    assert c.put(chunk(2), vec(1, 0.01, 0)) is False  # cos > 0.95
    assert len(c) == 1
    c.put(chunk(3), vec(1, 1, 0))  # cos with x-axis ~0.707
    res = c.get(vec(1, 0, 0), k=5, tau=0.4)
    assert [r.chunk.id for r in res] == ["1", "3"]
    assert [r.chunk.id for r in c.get(vec(1, 0, 0), k=5, tau=0.9)] == ["1"]
    assert len(c.get(vec(1, 0, 0), k=1, tau=0.0)) == 1


def test_cache_indexed_by_document_embedding():
    c = SemanticCache(dim=3)
    c.put(chunk("doc"), vec(0, 1, 0))
    assert c.get(vec(0.1, 1, 0))[0].chunk.id == "doc"


def test_cache_ttl_expiry():
    t = [0.0]
    c = SemanticCache(dim=3, ttl=300, clock=lambda: t[0])
    c.put(chunk(1), vec(1, 0, 0))
    t[0] = 299
    assert len(c.get(vec(1, 0, 0))) == 1
    t[0] = 301
    assert c.get(vec(1, 0, 0)) == [] and len(c) == 0


def test_cache_lru_eviction():
    t = [0.0]
    c = SemanticCache(dim=3, max_size=2, clock=lambda: t[0])
    c.put(chunk("a"), vec(1, 0, 0)); t[0] = 1
    c.put(chunk("b"), vec(0, 1, 0)); t[0] = 2
    c.get(vec(1, 0, 0), k=1, tau=0.9); t[0] = 3  # touch a
    c.put(chunk("c"), vec(0, 0, 1))
    ids = {e.chunk.id for e in c._entries}
    assert ids == {"a", "c"} and len(c) == 2


async def test_fake_embedder_and_store():
    e = HashEmbedder()
    v = await e.embed(["pricing plans cost", "pricing plans", "api endpoint"])
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0)
    assert v[0] @ v[1] > v[0] @ v[2]
    s = InMemoryStore(e.dim, latency_s=0.05)
    await s.add([Chunk("p", "pricing plans"), Chunk("a", "api endpoint")], v[1:])
    t0 = asyncio.get_running_loop().time()
    res = await s.search(v[0], 2)
    assert res[0].chunk.id == "p"
    assert asyncio.get_running_loop().time() - t0 >= 0.045


def test_cache_matches_bruteforce_on_random_data():
    rng = np.random.default_rng(0)
    for _ in range(100):
        n = int(rng.integers(1, 50))
        V = rng.normal(size=(n, 16)).astype(np.float32)
        V /= np.linalg.norm(V, axis=1, keepdims=True)
        c = SemanticCache(dim=16, dedup=2.0)  # dedup off: random vectors must all be kept
        for i, v in enumerate(V):
            c.put(chunk(i), v)
        q = rng.normal(size=16).astype(np.float32)
        q /= np.linalg.norm(q)
        k, tau = int(rng.integers(1, 15)), float(rng.uniform(-0.2, 0.6))
        sims = V @ q
        expect = [str(i) for i in np.argsort(-sims)[:k] if sims[i] >= tau]
        assert [r.chunk.id for r in c.get(q, k, tau)] == expect


async def test_extractive_llm_does_not_leak_markdown_headings():
    from kairo.providers.fake import ExtractiveLLM
    ctx = [Chunk("a", "# Fee Schedule\n\nOverdraft fee: 30 dollars per item. Stop payment costs 20 dollars.")]
    out = "".join([t async for t in ExtractiveLLM().stream_answer("overdraft fee", ctx, [])])
    assert "#" not in out and "30 dollars" in out
