from dataclasses import dataclass

import numpy as np


class Event:
    """Base class for conversation-stream events."""


@dataclass
class UserUtterance(Event):
    text: str
    embedding: np.ndarray | None = None  # shared query embedding (computed once by the router)


@dataclass
class PartialUtterance(Event):
    """Interim transcript while the user is still speaking (Stream RAG-style speculation)."""

    text: str


@dataclass
class AgentResponse(Event):
    text: str


@dataclass
class SilenceDetected(Event):
    pass


@dataclass
class TopicShift(Event):
    topic: str


@dataclass
class PriorityRetrieval(Event):
    """Published by the Fast Talker on a cache miss."""

    query: str
    embedding: np.ndarray
