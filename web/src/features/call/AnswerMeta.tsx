import type { TurnMsg } from "@/api/types";
import { Lamp, type LampKind } from "@/features/board/Lamp";
import { fmtMs } from "@/lib/format";
import { describeTurn, routeSegments } from "./turnMeta";
import styles from "./AnswerMeta.module.css";

const KIND_LAMP = { draft: "draft", hit: "neighbor", miss: "miss" } as const;

/** How the answer was made and how long it took, tucked under the bubble until asked for. */
export function AnswerMeta({ result, hasCache }: { result: TurnMsg; hasCache: boolean }) {
  const badge = describeTurn(result, hasCache);
  const seg = routeSegments(result);
  const pct = (f: number) => `${(f * 100).toFixed(1)}%`;
  const tags = result.tags as (LampKind | "")[];
  // Pages fetched from the database straight away were never in memory: they are "misses".
  const fallback: LampKind = result.source === "store" ? "miss" : "direct";

  return (
    <details className={styles.meta}>
      <summary>
        <span className={styles.chip}><Lamp tag={KIND_LAMP[badge.kind]} size={10} />{badge.title}</span>
        <span className={styles.wait}>{fmtMs(result.user_ms)}</span>
      </summary>
      <div className={styles.body}>
        <p>{badge.why}</p>
        <div className={styles.strip} role="img" aria-label="Time before the first word">
          <i className={styles.e} style={{ width: pct(seg.embed) }} />
          <i className={styles.r} style={{ width: pct(seg.lookup) }} />
          <i className={styles.l} style={{ width: pct(seg.model) }} />
        </div>
        <p className={styles.steps}>
          <span>understanding {fmtMs(result.embed_ms)}</span>
          <span>lookup {fmtMs(result.retrieval_ms)}</span>
          <span>{result.source === "draft" ? "no model wait" : `first word ${fmtMs(result.llm_ms)}`}</span>
        </p>
        {result.chunk_ids.length > 0 && (
          <div className={styles.evidence} aria-label="Pages used">
            {result.chunk_ids.map((id, i) => <Lamp key={id} tag={tags[i] || fallback} size={12} title={id} />)}
            <small>{result.chunk_ids.length} page{result.chunk_ids.length === 1 ? "" : "s"} used</small>
          </div>
        )}
        {result.gold && (
          <p className={styles.gold}>
            {result.gold.doc_ok != null && <span className={result.gold.doc_ok ? styles.ok : styles.no}>{result.gold.doc_ok ? "Right source page used" : "Wrong source page"}</span>}
            {result.gold.answer_ok != null && <> · <span className={result.gold.answer_ok ? styles.ok : styles.no}>{result.gold.answer_ok ? "Answer has the expected facts" : "Answer is missing expected facts"}</span></>}
          </p>
        )}
      </div>
    </details>
  );
}
