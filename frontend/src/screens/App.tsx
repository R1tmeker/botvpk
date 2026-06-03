import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart3,
  AlertTriangle,
  Bell,
  BookOpen,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  ClipboardCheck,
  ClipboardList,
  Download,
  Dumbbell,
  Flag,
  Flame,
  Home,
  Megaphone,
  MessageSquareWarning,
  RefreshCw,
  Settings,
  Target,
  User,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  useAbsenceReasons,
  useActivityFeed,
  useAdminApplications,
  useAdminAudit,
  useAdminMenu,
  useAdminPromo,
  useAdminSquads,
  useAdminUsers,
  useAnnouncements,
  useAppealMessages,
  useAppeals,
  useAttendanceReport,
  useCreateAnnouncement,
  useCreateAppeal,
  useCreateAppealMessage,
  useCreateJoinApplication,
  useCreateSquad,
  useDashboardSettings,
  useGradesReport,
  useJoinEvents,
  useJoinMe,
  useLearningCourses,
  useLearningMaterials,
  useMarkMaterialViewed,
  useMenu,
  useMyAttendance,
  useMyAttendanceStats,
  useMarkAttendance,
  useMyNormativeSubmissions,
  useMySquad,
  useNormatives,
  useNormativesReport,
  useNotifications,
  useNormativeSubmissionsHistory,
  useOpenFile,
  usePendingNormativeSubmissions,
  usePromo,
  usePublicContent,
  usePublicEvents,
  useReadAllNotifications,
  useReadNotification,
  useResetDashboardSettings,
  useReviewSubmission,
  useRespondEvent,
  useRespondCandidateEvent,
  useSendAnnouncement,
  useSchedule,
  useSquads,
  useSubmitNormative,
  useTelegramAuth,
  useUpdateDashboardSettings,
  useUpdateMe,
  useUploadAvatar,
  useUploadFile,
  useUsers,
  useAdminAcceptApplication,
  useAdminRejectApplication,
  useMyStreak,
  useCreatePromoBlock,
  useUpdatePromoBlock,
  useDeletePromoBlock,
  useDeleteScheduleTemplate,
  useAttendanceEvent,
  useUpdateMenuCard,
  useAdminSchedule,
  useCreateScheduleEvent,
  useCreateScheduleTemplate,
  useDeleteScheduleEvent,
  useGenerateScheduleTemplate,
  useScheduleTemplates,
  useScheduleWeekType,
  useUpdateScheduleEvent,
  useUpdateSquad,
  useUpdateUser,
  useAdminAppeals,
  useUpdateAppeal,
  useAdminJoinEvents,
  useAdminUpdateApplication,
  useCreateCandidateEvent,
  useUpdateCandidateEvent,
  useNormativesAdmin,
  useCreateNormative,
  useUpdateNormative,
  useDeleteNormative,
  useAdminLearningMaterials,
  useAdminLearningCourses,
  useCreateLearningMaterial,
  useUpdateLearningMaterial,
  useCreateLearningCourse,
  useUpdateLearningCourse,
  useAdminAuditFiltered,
  useAdminUpdateUser,
  useDeactivateUser,
  useAdminSettings,
  useUpdateSettings,
  usePublicUsers,
  useExportCSVviaBot,
  useExportXLSXviaBot,
  useExportReportViaBot,
  useGetFileBlob,
  useSendFileToBotDM,
  useEventResponses,
  useJoinHistory,
  type ApplicationHistoryItem,
  type EventResponseItem,
} from "../api/queries";
import { api } from "../api/client";
import type {
  Appeal,
  AppealMessage,
  Announcement,
  AuditLog,
  AttendanceRecord,
  CandidateEvent,
  DashboardSetting,
  JoinApplication,
  LearningCourse,
  LearningMaterial,
  MenuCard,
  Normative,
  NormativeSubmission,
  Notification,
  PromoBlock,
  PublicContent,
  ReportSummary,
  RoleCode,
  ScheduleEvent,
  ScheduleTemplate,
  Squad,
  UserProfile,
  UserRecord,
} from "../types/api";
import styles from "./App.module.scss";
import {
  AnimatedProgress,
  AttendanceDonut,
  BarChart,
  CalendarHeatmap,
  GradeDistribution,
  StatNumber,
} from "../components/Charts";
import { ToastContainer, toast } from "../components/Toast";
import { PromoCard, PromoStrip, AdminPromoCard, PromoEditForm } from "../components/PromoCard";
import { MilestoneToast } from "../components/Confetti";

function FilePicker({ accept, onFile, label = "Прикрепить файл", className, iconSrc }: {
  accept: string;
  onFile: (file: File) => void;
  label?: string;
  className?: string;
  iconSrc?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className={className} onClick={() => ref.current?.click()} aria-label={label} title={label}>
        {iconSrc ? <img src={iconSrc} alt="" aria-hidden="true" /> : label}
      </button>
      <input
        ref={ref}
        type="file"
        accept={accept}
        style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
      />
    </>
  );
}

const FILE_PREVIEW_ACCEPT = "video/*,image/*,application/pdf";
const PAPERCLIP_ICON_SRC = "/assets/icons/paperclip.png";
const PENDING_NORMATIVE_STATUSES = new Set(["SUBMITTED", "PENDING", "PENDING_REVIEW"]);

function isPendingNormativeStatus(statusCode: string): boolean {
  return PENDING_NORMATIVE_STATUSES.has(statusCode);
}

function toYouTubeEmbedUrl(url: string): string | null {
  const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([^&?/]+)/);
  if (m) return `https://www.youtube.com/embed/${m[1]}?autoplay=1`;
  return null;
}

function VideoPlayerModal({ src, embedSrc, onClose }: { src?: string; embedSrc?: string; onClose: () => void }) {
  return (
    <div className={styles.videoOverlay} onClick={onClose}>
      <div className={styles.videoModalBox} onClick={(e) => e.stopPropagation()}>
        <button type="button" className={styles.videoCloseBtn} onClick={onClose} aria-label="Закрыть">✕</button>
        {embedSrc ? (
          <iframe
            src={embedSrc}
            className={styles.videoPlayer}
            allowFullScreen
            allow="autoplay; encrypted-media"
            title="Видео"
          />
        ) : src ? (
          <video src={src} controls autoPlay playsInline className={styles.videoPlayer} />
        ) : null}
      </div>
    </div>
  );
}

function VideoThumbnailCard({ title, isLoading, onClick }: { title: string; isLoading?: boolean; onClick: () => void }) {
  return (
    <div className={styles.videoCard} onClick={!isLoading ? onClick : undefined} role="button" tabIndex={0}>
      <div className={styles.videoCardThumb}>
        {isLoading ? (
          <div className={styles.videoLoadingSpinner} />
        ) : (
          <svg width="52" height="52" viewBox="0 0 52 52" fill="white" aria-hidden="true">
            <circle cx="26" cy="26" r="26" fill="rgba(0,0,0,0.55)" />
            <path d="M21 18l16 8-16 8V18z" />
          </svg>
        )}
      </div>
      <div className={styles.videoCardMeta}>{title}</div>
    </div>
  );
}

function materialTypeFromMime(mimeType?: string | null) {
  if (!mimeType) return "FILE";
  if (mimeType.startsWith("video/")) return "VIDEO";
  if (mimeType.startsWith("image/")) return "IMAGE";
  if (mimeType === "application/pdf") return "PDF";
  return "FILE";
}

/* ─────────── ApplicantDetailDrawer ─────────── */
const APP_STATUS_COLOR: Record<string, string> = {
  NEW: "#1a2f5a",
  REVIEWING: "#3498db",
  NEEDS_INFO: "#f39c12",
  INVITED_MEETING: "#9b59b6",
  INVITED_NORMATIVES: "#e67e22",
  AWAITING_DECISION: "#16a085",
  ACCEPTED: "#27ae60",
  REJECTED: "#e74c3c",
  ARCHIVED: "#8a96b0",
};

function ApplicantDetailDrawer({
  app,
  publicUser,
  rosterUser,
  squads,
  applicationSquad,
  rejectReason,
  isBusy,
  onSquadChange,
  onRejectReasonChange,
  onInviteNormatives,
  onAccept,
  onReject,
  onClose,
}: {
  app?: JoinApplication | null;
  publicUser?: UserRecord | null;
  rosterUser?: UserRecord | null;
  squads: Squad[];
  applicationSquad?: string;
  rejectReason?: string;
  isBusy: boolean;
  onSquadChange?: (v: string) => void;
  onRejectReasonChange?: (v: string) => void;
  onInviteNormatives?: () => void;
  onAccept?: () => void;
  onReject?: () => void;
  onClose: () => void;
}) {
  const item = app ?? publicUser ?? rosterUser;
  if (!item) return null;

  const statusLabel = app ? (applicationStatusLabels[app.status_code] ?? app.status_code) : null;
  const statusColor = app ? (APP_STATUS_COLOR[app.status_code] ?? "#65708a") : null;

  const isInvited = app && app.status_code === "INVITED_NORMATIVES";
  const isNew = app && ["NEW", "REVIEWING", "NEEDS_INFO", "AWAITING_DECISION"].includes(app.status_code);
  const isClosed = app && ["ACCEPTED", "REJECTED", "ARCHIVED"].includes(app.status_code);

  const field = (label: string, value: string | null | undefined) =>
    value ? (
      <div className={styles.detailRow} key={label}>
        <span className={styles.detailLabel}>{label}</span>
        <span className={styles.detailValue}>{value}</span>
      </div>
    ) : null;

  return (
    <div className={styles.drawerOverlay} onClick={onClose}>
      <div className={styles.drawerSheet} onClick={(e) => e.stopPropagation()}>
        <div className={styles.drawerHandle} />
        <div className={styles.drawerHeader}>
          <div>
            <strong className={styles.drawerName}>{item.full_name}</strong>
            {item.username && <span className={styles.drawerUsername}>@{item.username}</span>}
          </div>
          {statusLabel && (
            <span className={styles.drawerStageBadge} style={{ background: statusColor ?? "#65708a" }}>
              {statusLabel}
            </span>
          )}
        </div>

        <div className={styles.detailGrid}>
          {field("Telegram ID", String(item.telegram_id))}
          {app && field("Дата подачи", formatDate(app.created_at))}
          {!app && rosterUser && field("В составе с", formatDate(rosterUser.linked_at ?? rosterUser.created_at))}
          {!app && publicUser && field("Нажал /start", formatDate(publicUser.created_at))}
          {app?.birth_date && field("Дата рождения", formatShortDate(new Date(app.birth_date)))}
          {!app && (item as UserRecord).birth_date && field("Дата рождения", formatShortDate(new Date((item as UserRecord).birth_date!)))}
          {field("Телефон", app?.phone ?? (item as UserRecord).phone)}
          {field("Город", app?.city ?? (item as UserRecord).city)}
          {field("Учёба / работа", app?.education_place ?? (item as UserRecord).education_place)}
          {app?.experience_text && field("Опыт", app.experience_text)}
          {app?.motivation_text && (
            <div className={styles.detailRow}>
              <span className={styles.detailLabel}>Мотивация</span>
              <span className={`${styles.detailValue} ${styles.detailLong}`}>{app.motivation_text}</span>
            </div>
          )}
          {app?.source_text && field("Откуда узнал", app.source_text)}
          {app?.comment && field("Комментарий", app.comment)}
          {app?.admin_comment && field("Комментарий команды", app.admin_comment)}
          {app?.decision_reason && field("Причина решения", app.decision_reason)}
          {rosterUser && field("Отделение", squads.find((s) => s.id === rosterUser.squad_id)?.name ?? "—")}
        </div>

        {!isClosed && app && (
          <div className={styles.drawerActions}>
            <input
              className={styles.drawerInput}
              placeholder="Комментарий / причина"
              value={rejectReason ?? ""}
              onChange={(e) => onRejectReasonChange?.(e.target.value)}
            />
            {isNew && (
              <button type="button" className={styles.drawerBtnWarning} disabled={isBusy} onClick={onInviteNormatives}>
                Пригласить на нормативы
              </button>
            )}
            {isInvited && (
              <>
                <select
                  className={styles.drawerSelect}
                  value={applicationSquad ?? ""}
                  onChange={(e) => onSquadChange?.(e.target.value)}
                  disabled={isBusy}
                >
                  <option value="">Выбрать отделение</option>
                  {squads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <button type="button" className={styles.drawerBtnSuccess} disabled={isBusy} onClick={onAccept}>
                  Принять в состав
                </button>
              </>
            )}
            <button type="button" className={styles.drawerBtnDanger} disabled={isBusy} onClick={onReject}>
              Отклонить
            </button>
          </div>
        )}

        <button type="button" className={styles.drawerCloseBtn} onClick={onClose}>Закрыть</button>
      </div>
    </div>
  );
}

function apiErrorDetail(error: unknown): string | null {
  if (typeof error !== "object" || error === null || !("response" in error)) return null;
  const response = (error as { response?: { data?: unknown } }).response;
  const data = response?.data;
  if (typeof data === "string") return data;
  if (typeof data !== "object" || data === null || !("detail" in data)) return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join(", ");
  return null;
}

function scheduleTemplateErrorMessage(error: unknown): string {
  const detail = apiErrorDetail(error);
  if (!detail) return "Не удалось сгенерировать шаблон";
  if (detail.includes("schedule_week_a_start")) {
    return "Для недель 1/2 укажите «Дата начала недели 1» в настройках.";
  }
  if (detail.includes("Week days")) {
    return "Дни недели укажите числами 1-7 через запятую.";
  }
  return detail;
}

type Props = {
  webApp: {
    initData: string;
    initDataUnsafe?: {
      user?: {
        id?: number;
        first_name?: string;
        last_name?: string;
        username?: string;
      };
    };
    HapticFeedback?: {
      impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
      notificationOccurred?: (type: "error" | "success" | "warning") => void;
    };
    BackButton?: { show: () => void; hide: () => void; onClick: (fn: () => void) => void; offClick: (fn: () => void) => void };
    MainButton?: { show: () => void; hide: () => void; setText: (t: string) => void; onClick: (fn: () => void) => void; offClick: (fn: () => void) => void; showProgress: (b: boolean) => void };
    close?: () => void;
  };
};

type AuthStatus = "checking" | "ready" | "missing_init_data" | "failed";

function AuthGate({
  status,
  error,
  initDataLength,
  telegramUserId,
  onAction,
}: {
  status: AuthStatus;
  error: string | null;
  initDataLength: number;
  telegramUserId: number | null;
  onAction: () => void;
}) {
  const title = status === "missing_init_data" ? "Telegram ID не передан" : "Авторизация не прошла";
  const text = status === "missing_init_data"
    ? "Откройте приложение через кнопку в боте. Обычная ссылка не передаёт Telegram ID."
    : "Закройте это окно и откройте свежую кнопку Mini App в @VPK_OPROS_ZOV_bot. Повтор внутри старого окна отправляет ту же подпись.";
  const actionLabel = status === "missing_init_data" ? "Проверить снова" : "Закрыть Mini App";

  return (
    <section className={`${styles.panel} ${styles.authGate}`}>
      <span className={styles.authGateIcon}>
        <AlertTriangle />
      </span>
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
      <dl className={styles.authGateMeta}>
        <div>
          <dt>Telegram</dt>
          <dd>{telegramUserId ?? "не передан"}</dd>
        </div>
        <div>
          <dt>initData</dt>
          <dd>{initDataLength > 0 ? `${initDataLength} символов` : "пусто"}</dd>
        </div>
        {error && (
          <div>
            <dt>Backend</dt>
            <dd>{error}</dd>
          </div>
        )}
      </dl>
      <div className={styles.authGateActions}>
        <button type="button" onClick={onAction}>
          {status === "missing_init_data" ? <RefreshCw /> : <X />}
          {actionLabel}
        </button>
      </div>
    </section>
  );
}

type ViewKey =
  | "dashboard"
  | "schedule"
  | "attendance"
  | "normatives"
  | "learning"
  | "notifications"
  | "announcements"
  | "appeals"
  | "reports"
  | "people"
  | "profile"
  | "admin";

type JoinApplicationPayload = {
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
};

type AppealPayload = {
  subject: string;
  description: string;
  category_code: string;
  urgency_code: string;
  is_anonymous: boolean;
  file_id?: number | null;
};

type AnnouncementPayload = {
  title: string;
  body: string;
  target_type: string;
  target_squad_id?: number | null;
  target_role_code?: string | null;
  file_id?: number | null;
  status_code: string;
  send_to_tg: boolean;
  send_to_app: boolean;
};

const fallbackProfile: UserProfile = {
  id: null,
  telegram_id: 0,
  username: null,
  full_name: "Гость",
  squad_id: null,
  avatar_file_id: null,
  role_code: "PUBLIC_USER",
  status_code: "ACTIVE",
  birth_date: null,
  phone: null,
  city: null,
  education_place: null,
};

const roleLabels: Record<RoleCode, string> = {
  PUBLIC_USER: "Новый пользователь",
  CANDIDATE: "Кандидат",
  USER_PENDING: "Ожидает привязки",
  PARTICIPANT: "Участник",
  DEPUTY_SQUAD_COMMANDER: "Зам. командира отделения",
  SQUAD_COMMANDER: "Командир отделения",
  DEPUTY_PLATOON_COMMANDER: "Зам. командира взвода",
  PLATOON_COMMANDER: "Командир взвода",
  ADMIN: "Администратор",
  SUPER_ADMIN: "Супер-администратор",
};

const applicationStatusLabels: Record<string, string> = {
  NEW: "Новая",
  REVIEWING: "На рассмотрении",
  NEEDS_INFO: "Нужна информация",
  INVITED_MEETING: "Приглашён на встречу",
  INVITED_NORMATIVES: "Приглашён на нормативы",
  AWAITING_DECISION: "Ожидает решения",
  ACCEPTED: "Принят",
  REJECTED: "Отклонён",
  ARCHIVED: "Архив",
};

const roleLevels: Record<RoleCode, number> = {
  PUBLIC_USER: 0,
  CANDIDATE: 1,
  USER_PENDING: 2,
  PARTICIPANT: 3,
  DEPUTY_SQUAD_COMMANDER: 4,
  SQUAD_COMMANDER: 5,
  DEPUTY_PLATOON_COMMANDER: 6,
  PLATOON_COMMANDER: 7,
  ADMIN: 8,
  SUPER_ADMIN: 9,
};

type DashboardBlockCode = "next_event" | "personal_stats" | "commander_summary" | "normatives" | "notifications" | "promo";

const dashboardBlocks: Array<{ code: DashboardBlockCode; title: string; required: boolean; commanderOnly?: boolean }> = [
  { code: "next_event", title: "Ближайшее занятие", required: true },
  { code: "personal_stats", title: "Личная статистика", required: false },
  { code: "commander_summary", title: "Сводка отделения", required: false, commanderOnly: true },
  { code: "normatives", title: "Активные нормативы", required: false },
  { code: "notifications", title: "Уведомления", required: false },
  { code: "promo", title: "Инфоблок", required: false },
];

const iconByCode: Record<string, LucideIcon> = {
  dashboard: Home,
  home: Home,
  schedule: CalendarDays,
  attendance: ClipboardCheck,
  mark_attendance: ClipboardList,
  normatives: Target,
  norms: Dumbbell,
  learning: BookOpen,
  notifications: Bell,
  announcements: Megaphone,
  appeals: MessageSquareWarning,
  reports: BarChart3,
  admin: Settings,
  profile: User,
  people: Users,
  squads: Users,
  join: Flag,
  full_roster: Users,
  my_squad: Users,
  appeal: MessageSquareWarning,
  download: Download,
};

function AppIcon({ code, className }: { code: string | null | undefined; className?: string }) {
  const Icon = iconByCode[code ?? ""] ?? Settings;
  return <Icon className={className ?? styles.appIcon} aria-hidden="true" strokeWidth={2} />;
}

function roleMenu(profile: UserProfile): MenuCard[] {
  const level = roleLevels[profile.role_code];
  const cards: MenuCard[] = [
    menuCard("schedule", "Расписание", "занятия, сборы и ответы", "schedule"),
    menuCard("people", "Состав", "отделение и общий список", "full_roster"),
    menuCard("attendance", "Посещаемость", "свои отметки и статистика", "attendance"),
    menuCard("normatives", "Нормативы", "задания и отчёты", "norms"),
    menuCard("learning", "Материалы", "курсы и памятки", "learning"),
    menuCard("notifications", "Уведомления", "личные сообщения", "notifications"),
    menuCard("appeals", "Обращение", "вопрос или сообщение", "appeals"),
  ];
  if (level >= 4) {
    cards.push(menuCard("announcements", "Объявления", "отправка в отделение", "announcements"));
  }
  if (level >= 5) {
    cards.push(menuCard("reports", "Отчёты", "посещаемость и нормативы", "reports"));
  }
  if (level >= 6) {
    cards.push(menuCard("admin", "Админка", "состав, меню, справочники", "admin"));
  }
  if (level < 3) {
    return [
      menuCard("dashboard", "Вступление", "заявка и события кандидата", "my_squad"),
      menuCard("schedule", "Открытые события", "ближайшие встречи", "schedule"),
      menuCard("learning", "Материалы", "подготовка к отбору", "learning"),
      menuCard("normatives", "Нормативы", "задания отбора", "norms"),
    ];
  }
  return cards;
}

function menuCard(code: string, title: string, description: string, icon: string): MenuCard {
  return {
    code,
    title,
    description,
    icon_code: icon,
    color_code: "DEFAULT",
    route: `/${code}`,
    sort_order: 0,
    is_required: false,
    show_badge: false,
  };
}

function formatPhoneDisplay(raw: string | null | undefined): string {
  if (!raw) return "—";
  const digits = raw.replace(/\D/g, "");
  const local = digits.startsWith("7") || digits.startsWith("8") ? digits.slice(1) : digits;
  if (local.length !== 10) return raw;
  return `+7 ${local.slice(0, 3)} ${local.slice(3, 6)} ${local.slice(6, 8)} ${local.slice(8, 10)}`;
}

function phoneInputToRaw(display: string): string {
  const digits = display.replace(/\D/g, "");
  const local = digits.startsWith("7") || digits.startsWith("8") ? digits.slice(1) : digits;
  return local.length > 0 ? "+7" + local.slice(0, 10) : "";
}

function applyPhoneMask(value: string): string {
  const digits = value.replace(/\D/g, "");
  const local = digits.startsWith("7") || digits.startsWith("8") ? digits.slice(1) : digits;
  const d = local.slice(0, 10);
  let result = "+7";
  if (d.length > 0) result += " " + d.slice(0, 3);
  if (d.length > 3) result += " " + d.slice(3, 6);
  if (d.length > 6) result += " " + d.slice(6, 8);
  if (d.length > 8) result += " " + d.slice(8, 10);
  return result;
}

// Set after auth to use server-configured timezone instead of browser-local
let _appTimezone = "Asia/Novosibirsk";

function formatDate(value: string | null) {
  if (!value) return "без даты";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    timeZone: _appTimezone,
  }).format(new Date(value));
}

function toDateTimeLocal(value: string | null) {
  if (!value) return "";
  const d = new Date(value);
  // Format in the server's configured timezone so datetime-local inputs show correct local times
  const parts = new Intl.DateTimeFormat("sv-SE", {
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
    timeZone: _appTimezone,
    hour12: false,
  }).formatToParts(d);
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "00";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

function formatDateFull(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit", month: "long", year: "numeric",
    timeZone: _appTimezone,
  }).format(new Date(value));
}

function formatUnreadCount(count: number) {
  const mod10 = count % 10;
  const mod100 = count % 100;
  const word = mod10 === 1 && mod100 !== 11 ? "новое" : "новых";
  return `${count} ${word}`;
}

type NavItem = {
  view: ViewKey;
  iconCode: string;
  label: string;
  minLevel: number;
};

const navItems: NavItem[] = [
  { view: "dashboard", iconCode: "home", label: "Главная", minLevel: 0 },
  { view: "schedule", iconCode: "schedule", label: "План", minLevel: 0 },
  { view: "attendance", iconCode: "attendance", label: "Явка", minLevel: 3 },
  { view: "normatives", iconCode: "norms", label: "Нормы", minLevel: 0 },
  { view: "profile", iconCode: "profile", label: "Профиль", minLevel: 0 },
];

const adminNavItem: NavItem = { view: "admin", iconCode: "admin", label: "Админка", minLevel: 6 };

const viewMinLevels: Record<ViewKey, number> = {
  dashboard: 0,
  schedule: 0,
  attendance: 3,
  normatives: 0,
  learning: 0,
  notifications: 3,
  announcements: 4,
  appeals: 3,
  reports: 5,
  people: 3,
  profile: 0,
  admin: 6,
};

function canAccessView(view: ViewKey, level: number) {
  return level >= viewMinLevels[view];
}

function apiPath(path: string) {
  const base = (api.defaults.baseURL ?? "").replace(/\/$/, "");
  return `${base}${path}`;
}

function avatarPath(fileId: number | null | undefined) {
  return fileId ? apiPath(`/files/avatars/${fileId}`) : null;
}

function runPromoAction(block: PromoBlock, navigate: (view: string) => void) {
  if (block.button_url) {
    window.open(block.button_url, "_blank", "noopener");
    return;
  }
  const sectionMap: Record<string, string> = {
    OPEN_SECTION: "dashboard",
    OPEN_SCHEDULE: "schedule",
    OPEN_NORMATIVE: "normatives",
    OPEN_COURSE: "learning",
    OPEN_FORM: "appeals",
  };
  const section = block.action_type_code ? sectionMap[block.action_type_code] : null;
  if (section) navigate(section);
}

