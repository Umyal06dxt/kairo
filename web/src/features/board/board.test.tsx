import { render, screen, within } from "@testing-library/react";
import type { ReadyMsg } from "@/api/types";
import { initialCallState, useCallStore } from "@/state/callStore";
import { LedgerPanel } from "./LedgerPanel";
import { MemoryBoard, describeConfig } from "./MemoryBoard";

const ready = (over: Partial<ReadyMsg> = {}): ReadyMsg => ({
  t: "ready",
  board: { n_chunks: 5, n_extra: 2, docs: [
    { name: "fees.md", title: "Fee Schedule", extra: false, chunks: ["fees.md:0", "fees.md:1"] },
    { name: "cards.md", title: "Debit Cards", extra: false, chunks: ["cards.md:0"] },
    { name: "x.md", title: "Extra page", extra: true, chunks: ["x.md:0", "x.md:1"] },
  ] },
  settings: {} as never, profile: { key: "optimized", label: "Kairo optimized", cache: true },
  config: { strategy: "hybrid", verify: true, drafts: true, tau: 0.6, context: 6, rerank: true },
  llm: "openai", embedder: "local", notes: [],
  domain: { key: "bank", title: "Bank", blurb: "", scenarios: [] }, voice: { stt: "ready", tts: true }, ...over,
});

beforeEach(() => useCallStore.setState({ ...initialCallState }));

describe("MemoryBoard", () => {
  it("lights only the lamps in memory, coloured by why they are there", () => {
    useCallStore.setState({
      ready: ready(),
      cache: { "fees.md:0": { id: "fees.md:0", tag: "predicted", hits: 2, ttl: 100 }, "x.md:1": { id: "x.md:1", tag: "partial", hits: 0, ttl: 100 } },
    });
    const { container } = render(<MemoryBoard />);
    expect(container.querySelectorAll('[data-tag="predicted"]')).toHaveLength(2); // lamp + legend swatch
    expect(container.querySelectorAll('[data-tag="partial"]')).toHaveLength(2);
    expect(screen.getByText("2 / 5")).toBeInTheDocument();
    expect(screen.getByTitle("Fee Schedule: predicted, used 2 times")).toBeInTheDocument();
    expect(screen.getByTitle("Debit Cards: not in memory")).toBeInTheDocument();
  });

  it("pulses the pages used by the latest answer", () => {
    useCallStore.setState({ ready: ready(), pulse: { ids: ["cards.md:0"], nonce: 3 } });
    const { container } = render(<MemoryBoard />);
    expect(container.querySelectorAll('[data-used="true"]')).toHaveLength(1);
  });

  it("groups background pages separately and shows rows per document", () => {
    useCallStore.setState({ ready: ready() });
    render(<MemoryBoard />);
    expect(screen.getByText(/Background pages \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("Fee Schedule")).toBeInTheDocument();
  });

  it("shows hit and wait counters from the latest finished turn", () => {
    useCallStore.setState({
      ready: ready(),
      turns: [{ id: 1, question: "q", via: "text", answer: "a", pending: false, voice: null, at: 0,
        result: { stats: { turns: 4, hits: 3, drafts: 1, corrected: 0, avg_user_ms: 912 } } as never }],
    });
    render(<MemoryBoard />);
    expect(screen.getByText("3/4")).toBeInTheDocument();
    expect(screen.getByText("912 ms")).toBeInTheDocument();
  });

  it("says the baseline has no memory", () => {
    useCallStore.setState({ ready: ready({ profile: { key: "baseline", label: "Traditional RAG", cache: false } }) });
    render(<MemoryBoard />);
    expect(screen.getByText(/no memory, so the board stays dark/)).toBeInTheDocument();
  });

  it("shows a connecting message before the first ready", () => {
    render(<MemoryBoard />);
    expect(screen.getByText(/Connecting to the knowledge base/)).toBeInTheDocument();
  });
});

describe("describeConfig", () => {
  it("names the strategy, drafts, verification and engines", () => {
    const t = describeConfig(ready());
    expect(t).toContain("GPT + nearby pages");
    expect(t).toContain("pre-drafted answers");
    expect(t).toContain("checked against the database");
    expect(t).toContain("Strictness 0.6");
  });
  it("describes the no-memory baseline in one sentence", () => {
    expect(describeConfig(ready({ llm: "extractive", profile: { key: "baseline", label: "Traditional RAG", cache: false } })))
      .toBe("Traditional RAG: every question goes to the database. No memory, no prediction. Answers by the offline stand-in.");
  });
});

describe("LedgerPanel", () => {
  it("invites the user to act when empty", () => {
    render(<LedgerPanel />);
    expect(screen.getByText(/Ask a question to watch it work/)).toBeInTheDocument();
  });
  it("lists entries newest first with a clock and predicted questions", () => {
    useCallStore.setState({ ledger: [
      { id: 2, at: 9000, kind: "predicted", text: "Expecting you to ask next", items: ["Is there a discount?"] },
      { id: 1, at: 1000, kind: "direct", text: "Heard “fees”" },
    ] });
    render(<LedgerPanel />);
    const items = screen.getAllByRole("listitem").filter((li) => li.className.includes("item"));
    expect(within(items[0]!).getByText("0:09")).toBeInTheDocument();
    expect(within(items[0]!).getByText("Is there a discount?")).toBeInTheDocument();
    expect(within(items[1]!).getByText("0:01")).toBeInTheDocument();
  });
});
