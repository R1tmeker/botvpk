import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, apiBaseUrl } from "./client";
import { loadOfflineValue, saveOfflineValue } from "../offline/storage";
import type {
  Announcement,
  ActionItem,
  Appeal,
  AppealMessage,
  AuditLog,
  AttendanceRecord,
  AuthResponse,
  CandidateEvent,
  CalendarSubscription,
  DashboardSetting,
  DashboardBootstrap,
  ImportPreview,
  JoinApplication,
  LearningCourse,
  MenuCard,
  Normative,
  NormativeSubmission,
  Notification,
  NotificationPreference,
  PromoBlock,
  PublicContent,
  ReportSummary,
  ScheduleEvent,
  ScheduleTemplate,
  SearchResult,
  LearningMaterial,
  Squad,
  UserProfile,
  UserRecord,
  UserProgress,
} from "../types/api";

const LIVE_QUERY_OPTIONS = {
  refetchInterval: () => typeof document !== "undefined" && document.visibilityState === "visible" ? 60_000 : false,
  refetchIntervalInBackground: false,
  refetchOnMount: true,
  refetchOnReconnect: true,
  refetchOnWindowFocus: true,
} as const;

const FAST_QUERY_OPTIONS = {
  ...LIVE_QUERY_OPTIONS,
} as const;

export function useRealtimeInvalidation(enabled: boolean) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!enabled || typeof EventSource === "undefined") return;
    const source = new EventSource(`${apiBaseUrl.replace(/\/$/, "")}/events/stream`, { withCredentials: true });
    source.addEventListener("invalidate", (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent<string>).data) as { query_keys?: string[] };
        for (const key of payload.query_keys ?? []) {
          queryClient.invalidateQueries({ queryKey: [key] });
        }
      } catch {
        queryClient.invalidateQueries();
      }
    });
    return () => source.close();
  }, [enabled, queryClient]);
}

export function useActionItems(enabled: boolean) {
  return useQuery({
    queryKey: ["dashboard", "action-items"],
    queryFn: async () => {
      const { data } = await api.get<ActionItem[]>("/dashboard/action-items");
      return data;
    },
    enabled,
    ...LIVE_QUERY_OPTIONS,
  });
}

export function useDashboardBootstrap(enabled: boolean) {
  return useQuery({
    queryKey: ["dashboard", "bootstrap"],
    queryFn: async () => {
      const { data } = await api.get<DashboardBootstrap>("/dashboard/bootstrap");
      return data;
    },
    enabled,
    ...LIVE_QUERY_OPTIONS,
  });
}

export function useNotificationPreferences(enabled: boolean) {
  return useQuery({
    queryKey: ["me", "notification-preferences"],
    queryFn: async () => {
      const { data } = await api.get<NotificationPreference[]>("/me/notification-preferences");
      return data;
    },
    enabled,
  });
}

export function useUpdateNotificationPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (items: NotificationPreference[]) => {
      const { data } = await api.put<NotificationPreference[]>("/me/notification-preferences", { items });
      return data;
    },
    onSuccess: (data) => queryClient.setQueryData(["me", "notification-preferences"], data),
  });
}

export function useCreateCalendarSubscription() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<CalendarSubscription>("/calendar/subscription");
      return data;
    },
  });
}

export function useRevokeCalendarSubscription() {
  return useMutation({ mutationFn: async () => api.delete("/calendar/subscription") });
}

export function useGlobalSearch(query: string, enabled = true) {
  return useQuery({
    queryKey: ["search", query],
    queryFn: async () => {
      const { data } = await api.get<SearchResult[]>("/search", { params: { q: query } });
      return data;
    },
    enabled: enabled && query.trim().length >= 2,
    staleTime: 30_000,
  });
}

export function useProgress(enabled: boolean) {
  return useQuery({
    queryKey: ["progress", "me"],
    queryFn: async () => {
      const { data } = await api.get<UserProgress>("/me/progress");
      return data;
    },
    enabled,
  });
}

export function useAdminImportPreview() {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("upload", file);
      const { data } = await api.post<ImportPreview>("/admin/imports/preview", form);
      return data;
    },
  });
}

export function useAdminImportCommit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (previewId: string) => {
      const { data } = await api.post<{ created: number; updated: number; audit_batch_id: number }>(
        `/admin/imports/${previewId}/commit`,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit"] });
    },
  });
}

export function useAdminAuditUndo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (auditId: number) => {
      const { data } = await api.post<{ audit_id: number; undo_audit_id: number; affected: number; detail: string }>(
        `/admin/audit/${auditId}/undo`,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "audit"] });
    },
  });
}

export function useTelegramAuth() {
  return useMutation({
    mutationFn: async (initData: string) => {
      const { data } = await api.post<AuthResponse>("/auth/telegram", { init_data: initData });
      return data;
    },
  });
}

export function usePasswordLogin() {
  return useMutation({
    mutationFn: async (payload: { telegram_id: number; password: string; totp_code?: string }) => {
      const { data } = await api.post<AuthResponse>("/auth/password/login", payload);
      return data;
    },
  });
}

export function useSession() {
  return useQuery({
    queryKey: ["auth", "session"],
    queryFn: async () => {
      const { data } = await api.get<AuthResponse>("/auth/session");
      return data;
    },
    retry: false,
    staleTime: 60_000,
  });
}

export function useLogout() {
  return useMutation({
    mutationFn: async () => {
      await api.post("/auth/logout");
    },
  });
}

export function useStepUp() {
  return useMutation({
    mutationFn: async (payload: { password?: string; totp_code?: string; init_data?: string }) => {
      const { data } = await api.post<{ step_up: boolean }>("/auth/step-up", payload);
      return data;
    },
  });
}

type TwoFactorStatus = { available: boolean; enabled: boolean };

export function useTwoFactorStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["auth", "2fa", "status"],
    queryFn: async () => {
      const { data } = await api.get<TwoFactorStatus>("/auth/2fa/status");
      return data;
    },
    enabled,
  });
}

export function useTwoFactorSetup() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ secret: string; provisioning_uri: string }>("/auth/2fa/setup");
      return data;
    },
  });
}

export function useTwoFactorEnable() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => {
      const { data } = await api.post<TwoFactorStatus>("/auth/2fa/enable", { code });
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["auth", "2fa", "status"] }),
  });
}

export function useTwoFactorDisable() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => {
      const { data } = await api.post<TwoFactorStatus>("/auth/2fa/disable", { code });
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["auth", "2fa", "status"] }),
  });
}

