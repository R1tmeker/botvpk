import { useEffect } from "react";

type Insets = { top?: number; bottom?: number; left?: number; right?: number };
export type ViewportBridge = {
  safeAreaInset?: Insets;
  contentSafeAreaInset?: Insets;
  onEvent?: (event: string, handler: () => void) => void;
  offEvent?: (event: string, handler: () => void) => void;
};

/** Keep portaled dialogs inside the visible viewport, including the keyboard. */
export function useAppViewport(bridge: object) {
  useEffect(() => {
    const root = document.documentElement;
    const webApp = bridge as ViewportBridge;
    const viewport = window.visualViewport;
    let layoutHeight = window.innerHeight;
    let layoutWidth = window.innerWidth;
    let frame = 0;
    const update = () => {
      frame = 0;
      const height = viewport?.height ?? window.innerHeight;
      if (Math.abs(window.innerWidth - layoutWidth) > 40) {
        layoutWidth = window.innerWidth;
        layoutHeight = window.innerHeight;
      }
      layoutHeight = Math.max(layoutHeight, window.innerHeight);
      root.style.setProperty("--app-viewport-height", `${height}px`);
      root.style.setProperty("--app-viewport-top", `${viewport?.offsetTop ?? 0}px`);
      // Pinch zoom reduces visualViewport too; it is not a virtual keyboard.
      const editing = document.activeElement?.matches('input:not([type="checkbox"]):not([type="radio"]), textarea, [contenteditable="true"]');
      const keyboard = navigator.maxTouchPoints > 0 && editing && (viewport?.scale ?? 1) <= 1.05 && layoutHeight - height > 150;
      root.dataset.keyboard = String(Boolean(keyboard));
      for (const side of ["top", "right", "bottom", "left"] as const) {
        const safe = Math.max(0, webApp.safeAreaInset?.[side] ?? 0);
        const content = Math.max(0, webApp.contentSafeAreaInset?.[side] ?? 0);
        root.style.setProperty(`--tg-safe-${side}`, `${safe + content}px`);
      }
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    const events = ["viewportChanged", "safeAreaChanged", "contentSafeAreaChanged"];
    update();
    viewport?.addEventListener("resize", schedule);
    viewport?.addEventListener("scroll", schedule);
    window.addEventListener("resize", schedule);
    document.addEventListener("focusin", schedule);
    document.addEventListener("focusout", schedule);
    events.forEach((event) => webApp.onEvent?.(event, schedule));
    return () => {
      window.cancelAnimationFrame(frame);
      viewport?.removeEventListener("resize", schedule);
      viewport?.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      document.removeEventListener("focusin", schedule);
      document.removeEventListener("focusout", schedule);
      events.forEach((event) => webApp.offEvent?.(event, schedule));
      ["--app-viewport-height", "--app-viewport-top", ...["top", "right", "bottom", "left"].map((s) => `--tg-safe-${s}`)]
        .forEach((property) => root.style.removeProperty(property));
      delete root.dataset.keyboard;
    };
  }, [bridge]);
}
