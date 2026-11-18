/** Display formatting shared across features. All functions are pure. */

export const fmtMs = (v: number | null | undefined): string => {
  if (v == null || Number.isNaN(v)) return "–";
  if (v >= 100) return `${Math.round(v).toLocaleString("en-US")} ms`;
  if (v >= 10) return `${v.toFixed(0)} ms`;
  return `${v.toFixed(1)} ms`;
};

export const fmtPct = (v: number | null | undefined): string =>
  v == null || Number.isNaN(v) ? "–" : `${Math.round(v * 100)}%`;

export function clock(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function clockTime(date: Date): string {
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export const truncate = (s: string, n: number): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Index of a clear winner, or -1. One run of ~100 turns can't resolve small gaps, so a winner
 *  must lead the runner-up by 4+ points (rates) or 8%+ (times). */
export function bestIndex(vals: (number | null)[], higherIsBetter: boolean, isRate: boolean): number {
  const ok = vals.map((v, i) => [v, i] as const).filter((p): p is readonly [number, number] => p[0] != null);
  if (ok.length < 2) return -1;
  const sorted = [...ok].sort((a, b) => (higherIsBetter ? b[0] - a[0] : a[0] - b[0]));
  const [first, second] = [sorted[0]!, sorted[1]!];
  const gap = Math.abs(first[0] - second[0]);
  const scale = Math.max(Math.abs(second[0]), 1e-9);
  return (isRate ? gap >= 0.04 : gap / scale >= 0.08) ? first[1] : -1;
}