export function usePasswordReset() {
  return useMutation({
    mutationFn: async (payload: { telegram_id: number; code: string; new_password: string }) => {
      const { data } = await api.post<{ has_password: boolean; password_set_at: string | null }>(
        "/auth/password/reset",
        payload,
      );
      return data;
    },
  });
}

export function usePasswordStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["auth", "password", "status"],
    queryFn: async () => {
      const { data } = await api.get<{ has_password: boolean; password_set_at: string | null }>(
        "/auth/password/status",
      );
      return data;
    },
    enabled,
  });
}

export function useSetPassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { new_password: string; current_password?: string }) => {
      const { data } = await api.post<{ has_password: boolean; password_set_at: string | null }>(
        "/auth/password/set",
        payload,
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "password", "status"] });
    },
  });
}

export function useDeletePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.delete<{ has_password: boolean; password_set_at: string | null }>(
        "/auth/password",
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "password", "status"] });
    },
  });
}

type VkStatus = { linked: boolean; vk_id: number | null; bot_url: string | null };

export function useVkStatus(enabled: boolean) {
  return useQuery({
    queryKey: ["auth", "vk", "status"],
    queryFn: async () => {
      const { data } = await api.get<VkStatus>("/auth/vk/status");
      return data;
    },
    enabled,
  });
}

export function useVkLinkCode() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ code: string; expires_at: string }>("/auth/vk/link-code");
      return data;
    },
  });
}

export function useVkUnlink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.delete<VkStatus>("/auth/vk/");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auth", "vk", "status"] });
    },
  });
}

type WebPushKeyResponse = { available: boolean; public_key: string | null };

export function useWebPushPublicKey(enabled: boolean) {
  return useQuery({
    queryKey: ["web-push", "public-key"],
    queryFn: async () => {
      const { data } = await api.get<WebPushKeyResponse>("/web-push/public-key");
      return data;
    },
    enabled,
  });
}

export function useWebPushSubscribe() {
  return useMutation({
    mutationFn: async (subscription: PushSubscriptionJSON) => {
      const { data } = await api.post<{ subscribed: boolean }>("/web-push/subscriptions", subscription);
      return data;
    },
  });
}

export function useWebPushUnsubscribe() {
  return useMutation({
    mutationFn: async (endpoint: string) => {
      const { data } = await api.delete<{ unsubscribed: boolean }>("/web-push/subscriptions", {
        data: { endpoint },
      });
      return data;
    },
  });
}

export function useMe(enabled: boolean) {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const { data } = await api.get<UserProfile>("/me");
      return data;
    },
    enabled,
  });
}

export function useMenu(enabled: boolean) {
  return useQuery({
    queryKey: ["menu"],
    queryFn: async () => {
      const { data } = await api.get<MenuCard[]>("/menu");
      return data;
    },
    enabled,
  });
}

export function usePublicContent(enabled: boolean) {
  return useQuery({
    queryKey: ["public", "content"],
    queryFn: async () => {
      const { data } = await api.get<PublicContent>("/public/content");
      return data;
    },
    enabled,
  });
}

export function usePublicEvents(enabled: boolean) {
  return useQuery({
    queryKey: ["public", "events"],
    queryFn: async () => {
      const { data } = await api.get<CandidateEvent[]>("/public/events");
      return data;
    },
    enabled,
  });
}

export function useJoinMe(enabled: boolean) {
  return useQuery({
    queryKey: ["join", "me"],
    queryFn: async () => {
      const { data } = await api.get<JoinApplication | null>("/join/me");
      return data;
    },
    enabled,
  });
}

export type ApplicationHistoryItem = {
  old_status: string | null;
  new_status: string;
  changed_at: string;
  comment: string | null;
};

export function useJoinHistory(enabled: boolean) {
  return useQuery({
    queryKey: ["join", "me", "history"],
    queryFn: async () => {
      const { data } = await api.get<ApplicationHistoryItem[]>("/join/me/history");
      return data;
    },
    enabled,
  });
}

export function useJoinEvents(enabled: boolean) {
  return useQuery({
    queryKey: ["join", "events"],
    queryFn: async () => {
      const { data } = await api.get<CandidateEvent[]>("/join/events");
      return data;
    },
    enabled,
  });
}

