import { NavLink, Outlet } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { MODE } from "../api/client";
import { useSettings } from "../lib/settings";
import { ErrorBoundary } from "./ErrorBoundary";
import { ErrorState } from "./States";

export const SCREENS = [
  { path: "/", key: "overview" },
  { path: "/contract", key: "contract" },
  { path: "/validate", key: "validate" },
  { path: "/conformance", key: "conformance" },
  { path: "/blackspots", key: "blackspots" },
  { path: "/lineage", key: "lineage" },
  { path: "/tasking", key: "tasking" },
  { path: "/method", key: "method" },
  { path: "/pilot", key: "pilot" },
] as const;

export function SyntheticBanner() {
  const { t } = useTranslation();
  // Not dismissible by design: there is no close control.
  return (
    <div className="banner" role="note" data-testid="synthetic-banner">
      {t("banner")}
    </div>
  );
}

export function Layout() {
  const { t } = useTranslation();
  const settings = useSettings();
  return (
    <>
      <a className="skip-link" href="#main">
        {t("skip")}
      </a>
      <SyntheticBanner />
      <header className="topbar">
        <NavLink to="/" className="brand">
          Sikka <span lang="ar">سكّة</span>
          <small>{t("brand_tagline")}</small>
        </NavLink>
        <div className="controls">
          <button
            type="button"
            onClick={() => settings.setLang(settings.lang === "en" ? "ar" : "en")}
            aria-label={t("controls.language_label")}
            lang={settings.lang === "en" ? "ar" : "en"}
          >
            {t("controls.language")}
          </button>
          <button
            type="button"
            onClick={settings.toggleDigits}
            aria-pressed={settings.arabicDigits}
            aria-label={t("controls.digits_label")}
          >
            {settings.arabicDigits ? t("controls.digits_on") : t("controls.digits_off")}
          </button>
          <button
            type="button"
            onClick={settings.toggleTheme}
            aria-pressed={settings.theme === "dark"}
            aria-label={t("controls.theme_label")}
          >
            {settings.theme === "dark" ? t("controls.theme_dark") : t("controls.theme_light")}
          </button>
        </div>
        <nav aria-label={t("nav.label")} style={{ inlineSize: "100%" }}>
          <ul className="nav">
            {SCREENS.map((s) => (
              <li key={s.key}>
                <NavLink to={s.path} end={s.path === "/"}>
                  {t(`nav.${s.key}`)}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main id="main" className="shell" tabIndex={-1}>
        <p className="muted" data-testid="mode-note">
          {t(`mode.${MODE}`)}
        </p>
        <ErrorBoundary fallback={(error) => <ErrorState error={error} />}>
          <Outlet />
        </ErrorBoundary>
      </main>
      <footer>{t("footer")}</footer>
    </>
  );
}
