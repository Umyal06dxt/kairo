import { clockTime } from "@/lib/format";
import type { Turn } from "@/state/callStore";
import { AnswerMeta } from "./AnswerMeta";
import { VoiceNoteBubble } from "./VoiceNoteBubble";
import styles from "./MessageBubble.module.css";

interface Props { turn: Turn; hasCache: boolean }

export function MessageBubble({ turn, hasCache }: Props) {
  const stamp = clockTime(new Date(turn.at));
  return (
    <li className={styles.pair}>
      <div className={styles.userRow}>
        {turn.voice ? (
          <>
            <VoiceNoteBubble note={turn.voice} seed={turn.id} />
            <p className={styles.caption}>“{turn.question}”</p>
          </>
        ) : (
          <p className={styles.user}>{turn.question}</p>
        )}
        <time className={styles.stamp}>{turn.via === "script" ? `Scripted caller · ${stamp}` : stamp}</time>
      </div>
      <div className={styles.botRow}>
        <span className={styles.avatar} aria-hidden="true"><i /></span>
        <div>
          <p className={[styles.bot, turn.pending && !turn.answer ? styles.pending : ""].join(" ")} aria-live="polite">
            {turn.answer || (turn.pending ? <span className={styles.dots} aria-label="Thinking" /> : "")}
          </p>
          {turn.result && <AnswerMeta result={turn.result} hasCache={hasCache} />}
        </div>
      </div>
    </li>
  );
}