export function useSchedule(enabled: boolean, userId?: number | null) {
  return useQuery({
    queryKey: ["schedule"],
    queryFn: async () => {
      const fromDt = new Date();
      fromDt.setHours(0, 0, 0, 0);
      try {
        const { data } = await api.get<ScheduleEvent[]>("/schedule", {
          params: { from_dt: fromDt.toISOString() },
        });
        if (userId) void saveOfflineValue(`cache:schedule:${userId}`, data);
        return data;
      } catch (error) {
        const cached = userId ? await loadOfflineValue<ScheduleEvent[]>(`cache:schedule:${userId}`) : null;
        if (cached) return cached;
        throw error;
      }
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useMyAttendance(enabled: boolean, limit = 100, offset = 0) {
  return useQuery({
    queryKey: ["attendance", "my", limit, offset],
    queryFn: async () => {
      const { data } = await api.get<AttendanceRecord[]>("/attendance/my", {
        params: { limit, offset },
      });
      return data;
    },
    enabled,
  });
}

export function useMyAttendanceStats(enabled: boolean) {
  return useQuery({
    queryKey: ["attendance", "stats", "my"],
    queryFn: async () => {
      const { data } = await api.get<ReportSummary>("/attendance/stats/my");
      return data;
    },
    enabled,
  });
}

export function useNormatives(enabled: boolean, includeInactive = false) {
  return useQuery({
    queryKey: ["normatives", includeInactive],
    queryFn: async () => {
      const { data } = await api.get<Normative[]>(`/normatives${includeInactive ? "?active_only=false" : ""}`);
      return data;
    },
    enabled,
    ...LIVE_QUERY_OPTIONS,
  });
}

export function useMyNormativeSubmissions(enabled: boolean, limit = 100, offset = 0) {
  return useQuery({
    queryKey: ["normatives", "submissions", "my", limit, offset],
    queryFn: async () => {
      const { data } = await api.get<NormativeSubmission[]>("/submissions/my", {
        params: { limit, offset },
      });
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function usePendingNormativeSubmissions(enabled: boolean, limit = 100, offset = 0) {
  return useQuery({
    queryKey: ["normatives", "submissions", "pending", limit, offset],
    queryFn: async () => {
      const { data } = await api.get<NormativeSubmission[]>("/submissions/pending", {
        params: { limit, offset },
      });
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useNormativeSubmissionsHistory(enabled: boolean, statusCode = "ALL", limit = 100, offset = 0) {
  return useQuery({
    queryKey: ["normatives", "submissions", "history", statusCode, limit, offset],
    queryFn: async () => {
      const { data } = await api.get<NormativeSubmission[]>("/submissions/history", {
        params: {
          limit,
          offset,
          ...(statusCode && statusCode !== "ALL" ? { status_code: statusCode } : {}),
        },
      });
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useNotifications(enabled: boolean) {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: async () => {
      const { data } = await api.get<Notification[]>("/notifications");
      return data;
    },
    enabled,
    ...LIVE_QUERY_OPTIONS,
  });
}

export function useAnnouncements(enabled: boolean) {
  return useQuery({
    queryKey: ["announcements"],
    queryFn: async () => {
      const { data } = await api.get<Announcement[]>("/announcements");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useAttendanceReport(enabled: boolean) {
  return useQuery({
    queryKey: ["reports", "attendance"],
    queryFn: async () => {
      const { data } = await api.get<ReportSummary>("/reports/attendance");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useGradesReport(enabled: boolean) {
  return useQuery({
    queryKey: ["reports", "grades"],
    queryFn: async () => {
      const { data } = await api.get<ReportSummary>("/reports/grades");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useNormativesReport(enabled: boolean) {
  return useQuery({
    queryKey: ["reports", "normatives"],
    queryFn: async () => {
      const { data } = await api.get<ReportSummary>("/reports/normatives");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useLearningMaterials(enabled: boolean, userId?: number | null) {
  return useQuery({
    queryKey: ["learning", "materials"],
    queryFn: async () => {
      try {
        const { data } = await api.get<LearningMaterial[]>("/learning/materials");
        if (userId) void saveOfflineValue(`cache:learning:${userId}`, data);
        return data;
      } catch (error) {
        const cached = userId ? await loadOfflineValue<LearningMaterial[]>(`cache:learning:${userId}`) : null;
        if (cached) return cached;
        throw error;
      }
    },
    enabled,
  });
}

export function useLearningCourses(enabled: boolean) {
  return useQuery({
    queryKey: ["learning", "courses"],
    queryFn: async () => {
      const { data } = await api.get<LearningCourse[]>("/learning/courses");
      return data;
    },
    enabled,
  });
}

export function useAppeals(enabled: boolean) {
  return useQuery({
    queryKey: ["appeals"],
    queryFn: async () => {
      const { data } = await api.get<Appeal[]>("/appeals");
      return data;
    },
    enabled,
  });
}

export function usePromo(enabled: boolean) {
  return useQuery({
    queryKey: ["promo", "active"],
    queryFn: async () => {
      const { data } = await api.get<PromoBlock[]>("/promo/active");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useDashboardSettings(enabled: boolean) {
  return useQuery({
    queryKey: ["dashboard", "settings"],
    queryFn: async () => {
      const { data } = await api.get<DashboardSetting[]>("/dashboard/settings");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useSquads(enabled: boolean) {
  return useQuery({
    queryKey: ["squads"],
    queryFn: async () => {
      const { data } = await api.get<Squad[]>("/squads");
      return data;
    },
    enabled,
  });
}

export function useAdminUsers(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: async () => {
      const { data } = await api.get<UserRecord[]>("/admin/users");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useAdminApplications(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "applications"],
    queryFn: async () => {
      const { data } = await api.get<JoinApplication[]>("/admin/join/applications");
      return data;
    },
    enabled,
  });
}

export function useAdminPromo(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "promo"],
    queryFn: async () => {
      const { data } = await api.get<PromoBlock[]>("/admin/promo");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useAdminMenu(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "menu"],
    queryFn: async () => {
      const { data } = await api.get<MenuCard[]>("/admin/menu");
      return data;
    },
    enabled,
  });
}

export function useAdminAudit(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "audit"],
    queryFn: async () => {
      const { data } = await api.get<AuditLog[]>("/admin/audit");
      return data;
    },
    enabled,
  });
}

export function useUpdateMenuCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; is_active?: boolean; sort_order?: number; show_badge?: boolean }) => {
      const { data } = await api.patch<MenuCard>(`/admin/menu/${id}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "menu"] });
      queryClient.invalidateQueries({ queryKey: ["menu"] });
    },
  });
}

export type EventResponseItem = {
  user_id: number;
  full_name: string;
  username: string | null;
  squad_id: number | null;
  response_code: string;
  custom_reason: string | null;
  responded_at: string | null;
};

export function useEventResponses(eventId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["schedule", "event", eventId, "responses"],
    queryFn: async () => {
      const { data } = await api.get<EventResponseItem[]>(`/schedule/events/${eventId}/responses`);
      return data;
    },
    enabled: enabled && eventId !== null,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useRespondEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      eventId,
      responseCode,
      absenceReasonId,
      customReason,
    }: {
      eventId: number;
      responseCode: string;
      absenceReasonId?: number | null;
      customReason?: string;
    }) => {
      const { data } = await api.post(`/schedule/events/${eventId}/respond`, {
        response_code: responseCode,
        absence_reason_id: absenceReasonId ?? null,
        custom_reason: customReason ?? null,
      });
      return data;
    },
    onSuccess: (_data, variables) => {
      queryClient.setQueryData<ScheduleEvent[]>(["schedule"], (items) =>
        items?.map((event) => event.id === variables.eventId ? { ...event, my_response_code: variables.responseCode } : event) ?? items,
      );
      queryClient.invalidateQueries({ queryKey: ["schedule", "event", variables.eventId, "responses"] });
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
    },
  });
}

export function useRespondCandidateEvent() {
  return useMutation({
    mutationFn: async ({ eventId, responseCode }: { eventId: number; responseCode: string }) => {
      const { data } = await api.post(`/join/events/${eventId}/respond`, { response_code: responseCode });
      return data;
    },
  });
}

export function useReadNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (notificationId: number) => {
      const { data } = await api.patch<Notification>(`/notifications/${notificationId}/read`);
      return data;
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<Notification[]>(["notifications"], (items) =>
        items?.map((item) => item.id === updated.id ? updated : item) ?? items,
      );
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useCreateJoinApplication() {
  return useMutation({
    mutationFn: async (payload: {
      full_name: string;
      birth_date?: string;
      phone?: string;
      city?: string;
      education_place?: string;
      experience_text?: string;
      motivation_text?: string;
      source_text?: string;
      consent_given: boolean;
      comment?: string;
    }) => {
      const { data } = await api.post("/join/applications", payload);
      return data;
    },
  });
}

export function useCreateAppeal() {
  return useMutation({
    mutationFn: async (payload: {
      subject: string;
      description: string;
      category_code: string;
      urgency_code: string;
      is_anonymous: boolean;
      file_id?: number | null;
    }) => {
      const { data } = await api.post("/appeals", payload);
      return data;
    },
  });
}

export function useCreateAnnouncement() {
  return useMutation({
    mutationFn: async (payload: {
      title: string;
      body: string;
      target_type: string;
      target_squad_id?: number | null;
      target_role_code?: string | null;
      file_id?: number | null;
      status_code: string;
      send_to_tg: boolean;
      send_to_app: boolean;
    }) => {
      const { data } = await api.post("/announcements", payload);
      return data;
    },
  });
}

export function useSendAnnouncement() {
  return useMutation({
    mutationFn: async (announcementId: number) => {
      const { data } = await api.post(`/announcements/${announcementId}/send`);
      return data;
    },
  });
}

export function useSubmitNormative() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ normativeId, comment, fileId, fileIds }: { normativeId: number; comment?: string; fileId?: number | null; fileIds?: number[] }) => {
      const ids = fileIds?.length ? fileIds : (fileId ? [fileId] : []);
      const { data } = await api.post(`/normatives/${normativeId}/submit`, { comment, file_id: ids[0] ?? undefined, file_ids: ids });
      return data;
    },
    onSuccess: (submission) => {
      queryClient.setQueryData<NormativeSubmission[]>(["normatives", "submissions", "my"], (items) => {
        const list = items ?? [];
        return [submission, ...list.filter((item) => item.id !== submission.id)];
      });
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "my"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "pending"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "history"] });
    },
  });
}

export function useReviewSubmission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      submissionId,
      statusCode,
      reviewerComment,
      gradeValue,
    }: {
      submissionId: number;
      statusCode: string;
      reviewerComment?: string;
      gradeValue?: string;
    }) => {
      const { data } = await api.patch<NormativeSubmission>(`/submissions/${submissionId}/review`, {
        status_code: statusCode,
        reviewer_comment: reviewerComment,
        grade_value: gradeValue,
      });
      return data;
    },
    onSuccess: (submission) => {
      queryClient.setQueryData<NormativeSubmission[]>(["normatives", "submissions", "pending"], (items) =>
        items?.filter((item) => item.id !== submission.id) ?? items,
      );
      queryClient.setQueriesData<NormativeSubmission[]>({ queryKey: ["normatives", "submissions", "history"] }, (items) => {
        const list = items ?? [];
        return [submission, ...list.filter((item) => item.id !== submission.id)];
      });
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "my"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "pending"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "history"] });
    },
  });
}

export function useUpdateDashboardSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (
      items: Array<{
        block_code: string;
        sort_order: number;
        is_hidden: boolean;
        is_pinned: boolean;
        view_mode_code?: string | null;
      }>,
    ) => {
      const { data } = await api.patch<DashboardSetting[]>("/dashboard/settings", { items });
      return data;
    },
    onMutate: async (items) => {
      await queryClient.cancelQueries({ queryKey: ["dashboard", "settings"] });
      const previous = queryClient.getQueryData<DashboardSetting[]>(["dashboard", "settings"]);
      const now = new Date().toISOString();
      queryClient.setQueryData<DashboardSetting[]>(["dashboard", "settings"], (current) => {
        const existing = current ?? previous ?? [];
        const byCode = new Map(existing.map((item) => [item.block_code, item]));
        const userId = existing[0]?.user_id ?? 0;
        return items
          .map((item, index) => {
            const old = byCode.get(item.block_code);
            return {
              id: old?.id ?? -(index + 1),
              user_id: old?.user_id ?? userId,
              block_code: item.block_code,
              sort_order: item.sort_order,
              is_hidden: item.is_hidden,
              is_pinned: item.is_pinned,
              view_mode_code: item.view_mode_code ?? null,
              updated_at: old?.updated_at ?? now,
            };
          })
          .sort((left, right) => left.sort_order - right.sort_order);
      });
      return { previous };
    },
    onError: (_error, _items, context) => {
      if (context?.previous) queryClient.setQueryData(["dashboard", "settings"], context.previous);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["dashboard", "settings"], data);
      queryClient.invalidateQueries({ queryKey: ["dashboard", "settings"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard", "bootstrap"] });
    },
  });
}

export function useResetDashboardSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<{ detail: string }>("/dashboard/settings/reset");
      return data;
    },
    onSuccess: () => {
      queryClient.setQueryData(["dashboard", "settings"], []);
      queryClient.invalidateQueries({ queryKey: ["dashboard", "settings"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard", "bootstrap"] });
    },
  });
}

export function useUsers(enabled: boolean) {
  return useQuery({
    queryKey: ["users"],
    queryFn: async () => {
      const { data } = await api.get<UserRecord[]>("/users");
      return data;
    },
    enabled,
  });
}

export function useUsersBySquad(squadId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["users", "squad", squadId],
    queryFn: async () => {
      const { data } = await api.get<UserRecord[]>(`/users?squad_id=${squadId}`);
      return data;
    },
    enabled: enabled && squadId !== null,
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, ...payload }: { userId: number; squad_id?: number | null; role_code?: string; status_code?: string; full_name?: string }) => {
      const { data } = await api.patch<UserRecord>(`/users/${userId}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["squads", "my"] });
    },
  });
}

export function useAppealMessages(appealId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["appeals", appealId, "messages"],
    queryFn: async () => {
      const { data } = await api.get<AppealMessage[]>(`/appeals/${appealId}/messages`);
      return data;
    },
    enabled: enabled && appealId !== null,
  });
}

export function useCreateAppealMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ appealId, body }: { appealId: number; body: string }) => {
      const { data } = await api.post<AppealMessage>(`/appeals/${appealId}/messages`, { body });
      return data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["appeals", variables.appealId, "messages"] });
    },
  });
}

export function useReadAllNotifications() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post("/notifications/read-all");
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkMaterialViewed() {
  return useMutation({
    mutationFn: async (materialId: number) => {
      const { data } = await api.post(`/learning/materials/${materialId}/view`);
      return data;
    },
  });
}

export function useDownloadFile() {
  return useMutation({
    mutationFn: async ({ fileId, fileName }: { fileId: number; fileName: string }) => {
      const response = await api.get(`/files/${fileId}/download`, { responseType: "blob" });
      const blob = response.data as Blob;
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName || `file-${fileId}`;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useOpenFile() {
  return useMutation({
    mutationFn: async ({ fileId, tgFileId }: { fileId?: number; tgFileId?: string }) => {
      const viewer = window.open("", "_blank");
      try {
        const response = await api.get(
          fileId ? `/files/${fileId}/download` : `/files/tg/${encodeURIComponent(tgFileId ?? "")}`,
          { responseType: "blob" },
        );
        const blob = new Blob([response.data as BlobPart], {
          type: String(response.headers["content-type"] ?? "application/octet-stream"),
        });
        const url = URL.createObjectURL(blob);
        if (viewer) {
          viewer.location.href = url;
        } else {
          window.open(url, "_blank");
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 120000);
      } catch (error) {
        viewer?.close();
        throw error;
      }
    },
  });
}

export function useExportReport() {
  return useMutation({
    mutationFn: async () => {
      const response = await api.get("/reports/export", { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([response.data as BlobPart]));
      const link = document.createElement("a");
      link.href = url;
      link.download = "vpk-report.csv";
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useUploadFile() {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("upload", file);
      const { data } = await api.post<{ id: number; original_name: string; mime_type: string; size_bytes: number }>("/files/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
  });
}

export function useUpdateMe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<{ full_name: string; phone: string; city: string; education_place: string; birth_date: string; if_unmodified_since: string | null }>) => {
      const { data } = await api.patch<UserProfile>("/me", payload);
      return data;
    },
    onSuccess: (profile) => {
      queryClient.setQueryData(["me"], profile);
    },
  });
}

export function useUploadAvatar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("upload", file);
      const { data } = await api.post<UserProfile>("/me/avatar", form);
      return data;
    },
    onSuccess: (profile) => {
      queryClient.setQueryData(["me"], profile);
    },
  });
}

export function useAdminJoinEvents(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "join", "events"],
    queryFn: async () => {
      const { data } = await api.get<CandidateEvent[]>("/admin/join/events");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useCreatePromoBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      title: string;
      body?: string | null;
      button_text?: string | null;
      button_url?: string | null;
      action_type_code?: string | null;
      audience_code?: string;
      style_code?: string;
      sort_order?: number;
      is_active?: boolean;
      active_from?: string | null;
      active_to?: string | null;
    }) => {
      const { data } = await api.post("/admin/promo", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "promo"] });
      queryClient.invalidateQueries({ queryKey: ["promo", "active"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard", "bootstrap"] });
    },
  });
}

export function useUpdatePromoBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; is_active?: boolean; title?: string; body?: string | null; button_text?: string | null; button_url?: string | null; style_code?: string; audience_code?: string; sort_order?: number }) => {
      const { data } = await api.patch<PromoBlock>(`/admin/promo/${id}`, payload);
      return data;
    },
    onSuccess: (block) => {
      queryClient.setQueryData<PromoBlock[]>(["admin", "promo"], (items) => {
        const list = items ?? [];
        const next = list.some((item) => item.id === block.id)
          ? list.map((item) => (item.id === block.id ? block : item))
          : [block, ...list];
        return next.sort((left, right) => left.sort_order - right.sort_order || right.id - left.id);
      });
      queryClient.setQueryData<PromoBlock[]>(["promo", "active"], (items) => {
        const list = (items ?? []).filter((item) => item.id !== block.id);
        if (!block.is_active) return list;
        return [block, ...list].sort((left, right) => left.sort_order - right.sort_order || right.id - left.id);
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "promo"] });
      queryClient.invalidateQueries({ queryKey: ["promo", "active"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard", "bootstrap"] });
    },
  });
}

export function useDeletePromoBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await api.delete(`/admin/promo/${id}`);
      return data;
    },
    onSuccess: (_data, id) => {
      queryClient.setQueryData<PromoBlock[]>(["admin", "promo"], (items) =>
        items?.filter((item) => item.id !== id) ?? items,
      );
      queryClient.setQueryData<PromoBlock[]>(["promo", "active"], (items) =>
        items?.filter((item) => item.id !== id) ?? items,
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "promo"] });
      queryClient.invalidateQueries({ queryKey: ["promo", "active"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard", "bootstrap"] });
    },
  });
}

export function useAdminSquads(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "squads"],
    queryFn: async () => {
      const { data } = await api.get<Squad[]>("/squads");
      return data;
    },
    enabled,
  });
}

export function useCreateSquad() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { name: string; commander_user_id?: number | null; deputy_user_id?: number | null; is_active?: boolean }) => {
      const { data } = await api.post<Squad>("/squads", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "squads"] });
    },
  });
}

