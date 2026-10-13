import { formatInterval, formatNumber, formatPercent } from "./format";

describe("number formatting", () => {
  it("uses Latin digits by default in both languages", () => {
    expect(formatNumber(1234, { lang: "en", arabicDigits: false })).toBe("1,234");
    expect(formatNumber(12, { lang: "ar", arabicDigits: false })).toBe("12");
  });

  it("switches to Arabic Indic digits on request", () => {
    const out = formatNumber(12, { lang: "ar", arabicDigits: true });
    expect(out).toBe("١٢");
  });

  it("formats shares and intervals as percent", () => {
    const s = { lang: "en" as const, arabicDigits: false };
    expect(formatPercent(0.1234, s)).toBe("12.3 %");
    expect(formatInterval(0.1, 0.2, s)).toBe("10.0 to 20.0 %");
    expect(formatInterval(0.1, 0.2, { lang: "ar", arabicDigits: false })).toContain(" إلى ");
  });
});
