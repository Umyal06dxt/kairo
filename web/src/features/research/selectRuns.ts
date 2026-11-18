import type { ExperimentResult, ProfileSummary } from "@/api/types";

export interface RunSelection {
  /** Live (GPT) run that includes the plain-RAG baseline. */
  liveBase: ExperimentResult | undefined;
  /** Newest live run that includes the optimized strategy (it may be a tuning variant). */
  liveOpt: ExperimentResult | undefined;
  /** Offline run with baseline + reactive, for the hit-quality comparison. */
  off: ExperimentResult | undefined;
}

const isLive = (r: ExperimentResult) => /llm=openai/.test(r.env);
const isOffline = (r: ExperimentResult) => /llm=extractive/.test(r.env);

/** `saved` is newest first. Each claim on the Research page cites the run that can support it. */
export function selectRuns(saved: ExperimentResult[]): RunSelection {
  return {
    liveBase: saved.find((r) => isLive(r) && r.profiles.baseline),
    liveOpt: saved.find((r) => isLive(r) && r.profiles.optimized),
    off: saved.find((r) => isOffline(r) && r.profiles.reactive && r.profiles.baseline),
  };
}

export const summaryOf = (r: ExperimentResult | undefined, key: string): ProfileSummary | null =>
  r?.profiles[key]?.summary ?? null;