export function useUpdateSquad() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; name?: string; commander_user_id?: number | null; deputy_user_id?: number | null; is_active?: boolean }) => {
      const { data } = await api.patch<Squad>(`/squads/${id}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "squads"] });
      queryClient.invalidateQueries({ queryKey: ["squads"] });
      queryClient.invalidateQueries({ queryKey: ["squads", "my"] });
    },
  });
}

export function useMySquad(enabled: boolean) {
  return useQuery({
    queryKey: ["squads", "my"],
    queryFn: async () => {
      const { data } = await api.get<{ squad: Squad | null; members: UserRecord[] }>("/squads/my");
      return data.squad;
    },
    enabled,
  });
}

export function useAdminAppeals(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "appeals"],
    queryFn: async () => {
      const { data } = await api.get<Appeal[]>("/appeals");
      return data;
    },
    enabled,
  });
}

export function useUpdateAppeal() {
  return useMutation({
    mutationFn: async ({ appealId, ...payload }: { appealId: number; status_code?: string; assignee_user_id?: number | null; resolution_text?: string }) => {
      const { data } = await api.patch<Appeal>(`/appeals/${appealId}`, payload);
      return data;
    },
  });
}

export function useAdminUpdateApplication() {
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; status_code?: string; admin_comment?: string }) => {
      const { data } = await api.patch(`/admin/join/applications/${id}`, payload);
      return data;
    },
  });
}

export function useAdminAcceptApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, squad_id }: { id: number; squad_id?: number | null }) => {
      const { data } = await api.post(`/admin/join/applications/${id}/accept`, { squad_id });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "applications"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "squads"] });
      queryClient.invalidateQueries({ queryKey: ["squads"] });
      queryClient.invalidateQueries({ queryKey: ["squads", "my"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useAdminRejectApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, decision_reason }: { id: number; decision_reason?: string }) => {
      const { data } = await api.post(`/admin/join/applications/${id}/reject`, { decision_reason });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "applications"] });
    },
  });
}

export function useAttendanceEvent(eventId: number | null, enabled: boolean, limit = 200, offset = 0) {
  return useQuery({
    queryKey: ["attendance", "event", eventId, limit, offset],
    queryFn: async () => {
      const { data } = await api.get<AttendanceRecord[]>(`/attendance/events/${eventId}`, {
        params: { limit, offset },
      });
      return data;
    },
    enabled: enabled && eventId !== null,
  });
}

export function useMarkAttendance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ eventId, entries }: { eventId: number; entries: Array<{ user_id: number; status_code: string; absence_reason_id?: number | null; comment?: string }> }) => {
      const { data } = await api.post(`/attendance/events/${eventId}/bulk`, { items: entries });
      return data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["attendance", "event", variables.eventId] });
      queryClient.invalidateQueries({ queryKey: ["attendance", "my"] });
      queryClient.invalidateQueries({ queryKey: ["attendance", "stats", "my"] });
      queryClient.invalidateQueries({ queryKey: ["reports", "attendance"] });
    },
  });
}

export function useSelfCheckIn() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (eventId: number) => {
      const { data } = await api.post<AttendanceRecord>(`/schedule/events/${eventId}/self-checkin`);
      return data;
    },
    onSuccess: (attendance) => {
      queryClient.setQueryData<AttendanceRecord[]>(["attendance", "my", 100, 0], (items) => {
        const current = items ?? [];
        return [attendance, ...current.filter((item) => item.id !== attendance.id)];
      });
      queryClient.invalidateQueries({ queryKey: ["attendance"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useAbsenceReasons() {
  return useQuery({
    queryKey: ["absence_reasons"],
    queryFn: async () => {
      const { data } = await api.get<Array<{ id: number; code: string; label: string; requires_comment: boolean; sort_order: number; is_active: boolean }>>("/schedule/absence-reasons");
      return data;
    },
  });
}

export function useMyAttendanceStatsFull(enabled: boolean) {
  return useQuery({
    queryKey: ["attendance", "stats", "full"],
    queryFn: async () => {
      const { data } = await api.get<{ present: number; absent: number; late: number; total: number; percent: number; avg_grade: number | null }>("/attendance/stats/my");
      return data;
    },
    enabled,
  });
}

export function useMyStreak(enabled: boolean) {
  return useQuery({
    queryKey: ["attendance", "streak"],
    queryFn: async () => {
      const { data } = await api.get<{ current_streak: number; best_streak: number; total_events: number; present_count: number; percent: number }>("/attendance/streak/my");
      return data;
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useAdminSchedule(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "schedule"],
    queryFn: async () => {
      const { data } = await api.get<ScheduleEvent[]>("/schedule");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

export function useScheduleWeekType(enabled: boolean) {
  return useQuery({
    queryKey: ["schedule", "current-week-type"],
    queryFn: async () => {
      const { data } = await api.get<{ parity: "A" | "B" | null; week_a_start: string | null }>("/schedule/current-week-type");
      return data;
    },
    enabled,
  });
}

export function useScheduleTemplates(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "schedule", "templates"],
    queryFn: async () => {
      const { data } = await api.get<ScheduleTemplate[]>("/schedule/templates");
      return data;
    },
    enabled,
    ...FAST_QUERY_OPTIONS,
  });
}

type ScheduleEventPayload = {
  title?: string;
  start_datetime?: string;
  end_datetime?: string | null;
  place?: string | null;
  squad_id?: number | null;
  event_type_code?: string;
  requires_response?: boolean;
  self_checkin_enabled?: boolean;
  self_checkin_opens_at?: string | null;
  self_checkin_closes_at?: string | null;
  late_after_minutes?: number;
  description?: string | null;
  status_code?: string;
};

type ScheduleTemplatePayload = {
  title: string;
  description?: string;
  week_days: string;
  week_parity?: "A" | "B" | null;
  start_time: string;
  end_time?: string | null;
  place?: string | null;
  squad_id?: number | null;
  requires_response?: boolean;
  response_deadline_minutes?: number | null;
  is_active?: boolean;
  valid_from?: string | null;
  valid_to?: string | null;
};

export function useCreateScheduleEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ScheduleEventPayload) => {
      const { data } = await api.post<ScheduleEvent>("/schedule/events", payload);
      return data;
    },
    onSuccess: (event) => {
      queryClient.setQueryData<ScheduleEvent[]>(["admin", "schedule"], (items) => {
        const list = items ?? [];
        return [...list.filter((item) => item.id !== event.id), event].sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
      });
      queryClient.setQueryData<ScheduleEvent[]>(["schedule"], (items) => {
        const list = items ?? [];
        return [...list.filter((item) => item.id !== event.id), event].sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule"] });
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
    },
  });
}

export function useUpdateScheduleEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number } & Partial<ScheduleEventPayload>) => {
      const { data } = await api.patch<ScheduleEvent>(`/schedule/events/${id}`, payload);
      return data;
    },
    onSuccess: (event) => {
      const update = (items: ScheduleEvent[] | undefined) => items?.map((item) => item.id === event.id ? event : item) ?? items;
      queryClient.setQueryData<ScheduleEvent[]>(["admin", "schedule"], update);
      queryClient.setQueryData<ScheduleEvent[]>(["schedule"], update);
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule"] });
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
    },
  });
}

export function useCreateScheduleTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: ScheduleTemplatePayload) => {
      const { data } = await api.post<ScheduleTemplate>("/schedule/templates", payload);
      return data;
    },
    onSuccess: (template) => {
      queryClient.setQueryData<ScheduleTemplate[]>(["admin", "schedule", "templates"], (items) => [template, ...(items ?? [])]);
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule", "templates"] });
    },
  });
}

export function useDeleteScheduleTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await api.delete(`/schedule/templates/${id}`);
      return data;
    },
    onSuccess: (_data, id) => {
      queryClient.setQueryData<ScheduleTemplate[]>(["admin", "schedule", "templates"], (items) =>
        items?.filter((template) => template.id !== id) ?? items,
      );
      queryClient.setQueryData<ScheduleEvent[]>(["admin", "schedule"], (items) =>
        items?.map((event) => event.template_id === id ? { ...event, status_code: "CANCELLED" } : event) ?? items,
      );
      queryClient.setQueryData<ScheduleEvent[]>(["schedule"], (items) =>
        items?.map((event) => event.template_id === id ? { ...event, status_code: "CANCELLED" } : event) ?? items,
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule", "templates"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule"] });
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
    },
  });
}

export function useGenerateScheduleTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, days }: { id: number; days: number }) => {
      const { data } = await api.post<ScheduleEvent[]>(`/schedule/templates/${id}/generate?days=${days}`);
      return data;
    },
    onSuccess: (events) => {
      const mergeEvents = (items: ScheduleEvent[] | undefined) => {
        const byId = new Map((items ?? []).map((item) => [item.id, item]));
        for (const event of events) byId.set(event.id, event);
        return Array.from(byId.values()).sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
      };
      queryClient.setQueryData<ScheduleEvent[]>(["admin", "schedule"], mergeEvents);
      queryClient.setQueryData<ScheduleEvent[]>(["schedule"], mergeEvents);
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule"] });
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
    },
  });
}

export function useDeleteScheduleEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/schedule/events/${id}`);
      return id;
    },
    onSuccess: (id) => {
      const markCancelled = (items: ScheduleEvent[] | undefined) =>
        items?.map((item) => item.id === id ? { ...item, status_code: "CANCELLED" } : item) ?? items;
      queryClient.setQueryData<ScheduleEvent[]>(["admin", "schedule"], markCancelled);
      queryClient.setQueryData<ScheduleEvent[]>(["schedule"], markCancelled);
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule"] });
      queryClient.invalidateQueries({ queryKey: ["schedule"] });
    },
  });
}

