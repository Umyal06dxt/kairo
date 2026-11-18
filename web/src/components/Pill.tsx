import type { ButtonHTMLAttributes } from "react";
import styles from "./Pill.module.css";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> { active?: boolean }

export function Pill({ active, className, children, ...rest }: Props) {
  return (
    <button
      type="button" aria-pressed={active}
      className={[styles.pill, active && styles.active, className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </button>
  );
}
