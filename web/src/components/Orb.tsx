import { useEffect, useRef } from "react";
import { orbRadius, ringColor, smoothLevel } from "@/lib/orbMath";
import styles from "./Orb.module.css";

interface Props {
  /** Live voice level 0..1. */
  level?: number;
  size?: number;
  rings?: number;
  /** Slower, calmer motion when the assistant is thinking or idle. */
  calm?: boolean;
}

const prefersReducedMotion = (): boolean =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Wireframe orb: stacked wobbling rings that shade from purple to orange and swell with the voice. */
export function Orb({ level = 0, size = 280, rings = 46, calm = false }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const levelRef = useRef(level);
  levelRef.current = level;

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext?.("2d");
    if (!el || !ctx) return; // jsdom / very old browsers: the glow behind still renders
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    el.width = size * dpr;
    el.height = size * dpr;
    ctx.scale(dpr, dpr);

    let raf = 0;
    let smooth = 0;
    const start = performance.now();
    const still = prefersReducedMotion();
    const R = size / 2 - 6;

    const frame = (now: number) => {
      const t = ((now - start) / 1000) * (calm ? 0.45 : 1);
      smooth = smoothLevel(smooth, calm ? 0.05 : levelRef.current);
      ctx.clearRect(0, 0, size, size);
      ctx.lineWidth = 0.8;
      for (let ring = 0; ring < rings; ring++) {
        ctx.beginPath();
        const tilt = ring * 0.07 + t * 0.12;
        for (let i = 0; i <= 120; i++) {
          const theta = (i / 120) * Math.PI * 2;
          const r = orbRadius({ ring, rings, theta, t, level: smooth }) * R;
          const x = Math.cos(theta + tilt) * r;
          const y = Math.sin(theta + tilt) * r * (0.82 + 0.18 * Math.sin(ring * 0.2 + t * 0.4));
          if (i === 0) ctx.moveTo(size / 2 + x, size / 2 + y);
          else ctx.lineTo(size / 2 + x, size / 2 + y);
        }
        ctx.closePath();
        ctx.strokeStyle = ringColor(ring, rings, 0.5);
        ctx.stroke();
      }
      if (!still) raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [size, rings, calm]);

  return (
    <div className={styles.wrap} style={{ width: size, height: size }} data-testid="orb">
      <div className={styles.glow} />
      <canvas ref={canvas} className={styles.canvas} role="img" aria-label="Voice activity" />
    </div>
  );
}
