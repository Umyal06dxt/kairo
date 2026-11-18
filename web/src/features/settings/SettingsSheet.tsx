import { useEffect, useState, type FormEvent } from "react";
import { getSession } from "@/api/session";
import type { EmbedderChoice, LlmChoice, Settings } from "@/api/types";
import { Sheet } from "@/components/Sheet";
import { useInfoStore } from "@/state/infoStore";
import { useSettingsStore } from "@/state/settingsStore";
import { describeProfile } from "./profileBlurb";
import styles from "./SettingsSheet.module.css";

export function SettingsSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Sheet open={open} title="Call settings" onClose={onClose}>
      <SettingsForm onClose={onClose} />
    </Sheet>
  );
}

/** Mounted only while the sheet is open, so every opening starts from the saved settings. */
function SettingsForm({ onClose }: { onClose: () => void }) {
  const info = useInfoStore((s) => s.info);
  const load = useInfoStore((s) => s.load);
  const saved = useSettingsStore((s) => s.settings);
  const replace = useSettingsStore((s) => s.replace);
  const [draft, setDraft] = useState<Settings>(saved);
  const [useDefaultTau, setUseDefaultTau] = useState(saved.tau == null);

  useEffect(() => { void load(); }, [load]);

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setDraft((d) => ({ ...d, [k]: v }));
  const apply = (e: FormEvent) => {
    e.preventDefault();
    replace({ ...draft, tau: useDefaultTau ? null : draft.tau ?? 0.6 });
    getSession().hello(); // a new call with the new settings
    onClose();
  };

  return (
    <>
      <p className={styles.sub}>Changing these starts a new call.</p>
      <form className={styles.form} onSubmit={apply}>
        <label className={styles.field}><span>Knowledge base</span>
          <select value={draft.domain} onChange={(e) => set("domain", e.target.value)}>
            {(info?.domains ?? [{ key: draft.domain, title: draft.domain, blurb: "" }]).map((d) => <option key={d.key} value={d.key}>{d.title}</option>)}
          </select></label>

        <fieldset className={styles.field}>
          <legend>Strategy</legend>
          {(info?.profiles ?? []).map((p) => (
            <label key={p.key} className={styles.profile}>
              <input type="radio" name="profile" checked={draft.profile === p.key} onChange={() => set("profile", p.key)} />
              <b>{p.label}</b><small>{describeProfile(p)}</small>
            </label>
          ))}
        </fieldset>

        <div className={styles.two}>
          <label className={styles.field}><span>Embeddings</span>
            <select value={draft.embedder} onChange={(e) => set("embedder", e.target.value as EmbedderChoice)}>
              <option value="local">On-device (5 ms)</option><option value="openai">OpenAI (700 ms)</option><option value="hash">Toy hashing</option>
            </select></label>
          <label className={styles.field}><span>Answers</span>
            <select value={draft.llm} onChange={(e) => set("llm", e.target.value as LlmChoice)}>
              <option value="auto">Auto (GPT if a key is set)</option><option value="openai">GPT</option><option value="extractive">Offline stand-in</option>
            </select></label>
        </div>

        <label className={styles.field}>
          <span>Memory strictness <output>{useDefaultTau ? "default" : (draft.tau ?? 0.6).toFixed(2)}</output></span>
          <input type="range" min={0.3} max={0.85} step={0.01} value={draft.tau ?? 0.6} disabled={useDefaultTau}
            aria-label="Memory strictness" onChange={(e) => set("tau", Number(e.target.value))} />
          <small>How similar a remembered page must be to count as a hit. Higher is stricter.</small>
        </label>
        <label className={styles.check}>
          <input type="checkbox" checked={useDefaultTau} onChange={(e) => setUseDefaultTau(e.target.checked)} /> Use the right default for these embeddings
        </label>

        <label className={styles.field}>
          <span>Database delay <output>{draft.store_latency_ms} ms</output></span>
          <input type="range" min={0} max={500} step={10} value={draft.store_latency_ms} aria-label="Database delay"
            onChange={(e) => set("store_latency_ms", Number(e.target.value))} />
          <small>Simulated round trip to a remote vector database.</small>
        </label>

        <label className={styles.check}><input type="checkbox" checked={draft.distractors} onChange={(e) => set("distractors", e.target.checked)} /> Add 64 pages of background (credit union only)</label>
        <label className={styles.check}><input type="checkbox" checked={draft.speak} onChange={(e) => set("speak", e.target.checked)} /> Speak answers aloud</label>

        <div className={styles.actions}>
          <button type="button" className={styles.cancel} onClick={onClose}>Cancel</button>
          <button type="submit" className={styles.go}>Start new call</button>
        </div>
      </form>
    </>
  );
}
