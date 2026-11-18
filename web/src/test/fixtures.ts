import type { ExperimentResult, ProfileSummary, ReadyMsg, TurnMsg } from "@/api/types";

export const summary = (over: Partial<ProfileSummary> = {}): ProfileSummary => ({
  n: 100, errors: 0, hit_rate: 0.8, warm_hit_rate: 0.9, draft_rate: 0.1, accuracy: 0.95, evidence: 0.95, fidelity: 0.8,
  embed_ms: 6, retrieval_ms: 5, hit_retrieval_ms: 0.2, llm_ms: 1000, user_p50: 950, user_p90: 2000, ...over,
});

export const ready = (over: Partial<ReadyMsg> = {}): ReadyMsg => ({
  t: "ready",
  board: { n_chunks: 3, n_extra: 0, docs: [{ name: "fees.md", title: "Fee Schedule", extra: false, chunks: ["fees.md:0", "fees.md:1", "fees.md:2"] }] },
  settings: { domain: "bank", profile: "optimized", embedder: "local", llm: "openai", distractors: true, tau: null, store_latency_ms: 110, speak: false },
  profile: { key: "optimized", label: "Kairo optimized", cache: true },
  config: { strategy: "hybrid", verify: true, drafts: true, tau: 0.6, context: 6, rerank: true },
  llm: "openai", embedder: "local", notes: [],
  domain: { key: "bank", title: "Harbor FCU - credit union voice support", blurb: "A support line.", scenarios: [
    { key: "B1 Lost debit card", turns: 10, questions: ["I lost my debit card, what now?", "How do I freeze it?", "Third question"] },
    { key: "B2 Fees", turns: 10, questions: ["What is the overdraft fee?", "Is there a stop payment fee?"] },
  ] },
  voice: { stt: "ready", tts: true }, ...over,
});

export const turnMsg = (over: Partial<TurnMsg> = {}): TurnMsg => ({
  t: "turn", q: "What is the overdraft fee?", answer: "It is 30 dollars per item.", source: "cache", hit: true, verified: true,
  corrected: false, embed_ms: 5, retrieval_ms: 0.2, llm_ms: 900, user_ms: 905, chunk_ids: ["fees.md:0"], tags: ["predicted"],
  draft_sim: null, store_failed: false, gold: { doc_ok: true, answer_ok: true, doc: "fees.md" },
  stats: { turns: 1, hits: 1, drafts: 0, corrected: 0, avg_user_ms: 905 }, ...over,
});

export const experiment = (id: string, env = "embedder=local, llm=openai", keys = ["baseline", "optimized"]): ExperimentResult => ({
  id, domain: "bank", env, notes: ["157 chunks indexed"], generated: "2026-11-18 15:00", sweep: [],
  profiles: Object.fromEntries(keys.map((k, i) => [k, { label: `Profile ${k}`, summary: summary(i ? { user_p50: 500 } : {}) }])),
});
