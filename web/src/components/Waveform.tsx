import styles from "./Waveform.module.css";

/** Deterministic pseudo-random bar heights so a voice note looks the same every render. */
export function barHeights(count: number, seed = 7): number[] {
  let s = seed;
  return Array.from({ length: count }, () => {
    s = (s * 9301 + 49297) % 233280;
    return 0.25 + (s / 233280) * 0.75;
  });
}

interface Props {
  bars?: number;
  /** 0..1: how much of the wave is "played" (bars at full opacity). */
  progress?: number;
  /** When set, the wave is live and scales with this level instead of being static. */
  level?: number;
  seed?: number;
  className?: string;
}

export function Waveform({ bars = 34, progress = 0, level, seed = 7, className }: Props) {
  const heights = barHeights(bars, seed);
  return (
    <div className={[styles.wave, className].filter(Boolean).join(" ")} aria-hidden="true">
      {heights.map((h, i) => {
        const live = level == null ? 1 : 0.25 + level * 0.75 * (0.6 + 0.4 * Math.sin(i * 1.7 + level * 9));
        return (
          <i
            key={i}
            className={[styles.bar, i / bars < progress ? styles.done : ""].join(" ")}
            style={{ height: `${Math.round(h * live * 100)}%` }}
          />
        );
      })}
    </div>
  );
}
