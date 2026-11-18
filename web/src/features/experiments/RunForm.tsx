import { useMemo, useState, type FormEvent } from "react";
import type { EmbedderChoice, ExperimentSpec, ProfileInfo, RunningExperiment } from "@/api/types";
import { describeProfile } from "@/features/settings/profileBlurb";
import styles from "./RunForm.module.css";

interface Props {
  profiles: ProfileInfo[];
  running: RunningExperiment | null;
  message: string;
  busy: boolean;
  onRun: (spec: ExperimentSpec) => void;
  /** Injectable for tests; defaults to the browser's confirm dialog. */
  confirmFn?: (msg: string) => boolean;
}

const DEFAULT_PICK = ["baseline", "paper", "optimized"];

export function RunForm({ profiles, running, message, busy, onRun, confirmFn = (m) => window.confirm(m) }: Props) {
  const [domain, setDomain] = useState("bank");
  const [picked, setPicked] = useState<string[]>(DEFAULT_PICK);
  const [embedder, setEmbedder] = useState<EmbedderChoice>("local");
  const [llm, setLlm] = useState<"extractive" | "openai">("extractive");
  const [sweep, setSweep] = useState("");
  const [distract, setDistract] = useState(true);
  const cached = useMemo(() => profiles.filter((p) => p.cache), [profiles]);

  const toggle = (k: string) => setPicked((p) => (p.includes(k) ? p.filter((x) => x !== k) : [...p, k]));
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const live = llm === "openai" || embedder === "openai";
    if (live && !confirmFn("This run calls the OpenAI API with your key and costs a few cents. Run it?")) return;
    onRun({ domain, profiles: picked, embedder, llm, sweep, distractors: distract && domain === "bank" ? 64 : 0, confirm: live });
  };

  return (
    <form className={styles.form} onSubmit={submit}>
      <h1>Compare strategies</h1>
      <p className={styles.lede}>Replays scripted calls against each strategy and measures how long the caller waits and whether the answer used the right page.</p>

      <fieldset>
        <legend>Knowledge base</legend>
        <label className={styles.row}><input type="radio" name="domain" checked={domain === "bank"} onChange={() => setDomain("bank")} /> Credit union support (100 turns, with gold answers)</label>
        <label className={styles.row}><input type="radio" name="domain" checked={domain === "novacrm"} onChange={() => setDomain("novacrm")} /> NovaCRM, as in the paper (200 turns)</label>
        <label className={styles.row}><input type="checkbox" checked={distract} onChange={(e) => setDistract(e.target.checked)} /> Add 64 pages of background (credit union only)</label>
      </fieldset>

      <fieldset>
        <legend>Strategies to compare</legend>
        {profiles.map((p) => (
          <label key={p.key} className={styles.profile}>
            <input type="checkbox" checked={picked.includes(p.key)} onChange={() => toggle(p.key)} />
            <b>{p.label}</b><small>{describeProfile(p)}</small>
          </label>
        ))}
      </fieldset>

      <fieldset>
        <legend>Engines</legend>
        <label className={styles.row}><span>Embeddings</span>
          <select value={embedder} onChange={(e) => setEmbedder(e.target.value as EmbedderChoice)}>
            <option value="local">On-device (free, 5 ms)</option><option value="openai">OpenAI (about 700 ms)</option><option value="hash">Toy hashing (instant, low quality)</option>
          </select></label>
        <label className={styles.row}><span>Answers</span>
          <select value={llm} onChange={(e) => setLlm(e.target.value as "extractive" | "openai")}>
            <option value="extractive">Offline stand-in (free)</option><option value="openai">GPT (uses your key, a few cents)</option>
          </select></label>
        <label className={styles.row}><span>Threshold sweep</span>
          <select value={sweep} onChange={(e) => setSweep(e.target.value)}>
            <option value="">None</option>{cached.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select></label>
      </fieldset>

      <button type="submit" className={styles.run} disabled={busy || picked.length === 0}>Run experiment</button>
      <p className={styles.msg} role="status">{message}</p>
      {running?.state === "running" && <pre className={styles.progress}>{running.progress.join("\n")}</pre>}
    </form>
  );
}
