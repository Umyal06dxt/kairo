# Kairo — Voice-Enabled Speculative RAG (Design Spec)

Implements the dual-agent architecture of *VoiceAgentRAG* (arXiv:2603.02206, Salesforce AI Research, 2026) as a voice assistant named **Kairo**.

## 1. Goal

A voice agent whose RAG retrieval never sits on the critical latency path. A background **Slow Thinker** predicts follow-up topics and pre-fills an in-memory **semantic cache**; a foreground **Fast Talker** answers from that cache (<1 ms) and only falls back to the vector DB on a miss.

Targets from the paper (to be *measured*, not assumed): ~75% overall cache hit rate, ~79% on warm turns, ~110 ms -> ~0.35 ms retrieval on hits.

## 2. Scope

In scope (v1):
- Text-mode pipeline fully working and testable offline (fake providers).
- Voice I/O: STT (Whisper via faster-whisper), TTS (Edge TTS), push-to-talk / silence-endpointed mic loop.
- Providers behind interfaces: embeddings, LLM, vector store (FAISS local, Qdrant remote).
- Ingestion: load docs, recursive char chunking (512 / overlap 50), embed, index.
- Benchmark harness: traditional RAG baseline vs dual-agent, hit rate + retrieval latency + threshold sweep.

Out of scope (v1): WebRTC telephony, barge-in/interruption handling, multi-user sessions, cache persistence, the paper's `TopicShift`/`SilenceDetected` producers (event types exist; no producer).

## 3. Components

| Component | Responsibility |
|---|---|
| `config.Config` | All tunables, defaults = paper Table 6 |
| `events` | `UserUtterance`, `AgentResponse`, `SilenceDetected`, `TopicShift`, `PriorityRetrieval` |
| `stream.ConversationStream` | asyncio pub/sub bus (each subscriber gets its own queue) + sliding window of last N=10 turns |
| `cache.SemanticCache` | FAISS `IndexFlatIP` on L2-normalised **document** embeddings; put/get/evict |
| `providers.*` | `Embedder`, `LLM`, `VectorStore` protocols + OpenAI / Qdrant / FAISS / fake impls |
| `slow_thinker.SlowThinker` | Background task: direct retrieval, LLM topic prediction, parallel prefetch, priority retrieval |
| `fast_talker.FastTalker` | Embed query -> cache lookup -> fallback + cache-on-miss -> streaming LLM answer |
| `router.MemoryRouter` | Wires everything; `handle_utterance(text) -> Turn` |
| `voice.*` | STT, TTS, mic loop, sentence-chunked streaming TTS |
| `ingest` | chunking + indexing CLI |
| `bench` | evaluation harness |

## 4. Semantic cache (the critical part)

- Index: `faiss.IndexFlatIP`, vectors L2-normalised so inner product = cosine.
- **Entries are indexed by their own document-chunk embedding**, never by the prediction query's embedding (paper §2.2: query-indexed caching returns topically-related but wrong chunks).
- `put(chunk, embedding, score, meta)`: if an existing entry has cosine > **0.95** (dedup threshold) it is refreshed (TTL/last-access/score) instead of added.
- `get(query_vec, k, tau)`: top-k entries with cosine >= **tau (0.40)**, expired entries excluded; updates last-access. Returns `[]` on empty cache.
- Eviction: TTL **300 s** (expired entries purged lazily on get/put); when size > **2000**, evict least-recently-accessed. FAISS flat indexes can't delete cheaply, so the index is rebuilt after eviction (acceptable at <=2000 entries).
- Thread/async safety: all mutation is synchronous with no awaits inside, so it is atomic under a single event loop. Not safe across threads (documented).
- Clock injectable for tests.

## 5. Slow Thinker

On `UserUtterance`:
1. Direct retrieval: embed utterance, vector-store top-k (10), cache each chunk with **its own** embedding.
2. Predict `n`<=5 follow-up topics via LLM from last 6 turns. Prompt demands **document-style descriptions, not questions**; output is a JSON list of strings. Malformed output -> skip prediction for that turn (log), never crash.
3. Prefetch: embed all predictions in one batch; `asyncio.gather` vector searches (top-k 10); cache results.

