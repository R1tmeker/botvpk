import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const openDialogs: HTMLElement[] = [];
let previousOverflow = "";
let previousRootInert = false;
const focusableSelector = 'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), iframe, [tabindex]:not([tabindex="-1"])';

export function Dialog({ children, onClose, overlayClassName, className, label, labelledBy }: {
  children: ReactNode;
  onClose: () => void;
  overlayClassName: string;
  className: string;
  label?: string;
  labelledBy?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    const dialog = ref.current!;
    const returnFocus = document.activeElement as HTMLElement | null;
    const root = document.getElementById("root");
    if (!openDialogs.length) {
      previousOverflow = document.body.style.overflow;
      previousRootInert = root?.inert ?? false;
      document.body.style.overflow = "hidden";
      if (root) root.inert = true;
    }
    openDialogs.push(dialog);
    dialog.focus({ preventScroll: true });
    const keydown = (event: KeyboardEvent) => {
      if (openDialogs[openDialogs.length - 1] !== dialog) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        closeRef.current();
      }
      if (event.key !== "Tab") return;
      const targets = [...dialog.querySelectorAll<HTMLElement>(focusableSelector)]
        .filter((element) => element.getClientRects().length > 0 && element.tabIndex >= 0);
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (!first) { event.preventDefault(); dialog.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === dialog)) {
        event.preventDefault(); first.focus();
      }
    };
    const focusin = (event: FocusEvent) => {
      if (openDialogs[openDialogs.length - 1] === dialog && !dialog.contains(event.target as Node)) {
        dialog.focus({ preventScroll: true });
      }
    };
    document.addEventListener("keydown", keydown, true);
    document.addEventListener("focusin", focusin);
    return () => {
      document.removeEventListener("keydown", keydown, true);
      document.removeEventListener("focusin", focusin);
      const index = openDialogs.indexOf(dialog);
      if (index >= 0) openDialogs.splice(index, 1);
      if (!openDialogs.length) {
        document.body.style.overflow = previousOverflow;
        if (root) root.inert = previousRootInert;
      }
      if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true });
    };
  }, []);

  return createPortal(
    <div className={overlayClassName} onClick={(event) => {
      if (event.target === event.currentTarget) closeRef.current();
    }}>
      <div ref={ref} className={className} role="dialog" aria-modal="true"
        aria-label={label} aria-labelledby={labelledBy} tabIndex={-1}>
        {children}
      </div>
    </div>, document.body,
  );
}
