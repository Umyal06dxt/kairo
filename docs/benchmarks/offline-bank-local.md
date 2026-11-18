# Kairo experiment — domain **bank** (embedder=local, llm=extractive)

> extractive stand-in LLM (simulated 400 ms first token; real GPT measured ~1200 ms): no follow-up prediction, so only the none/neighbors strategies are meaningful; answers are copied sentences
> 64 near-domain distractor pages added (GPT-written, same credit union)
> 157 chunks indexed (12 domain docs)
> vector store latency simulated at 110 ms

| Profile | Hit rate | Warm | Draft | Accuracy | Evidence | Fidelity | Embed ms | Hit retr. ms | LLM 1st tok ms | **User p50 ms** | p90 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Traditional RAG (no cache) | 0% | 0% | 0% | — | 97% | — | 15 | — | 403 | **529** | 537 |
| Reactive cache (no prediction) | 90% | 100% | 0% | — | 93% | 70% | 7 | 0.13 | 401 | **407** | 424 |
| Neighbour prefetch (no LLM) | 90% | 100% | 0% | — | 94% | 76% | 7 | 0.15 | 401 | **407** | 428 |
| Neighbours + verify + rerank (no LLM) | 78% | 87% | 0% | — | 92% | 77% | 8 | 0.56 | 449 | **408** | 1210 |

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
