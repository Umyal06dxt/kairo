/** Geometry for the wireframe orb. Kept pure so it can be tested without a canvas. */

export interface OrbParams {
  ring: number;       // 0..rings-1
  rings: number;
  theta: number;      // radians around the ring
  t: number;          // seconds
  level: number;      // 0..1 voice level
}

/** Radius (as a fraction of the orb radius) of one point on one ring. */
export function orbRadius({ ring, rings, theta, t, level }: OrbParams): number {
  const k = ring / Math.max(1, rings - 1);
  const swell = 0.16 + level * 0.1;
  // Amplitudes are chosen so the radius always stays within [0.10, 0.94] of the orb radius,
  // even at full voice level: 0.52 +/- (0.26 + 0.08 + 0.08).
  return (
    0.52 +
    swell * Math.sin(3 * theta + t * 0.9 + k * 2.2) +
    0.08 * Math.sin(5 * theta - t * 1.3 + k * 3.1) +
    level * 0.08 * Math.sin(7 * theta + t * 3.4 + k * 4)
  );
}

/** Purple to orange across the rings, as in the reference. Returns an rgba() string. */
export function ringColor(ring: number, rings: number, alpha = 0.55): string {
  const k = ring / Math.max(1, rings - 1);
  const lerp = (a: number, b: number) => Math.round(a + (b - a) * k);
  return `rgba(${lerp(139, 242)}, ${lerp(107, 154)}, ${lerp(232, 85)}, ${alpha})`;
}

/** Smooth a level toward a target (attack fast, release slow) so the orb breathes, not flickers. */
export function smoothLevel(prev: number, target: number): number {
  const rate = target > prev ? 0.35 : 0.08;
  return prev + (target - prev) * rate;
}

/** RMS of time-domain samples (0..255 centred on 128, as AnalyserNode.getByteTimeDomainData gives). */
export function rmsLevel(samples: ArrayLike<number>): number {
  if (!samples.length) return 0;
  let sum = 0;
  for (let i = 0; i < samples.length; i++) {
    const v = (samples[i]! - 128) / 128;
    sum += v * v;
  }
  return Math.min(1, Math.sqrt(sum / samples.length) * 3.2);
}
