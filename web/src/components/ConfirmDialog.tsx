"use client";

import { useEffect, useRef } from "react";

type ConfirmDialogProps = {
  titleId: string;
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  confirming?: boolean;
  danger?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
};

const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Minimal accessible confirm dialog: `role="dialog"` + `aria-modal`, a
 * basic focus trap (Tab/Shift+Tab cycle within the panel), Escape closes,
 * and focus returns to the element that opened it. Used for destructive,
 * explicit-confirmation actions (e.g. deleting a knowledge document) where
 * a native `confirm()` would not carry the explanatory copy the flow needs.
 */
export function ConfirmDialog({
  titleId,
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancelar",
  confirming = false,
  danger = false,
  error,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key !== "Tab") return;

      const panel = panelRef.current;
      if (!panel) return;
      const focusable = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;

      if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused.current?.focus();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="dialog-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div
        ref={panelRef}
        className="dialog-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={`${titleId}-description`}
      >
        <h2 id={titleId}>{title}</h2>
        <div id={`${titleId}-description`}>{description}</div>

        {error ? (
          <p role="alert" className="dialog-error">
            {error}
          </p>
        ) : null}

        <div className="dialog-actions">
          <button ref={cancelRef} type="button" className="btn btn-secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className={danger ? "btn btn-danger" : "btn btn-primary"}
            onClick={onConfirm}
            disabled={confirming}
          >
            {confirming ? "Procesando…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
