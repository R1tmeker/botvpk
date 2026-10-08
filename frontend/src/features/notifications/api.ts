import { useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { Notification } from "../../types/api";

const PAGE_SIZE = 20;

export function useNotificationSummary(enabled = true) {
  return useQuery({
    queryKey: ["notifications", "summary"],
    queryFn: async ({ signal }) => (await api.get<{ total: number; unread: number }>("/notifications/summary", { signal })).data,
    enabled,
    staleTime: 15_000,
  });
}

export function useNotificationInbox(unreadOnly: boolean, category: string, query: string) {
  return useInfiniteQuery({
    queryKey: ["notifications", "inbox", unreadOnly, category, query],
    initialPageParam: 0,
    queryFn: async ({ pageParam, signal }) => {
      const { data } = await api.get<Notification[]>("/notifications", {
        signal, params: { limit: PAGE_SIZE + 1, offset: pageParam, unread_only: unreadOnly, category: category || undefined, q: query || undefined },
      });
      return { items: data.slice(0, PAGE_SIZE), next: data.length > PAGE_SIZE ? pageParam + PAGE_SIZE : undefined };
    },
    getNextPageParam: (page) => page.next,
    staleTime: 15_000,
  });
}
