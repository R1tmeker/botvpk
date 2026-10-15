import type { Normative, NormativeSubmission } from "../../types/api";

export function currentSubmission(normative: Normative, submissions: NormativeSubmission[]) {
  return submissions.filter((item) => item.normative_id === normative.id
    && (item.period_start_date ?? null) === (normative.recurrence_days ? normative.current_period_start_date ?? null : null))
    .sort((a, b) => Date.parse(b.submitted_at) - Date.parse(a.submitted_at))[0];
}

export const normativeStatusLabels: Record<string, string> = {
  ACCEPTED: "Принято", PENDING: "На проверке", NEEDS_REDO: "Нужна пересдача", NOT_SUBMITTED: "Не сдавал",
};

export type NormativeMemberProgress = {
  user_id: number; full_name: string; squad_id: number | null; total: number;
  accepted: number; pending: number; redo: number; missing: number; accepted_all_time: number; percent: number;
  items: Array<{ normative_id: number; title: string; status: string; period_start_date: string | null; period_end_date: string | null; next_reset_at: string | null }>;
};

export function normativeDraftKey(userId: number, normative: Normative, field: "comment" | "files") {
  const period = normative.recurrence_days ? `:${normative.current_period_start_date ?? "upcoming"}` : "";
  return `draft:normative:${userId}:${normative.id}${period}:${field}`;
}
