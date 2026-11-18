"""Background agent: direct retrieval, follow-up topic prediction, prefetching."""

import asyncio
import logging

from .cache import SemanticCache
from .config import Config
from .events import PriorityRetrieval, UserUtterance
from .providers.base import LLM, Embedder, VectorStore
from .stream import ConversationStream

log = logging.getLogger(__name__)


class SlowThinker:
    def __init__(self, embedder: Embedder, llm: LLM, store: VectorStore,
                 cache: SemanticCache, stream: ConversationStream, config: Config):
        self.embedder, self.llm, self.store = embedder, llm, store
        self.cache, self.stream, self.config = cache, stream, config
        # Subscribe at construction so no event published before run() is lost.
        self._events = stream.subscribe()
        self._last_predict = float("-inf")

    async def run(self) -> None:
        """Consume events until cancelled."""
        utterance_task: asyncio.Task | None = None
        priority_tasks: set[asyncio.Task] = set()
        try:
            while True:
                event = await self._events.get()
                if isinstance(event, UserUtterance):
                    if utterance_task and not utterance_task.done():
                        utterance_task.cancel()  # stale cycle must not delay this one
                    utterance_task = asyncio.create_task(
                        self.handle_utterance(event.text, event.embedding))
                elif isinstance(event, PriorityRetrieval):
                    t = asyncio.create_task(self.handle_priority(event))
                    priority_tasks.add(t)
                    t.add_done_callback(priority_tasks.discard)
        finally:
            for t in [utterance_task, *priority_tasks]:
                if t and not t.done():
                    t.cancel()

    async def handle_utterance(self, text: str, embedding=None) -> None:
        try:
            await self._cycle(text, embedding)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("slow thinker cycle failed")

    async def _cycle(self, text: str, embedding=None) -> None:
        cfg = self.config
        # 1. direct retrieval for the current utterance (reuse the router's embedding if given)
        vec = embedding if embedding is not None else (await self.embedder.embed([text]))[0]
        for r in await self.store.search(vec, cfg.prefetch_top_k):
            self.cache.put(r.chunk, r.embedding, r.score)

        # 2. predict follow-ups (rate limited)
        loop = asyncio.get_running_loop()
        wait = self._last_predict + cfg.rate_limit_s - loop.time()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_predict = loop.time()
        history = self.stream.history(cfg.prediction_history_turns)
        if not history or history[-1] != ("user", text):
            history = [*history, ("user", text)][-cfg.prediction_history_turns:]
        try:
            topics = await self.llm.predict_topics(history, cfg.max_predictions)
        except Exception:
            log.exception("topic prediction failed; skipping prefetch")
            return
        topics = [t for t in topics if isinstance(t, str) and t.strip()][: cfg.max_predictions]
        if not topics:
            return

        # 3. prefetch: one batched embed, parallel searches
        vecs = await self.embedder.embed(topics)
        results = await asyncio.gather(
            *(self.store.search(v, cfg.prefetch_top_k) for v in vecs),
            return_exceptions=True,
        )
        for res in results:
            if isinstance(res, BaseException):
                if isinstance(res, asyncio.CancelledError):
                    raise res
                log.warning("prefetch search failed: %r", res)
                continue
            for r in res:
                self.cache.put(r.chunk, r.embedding, r.score)

    async def handle_priority(self, event: PriorityRetrieval) -> None:
        try:
            for r in await self.store.search(event.embedding, 2 * self.config.prefetch_top_k):
                self.cache.put(r.chunk, r.embedding, r.score)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("priority retrieval failed")
