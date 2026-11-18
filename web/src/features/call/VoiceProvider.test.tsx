import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useCallStore } from "@/state/callStore";
import { VoiceProvider, useVoice, type SpeechRecognitionLike, type VoiceDeps } from "./VoiceProvider";

class FakeRecorder {
  static isTypeSupported = () => true;
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: ((e: Event) => void) | null = null;
  constructor(public stream: MediaStream) {}
  start() { this.ondataavailable?.({ data: new Blob([new Uint8Array(5000)]) }); }
  stop() { queueMicrotask(() => this.onstop?.(new Event("stop"))); }
}

function setup(over: Partial<VoiceDeps> = {}) {
  const track = { stop: vi.fn() };
  const stream = { getTracks: () => [track] } as unknown as MediaStream;
  const session = { partial: vi.fn(), sendAudio: vi.fn(), unlockAudio: vi.fn() };
  const deps: VoiceDeps = {
    mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    MediaRecorderCtor: FakeRecorder as unknown as typeof MediaRecorder,
    SpeechRecognitionCtor: undefined,
    session, meter: () => ({ read: () => 0.4, close: vi.fn() }), ...over,
  };
  function Probe() {
    const v = useVoice();
    return (
      <div>
        <p data-testid="state">{v.state}</p><p data-testid="err">{v.error}</p><p data-testid="interim">{v.interim}</p>
        <button onClick={v.toggle}>toggle</button><button onClick={v.cancel}>cancel</button>
      </div>
    );
  }
  render(<VoiceProvider deps={deps}><Probe /></VoiceProvider>);
  return { track, session, deps };
}

beforeEach(() => {
  useCallStore.setState({ pendingVoice: null });
  URL.createObjectURL = vi.fn(() => "blob:voice");
});

describe("VoiceProvider", () => {
  it("starts listening on the first tap and sends the recording on the second", async () => {
    const { session, track } = setup();
    await userEvent.click(screen.getByText("toggle"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("listening"));
    expect(session.unlockAudio).toHaveBeenCalled();
    await userEvent.click(screen.getByText("toggle"));
    await waitFor(() => expect(session.sendAudio).toHaveBeenCalledOnce());
    expect(session.sendAudio.mock.calls[0]![1]).toBe("audio/webm");
    expect(useCallStore.getState().pendingVoice?.url).toBe("blob:voice");
    expect(track.stop).toHaveBeenCalled(); // the microphone is released
    expect(screen.getByTestId("state")).toHaveTextContent("idle");
  });

  it("cancel discards the recording and releases the microphone", async () => {
    const { session, track } = setup();
    await userEvent.click(screen.getByText("toggle"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("listening"));
    await userEvent.click(screen.getByText("cancel"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("idle"));
    expect(session.sendAudio).not.toHaveBeenCalled();
    expect(track.stop).toHaveBeenCalled();
  });

  it("explains a denied microphone instead of failing silently", async () => {
    setup({ mediaDevices: { getUserMedia: vi.fn().mockRejectedValue(new Error("denied")) } });
    await userEvent.click(screen.getByText("toggle"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("error"));
    expect(screen.getByTestId("err")).toHaveTextContent(/microphone permission/);
  });

  it("rejects a recording that is too short", async () => {
    class Tiny extends FakeRecorder { start() { this.ondataavailable?.({ data: new Blob(["x"]) }); } }
    const { session } = setup({ MediaRecorderCtor: Tiny as unknown as typeof MediaRecorder });
    await userEvent.click(screen.getByText("toggle"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("listening"));
    await userEvent.click(screen.getByText("toggle"));
    await waitFor(() => expect(screen.getByTestId("err")).toHaveTextContent(/too short/));
    expect(session.sendAudio).not.toHaveBeenCalled();
  });

  it("shows live speech and triggers early retrieval once there is enough text", async () => {
    class FakeSR implements SpeechRecognitionLike {
      static last: FakeSR | null = null;
      interimResults = false; lang = ""; onresult: SpeechRecognitionLike["onresult"] = null; onerror = null;
      constructor() { FakeSR.last = this; }
      start() {} stop() {}
    }
    const { session } = setup({ SpeechRecognitionCtor: FakeSR });
    await userEvent.click(screen.getByText("toggle"));
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("listening"));
    act(() => FakeSR.last!.onresult?.({ results: [[{ transcript: "how much" }]] }));
    expect(screen.getByTestId("interim")).toHaveTextContent("how much");
    expect(session.partial).not.toHaveBeenCalled(); // too short to be worth a lookup
    act(() => FakeSR.last!.onresult?.({ results: [[{ transcript: "how much is the overdraft fee" }]] }));
    expect(session.partial).toHaveBeenCalledWith("how much is the overdraft fee");
  });

  it("reports when the browser cannot record at all", () => {
    function Probe() { return <p data-testid="s">{String(useVoice().supported)}</p>; }
    render(<VoiceProvider deps={{ mediaDevices: undefined, MediaRecorderCtor: undefined }}><Probe /></VoiceProvider>);
    expect(screen.getByTestId("s")).toHaveTextContent("false");
  });
});
