import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { initialCallState, useCallStore, type Turn } from "@/state/callStore";
import { ready, turnMsg } from "@/test/fixtures";
import { ChatScreen } from "./ChatScreen";
import { Composer } from "./Composer";
import { HomeScreen } from "./HomeScreen";
import { ListeningScreen } from "./ListeningScreen";
import { MessageBubble } from "./MessageBubble";
import { VoiceProvider, useVoice, type VoiceDeps } from "./VoiceProvider";

const session = vi.hoisted(() => ({
  say: vi.fn(() => true), partial: vi.fn(), playScenario: vi.fn(), stopScenario: vi.fn(),
  sendAudio: vi.fn(), unlockAudio: vi.fn(), hello: vi.fn(),
}));
vi.mock("@/api/session", () => ({ getSession: () => session }));

const noMic: VoiceDeps = { mediaDevices: undefined, MediaRecorderCtor: undefined, session };
const withVoice = (ui: React.ReactNode, deps: VoiceDeps = noMic) => (
  <MemoryRouter><VoiceProvider deps={deps}>{ui}</VoiceProvider></MemoryRouter>
);
const turn = (over: Partial<Turn> = {}): Turn => ({
  id: 1, question: "What is the overdraft fee?", via: "text", answer: "It is 30 dollars per item.",
  pending: false, result: turnMsg(), voice: null, at: Date.UTC(2026, 10, 18, 15, 30), ...over,
});

beforeEach(() => { vi.clearAllMocks(); useCallStore.setState({ ...initialCallState }); });

