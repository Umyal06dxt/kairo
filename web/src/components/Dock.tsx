import { NavLink } from "react-router-dom";
import { Icon, type IconName } from "./Icon";
import styles from "./Dock.module.css";

interface Props { onMic: () => void; onSettings: () => void }

const link = (to: string, icon: IconName, label: string, extra = "") => (
  <NavLink to={to} end aria-label={label} title={label} className={`${styles.item} ${extra}`}>
    <Icon name={icon} />
  </NavLink>
);

/** Bottom navigation with the microphone as the primary action, as in the reference. */
export function Dock({ onMic, onSettings }: Props) {
  return (
    <div className={styles.wrap}>
      <nav className={styles.dock} aria-label="Main">
        {link("/", "home", "Home")}
        {link("/chat", "chat", "Conversation")}
        <button type="button" className={styles.mic} onClick={onMic} aria-label="Start talking" title="Start talking">
          <Icon name="mic" size={30} />
        </button>
        {link("/lab", "lab", "Memory board", styles.narrowOnly)}
        {link("/experiments", "chart", "Experiments", styles.wideOnly)}
        <button type="button" className={styles.item} onClick={onSettings} aria-label="Settings" title="Settings">
          <Icon name="settings" />
        </button>
      </nav>
    </div>
  );
}
