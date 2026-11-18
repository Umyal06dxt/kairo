import { Icon } from "@/components/Icon";
import { IconButton } from "@/components/IconButton";
import { Orb } from "@/components/Orb";
import { Waveform } from "@/components/Waveform";
import { useSettingsStore } from "@/state/settingsStore";
import { getSession } from "@/api/session";
import { splitInterim } from "./voiceCapture";
import { useVoice } from "./VoiceProvider";
import styles from "./ListeningScreen.module.css";

/** Full-screen voice mode, after the reference: the orb breathes with the caller's voice. */
export function ListeningScreen() {
  const voice = useVoice();
  const speak = useSettingsStore((s) => s.settings.speak);
  const update = useSettingsStore((s) => s.update);
  if (voice.state !== "listening" && voice.state !== "starting") return null;

  const { done, live } = splitInterim(voice.interim);
  const starting = voice.state === "starting";
  return (
    <div className={styles.overlay} role="dialog" aria-modal="true" aria-label="Voice mode">
      <div className={styles.head}>
        <IconButton icon="back" label="Cancel" onClick={voice.cancel} />
        <div className={styles.mid}>
          <h2 className={styles.title}>AI voice assistant</h2>
          <p className={styles.sub} role="status">{starting ? "Opening the microphone…" : "Listening…"}</p>
        </div>
      </div>
      <div className={styles.stage}>
        <Orb level={voice.level} size={Math.min(300, Math.round(window.innerWidth * 0.72))} />
        <p className={styles.text} aria-live="polite">
          {voice.interim ? (
            <>{done && <span className={styles.done}>{done} </span>}<span className={styles.live}>{live}</span></>
          ) : (
            <span className={styles.prompt}>Ask about fees, cards, loans or hours. Tap the microphone when you are done.</span>
          )}
        </p>
        <Waveform className={styles.wave} bars={9} level={Math.max(0.08, voice.level)} seed={3} />
      </div>
      <div className={styles.controls}>
        <IconButton icon="sparkle" label={speak ? "Spoken answers on" : "Spoken answers off"} pressed={speak}
          variant={speak ? "dark" : "light"} onClick={() => { update({ speak: !speak }); getSession().unlockAudio(); }} />
        <button type="button" className={styles.mic} onClick={voice.toggle} aria-label="Finish and send"><Icon name="mic" size={36} /></button>
        <IconButton icon="close" label="Cancel" onClick={voice.cancel} />
      </div>
    </div>
  );
}
