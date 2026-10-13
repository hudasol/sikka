import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

export function Loading({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="state" role="status" aria-live="polite">
      {label ?? t("state.loading")}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const detail = error instanceof Error ? error.message : String(error);
  return (
    <div className="state error" role="alert">
      <p>{t("state.error")}</p>
      <p className="mono">{detail}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry}>
          {t("state.retry")}
        </button>
      ) : null}
    </div>
  );
}

export function Empty({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  return <div className="state">{children ?? t("state.empty")}</div>;
}

export function Partial({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="state" role="note">
      <strong>{t("state.partial")}. </strong>
      {children}
    </div>
  );
}
