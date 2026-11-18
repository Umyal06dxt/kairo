# Kairo experiment — domain **bank** (embedder=local, llm=openai, tau=0.60)

> 64 near-domain distractor pages added (GPT-written, same credit union)
> 157 chunks indexed (12 domain docs)
> vector store latency simulated at 110 ms

| Profile | Hit rate | Warm | Draft | Accuracy | Evidence | Fidelity | Embed ms | Hit retr. ms | LLM 1st tok ms | **User p50 ms** | p90 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Kairo optimized (verified) | 77% | 86% | 10% | 95% | 93% | 77% | 7 | 14.96 | 1056 | **954** | 2004 |

_User ms = embed + retrieval + LLM first token (excludes STT/TTS). Fidelity = overlap of served top-3 chunks with the store's exact top-3 on cache hits._
