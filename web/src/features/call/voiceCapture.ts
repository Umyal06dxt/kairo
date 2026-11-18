import { rmsLevel } from "@/lib/orbMath";

export const MIN_VOICE_BYTES = 2000;
const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4"];

/** First recording format the browser supports, or undefined to let it choose. */
export function pickMimeType(isSupported: (t: string) => boolean): string | undefined {
  return PREFERRED_TYPES.find((t) => isSupported(t));
}

export function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve(String(fr.result).split(",")[1] ?? "");
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(blob);
  });
}

/** Split live speech text into the part already settled (grey) and the latest words (black). */
export function splitInterim(text: string, tail = 5): { done: string; live: string } {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length <= tail) return { done: "", live: words.join(" ") };
  return { done: words.slice(0, -tail).join(" "), live: words.slice(-tail).join(" ") };
}

export interface LevelMeter { read(): number; close(): void }

/** Reads the microphone's loudness (0..1) via a Web Audio analyser; no-ops where unsupported. */
export function createLevelMeter(stream: MediaStream): LevelMeter {
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return { read: () => 0, close: () => {} };
  const ctx = new Ctor();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const data = new Uint8Array(analyser.fftSize);
  return {
    read() {
      analyser.getByteTimeDomainData(data);
      return rmsLevel(data);
    },
    close() { void ctx.close().catch(() => {}); },
  };
}
