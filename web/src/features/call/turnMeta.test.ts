import type { TurnMsg } from "@/api/types";
import { describeTurn, routeSegments } from "./turnMeta";

const base: TurnMsg = {
  t: "turn", q: "q", answer: "a", source: "store", hit: false, verified: null, corrected: false,
  embed_ms: 5, retrieval_ms: 100, llm_ms: 900, user_ms: 1005, chunk_ids: [], tags: [], draft_sim: null,
  store_failed: false, gold: null, stats: { turns: 1, hits: 0, drafts: 0, corrected: 0, avg_user_ms: 1005 },
};

describe("describeTurn", () => {
  it("distinguishes every way an answer can be produced", () => {
    expect(describeTurn({ ...base, source: "draft", hit: true }, true).kind).toBe("draft");
    const hit = describeTurn({ ...base, source: "cache", hit: true, verified: true }, true);
    expect(hit.kind).toBe("hit");
    expect(hit.why).toMatch(/agreed/);
    expect(describeTurn({ ...base, source: "cache", hit: true }, true).why).toMatch(/without checking/);
    expect(describeTurn({ ...base, corrected: true }, true).title).toMatch(/wrong/);
    expect(describeTurn({ ...base, store_failed: true }, true).title).toMatch(/unavailable/);
    expect(describeTurn(base, true).title).toBe("Looked it up in the database");
  });
  it("explains that the baseline mode has no memory", () => {
    expect(describeTurn({ ...base, hit: true }, false).why).toBe("This mode has no memory.");
  });
  it("lets a store failure win over a stale hit flag", () => {
    expect(describeTurn({ ...base, hit: true, store_failed: true }, true).kind).toBe("miss");
  });
});

describe("routeSegments", () => {
  it("returns fractions that sum to one", () => {
    const s = routeSegments(base);
    expect(s.embed + s.lookup + s.model).toBeCloseTo(1, 5);
    expect(s.model).toBeGreaterThan(0.8);
  });
  it("handles a pre-drafted answer with no model wait", () => {
    const s = routeSegments({ embed_ms: 5, retrieval_ms: 1, llm_ms: null });
    expect(s.model).toBe(0);
  });
  it("never divides by zero", () => {
    expect(routeSegments({ embed_ms: 0, retrieval_ms: 0, llm_ms: null })).toEqual({ embed: 0, lookup: 0, model: 0 });
  });
});
