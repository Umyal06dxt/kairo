import { create } from "zustand";
import { fetchInfo } from "@/api/rest";
import type { Info } from "@/api/types";

interface InfoStore {
  info: Info | null;
  error: string | null;
  load: () => Promise<void>;
}

export const useInfoStore = create<InfoStore>((set, get) => ({
  info: null,
  error: null,
  load: async () => {
    if (get().info) return;
    try {
      set({ info: await fetchInfo(), error: null });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : "Couldn't reach the server." });
    }
  },
}));
