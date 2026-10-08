import { useCallback, useEffect, useRef, useState } from "react";

import { DraftSession, type DraftSnapshot } from "./draftSession";
import { deleteOfflineValue, getOfflineStorageMode, loadOfflineValue, saveOfflineValue, subscribeOfflineStorage } from "./storage";

export function usePersistentDraft<T>(key: string | null, initial: T, enabled = true) {
  const initialRef = useRef(initial);
  initialRef.current = initial;
  const sessionRef = useRef<DraftSession<T> | null>(null);
  const [current, setCurrent] = useState<{ key: string | null; snapshot: DraftSnapshot<T> } | null>(null);
  const [mode, setMode] = useState(getOfflineStorageMode);
  useEffect(() => subscribeOfflineStorage(() => setMode(getOfflineStorageMode())), []);

  useEffect(() => {
    if (!key || !enabled) { sessionRef.current = null; return; }
    const session = new DraftSession(key, initialRef.current, {
      load: loadOfflineValue<T>, save: saveOfflineValue<T>, remove: deleteOfflineValue,
    });
    sessionRef.current = session;
    const unsubscribe = session.subscribe((snapshot) => setCurrent({ key, snapshot }));
    setCurrent({ key, snapshot: session.getSnapshot() });
    void session.restore();
    const flush = () => { void session.flush(); };
    const onHidden = () => { if (document.visibilityState === "hidden") flush(); };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", onHidden);
    return () => {
      unsubscribe(); session.close();
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", onHidden);
      if (sessionRef.current === session) sessionRef.current = null;
    };
  }, [key, enabled]);

  useEffect(() => {
    if (!current?.snapshot.ready || !current.snapshot.dirty || !enabled || current.key !== key) return;
    const timer = window.setTimeout(() => { void sessionRef.current?.flush(); }, 350);
    return () => window.clearTimeout(timer);
  }, [current, key, enabled]);

  // Capture the session belonging to this render. A completed request must not clear another user's/chat's draft.
  const session = sessionRef.current?.key === key ? sessionRef.current : null;
  const setValue = useCallback((next: T | ((previous: T) => T)) => session?.update(next), [session]);
  const clear = useCallback(() => session?.clear() ?? Promise.resolve(), [session]);
  const flush = useCallback(() => session?.flush() ?? Promise.resolve(), [session]);
  const snapshot = current?.key === key && enabled ? current.snapshot : null;
  return {
    value: snapshot?.value ?? initial,
    setValue, clear, flush, mode,
    ready: key === null || Boolean(snapshot?.ready),
    restored: Boolean(snapshot?.restored),
    saving: Boolean(snapshot?.saving || snapshot?.dirty),
    saved: snapshot?.savedAt !== null && snapshot?.savedAt !== undefined,
  };
}
