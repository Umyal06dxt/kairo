import asyncio

import pytest

from kairo.cache import SemanticCache
from kairo.config import Config
from kairo.events import PriorityRetrieval, UserUtterance
from kairo.providers.fake import FakeLLM, HashEmbedder, InMemoryStore
from kairo.slow_thinker import SlowThinker
from kairo.stream import ConversationStream
from kairo.types import Chunk

DOCS = {"alpha": "alpha doc", "beta": "beta doc", "gamma": "gamma doc", "delta": "delta doc"}


class RaisingLLM:
    async def predict_topics(self, history, n):
        raise RuntimeError("llm down")


class SeqLLM(FakeLLM):
    """Predicts a topic derived from the last user utterance in history."""

    def __init__(self, mapping):
        super().__init__()
        self.mapping = mapping

    async def predict_topics(self, history, n):
        last = [t for r, t in history if r == "user"][-1]
        return self.mapping.get(last, [])


async def build(llm=None, latency=0.0, config=Config(prefetch_top_k=1, rate_limit_s=0.0)):
    emb = HashEmbedder(dim=256)
    store = InMemoryStore(emb.dim, latency_s=latency)
    texts = list(DOCS.values())
    await store.add([Chunk(k, v) for k, v in DOCS.items()], await emb.embed(texts))
    emb.calls = 0  # don't count seeding
    cache = SemanticCache(dim=emb.dim)
    stream = ConversationStream()
    st = SlowThinker(emb, llm or FakeLLM(), store, cache, stream, config)
    return st, emb, store, cache, stream


def cached_ids(cache):
    return {e.chunk.id for e in cache._entries}


async def test_direct_and_predicted_chunks_cached_with_one_batch_embed():
    st, emb, store, cache, _ = await build(FakeLLM(topics=["beta doc", "gamma doc"]))
    await st.handle_utterance("alpha")
    assert cached_ids(cache) == {"alpha", "beta", "gamma"}
    assert emb.calls == 2  # one direct embed + ONE batch for all predictions


async def test_priority_retrieval_uses_double_k():
    st, emb, store, cache, _ = await build()
    v = await emb.embed(["alpha"])
    await st.handle_priority(PriorityRetrieval(query="alpha", embedding=v[0]))
    assert store.search_calls == [2]
    assert len(cache) == 2


async def test_llm_failure_keeps_direct_retrieval():
    st, emb, store, cache, _ = await build(RaisingLLM())
    await st.handle_utterance("alpha")
    assert cached_ids(cache) == {"alpha"}


async def test_garbage_prediction_does_not_crash():
    st, emb, store, cache, _ = await build(FakeLLM(topics=[]))
    await st.handle_utterance("alpha")
    assert cached_ids(cache) == {"alpha"}


async def test_rate_limit_spaces_predictions():
    st, *_ = await build(config=Config(prefetch_top_k=1, rate_limit_s=0.3))
    loop = asyncio.get_running_loop()
    await st.handle_utterance("alpha")
    t0 = loop.time()
    await st.handle_utterance("beta")
    assert loop.time() - t0 >= 0.25


async def test_new_utterance_cancels_inflight_cycle():
    llm = SeqLLM({"alpha": ["gamma doc"]})
    st, emb, store, cache, stream = await build(llm, latency=0.1)
    task = asyncio.create_task(st.run())
    await stream.publish(UserUtterance("alpha"))
    await asyncio.sleep(0.15)  # direct retrieval done, gamma prefetch in flight
    await stream.publish(UserUtterance("beta"))
    await asyncio.sleep(0.4)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    ids = cached_ids(cache)
    assert "gamma" not in ids and {"alpha", "beta"} <= ids


async def test_run_handles_priority_event():
    st, emb, store, cache, stream = await build()
    task = asyncio.create_task(st.run())
    v = await emb.embed(["delta"])
    await stream.publish(PriorityRetrieval(query="delta", embedding=v[0]))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "delta" in cached_ids(cache)
