import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSession } from "@/api/session";
import { Card } from "@/components/Card";
import { Icon } from "@/components/Icon";
import { Pill } from "@/components/Pill";
import { ScreenHeader } from "@/components/ScreenHeader";
import { scenarioLabel, shortDomain } from "@/lib/scenario";
import { useCallStore } from "@/state/callStore";
import { useVoice } from "./VoiceProvider";
import styles from "./HomeScreen.module.css";

export function HomeScreen({ onMenu }: { onMenu: () => void }) {
  const navigate = useNavigate();
  const ready = useCallStore((s) => s.ready);
  const status = useCallStore((s) => s.status);
  const voice = useVoice();
  const [topic, setTopic] = useState<string | null>(null);
  const session = getSession();

  if (!ready) {
    return (
      <>
        <ScreenHeader title="Kairo" subtitle="Voice support line" onMenu={onMenu} />
        <p className={styles.status} role="status">{status || "Connecting to the knowledge base…"}</p>
      </>
    );
  }

  const scenarios = ready.domain.scenarios;
  const selected = scenarios.find((s) => s.key === topic) ?? scenarios[0];
  const ask = (q: string) => { session.say(q); navigate("/chat"); };
  const play = (key: string) => { session.playScenario(key); navigate("/chat"); };

  return (
    <>
      <ScreenHeader title="Kairo" subtitle={shortDomain(ready.domain.title)} onMenu={onMenu} />
      <div className={styles.body}>
        <Card className={styles.hero}>
          <p className={styles.kicker}>Voice support line</p>
          <h2 className={styles.heroTitle}>Ask out loud. Get answers before you finish thinking.</h2>
          <p className={styles.lede}>While you talk, a background agent guesses what you will ask next and gets it ready.</p>
          <button type="button" className={styles.start} onClick={voice.toggle} disabled={!voice.supported}>Start Talking</button>
          {!voice.supported && <p className={styles.kicker} role="status">This browser can't record audio. You can still type a question.</p>}
        </Card>

        <div className={styles.tiles}>
          <button type="button" className={styles.tile} onClick={() => navigate("/chat")}>
            <span className={styles.tileTop}><span className={styles.icon}><Icon name="chat" /></span><Icon name="arrow" size={18} /></span>
            <span><strong>Type a question</strong>Text instead of voice</span>
          </button>
          <button type="button" className={styles.tile} onClick={() => navigate("/lab")}>
            <span className={styles.tileTop}><span className={styles.icon}><Icon name="lab" /></span><Icon name="arrow" size={18} /></span>
            <span><strong>Memory board</strong>See what is ready</span>
          </button>
        </div>

        <div className={styles.section}><h2>Topics</h2></div>
        <div className={styles.pills} role="group" aria-label="Topics">
          {scenarios.map((s) => (
            <Pill key={s.key} active={s.key === selected?.key} onClick={() => setTopic(s.key)}>{scenarioLabel(s.key)}</Pill>
          ))}
        </div>

        {selected && (
          <>
            <div className={styles.cards}>
              {(selected.questions ?? []).slice(0, 2).map((q) => (
                <Card key={q} className={styles.q}>
                  <h3>{q}</h3>
                  <p>{scenarioLabel(selected.key)}</p>
                  <button type="button" className={styles.ask} onClick={() => ask(q)} aria-label={`Ask: ${q}`}>Ask<Icon name="arrow" size={16} /></button>
                </Card>
              ))}
            </div>
            <Card>
              <button type="button" className={`${styles.tile} ${styles.play}`} onClick={() => play(selected.key)}
                style={{ background: "transparent", boxShadow: "none", padding: 0 }}>
                <span className={styles.icon}><Icon name="play" /></span>
                <span><strong>Listen in on this call</strong>{selected.turns} questions, played back with pauses</span>
              </button>
            </Card>
          </>
        )}
      </div>
    </>
  );
}
