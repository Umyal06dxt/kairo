import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/Icon";
import { Waveform } from "@/components/Waveform";
import { clock } from "@/lib/format";
import type { VoiceNote } from "@/state/callStore";
import styles from "./VoiceNoteBubble.module.css";

/** The caller's own recording, playable, drawn like the voice message in the reference. */
export function VoiceNoteBubble({ note, seed = 7 }: { note: VoiceNote; seed?: number }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const a = new Audio(note.url);
    audio.current = a;
    a.addEventListener("timeupdate", () => setProgress(a.duration ? a.currentTime / a.duration : 0));
    a.addEventListener("ended", () => { setPlaying(false); setProgress(0); });
    return () => { a.pause(); audio.current = null; };
  }, [note.url]);

  const toggle = () => {
    const a = audio.current;
    if (!a) return;
    if (playing) { a.pause(); setPlaying(false); }
    else { void a.play().then(() => setPlaying(true)).catch(() => setPlaying(false)); }
  };

  return (
    <div className={styles.note}>
      <button type="button" className={styles.play} onClick={toggle} aria-label={playing ? "Pause voice note" : "Play voice note"}>
        <Icon name={playing ? "pause" : "play"} size={18} />
      </button>
      <Waveform className={styles.wave} bars={30} progress={progress} seed={seed} />
      <span className={styles.time}>{clock(note.durationMs)}</span>
    </div>
  );
}
