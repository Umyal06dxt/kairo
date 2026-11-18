import { useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { Dock } from "@/components/Dock";
import { LedgerPanel } from "@/features/board/LedgerPanel";
import { MemoryBoard } from "@/features/board/MemoryBoard";
import { ListeningScreen } from "@/features/call/ListeningScreen";
import { VoiceProvider, useVoice } from "@/features/call/VoiceProvider";
import { SettingsSheet } from "@/features/settings/SettingsSheet";
import { MenuSheet } from "./MenuSheet";
import { ShellContext } from "./ShellContext";
import { Icon } from "@/components/Icon";
import styles from "./AppShell.module.css";

const WIDE_ROUTES = ["/experiments", "/research"];

export function AppShell() {
  return (
    <VoiceProvider>
      <ShellFrame />
      <ListeningScreen />
    </VoiceProvider>
  );
}

function ShellFrame() {
  const { pathname } = useLocation();
  const voice = useVoice();
  const [menu, setMenu] = useState(false);
  const [settings, setSettings] = useState(false);
  const api = useMemo(() => ({ openMenu: () => setMenu(true), openSettings: () => setSettings(true) }), []);
  const wide = WIDE_ROUTES.includes(pathname);

  return (
    <ShellContext.Provider value={api}>
      {wide ? (
        <div className={styles.wide}>
          <header className={styles.topbar}>
            <Link to="/" className={styles.brand}><span className={styles.mark}><i /></span>Kairo lab</Link>
            <nav className={styles.tabs} aria-label="Sections">
              <NavLink to="/" end className={styles.tab}>Call</NavLink>
              <NavLink to="/experiments" className={styles.tab}>Experiments</NavLink>
              <NavLink to="/research" className={styles.tab}>Research</NavLink>
            </nav>
            <span className={styles.spacer} />
            <button type="button" className={styles.gear} onClick={api.openSettings} aria-label="Settings"><Icon name="settings" /></button>
          </header>
          <Outlet />
        </div>
      ) : (
        <div className={styles.shell}>
          <main className={styles.phone}>
            <Outlet />
            <Dock onMic={voice.toggle} onSettings={api.openSettings} />
          </main>
          <aside className={styles.lab} aria-label="Live memory board">
            <MemoryBoard />
            <LedgerPanel />
          </aside>
        </div>
      )}
      <MenuSheet open={menu} onClose={() => setMenu(false)} onSettings={api.openSettings} />
      <SettingsSheet open={settings} onClose={() => setSettings(false)} />
    </ShellContext.Provider>
  );
}
