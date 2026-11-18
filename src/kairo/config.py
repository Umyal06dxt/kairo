from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Config:
    """Defaults match Table 6 of the VoiceAgentRAG paper."""

    # cache
    cache_max_size: int = 2000
    cache_ttl_s: float = 300.0
    similarity_threshold: float = 0.40  # tau, query-to-document cosine
    dedup_threshold: float = 0.95
    # slow thinker
    max_predictions: int = 5
    prefetch_top_k: int = 10
    rate_limit_s: float = 0.5
    prediction_history_turns: int = 6
    # fast talker
    max_context_chunks: int = 10
    fallback_to_store: bool = True
    cache_on_miss: bool = True
    # llm
    temperature: float = 0.3
    # documents
    chunk_size: int = 512
    chunk_overlap: int = 50
    # stream
    stream_window: int = 10

    # --- beyond the paper (all off/neutral by default so Config() == paper Table 6) ---
    strategy: str = "llm"            # slow-thinker prediction: none | llm | neighbors | hybrid
    llm_context_chunks: int = 10     # chunks actually sent to the answering LLM
    speculative_answers: bool = False  # pre-draft answers to predicted follow-ups
    draft_top: int = 2               # predictions to pre-draft per turn
    answer_threshold: float = 0.85   # min question-question cosine to serve a pre-drafted answer
    answer_cache_size: int = 200
    neighbor_seeds: int = 2          # retrieved chunks to expand in the neighbors strategy
    neighbor_k: int = 5              # neighbours fetched per seed
    partial_min_chars: int = 12      # ignore shorter partial transcripts
    lexical_rerank: bool = False     # BM25+dense rerank of cached candidates before the LLM
    verify_hits: bool = False        # speculate-then-verify: check cache hits against the store in parallel


PAPER = Config()
# Tuned profile used by the CLI/web lab by default: hybrid prediction, speculative answers,
# smaller LLM context, lexical rerank, and speculate-then-verify (answers match traditional RAG).
# Re-tune thresholds per embedder.
OPTIMIZED = replace(Config(), strategy="hybrid", speculative_answers=True, llm_context_chunks=4,
                    lexical_rerank=True, verify_hits=True)


# Query-to-document cosine scales differ a lot between embedders (a correct chunk scores ~0.48 on
# OpenAI text-embedding-3-small but ~0.71 on bge-small), so the cache threshold must be per-embedder.
# Values come from the threshold sweeps in docs/benchmarks (re-run `kairo bench --sweep` to retune).
DEFAULT_TAU = {"openai": 0.40, "local": 0.60, "hash": 0.30}


def for_embedder(config: "Config", embedder: str) -> "Config":
    """Return `config` with the similarity threshold set for the given embedder family."""
    return replace(config, similarity_threshold=DEFAULT_TAU.get(embedder, config.similarity_threshold))
