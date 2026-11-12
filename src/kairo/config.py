from dataclasses import dataclass


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
