import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { getSession } from "@/api/session";
import { Pill } from "@/components/Pill";
import { ScreenHeader } from "@/components/ScreenHeader";
import { shortDomain } from "@/lib/scenario";
import { useCallStore } from "@/state/callStore";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import { useVoice } from "./VoiceProvider";
import styles from "./ChatScreen.module.css";

export function ChatScreen({ onMenu }: { onMenu: () => void }) {
  const navigate = useNavigate();
  const ready = useCallStore((s) => s.ready);
  const turns = useCallStore((s) => s.turns);
  const notices = useCallStore((s) => s.notices);
  const autoplay = useCallStore((s) => s.autoplay);
  const noSpeech = useCallStore((s) => s.noSpeech);
  const dismiss = useCallStore((s) => s.dismissNotice);
  const status = useCallStore((s) => s.status);
  const voice = useVoice();
  const end = useRef<HTMLDivElement>(null);
  const session = getSession();

  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [turns]);
  const last = turns[turns.length - 1];
  useEffect(() => { end.current?.scrollIntoView?.({ block: "end" }); }, [last?.answer]);

  const hasCache = ready?.profile.cache ?? true;
  return (
    <>
      <ScreenHeader title="Conversation" subtitle={status || (ready ? shortDomain(ready.domain.title) : "Connecting…")}
        onBack={() => navigate("/")} onMenu={onMenu} />
      <div className={styles.scroll}>
        {notices.map((n, i) => (
          <p key={`${i}:${n}`} className={styles.notice} role="status">
            <span>{n}</span><button type="button" onClick={() => dismiss(i)} aria-label="Dismiss">×</button>
          </p>
        ))}
        {autoplay.active && (
          <div className={styles.bar}>
            <span>Playing a scripted call.</span>
            <Pill onClick={() => session.stopScenario()}>Stop</Pill>
          </div>
        )}
        {turns.length === 0 ? (
          <p className={styles.empty}><strong>No questions yet</strong>Tap the microphone and talk, or type below.</p>
        ) : (
          <ol className={styles.list}>{turns.map((t) => <MessageBubble key={t.id} turn={t} hasCache={hasCache} />)}</ol>
        )}
        <div ref={end} />
      </div>
      <p className={styles.hint} role="status">
        {voice.error ?? (noSpeech ? "Didn't catch that. Tap the mic and try again." : "")}
      </p>
      <Composer onSend={(t) => session.say(t)} onPartial={(t) => session.partial(t)}
        placeholder={ready?.domain.key === "bank" ? "Ask about fees, cards, loans, hours…" : "Ask about pricing, the API, security…"} />
    </>
  );
}
