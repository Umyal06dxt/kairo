from dataclasses import dataclass

import numpy as np


class Event:
    """Base class for conversation-stream events."""


@dataclass
class UserUtterance(Event):
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
