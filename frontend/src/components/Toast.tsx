import { useCallback, useEffect, useRef, useState } from "react";
import styles from "./Toast.module.scss";

export type ToastType = "success" | "error" | "info" | "warning";

export type Toast = {
  id: number;
  type: ToastType;
  message: string;
  duration?: number;
};

type ToastContextValue = { show: (message: string, type?: ToastType, duration?: number) => void };

let globalShow: ToastContextValue["show"] | null = null;

export function toast(message: string, type: ToastType = "success", duration = 3000) {
  globalShow?.(message, type, duration);
}

const ICONS: Record<ToastType, string> = {
  success: "✅",
  error: "❌",
  info: "ℹ️",
  warning: "⚠️",
};

const COLORS: Record<ToastType, string> = {
  success: "#27ae60",
  error: "#e74c3c",
  info: "#3498db",
  warning: "#f39c12",
};

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const show = useCallback((message: string, type: ToastType = "success", duration = 3000) => {
    const id = ++nextId.current;
    setToasts((prev) => [...prev, { id, type, message, duration }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), duration + 400);
  }, []);

  useEffect(() => { globalShow = show; return () => { globalShow = null; }; }, [show]);

  return (
    <div className={styles.container} aria-live="polite">
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))} />
      ))}
    </div>
  );
}

function ToastItem({ toast: t, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const show = setTimeout(() => setVisible(true), 10);
    const hide = setTimeout(() => setVisible(false), (t.duration ?? 3000) - 350);
    return () => { clearTimeout(show); clearTimeout(hide); };
  }, [t.duration]);

  return (
    <div
      className={`${styles.toast} ${visible ? styles.visible : ""}`}
      style={{ borderLeftColor: COLORS[t.type] }}
      onClick={onDismiss}
    >
      <span className={styles.icon}>{ICONS[t.type]}</span>
      <span className={styles.message}>{t.message}</span>
    </div>
  );
}
