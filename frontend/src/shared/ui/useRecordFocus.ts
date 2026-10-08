import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { recordId } from "../../features/schedule/model";

export function useRecordFocus(parameter: string, prefix: string, revision: string) {
  const location = useLocation();
  const id = recordId(location.search, parameter);
  const handled = useRef("");
  useEffect(() => {
    const key = `${location.key}:${prefix}:${id}`;
    if (id === null || handled.current === key) return;
    const frame = requestAnimationFrame(() => {
      const target = document.getElementById(`${prefix}-${id}`);
      if (!target) return;
      target.scrollIntoView({ block: "center", behavior: "auto" });
      target.focus({ preventScroll: true });
      handled.current = key;
    });
    return () => cancelAnimationFrame(frame);
  }, [id, prefix, revision, location.key]);
  return id;
}
