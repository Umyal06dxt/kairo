import { useEffect, useMemo, useState } from "react";
import { useInfoStore } from "@/state/infoStore";
import { ResultsView } from "./ResultsView";
import { RunForm } from "./RunForm";
import { useExperiments } from "./useExperiments";
import styles from "./ExperimentsPage.module.css";

export function ExperimentsPage() {
  const info = useInfoStore((s) => s.info);
  const load = useInfoStore((s) => s.load);
  const ex = useExperiments();
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => { void load(); }, [load]);

  const current = useMemo(
    () => ex.saved.find((r) => r.id === selected) ?? ex.saved[0] ?? null,
    [ex.saved, selected],
  );

  return (
    <div className={styles.grid}>
      <RunForm profiles={info?.profiles ?? []} running={ex.running} message={ex.message} busy={ex.busy} onRun={ex.run} />
      <div className={styles.out}>
        {ex.saved.length > 0 && (
          <div className={styles.saved}>
            <label htmlFor="saved-run">Results</label>
            <select id="saved-run" value={current?.id ?? ""} onChange={(e) => setSelected(e.target.value)}>
              {ex.saved.map((r) => <option key={r.id} value={r.id}>{r.generated ?? r.id} · {r.domain} · {r.env}</option>)}
            </select>
          </div>
        )}
        {current ? <ResultsView result={current} /> : (
          <p className={styles.empty}>No runs yet. Pick strategies on the left and run an experiment, or open a saved run here.</p>
        )}
      </div>
    </div>
  );
}
