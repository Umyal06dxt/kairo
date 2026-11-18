import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Settings } from "@/api/types";

export const DEFAULT_SETTINGS: Settings = {
  domain: "bank", profile: "optimized", embedder: "local", llm: "auto",
  distractors: true, tau: null, store_latency_ms: 110, speak: false,
};

interface SettingsStore {
  settings: Settings;
  update: (patch: Partial<Settings>) => void;
  replace: (s: Settings) => void;
}

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      update: (patch) => set({ settings: { ...get().settings, ...patch } }),
      replace: (settings) => set({ settings }),
    }),
    { name: "kairo.settings.v2", version: 1, merge: (persisted, current) => ({
        ...current,
        // never trust stored shape: fill any missing field from defaults
        settings: { ...DEFAULT_SETTINGS, ...((persisted as Partial<SettingsStore> | undefined)?.settings ?? {}) },
      }) },
  ),
);
