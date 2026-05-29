import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, setAccessToken } from "./client";
import type {
  Announcement,
  Appeal,
  AppealMessage,
  AuditLog,
  AttendanceRecord,
  AuthResponse,
  CandidateEvent,
  DashboardSetting,
  JoinApplication,
  LearningCourse,
  MenuCard,
  Normative,
  NormativeSubmission,
  Notification,
  PromoBlock,
  PublicContent,
  ReportSummary,
  ScheduleEvent,
  ScheduleTemplate,
  LearningMaterial,
  Squad,
  UserProfile,
  UserRecord,
} from "../types/api";

export function useTelegramAuth() {
  return useMutation({
    mutationFn: async (initData: string) => {
      const { data } = await api.post<AuthResponse>("/auth/telegram", { init_data: initData });
      setAccessToken(data.access_token);
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

export function useSchedule(enabled: boolean) {
  return useQuery({
    queryKey: ["schedule"],
    queryFn: async () => {
      const { data } = await api.get<ScheduleEvent[]>("/schedule");
      return data;
    },
    enabled,
  });
}

export function useMyAttendance(enabled: boolean) {
  return useQuery({
    queryKey: ["attendance", "my"],
    queryFn: async () => {
      const { data } = await api.get<AttendanceRecord[]>("/attendance/my");
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
  });
}

export function useMyNormativeSubmissions(enabled: boolean) {
  return useQuery({
    queryKey: ["normatives", "submissions", "my"],
    queryFn: async () => {
      const { data } = await api.get<NormativeSubmission[]>("/submissions/my");
      return data;
    },
    enabled,
  });
}

export function usePendingNormativeSubmissions(enabled: boolean) {
  return useQuery({
    queryKey: ["normatives", "submissions", "pending"],
    queryFn: async () => {
      const { data } = await api.get<NormativeSubmission[]>("/submissions/pending");
      return data;
    },
    enabled,
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
  });
}

export function useLearningMaterials(enabled: boolean) {
  return useQuery({
    queryKey: ["learning", "materials"],
    queryFn: async () => {
      const { data } = await api.get<LearningMaterial[]>("/learning/materials");
      return data;
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
    onSuccess: () => {
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
  return useMutation({
    mutationFn: async (notificationId: number) => {
      const { data } = await api.patch(`/notifications/${notificationId}/read`);
      return data;
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "my"] });
      queryClient.invalidateQueries({ queryKey: ["normatives", "submissions", "pending"] });
    },
  });
}

export function useReviewSubmission() {
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
      const { data } = await api.patch(`/submissions/${submissionId}/review`, {
        status_code: statusCode,
        reviewer_comment: reviewerComment,
        grade_value: gradeValue,
      });
      return data;
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
    onSuccess: (data) => {
      queryClient.setQueryData(["dashboard", "settings"], data);
    },
  });
}

export function useResetDashboardSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await api.post<DashboardSetting[]>("/dashboard/settings/reset");
      return data;
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["dashboard", "settings"], data);
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
    mutationFn: async (payload: Partial<{ full_name: string; phone: string; city: string; education_place: string; birth_date: string }>) => {
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
    },
  });
}

export function useUpdatePromoBlock() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, ...payload }: { id: number; is_active?: boolean; title?: string; body?: string | null; button_text?: string | null; button_url?: string | null; style_code?: string; audience_code?: string; sort_order?: number }) => {
      const { data } = await api.patch(`/admin/promo/${id}`, payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "promo"] });
      queryClient.invalidateQueries({ queryKey: ["promo", "active"] });
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "promo"] });
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

export function useAttendanceEvent(eventId: number | null, enabled: boolean) {
  return useQuery({
    queryKey: ["attendance", "event", eventId],
    queryFn: async () => {
      const { data } = await api.get<AttendanceRecord[]>(`/attendance/events/${eventId}`);
      return data;
    },
    enabled: enabled && eventId !== null,
  });
}

export function useMarkAttendance() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ eventId, entries }: { eventId: number; entries: Array<{ user_id: number; status_code: string; absence_reason_id?: number | null; comment?: string }> }) => {
      const { data } = await api.post(`/attendance/events/${eventId}/mark`, { items: entries });
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
    onSuccess: () => {
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
    onSuccess: () => {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "schedule", "templates"] });
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
    onSuccess: () => {
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
    },
    onSuccess: () => {
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
    onSuccess: () => {
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
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
    onSuccess: () => {
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
    onSuccess: () => {
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
