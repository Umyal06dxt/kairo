import { DEFAULT_SETTINGS, useSettingsStore } from "./settingsStore";

describe("settings store", () => {
  beforeEach(() => { localStorage.clear(); useSettingsStore.setState({ settings: DEFAULT_SETTINGS }); });

  it("updates one field without losing the others", () => {
    useSettingsStore.getState().update({ profile: "paper" });
    expect(useSettingsStore.getState().settings).toEqual({ ...DEFAULT_SETTINGS, profile: "paper" });
  });
  it("persists to localStorage", () => {
    useSettingsStore.getState().update({ speak: true });
    expect(localStorage.getItem("kairo.settings.v2")).toContain('"speak":true');
  });
  it("defaults the memory strictness to the embedder's own default", () => {
    expect(DEFAULT_SETTINGS.tau).toBeNull();
  });
});
