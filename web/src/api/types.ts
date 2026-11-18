/** Wire protocol shared with the Python server (src/kairo/server/session.py, app.py). */

export type LampTag = "direct" | "predicted" | "neighbor" | "partial" | "miss";
export type TurnSource = "draft" | "cache" | "store" | "none";
export type TurnVia = "text" | "voice" | "script";
export type SttState = "off" | "loading" | "ready" | "error";
export type LlmChoice = "auto" | "openai" | "extractive";
export type EmbedderChoice = "local" | "openai" | "hash";

export interface Settings {
  domain: string;
  profile: string;
  embedder: EmbedderChoice;
  llm: LlmChoice;
  distractors: boolean;
  tau: number | null;
  store_latency_ms: number;
  speak: boolean;
}

export interface BoardDoc { name: string; title: string; extra: boolean; chunks: string[] }
export interface Board { docs: BoardDoc[]; n_chunks: number; n_extra: number }
export interface Scenario { key: string; turns: number; questions?: string[] }

export interface ReadyMsg {
  t: "ready";
  board: Board;
  settings: Settings;
  profile: { key: string; label: string; cache: boolean };
  config: { strategy: string; verify: boolean; drafts: boolean; tau: number; context: number; rerank: boolean };
  llm: "openai" | "extractive";
  embedder: string;
  notes: string[];
  domain: { key: string; title: string; blurb: string; scenarios: Scenario[] };
  voice: { stt: SttState; tts: boolean };
}
export interface StatusMsg { t: "status"; state: "loading" | "ready"; message: string }
export interface CacheEntry { id: string; tag: LampTag; hits: number; ttl: number }
export interface DraftInfo { question: string; answer: string; uses: number; age_s: number; chunk_ids: string[] }
export interface CacheMsg { t: "cache"; entries: CacheEntry[]; drafts: DraftInfo[] }
export interface TurnStartMsg { t: "turn_start"; q: string; via: TurnVia }
export interface TokenMsg { t: "token"; s: string }
export interface GoldResult { doc_ok: boolean | null; answer_ok: boolean | null; doc: string | null }
export interface TurnStats { turns: number; hits: number; drafts: number; corrected: number; avg_user_ms: number }
export interface TurnMsg {
  t: "turn";
  q: string;
  answer: string;
  source: TurnSource;
  hit: boolean;
  verified: boolean | null;
  corrected: boolean;
  embed_ms: number;
  retrieval_ms: number;
  llm_ms: number | null;
  user_ms: number;
  chunk_ids: string[];
  tags: string[];
  draft_sim: number | null;
  store_failed: boolean;
  gold: GoldResult | null;
  stats: TurnStats;
}
export type SlowMsg =
  | { t: "slow"; kind: "utterance"; text: string }
  | { t: "slow"; kind: "prefetch"; source: LampTag; query: string; added: string[]; returned: string[] }
  | { t: "slow"; kind: "predicted"; predictions: { topic: string; question: string | null }[] }
  | { t: "slow"; kind: "drafted"; question: string; answer: string; chunk_ids: string[] }
  | { t: "slow"; kind: "cancelled"; text: string }
  | { t: "slow"; kind: "corrected"; question: string; chunk_ids: string[] };
export interface TranscriptMsg { t: "transcript"; text: string }
export interface AudioOutMsg { t: "audio_out"; seq: number; sentence: string; data: string }
export interface AutoplayMsg { t: "autoplay"; state: "start" | "done" | "stopped"; scenario: string }
export interface ErrorMsg { t: "error"; message: string }

export type ServerMessage =
  | ReadyMsg | StatusMsg | CacheMsg | TurnStartMsg | TokenMsg | TurnMsg | SlowMsg
  | TranscriptMsg | AudioOutMsg | AutoplayMsg | ErrorMsg;

export type ClientMessage =
  | { t: "hello"; settings: Partial<Settings> }
  | { t: "say"; text: string }
  | { t: "partial"; text: string }
  | { t: "audio"; data: string; mime: string }
  | { t: "autoplay"; scenario: string }
  | { t: "stop" };

/* ---------------------------------------------------------------- REST */
export interface ProfileInfo { key: string; label: string; cache: boolean; strategy: string; verify: boolean; drafts: boolean }
export interface DomainInfo { key: string; title: string; blurb: string }
export interface Info { has_key: boolean; stt: SttState; domains: DomainInfo[]; profiles: ProfileInfo[] }

export interface ProfileSummary {
  n: number; errors: number;
  hit_rate: number | null; warm_hit_rate: number | null; draft_rate: number | null;
  accuracy: number | null; evidence: number | null; fidelity: number | null;
  embed_ms: number | null; retrieval_ms: number | null; hit_retrieval_ms: number | null; llm_ms: number | null;
  user_p50: number | null; user_p90: number | null;
}
export interface ExperimentResult {
  id?: string;
  domain: string;
  env: string;
  notes: string[];
  generated?: string;
  profiles: Record<string, { label: string; summary: ProfileSummary }>;
  sweep: { tau: number; summary: ProfileSummary }[];
}
export interface ExperimentSpec {
  domain: string;
  profiles: string[];
  embedder: EmbedderChoice;
  llm: "extractive" | "openai";
  sweep: string;
  distractors: number;
  confirm?: boolean;
}
export interface RunningExperiment {
  id: string;
  state: "running" | "done" | "error";
  progress: string[];
  error?: string;
  result?: ExperimentResult;
}
