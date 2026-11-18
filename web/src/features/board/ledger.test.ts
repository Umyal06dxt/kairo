import { describeSlow } from "./ledger";

describe("describeSlow", () => {
  it("narrates a direct lookup", () => {
    const d = describeSlow({ t: "slow", kind: "prefetch", source: "direct", query: "overdraft fee", added: ["a"], returned: ["a", "b", "c"] });
    expect(d.kind).toBe("direct");
    expect(d.text).toBe("Looked up “overdraft fee”");
    expect(d.sub).toBe("3 pages checked, 1 new in memory");
  });
  it("says what a predicted prefetch was for", () => {
    const d = describeSlow({ t: "slow", kind: "prefetch", source: "predicted", query: "annual discount", added: [], returned: ["x"] });
    expect(d.text).toBe("Loaded pages for a prediction");
    expect(d.sub).toContain("for “annual discount”");
  });
  it("lists predicted questions, preferring the question over the topic", () => {
    const d = describeSlow({ t: "slow", kind: "predicted", predictions: [{ topic: "t1", question: "Q1?" }, { topic: "t2", question: null }] });
    expect(d.items).toEqual(["Q1?", "t2"]);
  });
  it("covers drafts, cancellation and correction", () => {
    expect(describeSlow({ t: "slow", kind: "drafted", question: "q", answer: "a", chunk_ids: [] }).kind).toBe("draft");
    expect(describeSlow({ t: "slow", kind: "cancelled", text: "q" }).text).toBe("Dropped a plan");
    expect(describeSlow({ t: "slow", kind: "corrected", question: "q", chunk_ids: [] }).kind).toBe("corrected");
  });
  it("truncates very long quoted text", () => {
    expect(describeSlow({ t: "slow", kind: "utterance", text: "x".repeat(100) }).text.length).toBeLessThan(80);
  });
});
