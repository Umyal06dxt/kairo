import asyncio
from collections import deque

from .events import Event


class ConversationStream:
    """Async pub/sub bus plus a sliding window of recent turns."""

    def __init__(self, window: int = 10):
        self._subs: list[asyncio.Queue] = []
        self._turns: deque[tuple[str, str]] = deque(maxlen=window)

    def subscribe(self) -> "asyncio.Queue[Event]":
        q: asyncio.Queue = asyncio.Queue()
        self._subs.append(q)
        return q

    async def publish(self, event: Event) -> None:
        for q in self._subs:
            q.put_nowait(event)

    def add_turn(self, role: str, text: str) -> None:
        self._turns.append((role, text))

    def history(self, n: int | None = None) -> list[tuple[str, str]]:
        turns = list(self._turns)
        return turns if n is None else turns[-n:]
