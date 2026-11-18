# Kairo: speculative RAG for voice

A voice assistant whose knowledge lookups are mostly hidden from the caller. A background agent guesses what the caller will ask next and loads those pages into memory; a foreground agent answers from memory and only goes to the vector database when it has to.

It starts from the dual-agent design in *VoiceAgentRAG* (Qiu et al., 2026, arXiv:2603.02206), reproduces it, then measures where it falls short and tests fixes drawn from Speculative RAG (Google), Stream RAG and RaLMSpec. The real-world setting is a support line for a (fictional) credit union.

```
caller ──► Fast Talker ──► memory hit? ──yes──► answer (GPT streams, or a pre-drafted answer)
                │                │no
                │                └──► vector database ──► answer, and remember the pages
                ▼
           Slow Thinker (background): predict next questions ► prefetch pages ► pre-draft answers
```

## Run the lab

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,voice,qdrant,local,web]'
echo 'OPENAI_API_KEY=sk-...' > .env        # optional: without it, answers come from an offline stand-in
.venv/bin/kairo make-distractors             # optional, ~2 cents: 64 extra pages so the KB isn't tiny
.venv/bin/kairo serve                        # http://127.0.0.1:8000
```

The page has three tabs:

- **Call.** Type or hold the mic button and talk (the browser records, the server transcribes with Whisper and speaks back with Edge TTS). A switchboard shows every page of the knowledge base as a lamp: lit means in memory, colour says why (asked, predicted, nearby, heard while typing, fetched after a miss). The right-hand ledger narrates the background agent. Pick a scripted call to watch prediction happen.
- **Experiments.** Replay scripted calls against several strategies and compare wait, hit rate, whether the right page was used, and answer correctness.
- **Research.** The questions this raises, what was measured, and what is open.

`.env` is ignored by git. Never commit it.

## What's in the box

| Idea | Source | Where |
|---|---|---|
| Slow Thinker / Fast Talker, FAISS semantic cache indexed by document embeddings | VoiceAgentRAG | `slow_thinker.py`, `fast_talker.py`, `cache.py` |
| Pre-drafted answers for predicted questions, trusted only after checks | Speculative RAG | `answer_cache.py` |
| Retrieve on partial transcripts (typed, or browser speech recognition) | Stream RAG | `router.speculate`, lamps in the UI |
| Speculate, then verify hits against the database in parallel | RaLMSpec | `fast_talker.py` (`verify_hits`) |
| Prefetch nearby pages with no model call | new | `slow_thinker._neighbors` |
| BM25 + dense rerank of cached candidates | new | `rerank.py` |
| On-device embeddings (about 5 ms vs about 700 ms for an API) | | `providers/local.py` |

## Command line

```bash
kairo ingest --kb path/to/docs --index data/index    # your own documents
kairo chat   --index data/index                      # text REPL
kairo voice  --index data/index                      # microphone and speakers (ALSA)
kairo bench  --domain bank --distractors 64 --profiles baseline,paper,optimized \
             --embedder local --llm openai --json data/experiments/run.json
kairo bench  --domain bank --profiles baseline,reactive,neighbors,verified     # offline, free
kairo bench  --profiles optimized --set llm_context_chunks=6,answer_threshold=0.78
```

Profiles: `baseline` (plain RAG), `reactive`, `paper`, `neighbors`, `verified`, `fast`, `optimized`. `--llm extractive` runs with no key and no cost, but cannot predict follow-ups, so only the no-prediction strategies mean anything there.

## Results

Generated reports live in `docs/benchmarks/`. Read them with these cautions:

- Each is one run of about 100 turns. Differences of a few points are noise.
- The knowledge bases are small (157 chunks) and the calls are scripted, so predictability is flattering. See the Research tab for what to test next.
- The offline runs use a stand-in LLM with a simulated first-token delay.
- The similarity threshold is per embedder (`DEFAULT_TAU` in `config.py`): the paper's 0.40 fits OpenAI embeddings; on-device `bge-small` needs about 0.60.

## Layout and tests

`src/kairo/` core (`config`, `cache`, `answer_cache`, `fast_talker`, `slow_thinker`, `router`, `rerank`), `providers/` (OpenAI, local, FAISS, Qdrant, fakes), `voice/`, `server/` (FastAPI + the page in `static/`), `bench/` (domains, gold answers, runner). Design notes: `docs/superpowers/specs/` and `plans/`.

```bash
.venv/bin/python -m pytest -q
```

## Known limitations

- The Fast Talker still embeds the question before the cache lookup; use the on-device embedder to make that about 5 ms.
- Background speculation shares the API with the foreground answer and can slow it down. Measure it with your own rate limits.
- Cached pages and drafts are not invalidated if the knowledge base changes mid-call (5-minute expiry only).
- No barge-in: speaking over the assistant is ignored.
- The mic is muted while Kairo speaks; use headphones.
