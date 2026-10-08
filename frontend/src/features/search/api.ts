import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../shared/api/queryKeys";
import type { SearchResult } from "../../types/api";

export function useGlobalSearch(query: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.search(query),
    queryFn: async ({ signal }) => (await api.get<SearchResult[]>("/search", { signal, params: { q: query.trim() } })).data,
    enabled: enabled && query.trim().length >= 2,
    staleTime: 30_000,
  });
}
