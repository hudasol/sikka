import { useTranslation } from "react-i18next";

// Severity is encoded by shape and pattern as well as colour.
const SHAPES: Record<string, string> = {
  error: "■",
  warning: "▲",
  info: "○",
  ok: "●",
};

export function SeverityBadge({ severity }: { severity: "error" | "warning" | "info" | "ok" }) {
  const { t } = useTranslation();
  return (
    <span className={`badge ${severity}`}>
      <span className="shape" aria-hidden="true">
        {SHAPES[severity]}
      </span>
      {t(`severity.${severity}`)}
    </span>
  );
}
