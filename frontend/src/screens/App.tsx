import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  useDownloadFile,
  useExportReport,
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
  useSubmitNormative,
  useTelegramAuth,
  useUpdateDashboardSettings,
  useUploadAvatar,
  useUploadFile,
  useUsers,
  useAdminAcceptApplication,
  useAdminRejectApplication,
  useMyStreak,
  useCreatePromoBlock,
  useUpdatePromoBlock,
  useDeletePromoBlock,
  useAttendanceEvent,
  useUpdateMenuCard,
  useUpdateSquad,
  useUpdateUser,
} from "../api/queries";
import { api } from "../api/client";
import type {
  Appeal,
  AppealMessage,
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

type Props = {
  webApp: {
    initData: string;
    HapticFeedback?: {
      impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
      notificationOccurred?: (type: "error" | "success" | "warning") => void;
    };
    BackButton?: { show: () => void; hide: () => void; onClick: (fn: () => void) => void; offClick: (fn: () => void) => void };
    MainButton?: { show: () => void; hide: () => void; setText: (t: string) => void; onClick: (fn: () => void) => void; offClick: (fn: () => void) => void; showProgress: (b: boolean) => void };
  };
};

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
};

type AnnouncementPayload = {
  title: string;
  body: string;
  target_type: string;
  target_squad_id?: number | null;
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

const iconByCode: Record<string, string> = {
  dashboard: "home.png",
  home: "home.png",
  schedule: "schedule.png",
  attendance: "attendance.png",
  mark_attendance: "mark-attendance.png",
  normatives: "norms.png",
  norms: "norms.png",
  learning: "report.png",
  notifications: "notifications.png",
  announcements: "announcements.png",
  appeals: "report.png",
  reports: "reports.png",
  admin: "admin.png",
  profile: "profile.png",
  people: "full-roster.png",
  squads: "full-roster.png",
  join: "home.png",
  full_roster: "full-roster.png",
  my_squad: "my-squad.png",
  appeal: "report.png",
};

function roleMenu(profile: UserProfile): MenuCard[] {
  const level = roleLevels[profile.role_code];
  const cards: MenuCard[] = [
    menuCard("schedule", "Расписание", "занятия, сборы и ответы", "schedule"),
    menuCard("people", "Состав", "отделение и общий список", "full_roster"),
    menuCard("attendance", "Посещаемость", "свои отметки и статистика", "attendance"),
    menuCard("normatives", "Нормативы", "задания и отчёты", "norms"),
    menuCard("learning", "Материалы", "курсы и памятки", "learning"),
    menuCard("notifications", "Уведомления", "личные сообщения", "notifications"),
    menuCard("appeals", "Проблема", "обращение командованию", "appeals"),
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

function formatDate(value: string | null) {
  if (!value) return "без даты";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function formatDateFull(value: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "long", year: "numeric" }).format(new Date(value));
}

type NavItem = {
  view: ViewKey;
  iconCode: string;
  label: string;
  minLevel: number;
};

const navItems: NavItem[] = [
  { view: "dashboard", iconCode: "home", label: "Главная", minLevel: 0 },
  { view: "schedule", iconCode: "schedule", label: "Расписание", minLevel: 0 },
  { view: "attendance", iconCode: "attendance", label: "Явка", minLevel: 3 },
  { view: "normatives", iconCode: "norms", label: "Нормативы", minLevel: 3 },
  { view: "profile", iconCode: "profile", label: "Профиль", minLevel: 0 },
];

const adminNavItem: NavItem = { view: "admin", iconCode: "admin", label: "Админка", minLevel: 6 };

const viewMinLevels: Record<ViewKey, number> = {
  dashboard: 0,
  schedule: 0,
  attendance: 3,
  normatives: 3,
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

function iconPath(code: string | null | undefined) {
  const fileName = iconByCode[code ?? ""] ?? "admin.png";
  return `/assets/icons/${fileName}`;
}

function apiPath(path: string) {
  const base = (api.defaults.baseURL ?? "").replace(/\/$/, "");
  return `${base}${path}`;
}

function avatarPath(fileId: number | null | undefined) {
  return fileId ? apiPath(`/files/avatars/${fileId}`) : null;
}

/* ─────────────────────────── App ─────────────────────────── */

export function App({ webApp }: Props) {
  const auth = useTelegramAuth();
  const [profile, setProfile] = useState<UserProfile>(fallbackProfile);
  const [activeView, setActiveView] = useState<ViewKey>("dashboard");
  const [prevView, setPrevView] = useState<ViewKey | null>(null);
  const [milestoneStreak, setMilestoneStreak] = useState<number | null>(null);
  const prevStreakRef = useRef<number>(0);
  const hasToken = Boolean(auth.data?.access_token);

  // Apply Telegram color scheme to CSS
  useEffect(() => {
    const tg = (window as Window & { Telegram?: { WebApp?: { colorScheme?: string; themeParams?: Record<string, string> } } }).Telegram?.WebApp;
    if (tg?.colorScheme === "dark") {
      document.documentElement.setAttribute("data-theme", "dark");
    }
    if (tg?.themeParams) {
      const tp = tg.themeParams;
      const root = document.documentElement;
      if (tp.bg_color) root.style.setProperty("--tg-bg", tp.bg_color);
      if (tp.text_color) root.style.setProperty("--tg-text", tp.text_color);
      if (tp.button_color) root.style.setProperty("--tg-button", tp.button_color);
    }
  }, []);
  const level = roleLevels[profile.role_code];
  const publicMode = hasToken && level < 3;
  const internalMode = hasToken && level >= 3;

  const menu = useMenu(hasToken);
  const publicContent = usePublicContent(publicMode);
  const publicEvents = usePublicEvents(publicMode);
  const joinMe = useJoinMe(hasToken && profile.role_code === "CANDIDATE");
  const joinEvents = useJoinEvents(hasToken && profile.role_code === "CANDIDATE");
  const schedule = useSchedule(internalMode);
  const attendance = useMyAttendance(internalMode);
  const attendanceStats = useMyAttendanceStats(internalMode);
  const normatives = useNormatives(internalMode, level >= 6);
  const mySubmissions = useMyNormativeSubmissions(internalMode);
  const pendingSubmissions = usePendingNormativeSubmissions(hasToken && level >= 4);
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
  const adminUsers = useAdminUsers(hasToken && level >= 6);
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
    const initData = webApp.initData;
    if (!initData) return;
    auth.mutate(initData, {
      onSuccess: (data) => setProfile(data.profile),
    });
  }, []);

  const cards = useMemo(() => {
    const apiMenu = menu.data?.map((card) => ({ ...card, code: normalizeView(card.code) }));
    const source = apiMenu?.length ? apiMenu : roleMenu(profile);
    return source.filter((card) => canAccessView(normalizeView(card.code), level));
  }, [menu.data, profile, level]);

  const visibleSchedule = schedule.data ?? [];
  const visibleNormatives = normatives.data ?? [];
  const visibleAttendance = attendance.data ?? [];
  const unreadCount = notifications.data?.filter((item) => !item.is_read).length ?? 0;
  const visibleCandidateEvents = joinEvents.data?.length ? joinEvents.data : publicEvents.data ?? [];

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

  const visibleNav = [
    ...navItems.filter((item) => level >= item.minLevel),
    ...(level >= adminNavItem.minLevel ? [adminNavItem] : []),
  ];

  return (
    <>
    <ToastContainer />
    {milestoneStreak !== null && (
      <MilestoneToast streak={milestoneStreak} onDismiss={() => setMilestoneStreak(null)} />
    )}
    <main className={styles.shell}>
      <header className={styles.header}>
        <img src="/assets/zvezda-emblem.jpg" alt="ВПК Звезда" />
        <div>
          <strong>ВПК Звезда</strong>
          <span>{roleLabels[profile.role_code]}</span>
        </div>
      </header>

      <section className={styles.statusPanel}>
        <div>
          <p>{profile.full_name}</p>
          <h1>{level >= 3 ? "Личный кабинет" : "Вступление в клуб"}</h1>
        </div>
        <dl>
          <div>
            <dt>Отделение</dt>
            <dd>{profile.squad_id ?? "—"}</dd>
          </div>
          <div>
            <dt>Новых</dt>
            <dd>{unreadCount}</dd>
          </div>
        </dl>
      </section>

      <section className={styles.menuGrid} aria-label="Разделы">
        {cards.map((card) => (
          <button
            key={`${card.code}-${card.title}`}
            className={styles.menuCard}
            data-code={card.code}
            type="button"
            onClick={() => openView(card.code)}
          >
            <img src={iconPath(card.icon_code ?? card.code)} alt="" />
            <span>{card.title}</span>
            <small>{card.description}</small>
          </button>
        ))}
      </section>

      <section className={styles.workspace}>
        {auth.isPending && (
          <div className={styles.panel}>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </div>
        )}
        {!auth.isPending && activeView === "dashboard" && (
          profile.role_code === "CANDIDATE" ? (
            <CandidateDashboard
              application={joinMe.data ?? null}
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
              onSaveSettings={(items) => updateDashboardSettings.mutate(items)}
              onResetSettings={() => resetDashboardSettings.mutate()}
              isSavingSettings={updateDashboardSettings.isPending || resetDashboardSettings.isPending}
              navigate={openView}
              onRespond={(eventId, responseCode, absenceReasonId, customReason) =>
                respondEvent.mutate(
                  { eventId, responseCode, absenceReasonId, customReason },
                  {
                    onSuccess: () => {
                      hapticSuccess();
                      const labels: Record<string, string> = { COMING: "Ответ «Приду» сохранён ✅", NOT_COMING: "Ответ «Не приду» сохранён", MAYBE: "Ответ «Уточню» сохранён ⏳" };
                      toast(labels[responseCode] ?? "Ответ сохранён", "success");
                    },
                    onError: () => { hapticError(); toast("Не удалось сохранить ответ", "error"); },
                  },
                )
              }
            />
          )
        )}

        {!auth.isPending && activeView === "schedule" && (
          level < 3 ? (
            <CandidateEventsView
              events={visibleCandidateEvents}
              readonly={profile.role_code !== "CANDIDATE"}
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
              onRespond={(eventId, responseCode, absenceReasonId, customReason) => {
                respondEvent.mutate(
                  { eventId, responseCode, absenceReasonId, customReason },
                  { onSuccess: () => webApp.HapticFeedback?.notificationOccurred?.("success") },
                );
              }}
            />
          )
        )}

        {!auth.isPending && activeView === "attendance" && level >= 3 && (
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

        {!auth.isPending && activeView === "normatives" && level >= 3 && (
          <NormativesView
            items={visibleNormatives}
            submissions={mySubmissions.data ?? []}
            pending={pendingSubmissions.data ?? []}
            canReview={level >= 4}
            onSubmit={(normativeId, comment, fileId) =>
              submitNormative.mutate(
                { normativeId, comment, fileId },
                {
                  onSuccess: () => { hapticSuccess(); toast("Сдача отправлена на проверку 📋", "success"); },
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
                    const msgs: Record<string, string> = { ACCEPTED: "Сдача принята ✅", REJECTED: "Сдача отклонена", NEEDS_REDO: "Отправлено на доработку" };
                    toast(msgs[statusCode] ?? "Статус обновлён", statusCode === "ACCEPTED" ? "success" : "info");
                  },
                },
              )
            }
            isBusy={submitNormative.isPending || reviewSubmission.isPending}
          />
        )}

        {!auth.isPending && activeView === "learning" && (
          <LearningView
            items={learning.data ?? []}
            courses={learningCourses.data ?? []}
          />
        )}

        {!auth.isPending && activeView === "notifications" && level >= 3 && (
          <NotificationsView
            items={notifications.data ?? []}
            onRead={(id) => readNotification.mutate(id)}
            onReadAll={() => readAll.mutate()}
            isBusy={readAll.isPending}
          />
        )}

        {!auth.isPending && activeView === "announcements" && level >= 4 && (
          <AnnouncementsView
            items={announcements.data ?? []}
            onCreate={(payload) =>
              createAnnouncement.mutate(payload, {
                onSuccess: (item: { id: number }) => sendAnnouncement.mutate(item.id),
              })
            }
            isSubmitting={createAnnouncement.isPending || sendAnnouncement.isPending}
          />
        )}

        {!auth.isPending && activeView === "appeals" && level >= 3 && (
          <AppealsView
            items={appeals.data ?? []}
            currentUserId={profile.id}
            onCreate={(payload) =>
              createAppeal.mutate(payload, {
                onSuccess: () => { hapticSuccess(); toast("Обращение отправлено ✅", "success"); },
                onError: () => { hapticError(); toast("Не удалось отправить обращение", "error"); },
              })
            }
            isSubmitting={createAppeal.isPending}
          />
        )}

        {!auth.isPending && activeView === "reports" && level >= 5 && (
          <ReportsView
            level={level}
            attendance={attendanceReport.data}
            grades={gradesReport.data}
            normatives={normativesReport.data}
          />
        )}

        {!auth.isPending && activeView === "people" && level >= 3 && (
          <PeopleView
            level={level}
            profile={profile}
            mySquad={mySquad.data ?? null}
            allUsers={allUsers.data ?? []}
            squads={adminSquads.data ?? []}
          />
        )}

        {!auth.isPending && activeView === "profile" && (
          <ProfileView
            profile={profile}
            attendanceStats={attendanceStats.data}
            submissions={mySubmissions.data ?? []}
            streak={myStreak.data ?? null}
            onAvatarUpload={(file) =>
              uploadAvatar.mutate(file, {
                onSuccess: (updatedProfile) => {
                  setProfile(updatedProfile);
                  hapticSuccess();
                  toast("Аватар обновлён", "success");
                },
                onError: () => {
                  hapticError();
                  toast("Не удалось загрузить аватар", "error");
                },
              })
            }
            isAvatarUploading={uploadAvatar.isPending}
          />
        )}

        {!auth.isPending && activeView === "admin" && level >= 6 && (
          <AdminView
            level={level}
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
              <img src={iconPath(iconCode)} alt="" />
            </span>
            <span>{label}</span>
          </button>
        ))}
      </nav>
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
  const [customReason, setCustomReason] = useState("");
  const reasons = useAbsenceReasons();
  const activeReasons = reasons.data?.filter((r) => r.is_active) ?? [];

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
                  setPickingReason(false);
                  onRespond(eventId, "NOT_COMING", reason.id, undefined);
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
            style={{ border: "1px solid #d9deea", borderRadius: 10, padding: "8px 12px", fontSize: 12, fontFamily: "inherit", color: "#1a2f5a" }}
          />
          {customReason.trim().length >= 2 && (
            <button
              type="button"
              className={styles.btnNotComing}
              onClick={() => {
                setPickingReason(false);
                onRespond(eventId, "NOT_COMING", null, customReason.trim());
              }}
            >
              Отправить причину
            </button>
          )}
          <button type="button" className={styles.btnMaybeOutline} onClick={() => setPickingReason(false)}>
            Отмена
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.actions}>
      <button
        type="button"
        className={currentResponse === "COMING" ? styles.btnComing : styles.btnComingOutline}
        onClick={() => onRespond(eventId, "COMING")}
      >
        ✅ Приду
      </button>
      <button
        type="button"
        className={currentResponse === "NOT_COMING" ? styles.btnNotComing : styles.btnNotComingOutline}
        onClick={() => {
          if (requiresResponse) {
            setPickingReason(true);
          } else {
            onRespond(eventId, "NOT_COMING");
          }
        }}
      >
        ❌ Не приду
      </button>
      <button
        type="button"
        className={currentResponse === "MAYBE" ? styles.btnMaybe : styles.btnMaybeOutline}
        onClick={() => onRespond(eventId, "MAYBE")}
      >
        ⏳ Уточню
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

  const nextEvent = schedule[0];
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
              <div key={block.code}>
                <div className={styles.commandSummary}>
                  <Metric label="Событий" value={schedule.length} extraClass={styles.metricBlue} />
                  <Metric label="Без ответа" value={notAnswered} />
                  <Metric label="Причин ждут" value={attendance.filter((r) => r.status_code === "ABSENT").length} />
                  <Metric label="На проверке" value={normatives.length} extraClass={styles.metricGreen} />
                </div>
                {activityFeed.length > 0 && <ActivityFeed items={activityFeed.slice(0, 8)} />}
              </div>
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
  const canSubmit = form.full_name.trim().length >= 2 && form.consent_given;

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>{content?.title ?? "ВПК «Звезда»"}</h2>
        <span>публичный режим</span>
      </div>
      <div className={styles.publicIntro}>
        <p>{content?.description ?? "Подайте заявку, посмотрите ближайшие открытые мероприятия и материалы для подготовки."}</p>
        <div className={styles.requirements}>
          <span>Дисциплина</span>
          <span>Форма и порядок</span>
          <span>Готовность учиться</span>
        </div>
      </div>
      <LegacyPromoStrip items={content?.promo_blocks ?? []} />
      <CandidateEventsView events={events} readonly onRespond={() => undefined} compact />
      <MiniList title="Материалы для вступления" items={(content?.materials ?? []).map((item) => item.title).slice(0, 4)} />
      <div className={styles.formBlock}>
        <input placeholder="ФИО *" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        <input type="date" aria-label="Дата рождения" value={form.birth_date} onChange={(e) => setForm({ ...form, birth_date: e.target.value })} />
        <input placeholder="Телефон" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        <input placeholder="Город или район" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
        <input placeholder="Учебное заведение" value={form.education_place} onChange={(e) => setForm({ ...form, education_place: e.target.value })} />
        <textarea placeholder="Опыт или подготовка" rows={2} value={form.experience_text} onChange={(e) => setForm({ ...form, experience_text: e.target.value })} />
        <textarea placeholder="Почему хотите вступить *" rows={3} value={form.motivation_text} onChange={(e) => setForm({ ...form, motivation_text: e.target.value })} />
        <input placeholder="Откуда узнали о ВПК" value={form.source_text} onChange={(e) => setForm({ ...form, source_text: e.target.value })} />
        <textarea placeholder="Комментарий" rows={2} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
        <label className={styles.checkboxLine}>
          <input type="checkbox" checked={form.consent_given} onChange={(e) => setForm({ ...form, consent_given: e.target.checked })} />
          <span>Согласен на обработку данных для заявки</span>
        </label>
        <button type="button" disabled={!canSubmit || isSubmitting} onClick={() => onSubmit(form)}>
          {isSubmitting ? "Отправляем..." : "Подать заявку"}
        </button>
      </div>
    </div>
  );
}

