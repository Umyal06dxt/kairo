# Kairo — voice-enabled speculative RAG

Implementation of the dual-agent *VoiceAgentRAG* design (arXiv:2603.02206): a background **Slow Thinker** predicts follow-up topics and pre-fills a FAISS semantic cache; the foreground **Fast Talker** answers from the cache (<1 ms) and only hits the vector DB on a miss. Design: `docs/superpowers/specs/`, plan: `docs/superpowers/plans/`.

## Setup
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev,voice,qdrant]'
export OPENAI_API_KEY=...        # GPT (gpt-4o-mini) + text-embedding-3-small
```
Voice needs `arecord`/`aplay` (ALSA) and a network connection for Edge TTS. First run downloads the Whisper model.

## Use
```bash
kairo ingest --kb path/to/docs --index data/index   # .md/.txt -> chunks -> FAISS
kairo chat  --index data/index                      # text REPL, shows cache HIT/miss + latency
kairo voice --index data/index                      # mic -> Whisper -> RAG -> Edge TTS
kairo bench --mode offline --sweep                  # plumbing check, no API key
kairo bench --mode live --sweep --out report.md     # paper-comparable (OpenAI, ~110 ms injected DB latency)
kairo bench --mode live --qdrant                    # real Qdrant (QDRANT_URL, QDRANT_API_KEY)
```
Use `--store qdrant` on `ingest/chat/voice` for Qdrant instead of local FAISS.

## Test
`.venv/bin/python -m pytest -q`

## Known limitations
- The Fast Talker still embeds each query via the OpenAI API (~100-250 ms) before the cache lookup, so only the *vector-DB* round trip is removed from the critical path (as in the paper), not the embedding call.
- The 0.40 cache threshold was tuned for `text-embedding-3-small`; re-run `kairo bench --sweep` if you change models.
- Voice endpointing is energy-based (`--vad-threshold`); tune it for your mic. Use headphones to avoid echo (the mic is muted while Kairo speaks, plus 0.4 s).
- Cached chunks are not invalidated if the knowledge base changes mid-conversation (5-minute TTL only).
