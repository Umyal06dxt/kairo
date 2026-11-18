import { AudioPlayer } from "@/lib/audioPlayer";
import { useCallStore } from "@/state/callStore";
import { useSettingsStore } from "@/state/settingsStore";
import { CallSocket, defaultSocketUrl } from "./callSocket";

/** Owns the websocket for one browser tab and connects it to the stores and the audio player. */
export class Session {
  private started = false;
  private offs: (() => void)[] = [];

  constructor(
    private readonly socket: CallSocket = new CallSocket(defaultSocketUrl()),
    private readonly player: AudioPlayer = new AudioPlayer(),
  ) {}

  start(): void {
    if (this.started) return; // React StrictMode mounts effects twice in dev
    this.started = true;
    const call = useCallStore.getState();
    this.offs.push(
      this.socket.onState((s) => {
        call.setConnection(s);
        if (s === "open") this.hello();
      }),
      this.socket.onMessage((m) => {
        if (m.t === "audio_out") this.player.enqueue(m.data);
        call.apply(m);
      }),
    );
    this.socket.connect();
  }

  stop(): void {
    this.offs.forEach((o) => o());
    this.offs = [];
    this.socket.close();
    this.player.stop();
    this.started = false;
  }

  /** (Re)start the call with the current settings. */
  hello(): void {
    this.player.stop();
    useCallStore.getState().reset();
    this.socket.send({ t: "hello", settings: useSettingsStore.getState().settings });
  }

  unlockAudio(): void { this.player.unlock(); }
  say(text: string): boolean { return text.trim() !== "" && this.socket.send({ t: "say", text }); }
  partial(text: string): void { this.socket.send({ t: "partial", text }); }
  sendAudio(data: string, mime: string): void { this.socket.send({ t: "audio", data, mime }); }
  playScenario(scenario: string): void { this.socket.send({ t: "autoplay", scenario }); }
  stopScenario(): void { this.socket.send({ t: "stop" }); }
}

let shared: Session | null = null;
/** The app-wide session (created lazily so importing this module has no side effects). */
export const getSession = (): Session => (shared ??= new Session());
