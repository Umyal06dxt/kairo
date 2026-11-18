import { IconButton } from "./IconButton";
import styles from "./ScreenHeader.module.css";

interface Props {
  title: string;
  subtitle?: string;
  onBack?: () => void;
  onMenu?: () => void;
}

export function ScreenHeader({ title, subtitle, onBack, onMenu }: Props) {
  return (
    <header className={styles.head}>
      {onBack ? <IconButton icon="back" label="Back" onClick={onBack} /> : <span className={styles.spacer} />}
      <div className={styles.mid}>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.sub}>{subtitle}</p>
      </div>
      {onMenu ? <IconButton icon="menu" label="Menu" onClick={onMenu} /> : <span className={styles.spacer} />}
    </header>
  );
}
