import { Link } from "react-router-dom";
import { Icon, type IconName } from "@/components/Icon";
import { Sheet } from "@/components/Sheet";
import styles from "./MenuSheet.module.css";

interface Props { open: boolean; onClose: () => void; onSettings: () => void }

const ITEMS: { to: string; icon: IconName; title: string; sub: string }[] = [
  { to: "/experiments", icon: "chart", title: "Experiments", sub: "Compare strategies on scripted calls" },
  { to: "/research", icon: "book", title: "Research", sub: "What was measured and what is open" },
];

export function MenuSheet({ open, onClose, onSettings }: Props) {
  return (
    <Sheet open={open} title="Menu" onClose={onClose}>
      <ul className={styles.list}>
        {ITEMS.map((i) => (
          <li key={i.to}>
            <Link to={i.to} className={styles.link} onClick={onClose}>
              <span className={styles.icon}><Icon name={i.icon} /></span>
              <span>{i.title}<small>{i.sub}</small></span>
            </Link>
          </li>
        ))}
        <li>
          <button type="button" className={styles.link} onClick={() => { onClose(); onSettings(); }}>
            <span className={styles.icon}><Icon name="settings" /></span>
            <span>Call settings<small>Knowledge base, strategy, engines</small></span>
          </button>
        </li>
      </ul>
    </Sheet>
  );
}
