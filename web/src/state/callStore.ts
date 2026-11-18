import { create } from "zustand";
import type {
  CacheEntry, DraftInfo, ReadyMsg, ServerMessage, TurnMsg, TurnVia,
} from "@/api/types";
import type { ConnectionState } from "@/api/callSocket";
import { describeSlow, type LedgerKind } from "@/features/board/ledger";

export interface VoiceNote { url: string; durationMs: number }
export interface Turn {
  id: number;
  question: string;
  via: TurnVia;
  answer: string;
  pending: boolean;
  result: TurnMsg | null;
  voice: VoiceNote | null;
  at: number;
}
export interface LedgerItem {
  id: number; at: number; kind: LedgerKind; text: string; sub?: string; items?: string[];
}

export interface CallState {
  connection: ConnectionState;
  status: string;
  ready: ReadyMsg | null;
  turns: Turn[];
  ledger: LedgerItem[];
  cache: Record<string, CacheEntry>;
  drafts: DraftInfo[];
  notices: string[];
  autoplay: { active: boolean; scenario: string | null };
  startedAt: number | null;
  pulse: { ids: string[]; nonce: number };
  noSpeech: boolean;
  pendingVoice: VoiceNote | null;
  nextId: number;
}

export const initialCallState: CallState = {
  connection: "closed", status: "", ready: null, turns: [], ledger: [], cache: {}, drafts: [],
  notices: [], autoplay: { active: false, scenario: null }, startedAt: null,
  pulse: { ids: [], nonce: 0 }, noSpeech: false, pendingVoice: null, nextId: 1,
};

const MAX_LEDGER = 120;

/** Pure: server message -> state patch. All timing is injected so it is deterministic in tests. */
export function reduce(s: CallState, m: ServerMessage, now: number): Partial<CallState> {
  switch (m.t) {
    case "ready":
      return {
        ...initialCallState, connection: s.connection, ready: m, notices: [...m.notes],
        nextId: s.nextId, pendingVoice: null,
      };
    case "status":
      return { status: m.state === "loading" ? m.message : "" };
    case "cache": {
      const cache: Record<string, CacheEntry> = {};
      for (const e of m.entries) cache[e.id] = e;
      return { cache, drafts: m.drafts };
    }
    case "turn_start": {
      const turn: Turn = {
        id: s.nextId, question: m.q, via: m.via, answer: "", pending: true, result: null,
        voice: m.via === "voice" ? s.pendingVoice : null, at: now,
      };
      return {
        turns: [...s.turns, turn], nextId: s.nextId + 1, startedAt: s.startedAt ?? now,
        pendingVoice: m.via === "voice" ? null : s.pendingVoice, noSpeech: false,
      };
    }
    case "token": {
      const i = lastPending(s.turns);
      if (i < 0) return {};
      return { turns: patchTurn(s.turns, i, (t) => ({ ...t, answer: t.answer + m.s })) };
    }
    case "turn": {
      const i = lastPending(s.turns);
      const turns = i < 0 ? s.turns : patchTurn(s.turns, i, (t) => ({
        ...t, answer: m.answer || t.answer, pending: false, result: m,
      }));
      const verb = m.source === "draft" ? "from a pre-drafted answer" : m.hit ? "from memory"
        : m.corrected ? "memory was wrong, corrected" : "from the database";
      return {
        turns,
        pulse: { ids: m.chunk_ids, nonce: s.pulse.nonce + 1 },
        ...pushLedger(s, now, { kind: "turn", text: `Answered in ${Math.round(m.user_ms)} ms`, sub: verb }),
      };
    }
    case "slow":
      return pushLedger(s, now, describeSlow(m));
    case "transcript":
      return { noSpeech: m.text.trim() === "" };
    case "autoplay":
      return { autoplay: { active: m.state === "start", scenario: m.state === "start" ? m.scenario : null } };
    case "error": {
      const i = lastPending(s.turns);
      return {
        notices: [...s.notices, m.message],
        turns: i < 0 ? s.turns : patchTurn(s.turns, i, (t) => ({ ...t, pending: false })),
      };
    }
    case "audio_out":
      return {}; // playback is a side effect handled by the session, not state
  }
}

function lastPending(turns: Turn[]): number {
  for (let i = turns.length - 1; i >= 0; i--) if (turns[i]!.pending) return i;
  return -1;
}
function patchTurn(turns: Turn[], i: number, f: (t: Turn) => Turn): Turn[] {
  return turns.map((t, j) => (j === i ? f(t) : t));
}
function pushLedger(s: CallState, now: number, d: { kind: LedgerKind; text: string; sub?: string; items?: string[] }) {
  const base = s.startedAt ?? now;
  const item: LedgerItem = { id: s.nextId, at: now - base, ...d };
  return { ledger: [item, ...s.ledger].slice(0, MAX_LEDGER), nextId: s.nextId + 1 };
}

interface CallActions {
  apply: (m: ServerMessage) => void;
  setConnection: (c: ConnectionState) => void;
  reset: () => void;
  attachVoice: (v: VoiceNote) => void;
  dismissNotice: (i: number) => void;
}

export const useCallStore = create<CallState & CallActions>((set, get) => ({
  ...initialCallState,
  apply: (m) => set(reduce(get(), m, Date.now())),
  setConnection: (connection) => set({ connection }),
  reset: () => set({ ...initialCallState, connection: get().connection, nextId: get().nextId }),
  attachVoice: (pendingVoice) => set({ pendingVoice }),
  dismissNotice: (i) => set({ notices: get().notices.filter((_, j) => j !== i) }),
}));
