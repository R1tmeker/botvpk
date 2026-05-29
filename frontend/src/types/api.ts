export type RoleCode =
  | "PUBLIC_USER"
  | "CANDIDATE"
  | "USER_PENDING"
  | "PARTICIPANT"
  | "DEPUTY_SQUAD_COMMANDER"
  | "SQUAD_COMMANDER"
  | "DEPUTY_PLATOON_COMMANDER"
  | "PLATOON_COMMANDER"
  | "ADMIN"
  | "SUPER_ADMIN";

export type UserProfile = {
  id: number | null;
  telegram_id: number;
  username: string | null;
  full_name: string;
  squad_id: number | null;
  avatar_file_id: number | null;
  role_code: RoleCode;
  status_code: string;
  birth_date: string | null;
  phone: string | null;
};

export type UserRecord = UserProfile & {
  linked_at: string | null;
  created_at: string;
  updated_at: string | null;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  profile: UserProfile;
  app_timezone: string;
};

export type MenuCard = {
  id?: number;
  code: string;
  title: string;
  description: string | null;
  icon_code: string | null;
  color_code: string;
  route: string | null;
  sort_order: number;
  is_required: boolean;
  is_active?: boolean;
  show_badge: boolean;
};

export type ScheduleEvent = {
  id: number;
  template_id: number | null;
  event_type_code: string;
  title: string;
  description: string | null;
  start_datetime: string;
  end_datetime: string | null;
  place: string | null;
  squad_id: number | null;
  status_code: string;
  requires_response: boolean;
  is_overridden: boolean;
  response_deadline_at: string | null;
  grading_type: string;
  file_id: number | null;
  created_by_user_id: number;
  created_at: string;
  updated_at: string | null;
  my_response_code?: string | null;
};

export type ScheduleTemplate = {
  id: number;
  title: string;
  description: string | null;
  week_days: string;
  week_parity: "A" | "B" | null;
  start_time: string;
  end_time: string | null;
  place: string | null;
  squad_id: number | null;
  requires_response: boolean;
  response_deadline_minutes: number | null;
  reminder_minutes: number[] | null;
  is_active: boolean;
  valid_from: string | null;
  valid_to: string | null;
  created_by_user_id: number;
  created_at: string;
};

export type CandidateEvent = {
  id: number;
  title: string;
  description: string | null;
  event_type_code: string;
  start_datetime: string;
  end_datetime: string | null;
  place: string | null;
  capacity: number | null;
  is_active: boolean;
  created_by_user_id: number;
  created_at: string;
};

export type JoinApplication = {
  id: number;
  telegram_id: number;
  username: string | null;
  full_name: string;
  birth_date: string | null;
  phone: string | null;
  city: string | null;
  education_place: string | null;
  experience_text: string | null;
  motivation_text: string | null;
  source_text: string | null;
  consent_given: boolean;
  comment: string | null;
  status_code: string;
  admin_comment: string | null;
  decision_reason: string | null;
  reviewed_by_user_id: number | null;
  reviewed_at: string | null;
  accepted_user_id: number | null;
  created_at: string;
  updated_at: string | null;
};

export type AttendanceRecord = {
  id: number;
  event_id: number;
  user_id: number;
  status_code: string;
  custom_reason: string | null;
  marked_at: string | null;
  updated_at: string | null;
};

export type AttendanceGrade = {
  id: number;
  attendance_id: number;
  grade_value: string | null;
  comment: string | null;
  set_by_user_id: number;
  set_at: string;
  updated_at: string | null;
};

export type Normative = {
  id: number;
  title: string;
  description: string | null;
  deadline_at: string | null;
  type_code: string;
  target_audience: string;
  squad_id: number | null;
  is_active: boolean;
};

export type Notification = {
  id: number;
  title: string;
  body: string | null;
  type_code: string;
  is_read: boolean;
  is_pinned: boolean;
  created_at: string;
};

export type NormativeSubmission = {
  id: number;
  normative_id: number;
  user_id: number;
  status_code: string;
  file_id: number | null;
  comment: string | null;
  reviewer_comment: string | null;
  grade_value: string | null;
  reviewed_by_id: number | null;
  reviewed_at: string | null;
  submitted_at: string;
  updated_at: string | null;
};

export type Announcement = {
  id: number;
  title: string;
  body: string;
  importance_code: string;
  status_code: string;
  created_at: string;
};

export type LearningMaterial = {
  id: number;
  course_id: number | null;
  title: string;
  description: string | null;
  type_code: string;
  file_id: number | null;
  external_url: string | null;
  duration_minutes: number | null;
  audience_code: string;
  is_active: boolean;
};

export type LearningCourse = {
  id: number;
  title: string;
  description: string | null;
  audience_code: string;
  sort_order: number;
  is_active: boolean;
  created_at: string;
};

export type Appeal = {
  id: number;
  author_user_id: number | null;
  is_anonymous: boolean;
  subject: string;
  category_code: string;
  description: string;
  urgency_code: string;
  status_code: string;
  resolution_text: string | null;
  assignee_user_id: number | null;
  created_at: string;
  updated_at: string | null;
  closed_at: string | null;
};

export type AppealMessage = {
  id: number;
  appeal_id: number;
  author_id: number | null;
  body: string;
  created_at: string;
};

export type ReportSummary = {
  title: string;
  items: Array<Record<string, string | number | boolean | null | unknown[] | Record<string, unknown>>>;
};

export type PromoBlock = {
  id: number;
  title: string;
  body: string | null;
  image_file_id: number | null;
  button_text: string | null;
  button_url: string | null;
  action_type_code: string | null;
  audience_code: string;
  style_code: string;
  sort_order: number;
  is_active: boolean;
  active_from: string | null;
  active_to: string | null;
  created_by_id: number;
  created_at: string;
  updated_at: string | null;
};

export type PublicContent = {
  title: string;
  description: string;
  promo_blocks: PromoBlock[];
  courses: LearningCourse[];
  materials: LearningMaterial[];
};

export type DashboardSetting = {
  id: number;
  user_id: number;
  block_code: string;
  sort_order: number;
  is_hidden: boolean;
  is_pinned: boolean;
  view_mode_code: string | null;
  updated_at: string;
};

export type Squad = {
  id: number;
  name: string;
  commander_user_id: number | null;
  deputy_user_id: number | null;
  is_active: boolean;
  created_at: string;
};

export type AuditLog = {
  id: number;
  user_id: number | null;
  action_code: string;
  entity_name: string | null;
  entity_id: number | null;
  old_value: unknown;
  new_value: unknown;
  comment: string | null;
  created_at: string;
};
