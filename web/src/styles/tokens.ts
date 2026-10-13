// Design tokens: pearl and sakura (light) and deep plum (dark).
// The brief's pastel accent (#d9728f) fails text contrast, so it is used for
// decoration only; darker derived tones carry text, links and graphics.
// `contrast.test.ts` proves every pair listed in CONTRAST_PAIRS.

export type ThemeName = "light" | "dark";

export interface Tokens {
  bg: string;
  surface: string;
  raised: string;
  pink: string;
  accent: string;
  accentStrong: string;
  ink: string;
  text: string;
  mutedText: string;
  muted: string;
  link: string;
  focus: string;
  error: string;
  warning: string;
  info: string;
  ok: string;
}

export const THEMES: Record<ThemeName, Tokens> = {
  light: {
    bg: "#fdf8f5",
    surface: "#fbe3ea",
    raised: "#ffffff",
    pink: "#f7b6c8",
    accent: "#d9728f",
    accentStrong: "#a8456a",
    ink: "#5b3a4a",
    text: "#3d2632",
    mutedText: "#6e4f5d",
    muted: "#a8788a",
    link: "#8e3553",
    focus: "#7a3a52",
    error: "#8e2340",
    warning: "#7a4a12",
    info: "#3f4f7a",
    ok: "#2f5e3a",
  },
  dark: {
    bg: "#24131d",
    surface: "#341c2a",
    raised: "#432537",
    pink: "#7a3a52",
    accent: "#d9728f",
    accentStrong: "#ee93b0",
    ink: "#f3d6e0",
    text: "#fbe3ea",
    mutedText: "#d9a3b6",
    muted: "#a8788a",
    link: "#f7b6c8",
    focus: "#fbe3ea",
    error: "#ffb3c1",
    warning: "#f5c98a",
    info: "#b9c6f0",
    ok: "#a8dcb3",
  },
};

export type Role = "text" | "graphic";

// [foreground token, background token, role]. Text needs 4.5:1, graphics 3:1.
export const CONTRAST_PAIRS: [keyof Tokens, keyof Tokens, Role][] = [
  ["text", "bg", "text"],
  ["text", "surface", "text"],
  ["text", "raised", "text"],
  ["ink", "bg", "text"],
  ["ink", "surface", "text"],
  ["ink", "raised", "text"],
  ["mutedText", "bg", "text"],
  ["mutedText", "surface", "text"],
  ["mutedText", "raised", "text"],
  ["link", "bg", "text"],
  ["link", "surface", "text"],
  ["link", "raised", "text"],
  ["error", "raised", "text"],
  ["warning", "raised", "text"],
  ["info", "raised", "text"],
  ["ok", "raised", "text"],
  ["error", "surface", "text"],
  ["warning", "surface", "text"],
  ["info", "surface", "text"],
  ["ok", "surface", "text"],
  ["accentStrong", "bg", "graphic"],
  ["accentStrong", "surface", "graphic"],
  ["accentStrong", "raised", "graphic"],
  ["focus", "bg", "graphic"],
  ["focus", "surface", "graphic"],
  ["focus", "raised", "graphic"],
  ["ink", "pink", "text"],
  ["text", "pink", "text"],
];

function channel(value: number): number {
  const v = value / 255;
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const n = hex.replace("#", "");
  const r = channel(parseInt(n.slice(0, 2), 16));
  const g = channel(parseInt(n.slice(2, 4), 16));
  const b = channel(parseInt(n.slice(4, 6), 16));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(a: string, b: string): number {
  const la = luminance(a);
  const lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

export function themeCss(): string {
  const toVars = (t: Tokens) =>
    Object.entries(t)
      .map(([k, v]) => `--${k.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase())}:${v};`)
      .join("");
  return [
    `:root{${toVars(THEMES.light)}color-scheme:light;}`,
    `@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){${toVars(THEMES.dark)}color-scheme:dark;}}`,
    `:root[data-theme="dark"]{${toVars(THEMES.dark)}color-scheme:dark;}`,
  ].join("\n");
}