/* ─────────── CandidateDashboard ─────────── */
function CandidateDashboard({
  application,
  events,
  materials,
  notifications,
  onRespond,
}: {
  application: JoinApplication | null;
  events: CandidateEvent[];
  materials: LearningMaterial[];
  notifications: Notification[];
  onRespond: (eventId: number, responseCode: string) => void;
}) {
  const steps = [
    { title: "Анкета заполнена", done: Boolean(application) },
    { title: "Материалы открыты", done: materials.length > 0 },
    { title: "Запись на мероприятие", done: events.length > 0 },
    { title: "Ожидание решения", done: ["AWAITING_DECISION", "ACCEPTED"].includes(application?.status_code ?? "") },
  ];

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Кабинет кандидата</h2>
        <span>{applicationStatusLabels[application?.status_code ?? ""] ?? "заявка создаётся"}</span>
      </div>
      <div className={styles.steps}>
        {steps.map((step, index) => (
          <div key={step.title} data-done={step.done}>
            <b>{index + 1}</b>
            <span>{step.title}</span>
          </div>
        ))}
      </div>
      {application?.admin_comment && (
        <div className={styles.nextItem}>
          <span>Комментарий администратора</span>
          <strong>{application.admin_comment}</strong>
        </div>
      )}
      <CandidateEventsView events={events} onRespond={onRespond} />
      <MiniList title="Подготовка" items={materials.map((item) => item.title).slice(0, 4)} />
      <MiniList title="Уведомления по заявке" items={notifications.map((item) => item.title).slice(0, 3)} />
    </div>
  );
}

