import type { ProfileInfo } from "@/api/types";

const STRATEGY: Record<string, string> = {
  none: "No prediction",
  llm: "GPT predicts the next topics",
  neighbors: "Prefetches nearby pages (no GPT)",
  hybrid: "GPT plus nearby pages",
};

/** One plain-language line for a strategy, shared by the settings sheet and the experiment form. */
export function describeProfile(p: ProfileInfo): string {
  if (!p.cache) return "Every question goes to the database. The comparison point.";
  const bits = [STRATEGY[p.strategy] ?? p.strategy];
  if (p.drafts) bits.push("pre-drafts answers");
  if (p.verify) bits.push("verifies hits");
  return `${bits.join(", ")}.`;
}
