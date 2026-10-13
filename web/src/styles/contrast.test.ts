import { CONTRAST_PAIRS, THEMES, contrastRatio, themeCss } from "./tokens";

describe("colour contrast (WCAG 2.2 AA)", () => {
  for (const theme of ["light", "dark"] as const) {
    for (const [fg, bg, role] of CONTRAST_PAIRS) {
      const need = role === "text" ? 4.5 : 3;
      it(`${theme}: ${fg} on ${bg} is at least ${need}:1 (${role})`, () => {
        const ratio = contrastRatio(THEMES[theme][fg], THEMES[theme][bg]);
        expect(ratio).toBeGreaterThanOrEqual(need);
      });
    }
  }

  it("keeps the brief's palette and notes the accent is decorative", () => {
    expect(THEMES.light.bg).toBe("#fdf8f5");
    expect(THEMES.light.surface).toBe("#fbe3ea");
    expect(THEMES.light.pink).toBe("#f7b6c8");
    expect(THEMES.light.accent).toBe("#d9728f");
    expect(THEMES.light.ink).toBe("#5b3a4a");
    expect(THEMES.light.muted).toBe("#a8788a");
    expect(contrastRatio(THEMES.light.accent, THEMES.light.bg)).toBeLessThan(4.5);
  });

  it("knows reference ratios", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#777777", "#ffffff")).toBeCloseTo(4.48, 2);
  });

  it("emits light, system dark and forced dark variables", () => {
    const css = themeCss();
    expect(css).toContain("--accent-strong:#a8456a");
    expect(css).toContain("prefers-color-scheme: dark");
    expect(css).toContain(':root[data-theme="dark"]');
  });
});
