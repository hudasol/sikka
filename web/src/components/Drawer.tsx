import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
}

// A side panel built on the native dialog element: focus moves into it, Escape
// closes it, and focus returns to the element that opened it.
export function Drawer({ title, onClose, children }: Props) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    const dialog = ref.current;
    const opener = document.activeElement as HTMLElement | null;
    if (dialog && typeof dialog.showModal === "function" && !dialog.open) {
      dialog.showModal();
    }
    return () => {
      opener?.focus?.();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="drawer"
      aria-labelledby="drawer-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h2 id="drawer-title" style={{ marginBlockEnd: 0 }}>
          {title}
        </h2>
        <button type="button" onClick={onClose}>
          {t("common.close")}
        </button>
      </div>
      <div style={{ marginBlockStart: 16 }}>{children}</div>
    </dialog>
  );
}
