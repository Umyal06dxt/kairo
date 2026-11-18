import { orbRadius, ringColor, rmsLevel, smoothLevel } from "./orbMath";

describe("orb math", () => {
  it("keeps the radius inside the canvas for every ring, angle and level", () => {
    for (let ring = 0; ring < 40; ring += 7)
      for (let a = 0; a < 6.3; a += 0.4)
        for (const level of [0, 0.5, 1]) {
          const r = orbRadius({ ring, rings: 40, theta: a, t: 12.3, level });
          expect(r).toBeGreaterThanOrEqual(0.1 - 1e-9);
          expect(r).toBeLessThanOrEqual(0.94 + 1e-9); // never clips the canvas, even at full level
        }
  });
  it("swells more when the voice is louder", () => {
    const amp = (level: number) => {
      let lo = 9, hi = -9;
      for (let a = 0; a < 6.3; a += 0.05) {
        const r = orbRadius({ ring: 3, rings: 40, theta: a, t: 1, level });
        lo = Math.min(lo, r); hi = Math.max(hi, r);
      }
      return hi - lo;
    };
    expect(amp(1)).toBeGreaterThan(amp(0));
  });
  it("blends purple into orange", () => {
    expect(ringColor(0, 10)).toBe("rgba(139, 107, 232, 0.55)");
    expect(ringColor(9, 10)).toBe("rgba(242, 154, 85, 0.55)");
    expect(ringColor(0, 1)).toBe("rgba(139, 107, 232, 0.55)"); // single ring: no divide by zero
  });
  it("attacks faster than it releases", () => {
    expect(smoothLevel(0, 1)).toBeGreaterThan(1 - smoothLevel(1, 0));
  });
  it("measures silence as zero and a full-scale tone as loud", () => {
    expect(rmsLevel(new Uint8Array(256).fill(128))).toBe(0);
    expect(rmsLevel([])).toBe(0);
    const loud = Uint8Array.from({ length: 256 }, (_, i) => (i % 2 ? 255 : 0));
    expect(rmsLevel(loud)).toBe(1);
  });
});