export function useAdminUsersSearch(search: string, enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "users", "search", search],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      const { data } = await api.get<UserRecord[]>(`/admin/users?${params}`);
      return data;
    },
    enabled,
  });
}

export function useAdminUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, ...payload }: { userId: number; squad_id?: number | null; role_code?: string; status_code?: string; full_name?: string }) => {
      const { data } = await api.patch<UserRecord>(`/admin/users/${userId}`, payload);
      return data;
    },
    onSuccess: (user) => {
      queryClient.setQueryData<UserRecord[]>(["admin", "users"], (items) =>
        items?.map((item) => (item.id === user.id ? user : item)) ?? items,
      );
      queryClient.setQueryData<UserRecord[]>(["users"], (items) =>
        items?.map((item) => (item.id === user.id ? user : item)) ?? items,
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useDeactivateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (userId: number) => {
      const { data } = await api.patch<UserRecord>(`/admin/users/${userId}/deactivate`);
      return data;
    },
    onSuccess: (user) => {
      queryClient.setQueryData<UserRecord[]>(["admin", "users"], (items) =>
        items?.map((item) => (item.id === user.id ? user : item)) ?? items,
      );
      queryClient.setQueryData<UserRecord[]>(["users"], (items) =>
        items?.map((item) => (item.id === user.id ? user : item)) ?? items,
      );
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}

export function useNormativesAdmin(enabled: boolean) {
  return useQuery({
    queryKey: ["normatives", "admin"],
    queryFn: async () => {
      const { data } = await api.get<Normative[]>("/normatives?active_only=false");
      return data;
    },
    enabled,
    ...LIVE_QUERY_OPTIONS,
  });
}

export function useCreateNormative() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { title: string; description?: string; type_code?: string; target_audience?: string; squad_id?: number | null; instruction_video_file_id?: number | null; instruction_video_url?: string | null; is_active?: boolean }) => {
      const { data } = await api.post<Normative>("/normatives", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["normatives"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "admin"] });
    },
  });
}

