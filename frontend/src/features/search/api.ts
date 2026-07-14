import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../shared/api/queryKeys";
import type { SearchResult } from "../../types/api";

export function useGlobalSearch(query: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.search(query),
    queryFn: async () => (await api.get<SearchResult[]>("/search", { params: { q: query } })).data,
    enabled: enabled && query.trim().length >= 2,
    staleTime: 30_000,
  });
}
