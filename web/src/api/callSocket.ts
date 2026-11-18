import type { ClientMessage, ServerMessage } from "./types";

export type ConnectionState = "connecting" | "open" | "closed";
type MessageListener = (m: ServerMessage) => void;
type StateListener = (s: ConnectionState) => void;

export interface SocketLike {
  readyState: number;
  send(data: string): void;
  close(): void;
  onopen: ((ev: unknown) => void) | null;
  onclose: ((ev: unknown) => void) | null;
  onmessage: ((ev: { data: string }) => void) | null;
}
export type SocketFactory = (url: string) => SocketLike;

const OPEN = 1;

/** Reconnecting websocket with a typed message channel. Messages sent while closed are dropped
 *  (the caller re-sends `hello` in onOpen, which rebuilds the session). */
export class CallSocket {
  private ws: SocketLike | null = null;
  private msgListeners = new Set<MessageListener>();
  private stateListeners = new Set<StateListener>();
  private retry = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  state: ConnectionState = "closed";

  constructor(
    private readonly url: string,
    private readonly factory: SocketFactory = (u) => new WebSocket(u) as unknown as SocketLike,
    private readonly baseDelayMs = 1000,
  ) {}

  connect(): void {
    this.stopped = false;
    this.setState("connecting");
    const ws = this.factory(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.retry = 0;
      this.setState("open");
    };
    ws.onmessage = (ev) => {
      let msg: ServerMessage;
      try {
        msg = JSON.parse(ev.data) as ServerMessage;
      } catch {
        return; // ignore malformed frames rather than crash the UI
      }
      this.msgListeners.forEach((l) => l(msg));
    };
    ws.onclose = () => {
      this.setState("closed");
      if (this.stopped) return;
      const delay = Math.min(10_000, this.baseDelayMs * 2 ** this.retry++);
      this.timer = setTimeout(() => this.connect(), delay);
    };
  }

  send(msg: ClientMessage): boolean {
    if (!this.ws || this.ws.readyState !== OPEN) return false;
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  onMessage(l: MessageListener): () => void {
    this.msgListeners.add(l);
    return () => this.msgListeners.delete(l);
  }

  onState(l: StateListener): () => void {
    this.stateListeners.add(l);
    return () => this.stateListeners.delete(l);
  }

  close(): void {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    this.ws?.close();
  }

  private setState(s: ConnectionState): void {
    this.state = s;
    this.stateListeners.forEach((l) => l(s));
  }
}

export function defaultSocketUrl(loc: Pick<Location, "protocol" | "host"> = window.location): string {
  return `${loc.protocol === "https:" ? "wss" : "ws"}://${loc.host}/ws`;
}
