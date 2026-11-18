# Kairo experiment — domain **bank** (embedder=local, llm=extractive, tau=0.60)

> extractive stand-in LLM (simulated 400 ms first token; real GPT measured ~1200 ms): no follow-up prediction, so only the none/neighbors strategies are meaningful; answers are copied sentences
> 64 near-domain distractor pages added (GPT-written, same credit union)
> 157 chunks indexed (12 domain docs)
> vector store latency simulated at 110 ms

| Profile | Hit rate | Warm | Draft | Accuracy | Evidence | Fidelity | Embed ms | Hit retr. ms | LLM 1st tok ms | **User p50 ms** | p90 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Traditional RAG (no cache) | 0% | 0% | 0% | — | 97% | — | 15 | — | 403 | **528** | 540 |
| Reactive cache (no prediction) | 84% | 93% | 0% | — | 92% | 72% | 5 | 0.11 | 401 | **406** | 518 |
| Neighbour prefetch (no LLM) | 84% | 93% | 0% | — | 94% | 78% | 5 | 0.11 | 401 | **406** | 517 |
| Neighbours + verify + rerank (no LLM) | 74% | 82% | 0% | — | 91% | 77% | 6 | 0.39 | 441 | **407** | 595 |

_User ms = embed + retrieval + LLM first token (excludes STT/TTS). Fidelity = overlap of served top-3 chunks with the store's exact top-3 on cache hits._

## Similarity-threshold sweep
| tau | Hit rate | Evidence | Fidelity |
|---|---|---|---|
| 0.75 | 29% | 90% | 51% |
| 0.70 | 50% | 85% | 59% |
| 0.65 | 68% | 88% | 71% |
| 0.60 | 74% | 91% | 77% |
| 0.55 | 76% | 90% | 78% |
| 0.50 | 78% | 91% | 77% |
