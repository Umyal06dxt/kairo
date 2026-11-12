"""Memory router: wires the stream, cache, Fast Talker and Slow Thinker."""

import asyncio
from typing import Callable

from .cache import SemanticCache
from .config import Config
from .events import AgentResponse, UserUtterance
from .fast_talker import FastTalker, TurnResult
from .providers.base import LLM, Embedder, VectorStore
from .slow_thinker import SlowThinker
from .stream import ConversationStream


class MemoryRouter:
    def __init__(self, stream: ConversationStream, cache: SemanticCache,
                 fast: FastTalker, slow: SlowThinker):
        self.stream, self.cache, self.fast, self.slow = stream, cache, fast, slow
        self._task: asyncio.Task | None = None

    @classmethod
    def create(cls, embedder: Embedder, llm: LLM, store: VectorStore,
               config: Config = Config()) -> "MemoryRouter":
        stream = ConversationStream(window=config.stream_window)
        cache = SemanticCache(embedder.dim, config.cache_max_size, config.cache_ttl_s,
                              config.dedup_threshold)
        fast = FastTalker(embedder, llm, store, cache, stream, config)
        slow = SlowThinker(embedder, llm, store, cache, stream, config)
        return cls(stream, cache, fast, slow)

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

    async def handle_utterance(self, text: str,
                               on_token: Callable[[str], None] | None = None) -> TurnResult:
        text = text.strip()
        if not text:
            return TurnResult(answer="")
        # Both agents see the utterance concurrently; Slow Thinker works in the background.
        await self.stream.publish(UserUtterance(text))
        result = await self.fast.answer(text, on_token)
        self.stream.add_turn("user", text)
        self.stream.add_turn("assistant", result.answer)
        await self.stream.publish(AgentResponse(result.answer))
        return result
