import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="not-found-title">
      <h1 id="not-found-title">{t("not_found.title")}</h1>
      <p>{t("not_found.body")}</p>
      <Link to="/">{t("not_found.home")}</Link>
    </section>
  );
}