export function useUpdateNormative() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; title?: string; description?: string; is_active?: boolean; target_audience?: string; squad_id?: number | null; instruction_video_file_id?: number | null; instruction_video_url?: string | null }) => {
      const { data } = await api.patch<Normative>(`/normatives/${id}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["normatives"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "admin"] });
    },
  });
}

export function useDeleteNormative() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      const { data } = await api.delete(`/normatives/${id}`);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["normatives"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "admin"] });
    },
  });
}

export function useAdminLearningMaterials(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "learning", "materials"],
    queryFn: async () => {
      const { data } = await api.get<LearningMaterial[]>("/learning/materials?active_only=false");
      return data;
    },
    enabled,
  });
}

export function useAdminLearningCourses(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "learning", "courses"],
    queryFn: async () => {
      const { data } = await api.get<LearningCourse[]>("/learning/courses?active_only=false");
      return data;
    },
    enabled,
  });
}

export function useCreateLearningMaterial() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { title: string; description?: string; type_code?: string; file_id?: number | null; external_url?: string; audience_code?: string; sort_order?: number; is_active?: boolean; course_id?: number | null; duration_minutes?: number | null }) => {
      const { data } = await api.post<LearningMaterial>("/admin/learning/materials", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "learning", "materials"] });
      queryClient.invalidateQueries({ queryKey: ["learning", "materials"] });
    },
  });
}

export function useUpdateLearningMaterial() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; title?: string; description?: string; type_code?: string; file_id?: number | null; is_active?: boolean; external_url?: string; audience_code?: string; course_id?: number | null; duration_minutes?: number | null; sort_order?: number }) => {
      const { data } = await api.patch<LearningMaterial>(`/admin/learning/materials/${id}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "learning", "materials"] });
      queryClient.invalidateQueries({ queryKey: ["learning", "materials"] });
    },
  });
}

