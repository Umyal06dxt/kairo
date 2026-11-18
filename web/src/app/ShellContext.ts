import { createContext, useContext } from "react";

export interface ShellApi { openMenu: () => void; openSettings: () => void }
export const ShellContext = createContext<ShellApi | null>(null);

export function useShell(): ShellApi {
  const v = useContext(ShellContext);
  if (!v) throw new Error("useShell must be used inside <AppShell>");
  return v;
}
