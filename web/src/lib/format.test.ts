import { bestIndex, clock, fmtMs, fmtPct, truncate } from "./format";

describe("format", () => {
  it("formats milliseconds with sensible precision", () => {
    expect(fmtMs(0.36)).toBe("0.4 ms");
    expect(fmtMs(42.4)).toBe("42 ms");
    expect(fmtMs(1067.2)).toBe("1,067 ms");
    expect(fmtMs(null)).toBe("–");
    expect(fmtMs(Number.NaN)).toBe("–");
  });
  it("formats percentages and clocks", () => {
    expect(fmtPct(0.954)).toBe("95%");
    expect(fmtPct(undefined)).toBe("–");
    expect(clock(65_000)).toBe("1:05");
    expect(clock(-5)).toBe("0:00");
  });
  it("truncates with an ellipsis", () => {
    expect(truncate("abcdef", 4)).toBe("abc…");
    expect(truncate("abc", 4)).toBe("abc");
  });
});

describe("bestIndex", () => {
  it("only names a winner when the margin is clear", () => {
    expect(bestIndex([0.97, 0.95, 0.9], true, true)).toBe(-1); // 2 points: noise
    expect(bestIndex([0.97, 0.9, 0.85], true, true)).toBe(0);
    expect(bestIndex([401, 403, 528], false, false)).toBe(-1); // 0.5%: noise
    expect(bestIndex([528, 406, 520], false, false)).toBe(1);
  });
  it("ignores missing values and needs two to compare", () => {
    expect(bestIndex([null, 0.9], true, true)).toBe(-1);
    expect(bestIndex([null, 0.9, 0.5], true, true)).toBe(1);
  });
});
