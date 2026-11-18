"""Memory router: wires the stream, caches, Fast Talker and Slow Thinker."""

import asyncio
from collections import Counter
from dataclasses import asdict
from typing import Callable

from .answer_cache import AnswerCache
from .cache import SemanticCache
from .config import Config
from .events import AgentResponse, PartialUtterance, UserUtterance
from .fast_talker import FastTalker, TurnResult
from .providers.base import LLM, Embedder, VectorStore
from .slow_thinker import SlowThinker
from .stream import ConversationStream
from .telemetry import Telemetry


class MemoryRouter:
    def __init__(self, stream: ConversationStream, cache: SemanticCache,
                 fast: FastTalker, slow: SlowThinker, answers: AnswerCache | None = None,
                 telemetry: Telemetry | None = None, embedder=None, llm=None):
        self.stream, self.cache, self.fast, self.slow = stream, cache, fast, slow
        self.answers = answers
        self.telemetry = telemetry or Telemetry()
        self.embedder, self.llm = embedder, llm
        self.sources: Counter = Counter()
        self._task: asyncio.Task | None = None

    @classmethod
    def create(cls, embedder: Embedder, llm: LLM, store: VectorStore,
               config: Config = Config()) -> "MemoryRouter":
        stream = ConversationStream(window=config.stream_window)
        cache = SemanticCache(embedder.dim, config.cache_max_size, config.cache_ttl_s,
                              config.dedup_threshold)
        answers = (AnswerCache(embedder.dim, config.cache_ttl_s, config.answer_cache_size)
                   if config.speculative_answers else None)
        telemetry = Telemetry()
        fast = FastTalker(embedder, llm, store, cache, stream, config, answers, telemetry)
        slow = SlowThinker(embedder, llm, store, cache, stream, config, answers, telemetry)
        return cls(stream, cache, fast, slow, answers, telemetry, embedder, llm)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.slow.run())

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def warmup(self) -> None:
        """Pay one-time connection/model start-up costs before the first user turn."""
        warm = getattr(self.llm, "warmup", None)
        await asyncio.gather(self.embedder.embed(["warm up"]),
                             warm() if warm else asyncio.sleep(0),
                             return_exceptions=True)

    async def speculate(self, partial_text: str) -> None:
        """Feed an interim transcript (user still speaking/typing) to the Slow Thinker."""
        await self.stream.publish(PartialUtterance(partial_text))

    async def handle_utterance(self, text: str,
                               on_token: Callable[[str], None] | None = None) -> TurnResult:
        text = text.strip()
        if not text:
            return TurnResult(answer="")
        # Embed once (the Fast Talker needs it first anyway) and share it, so the query is
        # never embedded twice and the Slow Thinker cannot pre-empt the Fast Talker's lookup.
        vec, embed_ms = await self.fast.embed_query(text)
        await self.stream.publish(UserUtterance(text, vec))  # Slow Thinker runs in background
        result = await self.fast.answer(text, on_token, vec=vec, embed_ms=embed_ms)
        self.stream.add_turn("user", text)
        self.stream.add_turn("assistant", result.answer)
        await self.stream.publish(AgentResponse(result.answer))
        self.sources[result.source] += 1
        self.telemetry.emit("turn", question=text, **asdict(result))
        return result
