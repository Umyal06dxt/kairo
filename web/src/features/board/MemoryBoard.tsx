import { useCallStore } from "@/state/callStore";
import { fmtMs } from "@/lib/format";
import type { ReadyMsg } from "@/api/types";
import { LAMP_WORDS, Lamp, type LampKind } from "./Lamp";
import styles from "./MemoryBoard.module.css";

const STRATEGY_WORDS: Record<string, string> = {
  none: "none", llm: "GPT", neighbors: "nearby pages", hybrid: "GPT + nearby pages",
};

/** One plain-language line describing the active strategy. */
export function describeConfig(r: ReadyMsg): string {
  const engine = r.llm === "openai" ? "GPT" : "the offline stand-in";
  if (!r.profile.cache) return `${r.profile.label}: every question goes to the database. No memory, no prediction. Answers by ${engine}.`;
  const c = r.config;
  return (
    `${r.profile.label}. Prediction: ${STRATEGY_WORDS[c.strategy] ?? c.strategy}` +
    `${c.drafts ? ", pre-drafted answers" : ""}${c.verify ? ", checked against the database" : ""}. ` +
    `Strictness ${c.tau}. Answers by ${engine}; embeddings ${r.embedder}.`
  );
}

const LEGEND: LampKind[] = ["direct", "predicted", "neighbor", "partial", "miss"];

export function MemoryBoard() {
  const ready = useCallStore((s) => s.ready);
  const cache = useCallStore((s) => s.cache);
  const pulse = useCallStore((s) => s.pulse);
  const turns = useCallStore((s) => s.turns);
  if (!ready) return <section className={styles.console} aria-label="Memory board"><p className={styles.sub}>Connecting to the knowledge base…</p></section>;

  const used = new Set(pulse.ids);
  const stats = [...turns].reverse().find((t) => t.result)?.result?.stats;
  const lamp = (id: string, title: string) => {
    const e = cache[id];
    const isUsed = used.has(id);
    return <Lamp key={`${id}:${isUsed ? pulse.nonce : 0}`} tag={e?.tag} used={isUsed}
      title={e ? `${title}: ${LAMP_WORDS[e.tag]}, used ${e.hits} time${e.hits === 1 ? "" : "s"}` : `${title}: not in memory`} />;
  };
  const main = ready.board.docs.filter((d) => !d.extra);
  const extra = ready.board.docs.filter((d) => d.extra);

  return (
    <section className={styles.console} aria-label="Memory board">
      <div className={styles.head}>
        <div>
          <h2 className={styles.title}>Memory board</h2>
          <p className={styles.sub}>
            {ready.profile.cache ? "Each lamp is a page of the knowledge base. A lit lamp is in memory." : "This mode has no memory, so the board stays dark."}
          </p>
        </div>
        <dl className={styles.counters}>
          <div><dt>In memory</dt><dd>{Object.keys(cache).length} / {ready.board.n_chunks}</dd></div>
          <div><dt>Hits</dt><dd>{stats ? `${stats.hits}/${stats.turns}` : "–"}</dd></div>
          <div><dt>Avg wait</dt><dd>{stats ? fmtMs(stats.avg_user_ms) : "–"}</dd></div>
          <div><dt>Drafts used</dt><dd>{stats ? stats.drafts : "–"}</dd></div>
        </dl>
      </div>

      <div className={styles.board}>
        {main.map((d) => (
          <div key={d.name} className={styles.row} data-doc={d.name}>
            <span className={styles.name} title={d.title}>{d.title}</span>
            <div className={styles.lamps}>{d.chunks.map((c) => lamp(c, d.title))}</div>
          </div>
        ))}
      </div>

      {extra.length > 0 && (
        <>
          <p className={styles.extraHead}>Background pages ({extra.length}). Other products and services a real knowledge base would hold.</p>
          <div className={styles.extras}>{extra.flatMap((d) => d.chunks.map((c) => lamp(c, d.title)))}</div>
        </>
      )}

      <ul className={styles.legend} aria-label="Lamp colours">
        {LEGEND.map((k) => <li key={k}><Lamp tag={k} size={10} />{LAMP_WORDS[k][0]!.toUpperCase() + LAMP_WORDS[k].slice(1)}</li>)}
      </ul>
      <p className={styles.cfg}>{describeConfig(ready)}</p>
    </section>
  );
}
