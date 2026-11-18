import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ProfileInfo } from "@/api/types";
import { experiment, summary } from "@/test/fixtures";
import { ExperimentsPage } from "./ExperimentsPage";
import { ResultsView } from "./ResultsView";
import { RunForm } from "./RunForm";
import { SweepChart } from "./charts";

const rest = vi.hoisted(() => ({
  fetchExperiments: vi.fn(), startExperiment: vi.fn(), fetchInfo: vi.fn(),
}));
vi.mock("@/api/rest", () => rest);

const profiles: ProfileInfo[] = [
  { key: "baseline", label: "Traditional RAG", cache: false, strategy: "none", verify: false, drafts: false },
  { key: "paper", label: "VoiceAgentRAG", cache: true, strategy: "llm", verify: false, drafts: false },
  { key: "optimized", label: "Kairo optimized", cache: true, strategy: "hybrid", verify: true, drafts: true },
];

describe("RunForm", () => {
  const setup = (over: Partial<React.ComponentProps<typeof RunForm>> = {}) => {
    const onRun = vi.fn();
    render(<RunForm profiles={profiles} running={null} message="" busy={false} onRun={onRun} {...over} />);
    return onRun;
  };

  it("submits the default offline comparison without asking for confirmation", async () => {
    const confirmFn = vi.fn();
    const onRun = setup({ confirmFn });
    await userEvent.click(screen.getByRole("button", { name: "Run experiment" }));
    expect(confirmFn).not.toHaveBeenCalled(); // free: on-device embeddings, offline answers
    expect(onRun).toHaveBeenCalledWith({
      domain: "bank", profiles: ["baseline", "paper", "optimized"], embedder: "local", llm: "extractive",
      sweep: "", distractors: 64, confirm: false,
    });
  });

  it("asks before spending API credit and does not run if declined", async () => {
    const confirmFn = vi.fn().mockReturnValue(false);
    const onRun = setup({ confirmFn });
    await userEvent.selectOptions(screen.getByLabelText("Answers"), "openai");
    await userEvent.click(screen.getByRole("button", { name: "Run experiment" }));
    expect(confirmFn).toHaveBeenCalledWith(expect.stringContaining("costs a few cents"));
    expect(onRun).not.toHaveBeenCalled();
  });

  it("passes confirm=true once the user agrees to a live run", async () => {
    const onRun = setup({ confirmFn: () => true });
    await userEvent.selectOptions(screen.getByLabelText("Embeddings"), "openai");
    await userEvent.click(screen.getByRole("button", { name: "Run experiment" }));
    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ embedder: "openai", confirm: true }));
  });

  it("cannot run with no strategy selected, or while another run is in flight", async () => {
    setup();
    for (const p of ["Traditional RAG", "VoiceAgentRAG", "Kairo optimized"])
      await userEvent.click(screen.getByLabelText(new RegExp(p)));
    expect(screen.getByRole("button", { name: "Run experiment" })).toBeDisabled();
  });

  it("disables running while busy and shows live progress", () => {
    setup({ busy: true, running: { id: "r", state: "running", progress: ["running Traditional RAG"] } });
    expect(screen.getByRole("button", { name: "Run experiment" })).toBeDisabled();
    expect(screen.getByText("running Traditional RAG")).toBeInTheDocument();
  });

  it("drops the background pages for the NovaCRM knowledge base", async () => {
    const onRun = setup();
    await userEvent.click(screen.getByLabelText(/NovaCRM, as in the paper/));
    await userEvent.click(screen.getByRole("button", { name: "Run experiment" }));
    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ domain: "novacrm", distractors: 0 }));
  });

  it("only offers memory strategies for the threshold sweep", () => {
    setup();
    const opts = within(screen.getByLabelText("Threshold sweep")).getAllByRole("option").map((o) => o.textContent);
    expect(opts).toEqual(["None", "VoiceAgentRAG", "Kairo optimized"]);
  });
});

describe("ResultsView", () => {
  it("marks a clear winner but not a within-noise difference, per column", () => {
    const r = experiment("a");
    r.profiles.baseline!.summary = summary({ accuracy: 0.95, evidence: 0.97, user_p50: 1067 });
    r.profiles.optimized!.summary = summary({ accuracy: 0.97, evidence: 0.9, user_p50: 950 });
    render(<ResultsView result={r} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    const cellsOf = (col: string) => {
      const i = headers.indexOf(col);
      return screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[i]!);
    };
    const winners = (col: string) => cellsOf(col).filter((c) => c.classList.contains("best")).map((c) => c.textContent);
    expect(winners("Right page")).toEqual(["97%"]); // 97 vs 90: a clear 7-point gap
    expect(winners("Answer correct")).toEqual([]); // 95 vs 97: two points is noise
    expect(winners("Wait p50")).toEqual(["950 ms"]); // 12% faster: clear
  });

  it("renders the notes, the table and the wait chart", () => {
    render(<ResultsView result={experiment("a")} />);
    expect(screen.getByText("157 chunks indexed")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Right page" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Wait before the first word/ })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /against the threshold/ })).toBeNull(); // no sweep data
  });

  it("shows the threshold sweep only when it has data and handles missing values", () => {
    const r = experiment("a");
    r.sweep = [0.5, 0.6, 0.7].map((tau, i) => ({ tau, summary: summary({ hit_rate: 1 - i * 0.3, fidelity: i ? 0.8 : null }) }));
    render(<ResultsView result={r} />);
    expect(screen.getByRole("img", { name: /against the threshold/ })).toBeInTheDocument();
    expect(screen.getByText("Memory strictness: more hits or better hits?")).toBeInTheDocument();
  });

  it("renders dashes where a metric was not measured", () => {
    const r = experiment("a", "embedder=local, llm=extractive");
    r.profiles.baseline!.summary = summary({ accuracy: null, fidelity: null });
    render(<ResultsView result={r} />);
    expect(screen.getAllByText("–").length).toBeGreaterThanOrEqual(2);
  });
});

describe("SweepChart", () => {
  it("needs at least two points to draw a line", () => {
    const { container } = render(<SweepChart points={[{ tau: 0.5, summary: summary() }]} />);
    expect(container.querySelector("svg")).toBeNull();
  });
});

describe("ExperimentsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    rest.fetchInfo.mockResolvedValue({ has_key: true, stt: "ready", domains: [], profiles });
  });

  it("shows an empty state, then a saved run once one exists", async () => {
    rest.fetchExperiments.mockResolvedValue({ saved: [], current: null });
    const { unmount } = render(<ExperimentsPage />);
    expect(await screen.findByText(/No runs yet/)).toBeInTheDocument();
    unmount();

    rest.fetchExperiments.mockResolvedValue({ saved: [experiment("r1"), experiment("r2", "embedder=local, llm=extractive")], current: null });
    render(<ExperimentsPage />);
    expect(await screen.findByRole("combobox", { name: "Results" })).toHaveValue("r1");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Results" }), "r2");
    expect(await screen.findByText(/llm=extractive\./)).toBeInTheDocument();
  });

  it("starts a run and surfaces a server-side refusal", async () => {
    rest.fetchExperiments.mockResolvedValue({ saved: [], current: null });
    rest.startExperiment.mockRejectedValue(new Error("An experiment is already running."));
    render(<ExperimentsPage />);
    await screen.findByText(/No runs yet/);
    await userEvent.click(await screen.findByRole("button", { name: "Run experiment" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("An experiment is already running."));
  });
});
