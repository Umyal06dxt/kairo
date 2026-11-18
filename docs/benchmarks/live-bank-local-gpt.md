# Kairo experiment — domain **bank** (embedder=local, llm=openai, tau=0.60)

> 64 near-domain distractor pages added (GPT-written, same credit union)
> 157 chunks indexed (12 domain docs)
> vector store latency simulated at 110 ms

| Profile | Hit rate | Warm | Draft | Accuracy | Evidence | Fidelity | Embed ms | Hit retr. ms | LLM 1st tok ms | **User p50 ms** | p90 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Traditional RAG (no cache) | 0% | 0% | 0% | 95% | 97% | — | 7 | — | 1068 | **1067** | 1479 |
| VoiceAgentRAG (paper) | 85% | 94% | 0% | 91% | 92% | 81% | 7 | 0.15 | 1323 | **1045** | 2477 |
| Kairo fast (unverified) | 85% | 94% | 4% | 84% | 88% | 76% | 6 | 0.51 | 1145 | **960** | 1979 |
| Kairo optimized (verified) | 76% | 84% | 4% | 91% | 90% | 79% | 6 | 6.34 | 1214 | **928** | 2628 |

_User ms = embed + retrieval + LLM first token (excludes STT/TTS). Fidelity = overlap of served top-3 chunks with the store's exact top-3 on cache hits._
