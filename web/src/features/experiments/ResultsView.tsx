import type { ExperimentResult, ProfileSummary } from "@/api/types";
import { bestIndex, fmtMs, fmtPct } from "@/lib/format";
import { SweepChart, WaitChart, type ProfileRow } from "./charts";
import styles from "./ResultsView.module.css";

type Col = { title: string; key: keyof ProfileSummary; higher: boolean; rate: boolean };
export const COLUMNS: Col[] = [
  { title: "Hit rate", key: "hit_rate", higher: true, rate: true },
  { title: "Right page", key: "evidence", higher: true, rate: true },
  { title: "Answer correct", key: "accuracy", higher: true, rate: true },
  { title: "Hit fidelity", key: "fidelity", higher: true, rate: true },
  { title: "Wait p50", key: "user_p50", higher: false, rate: false },
  { title: "Wait p90", key: "user_p90", higher: false, rate: false },
  { title: "First word", key: "llm_ms", higher: false, rate: false },
];

export function ResultsView({ result }: { result: ExperimentResult }) {
  const rows: ProfileRow[] = Object.entries(result.profiles).map(([key, p]) => ({ key, label: p.label, s: p.summary }));
  const best = COLUMNS.map((c) => bestIndex(rows.map((r) => r.s[c.key] as number | null), c.higher, c.rate));
  const show = (c: Col, v: number | null) => (c.rate ? fmtPct(v) : fmtMs(v));

  return (
    <div className={styles.wrap}>
      <p className={styles.note}>{result.env}. {result.generated}</p>
      {result.notes?.map((n) => <p key={n} className={styles.note}>{n}</p>)}

      <h3>Results</h3>
      <div className={styles.tbl}>
        <table>
          <thead>
            <tr><th>Strategy</th>{COLUMNS.map((c) => <th key={c.title}>{c.title}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.key}>
                <td>{r.label}</td>
                {COLUMNS.map((c, ci) => (
                  <td key={c.title} className={best[ci] === i ? styles.best : ""}>{show(c, r.s[c.key] as number | null)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className={styles.note}>
        Bold green marks a clear winner (4+ points, or 8%+ faster); smaller gaps are within the noise of a single run.
        Wait is the time before the first word: understanding the question, looking up pages, and the model's first token.
        “Right page” is how often the page holding the answer was among those used. Fidelity is how often a memory hit served
        the same pages the database would have.
      </p>

      <h3>How long the caller waits (median and slowest 10%)</h3>
      <WaitChart rows={rows} />

      {result.sweep.length > 0 && (
        <>
          <h3>Memory strictness: more hits or better hits?</h3>
          <SweepChart points={result.sweep} />
        </>
      )}
    </div>
  );
}
