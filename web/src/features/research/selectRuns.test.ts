import type { ExperimentResult, ProfileSummary } from "@/api/types";
import { selectRuns, summaryOf } from "./selectRuns";

const S = {} as ProfileSummary;
const run = (id: string, env: string, keys: string[]): ExperimentResult => ({
  id, domain: "bank", env, notes: [], sweep: [],
  profiles: Object.fromEntries(keys.map((k) => [k, { label: k, summary: S }])),
});

describe("selectRuns", () => {
  const saved = [
    run("live-opt", "embedder=local, llm=openai", ["optimized"]),                       // newest: tuning variant, no baseline
    run("live-full", "embedder=local, llm=openai", ["baseline", "paper", "optimized"]),
    run("off", "embedder=local, llm=extractive", ["baseline", "reactive", "neighbors"]),
    run("off-partial", "embedder=local, llm=extractive", ["baseline"]),
  ];
  it("cites a different run for each claim", () => {
    const s = selectRuns(saved);
    expect(s.liveOpt?.id).toBe("live-opt");     // newest with optimized
    expect(s.liveBase?.id).toBe("live-full");   // only one with the plain-RAG comparison
    expect(s.off?.id).toBe("off");              // needs baseline AND reactive
  });
  it("returns undefined for claims no saved run can support", () => {
    expect(selectRuns([])).toEqual({ liveBase: undefined, liveOpt: undefined, off: undefined });
    expect(selectRuns([saved[2]!]).liveBase).toBeUndefined();
  });
  it("looks up a profile's summary safely", () => {
    expect(summaryOf(saved[1], "paper")).toBe(S);
    expect(summaryOf(saved[1], "nope")).toBeNull();
    expect(summaryOf(undefined, "paper")).toBeNull();
  });
});