describe("Composer", () => {
  it("sends trimmed text, clears the box and ignores empty input", async () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Your question"), "  hello  ");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(screen.getByLabelText("Your question")).toHaveValue("");
  });

  it("starts retrieval early while typing, debounced, and not for short text", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onPartial = vi.fn();
    render(<Composer onSend={() => {}} onPartial={onPartial} partialDelayMs={300} />);
    const input = screen.getByLabelText("Your question");
    await userEvent.type(input, "overdraft");
    act(() => { vi.advanceTimersByTime(400); });
    expect(onPartial).not.toHaveBeenCalled(); // 9 chars: too short to be worth a lookup
    await userEvent.type(input, " fee per item");
    expect(onPartial).not.toHaveBeenCalled(); // still debouncing
    act(() => { vi.advanceTimersByTime(300); });
    expect(onPartial).toHaveBeenCalledTimes(1);
    expect(onPartial).toHaveBeenCalledWith("overdraft fee per item");
    vi.useRealTimers();
  });

  it("submitting cancels a pending partial lookup", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const onPartial = vi.fn();
    render(<Composer onSend={() => {}} onPartial={onPartial} />);
    await userEvent.type(screen.getByLabelText("Your question"), "what is the overdraft fee");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    act(() => { vi.advanceTimersByTime(1000); });
    expect(onPartial).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe("MessageBubble", () => {
  it("shows the question, the answer and how the answer was made", () => {
    render(<ol><MessageBubble turn={turn()} hasCache /></ol>);
    expect(screen.getByText("What is the overdraft fee?")).toBeInTheDocument();
    expect(screen.getByText("It is 30 dollars per item.")).toBeInTheDocument();
    expect(screen.getByText("Answered from memory")).toBeInTheDocument();
    expect(screen.getByText("905 ms")).toBeInTheDocument();
    expect(screen.getByText("Right source page used")).toBeInTheDocument();
  });

  it("shows a thinking indicator while the answer is pending", () => {
    render(<ol><MessageBubble turn={turn({ answer: "", pending: true, result: null })} hasCache /></ol>);
    expect(screen.getByLabelText("Thinking")).toBeInTheDocument();
  });

  it("renders a voice message with its transcript underneath", () => {
    render(<ol><MessageBubble turn={turn({ via: "voice", voice: { url: "blob:x", durationMs: 4000 } })} hasCache /></ol>);
    expect(screen.getByRole("button", { name: "Play voice note" })).toBeInTheDocument();
    expect(screen.getByText("0:04")).toBeInTheDocument();
    expect(screen.getByText(/“What is the overdraft fee\?”/)).toBeInTheDocument();
  });

  it("labels scripted callers so they are not mistaken for the user", () => {
    render(<ol><MessageBubble turn={turn({ via: "script" })} hasCache /></ol>);
    expect(screen.getByText(/Scripted caller/)).toBeInTheDocument();
  });

  it("explains a pre-drafted answer and a correction distinctly", () => {
    const { rerender } = render(<ol><MessageBubble turn={turn({ result: turnMsg({ source: "draft" }) })} hasCache /></ol>);
    expect(screen.getByText("Answered from a pre-drafted answer")).toBeInTheDocument();
    rerender(<ol><MessageBubble turn={turn({ result: turnMsg({ corrected: true, hit: false, source: "store" }) })} hasCache /></ol>);
    expect(screen.getByText("Memory was wrong, so it looked again")).toBeInTheDocument();
  });
});

describe("ChatScreen", () => {
  it("invites the user to start when there is no conversation", () => {
    render(withVoice(<ChatScreen onMenu={() => {}} />));
    expect(screen.getByText("No questions yet")).toBeInTheDocument();
  });

  it("lists turns and lets notices be dismissed", async () => {
    useCallStore.setState({ ready: ready(), turns: [turn()], notices: ["No OPENAI_API_KEY: using offline answers."] });
    render(withVoice(<ChatScreen onMenu={() => {}} />));
    expect(screen.getByText("It is 30 dollars per item.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/No OPENAI_API_KEY/)).toBeNull();
  });

  it("sends typed questions through the session", async () => {
    useCallStore.setState({ ready: ready() });
    render(withVoice(<ChatScreen onMenu={() => {}} />));
    await userEvent.type(screen.getByLabelText("Your question"), "How do I freeze my card?");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(session.say).toHaveBeenCalledWith("How do I freeze my card?");
  });

  it("offers to stop a scripted call that is playing", async () => {
    useCallStore.setState({ ready: ready(), autoplay: { active: true, scenario: "B1" } });
    render(withVoice(<ChatScreen onMenu={() => {}} />));
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(session.stopScenario).toHaveBeenCalled();
  });

  it("tells the user when no speech was heard", () => {
    useCallStore.setState({ ready: ready(), noSpeech: true });
    render(withVoice(<ChatScreen onMenu={() => {}} />));
    expect(screen.getByText(/Didn't catch that/)).toBeInTheDocument();
  });
});

describe("HomeScreen", () => {
  it("waits for the server before showing topics", () => {
    useCallStore.setState({ status: "Loading knowledge base…" });
    render(withVoice(<HomeScreen onMenu={() => {}} />));
    expect(screen.getByRole("status")).toHaveTextContent("Loading knowledge base…");
  });

  it("shows topics from the scenarios and example questions for the selected one", async () => {
    useCallStore.setState({ ready: ready() });
    render(withVoice(<HomeScreen onMenu={() => {}} />));
    expect(screen.getByRole("button", { name: "Lost debit card" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("I lost my debit card, what now?")).toBeInTheDocument();
    expect(screen.queryByText("Third question")).toBeNull(); // only the first two
    await userEvent.click(screen.getByRole("button", { name: "Fees" }));
    expect(screen.getByText("What is the overdraft fee?")).toBeInTheDocument();
  });

  it("asks an example question and plays a scripted call", async () => {
    useCallStore.setState({ ready: ready() });
    render(withVoice(<HomeScreen onMenu={() => {}} />));
    await userEvent.click(screen.getByRole("button", { name: "Ask: How do I freeze it?" }));
    expect(session.say).toHaveBeenCalledWith("How do I freeze it?");
    await userEvent.click(screen.getByText("Listen in on this call"));
    expect(session.playScenario).toHaveBeenCalledWith("B1 Lost debit card");
  });

  it("disables voice and says why when the browser cannot record", () => {
    useCallStore.setState({ ready: ready() });
    render(withVoice(<HomeScreen onMenu={() => {}} />));
    expect(screen.getByRole("button", { name: "Start Talking" })).toBeDisabled();
    expect(screen.getByText(/can't record audio/)).toBeInTheDocument();
  });
});

describe("ListeningScreen", () => {
  class Rec {
    static isTypeSupported = () => true;
    mimeType = "audio/webm"; ondataavailable = null; onstop: ((e: Event) => void) | null = null;
    start() {} stop() { queueMicrotask(() => this.onstop?.(new Event("stop"))); }
  }
  const mic: VoiceDeps = {
    mediaDevices: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [] }) },
    MediaRecorderCtor: Rec as unknown as typeof MediaRecorder, SpeechRecognitionCtor: undefined,
    session, meter: () => ({ read: () => 0.3, close: () => {} }),
  };
  function Harness() {
    const v = useVoice();
    return <><button onClick={v.toggle}>go</button><ListeningScreen /></>;
  }

  it("is invisible until the user starts talking, then shows the orb and prompt", async () => {
    render(withVoice(<Harness />, mic));
    expect(screen.queryByRole("dialog")).toBeNull();
    await userEvent.click(screen.getByText("go"));
    expect(await screen.findByRole("dialog", { name: "Voice mode" })).toBeInTheDocument();
    expect(screen.getByTestId("orb")).toBeInTheDocument();
    expect(await screen.findByText("Listening…")).toBeInTheDocument();
    expect(screen.getByText(/Tap the microphone when you are done/)).toBeInTheDocument();
  });

  it("cancel closes it without sending anything", async () => {
    render(withVoice(<Harness />, mic));
    await userEvent.click(screen.getByText("go"));
    await screen.findByText("Listening…");
    await userEvent.click(screen.getAllByRole("button", { name: "Cancel" })[0]!);
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(session.sendAudio).not.toHaveBeenCalled();
  });
});

describe("AnswerMeta evidence lamps", () => {
  it("shows database-fetched pages as misses, not as dark (off) lamps", () => {
    const store = turn({ result: turnMsg({ source: "store", hit: false, tags: ["", ""], chunk_ids: ["a", "b"] }) });
    const { container } = render(<ol><MessageBubble turn={store} hasCache /></ol>);
    expect(container.querySelectorAll('[aria-label="Pages used"] [data-tag="miss"]')).toHaveLength(2);
    expect(container.querySelectorAll('[aria-label="Pages used"] [data-tag="off"]')).toHaveLength(0);
  });
  it("keeps the provenance colour for pages that came from memory", () => {
    const { container } = render(<ol><MessageBubble turn={turn({ result: turnMsg({ tags: ["predicted"] }) })} hasCache /></ol>);
    expect(container.querySelectorAll('[aria-label="Pages used"] [data-tag="predicted"]')).toHaveLength(1);
  });
});
