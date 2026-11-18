import { useCallStore } from "@/state/callStore";
import { clock } from "@/lib/format";
import { Lamp, type LampKind } from "./Lamp";
import type { LedgerKind } from "./ledger";
import styles from "./LedgerPanel.module.css";

const LAMP_FOR: Record<LedgerKind, LampKind | undefined> = {
  direct: "direct", predicted: "predicted", neighbor: "neighbor", partial: "partial", miss: "miss",
  draft: "draft", corrected: "miss", turn: undefined,
};

export function LedgerPanel() {
  const ledger = useCallStore((s) => s.ledger);
  return (
    <section className={styles.panel} aria-label="Behind the scenes">
      <h2 className={styles.title}>Behind the scenes</h2>
      <p className={styles.sub}>What the background agent is doing, as it happens.</p>
      {ledger.length === 0 ? (
        <p className={styles.empty}>Nothing yet. Ask a question to watch it work.</p>
      ) : (
        <ol className={styles.list}>
          {ledger.map((e) => (
            <li key={e.id} className={styles.item}>
              <time className={styles.time}>{clock(e.at)}</time>
              <Lamp tag={LAMP_FOR[e.kind]} size={10} />
              <div>
                {e.text}
                {e.sub && <small>{e.sub}</small>}
                {e.items && <ul>{e.items.map((x, i) => <li key={i}>{x}</li>)}</ul>}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
