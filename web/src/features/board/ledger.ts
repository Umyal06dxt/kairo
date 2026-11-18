import type { LampTag, SlowMsg } from "@/api/types";
import { truncate } from "@/lib/format";

export type LedgerKind = LampTag | "draft" | "turn" | "corrected";
export interface LedgerText { kind: LedgerKind; text: string; sub?: string; items?: string[] }

const quote = (s: string): string => `“${truncate(s, 60)}”`;

/** Plain-language narration of what the background agent just did. */
export function describeSlow(m: SlowMsg): LedgerText {
  switch (m.kind) {
    case "utterance":
      return { kind: "direct", text: `Heard ${quote(m.text)}` };
    case "prefetch": {
      const label: Record<LampTag, string> = {
        direct: `Looked up ${quote(m.query)}`,
        predicted: "Loaded pages for a prediction",
        neighbor: "Loaded pages near one it just found",
        partial: `Heard while you typed: ${quote(m.query)}`,
        miss: `Memory missed. Fetched ${quote(m.query)}`,
      };
      const forWhat = m.source === "predicted" ? ` · for ${quote(m.query)}` : "";
      return {
        kind: m.source,
        text: label[m.source] ?? "Loaded pages",
        sub: `${m.returned.length} pages checked, ${m.added.length} new in memory${forWhat}`,
      };
    }
    case "predicted":
      return {
        kind: "predicted",
        text: "Expecting you to ask next",
        items: m.predictions.map((p) => p.question ?? p.topic),
      };
    case "drafted":
      return { kind: "draft", text: `Wrote an answer in advance for ${quote(m.question)}`, sub: m.answer };
    case "cancelled":
      return { kind: "miss", text: "Dropped a plan", sub: "You moved on before it finished." };
    case "corrected":
      return { kind: "corrected", text: "Memory was wrong", sub: "Fetched the right pages and answered again before speaking." };
  }
}
