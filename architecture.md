# Kairo Architecture

Kairo is a speculative-RAG voice agent. A foreground agent (**Fast Talker**) answers the caller from an in-memory cache; a background agent (**Slow Thinker**) predicts the next questions and fills that cache ahead of time.

## System overview

```mermaid
flowchart TB
    subgraph Clients["Entry points"]
        WEB["Browser UI<br/>server/static (Call / Experiments / Research)"]
        CLI["CLI<br/>cli.py: serve, chat, voice, bench, ingest"]
        MIC["Mic + speakers (ALSA)<br/>voice/loop.py"]
    end

    subgraph Server["server/ (FastAPI)"]
        APP["app.py<br/>GET /, /api/info<br/>GET+POST /api/experiments<br/>WS /ws"]
        SESS["session.py<br/>one Session per websocket = one call"]
    end

    subgraph Voice["voice/"]
        VIO["io.py<br/>Whisper STT, Edge TTS, audio decode"]
        VEP["endpoint.py<br/>sentence splitting, endpointing"]
    end

    subgraph Core["Core (kairo/)"]
        ROUTER["router.py<br/>MemoryRouter: wires everything"]
        STREAM["stream.py<br/>ConversationStream (event bus)"]
        FAST["fast_talker.py<br/>Fast Talker (foreground)"]
        SLOW["slow_thinker.py<br/>Slow Thinker (background)"]
        RERANK["rerank.py<br/>BM25 + dense rerank"]
        TEL["telemetry.py"]
    end

    subgraph Memory["In-memory caches"]
        SC["cache.py<br/>SemanticCache (FAISS, TTL, dedup)"]
        AC["answer_cache.py<br/>AnswerCache (pre-drafted answers)"]
    end

    subgraph Providers["providers/ (pluggable)"]
        EMB["Embedder<br/>local (on-device) / openai / hash"]
        LLM["LLM<br/>openai / extractive (offline)"]
        VS["VectorStore<br/>faiss_store / qdrant_ / DelayedStore"]
    end

    KB[("Knowledge base<br/>ingest.py: chunk + index")]
    BENCH["bench/<br/>domains, scenarios, distractors, run"]

    WEB <-->|"text, audio, events"| APP
    APP --> SESS
    SESS --> VIO
    VIO --> VEP
    CLI --> ROUTER
    MIC --> VIO
    SESS --> ROUTER
    CLI --> BENCH
    APP -->|"/api/experiments"| BENCH
    BENCH --> ROUTER

    ROUTER --> STREAM
    ROUTER --> FAST
    ROUTER --> SLOW
    STREAM -->|"UserUtterance, PartialUtterance"| SLOW
    FAST -->|"AgentResponse, PriorityRetrieval"| STREAM

    FAST -->|"1. lookup"| AC
    FAST -->|"2. lookup"| SC
    FAST -->|"3. on miss"| VS
    FAST --> RERANK
    SLOW -->|"prefetch pages"| SC
    SLOW -->|"pre-draft answers"| AC
    SLOW --> VS

    FAST --> EMB
    FAST --> LLM
    SLOW --> EMB
    SLOW --> LLM
    KB --> VS
    FAST -.-> TEL
    SLOW -.-> TEL
```

## One turn, step by step

```mermaid
sequenceDiagram
    autonumber
    actor Caller
    participant S as Session / Voice IO
    participant F as Fast Talker
    participant C as AnswerCache + SemanticCache
    participant V as Vector store
    participant L as LLM
    participant T as Slow Thinker

    Caller->>S: speaks or types (partials while talking)
    S-->>T: PartialUtterance (speculative retrieval)
    T->>V: search on partial text
    T->>C: prefetch pages
    Caller->>S: final utterance
    S->>F: answer(question)
    F->>F: embed query once, shared with Slow Thinker
    F->>C: look up pre-drafted answer, then cached pages
    alt cache hit
        par speculate
            F->>L: stream answer from cached context
        and verify (RaLMSpec)
            F->>V: search in parallel (~100 ms)
        end
        opt top result missing from context
            F->>L: cancel, regenerate from correct chunks
        end
    else miss
        F->>V: retrieve
        F->>C: remember the pages
        F->>L: stream answer
    end
    L-->>S: tokens, split into sentences
    S-->>Caller: TTS audio
    F-->>T: AgentResponse
    T->>L: predict likely next questions
    T->>V: prefetch pages for each prediction, plus neighbors
    T->>C: store pages and pre-drafted answers
```

## Components

| Layer | Files | Role |
|---|---|---|
| Entry | `cli.py`, `server/app.py`, `voice/loop.py` | CLI commands, web server, local mic loop |
| Session | `server/session.py` | One per websocket; owns a router, streams audio and events to the UI |
| Voice | `voice/io.py`, `voice/endpoint.py` | STT (Whisper), TTS (Edge), audio decoding, sentence splitting |
| Orchestration | `router.py`, `stream.py`, `events.py` | Builds the agents and caches; event bus carries `UserUtterance`, `PartialUtterance`, `AgentResponse`, `PriorityRetrieval` |
| Foreground | `fast_talker.py` | Cache-first answer, speculate-then-verify, fallback to the store |
| Background | `slow_thinker.py` | Predict next questions, prefetch pages and neighbors, pre-draft answers |
| Memory | `cache.py`, `answer_cache.py`, `rerank.py` | FAISS semantic cache, answer cache, BM25 + dense rerank |
| Providers | `providers/*` | Swappable embedder, LLM and vector store behind `base.py` interfaces; `fake.py` gives offline stand-ins |
| Data | `ingest.py`, `bench/*` | Chunk and index documents; benchmark profiles, domains and scenarios |
| UI | `server/static/*`, `web/` | Call, Experiments and Research tabs |

## Design notes

- **Embed once.** The router computes the query embedding once and shares it between agents.
- **Verify off the critical path.** The store search (~100 ms) finishes before the LLM's first token (~1 s), so verification costs no extra latency.
- **Pluggable providers.** Everything runs offline with `hash` embeddings and the `extractive` LLM, which is what the free benchmarks use.
