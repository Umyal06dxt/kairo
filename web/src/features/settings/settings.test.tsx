import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useInfoStore } from "@/state/infoStore";
import { DEFAULT_SETTINGS, useSettingsStore } from "@/state/settingsStore";
import { describeProfile } from "./profileBlurb";
import { SettingsSheet } from "./SettingsSheet";

const session = vi.hoisted(() => ({ hello: vi.fn() }));
vi.mock("@/api/session", () => ({ getSession: () => session }));

const info = {
  has_key: true, stt: "ready" as const,
  domains: [{ key: "bank", title: "Credit union", blurb: "" }, { key: "novacrm", title: "NovaCRM", blurb: "" }],
  profiles: [
    { key: "baseline", label: "Traditional RAG", cache: false, strategy: "none", verify: false, drafts: false },
    { key: "optimized", label: "Kairo optimized", cache: true, strategy: "hybrid", verify: true, drafts: true },
  ],
};

beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear();
  useSettingsStore.setState({ settings: DEFAULT_SETTINGS });
  useInfoStore.setState({ info, error: null });
});

describe("describeProfile", () => {
  it("describes each way of running in one plain line", () => {
    expect(describeProfile(info.profiles[0]!)).toBe("Every question goes to the database. The comparison point.");
    expect(describeProfile(info.profiles[1]!)).toBe("GPT plus nearby pages, pre-drafts answers, verifies hits.");
  });
});

describe("SettingsSheet", () => {
  it("applies the chosen settings and starts a new call", async () => {
    render(<SettingsSheet open onClose={vi.fn()} />);
    await userEvent.selectOptions(screen.getByLabelText("Knowledge base"), "novacrm");
    await userEvent.click(screen.getByLabelText(/Traditional RAG/));
    await userEvent.click(screen.getByLabelText(/Speak answers aloud/));
    await userEvent.click(screen.getByRole("button", { name: "Start new call" }));
    expect(useSettingsStore.getState().settings).toMatchObject({ domain: "novacrm", profile: "baseline", speak: true, tau: null });
    expect(session.hello).toHaveBeenCalledOnce();
  });

  it("keeps the embedder's default strictness unless the user overrides it", async () => {
    render(<SettingsSheet open onClose={vi.fn()} />);
    const slider = screen.getByLabelText("Memory strictness");
    expect(slider).toBeDisabled(); // default in use
    await userEvent.click(screen.getByLabelText(/Use the right default/));
    expect(slider).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Start new call" }));
    expect(useSettingsStore.getState().settings.tau).toBe(0.6);
  });

  it("cancel changes nothing and does not restart the call", async () => {
    const onClose = vi.fn();
    render(<SettingsSheet open onClose={onClose} />);
    await userEvent.click(screen.getByLabelText(/Speak answers aloud/));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onClose).toHaveBeenCalled();
    expect(useSettingsStore.getState().settings.speak).toBe(false);
    expect(session.hello).not.toHaveBeenCalled();
  });

  it("starts from the saved settings each time it opens", () => {
    useSettingsStore.setState({ settings: { ...DEFAULT_SETTINGS, store_latency_ms: 250, tau: 0.7 } });
    render(<SettingsSheet open onClose={vi.fn()} />);
    expect(screen.getByLabelText("Database delay")).toHaveValue("250");
    expect(screen.getByLabelText("Memory strictness")).toHaveValue("0.7");
  });
});
