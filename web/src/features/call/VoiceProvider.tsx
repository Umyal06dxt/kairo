import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { getSession, type Session } from "@/api/session";
import { useCallStore } from "@/state/callStore";
import {
  MIN_VOICE_BYTES, blobToBase64, createLevelMeter, pickMimeType, type LevelMeter,
} from "./voiceCapture";

export type VoiceState = "idle" | "starting" | "listening" | "error";

export interface VoiceApi {
  state: VoiceState;
  level: number;
  interim: string;
  error: string | null;
  supported: boolean;
  /** Tap the mic: start listening, or stop and send what was said. */
  toggle: () => void;
  cancel: () => void;
}

/** Browser capabilities, injectable so the controller can be tested without hardware. */
export interface VoiceDeps {
  mediaDevices?: Pick<MediaDevices, "getUserMedia">;
  MediaRecorderCtor?: typeof MediaRecorder;
  SpeechRecognitionCtor?: (new () => SpeechRecognitionLike) | undefined;
  session?: Pick<Session, "partial" | "sendAudio" | "unlockAudio">;
  meter?: (stream: MediaStream) => LevelMeter;
}

/** The slice of the Web Speech API we use (it is not in lib.dom for all browsers). */
export interface SpeechRecognitionLike {
  interimResults: boolean;
  lang: string;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  start(): void;
  stop(): void;
}

/** Everything that must be released when a recording ends. */
interface LiveCapture {
  recorder: MediaRecorder;
  stream: MediaStream;
  meter: LevelMeter;
  raf: number;
  sr?: SpeechRecognitionLike;
  startedAt: number;
  chunks: Blob[];
  lastPartial: number;
}

const VoiceContext = createContext<VoiceApi | null>(null);

export function useVoice(): VoiceApi {
  const v = useContext(VoiceContext);
  if (!v) throw new Error("useVoice must be used inside <VoiceProvider>");
  return v;
}

function defaultSpeechRecognition(): VoiceDeps["SpeechRecognitionCtor"] {
  const w = window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export function VoiceProvider({ children, deps = {} }: { children: ReactNode; deps?: VoiceDeps }) {
  const mediaDevices = deps.mediaDevices ?? navigator.mediaDevices;
  const Recorder = deps.MediaRecorderCtor ?? (typeof MediaRecorder === "undefined" ? undefined : MediaRecorder);
  const supported = Boolean(mediaDevices && typeof mediaDevices.getUserMedia === "function" && Recorder);

  const [state, setState] = useState<VoiceState>("idle");
  const [level, setLevel] = useState(0);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);

  const live = useRef<LiveCapture | null>(null);

  const session = deps.session ?? getSession();

  const teardown = useCallback(() => {
    const l = live.current;
    if (!l) return;
    cancelAnimationFrame(l.raf);
    try { l.sr?.stop(); } catch { /* already stopped */ }
    l.meter.close();
    l.stream.getTracks().forEach((t) => t.stop());
    live.current = null;
    setLevel(0);
    setInterim("");
  }, []);

  const finish = useCallback((send: boolean) => {
    const l = live.current;
    if (!l) return;
    const { recorder, chunks, startedAt } = l;
    recorder.onstop = async () => {
      const blob = new Blob(chunks, { type: recorder.mimeType });
      teardown();
      setState("idle");
      if (!send) return;
      if (blob.size < MIN_VOICE_BYTES) {
        setError("That was too short. Tap the mic and speak, then tap again.");
        return;
      }
      useCallStore.getState().attachVoice({ url: URL.createObjectURL(blob), durationMs: Date.now() - startedAt });
      session.sendAudio(await blobToBase64(blob), recorder.mimeType);
    };
    try { recorder.stop(); } catch { recorder.onstop?.(new Event("stop")); }
  }, [session, teardown]);

  const start = useCallback(async () => {
    if (live.current || !supported || !mediaDevices || !Recorder) return;
    setError(null);
    setState("starting");
    session.unlockAudio();
    try {
      const stream = await mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      const mimeType = pickMimeType((t) => Recorder.isTypeSupported?.(t) ?? false);
      const recorder = new Recorder(stream, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      recorder.start(250);
      const meter = (deps.meter ?? createLevelMeter)(stream);
      const entry: LiveCapture = { recorder, stream, meter, raf: 0, startedAt: Date.now(), chunks, lastPartial: 0 };
      const tick = () => {
        setLevel(meter.read());
        entry.raf = requestAnimationFrame(tick);
      };
      entry.raf = requestAnimationFrame(tick);

      const SR = "SpeechRecognitionCtor" in deps ? deps.SpeechRecognitionCtor : defaultSpeechRecognition();
      if (SR) {
        const sr = new SR();
        sr.interimResults = true;
        sr.lang = "en-US";
        sr.onresult = (e) => {
          const text = Array.from(e.results as ArrayLike<ArrayLike<{ transcript: string }>>)
            .map((r) => r[0]?.transcript ?? "").join(" ").trim();
          setInterim(text);
          const now = Date.now();
          if (text.length >= 12 && now - entry.lastPartial > 400) {
            entry.lastPartial = now;
            session.partial(text); // Stream-RAG-style early lookup while the caller is still speaking
          }
        };
        sr.onerror = () => {};
        try { sr.start(); entry.sr = sr; } catch { /* some browsers throw if already running */ }
      }
      live.current = entry;
      setState("listening");
    } catch {
      setState("error");
      setError("Couldn't open the microphone. Check this site's microphone permission in your browser.");
    }
  }, [Recorder, deps, mediaDevices, session, supported]);

  const toggle = useCallback(() => {
    if (state === "listening") finish(true);
    else if (state === "idle" || state === "error") void start();
  }, [finish, start, state]);

  const cancel = useCallback(() => {
    if (live.current) finish(false);
    else setState("idle");
  }, [finish]);

  useEffect(() => teardown, [teardown]);

  const value = useMemo<VoiceApi>(
    () => ({ state, level, interim, error, supported, toggle, cancel }),
    [state, level, interim, error, supported, toggle, cancel],
  );
  return <VoiceContext.Provider value={value}>{children}</VoiceContext.Provider>;
}
