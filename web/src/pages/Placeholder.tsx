import { useTranslation } from "react-i18next";

export function Placeholder({ screen }: { screen: string }) {
  const { t } = useTranslation();
  const title = t(`nav.${screen}`);
  return (
    <section aria-labelledby={`${screen}-title`}>
      <h1 id={`${screen}-title`}>{title}</h1>
      <div className="state">{t("placeholder.body")}</div>
    </section>
  );
}