On `PriorityRetrieval`: retrieve with 2x top-k immediately for the missed query.
Rate limit: min 0.5 s between prediction cycles. A new utterance cancels an in-flight prediction/prefetch cycle for the previous turn (stale work must not delay the current one); priority retrievals are never dropped by rate limiting.
Any exception in a cycle is logged and swallowed; the loop continues.

## 6. Fast Talker

1. Embed query. 2. `cache.get(vec, k=10, tau=0.40)`. 3. Hit -> use chunks. Miss -> `vector_store.search(vec, 10)`, `cache.put` each result, publish `PriorityRetrieval`. 4. Stream LLM answer with chunks as context (max 10 chunks). Records `retrieval_ms`, `hit`, `source` ("cache"|"store") per turn.
If the vector store fails on a miss, answer without context and say so in metadata (voice agent must still speak).

Concurrency note (paper §2.1): both agents receive the utterance concurrently. On turn 1 the Slow Thinker's direct retrieval races the Fast Talker's miss path; both write the same chunks, and dedup makes that idempotent.

## 7. Voice layer

- Capture: `arecord` (ALSA) 16 kHz mono, playback via `aplay`, MP3 decode via PyAV (no PortAudio/ffmpeg); energy-based VAD endpointing (configurable silence ms) -> utterance WAV/array.
- STT: `faster-whisper` (model size configurable, default `base.en`), run in executor thread.
- TTS: `edge-tts`, synthesized per sentence as LLM tokens stream in, so audio starts before generation finishes.
- All voice deps optional (`pip install .[voice]`); core + text mode must import without them.
- Latency reporting per turn: stt_ms, embed_ms, retrieval_ms, llm_first_token_ms, first_audio_ms (printed by `kairo voice`).

## 8. Config defaults (verbatim from paper Table 6)

cache max 2000; TTL 300 s; tau 0.40; dedup 0.95; predictions/turn 5; prefetch top-k 10; rate limit 0.5 s; fast-talker max chunks 10; fallback on; cache-on-miss on; embedding `text-embedding-3-small` (1536-d); LLM temp 0.3; chunk 512 / overlap 50; stream window 10; prediction history 6 turns.
Embedding dim is read from the embedder, not hard-coded.

### 8.1 OpenAI provider (decided 2026-11-12)
- Embeddings: OpenAI `text-embedding-3-small` (1536-d), as in the paper — this resolves the embedder choice; tau 0.40 was tuned on this model.
- LLM: `OpenAILLM`, default `gpt-4o-mini`, temperature 0.3, as in the paper (uses `max_completion_tokens`). Prompts/parsing live in `providers/prompts.py`.
- **Decision: GPT is the only LLM backend** (an Anthropic provider was prototyped, then removed on request).

## 9. Evaluation

- Synthetic KB (NovaCRM-like, 12 docs) + 10 scripted 20-turn scenarios, per paper §3.
- Baseline (embed -> store -> generate) vs dual-agent; metrics: hit rate (overall/warm), retrieval latency, cache growth, threshold sweep 0.30–0.55.
- Offline mode uses a fake store with configurable injected latency (default 110 ms) so numbers are reproducible; real-Qdrant mode available. Reports must label which mode produced them.
- Caveat to document: with a hash/fake embedder, absolute hit rates are meaningless; only real embeddings reproduce paper numbers.

## 10. Risks / open questions

- Query-to-document cosine is low (0.30–0.55); tau must be re-tuned per embedding model (sweep tool provided).
- Prediction cost: 5 predictions x 10 chunks per turn is embedding-API heavy; keep batch embedding.
- Stale cache if KB changes mid-conversation (TTL only).
- Paper evaluates retrieval latency, not end-to-end; LLM latency dominates unless a fast model is used.
