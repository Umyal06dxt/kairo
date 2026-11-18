import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "@/components/Icon";
import styles from "./Composer.module.css";

interface Props {
  onSend: (text: string) => void;
  /** Called (debounced) while typing so the background agent can start looking early. */
  onPartial?: (text: string) => void;
  placeholder?: string;
  partialDelayMs?: number;
  minPartialChars?: number;
}

export function Composer({ onSend, onPartial, placeholder = "Ask a question…", partialDelayMs = 300, minPartialChars = 12 }: Props) {
  const [text, setText] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const change = (v: string) => {
    setText(v);
    if (timer.current) clearTimeout(timer.current);
    const t = v.trim();
    if (onPartial && t.length >= minPartialChars) timer.current = setTimeout(() => onPartial(t), partialDelayMs);
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    if (!t) return;
    if (timer.current) clearTimeout(timer.current); // the final question supersedes any pending partial
    onSend(t);
    setText("");
  };

  return (
    <form className={styles.form} onSubmit={submit} autoComplete="off">
      <label className="sr-only" htmlFor="composer-input">Your question</label>
      <input id="composer-input" className={styles.input} value={text} maxLength={300}
        placeholder={placeholder} onChange={(e) => change(e.target.value)} />
      <button type="submit" className={styles.send} aria-label="Send" disabled={!text.trim()}><Icon name="send" size={20} /></button>
    </form>
  );
}
