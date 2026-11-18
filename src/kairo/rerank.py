"""Cheap lexical+dense reranking of already-retrieved candidates (microseconds, no model call).

Dense embeddings blur exact tokens (error codes, amounts, product names); BM25 over the few
candidates restores them. IDF is computed over the candidate set itself, so no corpus
statistics are needed and it works on whatever the cache happens to hold."""

import math
import re
from collections import Counter

from .types import Retrieved

_TOK = re.compile(r"[a-z0-9]+")
_STOP = frozenset("a an the is are of to for and or in on do does i you my me it what how can be "
                  "there any your with at by from this that when".split())


def _tokens(s: str) -> list[str]:
    return [w for w in _TOK.findall(s.lower()) if w not in _STOP]


def _bm25(query: str, docs: list[str], k1: float = 1.2, b: float = 0.75) -> list[float]:
    d = [_tokens(x) for x in docs]
    n = len(d)
    avg = (sum(len(x) for x in d) / n) or 1.0
    df = Counter(w for x in d for w in set(x))
    q = set(_tokens(query))
    out = []
    for x in d:
        tf, s = Counter(x), 0.0
        for w in q:
            if w in tf:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * tf[w] * (k1 + 1) / (tf[w] + k1 * (1 - b + b * len(x) / avg))
        out.append(s)
    return out


def rerank(query: str, found: list[Retrieved], w_dense: float = 0.6) -> list[Retrieved]:
    """Reorder candidates by w*dense + (1-w)*bm25, each min-max normalised within the set."""
    if len(found) < 2:
        return found
    lex = _bm25(query, [r.chunk.text for r in found])
    dense = [r.score for r in found]
    lo, span = min(dense), (max(dense) - min(dense)) or 1.0
    top = max(lex) or 1.0
    fused = [w_dense * (d - lo) / span + (1 - w_dense) * (x / top) for d, x in zip(dense, lex)]
    order = sorted(range(len(found)), key=lambda i: -fused[i])
    return [found[i] for i in order]
