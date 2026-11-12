# Kairo Voice Speculative RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Voice agent where RAG retrieval is taken off the critical path by a background predictive prefetcher feeding an in-memory semantic cache.

**Architecture:** Python asyncio. `MemoryRouter` publishes utterances on a `ConversationStream`; `FastTalker` (cache-first answer) and `SlowThinker` (predict + prefetch) consume concurrently. Cache = FAISS flat-IP over document-chunk embeddings. All external services behind protocols so everything is testable offline.

**Tech Stack:** Python 3.10, numpy, faiss-cpu, pytest + pytest-asyncio; optional: openai, anthropic, qdrant-client, faster-whisper, edge-tts, sounddevice.

**Spec:** `docs/superpowers/specs/2026-11-12-kairo-voice-agent-rag-design.md`

**Commits:** The user said NOT to commit. No task contains a commit step; do not add one.

## Global Constraints

- Defaults verbatim from spec §8: cache max 2000, TTL 300 s, tau 0.40, dedup 0.95, predictions 5, prefetch top-k 10, rate limit 0.5 s, max context chunks 10, chunk 512/50, window 10, prediction history 6, LLM temp 0.3.
- Cache is indexed by **document** embeddings only (spec §4).
- Core package imports with no voice/network deps installed.
- Run tests with `.venv/bin/python -m pytest`.
- Exceptions inside the Slow Thinker never propagate; Fast Talker always yields an answer.

## Review Focus

- Empty cache `get` returns `[]` (no FAISS error).
- Utterance arriving while previous prediction cycle still running: old cycle cancelled, new one proceeds.
- LLM returns non-JSON / prose / empty prediction list: turn continues, no crash.
- Vector store raises on a miss: Fast Talker still answers (no context) and flags it.
- Empty / whitespace-only STT transcript: ignored, no retrieval, no LLM call.

## File Structure

```
pyproject.toml
src/kairo/{__init__,config,events,stream,cache,types}.py
src/kairo/providers/{__init__,base,fake,openai_,anthropic_,qdrant_,faiss_store}.py
src/kairo/{slow_thinker,fast_talker,router,ingest}.py
src/kairo/voice/{__init__,stt,tts,mic,loop}.py
src/kairo/bench/{__init__,kb,scenarios,run}.py
src/kairo/cli.py
tests/…  (one test file per module)
```

## Status

