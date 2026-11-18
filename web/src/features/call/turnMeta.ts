import type { TurnMsg } from "@/api/types";

export type BadgeKind = "draft" | "hit" | "miss";
export interface TurnBadge { kind: BadgeKind; title: string; why: string }

/** How an answer was produced, in words a caller would understand. */
export function describeTurn(m: TurnMsg, profileHasCache: boolean): TurnBadge {
  if (!profileHasCache) return { kind: "miss", title: "Looked it up in the database", why: "This mode has no memory." };
  if (m.store_failed) return { kind: "miss", title: "Database unavailable", why: "Answered without any pages." };
  if (m.corrected)
    return {
      kind: "miss",
      title: "Memory was wrong, so it looked again",
      why: "The database disagreed with what was remembered; the answer was regenerated before any speech.",
    };
  if (m.source === "draft")
    return {
      kind: "draft",
      title: "Answered from a pre-drafted answer",
      why: "Guessed this question earlier and wrote the answer in advance. No wait for the language model.",
    };
  if (m.hit)
    return {
      kind: "hit",
      title: "Answered from memory",
      why: m.verified ? "Checked against the database in parallel: it agreed." : "Served from memory without checking the database.",
    };
  return { kind: "miss", title: "Looked it up in the database", why: "Nothing useful was in memory yet." };
}

export interface RouteSegments { embed: number; lookup: number; model: number }
/** Fractions (0..1) of the time before the first word spent on each step. */
export function routeSegments(m: Pick<TurnMsg, "embed_ms" | "retrieval_ms" | "llm_ms">): RouteSegments {
  const total = Math.max(1, m.embed_ms + m.retrieval_ms + (m.llm_ms ?? 0));
  return { embed: m.embed_ms / total, lookup: m.retrieval_ms / total, model: (m.llm_ms ?? 0) / total };
}
