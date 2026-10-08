import type { LearningMaterial } from "../../types/api";

export type LearningFilter = "all" | "unread" | "viewed";

export function filterMaterials(items: LearningMaterial[], query: string, filter: LearningFilter): LearningMaterial[] {
  const needle = query.trim().toLocaleLowerCase("ru");
  return items.filter((item) => (filter === "all" || Boolean(item.is_viewed) === (filter === "viewed"))
    && (!needle || `${item.title} ${item.description ?? ""}`.toLocaleLowerCase("ru").includes(needle)));
}

export function learningProgress(items: LearningMaterial[]) {
  const total = items.length;
  const completed = items.filter((item) => item.is_viewed).length;
  return { total, completed, percent: total ? Math.round(completed / total * 100) : 0,
    nextId: items.find((item) => !item.is_viewed)?.id ?? null };
}
