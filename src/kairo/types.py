from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    meta: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass
class Retrieved:
    chunk: Chunk
    embedding: np.ndarray
    score: float
    tag: str = ""  # provenance in the cache: direct | predicted | neighbor | partial | miss
