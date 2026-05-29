from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    detail: str


class UserRead(ORMModel):
    id: int
    telegram_id: int | None = None
    username: str | None = None
    full_name: str
    squad_id: int | None = None
    avatar_file_id: int | None = None
    role_code: str
    status_code: str
    birth_date: date | None = None
    phone: str | None = None
    linked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class UserCreate(BaseModel):
    telegram_id: int | None = None
    username: str | None = None
    full_name: str = Field(min_length=2, max_length=255)
    squad_id: int | None = None
    avatar_file_id: int | None = None
    role_code: str = "USER_PENDING"
    status_code: str = "ACTIVE"
    birth_date: date | None = None
    phone: str | None = None


class UserUpdate(BaseModel):
    telegram_id: int | None = None
    username: str | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    squad_id: int | None = None
    avatar_file_id: int | None = None
    role_code: str | None = None
    status_code: str | None = None
    birth_date: date | None = None
    phone: str | None = None


class SquadRead(ORMModel):
    id: int
    name: str
    commander_user_id: int | None = None
    deputy_user_id: int | None = None
    is_active: bool
    created_at: datetime


class SquadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    commander_user_id: int | None = None
    deputy_user_id: int | None = None
    is_active: bool = True


class SquadUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    commander_user_id: int | None = None
    deputy_user_id: int | None = None
    is_active: bool | None = None


class JoinApplicationRead(ORMModel):
    id: int
    telegram_id: int
    username: str | None = None
    full_name: str
    birth_date: date | None = None
    phone: str | None = None
    city: str | None = None
    education_place: str | None = None
    experience_text: str | None = None
    motivation_text: str | None = None
    source_text: str | None = None
    consent_given: bool
    comment: str | None = None
    status_code: str
    admin_comment: str | None = None
    decision_reason: str | None = None
    reviewed_by_user_id: int | None = None
    reviewed_at: datetime | None = None
    accepted_user_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class JoinApplicationCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    birth_date: date | None = None
    phone: str | None = None
    city: str | None = None
    education_place: str | None = None
    experience_text: str | None = None
    motivation_text: str | None = None
    source_text: str | None = None
    consent_given: bool
    comment: str | None = None


class JoinApplicationUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    birth_date: date | None = None
    phone: str | None = None
    city: str | None = None
    education_place: str | None = None
    experience_text: str | None = None
    motivation_text: str | None = None
    source_text: str | None = None
    consent_given: bool | None = None
    comment: str | None = None


class ApplicationAdminUpdate(BaseModel):
    status_code: str | None = None
    admin_comment: str | None = None
    decision_reason: str | None = None


class ApplicationAcceptRequest(BaseModel):
    squad_id: int | None = None
    role_code: str = "PARTICIPANT"
    admin_comment: str | None = None


class CandidateEventRead(ORMModel):
    id: int
    title: str
    description: str | None = None
    event_type_code: str
    start_datetime: datetime
    end_datetime: datetime | None = None
    place: str | None = None
    capacity: int | None = None
    is_active: bool
    created_by_user_id: int
    created_at: datetime


class CandidateEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    event_type_code: str = "GENERAL"
    start_datetime: datetime
    end_datetime: datetime | None = None
    place: str | None = None
    capacity: int | None = None
    is_active: bool = True


class CandidateEventResponseCreate(BaseModel):
    response_code: str
    comment: str | None = None


class ScheduleEventRead(ORMModel):
    id: int
    template_id: int | None = None
    event_type_code: str
    title: str
    description: str | None = None
    start_datetime: datetime
    end_datetime: datetime | None = None
    place: str | None = None
    squad_id: int | None = None
    status_code: str
    requires_response: bool
    is_overridden: bool = False
    response_deadline_at: datetime | None = None
    grading_type: str
    file_id: int | None = None
    my_response_code: str | None = None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime | None = None


class ScheduleEventCreate(BaseModel):
    event_type_code: str = "CLASS"
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    start_datetime: datetime
    end_datetime: datetime | None = None
    place: str | None = None
    squad_id: int | None = None
    status_code: str = "PLANNED"
    requires_response: bool = True
    response_deadline_at: datetime | None = None
    grading_type: str = "FIVE_POINT"
    file_id: int | None = None


class ScheduleEventUpdate(BaseModel):
    event_type_code: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    place: str | None = None
    squad_id: int | None = None
    status_code: str | None = None
    requires_response: bool | None = None
    response_deadline_at: datetime | None = None
    grading_type: str | None = None
    file_id: int | None = None


class EventResponseCreate(BaseModel):
    response_code: str
    absence_reason_id: int | None = None
    custom_reason: str | None = None


class ScheduleTemplateRead(ORMModel):
    id: int
    title: str
    description: str | None = None
    week_days: str
    week_parity: str | None = None
    start_time: time
    end_time: time | None = None
    place: str | None = None
    squad_id: int | None = None
    requires_response: bool
    response_deadline_minutes: int | None = None
    reminder_minutes: list[int] | None = None
    is_active: bool
    valid_from: date | None = None
    valid_to: date | None = None
    created_by_user_id: int
    created_at: datetime


class ScheduleTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    week_days: str
    week_parity: str | None = Field(default=None, pattern="^(A|B)$")
    start_time: time
    end_time: time | None = None
    place: str | None = None
    squad_id: int | None = None
    requires_response: bool = True
    response_deadline_minutes: int | None = None
    reminder_minutes: list[int] | None = None
    is_active: bool = True
    valid_from: date | None = None
    valid_to: date | None = None


class ScheduleTemplateUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    week_days: str | None = None
    week_parity: str | None = Field(default=None, pattern="^(A|B)$")
    start_time: time | None = None
    end_time: time | None = None
    place: str | None = None
    squad_id: int | None = None
    requires_response: bool | None = None
    response_deadline_minutes: int | None = None
    reminder_minutes: list[int] | None = None
    is_active: bool | None = None
    valid_from: date | None = None
    valid_to: date | None = None


class AttendanceRead(ORMModel):
    id: int
    event_id: int
    user_id: int
    status_code: str
    absence_reason_id: int | None = None
    custom_reason: str | None = None
    marked_by_user_id: int | None = None
    marked_at: datetime | None = None
    is_draft: bool
    updated_at: datetime | None = None


class AttendanceMarkItem(BaseModel):
    user_id: int
    status_code: str
    absence_reason_id: int | None = None
    custom_reason: str | None = None
    comment: str | None = None
    is_draft: bool = False


class AttendanceMarkRequest(BaseModel):
    items: list[AttendanceMarkItem]


class AttendanceUpdate(BaseModel):
    status_code: str | None = None
    absence_reason_id: int | None = None
    custom_reason: str | None = None
    is_draft: bool | None = None
    change_reason: str | None = None


class AttendanceGradeRead(ORMModel):
    id: int
    attendance_id: int
    grade_value: str | None = None
    comment: str | None = None
    set_by_user_id: int
    set_at: datetime
    updated_at: datetime | None = None


class AttendanceGradeUpdate(BaseModel):
    grade_value: str | None = None
    comment: str | None = None
    change_reason: str


class NormativeRead(ORMModel):
    id: int
    title: str
    description: str | None = None
    type_code: str
    deadline_at: datetime | None = None
    target_audience: str
    squad_id: int | None = None
    file_id: int | None = None
    is_active: bool
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime | None = None


class NormativeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    type_code: str = "GENERAL"
    deadline_at: datetime | None = None
    target_audience: str = "ALL"
    squad_id: int | None = None
    file_id: int | None = None
    is_active: bool = True


class NormativeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    type_code: str | None = None
    deadline_at: datetime | None = None
    target_audience: str | None = None
    squad_id: int | None = None
    file_id: int | None = None
    is_active: bool | None = None


class NormativeSubmissionRead(ORMModel):
    id: int
    normative_id: int
    user_id: int
    status_code: str
    file_id: int | None = None
    comment: str | None = None
    reviewer_comment: str | None = None
    grade_value: str | None = None
    reviewed_by_id: int | None = None
    reviewed_at: datetime | None = None
    submitted_at: datetime
    updated_at: datetime | None = None


class NormativeSubmitRequest(BaseModel):
    file_id: int | None = None
    comment: str | None = None


class NormativeReviewRequest(BaseModel):
    status_code: str
    reviewer_comment: str | None = None
    grade_value: str | None = None


class NotificationRead(ORMModel):
    id: int
    user_id: int
    type_code: str
    title: str
    body: str | None = None
    entity_name: str | None = None
    entity_id: int | None = None
    is_read: bool
    is_pinned: bool
    send_to_tg: bool
    tg_sent_at: datetime | None = None
    read_at: datetime | None = None
    created_at: datetime


class AnnouncementRead(ORMModel):
    id: int
    title: str
    body: str
    importance_code: str
    target_type: str
    target_squad_id: int | None = None
    target_role_code: str | None = None
    file_id: int | None = None
    send_to_tg: bool
    send_to_app: bool
    require_read_confirm: bool
    status_code: str
    scheduled_at: datetime | None = None
    sent_at: datetime | None = None
    created_by_id: int
    created_at: datetime


class AnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    importance_code: str = "NORMAL"
    target_type: str = "ALL"
    target_squad_id: int | None = None
    target_role_code: str | None = None
    file_id: int | None = None
    send_to_tg: bool = True
    send_to_app: bool = True
    require_read_confirm: bool = False
    status_code: str = "DRAFT"
    scheduled_at: datetime | None = None


class AnnouncementUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = None
    importance_code: str | None = None
    target_type: str | None = None
    target_squad_id: int | None = None
    target_role_code: str | None = None
    file_id: int | None = None
    send_to_tg: bool | None = None
    send_to_app: bool | None = None
    require_read_confirm: bool | None = None
    status_code: str | None = None
    scheduled_at: datetime | None = None


class AppealRead(ORMModel):
    id: int
    author_user_id: int
    is_anonymous: bool
    subject: str
    category_code: str
    description: str
    urgency_code: str
    file_id: int | None = None
    assignee_user_id: int | None = None
    status_code: str
    resolution_text: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    closed_at: datetime | None = None


