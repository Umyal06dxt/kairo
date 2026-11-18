import type { ProfileSummary } from "@/api/types";
import { fmtMs } from "@/lib/format";
import styles from "./ResultsView.module.css";

export interface ProfileRow { key: string; label: string; s: ProfileSummary }

/** Median and slowest-10% wait per strategy, as horizontal bars. */
export function WaitChart({ rows }: { rows: ProfileRow[] }) {
  const W = 720, rowH = 46, left = 230, H = rows.length * rowH + 20;
  const max = Math.max(...rows.map((r) => r.s.user_p90 ?? 0), 1);
  const scale = (v: number | null) => ((v ?? 0) / max) * (W - left - 80);
  return (
    <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Wait before the first word, per strategy">
      {rows.map((r, i) => {
        const y = i * rowH + 8;
        const w50 = scale(r.s.user_p50), w90 = scale(r.s.user_p90);
        return (
          <g key={r.key}>
            <text x={0} y={y + 14}>{r.label}</text>
            <rect x={left} y={y} width={Math.max(2, w90)} height={14} rx={4} fill="rgba(14,14,16,.1)" />
            <rect x={left} y={y} width={Math.max(2, w50)} height={14} rx={4} fill="var(--purple)" />
            <text x={left + Math.max(w50, w90) + 8} y={y + 12}>{fmtMs(r.s.user_p50)}</text>
            <text className={styles.muted} x={left} y={y + 32}>slowest 10%: {fmtMs(r.s.user_p90)}</text>
          </g>
        );
      })}
    </svg>
  );
}

export interface SweepPoint { tau: number; summary: ProfileSummary }
const SERIES: { key: "hit_rate" | "evidence" | "fidelity"; name: string; color: string }[] = [
  { key: "hit_rate", name: "Hit rate", color: "var(--orange)" },
  { key: "evidence", name: "Right page", color: "var(--purple)" },
  { key: "fidelity", name: "Fidelity", color: "var(--pink)" },
];

/** Hit rate, right-page rate and fidelity as the memory threshold tightens. */
export function SweepChart({ points }: { points: SweepPoint[] }) {
  const pts = [...points].sort((a, b) => a.tau - b.tau);
  if (pts.length < 2) return null;
  const W = 720, H = 260, L = 44, B = 36, T = 14, R = 110;
  const span = Math.max(0.01, pts[pts.length - 1]!.tau - pts[0]!.tau);
  const x = (t: number) => L + ((t - pts[0]!.tau) / span) * (W - L - R);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  return (
    <svg className={styles.chart} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Hit rate, right page and fidelity against the threshold">
      {[0, 0.25, 0.5, 0.75, 1].map((g) => (
        <g key={g}>
          <line className={styles.grid} x1={L} x2={W - R} y1={y(g)} y2={y(g)} />
          <text className={styles.muted} x={4} y={y(g) + 4}>{Math.round(g * 100)}%</text>
        </g>
      ))}
      {pts.map((p) => <text key={p.tau} className={styles.muted} x={x(p.tau) - 12} y={H - 14}>{p.tau.toFixed(2)}</text>)}
      {SERIES.map(({ key, name, color }) => {
        const line = pts.filter((p) => p.summary[key] != null);
        const last = line[line.length - 1];
        return (
          <g key={key}>
            <polyline fill="none" stroke={color} strokeWidth={2.5} points={line.map((p) => `${x(p.tau)},${y(p.summary[key]!)}`).join(" ")} />
            {line.map((p) => <circle key={p.tau} cx={x(p.tau)} cy={y(p.summary[key]!)} r={3.5} fill={color} />)}
            {last && <text x={W - R + 8} y={y(last.summary[key]!) + 4}>{name}</text>}
          </g>
        );
      })}
    </svg>
  );
}
