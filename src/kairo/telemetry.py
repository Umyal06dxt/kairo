"""Tiny synchronous event tap so UIs/benchmarks can observe the agents without coupling."""

from typing import Callable

Sink = Callable[[str, dict], None]


class Telemetry:
    def __init__(self) -> None:
        self._sinks: list[Sink] = []

    def add_sink(self, sink: Sink) -> None:
        self._sinks.append(sink)

    def remove_sink(self, sink: Sink) -> None:
        if sink in self._sinks:
            self._sinks.remove(sink)

    def emit(self, kind: str, **data) -> None:
        for sink in list(self._sinks):
            try:
                sink(kind, data)
            except Exception:  # an observer must never break the pipeline
                pass
