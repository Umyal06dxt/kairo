import asyncio

from kairo.config import Config
from kairo.providers.fake import FakeLLM, HashEmbedder, InMemoryStore
from kairo.router import MemoryRouter
from kairo.types import Chunk

DOCS = [
    "pricing plans cost starter pro enterprise",
    "pricing discount annual billing",
    "enterprise plan pricing seats",
    "api endpoint contacts deals",
    "security soc2 encryption",
]


async def make_router(latency=0.05):
    emb = HashEmbedder(dim=256)
    store = InMemoryStore(emb.dim, latency_s=latency)
    await store.add([Chunk(str(i), d) for i, d in enumerate(DOCS)], await emb.embed(DOCS))
    llm = FakeLLM(topics=["annual billing discount pricing", "enterprise plan seats pricing"],
                  answer="Okay.")
    cfg = Config(prefetch_top_k=2, rate_limit_s=0.0)
    return MemoryRouter.create(emb, llm, store, cfg), store


async def test_single_topic_conversation_warms_cache():
    router, store = await make_router()
    await router.start()
    try:
        results = []
        for q in ["what are the pricing plans", "annual billing discount",
                  "enterprise plan seats", "pricing plans cost", "pricing discount"]:
            results.append(await router.handle_utterance(q))
            await asyncio.sleep(0.3)  # user thinking time: slow thinker prefetches here
    finally:
        await router.stop()
    assert results[0].hit is False
    assert [r.hit for r in results[1:]] == [True] * 4
    assert all(r.answer.strip() == "Okay." for r in results)


async def test_history_recorded_and_blank_ignored():
    router, _ = await make_router(latency=0.0)
    await router.start()
    try:
        assert (await router.handle_utterance("  ")).answer == ""
        await router.handle_utterance("pricing plans")
    finally:
        await router.stop()
    hist = router.stream.history()
    assert [r for r, _ in hist] == ["user", "assistant"]
    assert hist[0][1] == "pricing plans" and hist[1][1].strip() == "Okay."


async def test_stop_is_clean_and_idempotent():
    router, _ = await make_router()
    await router.start()
    await router.stop()
    await router.stop()
