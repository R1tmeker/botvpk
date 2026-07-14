import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../shared/api/queryKeys";
import type { AttendanceRecord, ReportSummary } from "../../types/api";

type AttendanceEntry = {
  user_id: number;
  status_code: string;
  absence_reason_id?: number | null;
  custom_reason?: string | null;
};

export function useMyAttendance(enabled: boolean, limit = 100, offset = 0) {
  return useQuery({
    queryKey: queryKeys.attendance.mine(limit, offset),
    queryFn: async () => (await api.get<AttendanceRecord[]>("/attendance/my", { params: { limit, offset } })).data,
    enabled,
  });
}

export function useMyAttendanceStats(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.attendance.myStats,
    queryFn: async () => (await api.get<ReportSummary>("/attendance/stats/my")).data,
    enabled,
  });
}

export function useAttendanceEvent(eventId: number | null, enabled: boolean, limit = 200, offset = 0) {
  return useQuery({
    queryKey: queryKeys.attendance.event(eventId, limit, offset),
    queryFn: async () => (
      await api.get<AttendanceRecord[]>(`/attendance/events/${eventId}`, { params: { limit, offset } })
    ).data,
    enabled: enabled && eventId !== null,
  });
}

export function useMarkAttendance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ eventId, entries }: { eventId: number; entries: AttendanceEntry[] }) => (
      await api.post<AttendanceRecord[]>(`/attendance/events/${eventId}/bulk`, { items: entries })
    ).data,
    onMutate: async (variables) => {
      const queryKey = queryKeys.attendance.event(variables.eventId, 200, 0);
      await queryClient.cancelQueries({ queryKey: ["attendance", "event", variables.eventId] });
      const previous = queryClient.getQueryData<AttendanceRecord[]>(queryKey);
      const byUser = new Map((previous ?? []).map((item) => [item.user_id, item]));
      const now = new Date().toISOString();
      queryClient.setQueryData<AttendanceRecord[]>(queryKey, variables.entries.map((entry, index) => {
        const old = byUser.get(entry.user_id);
        return {
          id: old?.id ?? -(index + 1),
          event_id: variables.eventId,
          user_id: entry.user_id,
          status_code: entry.status_code,
          absence_reason_id: entry.absence_reason_id ?? null,
          custom_reason: entry.custom_reason ?? null,
          marked_by_user_id: old?.marked_by_user_id ?? null,
          marked_at: now,
          source_code: "COMMANDER",
          is_draft: false,
          updated_at: now,
        };
      }));
      return { previous, queryKey };
    },
    onError: (_error, _variables, context) => {
      if (context) queryClient.setQueryData(context.queryKey, context.previous);
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(queryKeys.attendance.event(variables.eventId, 200, 0), data);
      queryClient.invalidateQueries({ queryKey: ["attendance", "event", variables.eventId] });
      queryClient.invalidateQueries({ queryKey: queryKeys.attendance.root });
      queryClient.invalidateQueries({ queryKey: ["reports", "attendance"] });
    },
  });
}

export function useSelfCheckIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (eventId: number) => (
      await api.post<AttendanceRecord>(`/schedule/events/${eventId}/self-checkin`)
    ).data,
    onSuccess: (attendance) => {
      queryClient.setQueryData<AttendanceRecord[]>(queryKeys.attendance.mine(100, 0), (items) => {
        const current = items ?? [];
        return [attendance, ...current.filter((item) => item.id !== attendance.id)];
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.attendance.root });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useAbsenceReasons() {
  return useQuery({
    queryKey: ["absence_reasons"],
    queryFn: async () => (
      await api.get<Array<{
        id: number;
        code: string;
        label: string;
        requires_comment: boolean;
        sort_order: number;
        is_active: boolean;
      }>>("/schedule/absence-reasons")
    ).data,
  });
}

export function useMyAttendanceStatsFull(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.attendance.fullStats,
    queryFn: async () => (
      await api.get<{
        present: number;
        absent: number;
        late: number;
        total: number;
        percent: number;
        avg_grade: number | null;
      }>("/attendance/stats/my")
    ).data,
    enabled,
  });
}

export function useMyStreak(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.attendance.streak,
    queryFn: async () => (
      await api.get<{
        current_streak: number;
        best_streak: number;
        total_events: number;
        present_count: number;
        percent: number;
      }>("/attendance/streak/my")
    ).data,
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}