class AppealCreate(BaseModel):
    is_anonymous: bool = False
    subject: str = Field(min_length=1, max_length=255)
    category_code: str = "OTHER"
    description: str = Field(min_length=1)
    urgency_code: str = "NORMAL"
    file_id: int | None = None


class AppealUpdate(BaseModel):
    assignee_user_id: int | None = None
    status_code: str | None = None
    resolution_text: str | None = None


class AppealMessageRead(ORMModel):
    id: int
    appeal_id: int
    author_id: int | None = None
    body: str
    created_at: datetime


class AppealMessageCreate(BaseModel):
    body: str = Field(min_length=1)


class LearningCourseRead(ORMModel):
    id: int
    title: str
    description: str | None = None
    audience_code: str
    sort_order: int
    is_active: bool
    created_at: datetime


class LearningMaterialRead(ORMModel):
    id: int
    course_id: int | None = None
    title: str
    description: str | None = None
    type_code: str
    file_id: int | None = None
    external_url: str | None = None
    duration_minutes: int | None = None
    sort_order: int
    audience_code: str
    is_active: bool
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class LearningCourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    audience_code: str = "ALL"
    sort_order: int = 0
    is_active: bool = True


class LearningCourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    audience_code: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class LearningMaterialCreate(BaseModel):
    course_id: int | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    type_code: str = "TEXT"
    file_id: int | None = None
    external_url: str | None = None
    duration_minutes: int | None = None
    sort_order: int = 0
    audience_code: str = "ALL"
    is_active: bool = True
    published_at: datetime | None = None


class LearningMaterialUpdate(BaseModel):
    course_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    type_code: str | None = None
    file_id: int | None = None
    external_url: str | None = None
    duration_minutes: int | None = None
    sort_order: int | None = None
    audience_code: str | None = None
    is_active: bool | None = None
    published_at: datetime | None = None


class PromoBlockRead(ORMModel):
    id: int
    title: str
    body: str | None = None
    image_file_id: int | None = None
    button_text: str | None = None
    button_url: str | None = None
    action_type_code: str | None = None
    audience_code: str
    style_code: str
    sort_order: int
    is_active: bool
    active_from: datetime | None = None
    active_to: datetime | None = None
    created_by_id: int
    created_at: datetime
    updated_at: datetime | None = None


class PromoBlockCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    body: str | None = None
    image_file_id: int | None = None
    button_text: str | None = None
    button_url: str | None = None
    action_type_code: str | None = None
    audience_code: str = "ALL"
    style_code: str = "DEFAULT"
    sort_order: int = 0
    is_active: bool = True
    active_from: datetime | None = None
    active_to: datetime | None = None


class PromoBlockUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = None
    image_file_id: int | None = None
    button_text: str | None = None
    button_url: str | None = None
    action_type_code: str | None = None
    audience_code: str | None = None
    style_code: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    active_from: datetime | None = None
    active_to: datetime | None = None


class MenuCardRead(ORMModel):
    id: int
    code: str
    title: str
    description: str | None = None
    icon_code: str | None = None
    color_code: str
    route: str | None = None
    roles_json: Any = None
    sort_order: int
    is_required: bool
    is_active: bool
    show_badge: bool
    created_at: datetime
    updated_at: datetime | None = None


class MenuCardCreate(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    icon_code: str | None = None
    color_code: str = "DEFAULT"
    route: str | None = None
    roles_json: Any = None
    sort_order: int = 0
    is_required: bool = False
    is_active: bool = True
    show_badge: bool = False


class MenuCardUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=100)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    icon_code: str | None = None
    color_code: str | None = None
    route: str | None = None
    roles_json: Any = None
    sort_order: int | None = None
    is_required: bool | None = None
    is_active: bool | None = None
    show_badge: bool | None = None


class DashboardSettingRead(ORMModel):
    id: int
    user_id: int
    block_code: str
    sort_order: int
    is_hidden: bool
    is_pinned: bool
    view_mode_code: str | None = None
    updated_at: datetime


class DashboardSettingItem(BaseModel):
    block_code: str = Field(min_length=1, max_length=100)
    sort_order: int = 0
    is_hidden: bool = False
    is_pinned: bool = False
    view_mode_code: str | None = None


class DashboardSettingsUpdate(BaseModel):
    items: list[DashboardSettingItem]


class SettingRead(ORMModel):
    id: int
    key: str
    value: str | None = None
    description: str | None = None
    updated_by_id: int | None = None
    updated_at: datetime


class SettingsPatch(BaseModel):
    values: dict[str, str | None]


class AbsenceReasonRead(ORMModel):
    id: int
    code: str
    label: str
    requires_comment: bool
    sort_order: int
    is_active: bool


class AbsenceReasonUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=255)
    requires_comment: bool | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class FileRead(ORMModel):
    id: int
    telegram_file_id: str | None = None
    file_path: str | None = None
    original_name: str | None = None
    mime_type: str | None = None
    size_bytes: int | None = None
    uploaded_by_id: int | None = None
    created_at: datetime


class ReportSummary(BaseModel):
    title: str
    items: list[dict[str, Any]]
