// Number formatting for English and Arabic, with optional Arabic Indic digits.

export interface FormatSettings {
  lang: "en" | "ar";
  arabicDigits: boolean;
}

function locale(s: FormatSettings): string {
  const base = s.lang === "ar" ? "ar-AE" : "en-GB";
  return `${base}-u-nu-${s.arabicDigits ? "arab" : "latn"}`;
}

export function formatNumber(value: number, s: FormatSettings, digits = 0): string {
  return new Intl.NumberFormat(locale(s), {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatPercent(share: number, s: FormatSettings, digits = 1): string {
  return `${formatNumber(share * 100, s, digits)} %`;
}

export function formatInterval(low: number, high: number, s: FormatSettings, digits = 1): string {
  const sep = s.lang === "ar" ? " إلى " : " to ";
  return `${formatNumber(low * 100, s, digits)}${sep}${formatNumber(high * 100, s, digits)} %`;
}

export function formatId(value: string): string {
  // Identifiers stay in Latin characters in both languages.
  return value;
}

export function formatYear(value: number | string, s: FormatSettings): string {
  return new Intl.NumberFormat(locale(s), { useGrouping: false }).format(Number(value));
}
