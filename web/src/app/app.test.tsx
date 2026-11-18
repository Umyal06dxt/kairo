import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { initialCallState, useCallStore } from "@/state/callStore";
import { useInfoStore } from "@/state/infoStore";
import { experiment, ready } from "@/test/fixtures";
import { AppRoutes } from "./routes";

const mocks = vi.hoisted(() => ({
  session: { say: vi.fn(() => true), partial: vi.fn(), playScenario: vi.fn(), stopScenario: vi.fn(), sendAudio: vi.fn(), unlockAudio: vi.fn(), hello: vi.fn(), start: vi.fn(), stop: vi.fn() },
  rest: { fetchExperiments: vi.fn(), startExperiment: vi.fn(), fetchInfo: vi.fn() },
}));
vi.mock("@/api/session", () => ({ getSession: () => mocks.session }));
vi.mock("@/api/rest", () => mocks.rest);

const at = (path: string) => render(<MemoryRouter initialEntries={[path]}><AppRoutes /></MemoryRouter>);

beforeEach(() => {
  vi.clearAllMocks();
  useCallStore.setState({ ...initialCallState, ready: ready() });
  useInfoStore.setState({ info: { has_key: true, stt: "ready", domains: [{ key: "bank", title: "Credit union", blurb: "" }], profiles: [] }, error: null });
  mocks.rest.fetchExperiments.mockResolvedValue({ saved: [experiment("live-full", "embedder=local, llm=openai", ["baseline", "paper", "fast", "optimized"])], current: null });
});

describe("routes", () => {
  it("home shows the hero and keeps the live board beside it", () => {
    at("/");
    expect(screen.getByText(/Ask out loud/)).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Live memory board" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });

  it("the dock navigates between home, conversation and the memory board", async () => {
    at("/");
    await userEvent.click(screen.getByRole("link", { name: "Conversation" }));
    expect(await screen.findByText("No questions yet")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Memory board" }));
    expect(await screen.findByText("What is ready before you ask")).toBeInTheDocument();
  });

  it("the menu reaches experiments and research as wide pages without the dock", async () => {
    at("/");
    await userEvent.click(screen.getByRole("button", { name: "Menu" }));
    const menu = screen.getByRole("dialog", { name: "Menu" });
    await userEvent.click(within(menu).getByRole("link", { name: /Experiments/ }));
    expect(await screen.findByText("Compare strategies")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "Main" })).toBeNull();
    await userEvent.click(screen.getByRole("link", { name: "Research" }));
    expect(await screen.findByText("Where this could go")).toBeInTheDocument();
  });

  it("the research page cites numbers from the saved runs", async () => {
    at("/research");
    expect(await screen.findByText(/On 100 scripted calls with GPT answers/)).toBeInTheDocument();
  });

  it("unknown routes fall back to home", () => {
    at("/nope");
    expect(screen.getByText(/Ask out loud/)).toBeInTheDocument();
  });

  it("opens call settings from the dock", async () => {
    at("/");
    await userEvent.click(screen.getByRole("button", { name: "Settings" }));
    expect(await screen.findByRole("button", { name: "Start new call" })).toBeInTheDocument();
  });
});