function StatusCarousel({
  profile,
  level,
  unreadCount,
  promo,
  navigate,
}: {
  profile: UserProfile;
  level: number;
  unreadCount: number;
  promo: PromoBlock[];
  navigate: (view: string) => void;
}) {
  const slides = useMemo(
    () => [
      { type: "profile" as const, key: "profile" },
      ...promo.filter((block) => block.is_active).slice(0, 5).map((block) => ({
        type: "promo" as const,
        key: `promo-${block.id}`,
        block,
      })),
    ],
    [promo],
  );
  const [index, setIndex] = useState(0);
  const touchStartX = useRef<number | null>(null);
  const current = slides[index % slides.length];
  const goTo = useCallback((next: number) => {
    setIndex((next + slides.length) % slides.length);
  }, [slides.length]);

  useEffect(() => {
    if (index >= slides.length) setIndex(0);
  }, [index, slides.length]);

  useEffect(() => {
    if (slides.length <= 1) return undefined;
    const timer = window.setInterval(() => goTo(index + 1), 6500);
    return () => window.clearInterval(timer);
  }, [goTo, index, slides.length]);

  const promoTheme: Record<string, string> = {
    INFO: "linear-gradient(135deg, rgba(41,128,185,0.96), rgba(31,111,168,0.96))",
    SUCCESS: "linear-gradient(135deg, rgba(39,174,96,0.96), rgba(30,148,80,0.96))",
    WARNING: "linear-gradient(135deg, rgba(230,126,34,0.96), rgba(212,96,16,0.96))",
    DANGER: "linear-gradient(135deg, rgba(231,76,60,0.96), rgba(192,57,43,0.96))",
    PROMO: "linear-gradient(135deg, rgba(18,37,83,0.98), rgba(44,74,138,0.96))",
    DEFAULT: "linear-gradient(135deg, rgba(18,37,83,0.98), rgba(44,74,138,0.96))",
  };

  return (
    <section
      className={`${styles.statusPanel} ${styles.statusCarousel} ${current.type === "promo" ? styles.statusPromoPanel : ""}`}
      style={current.type === "promo" ? { background: promoTheme[current.block.style_code] ?? promoTheme.DEFAULT } : undefined}
      onTouchStart={(event) => { touchStartX.current = event.touches[0].clientX; }}
      onTouchEnd={(event) => {
        if (touchStartX.current === null || slides.length <= 1) return;
        const diff = touchStartX.current - event.changedTouches[0].clientX;
        if (Math.abs(diff) > 42) goTo(index + (diff > 0 ? 1 : -1));
        touchStartX.current = null;
      }}
    >
      {current.type === "profile" ? (
        <>
          <div key={`${current.key}-info`} className={styles.carouselSlide}>
            <h1>{level >= 3 ? "Личный кабинет" : "Вступление в клуб"}</h1>
            <p>{profile.full_name}</p>
          </div>
          <dl key={`${current.key}-stats`} className={styles.carouselSlide}>
            <div>
              <dt>Отделение</dt>
              <dd>{profile.squad_id ?? "—"}</dd>
            </div>
            <div>
              <dt>Уведомления</dt>
              <dd>{unreadCount}</dd>
            </div>
          </dl>
        </>
      ) : (
        <div key={current.key} className={`${styles.statusPromoContent} ${styles.carouselSlide}`}>
          <span>Промо ВПК</span>
          <h1>{current.block.title}</h1>
          {current.block.body && <p>{current.block.body}</p>}
          {current.block.button_text && (current.block.button_url || current.block.action_type_code) && (
            <button type="button" onClick={() => runPromoAction(current.block, navigate)}>
              {current.block.button_text}
            </button>
          )}
        </div>
      )}
      {slides.length > 1 && (
        <div className={styles.statusDots} aria-label="Слайды">
          {slides.map((slide, dotIndex) => (
            <button
              key={slide.key}
              type="button"
              aria-label={`Открыть слайд ${dotIndex + 1}`}
              data-active={dotIndex === index % slides.length}
              onClick={() => goTo(dotIndex)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

/* ─────────────────────────── App ─────────────────────────── */

export function App({ webApp }: Props) {
  const auth = useTelegramAuth();
  const [profile, setProfile] = useState<UserProfile>(fallbackProfile);
  const [authStatus, setAuthStatus] = useState<AuthStatus>("checking");
  const [authError, setAuthError] = useState<string | null>(null);
  const [authAttempt, setAuthAttempt] = useState(0);
  const [activeView, setActiveView] = useState<ViewKey>("dashboard");
  const [prevView, setPrevView] = useState<ViewKey | null>(null);
  const [milestoneStreak, setMilestoneStreak] = useState<number | null>(null);
  const prevStreakRef = useRef<number>(0);
  const hasToken = authStatus === "ready" && Boolean(auth.data?.access_token);
  const telegramUserId = webApp.initDataUnsafe?.user?.id ?? null;
  const initDataLength = webApp.initData?.length ?? 0;
  const isAuthenticating = authStatus === "checking" || auth.isPending;

  // Force light theme always
  useEffect(() => {
    document.documentElement.removeAttribute("data-theme");
  }, []);
  const level = roleLevels[profile.role_code];
  const publicMode = hasToken && level < 3;
  const internalMode = hasToken && level >= 3;

  const menu = useMenu(hasToken);
  const publicContent = usePublicContent(publicMode);
  const publicEvents = usePublicEvents(publicMode);
  const joinMe = useJoinMe(hasToken && profile.role_code === "CANDIDATE");
  const joinHistory = useJoinHistory(hasToken && profile.role_code === "CANDIDATE");
  const joinEvents = useJoinEvents(hasToken && profile.role_code === "CANDIDATE");
  const schedule = useSchedule(internalMode);
  const squadsList = useSquads(internalMode);
  const scheduleWeekType = useScheduleWeekType(internalMode);
  const attendance = useMyAttendance(internalMode);
  const attendanceStats = useMyAttendanceStats(internalMode);
  const normatives = useNormatives(hasToken, level >= 6);
  const mySubmissions = useMyNormativeSubmissions(hasToken && level >= 1);
  const pendingSubmissions = usePendingNormativeSubmissions(hasToken && level >= 4);
  const submissionHistory = useNormativeSubmissionsHistory(hasToken && level >= 4);
  const notifications = useNotifications(internalMode);
  const announcements = useAnnouncements(internalMode);
  const attendanceReport = useAttendanceReport(hasToken && level >= 5);
  const gradesReport = useGradesReport(hasToken && level >= 5);
  const normativesReport = useNormativesReport(hasToken && level >= 5);
  const dashboardSettings = useDashboardSettings(internalMode);
  const promo = usePromo(internalMode);
  const learning = useLearningMaterials(hasToken);
  const learningCourses = useLearningCourses(hasToken);
  const appeals = useAppeals(internalMode);
  const mySquad = useMySquad(internalMode);
  const myStreak = useMyStreak(internalMode);
  const allUsers = useUsers(internalMode);
  const activityFeed = useActivityFeed(hasToken && level >= 4);
  const adminUsers = useAdminUsers(hasToken && level >= 4);
  const adminApplications = useAdminApplications(hasToken && level >= 6);
  const adminPromo = useAdminPromo(hasToken && level >= 6);
  const adminMenu = useAdminMenu(hasToken && level >= 6);
  const adminSquads = useAdminSquads(hasToken && level >= 6);
  const adminAudit = useAdminAudit(hasToken && level >= 8);

  const hapticSuccess = () => { webApp.HapticFeedback?.notificationOccurred?.("success"); };
  const hapticError = () => { webApp.HapticFeedback?.notificationOccurred?.("error"); };

  const respondEvent = useRespondEvent();
  const respondCandidateEvent = useRespondCandidateEvent();
  const readNotification = useReadNotification();
  const readAll = useReadAllNotifications();
  const createJoinApplication = useCreateJoinApplication();
  const createAppeal = useCreateAppeal();
  const createAnnouncement = useCreateAnnouncement();
  const sendAnnouncement = useSendAnnouncement();
  const submitNormative = useSubmitNormative();
  const reviewSubmission = useReviewSubmission();
  const updateDashboardSettings = useUpdateDashboardSettings();
  const resetDashboardSettings = useResetDashboardSettings();
  const acceptApplication = useAdminAcceptApplication();
  const rejectApplication = useAdminRejectApplication();
  const createPromo = useCreatePromoBlock();
  const updatePromo = useUpdatePromoBlock();
  const deletePromo = useDeletePromoBlock();
  const uploadAvatar = useUploadAvatar();

  useEffect(() => {
    const initData = webApp.initData?.trim() ?? "";
    if (!initData) {
      setAuthStatus("missing_init_data");
      setAuthError(null);
      return;
    }
    setAuthStatus("checking");
    setAuthError(null);
    auth.mutate(initData, {
      onSuccess: (data) => {
        setProfile(data.profile);
        setAuthStatus("ready");
        setAuthError(null);
        if (data.app_timezone) {
          _appTimezone = data.app_timezone;
        }
      },
      onError: (error) => {
        const detail = apiErrorDetail(error);
        setAuthStatus("failed");
        setAuthError(detail ?? "Не удалось проверить Telegram initData");
        toast(detail ? `Ошибка авторизации: ${detail}` : "Ошибка авторизации. Попробуйте перезапустить приложение.", "error");
      },
    });
  }, [authAttempt]);

  const navCodes = new Set(["dashboard", "schedule", "attendance", "normatives", "profile", "admin"]);

  const cards = useMemo(() => {
    const apiMenu = menu.data?.map((card) => ({ ...card, code: normalizeView(card.code) }));
    const source = apiMenu?.length ? apiMenu : roleMenu(profile);
    return source
      .filter((card) => canAccessView(normalizeView(card.code), level))
      .filter((card) => !navCodes.has(normalizeView(card.code)));
  }, [menu.data, profile, level]);
  const helpCard = cards.find((card) => normalizeView(card.code) === "appeals");
  const gridCards = cards.filter((card) => normalizeView(card.code) !== "appeals");

  const visibleSchedule = schedule.data ?? [];
  const visibleNormatives = normatives.data ?? [];
  const visibleAttendance = attendance.data ?? [];
  const unreadCount = notifications.data?.filter((item) => !item.is_read).length ?? 0;
  const appealNoticeCount = notifications.data?.filter((item) => {
    if (item.is_read) return false;
    const entity = (item.entity_name ?? "").toLowerCase();
    const type = item.type_code.toLowerCase();
    return entity.includes("appeal") || type.includes("appeal");
  }).length ?? 0;
  const visibleCandidateEvents = joinEvents.data?.length ? joinEvents.data : publicEvents.data ?? [];
  const showDashboardChrome = hasToken && activeView === "dashboard";

  useEffect(() => {
    document.body.dataset.appChrome = showDashboardChrome ? "dashboard" : "plain";
    return () => {
      delete document.body.dataset.appChrome;
    };
  }, [showDashboardChrome]);

  const openView = (view: string) => {
    const next = normalizeView(view);
    if (!canAccessView(next, level)) {
      setActiveView("dashboard");
      webApp.BackButton?.hide();
      return;
    }
    setPrevView(activeView);
    setActiveView(next);
    webApp.HapticFeedback?.impactOccurred("light");
    // Show Telegram BackButton when not on dashboard
    if (next !== "dashboard") {
      webApp.BackButton?.show();
    } else {
      webApp.BackButton?.hide();
    }
  };

  useEffect(() => {
    if (!canAccessView(activeView, level)) {
      setActiveView("dashboard");
      setPrevView(null);
      webApp.BackButton?.hide();
    }
  }, [activeView, level]);

  // Trigger milestone confetti when streak hits milestone
  useEffect(() => {
    const current = myStreak.data?.current_streak ?? 0;
    const prev = prevStreakRef.current;
    const MILESTONES = [5, 10, 15, 20, 30];
    if (current > prev && MILESTONES.includes(current)) {
      setMilestoneStreak(current);
      webApp.HapticFeedback?.notificationOccurred?.("success");
    }
    prevStreakRef.current = current;
  }, [myStreak.data?.current_streak]);

  // Wire up BackButton to go back
  useEffect(() => {
    const handler = () => {
      if (prevView) {
        setActiveView(prevView);
        setPrevView(null);
        webApp.HapticFeedback?.impactOccurred("soft");
        if (prevView === "dashboard") webApp.BackButton?.hide();
      } else {
        setActiveView("dashboard");
        webApp.BackButton?.hide();
      }
    };
    webApp.BackButton?.onClick(handler);
    return () => webApp.BackButton?.offClick(handler);
  }, [prevView]);

  const visibleNav = hasToken ? [
    ...navItems.filter((item) => level >= item.minLevel),
    ...(level >= adminNavItem.minLevel ? [adminNavItem] : []),
  ] : [];

  return (
    <>
    <ToastContainer />
    {milestoneStreak !== null && (
      <MilestoneToast streak={milestoneStreak} onDismiss={() => setMilestoneStreak(null)} />
    )}
    <main className={styles.shell}>
      <header className={styles.header}>
        <button
          type="button"
          className={styles.headerHomeBtn}
          onClick={() => openView("dashboard")}
          aria-label="На главную"
        >
          <img src="/assets/zvezda-emblem.jpg" alt="ВПК Звезда" />
          <div>
            <strong>ВПК Звезда</strong>
            <span>{hasToken ? roleLabels[profile.role_code] : "Авторизация"}</span>
          </div>
        </button>
      </header>

      {showDashboardChrome && (
        <>
          <StatusCarousel
            profile={profile}
            level={level}
            unreadCount={unreadCount}
            promo={promo.data ?? []}
            navigate={openView}
          />

          <section className={styles.menuGrid} aria-label="Разделы">
            {gridCards.map((card) => (
              <button
                key={`${card.code}-${card.title}`}
                className={styles.menuCard}
                data-code={card.code}
                type="button"
                onClick={() => openView(card.code)}
              >
                <AppIcon code={card.icon_code ?? card.code} />
                <span>{card.title}</span>
                <small>{card.description}</small>
              </button>
            ))}
          </section>
          {helpCard && (
            <button
              className={styles.helpStrip}
              type="button"
              onClick={() => openView(helpCard.code)}
              data-alert={appealNoticeCount > 0}
            >
              <span className={styles.helpStripIcon}>
                <AppIcon code="appeals" />
              </span>
              <span className={styles.helpStripText}>
                <strong>Нужна помощь?</strong>
                <small>Связь с командованием</small>
              </span>
              <span className={styles.helpStripBadge}>
                {appealNoticeCount > 0 ? "Есть ответ" : "Написать"}
              </span>
            </button>
          )}
        </>
      )}

      <section className={styles.workspace} data-compact={!showDashboardChrome}>
        {isAuthenticating && (
          <div className={styles.panel}>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        )}
        {!isAuthenticating && !hasToken && (
          <AuthGate
            status={authStatus}
            error={authError}
            initDataLength={initDataLength}
            telegramUserId={telegramUserId}
            onAction={() => {
              if (authStatus === "failed" && webApp.close) {
                webApp.close();
                return;
              }
              setAuthAttempt((value) => value + 1);
            }}
          />
        )}
        {!isAuthenticating && hasToken && activeView === "dashboard" && (
          profile.role_code === "CANDIDATE" ? (
            <CandidateDashboard
              application={joinMe.data ?? null}
              history={joinHistory.data ?? []}
              events={visibleCandidateEvents}
              materials={learning.data ?? []}
              notifications={notifications.data ?? []}
              onRespond={(eventId, responseCode) =>
                respondCandidateEvent.mutate(
                  { eventId, responseCode },
                  { onSuccess: () => webApp.HapticFeedback?.notificationOccurred?.("success") },
                )
              }
            />
          ) : level < 3 ? (
            <PublicScreen
              content={publicContent.data}
              events={publicEvents.data ?? []}
              onSubmit={(payload) =>
                createJoinApplication.mutate(payload, {
                  onSuccess: () => {
                    setProfile({ ...profile, full_name: payload.full_name, role_code: "CANDIDATE" });
                    webApp.HapticFeedback?.notificationOccurred?.("success");
                  },
                })
              }
              isSubmitting={createJoinApplication.isPending}
            />
          ) : (
            <Dashboard
              level={level}
              schedule={visibleSchedule}
              attendance={visibleAttendance}
              normatives={visibleNormatives}
              notifications={notifications.data ?? []}
              attendanceStats={attendanceStats.data}
              promo={promo.data ?? []}
              settings={dashboardSettings.data ?? []}
              streak={myStreak.data ?? null}
              activityFeed={activityFeed.data ?? []}
              onSaveSettings={(items) =>
                updateDashboardSettings.mutate(items, {
                  onSuccess: () => toast("Главная сохранена", "success"),
                  onError: () => toast("Не удалось сохранить главную", "error"),
                })
              }
              onResetSettings={() =>
                resetDashboardSettings.mutate(undefined, {
                  onSuccess: () => toast("Главная сброшена", "info"),
                  onError: () => toast("Не удалось сбросить главную", "error"),
                })
              }
              isSavingSettings={updateDashboardSettings.isPending || resetDashboardSettings.isPending}
              navigate={openView}
              onRespond={(eventId, responseCode, absenceReasonId, customReason) =>
                respondEvent.mutate(
                  { eventId, responseCode, absenceReasonId, customReason },
                  {
                    onSuccess: () => {
                      hapticSuccess();
                      const labels: Record<string, string> = { COMING: "Ответ «Приду» сохранён", NOT_COMING: "Ответ «Не приду» сохранён", MAYBE: "Ответ «Пока не знаю» сохранён" };
                      toast(labels[responseCode] ?? "Ответ сохранён", "success");
                    },
                    onError: () => { hapticError(); toast("Не удалось сохранить ответ", "error"); },
                  },
                )
              }
            />
          )
        )}

        {!isAuthenticating && hasToken && activeView === "schedule" && (
          level < 3 ? (
            <CandidateEventsView
              events={visibleCandidateEvents}
              readonly={profile.role_code !== "CANDIDATE"}
              framed
              onApplyClick={() => openView("dashboard")}
              onRespond={(eventId, responseCode) =>
                respondCandidateEvent.mutate(
                  { eventId, responseCode },
                  { onSuccess: () => webApp.HapticFeedback?.notificationOccurred?.("success") },
                )
              }
            />
          ) : (
            <ScheduleView
              events={visibleSchedule}
              weekType={scheduleWeekType.data}
              level={level}
              squads={squadsList.data ?? adminSquads.data ?? []}
              onRespond={(eventId, responseCode, absenceReasonId, customReason) => {
                respondEvent.mutate(
                  { eventId, responseCode, absenceReasonId, customReason },
                  { onSuccess: () => webApp.HapticFeedback?.notificationOccurred?.("success") },
                );
              }}
            />
          )
        )}

        {!isAuthenticating && hasToken && activeView === "attendance" && level >= 3 && (
          <AttendanceView
            records={visibleAttendance}
            canManage={level >= 4}
            managerLevel={level}
            managerSquadId={profile.squad_id}
            reportItems={attendanceReport.data?.items ?? []}
            stats={attendanceStats.data}
            schedule={schedule.data ?? []}
            users={allUsers.data ?? []}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "normatives" && (
          <NormativesView
            items={visibleNormatives}
            submissions={mySubmissions.data ?? []}
            pending={pendingSubmissions.data ?? []}
            history={submissionHistory.data ?? []}
            canSubmit={level >= 1}
            canReview={level >= 4}
            onSubmit={(normativeId, comment, fileIds) =>
              submitNormative.mutate(
                { normativeId, comment, fileIds },
                {
                  onSuccess: () => { hapticSuccess(); toast("Сдача отправлена на проверку", "success"); },
                  onError: () => { hapticError(); toast("Ошибка при отправке", "error"); },
                },
              )
            }
            onReview={(submissionId, statusCode, reviewerComment) =>
              reviewSubmission.mutate(
                { submissionId, statusCode, reviewerComment },
                {
                  onSuccess: () => {
                    hapticSuccess();
                    const msgs: Record<string, string> = { ACCEPTED: "Сдача принята", REJECTED: "Сдача отклонена", NEEDS_REDO: "Отправлено на доработку" };
                    toast(msgs[statusCode] ?? "Статус обновлён", statusCode === "ACCEPTED" ? "success" : "info");
                  },
                },
              )
            }
            isBusy={submitNormative.isPending || reviewSubmission.isPending}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "learning" && (
          <LearningView
            items={learning.data ?? []}
            courses={learningCourses.data ?? []}
            canTrack={level >= 1}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "notifications" && level >= 3 && (
          <NotificationsView
            items={notifications.data ?? []}
            onRead={(id) => readNotification.mutate(id)}
            onReadAll={() => readAll.mutate()}
            isBusy={readAll.isPending}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "announcements" && level >= 4 && (
          <AnnouncementsView
            items={announcements.data ?? []}
            level={level}
            squads={squadsList.data ?? adminSquads.data ?? []}
            profileSquadId={profile.squad_id}
            onCreate={(payload) =>
              createAnnouncement.mutate(payload, {
                onSuccess: (item: { id: number }) => sendAnnouncement.mutate(item.id),
              })
            }
            isSubmitting={createAnnouncement.isPending || sendAnnouncement.isPending}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "appeals" && level >= 3 && (
          <AppealsView
            items={appeals.data ?? []}
            currentUserId={profile.id}
            onCreate={(payload) =>
              createAppeal.mutate(payload, {
                onSuccess: () => { hapticSuccess(); toast("Обращение отправлено", "success"); },
                onError: () => { hapticError(); toast("Не удалось отправить обращение", "error"); },
              })
            }
            isSubmitting={createAppeal.isPending}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "reports" && level >= 5 && (
          <ReportsView
            level={level}
            attendance={attendanceReport.data}
            grades={gradesReport.data}
            normatives={normativesReport.data}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "people" && level >= 3 && (
          <PeopleView
            level={level}
            profile={profile}
            mySquad={mySquad.data ?? null}
            allUsers={allUsers.data ?? []}
            squads={squadsList.data ?? adminSquads.data ?? []}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "profile" && (
          <ProfileView
            profile={profile}
            attendanceStats={attendanceStats.data}
            submissions={mySubmissions.data ?? []}
            streak={myStreak.data ?? null}
            allUsers={allUsers.data ?? []}
            squads={squadsList.data ?? adminSquads.data ?? []}
            onProfileUpdate={(p) => setProfile(p)}
            onAvatarUpload={(file) => uploadAvatar.mutateAsync(file)}
            isAvatarUploading={uploadAvatar.isPending}
          />
        )}

        {!isAuthenticating && hasToken && activeView === "admin" && level >= 6 && (
          <AdminView
            level={level}
            currentUserId={profile.id}
            users={adminUsers.data ?? []}
            applications={adminApplications.data ?? []}
            promo={adminPromo.data ?? []}
            menu={adminMenu.data ?? []}
            squads={adminSquads.data ?? []}
            audit={adminAudit.data ?? []}
            onAccept={(id, squadId) =>
              acceptApplication.mutate(
                { id, squad_id: squadId },
                { onSuccess: () => webApp.HapticFeedback?.notificationOccurred?.("success") },
              )
            }
            onReject={(id, reason) =>
              rejectApplication.mutate(
                { id, decision_reason: reason },
                { onSuccess: () => webApp.HapticFeedback?.notificationOccurred?.("success") },
              )
            }
            isBusy={acceptApplication.isPending || rejectApplication.isPending}
          />
        )}
      </section>

      {hasToken && (
        <nav
          className={styles.nav}
          data-admin={visibleNav.length > 5}
          aria-label="Основная навигация"
          style={{ gridTemplateColumns: `repeat(${visibleNav.length}, minmax(0, 1fr))` }}
        >
          {visibleNav.map(({ view, iconCode, label }) => (
            <button
              key={view}
              type="button"
              data-active={activeView === view}
              onClick={() => openView(view)}
            >
              <span
                className={`${styles.navIcon} ${view === "notifications" && unreadCount > 0 ? styles.navBadge : ""}`}
                data-count={view === "notifications" && unreadCount > 0 ? unreadCount : undefined}
              >
                <AppIcon code={iconCode} />
              </span>
              <span>{label}</span>
            </button>
          ))}
        </nav>
      )}
    </main>
    </>
  );
}

/* ─────────── normalizeView ─────────── */
function normalizeView(code: string): ViewKey {
  if (code === "join") return "dashboard";
  if (code === "learning_public") return "learning";
  if (code === "norms") return "normatives";
  if (code === "full_roster" || code === "my_squad" || code === "squads") return "people";
  if (code === "appeal") return "appeals";
  if (code === "mark_attendance") return "attendance";
  if (["dashboard", "schedule", "attendance", "normatives", "learning", "notifications", "announcements", "appeals", "reports", "people", "profile", "admin"].includes(code)) {
    return code as ViewKey;
  }
  return "dashboard";
}

/* ─────────── ResponseButtons ─────────── */
type RespondFn = (eventId: number, code: string, absenceReasonId?: number | null, customReason?: string) => void;

function ResponseButtons({
  eventId,
  requiresResponse = true,
  currentResponse,
  onRespond,
}: {
  eventId: number;
  requiresResponse?: boolean;
  currentResponse?: string | null;
  onRespond: RespondFn;
}) {
  const [pickingReason, setPickingReason] = useState(false);
  const [changing, setChanging] = useState(false);
  const [customReason, setCustomReason] = useState("");
  const reasons = useAbsenceReasons();
  const activeReasons = reasons.data?.filter((r) => r.is_active) ?? [];

  const handleRespond = (code: string, reasonId?: number | null, custom?: string) => {
    setChanging(false);
    setPickingReason(false);
    onRespond(eventId, code, reasonId, custom);
  };

  if (pickingReason) {
    return (
      <div className={styles.actions} style={{ gridTemplateColumns: "1fr" }}>
        <div style={{ gridColumn: "1/-1", display: "grid", gap: 6 }}>
          <small style={{ color: "#65708a", fontSize: 11, fontWeight: 800 }}>Укажите причину отсутствия:</small>
          {activeReasons.map((reason) => (
            <button
              key={reason.id}
              type="button"
              className={styles.btnMaybeOutline}
              style={{ justifySelf: "stretch" }}
              onClick={() => {
                if (reason.requires_comment) {
                  setCustomReason("");
                } else {
                  handleRespond("NOT_COMING", reason.id, undefined);
                }
              }}
            >
              {reason.label}
            </button>
          ))}
          <input
            placeholder="Другая причина (текст)"
            value={customReason}
            onChange={(e) => setCustomReason(e.target.value)}
            style={{ border: "1px solid #d9deea", borderRadius: 10, padding: "8px 12px", fontSize: 16, fontFamily: "inherit", color: "#1a2f5a" }}
          />
          {customReason.trim().length >= 2 && (
            <button
              type="button"
              className={styles.btnNotComing}
              onClick={() => handleRespond("NOT_COMING", null, customReason.trim())}
            >
              Отправить причину
            </button>
          )}
          <button type="button" className={styles.btnMaybeOutline} onClick={() => { setPickingReason(false); setChanging(false); }}>
            Отмена
          </button>
        </div>
      </div>
    );
  }

  if (currentResponse && !changing) {
    return (
      <div className={styles.actions} style={{ gridTemplateColumns: "1fr" }}>
        <button
          type="button"
          className={styles.btnMaybeOutline}
          style={{ gridColumn: "1/-1" }}
          onClick={() => setChanging(true)}
        >
          Изменить ответ
        </button>
      </div>
    );
  }

  return (
    <div className={styles.actions}>
      <button
        type="button"
        className={styles.btnComingOutline}
        onClick={() => handleRespond("COMING")}
      >
        Приду
      </button>
      <button
        type="button"
        className={styles.btnNotComingOutline}
        onClick={() => {
          if (requiresResponse) {
            setPickingReason(true);
          } else {
            handleRespond("NOT_COMING");
          }
        }}
      >
        Не приду
      </button>
      <button
        type="button"
        className={styles.btnMaybeOutline}
        onClick={() => handleRespond("MAYBE")}
      >
        Пока не знаю
      </button>
    </div>
  );
}

/* ─────────── Dashboard ─────────── */
type StreakData = { current_streak: number; best_streak: number; total_events: number; present_count: number; percent: number } | null;
type ActivityItem = { type: string; text: string; created_at: string };

function Dashboard({
  level,
  schedule,
  attendance,
  normatives,
  notifications,
  attendanceStats,
  promo,
  settings,
  streak,
  activityFeed,
  onSaveSettings,
  onResetSettings,
  isSavingSettings,
  navigate,
  onRespond,
}: {
  level: number;
  schedule: ScheduleEvent[];
  attendance: AttendanceRecord[];
  normatives: Normative[];
  notifications: Notification[];
  attendanceStats?: ReportSummary;
  promo: PromoBlock[];
  settings: DashboardSetting[];
  streak: StreakData;
  activityFeed: ActivityItem[];
  onSaveSettings: (items: Array<{ block_code: string; sort_order: number; is_hidden: boolean; is_pinned: boolean; view_mode_code?: string | null }>) => void;
  onResetSettings: () => void;
  isSavingSettings: boolean;
  navigate: (view: string) => void;
  onRespond: RespondFn;
}) {
  const availableBlocks = dashboardBlocks.filter((block) => !block.commanderOnly || level >= 4);
  const settingByCode = new Map(settings.map((item) => [item.block_code, item]));
  const orderedBlocks = [...availableBlocks].sort((left, right) => {
    const leftSetting = settingByCode.get(left.code);
    const rightSetting = settingByCode.get(right.code);
    return (leftSetting?.sort_order ?? availableBlocks.indexOf(left)) - (rightSetting?.sort_order ?? availableBlocks.indexOf(right));
  });
  const isVisible = (code: DashboardBlockCode) =>
    !settingByCode.get(code)?.is_hidden || dashboardBlocks.find((block) => block.code === code)?.required;
  const statsItems = attendanceStats?.items ?? [];

  const nextEvent = schedule.find((event) => event.status_code !== "CANCELLED" && (!event.requires_response || event.my_response_code !== "COMING"));
  const presentCount = streak?.present_count ?? attendance.filter((r) => r.status_code === "PRESENT").length;
  const absentCount = attendance.filter((r) => r.status_code === "ABSENT").length;
  const percent = streak?.percent ?? (attendance.length ? Math.round((presentCount / attendance.length) * 100) : 0);

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Сводка</h2>
        <span>{level >= 4 ? "командирский доступ" : "личный доступ"}</span>
      </div>
      <div className={styles.dashboardStack}>
        {orderedBlocks.map((block) => {
          if (!isVisible(block.code)) return null;
          if (block.code === "next_event") {
            return (
              <div key={block.code}>
                <div className={styles.nextItem}>
                  <span>Ближайшее</span>
                  <strong>{nextEvent?.title ?? "нет событий"}</strong>
                  <small>
                    {formatDate(nextEvent?.start_datetime ?? null)} · {nextEvent?.place ?? "место уточняется"}
                  </small>
                </div>
                {nextEvent?.requires_response && (
                <ResponseButtons
                  eventId={nextEvent.id}
                  requiresResponse={nextEvent.requires_response}
                  currentResponse={nextEvent.my_response_code}
                  onRespond={onRespond}
                />
                )}
              </div>
            );
          }
          if (block.code === "personal_stats") {
            return (
              <div key={block.code}>
                <div className={styles.metrics}>
                  <Metric label="Посещено" value={presentCount} />
                  <Metric label="Пропущено" value={absentCount} />
                  <Metric label="Явка %" value={`${percent}%`} extraClass={styles.metricGreen} />
                  <Metric label="Нормативов" value={normatives.length} extraClass={styles.metricBlue} />
                </div>
                {streak && (streak.current_streak > 0 || streak.best_streak > 0) && (
                  <StreakBadge current={streak.current_streak} best={streak.best_streak} />
                )}
              </div>
            );
          }
          if (block.code === "commander_summary") {
            const notAnswered = attendance.filter((r) => r.status_code === "NOT_MARKED").length;
            return (
              <CommanderSummaryBlock
                key={block.code}
                schedule={schedule}
                notAnswered={notAnswered}
                attendance={attendance}
                normatives={normatives}
                activityFeed={activityFeed}
              />
            );
          }
          if (block.code === "normatives") {
            return <MiniList key={block.code} title="Активные нормативы" items={normatives.map((item) => item.title).slice(0, 3)} />;
          }
          if (block.code === "notifications") {
            return <MiniList key={block.code} title="Непрочитанные" items={notifications.filter((item) => !item.is_read).map((item) => item.title).slice(0, 3)} />;
          }
          return <PromoStrip key={block.code} blocks={promo} navigate={navigate} />;
        })}
      </div>
      <DashboardCustomizer
        blocks={availableBlocks}
        settings={settings}
        onSave={onSaveSettings}
        onReset={onResetSettings}
        isSaving={isSavingSettings}
      />
    </div>
  );
}

/* ─────────── CommanderSummaryBlock ─────────── */
function CommanderSummaryBlock({
  schedule, notAnswered, attendance, normatives, activityFeed,
}: {
  schedule: ScheduleEvent[];
  notAnswered: number;
  attendance: AttendanceRecord[];
  normatives: Normative[];
  activityFeed: ActivityItem[];
}) {
  const [feedCollapsed, setFeedCollapsed] = useState(false);
  return (
    <div>
      <div className={styles.commandSummary}>
        <Metric label="Событий" value={schedule.length} extraClass={styles.metricBlue} />
        <Metric label="Без ответа" value={notAnswered} />
        <Metric label="Пропустили" value={attendance.filter((r) => r.status_code === "ABSENT").length} />
        <Metric label="На проверке" value={normatives.length} extraClass={styles.metricGreen} />
      </div>
      {activityFeed.length > 0 && (
        <>
          <div className={styles.activityHeader}>
            <span>Активность</span>
            <button type="button" className={styles.collapseBtn} onClick={() => setFeedCollapsed((v) => !v)}>
              {feedCollapsed ? "Развернуть" : "Свернуть"}
            </button>
          </div>
          {!feedCollapsed && <ActivityFeed items={activityFeed.slice(0, 8)} />}
        </>
      )}
    </div>
  );
}

/* ─────────── WelcomeBanner ─────────── */
function WelcomeBanner({ blocks }: { blocks: PromoBlock[] }) {
  const slides = [
    { title: "Добро пожаловать в ВПК «Звезда»", body: "Заполните анкету и станьте частью команды", style: "PROMO" as const },
    ...blocks.filter((b) => b.is_active).map((b) => ({ title: b.title, body: b.body ?? "", style: (b.style_code ?? "DEFAULT") as string })),
  ];
  const [idx, setIdx] = useState(0);
  const touchStartX = useRef<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const goTo = useCallback((i: number) => {
    setIdx((i + slides.length) % slides.length);
  }, [slides.length]);

  useEffect(() => {
    timerRef.current = setTimeout(() => goTo(idx + 1), 4500);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [idx, goTo]);

  const themes: Record<string, { bg: string; color: string }> = {
    PROMO:   { bg: "linear-gradient(135deg, #1a2f5a, #2c4a8a)", color: "#fff" },
    INFO:    { bg: "linear-gradient(135deg, #2980b9, #1f6fa8)", color: "#fff" },
    SUCCESS: { bg: "linear-gradient(135deg, #27ae60, #1e9450)", color: "#fff" },
    WARNING: { bg: "linear-gradient(135deg, #e67e22, #d46010)", color: "#fff" },
    DANGER:  { bg: "linear-gradient(135deg, #e74c3c, #c0392b)", color: "#fff" },
    DEFAULT: { bg: "linear-gradient(135deg, #1a2f5a, #2c4a8a)", color: "#fff" },
  };

  const current = slides[idx];
  const theme = themes[current.style] ?? themes.DEFAULT;

  return (
    <div
      className={styles.welcomeBanner}
      style={{ background: theme.bg, color: theme.color }}
      onTouchStart={(e) => { touchStartX.current = e.touches[0].clientX; }}
      onTouchEnd={(e) => {
        if (touchStartX.current === null) return;
        const diff = touchStartX.current - e.changedTouches[0].clientX;
        if (Math.abs(diff) > 40) goTo(idx + (diff > 0 ? 1 : -1));
        touchStartX.current = null;
      }}
    >
      <div className={styles.bannerContent}>
        <strong>{current.title}</strong>
        {current.body && <span>{current.body}</span>}
      </div>
      {slides.length > 1 && (
        <div className={styles.bannerDots}>
          {slides.map((_, i) => (
            <button
              key={i}
              type="button"
              className={i === idx ? styles.bannerDotActive : styles.bannerDot}
              onClick={() => goTo(i)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ─────────── PrivacyModal ─────────── */
function PrivacyModal({ onClose }: { onClose: () => void }) {
  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalSheet} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <strong>Политика обработки данных</strong>
          <button type="button" onClick={onClose} aria-label="Закрыть">
            <X aria-hidden="true" />
          </button>
        </div>
        <div className={styles.modalBody}>
          <p><strong>Какие данные мы собираем</strong></p>
          <p>При подаче заявки: ФИО, дата рождения, номер телефона, город, группа/класс, Telegram ID, имя пользователя.</p>
          <p><strong>Для чего используются данные</strong></p>
          <p>Данные используются исключительно для организации деятельности ВПК «Звезда»: формирование состава, учёт посещаемости, выставление оценок, внутренняя коммуникация.</p>
          <p><strong>Кто имеет доступ</strong></p>
          <p>Командиры отделений и взвода ВПК «Звезда». Данные не передаются третьим лицам и не используются в коммерческих целях.</p>
          <p><strong>Хранение и удаление</strong></p>
          <p>Данные хранятся на защищённом сервере. По письменному запросу участника данные могут быть удалены из системы.</p>
          <p><strong>Контакт</strong></p>
          <p>По вопросам обработки данных обращайтесь к командиру через раздел «Обращения» в приложении.</p>
        </div>
      </div>
    </div>
  );
}

/* ─────────── PublicScreen ─────────── */
function PublicScreen({
  content,
  events,
  onSubmit,
  isSubmitting,
}: {
  content?: PublicContent;
  events: CandidateEvent[];
  onSubmit: (payload: JoinApplicationPayload) => void;
  isSubmitting: boolean;
}) {
  const [form, setForm] = useState<JoinApplicationPayload>({
    full_name: "",
    birth_date: "",
    phone: "",
    city: "",
    education_place: "",
    experience_text: "",
    motivation_text: "",
    source_text: "",
    consent_given: false,
    comment: "",
  });
  const [phoneDisplay, setPhoneDisplay] = useState("+7");
  const [showPrivacy, setShowPrivacy] = useState(false);
  const [screen, setScreen] = useState<"overview" | "application">("overview");
  const canSubmit = form.full_name.trim().length >= 2 && form.consent_given;
  const materials = (content?.materials ?? []).map((item) => item.title).slice(0, 4);

  if (screen === "application") {
    return (
      <div className={styles.panel}>
        <div className={styles.panelHeader}>
          <h2>Анкета вступления</h2>
          <button type="button" className={styles.editProfileBtn} onClick={() => setScreen("overview")}>
            Назад
          </button>
        </div>
        <div className={styles.formBlock}>
          <label className={styles.fieldLabel}>
            <span>ФИО *</span>
            <input placeholder="Иванов Иван Иванович" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </label>
          <label className={styles.fieldLabel}>
            <span>Дата рождения</span>
            <input type="date" value={form.birth_date} onChange={(e) => setForm({ ...form, birth_date: e.target.value })} />
          </label>
          <label className={styles.fieldLabel}>
            <span>Телефон</span>
            <input
              type="tel"
              placeholder="+7 999 000 11 22"
              value={phoneDisplay}
              inputMode="numeric"
              onChange={(e) => {
                const raw = e.target.value;
                if (raw === "" || raw === "+") {
                  setPhoneDisplay("+7");
                  setForm({ ...form, phone: "" });
                  return;
                }
                const masked = applyPhoneMask(raw);
                setPhoneDisplay(masked);
                setForm({ ...form, phone: phoneInputToRaw(masked) });
              }}
              onFocus={(e) => {
                if (e.target.value === "+7") {
                  const len = e.target.value.length;
                  setTimeout(() => e.target.setSelectionRange(len, len), 0);
                }
              }}
            />
          </label>
          <label className={styles.fieldLabel}>
            <span>Город или район</span>
            <input placeholder="Новосибирск" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
          </label>
          <label className={styles.fieldLabel}>
            <span>Учебная группа</span>
            <input placeholder="Например, 1ИСП-21" value={form.education_place} onChange={(e) => setForm({ ...form, education_place: e.target.value })} />
          </label>
          <label className={styles.fieldLabel}>
            <span>Опыт или подготовка</span>
            <textarea placeholder="Расскажите коротко о подготовке" rows={2} value={form.experience_text} onChange={(e) => setForm({ ...form, experience_text: e.target.value })} />
          </label>
          <label className={styles.fieldLabel}>
            <span>Почему хотите вступить *</span>
            <textarea placeholder="Мотивация кандидата" rows={3} value={form.motivation_text} onChange={(e) => setForm({ ...form, motivation_text: e.target.value })} />
          </label>
          <label className={styles.fieldLabel}>
            <span>Откуда узнали о ВПК</span>
            <input placeholder="Друзья, школа, соцсети" value={form.source_text} onChange={(e) => setForm({ ...form, source_text: e.target.value })} />
          </label>
          <label className={styles.fieldLabel}>
            <span>Комментарий</span>
            <textarea placeholder="Дополнительная информация" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
          </label>
          <label className={styles.checkboxLine}>
            <input type="checkbox" checked={form.consent_given} onChange={(e) => setForm({ ...form, consent_given: e.target.checked })} />
            <span>
              Согласен на{" "}
              <button
              type="button"
              className={styles.linkButton}
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                setShowPrivacy(true);
              }}
            >
                обработку персональных данных
              </button>
            </span>
          </label>
          <button type="button" disabled={!canSubmit || isSubmitting} onClick={() => onSubmit(form)}>
            {isSubmitting ? "Отправляем..." : "Подать заявку"}
          </button>
        </div>
        {showPrivacy && <PrivacyModal onClose={() => setShowPrivacy(false)} />}
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      <WelcomeBanner blocks={content?.promo_blocks ?? []} />
      <CandidateEventsView events={events} readonly onRespond={() => undefined} compact onApplyClick={() => setScreen("application")} />
      {materials.length > 0 && <MiniList title="Материалы для вступления" items={materials} />}
      <div className={styles.joinCta}>
        <div>
          <strong>Анкета вступления</strong>
          <span>Заполните данные кандидата отдельно от мероприятий.</span>
        </div>
        <button type="button" onClick={() => setScreen("application")}>
          Заполнить
        </button>
      </div>
    </div>
  );
}

/* ─────────── CandidateDashboard ─────────── */
const STATUS_FLOW_LABELS: Record<string, { label: string; color: string }> = {
  NEW:                 { label: "Заявка получена", color: "#1a2f5a" },
  REVIEWING:           { label: "На рассмотрении", color: "#3498db" },
  NEEDS_INFO:          { label: "Нужна информация", color: "#f39c12" },
  INVITED_MEETING:     { label: "Приглашён на встречу", color: "#9b59b6" },
  INVITED_NORMATIVES:  { label: "Приглашён на нормативы", color: "#e67e22" },
  AWAITING_DECISION:   { label: "Ожидает решения", color: "#3498db" },
  ACCEPTED:            { label: "Принят в состав", color: "#27ae60" },
  REJECTED:            { label: "Отклонён", color: "#e74c3c" },
  ARCHIVED:            { label: "Архив", color: "#95a5a6" },
};

function CandidateDashboard({
  application,
  history,
  events,
  materials,
  notifications,
  onRespond,
}: {
  application: JoinApplication | null;
  history: ApplicationHistoryItem[];
  events: CandidateEvent[];
  materials: LearningMaterial[];
  notifications: Notification[];
  onRespond: (eventId: number, responseCode: string) => void;
}) {
  const [showHistory, setShowHistory] = useState(false);
  const currentStatus = application?.status_code ?? "";
  const statusInfo = STATUS_FLOW_LABELS[currentStatus];

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Кабинет кандидата</h2>
        {statusInfo && (
          <span style={{ color: statusInfo.color, fontWeight: 900, fontSize: 11 }}>{statusInfo.label}</span>
        )}
      </div>

      {application && (
        <div style={{ border: "1px solid #e0e5ef", borderRadius: 12, background: "#fff", padding: "12px 14px", marginBottom: 10 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <strong style={{ fontSize: 14, color: "#1a2f5a" }}>История заявки</strong>
            <button type="button" className={styles.collapseBtn} onClick={() => setShowHistory(v => !v)}>
              {showHistory ? "Скрыть" : "Показать"}
            </button>
          </div>
          {showHistory && (
            <div style={{ marginTop: 10, display: "grid", gap: 6 }}>
              {history.length === 0 && <span style={{ fontSize: 12, color: "#8a96b0" }}>Изменений пока нет</span>}
              {history.map((item, i) => {
                const info = STATUS_FLOW_LABELS[item.new_status];
                return (
                  <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                    <div style={{ width: 8, height: 8, borderRadius: "50%", background: info?.color ?? "#bdc3c7", marginTop: 5, flexShrink: 0 }} />
                    <div>
                      <span style={{ fontSize: 13, fontWeight: 700, color: info?.color ?? "#1a2f5a" }}>{info?.label ?? item.new_status}</span>
                      <small style={{ display: "block", fontSize: 11, color: "#8a96b0" }}>
                        {new Date(item.changed_at).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                        {item.comment ? ` · ${item.comment}` : ""}
                      </small>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {application?.admin_comment && (
        <div className={styles.nextItem}>
          <span>Комментарий командира</span>
          <strong>{application.admin_comment}</strong>
        </div>
      )}
      <CandidateEventsView events={events} onRespond={onRespond} />
      {materials.length > 0 && <MiniList title="Подготовка" items={materials.map((item) => item.title).slice(0, 4)} />}
      {notifications.filter(n => !n.is_read).length > 0 && (
        <MiniList title="Новые уведомления" items={notifications.filter(n => !n.is_read).map((item) => item.title).slice(0, 3)} />
      )}
    </div>
  );
}

/* ─────────── CandidateEventsView ─────────── */
function CandidateEventsView({
  events,
  readonly = false,
  compact = false,
  framed = false,
  onRespond,
  onApplyClick,
}: {
  events: CandidateEvent[];
  readonly?: boolean;
  compact?: boolean;
  framed?: boolean;
  onRespond: (eventId: number, responseCode: string) => void;
  onApplyClick?: () => void;
}) {
  const [selectedEvent, setSelectedEvent] = useState<CandidateEvent | null>(null);
  const rootClassName = framed ? styles.panel : compact ? styles.compactSection : styles.subPanel;

  if (selectedEvent) {
    return (
      <div className={rootClassName}>
        <CandidateEventDetail
          event={selectedEvent}
          readonly={readonly}
          onBack={() => setSelectedEvent(null)}
          onRespond={onRespond}
          onApplyClick={onApplyClick}
        />
      </div>
    );
  }

  return (
    <div className={rootClassName}>
      <div className={styles.panelHeader}>
        <h2>{readonly ? "Открытые мероприятия" : "Мероприятия кандидата"}</h2>
        <span>{events.length} доступно</span>
      </div>
      <div className={styles.list}>
        {events.length === 0 && <Empty text="Пока нет опубликованных дат. Анкету можно отправить отдельно, приглашение появится позже." />}
        {events.map((event) => (
          <article
            className={`${styles.row} ${styles.eventRow}`}
            key={event.id}
            onClick={() => setSelectedEvent(event)}
          >
            <AppIcon code="schedule" />
            <div>
              <strong>{event.title}</strong>
              <span>{formatDate(event.start_datetime)} · {event.place ?? "место уточняется"}</span>
              {event.description && <small>{event.description}</small>}
            </div>
            {!readonly && (
              <div className={styles.eventRowActions} onClick={(e) => e.stopPropagation()}>
                <ResponseButtons eventId={event.id} onRespond={onRespond} />
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

function CandidateEventDetail({
  event,
  readonly,
  onBack,
  onRespond,
  onApplyClick,
}: {
  event: CandidateEvent;
  readonly: boolean;
  onBack: () => void;
  onRespond: (eventId: number, responseCode: string) => void;
  onApplyClick?: () => void;
}) {
  return (
    <div className={styles.eventDetail}>
      <button type="button" className={styles.eventBackButton} onClick={onBack}>
        Назад к мероприятиям
      </button>
      <div className={styles.eventHero}>
        <span>{event.event_type_code}</span>
        <h2>{event.title}</h2>
        <p>{formatDate(event.start_datetime)}</p>
      </div>
      <div className={styles.eventMetaGrid}>
        <div>
          <span>Место</span>
          <strong>{event.place || "место уточняется"}</strong>
        </div>
        <div>
          <span>Окончание</span>
          <strong>{event.end_datetime ? formatDate(event.end_datetime) : "по ситуации"}</strong>
        </div>
        {event.capacity !== null && (
          <div>
            <span>Лимит</span>
            <strong>{event.capacity} мест</strong>
          </div>
        )}
      </div>
      <div className={styles.eventDescription}>
        <span>Описание</span>
        <p>{event.description?.trim() || "Описание пока не добавлено. Уточните детали у организатора перед посещением."}</p>
      </div>
      {readonly ? (
        <button type="button" className={styles.iconAction} onClick={onApplyClick}>
          Заполнить анкету для записи
        </button>
      ) : (
        <ResponseButtons eventId={event.id} onRespond={onRespond} />
      )}
    </div>
  );
}

/* ─────────── EventVoterList ─────────── */
function EventVoterList({ eventId, squads, canView }: { eventId: number; squads: Squad[]; canView: boolean }) {
  const [open, setOpen] = useState(false);
  const responses = useEventResponses(open ? eventId : null, open && canView);

  if (!canView) return null;

  const squadName = (id: number | null) => squads.find((s) => s.id === id)?.name ?? "Без отделения";
  const byCode = responses.data?.reduce<Record<string, EventResponseItem[]>>((acc, r) => {
    (acc[r.response_code] ??= []).push(r);
    return acc;
  }, {}) ?? {};

  const codeLabel: Record<string, string> = { COMING: "Идут", NOT_COMING: "Не идут", MAYBE: "Пока не знают", NO_RESPONSE: "Без ответа" };

  return (
    <div style={{ gridColumn: "1/-1", marginTop: 4 }}>
      <button
        type="button"
        className={styles.btnMaybeOutline}
        style={{ width: "100%", minHeight: 32, fontSize: 11 }}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Скрыть ответы" : "Посмотреть ответы"}
      </button>
      {open && responses.isLoading && <div className={styles.empty} style={{ minHeight: 40, marginTop: 6 }}>Загрузка...</div>}
      {open && responses.isError && <div className={styles.empty} style={{ minHeight: 40, marginTop: 6 }}>Не удалось загрузить ответы</div>}
      {open && responses.data && (
        <div style={{ marginTop: 6, display: "grid", gap: 8 }}>
          {Object.entries(codeLabel).map(([code, label]) => {
            const group = byCode[code] ?? [];
            if (group.length === 0) return null;
            const bySquad = group.reduce<Record<string, EventResponseItem[]>>((acc, r) => {
              const name = squadName(r.squad_id);
              (acc[name] ??= []).push(r);
              return acc;
            }, {});
            return (
              <div key={code} style={{ border: "1px solid #e0e5ef", borderRadius: 10, background: "#fff", padding: "8px 10px" }}>
                <strong style={{ fontSize: 12, color: "#1a2f5a", display: "block", marginBottom: 4 }}>{label} ({group.length})</strong>
                {Object.entries(bySquad).sort(([a], [b]) => a.localeCompare(b, "ru")).map(([squad, members]) => (
                  <div key={squad} style={{ marginBottom: 4 }}>
                    <span style={{ fontSize: 10, fontWeight: 900, color: "#8a96b0", textTransform: "uppercase" }}>{squad}</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 2 }}>
                      {members.map((m) => (
                        <span key={m.user_id} style={{ fontSize: 11, background: "#f0f2f8", borderRadius: 6, padding: "2px 7px", color: "#1a2f5a" }}>
                          {m.full_name}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            );
          })}
          {responses.data.length === 0 && <div className={styles.empty} style={{ minHeight: 40 }}>Никто ещё не ответил</div>}
        </div>
      )}
    </div>
  );
}

/* ─────────── ScheduleView ─────────── */
function ScheduleView({
  events,
  weekType,
  level,
  squads,
  onRespond,
}: {
  events: ScheduleEvent[];
  weekType?: { parity: "A" | "B" | null; week_a_start: string | null };
  level: number;
  squads: Squad[];
  onRespond: RespondFn;
}) {
  const [tab, setTab] = useState<"today" | "week" | "month" | "archive">("week");
  const [filter, setFilter] = useState<"all" | "unanswered" | "coming" | "not_coming">("all");
  const now = Date.now();

  const byDate = events.filter((event) => {
    const t = new Date(event.start_datetime).getTime();
    if (tab === "archive") return t < now || event.status_code === "CANCELLED";
    if (tab === "today") return Math.abs(t - now) < 86400000;
    if (tab === "week") return t >= now - 86400000 && t <= now + 7 * 86400000;
    return t >= now - 86400000 && t <= now + 31 * 86400000;
  });

  const filtered = byDate.filter((event) => {
    if (tab === "archive" || filter === "all") return true;
    if (filter === "unanswered") return event.requires_response && !event.my_response_code;
    if (filter === "coming") return event.my_response_code === "COMING";
    if (filter === "not_coming") return event.my_response_code === "NOT_COMING";
    return true;
  });

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Расписание</h2>
        <span>{events.length} событий</span>
      </div>
      {weekType?.parity && (
        <div className={styles.weekBadge}>
          <span>Текущая неделя</span>
          <b>{weekType.parity === "A" ? "1" : "2"}</b>
        </div>
      )}
      <Tabs
        tabs={[["today", "Сегодня"], ["week", "Неделя"], ["month", "Месяц"], ["archive", "Архив"]]}
        active={tab}
        onChange={(value) => { setTab(value as typeof tab); setFilter("all"); }}
      />
      {tab !== "archive" && (
        <div className={styles.filterChips}>
          <button type="button" className={styles.chip} data-active={filter === "all"} onClick={() => setFilter("all")}>Все</button>
          <button type="button" className={styles.chip} data-active={filter === "unanswered"} onClick={() => setFilter("unanswered")}>Без ответа</button>
          <button type="button" className={styles.chip} data-active={filter === "coming"} data-color="green" onClick={() => setFilter("coming")}>Иду</button>
          <button type="button" className={styles.chip} data-active={filter === "not_coming"} data-color="red" onClick={() => setFilter("not_coming")}>Не иду</button>
        </div>
      )}
      <div className={styles.list}>
        {filtered.length === 0 && <Empty text="В этой вкладке пока пусто" />}
        {filtered.map((event) => (
          <article className={styles.row} key={event.id}>
            <AppIcon code="schedule" />
            <div>
              <strong>
                {event.title}
                {event.is_overridden && <span className={styles.inlineBadge}>изм.</span>}
                {event.status_code === "CANCELLED" && <span className={styles.inlineBadge} data-tone="warning">закрыт</span>}
              </strong>
              <span>{formatDate(event.start_datetime)} · {event.place ?? "место уточняется"}</span>
            </div>
            {event.requires_response && event.status_code !== "CANCELLED" && tab !== "archive" && (
              <ResponseButtons
                eventId={event.id}
                requiresResponse={event.requires_response}
                currentResponse={event.my_response_code}
                onRespond={onRespond}
              />
            )}
            {event.requires_response && level >= 4 && (
              <EventVoterList eventId={event.id} squads={squads} canView={level >= 4} />
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

/* ─────────── AttendanceView ─────────── */
function AttendanceView({
  records,
  canManage,
  managerLevel,
  managerSquadId,
  reportItems,
  stats,
  schedule,
  users,
}: {
  records: AttendanceRecord[];
  canManage: boolean;
  managerLevel: number;
  managerSquadId: number | null;
  reportItems: unknown[];
  stats?: ReportSummary;
  schedule: ScheduleEvent[];
  users: UserRecord[];
}) {
  const [tab, setTab] = useState<"chart" | "calendar" | "history" | "journal">("chart");
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [draftAttendance, setDraftAttendance] = useState<Record<number, string>>({});
  const manageableEvents = schedule.filter((event) => event.status_code !== "CANCELLED");
  const selectedEvent = manageableEvents.find((event) => event.id === selectedEventId) ?? null;
  const hasSelectedEvent = selectedEvent !== null;
  const eventAttendance = useAttendanceEvent(selectedEventId, canManage && hasSelectedEvent);
  const markAttendance = useMarkAttendance();
  const eventMap = new Map(schedule.map((e) => [e.id, e.title]));
  const scopeSquadId = selectedEvent?.squad_id ?? (managerLevel < 5 ? managerSquadId : null);
  const targetUsers = hasSelectedEvent
    ? users.filter((user) => {
        if (managerLevel < 5 && scopeSquadId === null) return false;
        if (typeof user.id !== "number" || user.status_code !== "ACTIVE") return false;
        if (roleLevels[user.role_code as RoleCode] < roleLevels.PARTICIPANT) return false;
        if (scopeSquadId !== null && user.squad_id !== scopeSquadId) return false;
        return true;
      })
    : [];
  const existingAttendance = new Map((eventAttendance.data ?? []).map((item) => [item.user_id, item.status_code]));
  const eventTitle = (eventId: number) => eventMap.get(eventId) ?? "Событие вне текущего расписания";

  const statusLabels: Record<string, string> = {
    PRESENT: "Присутствовал", ABSENT: "Отсутствовал", LATE: "Опоздал",
    EXCUSED: "Уважительная", SICK: "Больничный", RELEASED: "Освобождён", NOT_MARKED: "Не отмечен",
  };
  const statusOptions = ["PRESENT", "ABSENT", "LATE", "EXCUSED", "SICK", "RELEASED", "NOT_MARKED"];

  useEffect(() => {
    if (!canManage) return;
    if (selectedEventId !== null && !manageableEvents.some((event) => event.id === selectedEventId)) {
      setSelectedEventId(null);
    }
  }, [canManage, selectedEventId, manageableEvents]);

  useEffect(() => {
    if (tab === "journal" && !canManage) setTab("chart");
  }, [tab, canManage]);

  useEffect(() => {
    setDraftAttendance({});
  }, [selectedEventId]);
  const statusColors: Record<string, string> = {
    PRESENT: "#27ae60", ABSENT: "#e74c3c", LATE: "#f39c12",
    EXCUSED: "#3498db", SICK: "#9b59b6", RELEASED: "#95a5a6", NOT_MARKED: "#bdc3c7",
  };

  const statsByCode = new Map<string, number>();
  for (const r of records) statsByCode.set(r.status_code, (statsByCode.get(r.status_code) ?? 0) + 1);
  const total = records.length;
  const present = statsByCode.get("PRESENT") ?? 0;
  const absent = statsByCode.get("ABSENT") ?? 0;
  const late = statsByCode.get("LATE") ?? 0;

  // Build heatmap data: use marked_at or event start_datetime as fallback
  // Convert to local app timezone so calendar cells match displayed dates
  const eventDateMap = new Map(schedule.map((e) => [e.id, e.start_datetime]));
  const toLocalDate = (iso: string) =>
    new Intl.DateTimeFormat("sv-SE", { timeZone: _appTimezone }).format(new Date(iso));
  const heatData = records
    .map((r) => {
      const dateStr = r.marked_at ?? eventDateMap.get(r.event_id) ?? null;
      if (!dateStr) return null;
      return { date: toLocalDate(dateStr), status: r.status_code };
    })
    .filter((r): r is { date: string; status: string } => r !== null);

  // Monthly bar chart data
  const monthCounts: Record<string, number> = {};
  for (const r of records) {
    if (!r.marked_at) continue;
    const month = new Intl.DateTimeFormat("ru-RU", { month: "short", timeZone: _appTimezone }).format(new Date(r.marked_at));
    if (r.status_code === "PRESENT") monthCounts[month] = (monthCounts[month] ?? 0) + 1;
  }
  const barData = Object.entries(monthCounts).slice(-6).map(([label, value]) => ({ label, value, color: "#27ae60" }));

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Посещаемость</h2>
        <span>{canManage ? "можно отмечать людей" : "только свои"}</span>
      </div>
      <Tabs
        tabs={[
          ["chart", "Графики"],
          ["calendar", "Календарь"],
          ["history", "История"],
          ...(canManage ? ([["journal", "Журнал"]] as Array<["journal", string]>) : []),
        ]}
        active={tab}
        onChange={(v) => setTab(v as typeof tab)}
      />

      {tab === "chart" && (
        <div>
          <div className={styles.chartsSection}>
            <div className={styles.chartSectionTitle}>Распределение по статусам</div>
            {total > 0
              ? <AttendanceDonut present={present} absent={absent} late={late} total={total} />
              : <Empty text="Отметок пока нет" />
            }
          </div>
          {barData.length > 0 && (
            <div className={styles.chartsSection}>
              <div className={styles.chartSectionTitle}>Присутствия по месяцам</div>
              <BarChart data={barData} height={130} />
            </div>
          )}
        </div>
      )}

      {tab === "calendar" && (
        <div className={styles.chartsSection}>
          <CalendarHeatmap records={heatData} />
        </div>
      )}

      {tab === "history" && (
        <div className={styles.list}>
          {records.length === 0 && <Empty text="Отметок пока нет" />}
          {records.map((record) => (
            <article className={styles.row} key={record.id}>
              <AppIcon code="attendance" />
              <div>
                <strong>{eventTitle(record.event_id)}</strong>
                <span style={{ color: statusColors[record.status_code] ?? "#65708a" }}>
                  {statusLabels[record.status_code] ?? record.status_code} · {formatDate(record.marked_at)}
                </span>
              </div>
            </article>
          ))}
        </div>
      )}

      {tab === "journal" && canManage && (
        <div className={styles.dashboardStack}>
          <div className={styles.formBlock}>
            <select
              value={selectedEventId ?? ""}
              onChange={(event) => setSelectedEventId(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">{manageableEvents.length === 0 ? "Нет доступных событий" : "Выберите событие"}</option>
              {manageableEvents.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.title} · {formatDate(event.start_datetime)}
                </option>
              ))}
            </select>
          </div>
          {hasSelectedEvent && targetUsers.length > 0 && (
            <div className={styles.commandStrip}>
              <button
                type="button"
                style={{ background: "#27ae60" }}
                onClick={() => {
                  const preset: Record<number, string> = {};
                  for (const u of targetUsers) preset[u.id as number] = "PRESENT";
                  setDraftAttendance(preset);
                }}
              >
                Все присутствуют
              </button>
              <button
                type="button"
                style={{ background: "#e74c3c" }}
                onClick={() => {
                  const preset: Record<number, string> = {};
                  for (const u of targetUsers) preset[u.id as number] = "ABSENT";
                  setDraftAttendance(preset);
                }}
              >
                Все отсутствуют
              </button>
            </div>
          )}
          <div className={styles.list}>
            {!hasSelectedEvent && <Empty text="Выберите событие для отметки" />}
            {hasSelectedEvent && targetUsers.length === 0 && <Empty text="Нет участников для отметки" />}
            {targetUsers.map((user) => {
              const userId = user.id as number;
              const value = draftAttendance[userId] ?? existingAttendance.get(userId) ?? "NOT_MARKED";
              return (
                <div className={styles.memberRow} key={userId}>
                  <div>
                    <strong>{user.full_name}</strong>
                    <span style={{ color: value === "PRESENT" ? "#27ae60" : value === "ABSENT" ? "#e74c3c" : value === "LATE" ? "#f39c12" : "#8a96b0" }}>
                      {statusLabels[value] ?? value}
                    </span>
                  </div>
                  <select
                    value={value}
                    onChange={(event) => setDraftAttendance((prev) => ({ ...prev, [userId]: event.target.value }))}
                  >
                    {statusOptions.map((status) => (
                      <option key={status} value={status}>{statusLabels[status] ?? status}</option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>
          {hasSelectedEvent && targetUsers.length > 0 && (
            <div className={styles.commandStrip}>
              <button
                type="button"
                disabled={markAttendance.isPending}
                onClick={() => {
                  markAttendance.mutate(
                    {
                      eventId: selectedEvent!.id,
                      entries: targetUsers.map((user) => ({
                        user_id: user.id as number,
                        status_code: draftAttendance[user.id as number] ?? existingAttendance.get(user.id as number) ?? "NOT_MARKED",
                      })),
                    },
                    {
                      onSuccess: () => toast("Журнал явки сохранён", "success"),
                      onError: () => toast("Не удалось сохранить журнал", "error"),
                    },
                  );
                }}
              >
                {markAttendance.isPending ? "Сохраняем..." : "Сохранить отметки"}
              </button>
            </div>
          )}
        </div>
      )}

      {canManage && tab !== "journal" && (
        <div className={styles.commandStrip}>
          <button type="button" onClick={() => setTab("journal")}>Открыть журнал отметки</button>
        </div>
      )}
    </div>
  );
}

function getWeekStart(): Date {
  const d = new Date();
  const day = d.getDay();
  d.setDate(d.getDate() - (day === 0 ? 6 : day - 1));
  d.setHours(0, 0, 0, 0);
  return d;
}

function getNextMonday(): Date {
  const d = new Date();
  const day = d.getDay();
  d.setDate(d.getDate() + (day === 0 ? 1 : 8 - day));
  d.setHours(0, 0, 0, 0);
  return d;
}

function formatShortDate(d: Date): string {
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(d);
}

/* ─────────── NormativesView ─────────── */
function NormativesView({
  items,
  submissions,
  pending,
  history,
  canSubmit,
  canReview,
  onSubmit,
  onReview,
  isBusy,
}: {
  items: Normative[];
  submissions: NormativeSubmission[];
  pending: NormativeSubmission[];
  history: NormativeSubmission[];
  canSubmit: boolean;
  canReview: boolean;
  onSubmit: (normativeId: number, comment?: string, fileIds?: number[]) => void;
  onReview: (submissionId: number, statusCode: string, reviewerComment?: string) => void;
  isBusy: boolean;
}) {
  const [tab, setTab] = useState<"active" | "mine" | "pending" | "accepted" | "history" | "archive">("active");
  const reviewHistory = canReview ? history : [];
  const accepted = (canReview ? reviewHistory : submissions).filter((item) => item.status_code === "ACCEPTED");
  const historyRows = reviewHistory.filter((item) => !isPendingNormativeStatus(item.status_code));
  const activeItems = items.filter((item) => item.is_active);
  const archiveItems = items.filter((item) => !item.is_active);
  const upload = useUploadFile();
  const openFile = useOpenFile();
  const getFileBlob = useGetFileBlob();
  const sendFileToBotDM = useSendFileToBotDM();
  const [videoModal, setVideoModal] = useState<{ src?: string; embedSrc?: string } | null>(null);
  const [uploadedFiles, setUploadedFiles] = useState<Record<number, Array<{ id: number; name: string }>>>({});
  const [comments, setComments] = useState<Record<number, string>>({});

  const openVideoModal = async (url?: string | null, fileId?: number | null) => {
    if (url) {
      const embed = toYouTubeEmbedUrl(url);
      setVideoModal(embed ? { embedSrc: embed } : { src: url });
    } else if (fileId) {
      try {
        const blobUrl = await getFileBlob.mutateAsync(fileId);
        setVideoModal({ src: blobUrl });
      } catch {
        toast("Не удалось загрузить видео", "error");
      }
    }
  };

  const tabs: Array<["active" | "mine" | "pending" | "accepted" | "history" | "archive", string]> = [
    ["active", "Активные"],
    ...(canSubmit ? ([["mine", "Мои сдачи"]] as Array<["mine", string]>) : []),
    ...(canReview ? ([["pending", "На проверке"]] as Array<["pending", string]>) : []),
    ...(canSubmit || canReview ? ([["accepted", "Принятые"]] as Array<["accepted", string]>) : []),
    ...(canReview ? ([["history", "История"]] as Array<["history", string]>) : []),
    ...(canReview ? ([["archive", "Архив"]] as Array<["archive", string]>) : []),
  ];

  useEffect(() => {
    if (!tabs.some(([value]) => value === tab)) setTab("active");
  }, [tab, tabs.length]);

  const handleFileChange = async (normativeId: number, file: File) => {
    try {
      const result = await upload.mutateAsync(file);
      setUploadedFiles((prev) => ({ ...prev, [normativeId]: [...(prev[normativeId] ?? []), { id: result.id, name: file.name }] }));
    } catch {
      toast("Не удалось загрузить файл", "error");
    }
  };

  return (
    <div className={styles.panel}>
      {videoModal && (
        <VideoPlayerModal
          src={videoModal.src}
          embedSrc={videoModal.embedSrc}
          onClose={() => {
            if (videoModal.src?.startsWith("blob:")) URL.revokeObjectURL(videoModal.src);
            setVideoModal(null);
          }}
        />
      )}
      <div className={styles.panelHeader}>
        <h2>Нормативы</h2>
        <span>{activeItems.length} активных</span>
      </div>
      <Tabs
        tabs={tabs}
        active={tab}
        onChange={(value) => setTab(value as typeof tab)}
      />
      <div className={styles.list}>
        {tab === "active" && (
          <>
            {/* Progress overview */}
            {activeItems.length > 0 && (
              <div className={styles.chartsSection} style={{ marginBottom: 10 }}>
                <div className={styles.chartSectionTitle}>Прогресс сдачи</div>
                <div className={styles.normProgressList}>
                  {activeItems.slice(0, 5).map((item) => {
                    const sub = submissions.find((s) => s.normative_id === item.id);
                    const pct = !sub ? 0 : sub.status_code === "ACCEPTED" ? 100 : isPendingNormativeStatus(sub.status_code) ? 50 : 10;
                    const color = pct === 100 ? "#27ae60" : pct === 50 ? "#f39c12" : "#e8ecf0";
                    return (
                      <div key={item.id} className={styles.normProgressItem}>
                        <strong>{item.title}</strong>
                        <AnimatedProgress value={pct} max={100} color={color === "#e8ecf0" ? "#d0d6e2" : color} height={6} showPercent={false} />
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </>
        )}
        {tab === "active" && (() => {
          const weekStart = getWeekStart();
          const nextMonday = getNextMonday();
          return activeItems.map((item) => {
            const attached = uploadedFiles[item.id] ?? [];
            const acceptedThisWeek = submissions.find(
              (s) => s.normative_id === item.id && s.status_code === "ACCEPTED" && new Date(s.submitted_at) >= weekStart,
            );
            const pendingSub = !acceptedThisWeek && submissions.find(
              (s) => s.normative_id === item.id && isPendingNormativeStatus(s.status_code),
            );
            return (
              <article className={styles.row} key={item.id}>
                <AppIcon code="norms" />
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.description ?? "описание будет добавлено"} · до {formatDate(item.deadline_at)}</span>
                </div>
                {(item.instruction_video_url || item.instruction_video_file_id) && (
                  <VideoThumbnailCard
                    title="Смотреть видео выполнения"
                    isLoading={getFileBlob.isPending}
                    onClick={() => openVideoModal(item.instruction_video_url, item.instruction_video_file_id)}
                  />
                )}
                {acceptedThisWeek ? (
                  <div className={styles.normLocked}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <path d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z"/>
                    </svg>
                    Сдан на этой неделе · следующая сдача с {formatShortDate(nextMonday)}
                  </div>
                ) : pendingSub ? (
                  <div className={styles.normPending}>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
                    </svg>
                    Отправлено на проверку командиру
                  </div>
                ) : canSubmit ? (
                  <div className={styles.fileUploadArea}>
                    {attached.map((file) => (
                      <div className={styles.fileAttached} key={file.id}>
                        <span>{file.name}</span>
                        <button
                          type="button"
                          onClick={() => setUploadedFiles((prev) => ({ ...prev, [item.id]: (prev[item.id] ?? []).filter((entry) => entry.id !== file.id) }))}
                        >
                          Убрать
                        </button>
                      </div>
                    ))}
                    <div className={styles.submissionCommentRow}>
                      <input
                        placeholder="Комментарий к сдаче..."
                        value={comments[item.id] ?? ""}
                        onChange={(e) => setComments((prev) => ({ ...prev, [item.id]: e.target.value }))}
                      />
                      <FilePicker
                        accept={FILE_PREVIEW_ACCEPT}
                        label={attached.length ? "Добавить ещё файл" : "Прикрепить файл"}
                        iconSrc={PAPERCLIP_ICON_SRC}
                        onFile={(file) => handleFileChange(item.id, file)}
                        className={`${styles.fileButton} ${styles.fileIconButton}`}
                      />
                    </div>
                    <button
                      className={styles.iconAction}
                      type="button"
                      disabled={isBusy || upload.isPending}
                      onClick={() => onSubmit(item.id, comments[item.id] || undefined, attached.map((file) => file.id))}
                    >
                      {isBusy || upload.isPending ? "Отправляем..." : "Отправить на проверку"}
                    </button>
                  </div>
                ) : (
                  <div className={styles.normReadOnly}>Требование доступно для просмотра. Сдача откроется после отправки анкеты.</div>
                )}
              </article>
            );
          });
        })()}
        {tab === "mine" && (submissions.length === 0
          ? <Empty text="Сдач пока нет" />
          : submissions.map((item) => <SubmissionRow key={item.id} item={item} />)
        )}
        {tab === "pending" && (
          canReview
            ? (pending.length === 0 ? <Empty text="Нет сдач на проверке" /> : pending.map((item) => (
              <SubmissionRow key={item.id} item={item} onReview={onReview} isBusy={isBusy} />
            )))
            : <Empty text="Проверка доступна командирам" />
        )}
        {tab === "accepted" && (accepted.length === 0
          ? <Empty text="Принятых сдач пока нет" />
          : accepted.map((item) => <SubmissionRow key={item.id} item={item} />)
        )}
        {tab === "history" && (
          canReview
            ? (historyRows.length === 0 ? <Empty text="История сдач пока пуста" /> : historyRows.map((item) => (
              <SubmissionRow key={item.id} item={item} />
            )))
            : <Empty text="История доступна командирам" />
        )}
        {tab === "archive" && (archiveItems.length === 0
          ? <Empty text="Архив нормативов пуст" />
          : archiveItems.map((item) => (
            <article className={styles.row} key={item.id}>
              <AppIcon code="norms" />
              <div>
                <strong>{item.title}</strong>
                <span>{item.description ?? "закрытый норматив"} · до {formatDate(item.deadline_at)}</span>
              </div>
              {(item.instruction_video_url || item.instruction_video_file_id) && (
                <VideoThumbnailCard
                  title="Смотреть видео выполнения"
                  isLoading={getFileBlob.isPending}
                  onClick={() => openVideoModal(item.instruction_video_url, item.instruction_video_file_id)}
                />
              )}
            </article>
          ))
        )}
      </div>
    </div>
  );
}

/* ─────────── NotificationsView ─────────── */
function NotificationsView({
  items,
  onRead,
  onReadAll,
  isBusy,
}: {
  items: Notification[];
  onRead: (id: number) => void;
  onReadAll: () => void;
  isBusy: boolean;
}) {
  const unread = items.filter((item) => !item.is_read);
  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Уведомления</h2>
        <span>{formatUnreadCount(unread.length)}</span>
      </div>
      {unread.length > 1 && (
        <div className={styles.commandStrip}>
          <button type="button" disabled={isBusy} onClick={onReadAll}>Прочитать все</button>
        </div>
      )}
      <div className={styles.list}>
        {items.length === 0 && <Empty text="Уведомлений пока нет" />}
        {items.map((item) => (
          <article className={styles.row} key={item.id} data-muted={item.is_read}>
            <AppIcon code="notifications" />
            <div>
              <strong>{item.title}</strong>
              <span>{item.body ?? item.type_code} · {formatDate(item.created_at)}</span>
            </div>
            {!item.is_read && (
              <button className={styles.iconAction} type="button" onClick={() => onRead(item.id)}>Прочитано</button>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

/* ─────────── AnnouncementsView ─────────── */
function AnnouncementsView({
  items,
  level,
  squads,
  profileSquadId,
  onCreate,
  isSubmitting,
}: {
  items: Announcement[];
  level: number;
  squads: Squad[];
  profileSquadId: number | null;
  onCreate: (payload: AnnouncementPayload) => void;
  isSubmitting: boolean;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [targetType, setTargetType] = useState<"ALL" | "SQUAD">(() => level >= 6 ? "ALL" : "SQUAD");
  const [targetSquadId, setTargetSquadId] = useState("");
  const [sendToApp, setSendToApp] = useState(true);
  const [sendToTg, setSendToTg] = useState(true);
  const [attachment, setAttachment] = useState<{ id: number; name: string } | null>(null);
  const upload = useUploadFile();
  const openFile = useOpenFile();
  const ownSquadLabel = squads.find((squad) => squad.id === profileSquadId)?.name ?? (profileSquadId ? `Отделение #${profileSquadId}` : "отделение не назначено");
  const selectedTargetSquadId = targetType === "SQUAD"
    ? (targetSquadId ? Number(targetSquadId) : level < 6 ? profileSquadId : null)
    : null;
  const targetReady = targetType !== "SQUAD" || selectedTargetSquadId !== null;
  const channelsReady = sendToApp || sendToTg;
  const canSubmit = title.trim().length > 0 && body.trim().length > 0 && targetReady && channelsReady;

  useEffect(() => {
    if (level < 6 && targetType !== "SQUAD") {
      setTargetType("SQUAD");
      setTargetSquadId("");
    }
  }, [level, targetType]);

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Объявления</h2>
        <span>{items.length} записей</span>
      </div>
      <div className={`${styles.formBlock} ${styles.announcementComposer}`}>
        <label className={styles.fieldLabel}>
          <span>Заголовок</span>
          <input placeholder="Коротко о главном" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <div className={styles.announcementTopGrid}>
          <label className={styles.fieldLabel}>
            <span>Получатели</span>
            <select
              value={targetType}
              disabled={level < 6}
              onChange={(event) => {
                setTargetType(event.target.value as "ALL" | "SQUAD");
                setTargetSquadId("");
              }}
            >
              {level >= 6 && <option value="ALL">Всем участникам</option>}
              <option value="SQUAD">{level >= 6 ? "Отделению" : "Своё отделение"}</option>
            </select>
          </label>
          {targetType === "SQUAD" && (
            <label className={styles.fieldLabel}>
              <span>Отделение</span>
              {level >= 6 ? (
                <select value={targetSquadId} onChange={(event) => setTargetSquadId(event.target.value)}>
                  <option value="">Выберите отделение</option>
                  {squads.map((squad) => (
                    <option key={squad.id} value={squad.id}>{squad.name}</option>
                  ))}
                </select>
              ) : (
                <input value={ownSquadLabel} disabled readOnly />
              )}
            </label>
          )}
          <div className={styles.announcementAttachment}>
            <span>Вложение</span>
            {attachment && (
              <div className={styles.fileAttached}>
                <span>{attachment.name}</span>
                <button type="button" onClick={() => setAttachment(null)}>Убрать</button>
              </div>
            )}
            <FilePicker
              accept={FILE_PREVIEW_ACCEPT}
              label={upload.isPending ? "Загружаем..." : attachment ? "Заменить файл" : "Прикрепить файл"}
              className={`${styles.fileButton} ${styles.secondaryFileButton}`}
              onFile={async (file) => {
                try {
                  const result = await upload.mutateAsync(file);
                  setAttachment({ id: result.id, name: result.original_name || file.name });
                } catch {
                  toast("Не удалось загрузить вложение", "error");
                }
              }}
            />
          </div>
        </div>
        <label className={styles.fieldLabel}>
          <span>Текст</span>
          <textarea placeholder="Текст объявления" rows={2} value={body} onChange={(e) => setBody(e.target.value)} />
        </label>
        <div className={styles.announcementChannels} role="group" aria-label="Каналы отправки">
          <button type="button" data-active={sendToApp} onClick={() => setSendToApp((value) => !value)}>Приложение</button>
          <button type="button" data-active={sendToTg} onClick={() => setSendToTg((value) => !value)}>Telegram</button>
        </div>
        <button
          className={styles.primaryButton}
          type="button"
          disabled={!canSubmit || isSubmitting || upload.isPending}
          onClick={() => onCreate({
            title,
            body,
            target_type: targetType,
            target_squad_id: selectedTargetSquadId,
            file_id: attachment?.id ?? null,
            status_code: "DRAFT",
            send_to_tg: sendToTg,
            send_to_app: sendToApp,
          })}
        >
          {isSubmitting ? "Отправляем..." : "Отправить объявление"}
        </button>
      </div>
      <div className={styles.list}>
        {items.length === 0 && <Empty text="Объявлений пока нет" />}
        {items.map((item) => (
          <article className={styles.row} key={item.id}>
            <AppIcon code="announcements" />
            <div>
              <strong>{item.title}</strong>
              <span>{item.status_code} · {item.body?.slice(0, 60)}</span>
            </div>
            {item.file_id && (
              <div className={styles.filePreviewActions}>
                <button type="button" disabled={openFile.isPending} onClick={() => openFile.mutate({ fileId: item.file_id ?? undefined })}>
                  {openFile.isPending ? "Открываем..." : "Открыть вложение"}
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

/* ─────────── AppealsView ─────────── */
function AppealsView({
  items,
  currentUserId,
  onCreate,
  isSubmitting,
}: {
  items: Appeal[];
  currentUserId: number | null;
  onCreate: (payload: AppealPayload) => void;
  isSubmitting: boolean;
}) {
  const [form, setForm] = useState<AppealPayload>({
    subject: "",
    description: "",
    category_code: "OTHER",
    urgency_code: "NORMAL",
    is_anonymous: false,
    file_id: null,
  });
  const [appealAttachment, setAppealAttachment] = useState<{ id: number; name: string } | null>(null);
  const canSubmit = form.subject.trim().length > 0 && form.description.trim().length > 0;
  const [openAppealId, setOpenAppealId] = useState<number | null>(null);

  const upload = useUploadFile();
  const openFile = useOpenFile();
  const messages = useAppealMessages(openAppealId, openAppealId !== null);
  const createMessage = useCreateAppealMessage();
  const [msgText, setMsgText] = useState("");

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Обращения</h2>
        <span>{items.length} создано</span>
      </div>

      {openAppealId === null ? (
        <>
          <div className={styles.formBlock}>
            <input
              placeholder="Тема обращения"
              value={form.subject}
              onChange={(e) => setForm({ ...form, subject: e.target.value })}
            />
            <textarea
              placeholder="Опишите проблему или предложение"
              rows={3}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <select value={form.category_code} onChange={(e) => setForm({ ...form, category_code: e.target.value })}>
              <option value="TECHNICAL">Техническая проблема</option>
              <option value="SCHEDULE">Проблема с расписанием</option>
              <option value="ATTENDANCE_ERROR">Ошибка в посещаемости</option>
              <option value="GRADE_ERROR">Ошибка в оценке</option>
              <option value="PERSONAL">Личный вопрос</option>
              <option value="COMPLAINT">Жалоба</option>
              <option value="SUGGESTION">Предложение</option>
              <option value="OTHER">Другое</option>
            </select>
            <select value={form.urgency_code} onChange={(e) => setForm({ ...form, urgency_code: e.target.value })}>
              <option value="LOW">Низкая срочность</option>
              <option value="NORMAL">Обычная срочность</option>
              <option value="HIGH">Срочно</option>
              <option value="URGENT">Очень срочно</option>
            </select>
            <label className={styles.checkboxLine}>
              <input
                type="checkbox"
                checked={form.is_anonymous}
                onChange={(e) => setForm({ ...form, is_anonymous: e.target.checked })}
              />
              <span>Отправить анонимно</span>
            </label>
            {appealAttachment && (
              <div className={styles.fileAttached}>
                <span>{appealAttachment.name}</span>
                <button type="button" onClick={() => { setAppealAttachment(null); setForm({ ...form, file_id: null }); }}>Убрать</button>
              </div>
            )}
            <FilePicker
              accept={FILE_PREVIEW_ACCEPT}
              label={upload.isPending ? "Загружаем..." : appealAttachment ? "Заменить вложение" : "Прикрепить файл или видео"}
              className={styles.fileButton}
              onFile={async (file) => {
                try {
                  const result = await upload.mutateAsync(file);
                  setAppealAttachment({ id: result.id, name: result.original_name || file.name });
                  setForm((prev) => ({ ...prev, file_id: result.id }));
                } catch {
                  toast("Не удалось загрузить вложение", "error");
                }
              }}
            />
            <button type="button" disabled={!canSubmit || isSubmitting || upload.isPending} onClick={() => onCreate(form)}>
              {isSubmitting ? "Отправляем..." : "Отправить обращение"}
            </button>
          </div>

          <div className={styles.list}>
            {items.length === 0 && <Empty text="Обращений пока нет" />}
            {items.map((item) => (
              <article className={styles.row} key={item.id} style={{ cursor: "pointer" }} onClick={() => setOpenAppealId(item.id)}>
                <AppIcon code="appeals" />
                <div>
                  <strong>{item.subject}</strong>
                  <span>{appealStatusLabel(item.status_code)} · {item.category_code} · {formatDate(item.created_at)}</span>
                </div>
                {item.file_id && (
                  <div className={styles.filePreviewActions}>
                    <button
                      type="button"
                      disabled={openFile.isPending}
                      onClick={(event) => {
                        event.stopPropagation();
                        openFile.mutate({ fileId: item.file_id ?? undefined });
                      }}
                    >
                      {openFile.isPending ? "Открываем..." : "Открыть вложение"}
                    </button>
                  </div>
                )}
                <span style={{ fontSize: 10, color: "#8a96b0", gridColumn: "1/-1" }}>Нажмите чтобы открыть переписку →</span>
              </article>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className={styles.commandStrip}>
            <button type="button" onClick={() => setOpenAppealId(null)}>← Назад к списку</button>
          </div>
          {(() => {
            const appeal = items.find((a) => a.id === openAppealId);
            return appeal ? (
              <div className={styles.nextItem}>
                <span>Тема</span>
                <strong>{appeal.subject}</strong>
                <small>{appealStatusLabel(appeal.status_code)} · {appeal.urgency_code}</small>
                {appeal.resolution_text && <small>Решение: {appeal.resolution_text}</small>}
                {appeal.file_id && (
                  <div className={styles.filePreviewActions}>
                    <button type="button" disabled={openFile.isPending} onClick={() => openFile.mutate({ fileId: appeal.file_id ?? undefined })}>
                      {openFile.isPending ? "Открываем..." : "Открыть вложение"}
                    </button>
                  </div>
                )}
              </div>
            ) : null;
          })()}
          <div className={styles.messageThread}>
            {messages.isLoading && <Empty text="Загрузка переписки..." />}
            {(messages.data ?? []).map((msg) => (
              <MessageBubble key={msg.id} msg={msg} isMine={msg.author_id === currentUserId} />
            ))}
            {messages.data?.length === 0 && <Empty text="Переписка пуста" />}
          </div>
          <div className={styles.messageInput}>
            <input
              placeholder="Написать сообщение..."
              value={msgText}
              onChange={(e) => setMsgText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && msgText.trim() && openAppealId) {
                  createMessage.mutate({ appealId: openAppealId, body: msgText.trim() });
                  setMsgText("");
                }
              }}
            />
            <button
              type="button"
              disabled={!msgText.trim() || createMessage.isPending}
              onClick={() => {
                if (msgText.trim() && openAppealId) {
                  createMessage.mutate({ appealId: openAppealId, body: msgText.trim() });
                  setMsgText("");
                }
              }}
            >
              Отправить
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function MessageBubble({ msg, isMine }: { msg: AppealMessage; isMine: boolean }) {
  return (
    <div className={styles.messageBubble} data-mine={isMine}>
      <p>{msg.body}</p>
      <small>{formatDate(msg.created_at)}</small>
    </div>
  );
}

function appealStatusLabel(code: string) {
  const labels: Record<string, string> = {
    CREATED: "Создано",
    IN_PROGRESS: "В работе",
    NEEDS_INFO: "Нужна информация",
    RESOLVED: "Решено",
    REJECTED: "Отклонено",
    CLOSED: "Закрыто",
  };
  return labels[code] ?? code;
}

/* ─────────── ReportsView ─────────── */
function ReportsView({
  level,
  attendance,
  grades,
  normatives,
}: {
  level: number;
  attendance?: ReportSummary;
  grades?: ReportSummary;
  normatives?: ReportSummary;
}) {
  const [tab, setTab] = useState<"attendance" | "grades" | "normatives" | "export">("attendance");
  const exportReport = useExportReportViaBot();
  const tabs: Array<[typeof tab, string]> = [["attendance", "Явка"], ["grades", "Оценки"], ["normatives", "Нормативы"]];
  if (level >= 6) tabs.push(["export", "Экспорт"]);
  const activeReport = tab === "grades" ? grades : tab === "normatives" ? normatives : attendance;
  const items = activeReport?.items ?? [];

  useEffect(() => {
    if (tab === "export" && level < 6) setTab("attendance");
  }, [level, tab]);

  const statusLabelMap: Record<string, string> = {
    PRESENT: "Присутствовал",
    ABSENT: "Отсутствовал",
    LATE: "Опоздал",
    EXCUSED: "Уважительная",
    SICK: "Больничный",
    RELEASED: "Освобождён",
    NOT_MARKED: "Не отмечен",
    PENDING: "На проверке",
    ACCEPTED: "Принято",
    REJECTED: "Отклонено",
    NEEDS_REDO: "Пересдача",
    OVERDUE: "Просрочено",
  };
  const reportRows = items.map((item, index) => {
    const rec = item as Record<string, unknown>;
    const key = String(rec.status_code ?? rec.grade_value ?? rec.label ?? `#${index + 1}`);
    return {
      key,
      label: statusLabelMap[key] ?? key,
      value: extractCount(item),
    };
  });
  const totalCount = reportRows.reduce((sum, item) => sum + item.value, 0);
  const leader = [...reportRows].sort((left, right) => right.value - left.value)[0];

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Отчёты</h2>
        <span>{activeReport?.title ?? "сводки"}</span>
      </div>
      <Tabs
        tabs={tabs}
        active={tab}
        onChange={(value) => setTab(value as typeof tab)}
      />

      {tab === "export" ? (
        <div className={styles.dashboardStack}>
          <div className={styles.nextItem}>
            <span>Экспорт данных</span>
            <strong>Сводный отчёт CSV</strong>
            <small>Бот отправит файл в личные сообщения</small>
          </div>
          <div className={styles.commandStrip}>
            <button
              type="button"
              disabled={exportReport.isPending}
              onClick={() => {
                exportReport.mutate(undefined, {
                  onSuccess: () => toast("CSV отправлен в личные сообщения", "success"),
                  onError: () => toast("Не удалось отправить", "error"),
                });
              }}
            >
              {exportReport.isPending ? "Отправляем..." : "Получить CSV"}
            </button>
          </div>
        </div>
      ) : (
        <>
          {items.length === 0 ? (
            <Empty text="Данных пока нет" />
          ) : (
            <>
              <div className={styles.reportOverview}>
                <div className={styles.reportStat}>
                  <span>Всего</span>
                  <strong>{totalCount}</strong>
                </div>
                <div className={styles.reportStat}>
                  <span>Лидер</span>
                  <strong>{leader?.label ?? "—"}</strong>
                </div>
                <div className={styles.reportStat}>
                  <span>Категорий</span>
                  <strong>{reportRows.length}</strong>
                </div>
              </div>
              {/* Bar chart */}
              <div className={styles.chartsSection}>
                <div className={styles.chartSectionTitle}>{activeReport?.title ?? "Данные"}</div>
                <BarChart
                  data={reportRows.map((item) => {
                    const key = item.key;
                    return {
                      label: item.label.slice(0, 5),
                      value: item.value,
                      color: key === "PRESENT" || key === "ACCEPTED" || key === "5" ? "#27ae60"
                        : key === "ABSENT" || key === "REJECTED" || key === "2" || key === "1" ? "#e74c3c"
                        : key === "LATE" || key === "NEEDS_REDO" || key === "3" ? "#f39c12"
                        : "#3498db",
                    };
                  })}
                  height={140}
                />
              </div>
              {/* Summary numbers */}
              <div className={styles.statsGrid2}>
                {reportRows.slice(0, 4).map((item, index) => {
                  const key = item.key;
                  return (
                    <StatNumber
                      key={index}
                      value={item.value}
                      label={item.label}
                      color={key === "PRESENT" || key === "ACCEPTED" || key === "5" ? "#27ae60"
                        : key === "ABSENT" || key === "REJECTED" ? "#e74c3c"
                        : "#1a2f5a"}
                    />
                  );
                })}
              </div>
            </>
          )}
          {tab === "grades" && items.length > 0 && (
            <div className={styles.chartsSection} style={{ marginTop: 12 }}>
              <div className={styles.chartSectionTitle}>Распределение оценок</div>
              <GradeDistribution
                grades={Object.fromEntries(
                  reportRows.map((item) => [item.key, item.value])
                )}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* ─────────── LearningView ─────────── */
function LearningView({ items, courses, canTrack }: { items: LearningMaterial[]; courses: LearningCourse[]; canTrack: boolean }) {
  const [tab, setTab] = useState<"main" | "candidates" | "courses">("main");
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const [videoModal, setVideoModal] = useState<{ src?: string; embedSrc?: string } | null>(null);
  const markViewed = useMarkMaterialViewed();
  const openFile = useOpenFile();
  const getFileBlob = useGetFileBlob();
  const sendFileToBotDM = useSendFileToBotDM();

  const openVideoModal = async (url?: string | null, fileId?: number | null) => {
    if (url) {
      const embed = toYouTubeEmbedUrl(url);
      setVideoModal(embed ? { embedSrc: embed } : { src: url });
    } else if (fileId) {
      try {
        const blobUrl = await getFileBlob.mutateAsync(fileId);
        setVideoModal({ src: blobUrl });
      } catch {
        toast("Не удалось загрузить видео", "error");
      }
    }
  };
  const audienceItems = items.filter((item) => {
    if (tab === "candidates") return item.audience_code === "CANDIDATE";
    return item.audience_code !== "CANDIDATE";
  });
  const visibleItems = selectedCourseId === null ? audienceItems : audienceItems.filter((item) => item.course_id === selectedCourseId);
  const selectedCourse = courses.find((course) => course.id === selectedCourseId);

  const typeLabels: Record<string, string> = {
    VIDEO: "Видео",
    TEXT: "Текст",
    NORMATIVE_CARD: "Карточка норматива",
    IMAGE: "Изображение",
    LINK: "Ссылка",
    PDF: "PDF",
    FILE: "Файл",
    COLLECTION: "Подборка",
  };

  return (
    <div className={styles.panel}>
      {videoModal && (
        <VideoPlayerModal
          src={videoModal.src}
          embedSrc={videoModal.embedSrc}
          onClose={() => {
            if (videoModal.src?.startsWith("blob:")) URL.revokeObjectURL(videoModal.src);
            setVideoModal(null);
          }}
        />
      )}
      <div className={styles.panelHeader}>
        <h2>Материалы</h2>
        <span>{visibleItems.length} доступно</span>
      </div>
      <Tabs
        tabs={[["main", "Основной состав"], ["candidates", "Отбор"], ["courses", "Курсы"]]}
        active={tab}
        onChange={(value) => { setTab(value as typeof tab); setSelectedCourseId(null); }}
      />
      <div className={styles.list}>
        {tab !== "courses" && selectedCourse && (
          <div className={styles.commandStrip}>
            <small>{selectedCourse.title}</small>
            <button type="button" onClick={() => setSelectedCourseId(null)}>Все материалы</button>
          </div>
        )}
        {tab !== "courses" && visibleItems.length === 0 && (
          <Empty text={tab === "candidates" ? "Материалы отбора появятся после публикации" : "Материалы основного состава появятся после публикации"} />
        )}
        {tab !== "courses" && visibleItems.map((item) => (
          <article className={styles.row} key={item.id} style={{ cursor: "default" }}>
            <AppIcon code="learning" />
            <div>
              <strong>{item.title}</strong>
              <span>{typeLabels[item.type_code] ?? item.type_code} · {item.description ?? "материал подготовки"}{item.duration_minutes ? ` · ${item.duration_minutes} мин` : ""}</span>
            </div>
            {(item.external_url || item.file_id) && (item.type_code === "VIDEO" ? (
              <VideoThumbnailCard
                title={item.external_url ? "Смотреть видео" : "Смотреть видео"}
                isLoading={getFileBlob.isPending}
                onClick={() => openVideoModal(item.external_url, item.file_id)}
              />
            ) : (
              <div className={styles.filePreviewActions}>
                {item.file_id && (
                  <button
                    type="button"
                    disabled={sendFileToBotDM.isPending}
                    onClick={() => sendFileToBotDM.mutate(item.file_id!, {
                      onSuccess: () => toast("Файл отправлен в личные сообщения", "success"),
                      onError: () => toast("Не удалось отправить файл", "error"),
                    })}
                  >
                    {sendFileToBotDM.isPending ? "Отправляем..." : "Отправить в бота"}
                  </button>
                )}
                {item.external_url && (
                  <button type="button" onClick={() => {
                    if (typeof window !== "undefined" && (window as unknown as Record<string, unknown>).Telegram) {
                      (window as unknown as { Telegram: { WebApp: { openLink: (url: string) => void } } }).Telegram.WebApp.openLink(item.external_url!);
                    } else {
                      window.open(item.external_url!, "_blank");
                    }
                  }}>
                    Открыть материал
                  </button>
                )}
              </div>
            ))}
          </article>
        ))}
        {tab === "courses" && courses.length === 0 && <Empty text="Курсы появятся после публикации" />}
        {tab === "courses" && courses.map((item) => (
          <article
            className={styles.row}
            key={item.id}
            style={{ cursor: "pointer" }}
            onClick={() => {
              setSelectedCourseId(item.id);
              setTab(item.audience_code === "CANDIDATE" ? "candidates" : "main");
            }}
          >
            <AppIcon code="learning" />
            <div>
              <strong>{item.title}</strong>
              <span>{item.audience_code} · {item.description ?? "мини-курс"} · {items.filter((material) => material.course_id === item.id).length} материалов</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

/* ─────────── MemberModal ─────────── */
function MemberModal({ user, squads, onClose }: { user: UserRecord; squads: Squad[]; onClose: () => void }) {
  const squadName = squads.find((s) => s.id === user.squad_id)?.name ?? "Не назначено";
  const rows: Array<{ label: string; value: string; copyable?: boolean; link?: string }> = [
    { label: "ФИО", value: user.full_name },
    { label: "Роль", value: roleLabels[user.role_code as RoleCode] ?? user.role_code },
    { label: "Отделение", value: squadName },
    { label: "Телефон", value: formatPhoneDisplay(user.phone), copyable: true },
    { label: "Группа", value: user.education_place || "—" },
    { label: "Город", value: user.city || "—" },
    { label: "Дата рождения", value: user.birth_date ? formatDateFull(user.birth_date) : "—" },
    { label: "Telegram ID", value: String(user.telegram_id || "—"), copyable: true },
    ...(user.username ? [{ label: "Telegram", value: `@${user.username}`, link: `https://t.me/${user.username}` }] : []),
  ];
  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modalSheet} onClick={(e) => e.stopPropagation()}>
        <div className={styles.modalHeader}>
          <strong>{user.full_name}</strong>
          <button type="button" onClick={onClose} aria-label="Закрыть">
            <X aria-hidden="true" />
          </button>
        </div>
        <div className={styles.modalBody} style={{ padding: "0 16px 16px" }}>
          <dl style={{ margin: 0 }}>
            {rows.map(({ label, value, copyable, link }) => (
              <div
                key={label}
                className={styles.profileRow}
                style={copyable || link ? { cursor: "pointer" } : undefined}
                onClick={() => {
                  if (link) { window.open(link, "_blank"); return; }
                  if (copyable && value !== "—") {
                    navigator.clipboard.writeText(value).then(() => toast(`${label} скопирован`, "info")).catch(() => {});
                  }
                }}
              >
                <dt>{label}</dt>
                <dd style={link ? { color: "#1a2f5a", textDecoration: "underline" } : copyable && value !== "—" ? { textDecoration: "underline dotted" } : undefined}>
                  {value} {copyable && value !== "—" ? (
                    <svg style={{ display: "inline", verticalAlign: "middle", marginLeft: 3 }} width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                      <path d="M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z"/>
                    </svg>
                  ) : ""}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}

/* ─────────── PeopleView ─────────── */
const ROSTER_ROLE_CODES = new Set([
  "PARTICIPANT", "DEPUTY_SQUAD_COMMANDER", "SQUAD_COMMANDER",
  "DEPUTY_PLATOON_COMMANDER", "PLATOON_COMMANDER", "ADMIN", "SUPER_ADMIN",
]);

function PeopleView({
  level,
  profile,
  mySquad,
  allUsers,
  squads,
}: {
  level: number;
  profile: UserProfile;
  mySquad: Squad | null;
  allUsers: UserRecord[];
  squads: Squad[];
}) {
  type PeopleSegment = "roster" | "my_squad" | "candidates" | "archive";
  const [segment, setSegment] = useState<PeopleSegment>("roster");
  const [search, setSearch] = useState("");
  const [selectedUser, setSelectedUser] = useState<UserRecord | null>(null);

  const squadMap = new Map(squads.map((s) => [s.id, s]));

  // Основной состав: подтверждённые участники + непривязанные (USER_PENDING), исключаем PUBLIC_USER
  const rosterUsers = allUsers.filter(
    (u) => (ROSTER_ROLE_CODES.has(u.role_code) || u.role_code === "USER_PENDING") && u.status_code === "ACTIVE"
  );
  // Кандидаты: подали заявку
  const candidateUsers = allUsers.filter((u) => u.role_code === "CANDIDATE" && u.status_code === "ACTIVE");
  // Архив
  const archivedUsers = allUsers.filter((u) => u.status_code === "ARCHIVED");
  const mySquadUsers = rosterUsers.filter((u) => profile.squad_id !== null && u.squad_id === profile.squad_id);

  const sourceBySegment: Record<PeopleSegment, UserRecord[]> = {
    roster: rosterUsers,
    my_squad: mySquadUsers,
    candidates: candidateUsers,
    archive: archivedUsers,
  };
  const rawUsers = sourceBySegment[segment];

  const filteredUsers = search.trim()
    ? rawUsers.filter(
        (u) =>
          u.full_name.toLowerCase().includes(search.toLowerCase()) ||
          (u.username ?? "").toLowerCase().includes(search.toLowerCase())
      )
    : rawUsers;

  const segmentTabs: Array<[PeopleSegment, string]> = [
    ["roster", `Состав (${rosterUsers.length})`],
    ["my_squad", `Моё отделение (${mySquadUsers.length})`],
    ["candidates", `Заявки (${candidateUsers.length})`],
    ["archive", `Архив (${archivedUsers.length})`],
  ];

  return (
    <div className={styles.panel}>
      {selectedUser && <MemberModal user={selectedUser} squads={squads} onClose={() => setSelectedUser(null)} />}
      <div className={styles.panelHeader}>
        <h2>Состав</h2>
        <span>{filteredUsers.length} чел.</span>
      </div>

      <Tabs tabs={segmentTabs} active={segment} onChange={(v) => { setSegment(v as PeopleSegment); setSearch(""); }} />

      <div className={styles.searchBar}>
        <input
          placeholder="Поиск по имени или @username"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {(segment === "roster" || segment === "my_squad") && (
        <div>
          {segment === "my_squad" && mySquad && (
            <div className={styles.sectionHeader}>
              <strong>{mySquad.name}</strong>
              <span>{filteredUsers.length} чел.</span>
            </div>
          )}
          <RosterTable users={filteredUsers} squads={squads} emptyText={segment === "my_squad" ? "В вашем отделении пока никого нет" : "Участников нет"} onRowClick={setSelectedUser} />
        </div>
      )}

      {segment !== "roster" && segment !== "my_squad" && (
        <div className={styles.list}>
          {filteredUsers.length === 0 && <Empty text="Записей нет" />}
          {filteredUsers.map((user) => (
            <div
              className={styles.memberRow}
              key={user.id ?? user.telegram_id}
              style={{ cursor: "pointer" }}
              onClick={() => setSelectedUser(user)}
            >
              <div>
                <strong>{user.full_name}</strong>
                <span>
                  {(squadMap.get(user.squad_id ?? -1) as Squad | undefined)?.name ?? "без отделения"}
                  {user.username ? ` · @${user.username}` : ""}
                </span>
              </div>
              <span className={styles.roleBadge}>{roleLabels[user.role_code as RoleCode] ?? user.role_code}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RosterTable({
  users,
  squads,
  compact = false,
  emptyText = "Записей нет",
  onRowClick,
}: {
  users: UserRecord[];
  squads: Squad[];
  compact?: boolean;
  emptyText?: string;
  onRowClick?: (user: UserRecord) => void;
}) {
  const squadName = (id: number | null) => squads.find((s) => s.id === id)?.name ?? "—";
  const sorted = [...users].sort((a, b) => {
    const bySquad = squadName(a.squad_id).localeCompare(squadName(b.squad_id), "ru");
    return bySquad || a.full_name.localeCompare(b.full_name, "ru");
  });
  if (sorted.length === 0) return <Empty text={emptyText} />;
  return (
    <div className={styles.rosterTableWrap}>
      <table className={styles.rosterTable} data-compact={compact}>
        <thead>
          <tr>
            <th>ФИО</th>
            <th>Telegram</th>
            <th>Отделение</th>
            <th>Роль</th>
            {!compact && <th>Статус</th>}
            {!compact && <th>Телефон</th>}
            {!compact && <th>Дата рождения</th>}
          </tr>
        </thead>
        <tbody>
          {sorted.map((user) => (
            <tr
              key={user.id ?? user.telegram_id}
              style={onRowClick ? { cursor: "pointer" } : undefined}
              onClick={onRowClick ? () => onRowClick(user) : undefined}
            >
              <td>{user.full_name}</td>
              <td>
                {user.username ? (
                  <a
                    href={`https://t.me/${user.username}`}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "#1a2f5a", textDecoration: "underline" }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    @{user.username}
                  </a>
                ) : (
                  <span
                    className={styles.telegramFallback}
                    title={user.telegram_id ? "Username не указан. Нажмите, чтобы скопировать Telegram ID" : "Telegram не привязан"}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (user.telegram_id) {
                        navigator.clipboard.writeText(String(user.telegram_id)).then(() => toast("TG ID скопирован", "info")).catch(() => {});
                      }
                    }}
                  >
                    {user.telegram_id ? `ID ${user.telegram_id}` : "нет Telegram"}
                  </span>
                )}
              </td>
              <td>{squadName(user.squad_id)}</td>
              <td>{roleLabels[user.role_code as RoleCode] ?? user.role_code}</td>
              {!compact && <td>{user.status_code === "ACTIVE" ? "Активен" : user.status_code === "ARCHIVED" ? "Архив" : user.status_code}</td>}
              {!compact && <td>{formatPhoneDisplay(user.phone)}</td>}
              {!compact && <td>{user.birth_date ? formatDateFull(user.birth_date) : "—"}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProfileRosterTabs({
  profile,
  allUsers,
  squads,
}: {
  profile: UserProfile;
  allUsers: UserRecord[];
  squads: Squad[];
}) {
  const [tab, setTab] = useState<"roster" | "my_squad">("my_squad");
  const [selectedUser, setSelectedUser] = useState<UserRecord | null>(null);
  const rosterUsers = allUsers.filter(
    (u) => ROSTER_ROLE_CODES.has(u.role_code) && u.status_code === "ACTIVE"
  );
  const visible = tab === "my_squad"
    ? rosterUsers.filter((u) => profile.squad_id !== null && u.squad_id === profile.squad_id)
    : rosterUsers;
  return (
    <div className={styles.profileRoster}>
      <Tabs
        tabs={[["my_squad", "Моё отделение"], ["roster", "Состав"]]}
        active={tab}
        onChange={(value) => setTab(value as typeof tab)}
      />
      <RosterTable users={visible} squads={squads} compact emptyText={tab === "my_squad" ? "Отделение не назначено" : "Состав пока пуст"} onRowClick={setSelectedUser} />
      {selectedUser && <MemberModal user={selectedUser} squads={squads} onClose={() => setSelectedUser(null)} />}
    </div>
  );
}

/* ─────────── ProfileView ─────────── */
function ProfileView({
  profile,
  attendanceStats,
  submissions,
  streak,
  allUsers,
  squads,
  onAvatarUpload,
  isAvatarUploading,
  onProfileUpdate,
}: {
  profile: UserProfile;
  attendanceStats?: ReportSummary;
  submissions: NormativeSubmission[];
  streak: StreakData;
  allUsers: UserRecord[];
  squads: Squad[];
  onAvatarUpload: (file: File) => Promise<UserProfile>;
  isAvatarUploading: boolean;
  onProfileUpdate: (p: UserProfile) => void;
}) {
  const avatarInputRef = useRef<HTMLInputElement>(null);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ full_name: "", phone: "", city: "", education_place: "", birth_date: "" });
  const [editPhone, setEditPhone] = useState("+7");
  const [localAvatarPreview, setLocalAvatarPreview] = useState<string | null>(null);
  const [avatarFailed, setAvatarFailed] = useState(false);
  const updateMe = useUpdateMe();

  const startEdit = () => {
    setEditForm({
      full_name: profile.full_name ?? "",
      phone: profile.phone ?? "",
      city: profile.city ?? "",
      education_place: profile.education_place ?? "",
      birth_date: profile.birth_date ?? "",
    });
    setEditPhone(profile.phone ? formatPhoneDisplay(profile.phone) : "+7");
    setEditing(true);
  };

  const saveEdit = () => {
    updateMe.mutate(
      { ...editForm, phone: editForm.phone || undefined },
      {
        onSuccess: (updated) => {
          setEditing(false);
          onProfileUpdate(updated);
          toast("Профиль сохранён", "success");
        },
        onError: () => toast("Не удалось сохранить", "error"),
      },
    );
  };

  const items = attendanceStats?.items ?? [];
  const presentItem = items.find((i) => (i as Record<string, unknown>).status_code === "PRESENT");
  const absentItem = items.find((i) => (i as Record<string, unknown>).status_code === "ABSENT");
  const presentCount = extractCount(presentItem ?? 0);
  const absentCount = extractCount(absentItem ?? 0);
  const total = items.reduce((acc, i) => acc + extractCount(i), 0);
  const percent = total ? Math.round((presentCount / total) * 100) : 0;
  const accepted = submissions.filter((s) => s.status_code === "ACCEPTED").length;
  const avatar = localAvatarPreview || (!avatarFailed ? avatarPath(profile.avatar_file_id) : null);

  useEffect(() => {
    setAvatarFailed(false);
  }, [profile.avatar_file_id]);

  useEffect(() => () => {
    if (localAvatarPreview) URL.revokeObjectURL(localAvatarPreview);
  }, [localAvatarPreview]);

  const handleAvatarFile = async (file: File) => {
    const previewUrl = URL.createObjectURL(file);
    setLocalAvatarPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return previewUrl;
    });
    setAvatarFailed(false);
    try {
      const updated = await onAvatarUpload(file);
      onProfileUpdate(updated);
      toast("Аватар обновлён", "success");
    } catch {
      setLocalAvatarPreview(null);
      setAvatarFailed(true);
      toast("Не удалось загрузить аватар", "error");
    }
  };

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Профиль</h2>
        <button type="button" className={styles.editProfileBtn} onClick={editing ? () => setEditing(false) : startEdit}>
          {editing ? "Отмена" : "Редактировать"}
        </button>
      </div>
      <div className={styles.profileCard}>
        <div className={styles.profileAvatarUpload} onClick={() => !isAvatarUploading && avatarInputRef.current?.click()}>
          <span className={styles.profileAvatar}>
            {avatar ? <img src={avatar} alt="" onError={() => { setAvatarFailed(true); setLocalAvatarPreview(null); }} /> : profile.full_name.charAt(0).toUpperCase()}
          </span>
          <span className={styles.avatarUploadButton}>
            {isAvatarUploading ? "Загрузка..." : avatar ? "Сменить фото" : "Загрузить фото"}
          </span>
          <input
            ref={avatarInputRef}
            type="file"
            accept="image/*"
            style={{ position: "absolute", width: 1, height: 1, opacity: 0 }}
            disabled={isAvatarUploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleAvatarFile(file);
              e.target.value = "";
            }}
          />
        </div>

        {editing ? (
          <div className={styles.formBlock}>
            <label className={styles.fieldLabel}>
              <span>ФИО</span>
              <input
                placeholder="Иванов Иван Иванович"
                value={editForm.full_name}
                onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
              />
            </label>
            <label className={styles.fieldLabel}>
              <span>Телефон</span>
              <input
                type="tel"
                inputMode="numeric"
                placeholder="+7 999 000 11 22"
                value={editPhone}
                onChange={(e) => {
                  const masked = applyPhoneMask(e.target.value);
                  setEditPhone(masked);
                  setEditForm({ ...editForm, phone: phoneInputToRaw(masked) });
                }}
              />
            </label>
            <label className={styles.fieldLabel}>
              <span>Город или район</span>
              <input
                placeholder="Новосибирск"
                value={editForm.city}
                onChange={(e) => setEditForm({ ...editForm, city: e.target.value })}
              />
            </label>
            <label className={styles.fieldLabel}>
              <span>Группа</span>
              <input
                placeholder="Например, 1ИСП-21"
                value={editForm.education_place}
                onChange={(e) => setEditForm({ ...editForm, education_place: e.target.value })}
              />
            </label>
            <label className={styles.fieldLabel}>
              <span>Дата рождения</span>
              <input
                type="date"
                value={editForm.birth_date}
                onChange={(e) => setEditForm({ ...editForm, birth_date: e.target.value })}
              />
            </label>
            <button type="button" disabled={!editForm.full_name.trim() || updateMe.isPending} onClick={saveEdit}>
              {updateMe.isPending ? "Сохранение..." : "Сохранить"}
            </button>
          </div>
        ) : (
          <dl>
            <div className={styles.profileRow}>
              <dt>ФИО</dt>
              <dd>{profile.full_name}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Должность</dt>
              <dd>{roleLabels[profile.role_code]}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Отделение</dt>
              <dd>{squads.find((s) => s.id === profile.squad_id)?.name ?? (profile.squad_id ? `#${profile.squad_id}` : "не назначено")}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Телефон</dt>
              <dd>{profile.phone ? formatPhoneDisplay(profile.phone) : "—"}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Группа</dt>
              <dd>{profile.education_place || "—"}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Город</dt>
              <dd>{profile.city || "—"}</dd>
            </div>
            <div className={styles.profileRow}>
              <dt>Дата рождения</dt>
              <dd>{profile.birth_date ? formatDateFull(profile.birth_date) : "—"}</dd>
            </div>
            <div
              className={styles.profileRow}
              style={{ cursor: "pointer" }}
              onClick={() => {
                navigator.clipboard.writeText(String(profile.telegram_id)).then(() => toast("Telegram ID скопирован", "info")).catch(() => {});
              }}
            >
              <dt>Telegram ID</dt>
              <dd style={{ color: "#1a2f5a", textDecoration: "underline dotted" }}>
                {profile.telegram_id}
                <svg style={{ display: "inline", verticalAlign: "middle", marginLeft: 4 }} width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z"/>
                </svg>
              </dd>
            </div>
            {profile.username && (
              <div className={styles.profileRow}>
                <dt>Telegram</dt>
                <dd>@{profile.username}</dd>
              </div>
            )}
          </dl>
        )}
      </div>
      {total > 0 && (
        <>
          <div className={styles.statsGrid4} style={{ marginTop: 12 }}>
            <StatNumber value={streak?.present_count ?? presentCount} label="Посещено" color="#27ae60" />
            <StatNumber value={streak?.percent ?? percent} label="Явка" color="#27ae60" suffix="%" />
            <StatNumber value={streak?.total_events ?? total} label="Занятий" color="#1a2f5a" />
            <StatNumber value={accepted} label="Сдано" color="#3498db" />
          </div>
          {total >= 3 && (
            <div className={styles.chartsSection} style={{ marginTop: 12 }}>
              <div className={styles.chartSectionTitle}>Распределение явки</div>
              <AttendanceDonut present={presentCount} absent={absentCount} late={0} total={total} />
            </div>
          )}
        </>
      )}
      {streak && (streak.current_streak > 0 || streak.best_streak > 0) && (
        <div style={{ marginTop: 12 }}>
          <StreakBadge current={streak.current_streak} best={streak.best_streak} />
        </div>
      )}
      {allUsers.length > 0 && (
        <ProfileRosterTabs profile={profile} allUsers={allUsers} squads={squads} />
      )}
    </div>
  );
}

/* ─────────── AdminView ─────────── */
function AdminView({
  level,
  currentUserId,
  users,
  applications,
  promo,
  menu,
  squads,
  audit,
  onAccept,
  onReject,
  isBusy,
}: {
  level: number;
  currentUserId: number | null;
  users: UserRecord[];
  applications: JoinApplication[];
  promo: PromoBlock[];
  menu: MenuCard[];
  squads: Squad[];
  audit: AuditLog[];
  onAccept: (id: number, squadId?: number | null) => void;
  onReject: (id: number, reason?: string) => void;
  isBusy: boolean;
}) {
  type AdminTab = "users" | "applications" | "appeals" | "squads" | "schedule" | "events" | "normatives" | "learning" | "promo" | "menu" | "logs" | "settings";
  const [tab, setTab] = useState<AdminTab>("users");
  const [scheduleAdminTab, setScheduleAdminTab] = useState<"active" | "closed">("active");
  const [editingPromo, setEditingPromo] = useState<PromoBlock | null | "new">(null);
  const [applicationSquads, setApplicationSquads] = useState<Record<number, string>>({});
  const [rejectReasons, setRejectReasons] = useState<Record<number, string>>({});
  const [newSquadName, setNewSquadName] = useState("");
  const [squadNames, setSquadNames] = useState<Record<number, string>>({});
  const [userSearch, setUserSearch] = useState("");
  const [appStatusFilter, setAppStatusFilter] = useState("");
  const [logFilter, setLogFilter] = useState({ action_code: "", entity_name: "" });
  const [pipelineStage, setPipelineStage] = useState<"start" | "applied" | "invited" | "roster">("applied");
  const [drawerApp, setDrawerApp] = useState<JoinApplication | null>(null);
  const [drawerPublicUser, setDrawerPublicUser] = useState<UserRecord | null>(null);
  const [drawerRosterUser, setDrawerRosterUser] = useState<UserRecord | null>(null);
  const publicUsers = usePublicUsers(tab === "applications");
  const [newNorm, setNewNorm] = useState({
    title: "",
    description: "",
    target_audience: "PARTICIPANTS",
    squad_id: "",
    instruction_video_url: "",
    instruction_video_file_id: null as number | null,
    instruction_video_file_name: "",
  });
  const [normVideoDrafts, setNormVideoDrafts] = useState<Record<number, string>>({});
  const [newMaterial, setNewMaterial] = useState({
    title: "",
    type_code: "TEXT",
    external_url: "",
    audience_code: "PARTICIPANTS",
    is_active: true,
    file_id: null as number | null,
    file_name: "",
  });
  const [newCourse, setNewCourse] = useState({ title: "", description: "", audience_code: "PARTICIPANTS" });
  const [learningScope, setLearningScope] = useState<"main" | "candidates">("main");
  const [newCandEvent, setNewCandEvent] = useState({ title: "", start_datetime: "", place: "", description: "" });
  const birthdayTemplateRef = useRef<HTMLTextAreaElement>(null);
  const [newTemplate, setNewTemplate] = useState({
    title: "",
    description: "",
    week_days: "1",
    week_parity: "",
    start_time: "16:00",
    end_time: "",
    place: "",
    squad_id: "",
    valid_from: "",
    valid_to: "",
    requires_response: true,
  });
  const [editingEventId, setEditingEventId] = useState<number | null>(null);
  const [eventEdits, setEventEdits] = useState<Record<number, {
    title: string;
    description: string;
    start_datetime: string;
    end_datetime: string;
    place: string;
  }>>({});

  const createPromo = useCreatePromoBlock();
  const updatePromo = useUpdatePromoBlock();
  const deletePromo = useDeletePromoBlock();
  const updateUser = useAdminUpdateUser();
  const deactivateUser = useDeactivateUser();
  const createSquad = useCreateSquad();
  const updateSquad = useUpdateSquad();
  const updateMenu = useUpdateMenuCard();
  const adminSchedule = useAdminSchedule(tab === "schedule");
  const scheduleTemplates = useScheduleTemplates(tab === "schedule");
  const createEvent = useCreateScheduleEvent();
  const updateEvent = useUpdateScheduleEvent();
  const deleteEvent = useDeleteScheduleEvent();
  const createTemplate = useCreateScheduleTemplate();
  const deleteTemplate = useDeleteScheduleTemplate();
  const generateTemplate = useGenerateScheduleTemplate();
  const adminAppeals = useAdminAppeals(tab === "appeals");
  const updateAppeal = useUpdateAppeal();
  const adminJoinEvents = useAdminJoinEvents(tab === "events");
  const createCandEvent = useCreateCandidateEvent();
  const updateCandEvent = useUpdateCandidateEvent();
  const updateApplication = useAdminUpdateApplication();
  const adminNorms = useNormativesAdmin(tab === "normatives");
  const createNorm = useCreateNormative();
  const updateNorm = useUpdateNormative();
  const deleteNorm = useDeleteNormative();
  const uploadNormVideo = useUploadFile();
  const adminMaterials = useAdminLearningMaterials(tab === "learning");
  const adminCourses = useAdminLearningCourses(tab === "learning");
  const createMaterial = useCreateLearningMaterial();
  const updateMaterial = useUpdateLearningMaterial();
  const uploadLearningFile = useUploadFile();
  const openFile = useOpenFile();
  const getFileBlob = useGetFileBlob();
  const [videoModal, setVideoModal] = useState<{ src?: string; embedSrc?: string } | null>(null);
  const openVideoModal = async (url?: string | null, fileId?: number | null) => {
    if (url) {
      const embed = toYouTubeEmbedUrl(url);
      setVideoModal(embed ? { embedSrc: embed } : { src: url });
    } else if (fileId) {
      try {
        const blobUrl = await getFileBlob.mutateAsync(fileId);
        setVideoModal({ src: blobUrl });
      } catch {
        toast("Не удалось загрузить видео", "error");
      }
    }
  };
  const createCourse = useCreateLearningCourse();
  const updateCourse = useUpdateLearningCourse();
  const auditFiltered = useAdminAuditFiltered(
    { action_code: logFilter.action_code || undefined, entity_name: logFilter.entity_name || undefined },
    tab === "logs",
  );
  const adminSettings = useAdminSettings(tab === "settings" && level >= 9);
  const updateSettings = useUpdateSettings();
  const exportCSV = useExportCSVviaBot();
  const exportXLSX = useExportXLSXviaBot();
  const [settingsDraft, setSettingsDraft] = useState<Record<string, string>>({});

  const squadMap = new Map(squads.map((s) => [s.id, s.name]));
  const roleOptions = Object.keys(roleLabels) as RoleCode[];
  const statusOptions = ["ACTIVE", "INACTIVE", "ARCHIVED", "BLOCKED"];
  const [newEvent, setNewEvent] = useState({ title: "", start_datetime: "", end_datetime: "", place: "", squad_id: "", requires_response: true });
  const scheduleEvents = adminSchedule.data ?? [];
  const isClosedAdminScheduleEvent = (event: ScheduleEvent) => {
    if (event.status_code === "CANCELLED") return true;
    if (!event.requires_response || !event.response_deadline_at) return false;
    const deadlineTime = new Date(event.response_deadline_at).getTime();
    return Number.isFinite(deadlineTime) && deadlineTime < Date.now();
  };
  const activeScheduleEvents = scheduleEvents.filter((event) => !isClosedAdminScheduleEvent(event));
  const closedScheduleEvents = scheduleEvents.filter(isClosedAdminScheduleEvent);
  const visibleScheduleEvents = scheduleAdminTab === "active" ? activeScheduleEvents : closedScheduleEvents;

  const filteredUsers = userSearch.trim()
    ? users.filter((u) => u.full_name.toLowerCase().includes(userSearch.toLowerCase()) || (u.username ?? "").toLowerCase().includes(userSearch.toLowerCase()))
    : users;
  void appStatusFilter; // kept for potential future use

  const contentAdminGroups: Array<{ title: string; tabs: Array<[AdminTab, string, number]> }> = [
    { title: "Состав", tabs: [["users", "Люди", 4], ["applications", "Заявки", 6], ["squads", "Отделения", 6]] },
    { title: "Занятия", tabs: [["schedule", "Расписание", 6], ["events", "События канд.", 6]] },
    { title: "Подготовка", tabs: [["normatives", "Нормативы", 6], ["learning", "Материалы", 6], ["appeals", "Связь", 6]] },
    { title: "Интерфейс", tabs: [["promo", "Промо", 6], ["menu", "Меню", 6]] },
  ];
  const systemAdminGroup = { title: "Система", tabs: [["logs", "Логи", 8], ["settings", "Настройки", 9]] as Array<[AdminTab, string, number]> };
  const adminGroups = level >= 8 ? [systemAdminGroup, ...contentAdminGroups] : contentAdminGroups;
  const adminTabs = adminGroups.flatMap((group) => group.tabs);
  const visibleTabs = adminTabs.filter(([, , minLevel]) => level >= minLevel);
  const visibleAdminGroups = adminGroups
    .map((group) => ({ ...group, tabs: group.tabs.filter(([, , minLevel]) => level >= minLevel) }))
    .filter((group) => group.tabs.length > 0);
  const currentLearningAudience = learningScope === "candidates" ? "CANDIDATE" : "PARTICIPANTS";
  const resetNewNorm = () => setNewNorm({
    title: "",
    description: "",
    target_audience: "PARTICIPANTS",
    squad_id: "",
    instruction_video_url: "",
    instruction_video_file_id: null,
    instruction_video_file_name: "",
  });
  const resetNewMaterial = () => setNewMaterial({
    title: "",
    type_code: "TEXT",
    external_url: "",
    audience_code: currentLearningAudience,
    is_active: true,
    file_id: null,
    file_name: "",
  });
  const handleNewNormVideoUpload = async (file: File) => {
    try {
      const result = await uploadNormVideo.mutateAsync(file);
      setNewNorm((prev) => ({
        ...prev,
        instruction_video_file_id: result.id,
        instruction_video_file_name: result.original_name || file.name,
        instruction_video_url: "",
      }));
    } catch {
      toast("Не удалось загрузить видео", "error");
    }
  };
  const handleNormVideoUpload = async (normId: number, file: File) => {
    try {
      const result = await uploadNormVideo.mutateAsync(file);
      updateNorm.mutate(
        { id: normId, instruction_video_file_id: result.id, instruction_video_url: null },
        { onSuccess: () => toast("Видеофайл норматива сохранён", "success") },
      );
    } catch {
      toast("Не удалось загрузить видео", "error");
    }
  };
  const handleNewMaterialFileUpload = async (file: File) => {
    try {
      const result = await uploadLearningFile.mutateAsync(file);
      setNewMaterial((prev) => ({
        ...prev,
        file_id: result.id,
        file_name: result.original_name || file.name,
        type_code: materialTypeFromMime(result.mime_type),
      }));
    } catch {
      toast("Не удалось загрузить файл", "error");
    }
  };
  const handleMaterialFileUpload = async (materialId: number, file: File) => {
    try {
      const result = await uploadLearningFile.mutateAsync(file);
      updateMaterial.mutate(
        { id: materialId, file_id: result.id, type_code: materialTypeFromMime(result.mime_type) },
        { onSuccess: () => toast("Файл материала сохранён", "success") },
      );
    } catch {
      toast("Не удалось загрузить файл", "error");
    }
  };

  useEffect(() => {
    if (!visibleTabs.some(([value]) => value === tab)) {
      setTab(visibleTabs[0]?.[0] ?? "users");
      setEditingPromo(null);
    }
  }, [level, tab, visibleTabs.length]);

  return (
    <div className={styles.panel}>
      {videoModal && (
        <VideoPlayerModal
          src={videoModal.src}
          embedSrc={videoModal.embedSrc}
          onClose={() => {
            if (videoModal.src?.startsWith("blob:")) URL.revokeObjectURL(videoModal.src);
            setVideoModal(null);
          }}
        />
      )}
      <div className={styles.panelHeader}>
        <h2>Админка</h2>
        <span className={styles.adminAccessPill} data-tone={level >= 8 ? "admin" : level >= 6 ? "commander" : "squad"}>
          {level >= 8 ? "ADMIN · системные разделы" : level >= 6 ? "командирский доступ" : "доступ отделения"}
        </span>
      </div>
      <div className={styles.adminTabGroups}>
        {visibleAdminGroups.map((group) => (
          <section key={group.title} data-system={group.title === "Система" ? "true" : "false"}>
            <strong>{group.title}</strong>
            <div>
              {group.tabs.map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  data-active={tab === value}
                  data-privileged={value === "logs" || value === "settings" ? "true" : "false"}
                  onClick={() => { setTab(value); setEditingPromo(null); }}
                >
                  {label}
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>

      {/* ── Promo tab ── */}
      {tab === "promo" && (
        <div>
          {editingPromo !== null ? (
            <PromoEditForm
              initial={editingPromo === "new" ? null : editingPromo}
              isSaving={createPromo.isPending || updatePromo.isPending}
              onCancel={() => setEditingPromo(null)}
              onSave={(data) => {
                const payload = {
                  title: data.title,
                  body: data.body || null,
                  button_text: data.button_text || null,
                  button_url: data.button_url || null,
                  action_type_code: data.action_type_code || null,
                  audience_code: data.audience_code,
                  style_code: data.style_code,
                  sort_order: data.sort_order,
                  is_active: data.is_active,
                  active_from: data.active_from || null,
                  active_to: data.active_to || null,
                };
                if (editingPromo === "new") {
                  createPromo.mutate(payload, {
                    onSuccess: () => { toast("Промо-блок создан", "success"); setEditingPromo(null); },
                    onError: () => toast("Ошибка создания", "error"),
                  });
                } else {
                  updatePromo.mutate({ id: editingPromo!.id, ...payload }, {
                    onSuccess: () => { toast("Промо-блок сохранён", "success"); setEditingPromo(null); },
                    onError: () => toast("Ошибка сохранения", "error"),
                  });
                }
              }}
            />
          ) : (
            <div className={styles.list}>
              <button
                type="button"
                className={styles.iconAction}
                style={{ gridColumn: "unset", marginBottom: 8 }}
                onClick={() => setEditingPromo("new")}
              >
                + Создать промо-блок
              </button>
              {promo.length === 0 && <Empty text="Промо-блоков пока нет. Создайте первый!" />}
              {promo.map((item) => (
                <AdminPromoCard
                  key={item.id}
                  block={item}
                  onToggle={(id, active) => updatePromo.mutate({ id, is_active: active }, {
                    onSuccess: () => toast(active ? "Блок показан" : "Блок скрыт", "info"),
                  })}
                  onEdit={(block) => setEditingPromo(block)}
                  onDelete={(id) => {
                    if (!window.confirm("Удалить промо-блок?")) return;
                    deletePromo.mutate(id, { onSuccess: () => toast("Блок удалён", "warning") });
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Other tabs ── */}
      {tab !== "promo" && (
        <div className={styles.list}>

          {/* ── Users ── */}
          {tab === "users" && (
            <>
              <div className={styles.adminToolbar}>
                <input
                  placeholder="Имя или @username"
                  value={userSearch}
                  onChange={(e) => setUserSearch(e.target.value)}
                />
                <details className={styles.exportDropdown}>
                  <summary title="Скачать список">
                    <AppIcon code="download" />
                    <span>Скачать</span>
                  </summary>
                  <div>
                    <button
                      type="button"
                      disabled={exportCSV.isPending}
                      onClick={() => exportCSV.mutate(
                        { search: userSearch || undefined },
                        { onSuccess: () => toast("CSV отправлен в личные сообщения", "success"), onError: () => toast("Не удалось отправить CSV", "error") },
                      )}
                    >
                      {exportCSV.isPending ? "Отправляем..." : "CSV в бот"}
                    </button>
                    <button
                      type="button"
                      disabled={exportXLSX.isPending}
                      onClick={() => exportXLSX.mutate(
                        { search: userSearch || undefined },
                        { onSuccess: () => toast("Excel отправлен в личные сообщения", "success"), onError: () => toast("Не удалось отправить Excel", "error") },
                      )}
                    >
                      {exportXLSX.isPending ? "Отправляем..." : "Excel в бот"}
                    </button>
                  </div>
                </details>
              </div>
              {filteredUsers.length === 0 ? <Empty text="Пользователей нет" /> : filteredUsers.map((user) => {
                const userLevel = roleLevels[user.role_code as RoleCode] ?? 0;
                const canDeactivate =
                  level >= roleLevels.ADMIN &&
                  user.id !== null &&
                  user.id !== currentUserId &&
                  user.status_code !== "ARCHIVED" &&
                  (level >= roleLevels.SUPER_ADMIN || userLevel < level);
                return (
                <div className={`${styles.memberRow} ${styles.adminUserRow}`} key={user.id ?? user.telegram_id}>
                  <div>
                    <strong>{user.full_name}</strong>
                    <span>{squadMap.get(user.squad_id ?? -1) ?? "без отделения"}{user.username ? ` · @${user.username}` : ""} · {user.status_code}</span>
                  </div>
                  <div className={styles.adminControls}>
                    <label className={styles.adminControlRow}>
                      <span>Роль</span>
                      <select
                        value={user.role_code}
                        disabled={user.id === null || updateUser.isPending}
                        onChange={(event) => {
                          if (user.id === null) return;
                          const nextRole = event.target.value;
                          if (["SQUAD_COMMANDER", "DEPUTY_SQUAD_COMMANDER"].includes(nextRole)) {
                            if (!user.squad_id) {
                              toast("Сначала выберите отделение", "warning");
                              event.target.value = user.role_code;
                              return;
                            }
                            const squad = squads.find((s) => s.id === user.squad_id);
                            const existingId = nextRole === "SQUAD_COMMANDER" ? squad?.commander_user_id : squad?.deputy_user_id;
                            if (existingId && existingId !== user.id) {
                              const label = nextRole === "SQUAD_COMMANDER" ? "командира" : "заместителя";
                              if (!window.confirm(`В отделении уже есть ${label}. Заменить назначение?`)) {
                                event.target.value = user.role_code;
                                return;
                              }
                            }
                          }
                          updateUser.mutate({ userId: user.id, role_code: nextRole });
                        }}
                      >
                        {roleOptions.map((role) => (
                          <option key={role} value={role}>{roleLabels[role]}</option>
                        ))}
                      </select>
                    </label>
                    <label className={styles.adminControlRow}>
                      <span>Отделение</span>
                      <select
                        value={user.squad_id ?? ""}
                        disabled={user.id === null || updateUser.isPending}
                        onChange={(event) => user.id !== null && updateUser.mutate({ userId: user.id, squad_id: event.target.value ? Number(event.target.value) : null })}
                      >
                        <option value="">Без отделения</option>
                        {squads.map((squad) => (
                          <option key={squad.id} value={squad.id}>{squad.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className={styles.adminControlRow}>
                      <span>Статус</span>
                      <select
                        value={user.status_code}
                        disabled={user.id === null || updateUser.isPending}
                        onChange={(event) => user.id !== null && updateUser.mutate({ userId: user.id, status_code: event.target.value })}
                      >
                        {statusOptions.map((s) => (
                          <option key={s} value={s}>{s}</option>
                        ))}
                      </select>
                    </label>
                    {canDeactivate && (
                      <button
                        type="button"
                        className={styles.adminDangerButton}
                        disabled={deactivateUser.isPending}
                        onClick={() => {
                          if (!window.confirm(`Деактивировать ${user.full_name}?`)) return;
                          deactivateUser.mutate(user.id as number, {
                            onSuccess: () => toast("Пользователь деактивирован", "warning"),
                            onError: () => toast("Не удалось деактивировать пользователя", "error"),
                          });
                        }}
                      >
                        Деактивировать
                      </button>
                    )}
                  </div>
                </div>
              );})}
            </>
          )}

          {/* ── Schedule ── */}
          {tab === "schedule" && (
            <>
              <div className={styles.formBlock}>
                <strong className={styles.formTitle}>Шаблон занятий</strong>
                <input placeholder="Название шаблона *" value={newTemplate.title} onChange={(e) => setNewTemplate({ ...newTemplate, title: e.target.value })} />
                <textarea placeholder="Описание" rows={2} value={newTemplate.description} onChange={(e) => setNewTemplate({ ...newTemplate, description: e.target.value })} />
                <label className={styles.fieldLabel}>
                  <span>Дни недели ISO (1=пн, 3=ср)</span>
                  <input value={newTemplate.week_days} onChange={(e) => setNewTemplate({ ...newTemplate, week_days: e.target.value })} />
                </label>
                <label className={styles.fieldLabel}>
                  <span>Чередование</span>
                  <select value={newTemplate.week_parity} onChange={(e) => setNewTemplate({ ...newTemplate, week_parity: e.target.value })}>
                    <option value="">Каждую неделю</option>
                    <option value="A">Неделя 1</option>
                    <option value="B">Неделя 2</option>
                  </select>
                </label>
                <div className={styles.twoCol}>
                  <label className={styles.fieldLabel}>
                    <span>Начало</span>
                    <input type="time" value={newTemplate.start_time} onChange={(e) => setNewTemplate({ ...newTemplate, start_time: e.target.value })} />
                  </label>
                  <label className={styles.fieldLabel}>
                    <span>Конец</span>
                    <input type="time" value={newTemplate.end_time} onChange={(e) => setNewTemplate({ ...newTemplate, end_time: e.target.value })} />
                  </label>
                </div>
                <input placeholder="Место" value={newTemplate.place} onChange={(e) => setNewTemplate({ ...newTemplate, place: e.target.value })} />
                <select value={newTemplate.squad_id} onChange={(e) => setNewTemplate({ ...newTemplate, squad_id: e.target.value })}>
                  <option value="">Для всех отделений</option>
                  {squads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <div className={styles.twoCol}>
                  <label className={styles.fieldLabel}>
                    <span>Действует с</span>
                    <input type="date" value={newTemplate.valid_from} onChange={(e) => setNewTemplate({ ...newTemplate, valid_from: e.target.value })} />
                  </label>
                  <label className={styles.fieldLabel}>
                    <span>Действует до</span>
                    <input type="date" value={newTemplate.valid_to} onChange={(e) => setNewTemplate({ ...newTemplate, valid_to: e.target.value })} />
                  </label>
                </div>
                <label className={styles.checkboxLine}>
                  <input type="checkbox" checked={newTemplate.requires_response} onChange={(e) => setNewTemplate({ ...newTemplate, requires_response: e.target.checked })} />
                  <span>Требуется ответ участников</span>
                </label>
                <button
                  type="button"
                  disabled={!newTemplate.title.trim() || !newTemplate.week_days.trim() || !newTemplate.start_time || createTemplate.isPending}
                  onClick={() => createTemplate.mutate(
                    {
                      title: newTemplate.title.trim(),
                      description: newTemplate.description || undefined,
                      week_days: newTemplate.week_days,
                      week_parity: newTemplate.week_parity ? (newTemplate.week_parity as "A" | "B") : null,
                      start_time: newTemplate.start_time,
                      end_time: newTemplate.end_time || null,
                      place: newTemplate.place || null,
                      squad_id: newTemplate.squad_id ? Number(newTemplate.squad_id) : null,
                      valid_from: newTemplate.valid_from || null,
                      valid_to: newTemplate.valid_to || null,
                      requires_response: newTemplate.requires_response,
                    },
                    { onSuccess: () => { setNewTemplate({ title: "", description: "", week_days: "1", week_parity: "", start_time: "16:00", end_time: "", place: "", squad_id: "", valid_from: "", valid_to: "", requires_response: true }); toast("Шаблон создан", "success"); } },
                  )}
                >
                  {createTemplate.isPending ? "Создаём..." : "Создать шаблон"}
                </button>
              </div>
              <div className={styles.list}>
                {scheduleTemplates.data?.length === 0 && <Empty text="Шаблонов пока нет" />}
                {scheduleTemplates.data?.map((template: ScheduleTemplate) => (
                  <div className={styles.row} key={template.id}>
                    <AppIcon code="schedule" />
                    <div>
                      <strong>
                        {template.title}
                        <span className={styles.inlineBadge}>
                          {template.week_parity === "A" ? "1" : template.week_parity === "B" ? "2" : "каждую"}
                        </span>
                      </strong>
                      <span>{template.week_days} · {template.start_time.slice(0, 5)}{template.place ? ` · ${template.place}` : ""}</span>
                    </div>
                    <div className={styles.commandStrip} style={{ gridColumn: "1/-1" }}>
                      <button
                        type="button"
                        disabled={generateTemplate.isPending}
                        onClick={() => generateTemplate.mutate(
                          { id: template.id, days: 60 },
                          {
                            onSuccess: (created) => toast(
                              created.length ? `Сгенерировано: ${created.length}` : "Новых событий нет: даты уже заняты или не подходят",
                              created.length ? "success" : "info",
                            ),
                            onError: (error) => toast(scheduleTemplateErrorMessage(error), "error"),
                          },
                        )}
                      >
                        Сгенерировать на 60 дней
                      </button>
                      <button
                        type="button"
                        className={styles.btnNotComing}
                        disabled={deleteTemplate.isPending}
                        onClick={() => {
                          if (!window.confirm(`Удалить шаблон «${template.title}» и закрыть будущие занятия по нему?`)) return;
                          deleteTemplate.mutate(template.id, {
                            onSuccess: () => toast("Шаблон удалён, будущие занятия закрыты", "warning"),
                            onError: (error) => toast(apiErrorDetail(error) ?? "Не удалось удалить шаблон", "error"),
                          });
                        }}
                      >
                        Удалить шаблон
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <div className={styles.formBlock}>
                <strong className={styles.formTitle}>Разовое событие</strong>
                <input placeholder="Название события *" value={newEvent.title} onChange={(e) => setNewEvent({ ...newEvent, title: e.target.value })} />
                <div className={styles.twoCol}>
                  <label className={styles.fieldLabel}>
                    <span>Начало *</span>
                    <input type="datetime-local" value={newEvent.start_datetime} onChange={(e) => setNewEvent({ ...newEvent, start_datetime: e.target.value })} />
                  </label>
                  <label className={styles.fieldLabel}>
                    <span>Конец</span>
                    <input type="datetime-local" value={newEvent.end_datetime} onChange={(e) => setNewEvent({ ...newEvent, end_datetime: e.target.value })} />
                  </label>
                </div>
                <input placeholder="Место проведения" value={newEvent.place} onChange={(e) => setNewEvent({ ...newEvent, place: e.target.value })} />
                <select value={newEvent.squad_id} onChange={(e) => setNewEvent({ ...newEvent, squad_id: e.target.value })}>
                  <option value="">Для всех отделений</option>
                  {squads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <label className={styles.checkboxLine}>
                  <input type="checkbox" checked={newEvent.requires_response} onChange={(e) => setNewEvent({ ...newEvent, requires_response: e.target.checked })} />
                  <span>Требуется ответ (приду / не приду)</span>
                </label>
                <button
                  type="button"
                  disabled={!newEvent.title.trim() || !newEvent.start_datetime || createEvent.isPending}
                  onClick={() => createEvent.mutate(
                    {
                      title: newEvent.title.trim(),
                      start_datetime: new Date(newEvent.start_datetime).toISOString(),
                      end_datetime: newEvent.end_datetime ? new Date(newEvent.end_datetime).toISOString() : undefined,
                      place: newEvent.place || undefined,
                      squad_id: newEvent.squad_id ? Number(newEvent.squad_id) : null,
                      requires_response: newEvent.requires_response,
                    },
                    { onSuccess: () => { setNewEvent({ title: "", start_datetime: "", end_datetime: "", place: "", squad_id: "", requires_response: true }); toast("Событие создано", "success"); } },
                  )}
                >
                  {createEvent.isPending ? "Создаём..." : "Создать событие"}
                </button>
              </div>
              <Tabs
                tabs={[
                  ["active", `Активные (${activeScheduleEvents.length})`],
                  ["closed", `Закрытые (${closedScheduleEvents.length})`],
                ]}
                active={scheduleAdminTab}
                onChange={(value) => setScheduleAdminTab(value as typeof scheduleAdminTab)}
              />
              {scheduleEvents.length === 0 && <Empty text="Событий нет" />}
              {scheduleEvents.length > 0 && visibleScheduleEvents.length === 0 && (
                <Empty text={scheduleAdminTab === "active" ? "Активных событий нет" : "Закрытых событий нет"} />
              )}
              {visibleScheduleEvents.map((ev) => (
                <div className={styles.row} key={ev.id}>
                  <AppIcon code="schedule" />
                  <div>
                    <strong>
                      {ev.title}
                      {ev.is_overridden && <span className={styles.inlineBadge} data-tone="warning">изм.</span>}
                      {isClosedAdminScheduleEvent(ev) && <span className={styles.inlineBadge} data-tone="warning">закрыт</span>}
                    </strong>
                    <span>{formatDate(ev.start_datetime)}{ev.place ? ` · ${ev.place}` : ""}{ev.squad_id ? ` · ${squadMap.get(ev.squad_id) ?? "отделение"}` : " · все"}</span>
                  </div>
                  {editingEventId === ev.id && (
                    <div className={styles.formBlock} style={{ gridColumn: "1/-1" }}>
                      <input value={eventEdits[ev.id]?.title ?? ""} onChange={(e) => setEventEdits({ ...eventEdits, [ev.id]: { ...eventEdits[ev.id], title: e.target.value } })} />
                      <div className={styles.twoCol}>
                        <label className={styles.fieldLabel}>
                          <span>Начало</span>
                          <input type="datetime-local" value={eventEdits[ev.id]?.start_datetime ?? ""} onChange={(e) => setEventEdits({ ...eventEdits, [ev.id]: { ...eventEdits[ev.id], start_datetime: e.target.value } })} />
                        </label>
                        <label className={styles.fieldLabel}>
                          <span>Конец</span>
                          <input type="datetime-local" value={eventEdits[ev.id]?.end_datetime ?? ""} onChange={(e) => setEventEdits({ ...eventEdits, [ev.id]: { ...eventEdits[ev.id], end_datetime: e.target.value } })} />
                        </label>
                      </div>
                      <input placeholder="Место" value={eventEdits[ev.id]?.place ?? ""} onChange={(e) => setEventEdits({ ...eventEdits, [ev.id]: { ...eventEdits[ev.id], place: e.target.value } })} />
                      <textarea rows={2} placeholder="Описание" value={eventEdits[ev.id]?.description ?? ""} onChange={(e) => setEventEdits({ ...eventEdits, [ev.id]: { ...eventEdits[ev.id], description: e.target.value } })} />
                      <div className={styles.commandStrip}>
                        <button
                          type="button"
                          disabled={updateEvent.isPending || !eventEdits[ev.id]?.title?.trim() || !eventEdits[ev.id]?.start_datetime}
                          onClick={() => {
                            const edit = eventEdits[ev.id];
                            updateEvent.mutate(
                              {
                                id: ev.id,
                                title: edit.title.trim(),
                                description: edit.description || null,
                                start_datetime: new Date(edit.start_datetime).toISOString(),
                                end_datetime: edit.end_datetime ? new Date(edit.end_datetime).toISOString() : null,
                                place: edit.place || null,
                              },
                              { onSuccess: () => { setEditingEventId(null); toast("Событие изменено", "success"); } },
                            );
                          }}
                        >
                          Сохранить изменение
                        </button>
                        <button type="button" disabled={updateEvent.isPending} onClick={() => setEditingEventId(null)}>Отмена</button>
                      </div>
                    </div>
                  )}
                  <div className={styles.commandStrip} style={{ gridColumn: "1/-1" }}>
                    <button
                      type="button"
                      onClick={() => {
                        setEditingEventId(ev.id);
                        setEventEdits({
                          ...eventEdits,
                          [ev.id]: {
                            title: ev.title,
                            description: ev.description ?? "",
                            start_datetime: toDateTimeLocal(ev.start_datetime),
                            end_datetime: toDateTimeLocal(ev.end_datetime),
                            place: ev.place ?? "",
                          },
                        });
                      }}
                    >
                      Изменить
                    </button>
                    {ev.requires_response && !isClosedAdminScheduleEvent(ev) && (
                      <button
                        type="button"
                        className={styles.btnMaybe}
                        disabled={updateEvent.isPending}
                        onClick={() => {
                          if (!window.confirm(`Закрыть опрос «${ev.title}»? Голосование будет остановлено.`)) return;
                          updateEvent.mutate(
                            { id: ev.id, status_code: "CANCELLED" },
                            { onSuccess: () => toast("Опрос закрыт", "info") },
                          );
                        }}
                      >
                        Закрыть опрос
                      </button>
                    )}
                    <button
                      type="button"
                      className={styles.btnNotComing}
                      disabled={deleteEvent.isPending || ev.status_code === "CANCELLED"}
                      onClick={() => {
                        if (!window.confirm(`Удалить событие «${ev.title}»?`)) return;
                        deleteEvent.mutate(ev.id, { onSuccess: () => toast("Событие перемещено в закрытые", "warning") });
                      }}
                    >
                      Удалить
                    </button>
                  </div>
                </div>
              ))}
            </>
          )}

          {/* ── Applications (Pipeline) ── */}
          {tab === "applications" && (() => {
            const startUsers = publicUsers.data ?? [];
            const appliedApps = (applications ?? []).filter((a) => ["NEW", "REVIEWING", "NEEDS_INFO", "AWAITING_DECISION"].includes(a.status_code));
            const invitedApps = (applications ?? []).filter((a) => ["INVITED_MEETING", "INVITED_NORMATIVES"].includes(a.status_code));
            const rosterMembers = (users ?? []).filter((u) => !["PUBLIC_USER", "CANDIDATE", "USER_PENDING"].includes(u.role_code));

            const stages: Array<{ key: typeof pipelineStage; label: string; count: number; color: string }> = [
              { key: "start", label: "/start", count: startUsers.length, color: "#64708b" },
              { key: "applied", label: "Заявки", count: appliedApps.length, color: "#1a2f5a" },
              { key: "invited", label: "Приглашены", count: invitedApps.length, color: "#e67e22" },
              { key: "roster", label: "Состав", count: rosterMembers.length, color: "#27ae60" },
            ];

            const PipelineRow = ({ name, sub, date, badge, badgeColor, onClick }: {
              name: string; sub?: string; date?: string; badge?: string; badgeColor?: string; onClick: () => void;
            }) => (
              <div className={styles.pipelineRow} onClick={onClick} role="button" tabIndex={0}>
                <div className={styles.pipelineRowInfo}>
                  <strong>{name}</strong>
                  {sub && <span>{sub}</span>}
                </div>
                <div className={styles.pipelineRowMeta}>
                  {date && <span className={styles.pipelineDate}>{date}</span>}
                  {badge && <span className={styles.pipelineBadge} style={{ background: badgeColor ?? "#65708a" }}>{badge}</span>}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ color: "#c0c8da", flexShrink: 0 }}><path d="M9 18l6-6-6-6"/></svg>
                </div>
              </div>
            );

            return (
              <>
                {/* Funnel stage tabs */}
                <div className={styles.pipelineStages}>
                  {stages.map((s) => (
                    <button
                      key={s.key}
                      type="button"
                      className={styles.pipelineStageTab}
                      data-active={pipelineStage === s.key}
                      style={pipelineStage === s.key ? { borderColor: s.color, color: s.color } : undefined}
                      onClick={() => setPipelineStage(s.key)}
                    >
                      <span className={styles.pipelineStageCount} style={pipelineStage === s.key ? { background: s.color } : undefined}>{s.count}</span>
                      {s.label}
                    </button>
                  ))}
                </div>

                {/* Stage content */}
                <div className={styles.pipelineTable}>
                  {pipelineStage === "start" && (
                    startUsers.length === 0
                      ? <div className={styles.pipelineEmpty}>Нет пользователей, нажавших /start</div>
                      : startUsers.map((u) => (
                        <PipelineRow
                          key={u.telegram_id}
                          name={u.full_name}
                          sub={u.username ? `@${u.username}` : `TG ${u.telegram_id}`}
                          date={formatShortDate(new Date(u.created_at))}
                          onClick={() => { setDrawerPublicUser(u); setDrawerApp(null); setDrawerRosterUser(null); }}
                        />
                      ))
                  )}

                  {pipelineStage === "applied" && (
                    appliedApps.length === 0
                      ? <div className={styles.pipelineEmpty}>Новых заявок нет</div>
                      : appliedApps.map((a) => (
                        <PipelineRow
                          key={a.id}
                          name={a.full_name}
                          sub={a.username ? `@${a.username}` : a.phone ? formatPhoneDisplay(a.phone) : undefined}
                          date={formatShortDate(new Date(a.created_at))}
                          badge={applicationStatusLabels[a.status_code] ?? a.status_code}
                          badgeColor={APP_STATUS_COLOR[a.status_code]}
                          onClick={() => { setDrawerApp(a); setDrawerPublicUser(null); setDrawerRosterUser(null); }}
                        />
                      ))
                  )}

                  {pipelineStage === "invited" && (
                    invitedApps.length === 0
                      ? <div className={styles.pipelineEmpty}>Нет приглашённых</div>
                      : invitedApps.map((a) => (
                        <PipelineRow
                          key={a.id}
                          name={a.full_name}
                          sub={a.username ? `@${a.username}` : a.phone ? formatPhoneDisplay(a.phone) : undefined}
                          date={formatShortDate(new Date(a.created_at))}
                          badge={applicationStatusLabels[a.status_code] ?? a.status_code}
                          badgeColor={APP_STATUS_COLOR[a.status_code]}
                          onClick={() => { setDrawerApp(a); setDrawerPublicUser(null); setDrawerRosterUser(null); }}
                        />
                      ))
                  )}

                  {pipelineStage === "roster" && (
                    rosterMembers.length === 0
                      ? <div className={styles.pipelineEmpty}>Состав пуст</div>
                      : rosterMembers.map((u) => (
                        <PipelineRow
                          key={u.telegram_id}
                          name={u.full_name}
                          sub={u.username ? `@${u.username}` : squads.find((s) => s.id === u.squad_id)?.name}
                          date={u.linked_at ? formatShortDate(new Date(u.linked_at)) : undefined}
                          badge={squads.find((s) => s.id === u.squad_id)?.name}
                          badgeColor="#27ae60"
                          onClick={() => { setDrawerRosterUser(u); setDrawerApp(null); setDrawerPublicUser(null); }}
                        />
                      ))
                  )}
                </div>

                {/* Detail drawer */}
                {(drawerApp || drawerPublicUser || drawerRosterUser) && (
                  <ApplicantDetailDrawer
                    app={drawerApp}
                    publicUser={drawerPublicUser}
                    rosterUser={drawerRosterUser}
                    squads={squads}
                    applicationSquad={drawerApp ? applicationSquads[drawerApp.id] : undefined}
                    rejectReason={drawerApp ? rejectReasons[drawerApp.id] : undefined}
                    isBusy={isBusy}
                    onSquadChange={(v) => drawerApp && setApplicationSquads((prev) => ({ ...prev, [drawerApp.id]: v }))}
                    onRejectReasonChange={(v) => drawerApp && setRejectReasons((prev) => ({ ...prev, [drawerApp.id]: v }))}
                    onInviteNormatives={() => drawerApp && updateApplication.mutate(
                      { id: drawerApp.id, status_code: "INVITED_NORMATIVES", admin_comment: rejectReasons[drawerApp.id] || undefined },
                      { onSuccess: () => { toast("Приглашён на нормативы", "info"); setDrawerApp(null); } },
                    )}
                    onAccept={() => {
                      if (!drawerApp) return;
                      const squadId = applicationSquads[drawerApp.id];
                      onAccept(drawerApp.id, squadId ? Number(squadId) : null);
                      setDrawerApp(null);
                    }}
                    onReject={() => {
                      if (!drawerApp) return;
                      onReject(drawerApp.id, rejectReasons[drawerApp.id]?.trim() || undefined);
                      setDrawerApp(null);
                    }}
                    onClose={() => { setDrawerApp(null); setDrawerPublicUser(null); setDrawerRosterUser(null); }}
                  />
                )}
              </>
            );
          })()}

          {/* ── Appeals (обращения) ── */}
          {tab === "appeals" && (
            adminAppeals.isLoading ? <Empty text="Загрузка..." /> :
            (adminAppeals.data ?? []).length === 0 ? <Empty text="Обращений нет" /> :
            (adminAppeals.data ?? []).map((item) => (
              <article className={styles.row} key={item.id}>
                <AppIcon code="appeal" />
                <div>
                  <strong>{item.subject}</strong>
                  <span>
                    {appealStatusLabel(item.status_code)} · {item.urgency_code} · {item.category_code}
                    {!item.is_anonymous && item.author_user_id ? ` · пользователь #${item.author_user_id}` : " · анонимно"}
                  </span>
                  <span>{formatDate(item.created_at)}</span>
                  {item.resolution_text && <span style={{ color: "#27ae60" }}>Решение: {item.resolution_text}</span>}
                </div>
                {item.status_code !== "CLOSED" && (
                  <div className={styles.memberControls}>
                    <select
                      defaultValue=""
                      disabled={updateAppeal.isPending}
                      onChange={(event) => {
                        const value = event.target.value;
                        if (!value) return;
                        updateAppeal.mutate(
                          { appealId: item.id, status_code: value },
                          { onSuccess: () => toast(`Статус → ${value}`, "info") },
                        );
                        event.target.value = "";
                      }}
                    >
                      <option value="">Изменить статус...</option>
                      <option value="IN_PROGRESS">В работе</option>
                      <option value="NEEDS_INFO">Нужна информация</option>
                      <option value="RESOLVED">Решено</option>
                      <option value="CLOSED">Закрыто</option>
                    </select>
                  </div>
                )}
              </article>
            ))
          )}

          {/* ── Squads ── */}
          {tab === "squads" && (
            <>
              <div className={styles.formBlock}>
                <input
                  value={newSquadName}
                  placeholder="Название отделения"
                  onChange={(event) => setNewSquadName(event.target.value)}
                />
                <button
                  type="button"
                  disabled={newSquadName.trim().length === 0 || createSquad.isPending}
                  onClick={() => {
                    createSquad.mutate(
                      { name: newSquadName.trim() },
                      { onSuccess: () => { setNewSquadName(""); toast("Отделение создано", "success"); } },
                    );
                  }}
                >
                  Создать отделение
                </button>
              </div>
              {squads.length === 0 ? <Empty text="Отделений нет" /> : squads.map((squad) => {
                const commanderUsers = users.filter((user) => typeof user.id === "number" && roleLevels[user.role_code as RoleCode] >= 4);
                return (
                  <div className={styles.memberRow} key={squad.id}>
                    <div>
                      <input
                        value={squadNames[squad.id] ?? squad.name}
                        onChange={(event) => setSquadNames((prev) => ({ ...prev, [squad.id]: event.target.value }))}
                      />
                      <span>
                        {users.filter((u) => u.squad_id === squad.id).length} участников · {squad.is_active ? "активно" : "неактивно"}
                        {squad.commander_user_id ? ` · Ком: ${users.find((u) => u.id === squad.commander_user_id)?.full_name ?? "—"}` : ""}
                      </span>
                    </div>
                    <div className={styles.memberControls}>
                      <select
                        value={squad.commander_user_id ?? ""}
                        disabled={updateSquad.isPending}
                        onChange={(event) => updateSquad.mutate({ id: squad.id, commander_user_id: event.target.value ? Number(event.target.value) : null })}
                      >
                        <option value="">Командир не выбран</option>
                        {commanderUsers.map((user) => (
                          <option key={user.id} value={user.id as number}>{user.full_name}</option>
                        ))}
                      </select>
                      <select
                        value={squad.deputy_user_id ?? ""}
                        disabled={updateSquad.isPending}
                        onChange={(event) => updateSquad.mutate({ id: squad.id, deputy_user_id: event.target.value ? Number(event.target.value) : null })}
                      >
                        <option value="">Заместитель не выбран</option>
                        {commanderUsers.map((user) => (
                          <option key={user.id} value={user.id as number}>{user.full_name}</option>
                        ))}
                      </select>
                      <button
                        type="button"
                        disabled={updateSquad.isPending}
                        onClick={() => updateSquad.mutate({ id: squad.id, name: (squadNames[squad.id] ?? squad.name).trim() })}
                      >
                        Сохранить
                      </button>
                      <button
                        type="button"
                        disabled={updateSquad.isPending}
                        onClick={() => updateSquad.mutate({ id: squad.id, is_active: !squad.is_active })}
                      >
                        {squad.is_active ? "Деактивировать" : "Активировать"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {/* ── Candidate Events ── */}
          {tab === "events" && (
            <>
              <div className={styles.formBlock}>
                <input placeholder="Название события *" value={newCandEvent.title} onChange={(e) => setNewCandEvent({ ...newCandEvent, title: e.target.value })} />
                <label className={styles.fieldLabel}>
                  <span>Начало *</span>
                  <input type="datetime-local" value={newCandEvent.start_datetime} onChange={(e) => setNewCandEvent({ ...newCandEvent, start_datetime: e.target.value })} />
                </label>
                <input placeholder="Место проведения" value={newCandEvent.place} onChange={(e) => setNewCandEvent({ ...newCandEvent, place: e.target.value })} />
                <input placeholder="Описание" value={newCandEvent.description} onChange={(e) => setNewCandEvent({ ...newCandEvent, description: e.target.value })} />
                <button
                  type="button"
                  disabled={!newCandEvent.title.trim() || !newCandEvent.start_datetime || createCandEvent.isPending}
                  onClick={() => createCandEvent.mutate(
                    {
                      title: newCandEvent.title.trim(),
                      start_datetime: new Date(newCandEvent.start_datetime).toISOString(),
                      place: newCandEvent.place || undefined,
                      description: newCandEvent.description || undefined,
                    },
                    { onSuccess: () => { setNewCandEvent({ title: "", start_datetime: "", place: "", description: "" }); toast("Событие создано", "success"); } },
                  )}
                >
                  {createCandEvent.isPending ? "Создаём..." : "Создать событие для кандидатов"}
                </button>
              </div>
              {adminJoinEvents.isLoading && <Empty text="Загрузка..." />}
              {(adminJoinEvents.data ?? []).length === 0 && !adminJoinEvents.isLoading && <Empty text="Событий нет" />}
              {(adminJoinEvents.data ?? []).map((ev) => (
                <div className={styles.row} key={ev.id}>
                  <AppIcon code="schedule" />
                  <div>
                    <strong>{ev.title}</strong>
                    <span>{formatDate(ev.start_datetime)}{ev.place ? ` · ${ev.place}` : ""} · {ev.is_active ? "активно" : "неактивно"}</span>
                  </div>
                  <button
                    type="button"
                    className={styles.iconAction}
                    onClick={() => updateCandEvent.mutate({ id: ev.id, is_active: !ev.is_active }, {
                      onSuccess: () => toast(ev.is_active ? "Скрыто" : "Показано", "info"),
                    })}
                  >
                    {ev.is_active ? "Скрыть" : "Показать"}
                  </button>
                </div>
              ))}
            </>
          )}

          {/* ── Normatives ── */}
          {tab === "normatives" && (
            <>
              <div className={styles.formBlock}>
                <input placeholder="Название норматива *" value={newNorm.title} onChange={(e) => setNewNorm({ ...newNorm, title: e.target.value })} />
                <input placeholder="Описание" value={newNorm.description} onChange={(e) => setNewNorm({ ...newNorm, description: e.target.value })} />
                <input placeholder="Ссылка на видео правильного выполнения" value={newNorm.instruction_video_url} onChange={(e) => setNewNorm({ ...newNorm, instruction_video_url: e.target.value })} />
                {newNorm.instruction_video_file_id && (
                  <div className={styles.fileAttached}>
                    <span>{newNorm.instruction_video_file_name || "Видеофайл прикреплён"}</span>
                    <button type="button" onClick={() => setNewNorm({ ...newNorm, instruction_video_file_id: null, instruction_video_file_name: "" })}>Убрать</button>
                  </div>
                )}
                <FilePicker
                  accept="video/*"
                  label={uploadNormVideo.isPending ? "Загружаем видео..." : newNorm.instruction_video_file_id ? "Заменить видеофайл" : "Прикрепить видеофайл"}
                  className={styles.fileButton}
                  onFile={handleNewNormVideoUpload}
                />
                <select value={newNorm.target_audience} onChange={(e) => setNewNorm({ ...newNorm, target_audience: e.target.value })}>
                  <option value="ALL">Для всех</option>
                  <option value="PARTICIPANTS">Основной состав</option>
                  <option value="CANDIDATE">Кандидаты / отбор</option>
                  <option value="SQUAD">Для отделения</option>
                  <option value="COMMANDERS">Для командиров</option>
                </select>
                <select value={newNorm.squad_id} onChange={(e) => setNewNorm({ ...newNorm, squad_id: e.target.value })}>
                  <option value="">Без привязки к отделению</option>
                  {squads.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <button
                  type="button"
                  disabled={!newNorm.title.trim() || createNorm.isPending || uploadNormVideo.isPending}
                  onClick={() => createNorm.mutate(
                    {
                      title: newNorm.title.trim(),
                      description: newNorm.description || undefined,
                      target_audience: newNorm.target_audience,
                      squad_id: newNorm.squad_id ? Number(newNorm.squad_id) : null,
                      instruction_video_file_id: newNorm.instruction_video_file_id,
                      instruction_video_url: newNorm.instruction_video_url || null,
                    },
                    { onSuccess: () => { resetNewNorm(); toast("Норматив создан", "success"); } },
                  )}
                >
                  {createNorm.isPending ? "Создаём..." : "Создать норматив"}
                </button>
              </div>
              {adminNorms.isLoading && <Empty text="Загрузка..." />}
              {(adminNorms.data ?? []).length === 0 && !adminNorms.isLoading && <Empty text="Нормативов нет" />}
              {(adminNorms.data ?? []).map((norm) => (
                <div className={styles.row} key={norm.id}>
                  <AppIcon code="norms" />
                  <div>
                    <strong>{norm.title}</strong>
                    <span>{norm.target_audience}{norm.squad_id ? ` · ${squadMap.get(norm.squad_id) ?? "#" + norm.squad_id}` : ""} · {norm.is_active ? "активен" : "архив"}</span>
                    {(norm.instruction_video_url || norm.instruction_video_file_id) && (
                      <span style={{ color: "#1a2f5a" }}>Видео выполнения прикреплено</span>
                    )}
                  </div>
                  <div className={styles.memberControls}>
                    {norm.instruction_video_file_id && (
                      <button
                        type="button"
                        disabled={getFileBlob.isPending}
                        onClick={() => openVideoModal(null, norm.instruction_video_file_id)}
                      >
                        {getFileBlob.isPending ? "Загружаем..." : "Смотреть видеофайл"}
                      </button>
                    )}
                    <input
                      placeholder="Видео выполнения URL"
                      value={normVideoDrafts[norm.id] ?? norm.instruction_video_url ?? ""}
                      onChange={(event) => setNormVideoDrafts((prev) => ({ ...prev, [norm.id]: event.target.value }))}
                    />
                    <FilePicker
                      accept="video/*"
                      label={uploadNormVideo.isPending ? "Загружаем..." : norm.instruction_video_file_id ? "Заменить видеофайл" : "Прикрепить видеофайл"}
                      className={styles.fileButton}
                      onFile={(file) => handleNormVideoUpload(norm.id, file)}
                    />
                    <button
                      type="button"
                      disabled={updateNorm.isPending}
                      onClick={() => updateNorm.mutate(
                        { id: norm.id, instruction_video_url: normVideoDrafts[norm.id] ?? norm.instruction_video_url ?? null },
                        { onSuccess: () => toast("Видео норматива сохранено", "success") },
                      )}
                    >
                      Сохранить видео
                    </button>
                    <button
                      type="button"
                      className={styles.iconAction}
                      disabled={updateNorm.isPending}
                      onClick={() => updateNorm.mutate({ id: norm.id, is_active: !norm.is_active }, {
                        onSuccess: () => toast(norm.is_active ? "Архивирован" : "Восстановлен", "info"),
                      })}
                    >
                      {norm.is_active ? "Архивировать" : "Восстановить"}
                    </button>
                    {!norm.is_active && (
                      <button
                        type="button"
                        className={styles.btnNotComing}
                        disabled={deleteNorm.isPending}
                        onClick={() => {
                          if (!window.confirm(`Удалить норматив «${norm.title}»?`)) return;
                          deleteNorm.mutate(norm.id, { onSuccess: () => toast("Норматив удалён", "warning") });
                        }}
                      >
                        Удалить
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}

          {/* ── Learning materials ── */}
          {tab === "learning" && (
            <>
              <Tabs
                tabs={[["main", "Основной состав"], ["candidates", "Кандидаты / отбор"]]}
                active={learningScope}
                onChange={(value) => {
                  const next = value as typeof learningScope;
                  setLearningScope(next);
                  const audience = next === "candidates" ? "CANDIDATE" : "PARTICIPANTS";
                  setNewCourse((prev) => ({ ...prev, audience_code: audience }));
                  setNewMaterial((prev) => ({ ...prev, audience_code: audience }));
                }}
              />
              <div className={styles.formBlock}>
                <strong style={{ display: "block", marginBottom: 6 }}>Новый курс</strong>
                <input placeholder="Название курса *" value={newCourse.title} onChange={(e) => setNewCourse({ ...newCourse, title: e.target.value })} />
                <input placeholder="Описание" value={newCourse.description} onChange={(e) => setNewCourse({ ...newCourse, description: e.target.value })} />
                <select value={newCourse.audience_code} onChange={(e) => setNewCourse({ ...newCourse, audience_code: e.target.value })}>
                  <option value="ALL">Для всех</option>
                  <option value="PARTICIPANTS">Основной состав</option>
                  <option value="COMMANDERS">Для командиров</option>
                  <option value="CANDIDATE">Для кандидатов</option>
                </select>
                <button
                  type="button"
                  disabled={!newCourse.title.trim() || createCourse.isPending}
                  onClick={() => createCourse.mutate(
                    { title: newCourse.title.trim(), description: newCourse.description || undefined, audience_code: newCourse.audience_code },
                    { onSuccess: () => { setNewCourse({ title: "", description: "", audience_code: currentLearningAudience }); toast("Курс создан", "success"); } },
                  )}
                >
                  {createCourse.isPending ? "Создаём..." : "Создать курс"}
                </button>
              </div>
              <div className={styles.formBlock}>
                <strong style={{ display: "block", marginBottom: 6 }}>Новый материал</strong>
                <input placeholder="Название материала *" value={newMaterial.title} onChange={(e) => setNewMaterial({ ...newMaterial, title: e.target.value })} />
                <input placeholder="URL (видео/ссылка)" value={newMaterial.external_url} onChange={(e) => setNewMaterial({ ...newMaterial, external_url: e.target.value })} />
                {newMaterial.file_id && (
                  <div className={styles.fileAttached}>
                    <span>{newMaterial.file_name || "Файл прикреплён"}</span>
                    <button type="button" onClick={() => setNewMaterial({ ...newMaterial, file_id: null, file_name: "" })}>Убрать</button>
                  </div>
                )}
                <FilePicker
                  accept={FILE_PREVIEW_ACCEPT}
                  label={uploadLearningFile.isPending ? "Загружаем..." : newMaterial.file_id ? "Заменить файл или видео" : "Прикрепить файл или видео"}
                  className={styles.fileButton}
                  onFile={handleNewMaterialFileUpload}
                />
                <select value={newMaterial.type_code} onChange={(e) => setNewMaterial({ ...newMaterial, type_code: e.target.value })}>
                  <option value="TEXT">Текст</option>
                  <option value="VIDEO">Видео</option>
                  <option value="IMAGE">Изображение</option>
                  <option value="PDF">PDF</option>
                  <option value="LINK">Ссылка</option>
                  <option value="FILE">Файл</option>
                </select>
                <select value={newMaterial.audience_code} onChange={(e) => setNewMaterial({ ...newMaterial, audience_code: e.target.value })}>
                  <option value="ALL">Для всех</option>
                  <option value="PARTICIPANTS">Основной состав</option>
                  <option value="COMMANDERS">Для командиров</option>
                  <option value="CANDIDATE">Для кандидатов</option>
                </select>
                <button
                  type="button"
                  disabled={!newMaterial.title.trim() || createMaterial.isPending || uploadLearningFile.isPending}
                  onClick={() => createMaterial.mutate(
                    {
                      title: newMaterial.title.trim(),
                      type_code: newMaterial.type_code,
                      file_id: newMaterial.file_id,
                      external_url: newMaterial.external_url || undefined,
                      audience_code: newMaterial.audience_code,
                      is_active: true,
                    },
                    { onSuccess: () => { resetNewMaterial(); toast("Материал добавлен", "success"); } },
                  )}
                >
                  {createMaterial.isPending ? "Создаём..." : "Добавить материал"}
                </button>
              </div>
              {adminCourses.isLoading && <Empty text="Загрузка курсов..." />}
              {(adminCourses.data ?? []).filter((course) => learningScope === "candidates" ? course.audience_code === "CANDIDATE" : course.audience_code !== "CANDIDATE").map((course) => (
                <div className={styles.row} key={course.id}>
                  <AppIcon code="learning" />
                  <div>
                    <strong>{course.title}</strong>
                    <span>Курс · {course.audience_code} · {course.is_active ? "активен" : "скрыт"}</span>
                  </div>
                  <button
                    type="button"
                    className={styles.iconAction}
                    disabled={updateCourse.isPending}
                    onClick={() => updateCourse.mutate({ id: course.id, is_active: !course.is_active }, {
                      onSuccess: () => toast(course.is_active ? "Скрыт" : "Показан", "info"),
                    })}
                  >
                    {course.is_active ? "Скрыть" : "Показать"}
                  </button>
                </div>
              ))}
              {adminMaterials.isLoading && <Empty text="Загрузка материалов..." />}
              {(adminMaterials.data ?? []).filter((mat) => learningScope === "candidates" ? mat.audience_code === "CANDIDATE" : mat.audience_code !== "CANDIDATE").map((mat) => (
                <div className={styles.row} key={mat.id}>
                  <AppIcon code="learning" />
                  <div>
                    <strong>{mat.title}</strong>
                    <span>{mat.type_code} · {mat.audience_code} · {mat.is_active ? "активен" : "скрыт"}</span>
                    {mat.external_url && <span style={{ fontSize: "0.75rem", wordBreak: "break-all" }}>{mat.external_url}</span>}
                    {mat.file_id && <span style={{ color: "#1a2f5a" }}>Файл или видео прикреплены</span>}
                  </div>
                  <div className={styles.memberControls}>
                    {mat.file_id && (
                      <button
                        type="button"
                        disabled={getFileBlob.isPending}
                        onClick={() => mat.type_code === "VIDEO"
                          ? openVideoModal(null, mat.file_id)
                          : openFile.mutate({ fileId: mat.file_id ?? undefined })}
                      >
                        {getFileBlob.isPending ? "Загружаем..." : mat.type_code === "VIDEO" ? "Смотреть видео" : "Открыть файл"}
                      </button>
                    )}
                    <FilePicker
                      accept={FILE_PREVIEW_ACCEPT}
                      label={uploadLearningFile.isPending ? "Загружаем..." : mat.file_id ? "Заменить файл/видео" : "Прикрепить файл/видео"}
                      className={styles.fileButton}
                      onFile={(file) => handleMaterialFileUpload(mat.id, file)}
                    />
                  <button
                    type="button"
                    className={styles.iconAction}
                    disabled={updateMaterial.isPending}
                    onClick={() => updateMaterial.mutate({ id: mat.id, is_active: !mat.is_active }, {
                      onSuccess: () => toast(mat.is_active ? "Скрыт" : "Показан", "info"),
                    })}
                  >
                    {mat.is_active ? "Скрыть" : "Показать"}
                  </button>
                  </div>
                </div>
              ))}
            </>
          )}

          {/* ── Menu ── */}
          {tab === "menu" && (menu.length === 0 ? <Empty text="Карточек меню нет" /> : menu.map((item) => (
            <article className={styles.row} key={item.id ?? item.code}>
              <AppIcon code={item.icon_code ?? item.code} />
              <div>
                <strong>{item.title}</strong>
                <span>{item.is_required ? "обязательная" : "обычная"} · {item.is_active ? "активна" : "скрыта"} · порядок: {item.sort_order}</span>
              </div>
              {item.id && (
                <div className={styles.memberControls}>
                  <button
                    className={styles.iconAction}
                    type="button"
                    disabled={updateMenu.isPending}
                    onClick={() => updateMenu.mutate({ id: item.id!, is_active: !item.is_active })}
                  >
                    {item.is_active ? "Скрыть" : "Показать"}
                  </button>
                  <button
                    className={styles.iconAction}
                    type="button"
                    disabled={updateMenu.isPending}
                    onClick={() => updateMenu.mutate({ id: item.id!, sort_order: Math.max(0, item.sort_order - 1) })}
                    aria-label="Поднять"
                  >
                    <ChevronUp aria-hidden="true" />
                  </button>
                  <button
                    className={styles.iconAction}
                    type="button"
                    disabled={updateMenu.isPending}
                    onClick={() => updateMenu.mutate({ id: item.id!, sort_order: item.sort_order + 1 })}
                    aria-label="Опустить"
                  >
                    <ChevronDown aria-hidden="true" />
                  </button>
                </div>
              )}
            </article>
          )))}

          {/* ── Audit Logs ── */}
          {tab === "logs" && (
            <>
              <div style={{ display: "flex", gap: 8, marginBottom: 8, flexWrap: "wrap" }}>
                <input
                  placeholder="Код действия (фильтр)"
                  value={logFilter.action_code}
                  onChange={(e) => setLogFilter((f) => ({ ...f, action_code: e.target.value }))}
                  style={{ flex: 1 }}
                />
                <input
                  placeholder="Сущность (users, files...)"
                  value={logFilter.entity_name}
                  onChange={(e) => setLogFilter((f) => ({ ...f, entity_name: e.target.value }))}
                  style={{ flex: 1 }}
                />
              </div>
              {auditFiltered.isLoading && <Empty text="Загрузка..." />}
              {(auditFiltered.data ?? audit).length === 0 ? <Empty text="Аудит-лог пуст" /> : (auditFiltered.data ?? audit).map((item) => (
                <article className={styles.row} key={item.id}>
                  <AppIcon code="admin" />
                  <div>
                    <strong>{item.action_code}</strong>
                    <span>
                      {item.entity_name ?? "—"} #{item.entity_id ?? "—"} · user {item.user_id ?? "—"} · {formatDate(item.created_at)}
                    </span>
                    {item.new_value != null && (
                      <span style={{ fontSize: "0.72rem", color: "#65708a", wordBreak: "break-all" }}>
                        {String(JSON.stringify(item.new_value)).slice(0, 120)}
                      </span>
                    )}
                  </div>
                </article>
              ))}
            </>
          )}

          {/* ── Settings (SUPER_ADMIN only) ── */}
          {tab === "settings" && (
            <>
              {adminSettings.isLoading && <Empty text="Загрузка настроек..." />}
              {adminSettings.data && (() => {
                const byKey = Object.fromEntries(adminSettings.data.map((s) => [s.key, s.value ?? ""]));
                const draft = { ...byKey, ...settingsDraft };
                const field = (key: string, label: string, placeholder = "", type: "text" | "textarea" | "date" = "text") => (
                  <label key={key} className={styles.fieldLabel} style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
                    <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{label}</span>
                    {type === "textarea" ? (
                      <textarea
                        value={draft[key] ?? ""}
                        placeholder={placeholder}
                        rows={3}
                        style={{ width: "100%", resize: "vertical" }}
                        onChange={(e) => setSettingsDraft((d) => ({ ...d, [key]: e.target.value }))}
                      />
                    ) : (
                      <input
                        type={type}
                        value={draft[key] ?? ""}
                        placeholder={placeholder}
                        onChange={(e) => setSettingsDraft((d) => ({ ...d, [key]: e.target.value }))}
                      />
                    )}
                  </label>
                );
                const birthdayTemplate = draft["birthday_greeting_template"] ?? "Поздравляем {name} с днём рождения! Желаем успехов и боевого духа!";
                const birthdayPreview = birthdayTemplate
                  .replace(/\{name\}/g, "Иванов Иван")
                  .replace(/\{first_name\}/g, "Иван")
                  .replace(/\{age\}/g, "17")
                  .replace(/\{squad\}/g, "1 отделение");
                const insertBirthdayToken = (token: string) => {
                  const input = birthdayTemplateRef.current;
                  const current = birthdayTemplate;
                  const start = input?.selectionStart ?? current.length;
                  const end = input?.selectionEnd ?? current.length;
                  const next = `${current.slice(0, start)}${token}${current.slice(end)}`;
                  setSettingsDraft((d) => ({ ...d, birthday_greeting_template: next }));
                  window.requestAnimationFrame(() => {
                    birthdayTemplateRef.current?.focus();
                    birthdayTemplateRef.current?.setSelectionRange(start + token.length, start + token.length);
                  });
                };
                return (
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <strong className={styles.settingsGroupTitle}>Поздравления с днём рождения</strong>
                    <label className={styles.checkboxLine}>
                      <input
                        type="checkbox"
                        checked={(draft["birthday_enabled"] ?? "true") !== "false"}
                        onChange={(e) => setSettingsDraft((d) => ({ ...d, birthday_enabled: e.target.checked ? "true" : "false" }))}
                      />
                      <span>Включить поздравления</span>
                    </label>
                    {field("birthday_time", "Время отправки (HH:MM)", "09:00")}
                    <label className={`${styles.fieldLabel} ${styles.birthdayTemplate}`}>
                      <span>Текст поздравления</span>
                      <textarea
                        ref={birthdayTemplateRef}
                        value={birthdayTemplate}
                        placeholder="Поздравляем {name} с днём рождения!"
                        rows={4}
                        onChange={(e) => setSettingsDraft((d) => ({ ...d, birthday_greeting_template: e.target.value }))}
                      />
                    </label>
                    <div className={styles.tokenBar}>
                      <button type="button" onClick={() => insertBirthdayToken("{name}")}>ФИО</button>
                      <button type="button" onClick={() => insertBirthdayToken("{first_name}")}>Имя</button>
                      <button type="button" onClick={() => insertBirthdayToken("{age}")}>Возраст</button>
                      <button type="button" onClick={() => insertBirthdayToken("{squad}")}>Отделение</button>
                    </div>
                    <div className={styles.birthdayPreview}>
                      <span>Предпросмотр</span>
                      <p>{birthdayPreview}</p>
                    </div>
                    <strong className={styles.settingsGroupTitle}>Расписание</strong>
                    {field("schedule_week_a_start", "Дата начала недели 1", "2026-06-02", "date")}
                    <small style={{ color: "#65708a", fontWeight: 700 }}>
                      Любой понедельник: эта неделя и все четные после нее считаются неделей 1.
                    </small>
                    <label className={styles.fieldLabel} style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
                      <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>Политика 29 февраля</span>
                      <select
                        value={draft["leap_policy"] ?? "28"}
                        onChange={(e) => setSettingsDraft((d) => ({ ...d, leap_policy: e.target.value }))}
                      >
                        <option value="28">28 февраля</option>
                        <option value="march1">1 марта</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      disabled={Object.keys(settingsDraft).length === 0 || updateSettings.isPending}
                      onClick={() => {
                        const changed: Record<string, string | null> = {};
                        for (const [k, v] of Object.entries(settingsDraft)) {
                          changed[k] = v || null;
                        }
                        updateSettings.mutate(changed, {
                          onSuccess: () => { toast("Настройки сохранены", "success"); setSettingsDraft({}); },
                          onError: () => toast("Ошибка сохранения", "error"),
                        });
                      }}
                    >
                      {updateSettings.isPending ? "Сохраняем..." : "Сохранить настройки"}
                    </button>
                  </div>
                );
              })()}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ─────────── DashboardCustomizer ─────────── */
function DashboardCustomizer({
  blocks,
  settings,
  onSave,
  onReset,
  isSaving,
}: {
  blocks: Array<{ code: DashboardBlockCode; title: string; required: boolean; commanderOnly?: boolean }>;
  settings: DashboardSetting[];
  onSave: (items: Array<{ block_code: string; sort_order: number; is_hidden: boolean; is_pinned: boolean; view_mode_code?: string | null }>) => void;
  onReset: () => void;
  isSaving: boolean;
}) {
  const buildDraft = () => {
    const byCode = new Map(settings.map((item) => [item.block_code, item]));
    return [...blocks]
      .sort((left, right) => (byCode.get(left.code)?.sort_order ?? blocks.indexOf(left)) - (byCode.get(right.code)?.sort_order ?? blocks.indexOf(right)))
      .map((block, index) => {
        const setting = byCode.get(block.code);
        return {
          block_code: block.code,
          title: block.title,
          required: block.required,
          sort_order: setting?.sort_order ?? index,
          is_hidden: block.required ? false : setting?.is_hidden ?? false,
          is_pinned: setting?.is_pinned ?? false,
          view_mode_code: setting?.view_mode_code ?? "NORMAL",
        };
      });
  };
  const [draft, setDraft] = useState(buildDraft);

  const settingsKey = settings.map((s) => `${s.block_code}:${s.sort_order}:${s.is_hidden}`).join(",");
  useEffect(() => {
    setDraft(buildDraft());
  }, [settingsKey, blocks.length]);

  const move = (index: number, direction: -1 | 1) => {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= draft.length) return;
    const next = [...draft];
    [next[index], next[newIndex]] = [next[newIndex], next[index]];
    setDraft(next.map((entry, i) => ({ ...entry, sort_order: i })));
  };

  return (
    <details className={styles.customizer}>
      <summary>
        <AppIcon code="admin" />
        <span>Настроить главную</span>
      </summary>
      <div className={styles.dragList}>
        {draft.map((item, index) => (
          <div key={item.block_code} data-hidden={item.is_hidden ? "true" : "false"}>
            <span>{item.title}</span>
            <button
              type="button"
              className={styles.dragMoveBtn}
              disabled={index === 0}
              onClick={() => move(index, -1)}
              title="Вверх"
              aria-label="Вверх"
            >
              <ChevronUp aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.dragMoveBtn}
              disabled={index === draft.length - 1}
              onClick={() => move(index, 1)}
              title="Вниз"
              aria-label="Вниз"
            >
              <ChevronDown aria-hidden="true" />
            </button>
            <label>
              <input
                type="checkbox"
                disabled={item.required}
                checked={!item.is_hidden}
                onChange={(e) =>
                  setDraft(draft.map((entry) =>
                    entry.block_code === item.block_code ? { ...entry, is_hidden: !e.target.checked } : entry
                  ))
                }
              />
              Показывать
            </label>
          </div>
        ))}
      </div>
      <div className={styles.commandStrip}>
        <button
          type="button"
          disabled={isSaving}
          onClick={() =>
            onSave(
              draft.map((item, index) => ({
                block_code: item.block_code,
                sort_order: index,
                is_hidden: item.required ? false : item.is_hidden,
                is_pinned: item.is_pinned,
                view_mode_code: item.view_mode_code,
              })),
            )
          }
        >
          Сохранить
        </button>
        <button type="button" disabled={isSaving} onClick={onReset}>Сбросить</button>
      </div>
    </details>
  );
}

/* ─────────── Reusable components ─────────── */

function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<[string, string]>;
  active: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className={styles.tabs}>
      {tabs.map(([value, label]) => (
        <button key={value} type="button" data-active={active === value} onClick={() => onChange(value)}>
          {label}
        </button>
      ))}
    </div>
  );
}

function MiniList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className={styles.miniList}>
      <strong>{title}</strong>
      {items.length === 0 ? <span>Пока пусто</span> : items.map((item) => <span key={item}>{item}</span>)}
    </div>
  );
}

function LegacyPromoStrip({ items }: { items: PromoBlock[] }) {
  if (items.length === 0) return null;
  return (
    <div className={styles.promoStrip}>
      {items.slice(0, 2).map((item) => (
        <div key={item.id}>
          <strong>{item.title}</strong>
          <span>{item.body ?? item.button_text ?? item.audience_code}</span>
        </div>
      ))}
    </div>
  );
}

function SubmissionRow({
  item,
  onReview,
  isBusy,
}: {
  item: NormativeSubmission;
  onReview?: (submissionId: number, statusCode: string, reviewerComment?: string) => void;
  isBusy?: boolean;
}) {
  const openFile = useOpenFile();
  const sendToBot = useSendFileToBotDM();
  const [reviewComment, setReviewComment] = useState("");
  const fileIds = item.file_ids?.length ? item.file_ids : (item.file_id ? [item.file_id] : []);
  const statusColors: Record<string, string> = {
    SUBMITTED: "#f39c12",
    PENDING: "#f39c12",
    PENDING_REVIEW: "#f39c12",
    ACCEPTED: "#27ae60",
    REJECTED: "#e74c3c",
    NEEDS_REDO: "#3498db",
    OVERDUE: "#95a5a6",
  };
  const statusLabels: Record<string, string> = {
    SUBMITTED: "На проверке",
    PENDING: "На проверке",
    PENDING_REVIEW: "На проверке",
    ACCEPTED: "Принято",
    REJECTED: "Отклонено",
    NEEDS_REDO: "Нужна пересдача",
    OVERDUE: "Просрочено",
  };
  return (
    <article className={styles.row}>
      <AppIcon code="norms" />
      <div>
        <strong>{item.user_full_name ?? `Сдача #${item.id}`}</strong>
        <span style={{ color: statusColors[item.status_code] ?? "#65708a" }}>
          {statusLabels[item.status_code] ?? item.status_code} · {item.normative_title ?? `норматив #${item.normative_id}`} · сдано {formatDate(item.submitted_at)}
        </span>
        {item.reviewed_at && (
          <span>Проверено {formatDate(item.reviewed_at)}{item.reviewer_full_name ? ` · ${item.reviewer_full_name}` : ""}</span>
        )}
        {item.comment && <span style={{ color: "#65708a" }}>Пояснение: {item.comment}</span>}
        {item.reviewer_comment && <span>Комментарий: {item.reviewer_comment}</span>}
        {item.grade_value && <span>Оценка: {item.grade_value}</span>}
      </div>
      {(() => {
        const tgMatch = item.comment?.match(/\[TG file_id: ([^\]]+)\]/);
        if (tgMatch) {
          const tgFileId = tgMatch[1];
          return (
            <div className={styles.filePreviewActions}>
              <small style={{ color: "#65708a", fontSize: 11, fontWeight: 700 }}>Файл загружен через бот</small>
              <button
                type="button"
                disabled={openFile.isPending}
                onClick={() => openFile.mutate({ tgFileId })}
              >
                {openFile.isPending ? "Открываем..." : "Открыть файл"}
              </button>
            </div>
          );
        }
        if (fileIds.length > 0) {
          return (
            <div className={styles.filePreviewActions}>
              {fileIds.map((fileId, index) => (
                <button
                  key={fileId}
                  type="button"
                  disabled={sendToBot.isPending}
                  onClick={() => sendToBot.mutate(fileId, {
                    onSuccess: () => toast("Файл отправлен в личные сообщения", "success"),
                    onError: () => toast("Не удалось отправить файл", "error"),
                  })}
                >
                  {sendToBot.isPending ? "Отправляем..." : `Отправить в бота${fileIds.length > 1 ? ` (${index + 1})` : ""}`}
                </button>
              ))}
            </div>
          );
        }
        return null;
      })()}
      {onReview && (
        <>
          <input
            style={{ gridColumn: "1/-1", border: "1px solid #d9deea", borderRadius: 10, padding: "8px 12px", fontSize: 16, fontFamily: "inherit", color: "#1a2f5a" }}
            placeholder="Комментарий проверяющего (необязательно)"
            value={reviewComment}
            onChange={(e) => setReviewComment(e.target.value)}
          />
          <div className={styles.actions}>
            <button type="button" className={styles.btnComing} disabled={isBusy} onClick={() => onReview(item.id, "ACCEPTED", reviewComment || undefined)}>Принять</button>
            <button type="button" className={styles.btnMaybe} disabled={isBusy} onClick={() => onReview(item.id, "NEEDS_REDO", reviewComment || undefined)}>Доработать</button>
            <button type="button" className={styles.btnNotComing} disabled={isBusy} onClick={() => onReview(item.id, "REJECTED", reviewComment || undefined)}>Отклонить</button>
          </div>
        </>
      )}
    </article>
  );
}

function Metric({ label, value, extraClass }: { label: string; value: number | string; extraClass?: string }) {
  return (
    <div className={`${styles.metric} ${extraClass ?? ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className={styles.empty}>{text}</div>;
}

function StreakBadge({ current, best }: { current: number; best: number }) {
  const isActive = current > 0;
  return (
    <div className={styles.streakBadge}>
      <span className={styles.streakIcon} data-active={isActive ? "true" : "false"}>
        <Flame aria-hidden="true" />
      </span>
      <div>
        <strong>
          {isActive
            ? `${current} занятий подряд без пропуска`
            : "Серия прервана — вернись скорее!"}
        </strong>
        <span>Лучшая серия: {best} занятий</span>
      </div>
    </div>
  );
}

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  const typeColors: Record<string, string> = {
    response: "#3498db",
    normative: "#27ae60",
    appeal: "#e74c3c",
    attendance: "#f39c12",
  };
  return (
    <div className={styles.activityFeed}>
      <div className={styles.panelHeader} style={{ marginBottom: 8 }}>
        <h2>Активность</h2>
        <span>{items.length} событий</span>
      </div>
      {items.map((item, i) => (
        <div key={i} className={styles.activityItem}>
          <div
            className={styles.activityDot}
            style={{ background: typeColors[item.type] ?? "#bdc3c7" }}
          />
          <div>
            <span>{item.text}</span>
            <small>{formatDate(item.created_at)}</small>
          </div>
        </div>
      ))}
    </div>
  );
}

function Skeleton({ width = "100%", height = 20, radius = 8 }: { width?: string | number; height?: number; radius?: number }) {
  return (
    <div
      className={styles.skeleton}
      style={{ width, height, borderRadius: radius }}
    />
  );
}

function SkeletonCard() {
  return (
    <div className={styles.skeletonCard}>
      <Skeleton height={16} width="60%" />
      <Skeleton height={12} width="80%" />
      <Skeleton height={12} width="40%" />
    </div>
  );
}

function extractCount(item: unknown): number {
  if (typeof item === "number") return item;
  if (typeof item === "object" && item && "count" in item && typeof (item as Record<string, unknown>).count === "number") {
    return (item as Record<string, unknown>).count as number;
  }
  return 0;
}
