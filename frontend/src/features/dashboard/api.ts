import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { liveQueryOptions } from "../../shared/api/queryOptions";
import { queryKeys } from "../../shared/api/queryKeys";
import type { ActionItem, ActionItemExecutionResult, DashboardBootstrap } from "../../types/api";

export function useActionItems(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.dashboard.actionItems,
    queryFn: async () => (await api.get<ActionItem[]>("/dashboard/action-items")).data,
    enabled,
    ...liveQueryOptions,
  });
}

export function useExecuteActionItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ itemCode, actionCode }: { itemCode: string; actionCode: string }) => (
      await api.post<ActionItemExecutionResult>(
        `/dashboard/action-items/${encodeURIComponent(itemCode)}/actions/${encodeURIComponent(actionCode)}`,
      )
    ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.root });
      queryClient.invalidateQueries({ queryKey: queryKeys.attendance.root });
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.root });
      queryClient.invalidateQueries({ queryKey: queryKeys.normatives.root });
      queryClient.invalidateQueries({ queryKey: queryKeys.appeals.root });
    },
  });
}

export function useDashboardBootstrap(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.dashboard.bootstrap,
    queryFn: async () => (await api.get<DashboardBootstrap>("/dashboard/bootstrap")).data,
    enabled,
    ...liveQueryOptions,
  });
}
