import type { ButtonHTMLAttributes } from "react";
import { Icon, type IconName } from "./Icon";
import styles from "./IconButton.module.css";

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: IconName;
  /** Required: an icon-only button must have an accessible name. */
  label: string;
  variant?: "light" | "dark" | "ghost";
  size?: number;
  pressed?: boolean;
}

export function IconButton({ icon, label, variant = "light", size = 44, pressed, className, style, ...rest }: Props) {
  return (
    <button
      type="button" aria-label={label} title={label} aria-pressed={pressed}
      className={[styles.btn, styles[variant], className].filter(Boolean).join(" ")}
      style={{ width: size, height: size, ...style }}
      {...rest}
    >
      <Icon name={icon} size={Math.round(size * 0.5)} />
    </button>
  );
}
