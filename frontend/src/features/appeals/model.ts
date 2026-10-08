import type { Appeal } from "../../types/api";

export const APPEAL_MESSAGE_LIMIT = 4000;

export function filterAppeals(items: Appeal[], query: string, status: string): Appeal[] {
  const needle = query.trim().toLocaleLowerCase("ru");
  return items.filter((item) => (!status || item.status_code === status)
    && (!needle || `${item.id} ${item.subject} ${item.description}`.toLocaleLowerCase("ru").includes(needle)))
    .sort((a, b) => Date.parse(b.updated_at ?? b.created_at) - Date.parse(a.updated_at ?? a.created_at) || b.id - a.id);
}

export function messageDraftKey(userId: number | null, appealId: number | null): string | null {
  return userId && appealId ? `draft:appeal-message:${userId}:${appealId}` : null;
}

export function validMessageBody(text: string): boolean {
  return text.trim().length > 0 && text.length <= APPEAL_MESSAGE_LIMIT;
}
