import type { LampTag } from "@/api/types";
import styles from "./Lamp.module.css";

export type LampKind = LampTag | "draft";

interface Props {
  /** Why the page is in memory; undefined = not in memory (lamp off). */
  tag?: LampKind;
  /** Pulse ring: this page was used for the latest answer. */
  used?: boolean;
  size?: number;
  title?: string;
}

export function Lamp({ tag, used, size, title }: Props) {
  const cls = [styles.lamp, tag && styles.on, tag && styles[tag], used && styles.used].filter(Boolean).join(" ");
  return (
    <i
      className={cls} title={title} data-tag={tag ?? "off"} data-used={used ? "true" : undefined}
      style={size ? { width: size, height: size } : undefined}
    />
  );
}

export const LAMP_WORDS: Record<LampKind, string> = {
  direct: "asked directly", predicted: "predicted", neighbor: "nearby page",
  partial: "heard while typing", miss: "fetched after a miss", draft: "pre-drafted answer",
};