export function useCreateLearningCourse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { title: string; description?: string; audience_code?: string; sort_order?: number; is_active?: boolean }) => {
      const { data } = await api.post<LearningCourse>("/admin/learning/courses", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "learning", "courses"] });
      queryClient.invalidateQueries({ queryKey: ["learning", "courses"] });
    },
  });
}

export function useUpdateLearningCourse() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; title?: string; description?: string; is_active?: boolean; audience_code?: string }) => {
      const { data } = await api.patch<LearningCourse>(`/admin/learning/courses/${id}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "learning", "courses"] });
      queryClient.invalidateQueries({ queryKey: ["learning", "courses"] });
    },
  });
}

export function useCreateCandidateEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { title: string; description?: string; event_type_code?: string; start_datetime: string; end_datetime?: string; place?: string; capacity?: number | null; is_active?: boolean }) => {
      const { data } = await api.post<CandidateEvent>("/admin/join/events", payload);
      return data;
    },
    onSuccess: (event) => {
      queryClient.setQueryData<CandidateEvent[]>(["admin", "join", "events"], (items) => {
        const list = items ?? [];
        return [event, ...list.filter((item) => item.id !== event.id)].sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "join", "events"] });
      queryClient.invalidateQueries({ queryKey: ["public", "events"] });
    },
  });
}

export function useUpdateCandidateEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; title?: string; description?: string; start_datetime?: string; end_datetime?: string; place?: string; is_active?: boolean }) => {
      const { data } = await api.patch<CandidateEvent>(`/admin/join/events/${id}`, payload);
      return data;
    },
    onSuccess: (event) => {
      queryClient.setQueryData<CandidateEvent[]>(["admin", "join", "events"], (items) =>
        items?.map((item) => (item.id === event.id ? event : item)) ?? items,
      );
      queryClient.setQueryData<CandidateEvent[]>(["public", "events"], (items) => {
        const list = (items ?? []).filter((item) => item.id !== event.id);
        if (!event.is_active) return list;
        return [event, ...list].sort((a, b) => a.start_datetime.localeCompare(b.start_datetime));
      });
      queryClient.invalidateQueries({ queryKey: ["admin", "join", "events"] });
      queryClient.invalidateQueries({ queryKey: ["public", "events"] });
    },
  });
}

export function useAdminAuditFiltered(params: { user_id?: number; action_code?: string; entity_name?: string; offset?: number }, enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "audit", "filtered", params],
    queryFn: async () => {
      const q = new URLSearchParams({ limit: "100" });
      if (params.user_id) q.set("user_id", String(params.user_id));
      if (params.action_code) q.set("action_code", params.action_code);
      if (params.entity_name) q.set("entity_name", params.entity_name);
      if (params.offset) q.set("offset", String(params.offset));
      const { data } = await api.get<AuditLog[]>(`/admin/audit?${q}`);
      return data;
    },
    enabled,
  });
}

export function useAdminSettings(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "settings"],
    queryFn: async () => {
      const { data } = await api.get<Array<{ id: number; key: string; value: string | null; description: string | null; updated_at: string }>>("/admin/settings");
      return data;
    },
    enabled,
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (values: Record<string, string | null>) => {
      const { data } = await api.patch("/admin/settings", { values });
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "settings"] });
    },
  });
}

export function useExportUsersCSV() {
  return useMutation({
    mutationFn: async (params: { squad_id?: number | null; search?: string }) => {
      const q = new URLSearchParams();
      if (params.squad_id) q.set("squad_id", String(params.squad_id));
      if (params.search) q.set("search", params.search);
      const response = await api.get(`/admin/users/export.csv?${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([response.data as BlobPart], { type: "text/csv;charset=utf-8;" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "roster.csv";
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useExportUsersXLSX() {
  return useMutation({
    mutationFn: async (params: { squad_id?: number | null; search?: string }) => {
      const q = new URLSearchParams();
      if (params.squad_id) q.set("squad_id", String(params.squad_id));
      if (params.search) q.set("search", params.search);
      const response = await api.get(`/admin/users/export.xlsx?${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([response.data as BlobPart]));
      const link = document.createElement("a");
      link.href = url;
      link.download = "roster.xlsx";
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useExportAttendanceMatrix() {
  return useMutation({
    mutationFn: async (params?: { squad_id?: number | null; month?: string }) => {
      const q = new URLSearchParams();
      if (params?.squad_id) q.set("squad_id", String(params.squad_id));
      if (params?.month) q.set("month", params.month);
      const response = await api.get(`/reports/attendance/matrix.xlsx?${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([response.data as BlobPart]));
      const link = document.createElement("a");
      link.href = url;
      link.download = `attendance-${params?.month ?? "month"}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
    },
  });
}

export function useExportCSVviaBot() {
  return useMutation({
    mutationFn: async (params: { squad_id?: number | null; search?: string }) => {
      const q = new URLSearchParams();
      if (params.squad_id) q.set("squad_id", String(params.squad_id));
      if (params.search) q.set("search", params.search);
      await api.post(`/admin/users/export.csv/send?${q}`);
    },
  });
}

export function useExportXLSXviaBot() {
  return useMutation({
    mutationFn: async (params: { squad_id?: number | null; search?: string }) => {
      const q = new URLSearchParams();
      if (params.squad_id) q.set("squad_id", String(params.squad_id));
      if (params.search) q.set("search", params.search);
      await api.post(`/admin/users/export.xlsx/send?${q}`);
    },
  });
}

export function useExportReportViaBot() {
  return useMutation({
    mutationFn: async (params?: { squad_id?: number | null }) => {
      const q = new URLSearchParams();
      if (params?.squad_id) q.set("squad_id", String(params.squad_id));
      await api.post(`/reports/export/send?${q}`);
    },
  });
}

export function useExportAttendanceCSVviaBot() {
  return useMutation({
    mutationFn: async (params?: { squad_id?: number | null }) => {
      const q = new URLSearchParams();
      if (params?.squad_id) q.set("squad_id", String(params.squad_id));
      await api.post(`/reports/attendance/export.csv/send?${q}`);
    },
  });
}

export function useExportAttendanceXLSXviaBot() {
  return useMutation({
    mutationFn: async (params?: { squad_id?: number | null }) => {
      const q = new URLSearchParams();
      if (params?.squad_id) q.set("squad_id", String(params.squad_id));
      await api.post(`/reports/attendance/export.xlsx/send?${q}`);
    },
  });
}

export function useGetFileBlob() {
  return useMutation({
    mutationFn: async (fileId: number): Promise<string> => {
      const response = await api.get(`/files/${fileId}/download`, { responseType: "blob" });
      const mimeType = String(response.headers["content-type"] ?? "video/mp4");
      const blob = new Blob([response.data as BlobPart], { type: mimeType });
      return URL.createObjectURL(blob);
    },
  });
}

export function useSendFileToBotDM() {
  return useMutation({
    mutationFn: async (fileId: number) => {
      await api.post(`/files/${fileId}/send-to-tg`);
    },
  });
}

export function usePublicUsers(enabled: boolean) {
  return useQuery({
    queryKey: ["admin", "users", "public_only"],
    queryFn: async () => {
      const { data } = await api.get<UserRecord[]>("/admin/users?exclude_public=false&role_code=PUBLIC_USER");
      return data;
    },
    enabled,
  });
}

export function useActivityFeed(enabled: boolean) {
  return useQuery({
    queryKey: ["reports", "activity-feed"],
    queryFn: async () => {
      const { data } = await api.get<Array<{ type: string; text: string; created_at: string }>>("/reports/activity-feed");
      return data;
    },
    enabled,
    refetchInterval: 60 * 1000, // refresh every minute
  });
}