All 10 tasks done (44 tests passing). Deviations from the plan as written:
- LLM is GPT only (`OpenAILLM`, `gpt-4o-mini`); the Anthropic provider was removed.
- Voice uses `arecord`/`aplay` (ALSA) + PyAV instead of sounddevice/ffmpeg because PortAudio is not installed. Files: `voice/endpoint.py` (Endpointer, split_sentences), `voice/io.py` (WhisperSTT, EdgeTTS, ArecordMic), `voice/loop.py`.
- Benchmark KB chunks to 34 chunks (paper: 76); scenarios are original (the paper's are unpublished in the text).
- Benchmark modes: `offline` (hash embeddings, no prediction: reactive-caching ablation only) and `live` (OpenAI). The live run has NOT been executed (no OPENAI_API_KEY in this session).
- Not exercised in this session: Whisper transcription (model download), mic capture, speaker playback, real Qdrant Cloud.

### Task 1: Project scaffold + Config + Events — DONE

**Files:** Create `pyproject.toml`, `src/kairo/{__init__,config,events,types}.py`, `tests/test_config.py`

**Interfaces — Produces:**
- `Config` (frozen dataclass) with fields per spec §8.
- `Chunk(id: str, text: str, meta: dict)`; `Retrieved(chunk: Chunk, embedding: np.ndarray, score: float)`.
- Events: `UserUtterance(text)`, `AgentResponse(text)`, `SilenceDetected`, `TopicShift(topic)`, `PriorityRetrieval(query, embedding)`.

- [x] Test: `Config()` values equal spec §8.
- [x] Implement and run `pytest tests/test_config.py` -> PASS.

### Task 2: ConversationStream — DONE

**Files:** Create `src/kairo/stream.py`, `tests/test_stream.py`

**Interfaces — Produces:**
- `ConversationStream(window: int = 10)`
- `subscribe() -> asyncio.Queue[Event]`; `async publish(event) -> None` (fan-out to every subscriber); `add_turn(role: str, text: str)`; `history(n: int | None = None) -> list[tuple[str, str]]`.

- [x] Tests: two subscribers both receive an event; window keeps only last N turns; `history(6)` returns last 6.
- [x] Implement; run -> PASS.

### Task 3: SemanticCache — DONE

**Files:** Create `src/kairo/cache.py`, `tests/test_cache.py`

**Interfaces — Produces:**
- `SemanticCache(dim: int, max_size=2000, ttl=300.0, dedup=0.95, clock=time.monotonic)`
- `put(chunk: Chunk, embedding: np.ndarray, score: float = 0.0) -> bool` (True if new, False if deduped)
- `get(query: np.ndarray, k: int = 10, tau: float = 0.40) -> list[Retrieved]`
- `__len__`

- [x] Tests: empty get -> `[]`; near-duplicate (>0.95) not added; get respects tau and k, sorted by similarity; entries expire after TTL (fake clock); LRU eviction at max_size drops the least recently *accessed*; indexing is by document embedding (put chunk A, query close to A returns A even though no query was ever cached).
- [x] Implement; run -> PASS.

### Task 4: Provider protocols + fakes — DONE

**Files:** Create `src/kairo/providers/{__init__,base,fake}.py`, `tests/test_fake_providers.py`

**Interfaces — Produces:**
- `Embedder`: `dim: int`; `async embed(texts: list[str]) -> np.ndarray` (n x dim, L2-normalised).
- `LLM`: `async predict_topics(history: list[tuple[str,str]], n: int) -> list[str]`; `stream_answer(question: str, context: list[Chunk], history) -> AsyncIterator[str]`.
- `VectorStore`: `async search(vec: np.ndarray, k: int) -> list[Retrieved]`; `async add(chunks, embeddings)`.
- Fakes: `HashEmbedder(dim=64)` (bag-of-words hashing, so overlapping words -> higher cosine), `FakeLLM`, `InMemoryStore(latency_s=0.0)`.

- [x] Tests: HashEmbedder output is unit-norm and deterministic; texts sharing words are closer than disjoint ones; InMemoryStore returns best match first and honours latency.
- [x] Implement; run -> PASS.

### Task 5: FastTalker — DONE

**Files:** Create `src/kairo/fast_talker.py`, `tests/test_fast_talker.py`

**Interfaces — Consumes:** `Embedder`, `LLM`, `VectorStore`, `SemanticCache`, `ConversationStream`, `Config`. **Produces:**
- `@dataclass TurnResult(answer: str, hit: bool, source: str, retrieval_ms: float, embed_ms: float, store_failed: bool)`
- `FastTalker.__init__(embedder, llm, store, cache, stream, config)`
- `async answer(question: str, on_token: Callable[[str], None] | None = None) -> TurnResult`

- [x] Tests: warm cache -> `hit=True`, store untouched (spy counts 0 calls); cold -> `hit=False`, store called once, cache now non-empty, `PriorityRetrieval` published; second identical question -> hit; store raising -> `store_failed=True` and non-empty answer; blank question -> returns empty result without calling embedder/LLM.
- [x] Implement; run -> PASS.

### Task 6: SlowThinker — DONE

**Files:** Create `src/kairo/slow_thinker.py`, `tests/test_slow_thinker.py`

**Interfaces — Produces:** `SlowThinker(embedder, llm, store, cache, stream, config)`; `async run() -> None` (loop until cancelled); `async handle_utterance(text)`; `async handle_priority(event: PriorityRetrieval)`.

- [x] Tests: after `handle_utterance`, cache contains chunks for direct retrieval AND for each predicted topic; predictions batch-embedded in one `embed` call; priority retrieval calls `store.search` with `k = 2 * config.prefetch_top_k`; `llm.predict_topics` returning garbage/raising -> no exception, direct retrieval still cached; new utterance cancels in-flight cycle (use a slow fake store + assert first cycle's later predictions never cached); two cycles within 0.5 s -> second waits (fake sleep).
- [x] Implement; run -> PASS.

### Task 7: MemoryRouter — DONE

**Files:** Create `src/kairo/router.py`, `tests/test_router.py`

**Interfaces — Produces:** `MemoryRouter.create(embedder, llm, store, config=Config()) -> MemoryRouter`; `async start()`; `async stop()`; `async handle_utterance(text, on_token=None) -> TurnResult` (publishes `UserUtterance`, runs FastTalker, records `AgentResponse`).

- [x] Test (end-to-end, fakes, store latency 50 ms): scripted 5-turn single-topic conversation with 0.2 s gaps -> turns >=3 are cache hits; `stop()` cancels the SlowThinker task cleanly.
- [x] Implement; run -> PASS.

### Task 4b: AnthropicLLM — DONE

`src/kairo/providers/anthropic_.py` (`AnthropicLLM(model="claude-opus-5-5", effort="low", use_fallbacks=True, client=None)`, `parse_topics`), `tests/test_anthropic_llm.py` (request shape has no temperature/thinking, refusal -> `[]`, tolerant JSON parse). Spec §8.1.

### Task 8: Real providers + ingest + CLI (text mode) — DONE

`OpenAIEmbedder` and `OpenAILLM` are DONE (`providers/openai_.py`, `tests/test_openai_providers.py`); shared prompts in `providers/prompts.py`. Remaining here: `QdrantStore`, `FaissStore`, ingest, CLI with `--llm {openai,anthropic}`.

**Files:** Create `src/kairo/providers/{openai_,anthropic_,qdrant_,faiss_store}.py`, `src/kairo/ingest.py`, `src/kairo/cli.py`, tests for chunker and FaissStore.

**Interfaces — Produces:** `chunk_text(text: str, size=512, overlap=50) -> list[str]` (recursive split on `\n\n`, `\n`, `. `, ` `); `OpenAIEmbedder`, `OpenAILLM`, `AnthropicLLM`, `QdrantStore`, `FaissStore`; `kairo chat --kb DIR` text REPL.

- [x] Tests: `chunk_text` never exceeds size, consecutive chunks overlap, empty string -> `[]`; FaissStore round-trips add/search. Network providers: construction-only tests (no network).
- [x] Implement; `kairo chat` smoke-run against fakes.

### Task 9: Voice layer — DONE

**Files:** Create `src/kairo/voice/{stt,tts,mic,loop}.py`, tests for VAD + sentence splitter.

**Interfaces — Produces:** `WhisperSTT.transcribe(audio: np.ndarray, sr: int) -> str`; `EdgeTTS.speak(text: str) -> None`; `split_sentences(token_stream) -> AsyncIterator[str]`; `Endpointer(sr, silence_ms=700, threshold=...)` with `feed(frame) -> np.ndarray | None`; `run_voice(router)`.

- [x] Tests: Endpointer emits one utterance after speech+silence, nothing on pure silence; `split_sentences` yields on `.?!` boundaries and flushes the tail.
- [x] Implement behind optional deps; manual mic smoke test.

### Task 10: Benchmark harness — DONE

**Files:** Create `src/kairo/bench/{kb,scenarios,run}.py`, `tests/test_bench.py`

**Interfaces — Produces:** `run_benchmark(mode: Literal["offline","qdrant"]) -> Report` with per-scenario hit rate, warm hit rate, avg retrieval, threshold sweep; baseline vs dual-agent; report labels its mode.

- [x] Test: tiny 2-scenario offline run returns hit rate in [0,1], dual-agent mean retrieval < baseline mean retrieval.
- [x] Implement; run full offline benchmark; compare to paper Table 1–4 and record the gap honestly.

## Self-Review

- Spec coverage: §3 components -> Tasks 1–10; §4 -> 3; §5 -> 6; §6 -> 5; §7 -> 9; §9 -> 10. TopicShift/SilenceDetected producers intentionally out of scope.
- Types: `Retrieved`, `Chunk`, `TurnResult` names are used consistently across tasks.
