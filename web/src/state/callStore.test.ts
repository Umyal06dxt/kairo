import type { CacheMsg, ReadyMsg, ServerMessage, TurnMsg } from "@/api/types";
import { initialCallState, reduce, type CallState } from "./callStore";

const apply = (s: CallState, m: ServerMessage, now = 1000): CallState => ({ ...s, ...reduce(s, m, now) });

const ready = {
  t: "ready", board: { docs: [], n_chunks: 0, n_extra: 0 },
  settings: {}, profile: { key: "optimized", label: "Kairo", cache: true },
  config: { strategy: "hybrid", verify: true, drafts: true, tau: 0.6, context: 6, rerank: true },
  llm: "openai", embedder: "local", notes: ["be careful"],
  domain: { key: "bank", title: "Bank", blurb: "", scenarios: [] }, voice: { stt: "ready", tts: true },
} as unknown as ReadyMsg;

const turn = (over: Partial<TurnMsg> = {}): TurnMsg => ({
  t: "turn", q: "q", answer: "final", source: "cache", hit: true, verified: true, corrected: false,
  embed_ms: 5, retrieval_ms: 0.2, llm_ms: 900, user_ms: 905, chunk_ids: ["a", "b"], tags: ["direct", "predicted"],
  draft_sim: null, store_failed: false, gold: null,
  stats: { turns: 1, hits: 1, drafts: 0, corrected: 0, avg_user_ms: 905 }, ...over,
});

describe("call reducer", () => {
  it("ready resets the call but keeps the connection and server notes", () => {
    let s: CallState = { ...initialCallState, connection: "open", turns: [{ id: 1 } as never], nextId: 9 };
    s = apply(s, ready);
    expect(s.turns).toEqual([]);
    expect(s.connection).toBe("open");
    expect(s.notices).toEqual(["be careful"]);
    expect(s.nextId).toBe(9);
  });

  it("streams tokens into the pending turn, then finalises it with the authoritative answer", () => {
    let s = apply(initialCallState, { t: "turn_start", q: "fee?", via: "text" }, 5000);
    s = apply(s, { t: "token", s: "Hel" }); s = apply(s, { t: "token", s: "lo" });
    expect(s.turns[0]).toMatchObject({ answer: "Hello", pending: true });
    s = apply(s, turn({ answer: "Hello there." }), 7000);
    expect(s.turns[0]).toMatchObject({ answer: "Hello there.", pending: false });
    expect(s.turns[0]!.result?.source).toBe("cache");
    expect(s.pulse.ids).toEqual(["a", "b"]);
    expect(s.pulse.nonce).toBe(1);
    expect(s.ledger[0]).toMatchObject({ kind: "turn", text: "Answered in 905 ms", sub: "from memory", at: 2000 });
  });

  it("ignores stray tokens when no turn is pending", () => {
    expect(reduce(initialCallState, { t: "token", s: "x" }, 0)).toEqual({});
  });

  it("builds the cache map and draft list from a cache message", () => {
    const m: CacheMsg = { t: "cache", entries: [{ id: "a", tag: "predicted", hits: 2, ttl: 100 }], drafts: [] };
    const s = apply(initialCallState, m);
    expect(s.cache.a).toMatchObject({ tag: "predicted", hits: 2 });
    expect(apply(s, { ...m, entries: [] }).cache).toEqual({}); // evicted entries disappear
  });

  it("attaches a recorded voice note only to a voice turn", () => {
    const note = { url: "blob:1", durationMs: 1500 };
    let s: CallState = { ...initialCallState, pendingVoice: note };
    s = apply(s, { t: "turn_start", q: "typed", via: "text" });
    expect(s.turns[0]!.voice).toBeNull();
    expect(s.pendingVoice).toBe(note); // still waiting for its voice turn
    s = apply(s, { t: "turn_start", q: "spoken", via: "voice" });
    expect(s.turns[1]!.voice).toBe(note);
    expect(s.pendingVoice).toBeNull();
  });

  it("flags an empty transcript and clears the flag on the next turn", () => {
    let s = apply(initialCallState, { t: "transcript", text: "  " });
    expect(s.noSpeech).toBe(true);
    s = apply(s, { t: "turn_start", q: "x", via: "voice" });
    expect(s.noSpeech).toBe(false);
  });

  it("an error stops the pending spinner and surfaces the message", () => {
    let s = apply(initialCallState, { t: "turn_start", q: "x", via: "text" });
    s = apply(s, { t: "error", message: "boom" });
    expect(s.turns[0]!.pending).toBe(false);
    expect(s.notices).toEqual(["boom"]);
  });

  it("tracks scripted-call state and slow-thinker narration, newest first, capped", () => {
    let s = apply(initialCallState, { t: "autoplay", state: "start", scenario: "B2" });
    expect(s.autoplay).toEqual({ active: true, scenario: "B2" });
    s = apply(s, { t: "autoplay", state: "done", scenario: "B2" });
    expect(s.autoplay.active).toBe(false);
    for (let i = 0; i < 150; i++) s = apply(s, { t: "slow", kind: "cancelled", text: String(i) });
    expect(s.ledger).toHaveLength(120);
    expect(s.ledger[0]!.id).toBeGreaterThan(s.ledger[1]!.id);
  });

  it("does not change state for playback-only messages", () => {
    expect(reduce(initialCallState, { t: "audio_out", seq: 0, sentence: "s", data: "" }, 0)).toEqual({});
  });
});
