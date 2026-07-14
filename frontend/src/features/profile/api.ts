import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../shared/api/queryKeys";
import type { CalendarSubscription, NotificationPreference, UserProgress } from "../../types/api";

export function useNotificationPreferences(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.notifications.preferences,
    queryFn: async () => (await api.get<NotificationPreference[]>("/me/notification-preferences")).data,
    enabled,
  });
}

export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (items: NotificationPreference[]) => (
      await api.put<NotificationPreference[]>("/me/notification-preferences", { items })
    ).data,
    onSuccess: (data) => queryClient.setQueryData(queryKeys.notifications.preferences, data),
  });
}

export function useCreateCalendarSubscription() {
  return useMutation({
    mutationFn: async () => (await api.post<CalendarSubscription>("/calendar/subscription")).data,
  });
}

export function useRevokeCalendarSubscription() {
  return useMutation({ mutationFn: async () => api.delete("/calendar/subscription") });
}

export function useProgress(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.progress,
    queryFn: async () => (await api.get<UserProgress>("/me/progress")).data,
    enabled,
  });
}
