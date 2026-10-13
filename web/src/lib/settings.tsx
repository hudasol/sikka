import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { applyDocumentLanguage, readStored, writeStored } from "../i18n";
import type { Language } from "../i18n";
import type { FormatSettings } from "./format";

type Theme = "light" | "dark";

interface Settings extends FormatSettings {
  theme: Theme;
  setLang: (lang: Language) => void;
  toggleDigits: () => void;
  toggleTheme: () => void;
}

const SettingsContext = createContext<Settings | null>(null);

function initialTheme(): Theme {
  const stored = readStored("sikka.theme");
  if (stored === "dark" || stored === "light") {
    return stored;
  }
  const prefersDark =
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  return prefersDark ? "dark" : "light";
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation();
  const [lang, setLangState] = useState<Language>(i18n.language === "ar" ? "ar" : "en");
  const [arabicDigits, setArabicDigits] = useState(readStored("sikka.digits") === "arab");
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setLang = useCallback(
    (next: Language) => {
      setLangState(next);
      writeStored("sikka.lang", next);
      void i18n.changeLanguage(next);
      applyDocumentLanguage(next);
    },
    [i18n],
  );

  const value = useMemo<Settings>(
    () => ({
      lang,
      arabicDigits,
      theme,
      setLang,
      toggleDigits: () =>
        setArabicDigits((on) => {
          writeStored("sikka.digits", on ? "latn" : "arab");
          return !on;
        }),
      toggleTheme: () =>
        setTheme((t) => {
          const next = t === "dark" ? "light" : "dark";
          writeStored("sikka.theme", next);
          return next;
        }),
    }),
    [lang, arabicDigits, theme, setLang],
  );
  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): Settings {
  const value = useContext(SettingsContext);
  if (value === null) {
    throw new Error("useSettings must be used inside SettingsProvider");
  }
  return value;
}
