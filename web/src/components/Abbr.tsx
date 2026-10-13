import { useTranslation } from "react-i18next";

// Abbreviations always carry their expansion, on hover and for screen readers.
export function Abbr({ term }: { term: string }) {
  const { t } = useTranslation();
  const full = t(`abbr.${term}`);
  return (
    <abbr title={full} aria-label={full}>
      {term}
    </abbr>
  );
}
