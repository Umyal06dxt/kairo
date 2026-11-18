import { CallSocket, defaultSocketUrl, type SocketLike } from "./callSocket";

class FakeSocket implements SocketLike {
  static instances: FakeSocket[] = [];
  readyState = 0;
  sent: string[] = [];
  onopen: SocketLike["onopen"] = null;
  onclose: SocketLike["onclose"] = null;
  onmessage: SocketLike["onmessage"] = null;
  constructor(public url: string) { FakeSocket.instances.push(this); }
  send(d: string) { this.sent.push(d); }
  close() { this.readyState = 3; this.onclose?.({}); }
  open() { this.readyState = 1; this.onopen?.({}); }
  receive(o: unknown) { this.onmessage?.({ data: typeof o === "string" ? o : JSON.stringify(o) }); }
}

beforeEach(() => { FakeSocket.instances = []; vi.useFakeTimers(); });
afterEach(() => vi.useRealTimers());
const make = () => new CallSocket("ws://x/ws", (u) => new FakeSocket(u), 100);

describe("CallSocket", () => {
  it("drops sends while closed and delivers them once open", () => {
    const s = make(); s.connect();
    expect(s.send({ t: "say", text: "hi" })).toBe(false);
    FakeSocket.instances[0]!.open();
    expect(s.state).toBe("open");
    expect(s.send({ t: "say", text: "hi" })).toBe(true);
    expect(JSON.parse(FakeSocket.instances[0]!.sent[0]!)).toEqual({ t: "say", text: "hi" });
  });

  it("dispatches parsed messages and ignores malformed frames", () => {
    const s = make(); s.connect(); const got: unknown[] = [];
    s.onMessage((m) => got.push(m));
    const ws = FakeSocket.instances[0]!; ws.open();
    ws.receive({ t: "token", s: "a" }); ws.receive("{not json"); ws.receive({ t: "token", s: "b" });
    expect(got).toEqual([{ t: "token", s: "a" }, { t: "token", s: "b" }]);
  });

  it("reconnects with exponential backoff and stops after close()", () => {
    const s = make(); s.connect();
    FakeSocket.instances[0]!.open(); FakeSocket.instances[0]!.close();
    expect(s.state).toBe("closed");
    vi.advanceTimersByTime(100);
    expect(FakeSocket.instances).toHaveLength(2);
    FakeSocket.instances[1]!.close(); // second failure waits 200 ms
    vi.advanceTimersByTime(199); expect(FakeSocket.instances).toHaveLength(2);
    vi.advanceTimersByTime(1); expect(FakeSocket.instances).toHaveLength(3);
    s.close(); vi.advanceTimersByTime(60_000);
    expect(FakeSocket.instances).toHaveLength(3);
  });

  it("builds the websocket url from the page location", () => {
    expect(defaultSocketUrl({ protocol: "http:", host: "localhost:8000" })).toBe("ws://localhost:8000/ws");
    expect(defaultSocketUrl({ protocol: "https:", host: "lab.example" })).toBe("wss://lab.example/ws");
  });
});