/* ─────────── CandidateEventsView ─────────── */
function CandidateEventsView({
  events,
  readonly = false,
  compact = false,
  onRespond,
}: {
  events: CandidateEvent[];
  readonly?: boolean;
  compact?: boolean;
  onRespond: (eventId: number, responseCode: string) => void;
}) {
  return (
    <div className={compact ? styles.compactSection : styles.subPanel}>
      <div className={styles.panelHeader}>
        <h2>{readonly ? "Открытые мероприятия" : "Мероприятия кандидата"}</h2>
        <span>{events.length} доступно</span>
      </div>
      <div className={styles.list}>
        {events.length === 0 && <Empty text="Даты появятся после публикации" />}
        {events.map((event) => (
          <article className={styles.row} key={event.id}>
            <img src={iconPath("schedule")} alt="" />
            <div>
              <strong>{event.title}</strong>
              <span>{formatDate(event.start_datetime)} · {event.place ?? "место уточняется"}</span>
            </div>
            {!readonly && (
              <ResponseButtons eventId={event.id} onRespond={onRespond} />
            )}
          </article>
        ))}
      </div>
    </div>
  );
}

/* ─────────── ScheduleView ─────────── */
function ScheduleView({ events, onRespond }: { events: ScheduleEvent[]; onRespond: RespondFn }) {
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
      <Tabs
        tabs={[["today", "Сегодня"], ["week", "Неделя"], ["month", "Месяц"], ["archive", "Архив"]]}
        active={tab}
        onChange={(value) => { setTab(value as typeof tab); setFilter("all"); }}
      />
      {tab !== "archive" && (
        <div className={styles.filterChips}>
          <button type="button" className={styles.chip} data-active={filter === "all"} onClick={() => setFilter("all")}>Все</button>
          <button type="button" className={styles.chip} data-active={filter === "unanswered"} onClick={() => setFilter("unanswered")}>Без ответа</button>
          <button type="button" className={styles.chip} data-active={filter === "coming"} data-color="green" onClick={() => setFilter("coming")}>Иду ✅</button>
          <button type="button" className={styles.chip} data-active={filter === "not_coming"} data-color="red" onClick={() => setFilter("not_coming")}>Не иду ❌</button>
        </div>
      )}
      <div className={styles.list}>
        {filtered.length === 0 && <Empty text="В этой вкладке пока пусто" />}
        {filtered.map((event) => (
          <article className={styles.row} key={event.id}>
            <img src={iconPath("schedule")} alt="" />
            <div>
              <strong>{event.title}</strong>
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
  const eventAttendance = useAttendanceEvent(selectedEventId, canManage && selectedEventId !== null);
  const markAttendance = useMarkAttendance();
  const eventMap = new Map(schedule.map((e) => [e.id, e.title]));
  const scopeSquadId = selectedEvent?.squad_id ?? (managerLevel < 5 ? managerSquadId : null);
  const targetUsers = users.filter((user) => {
    if (managerLevel < 5 && scopeSquadId === null) return false;
    if (typeof user.id !== "number" || user.status_code !== "ACTIVE") return false;
    if (roleLevels[user.role_code as RoleCode] < roleLevels.PARTICIPANT) return false;
    if (scopeSquadId !== null && user.squad_id !== scopeSquadId) return false;
    return true;
  });
  const existingAttendance = new Map((eventAttendance.data ?? []).map((item) => [item.user_id, item.status_code]));

  const statusLabels: Record<string, string> = {
    PRESENT: "Присутствовал", ABSENT: "Отсутствовал", LATE: "Опоздал",
    EXCUSED: "Уважительная", SICK: "Больничный", RELEASED: "Освобождён", NOT_MARKED: "Не отмечен",
  };
  const statusOptions = ["PRESENT", "ABSENT", "LATE", "EXCUSED", "SICK", "RELEASED", "NOT_MARKED"];

  useEffect(() => {
    if (!canManage) return;
    if (selectedEventId === null && manageableEvents.length > 0) {
      setSelectedEventId(manageableEvents[0].id);
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

  // Build heatmap data: one entry per attendance record with date from schedule
  const heatData = records
    .filter((r) => r.marked_at)
    .map((r) => ({
      date: r.marked_at!.slice(0, 10),
      status: r.status_code,
    }));

  // Monthly bar chart data
  const monthCounts: Record<string, number> = {};
  for (const r of records) {
    if (!r.marked_at) continue;
    const month = new Intl.DateTimeFormat("ru-RU", { month: "short" }).format(new Date(r.marked_at));
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
              <img src={iconPath("attendance")} alt="" />
              <div>
                <strong>{eventMap.get(record.event_id) ?? `Занятие #${record.event_id}`}</strong>
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
              {manageableEvents.length === 0 && <option value="">Нет доступных событий</option>}
              {manageableEvents.map((event) => (
                <option key={event.id} value={event.id}>
                  {event.title} · {formatDate(event.start_datetime)}
                </option>
              ))}
            </select>
          </div>
          <div className={styles.list}>
            {selectedEventId === null && <Empty text="Выберите событие для отметки" />}
            {selectedEventId !== null && targetUsers.length === 0 && <Empty text="Нет участников для отметки" />}
            {targetUsers.map((user) => {
              const userId = user.id as number;
              const value = draftAttendance[userId] ?? existingAttendance.get(userId) ?? "NOT_MARKED";
              return (
                <div className={styles.memberRow} key={userId}>
                  <div>
                    <strong>{user.full_name}</strong>
                    <span>{statusLabels[value] ?? value}</span>
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
          {selectedEventId !== null && targetUsers.length > 0 && (
            <div className={styles.commandStrip}>
              <button
                type="button"
                disabled={markAttendance.isPending}
                onClick={() => {
                  markAttendance.mutate(
                    {
                      eventId: selectedEventId,
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

/* ─────────── NormativesView ─────────── */
function NormativesView({
  items,
  submissions,
  pending,
  canReview,
  onSubmit,
  onReview,
  isBusy,
}: {
  items: Normative[];
  submissions: NormativeSubmission[];
  pending: NormativeSubmission[];
  canReview: boolean;
  onSubmit: (normativeId: number, comment?: string, fileId?: number | null) => void;
  onReview: (submissionId: number, statusCode: string, reviewerComment?: string) => void;
  isBusy: boolean;
}) {
  const [tab, setTab] = useState<"active" | "mine" | "pending" | "accepted" | "archive">("active");
  const accepted = submissions.filter((item) => item.status_code === "ACCEPTED");
  const activeItems = items.filter((item) => item.is_active);
  const archiveItems = items.filter((item) => !item.is_active);
  const upload = useUploadFile();
  const [uploadedFiles, setUploadedFiles] = useState<Record<number, { id: number; name: string }>>({});
  const [comments, setComments] = useState<Record<number, string>>({});
  const tabs: Array<["active" | "mine" | "pending" | "accepted" | "archive", string]> = [
    ["active", "Активные"],
    ["mine", "Мои сдачи"],
    ...(canReview ? ([["pending", "На проверке"]] as Array<["pending", string]>) : []),
    ["accepted", "Принятые"],
    ["archive", "Архив"],
  ];

  useEffect(() => {
    if (tab === "pending" && !canReview) setTab("active");
  }, [tab, canReview]);

  const handleFileChange = async (normativeId: number, file: File) => {
    const result = await upload.mutateAsync(file);
    setUploadedFiles((prev) => ({ ...prev, [normativeId]: { id: result.id, name: file.name } }));
  };

  return (
    <div className={styles.panel}>
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
                    const pct = !sub ? 0 : sub.status_code === "ACCEPTED" ? 100 : sub.status_code === "PENDING" ? 50 : 10;
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
        {tab === "active" && activeItems.map((item) => {
          const attached = uploadedFiles[item.id];
          return (
            <article className={styles.row} key={item.id}>
              <img src={iconPath("norms")} alt="" />
              <div>
                <strong>{item.title}</strong>
                <span>{item.description ?? "описание будет добавлено"} · до {formatDate(item.deadline_at)}</span>
              </div>
              <div className={styles.fileUploadArea}>
                {attached ? (
                  <div className={styles.fileAttached}>
                    📎 {attached.name}
                    <button type="button" onClick={() => setUploadedFiles((prev) => { const next = { ...prev }; delete next[item.id]; return next; })}>✕</button>
                  </div>
                ) : (
                  <label className={styles.fileButton}>
                    📎 Прикрепить файл
                    <input
                      type="file"
                      accept="video/*,image/*,application/pdf"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleFileChange(item.id, file);
                      }}
                    />
                  </label>
                )}
                <input
                  placeholder="Комментарий к сдаче..."
                  value={comments[item.id] ?? ""}
                  onChange={(e) => setComments((prev) => ({ ...prev, [item.id]: e.target.value }))}
                  style={{ border: "1px solid #d9deea", borderRadius: 10, padding: "8px 12px", fontSize: 12, width: "100%", fontFamily: "inherit", color: "#1a2f5a" }}
                />
                <button
                  className={styles.iconAction}
                  type="button"
                  disabled={isBusy || upload.isPending}
                  onClick={() => onSubmit(item.id, comments[item.id] || undefined, attached?.id ?? null)}
                >
                  {isBusy || upload.isPending ? "Отправляем..." : "Отправить на проверку"}
                </button>
              </div>
            </article>
          );
        })}
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
        {tab === "archive" && (archiveItems.length === 0
          ? <Empty text="Архив нормативов пуст" />
          : archiveItems.map((item) => (
            <article className={styles.row} key={item.id}>
              <img src={iconPath("norms")} alt="" />
              <div>
                <strong>{item.title}</strong>
                <span>{item.description ?? "закрытый норматив"} · до {formatDate(item.deadline_at)}</span>
              </div>
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
        <span>{unread.length} новых</span>
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
            <img src={iconPath("notifications")} alt="" />
            <div>
              <strong>{item.title}</strong>
              <span>{item.body ?? item.type_code} · {formatDate(item.created_at)}</span>
            </div>
            {!item.is_read && (
              <button className={styles.iconAction} type="button" onClick={() => onRead(item.id)}>✓ Прочитано</button>
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
  onCreate,
  isSubmitting,
}: {
  items: Array<{ id: number; title: string; body: string; status_code: string }>;
  onCreate: (payload: AnnouncementPayload) => void;
  isSubmitting: boolean;
}) {
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const canSubmit = title.trim().length > 0 && body.trim().length > 0;
  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Объявления</h2>
        <span>{items.length} записей</span>
      </div>
      <div className={styles.formBlock}>
        <input placeholder="Заголовок" value={title} onChange={(e) => setTitle(e.target.value)} />
        <textarea placeholder="Текст объявления" rows={3} value={body} onChange={(e) => setBody(e.target.value)} />
        <button
          type="button"
          disabled={!canSubmit || isSubmitting}
          onClick={() => onCreate({ title, body, target_type: "SQUAD", status_code: "DRAFT", send_to_tg: true, send_to_app: true })}
        >
          {isSubmitting ? "Отправляем..." : "Отправить объявление"}
        </button>
      </div>
      <div className={styles.list}>
        {items.map((item) => (
          <article className={styles.row} key={item.id}>
            <img src={iconPath("announcements")} alt="" />
            <div>
              <strong>{item.title}</strong>
              <span>{item.status_code} · {item.body?.slice(0, 60)}</span>
            </div>
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
  });
  const canSubmit = form.subject.trim().length > 0 && form.description.trim().length > 0;
  const [openAppealId, setOpenAppealId] = useState<number | null>(null);

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
            <button type="button" disabled={!canSubmit || isSubmitting} onClick={() => onCreate(form)}>
              {isSubmitting ? "Отправляем..." : "Отправить обращение"}
            </button>
          </div>

          <div className={styles.list}>
            {items.length === 0 && <Empty text="Обращений пока нет" />}
            {items.map((item) => (
              <article className={styles.row} key={item.id} style={{ cursor: "pointer" }} onClick={() => setOpenAppealId(item.id)}>
                <img src={iconPath("appeals")} alt="" />
                <div>
                  <strong>{item.subject}</strong>
                  <span>{appealStatusLabel(item.status_code)} · {item.category_code} · {formatDate(item.created_at)}</span>
                </div>
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
  const exportReport = useExportReport();
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
            <strong>Скачать сводный отчёт CSV</strong>
            <small>Включает явку, оценки, нормативы и заявки</small>
          </div>
          <div className={styles.commandStrip}>
            <button
              type="button"
              disabled={exportReport.isPending}
              onClick={() => { exportReport.mutate(); toast("Файл формируется...", "info"); }}
            >
              {exportReport.isPending ? "Формируем..." : "⬇ Скачать CSV"}
            </button>
          </div>
        </div>
      ) : (
        <>
          {items.length === 0 ? (
            <Empty text="Данных пока нет" />
          ) : (
            <>
              {/* Bar chart */}
              <div className={styles.chartsSection}>
                <div className={styles.chartSectionTitle}>{activeReport?.title ?? "Данные"}</div>
                <BarChart
                  data={items.map((item) => {
                    const rec = item as Record<string, unknown>;
                    const key = String(rec.status_code ?? rec.grade_value ?? rec.label ?? "?");
                    return {
                      label: (statusLabelMap[key] ?? key).slice(0, 5),
                      value: extractCount(item),
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
                {items.slice(0, 4).map((item, index) => {
                  const rec = item as Record<string, unknown>;
                  const key = String(rec.status_code ?? rec.grade_value ?? rec.label ?? `#${index + 1}`);
                  return (
                    <StatNumber
                      key={index}
                      value={extractCount(item)}
                      label={statusLabelMap[key] ?? key}
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
                  items.map((item) => {
                    const rec = item as Record<string, unknown>;
                    return [String(rec.grade_value ?? "?"), extractCount(item)];
                  })
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
function LearningView({ items, courses }: { items: LearningMaterial[]; courses: LearningCourse[] }) {
  const [tab, setTab] = useState<"materials" | "courses">("materials");
  const [selectedCourseId, setSelectedCourseId] = useState<number | null>(null);
  const markViewed = useMarkMaterialViewed();
  const downloadFile = useDownloadFile();
  const visibleItems = selectedCourseId === null ? items : items.filter((item) => item.course_id === selectedCourseId);
  const selectedCourse = courses.find((course) => course.id === selectedCourseId);

  const typeLabels: Record<string, string> = {
    VIDEO: "Видео",
    TEXT: "Текст",
    NORMATIVE_CARD: "Карточка норматива",
    IMAGE: "Изображение",
    LINK: "Ссылка",
    PDF: "PDF",
    COLLECTION: "Подборка",
  };

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Материалы</h2>
        <span>{visibleItems.length} доступно</span>
      </div>
      <Tabs
        tabs={[["materials", "Материалы"], ["courses", "Курсы"]]}
        active={tab}
        onChange={(value) => setTab(value as typeof tab)}
      />
      <div className={styles.list}>
        {tab === "materials" && selectedCourse && (
          <div className={styles.commandStrip}>
            <small>{selectedCourse.title}</small>
            <button type="button" onClick={() => setSelectedCourseId(null)}>Все материалы</button>
          </div>
        )}
        {tab === "materials" && visibleItems.length === 0 && <Empty text="Материалы появятся после публикации" />}
        {tab === "materials" && visibleItems.map((item) => (
          <article className={styles.row} key={item.id} style={{ cursor: item.external_url || item.file_id ? "pointer" : "default" }}
            onClick={() => {
              if (item.external_url) {
                markViewed.mutate(item.id);
                window.open(item.external_url, "_blank");
                return;
              }
              if (item.file_id) {
                markViewed.mutate(item.id);
                downloadFile.mutate({ fileId: item.file_id, fileName: item.title });
              }
            }}
          >
            <img src={iconPath("learning")} alt="" />
            <div>
              <strong>{item.title}</strong>
              <span>{typeLabels[item.type_code] ?? item.type_code} · {item.description ?? "материал подготовки"}{item.duration_minutes ? ` · ${item.duration_minutes} мин` : ""}</span>
            </div>
            {(item.external_url || item.file_id) && (
              <span style={{ gridColumn: "1/-1", fontSize: 10, color: "#3498db" }}>
                {item.external_url ? "Открыть →" : downloadFile.isPending ? "Скачиваем..." : "Скачать файл"}
              </span>
            )}
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
              setTab("materials");
            }}
          >
            <img src={iconPath("learning")} alt="" />
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

/* ─────────── PeopleView ─────────── */
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
  const [tab, setTab] = useState<"my_squad" | "all" | "commanders" | "pending">("my_squad");
  const [search, setSearch] = useState("");

  const mySquadMembers = allUsers.filter((u) => u.squad_id === profile.squad_id && u.status_code !== "ARCHIVED");
  const allActive = allUsers.filter((u) => u.status_code !== "ARCHIVED");
  const commanders = allUsers.filter((u) =>
    ["SQUAD_COMMANDER", "DEPUTY_SQUAD_COMMANDER", "PLATOON_COMMANDER", "DEPUTY_PLATOON_COMMANDER"].includes(u.role_code)
  );
  const pending = allUsers.filter((u) => u.role_code === "USER_PENDING");

  const tabs: Array<[string, string]> = [["my_squad", "Моё отделение"], ["all", "Все"]];
  if (level >= 4) tabs.push(["commanders", "Командиры"]);
  if (level >= 6) tabs.push(["pending", "Непривязанные"]);

  const rawUsers =
    tab === "my_squad" ? mySquadMembers :
    tab === "commanders" ? commanders :
    tab === "pending" ? pending :
    allActive;

  const displayUsers = search.trim()
    ? rawUsers.filter((u) => u.full_name.toLowerCase().includes(search.toLowerCase()) || u.username?.toLowerCase().includes(search.toLowerCase()))
    : rawUsers;

  const squadMap = new Map(squads.map((s) => [s.id, s.name]));

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Состав</h2>
        <span>{tab === "my_squad" && mySquad ? mySquad.name : `${displayUsers.length} человек`}</span>
      </div>
      <Tabs tabs={tabs} active={tab} onChange={(v) => { setTab(v as typeof tab); setSearch(""); }} />

      <div className={styles.searchBar}>
        <input
          placeholder={`Поиск по ${rawUsers.length} участникам...`}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {mySquad && tab === "my_squad" && !search && (
        <div className={styles.nextItem}>
          <span>Отделение</span>
          <strong>{mySquad.name}</strong>
          <small>
            {mySquad.commander_user_id ? `Командир: ${allUsers.find((u) => u.id === mySquad.commander_user_id)?.full_name ?? "не указан"}` : "Командир не назначен"}
          </small>
        </div>
      )}

      <div className={styles.list}>
        {displayUsers.length === 0 && <Empty text="Участников в этой категории нет" />}
        {displayUsers.map((user) => (
          <div className={styles.memberRow} key={user.id ?? user.telegram_id}>
            <div>
              <strong>{user.full_name}</strong>
              <span>
                {tab === "all" && user.squad_id ? squadMap.get(user.squad_id) ?? `Отделение ${user.squad_id}` : ""}
                {user.username ? ` @${user.username}` : ""}
              </span>
            </div>
            <span className={styles.roleBadge}>{roleLabels[user.role_code as RoleCode] ?? user.role_code}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─────────── ProfileView ─────────── */
function ProfileView({
  profile,
  attendanceStats,
  submissions,
  streak,
  onAvatarUpload,
  isAvatarUploading,
}: {
  profile: UserProfile;
  attendanceStats?: ReportSummary;
  submissions: NormativeSubmission[];
  streak: StreakData;
  onAvatarUpload: (file: File) => void;
  isAvatarUploading: boolean;
}) {
  const items = attendanceStats?.items ?? [];
  const presentItem = items.find((i) => (i as Record<string, unknown>).status_code === "PRESENT");
  const absentItem = items.find((i) => (i as Record<string, unknown>).status_code === "ABSENT");
  const presentCount = extractCount(presentItem ?? 0);
  const absentCount = extractCount(absentItem ?? 0);
  const total = items.reduce((acc, i) => acc + extractCount(i), 0);
  const percent = total ? Math.round((presentCount / total) * 100) : 0;
  const accepted = submissions.filter((s) => s.status_code === "ACCEPTED").length;
  const avatar = avatarPath(profile.avatar_file_id);

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Профиль</h2>
        <span>{roleLabels[profile.role_code]}</span>
      </div>
      <div className={styles.profileCard}>
        <label className={styles.profileAvatarUpload}>
          <span className={styles.profileAvatar}>
            {avatar ? <img src={avatar} alt="" /> : profile.full_name.charAt(0).toUpperCase()}
          </span>
          <span className={styles.avatarUploadButton}>
            {isAvatarUploading ? "Загрузка..." : avatar ? "Сменить фото" : "Загрузить фото"}
          </span>
          <input
            type="file"
            accept="image/*"
            disabled={isAvatarUploading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onAvatarUpload(file);
              e.target.value = "";
            }}
          />
        </label>
        <dl>
          <div className={styles.profileRow}>
            <dt>ФИО</dt>
            <dd>{profile.full_name}</dd>
          </div>
          <div className={styles.profileRow}>
            <dt>Роль</dt>
            <dd>{roleLabels[profile.role_code]}</dd>
          </div>
          <div className={styles.profileRow}>
            <dt>Отделение</dt>
            <dd>{profile.squad_id ?? "не назначено"}</dd>
          </div>
          <div className={styles.profileRow}>
            <dt>Статус</dt>
            <dd>{profile.status_code}</dd>
          </div>
          {profile.phone && (
            <div className={styles.profileRow}>
              <dt>Телефон</dt>
              <dd>{profile.phone}</dd>
            </div>
          )}
          {profile.birth_date && (
            <div className={styles.profileRow}>
              <dt>Дата рождения</dt>
              <dd>{formatDateFull(profile.birth_date)}</dd>
            </div>
          )}
          {profile.username && (
            <div className={styles.profileRow}>
              <dt>Telegram</dt>
              <dd>@{profile.username}</dd>
            </div>
          )}
        </dl>
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
    </div>
  );
}

/* ─────────── AdminView ─────────── */
function AdminView({
  level,
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
  type AdminTab = "users" | "applications" | "promo" | "menu" | "squads" | "logs";
  const [tab, setTab] = useState<AdminTab>("users");
  const [editingPromo, setEditingPromo] = useState<PromoBlock | null | "new">(null);
  const [applicationSquads, setApplicationSquads] = useState<Record<number, string>>({});
  const [rejectReasons, setRejectReasons] = useState<Record<number, string>>({});
  const [newSquadName, setNewSquadName] = useState("");
  const [squadNames, setSquadNames] = useState<Record<number, string>>({});
  const createPromo = useCreatePromoBlock();
  const updatePromo = useUpdatePromoBlock();
  const deletePromo = useDeletePromoBlock();
  const updateUser = useUpdateUser();
  const createSquad = useCreateSquad();
  const updateSquad = useUpdateSquad();
  const updateMenu = useUpdateMenuCard();
  const squadMap = new Map(squads.map((s) => [s.id, s.name]));
  const roleOptions = Object.keys(roleLabels) as RoleCode[];
  const statusOptions = ["ACTIVE", "INACTIVE", "ARCHIVED", "BLOCKED"];
  const adminTabs: Array<[AdminTab, string, number]> = [
    ["users", "Люди", 6],
    ["applications", "Заявки", 6],
    ["squads", "Отделения", 6],
    ["promo", "Промо", 6],
    ["menu", "Меню", 6],
    ["logs", "Логи", 8],
  ];
  const visibleTabs = adminTabs.filter(([, , minLevel]) => level >= minLevel);

  useEffect(() => {
    if (!visibleTabs.some(([value]) => value === tab)) {
      setTab(visibleTabs[0]?.[0] ?? "users");
      setEditingPromo(null);
    }
  }, [level, tab, visibleTabs.length]);

  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <h2>Админка</h2>
        <span>{level >= 8 ? "полный доступ" : "командирский доступ"}</span>
      </div>
      <Tabs
        tabs={visibleTabs.map(([value, label]) => [value, label] as [string, string])}
        active={tab}
        onChange={(value) => { setTab(value as AdminTab); setEditingPromo(null); }}
      />

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
                    onSuccess: () => { toast("Промо-блок создан ✅", "success"); setEditingPromo(null); },
                    onError: () => toast("Ошибка создания", "error"),
                  });
                } else {
                  updatePromo.mutate({ id: editingPromo!.id, ...payload }, {
                    onSuccess: () => { toast("Промо-блок сохранён ✅", "success"); setEditingPromo(null); },
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
                  onDelete={(id) => deletePromo.mutate(id, {
                    onSuccess: () => toast("Блок удалён", "warning"),
                  })}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Other tabs ── */}
      {tab !== "promo" && (
        <div className={styles.list}>
          {tab === "users" && (users.length === 0 ? <Empty text="Пользователей нет" /> : users.slice(0, 50).map((user) => (
            <div className={styles.memberRow} key={user.id ?? user.telegram_id}>
              <div>
                <strong>{user.full_name}</strong>
                <span>{squadMap.get(user.squad_id ?? -1) ?? "без отделения"}{user.username ? ` · @${user.username}` : ""}</span>
              </div>
              <div className={styles.memberControls}>
                <select
                  value={user.role_code}
                  disabled={user.id === null || updateUser.isPending}
                  onChange={(event) => user.id !== null && updateUser.mutate({ userId: user.id, role_code: event.target.value })}
                >
                  {roleOptions.map((role) => (
                    <option key={role} value={role}>{roleLabels[role]}</option>
                  ))}
                </select>
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
                <select
                  value={user.status_code}
                  disabled={user.id === null || updateUser.isPending}
                  onChange={(event) => user.id !== null && updateUser.mutate({ userId: user.id, status_code: event.target.value })}
                >
                  {statusOptions.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </div>
            </div>
          )))}

          {tab === "applications" && (applications.length === 0 ? <Empty text="Заявок нет" /> : applications.slice(0, 30).map((item) => (
            <article className={styles.row} key={item.id}>
              <img src={iconPath("my_squad")} alt="" />
              <div>
                <strong>{item.full_name}</strong>
                <span>{applicationStatusLabels[item.status_code] ?? item.status_code} · {item.phone ?? "телефон не указан"}</span>
              </div>
              {!["ACCEPTED", "REJECTED", "ARCHIVED"].includes(item.status_code) && (
                <div className={styles.applicationActions}>
                  <select
                    value={applicationSquads[item.id] ?? ""}
                    disabled={isBusy}
                    onChange={(event) => setApplicationSquads((prev) => ({ ...prev, [item.id]: event.target.value }))}
                  >
                    <option value="">Без отделения</option>
                    {squads.map((squad) => (
                      <option key={squad.id} value={squad.id}>{squad.name}</option>
                    ))}
                  </select>
                  <input
                    value={rejectReasons[item.id] ?? ""}
                    disabled={isBusy}
                    placeholder="Причина отказа"
                    onChange={(event) => setRejectReasons((prev) => ({ ...prev, [item.id]: event.target.value }))}
                  />
                  <button
                    type="button"
                    className={styles.btnComing}
                    disabled={isBusy}
                    onClick={() => {
                      const squadId = applicationSquads[item.id];
                      onAccept(item.id, squadId ? Number(squadId) : null);
                    }}
                  >
                    Принять
                  </button>
                  <button
                    type="button"
                    className={styles.btnNotComing}
                    disabled={isBusy}
                    onClick={() => onReject(item.id, rejectReasons[item.id]?.trim() || undefined)}
                  >
                    Отклонить
                  </button>
                  <button type="button" className={styles.btnMaybe} disabled>
                    {applicationStatusLabels[item.status_code] ?? "—"}
                  </button>
                </div>
              )}
            </article>
          )))}

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
                        {users.filter((u) => u.squad_id === squad.id).length} участников
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
                        {squad.is_active ? "Выключить" : "Включить"}
                      </button>
                    </div>
                  </div>
                );
              })}
            </>
          )}

          {tab === "menu" && (menu.length === 0 ? <Empty text="Карточек меню нет" /> : menu.slice(0, 12).map((item) => (
            <article className={styles.row} key={item.id ?? item.code}>
              <img src={iconPath(item.icon_code ?? item.code)} alt="" />
              <div>
                <strong>{item.title}</strong>
                <span>{item.is_required ? "обязательная" : "обычная"} · {item.is_active ? "активна" : "скрыта"}</span>
              </div>
              {level >= 8 && item.id && (
                <button
                  className={styles.iconAction}
                  type="button"
                  disabled={updateMenu.isPending}
                  onClick={() => updateMenu.mutate({ id: item.id!, is_active: !item.is_active })}
                >
                  {item.is_active ? "Скрыть" : "Показать"}
                </button>
              )}
            </article>
          )))}

          {tab === "logs" && (
            audit.length === 0 ? <Empty text="Аудит-лог пуст" /> : audit.slice(0, 80).map((item) => (
              <article className={styles.row} key={item.id}>
                <img src={iconPath("admin")} alt="" />
                <div>
                  <strong>{item.action_code}</strong>
                  <span>
                    {item.entity_name ?? "entity"} #{item.entity_id ?? "—"} · user {item.user_id ?? "—"} · {formatDate(item.created_at)}
                  </span>
                </div>
              </article>
            ))
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

  useEffect(() => {
    setDraft(buildDraft());
  }, [settings.length, blocks.length]);

  const move = (index: number, direction: -1 | 1) => {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= draft.length) return;
    const next = [...draft];
    [next[index], next[newIndex]] = [next[newIndex], next[index]];
    setDraft(next.map((entry, i) => ({ ...entry, sort_order: i })));
  };

  return (
    <details className={styles.customizer}>
      <summary>Настроить главную</summary>
      <div className={styles.dragList}>
        {draft.map((item, index) => (
          <div key={item.block_code}>
            <span>{item.title}</span>
            <button
              type="button"
              className={styles.dragMoveBtn}
              disabled={index === 0}
              onClick={() => move(index, -1)}
              title="Вверх"
            >
              ▲
            </button>
            <button
              type="button"
              className={styles.dragMoveBtn}
              disabled={index === draft.length - 1}
              onClick={() => move(index, 1)}
              title="Вниз"
            >
              ▼
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
  const statusColors: Record<string, string> = {
    PENDING: "#f39c12",
    ACCEPTED: "#27ae60",
    REJECTED: "#e74c3c",
    NEEDS_REDO: "#3498db",
    OVERDUE: "#95a5a6",
  };
  const statusLabels: Record<string, string> = {
    PENDING: "На проверке",
    ACCEPTED: "Принято",
    REJECTED: "Отклонено",
    NEEDS_REDO: "Нужна пересдача",
    OVERDUE: "Просрочено",
  };
  return (
    <article className={styles.row}>
      <img src={iconPath("norms")} alt="" />
      <div>
        <strong>Сдача #{item.id}</strong>
        <span style={{ color: statusColors[item.status_code] ?? "#65708a" }}>
          {statusLabels[item.status_code] ?? item.status_code} · норматив {item.normative_id} · {formatDate(item.submitted_at)}
        </span>
        {item.reviewer_comment && <span>Комментарий: {item.reviewer_comment}</span>}
        {item.grade_value && <span>Оценка: {item.grade_value}</span>}
      </div>
      {onReview && (
        <div className={styles.actions}>
          <button type="button" className={styles.btnComing} disabled={isBusy} onClick={() => onReview(item.id, "ACCEPTED")}>Принять</button>
          <button type="button" className={styles.btnMaybe} disabled={isBusy} onClick={() => onReview(item.id, "NEEDS_REDO")}>Доработать</button>
          <button type="button" className={styles.btnNotComing} disabled={isBusy} onClick={() => onReview(item.id, "REJECTED")}>Отклонить</button>
        </div>
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
  return (
    <div className={styles.streakBadge}>
      <span className={styles.streakFire}>{current > 0 ? "🔥" : "💤"}</span>
      <div>
        <strong>
          {current > 0
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
