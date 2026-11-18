import { useEffect, useRef, type ReactNode } from "react";
import { IconButton } from "./IconButton";
import styles from "./Sheet.module.css";

interface Props { open: boolean; title: string; onClose: () => void; children: ReactNode }

/** Modal sheet on the native <dialog>: focus is trapped and Escape closes it without extra code. */
export function Sheet({ open, title, onClose, children }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) (d.showModal ? d.showModal() : d.setAttribute("open", ""));
    if (!open && d.open) (d.close ? d.close() : d.removeAttribute("open"));
  }, [open]);

  return (
    <dialog ref={ref} className={styles.sheet} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()} aria-label={title}>
      {open && (
        <div className={styles.panel}>
          <div className={styles.top}>
            <h2>{title}</h2>
            <IconButton icon="close" label="Close" onClick={onClose} size={38} />
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}
