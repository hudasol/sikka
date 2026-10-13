import { useTranslation } from "react-i18next";

const SECTIONS = {
  agreement: ["parties", "purpose", "fields", "frequency", "retention", "security", "exit"],
  privacy: ["dpia", "minimise", "quarantine", "access", "audit"],
  roles: ["owner", "steward", "producer", "analyst", "reviewer"],
  contract: ["identifiers", "segments", "severity", "exposure", "version"],
} as const;

export function Pilot() {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="pilot-title">
      <h1 id="pilot-title">{t("pilot.title")}</h1>
      <p>{t("pilot.intro")}</p>
      <p className="state">{t("pilot.proposal")}</p>
      {Object.entries(SECTIONS).map(([section, items]) => (
        <div className="card" key={section}>
          <h2>{t(`pilot.${section}`)}</h2>
          <ul className={section === "agreement" ? "checklist" : undefined}>
            {items.map((item) => (
              <li key={item}>{t(`pilot.${section}_${item}`)}</li>
            ))}
          </ul>
        </div>
      ))}
      <div className="card">
        <h2>{t("pilot.steps")}</h2>
        <ol>
          {["one", "two", "three", "four"].map((s) => (
            <li key={s}>{t(`pilot.step_${s}`)}</li>
          ))}
        </ol>
      </div>
    </section>
  );
}
