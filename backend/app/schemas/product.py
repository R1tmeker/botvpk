from __future__ import annotations

from datetime import datetime, time
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator

from .core import DashboardSettingRead, PromoBlockRead


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ActionItem(BaseModel):
    code: str
    title: str
    description: str
    severity: Literal["info", "warning", "critical"]
    count: int = Field(ge=1)
    due_at: datetime | None = None
    deep_link: str
    bulk_actions: list[str] = Field(default_factory=list)


class DashboardBootstrap(BaseModel):
    settings: list[DashboardSettingRead]
    promo: list[PromoBlockRead]
    action_items: list[ActionItem]


class CheckInWindow(BaseModel):
    opens_at: datetime
    closes_at: datetime
    late_at: datetime
    server_now: datetime
    state: Literal["disabled", "not_open", "open", "closed", "cancelled"]


class NotificationPreference(BaseModel):
    category_code: str
    telegram_enabled: bool = True
    vk_enabled: bool = True
    web_push_enabled: bool = False
    in_app_enabled: bool = True
    quiet_hours_enabled: bool = False
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    @model_validator(mode="after")
    def validate_quiet_hours(self):
        if self.quiet_hours_enabled and (self.quiet_hours_start is None or self.quiet_hours_end is None):
            raise ValueError("quiet_hours_start and quiet_hours_end are required when quiet hours are enabled")
        return self


class NotificationPreferencesUpdate(BaseModel):
    items: list[NotificationPreference]


class CalendarSubscription(BaseModel):
    url: str
    created_at: datetime


class SearchResult(BaseModel):
    type: Literal["person", "event", "normative", "material", "appeal"]
    id: int
    title: str
    description: str | None = None
    deep_link: str


class AchievementProgress(BaseModel):
    code: str
    title: str
    current_value: int
    target_value: int
    unlocked_at: datetime | None = None
    is_public: bool = False


class ProgressPeriod(BaseModel):
    period: str
    attended: int = 0
    total: int = 0
    normatives_accepted: int = 0


class UserProgress(BaseModel):
    attendance_percent: int
    attendance_total: int
    normatives_accepted: int
    current_streak: int
    periods: list[ProgressPeriod]
    achievements: list[AchievementProgress]


class ImportRowIssue(BaseModel):
    row: int
    message: str


class ImportChange(BaseModel):
    row: int
    action: Literal["CREATE", "UPDATE", "UNCHANGED"]
    identity: str
    before: dict | None = None
    after: dict


class ImportPreview(BaseModel):
    preview_id: str
    total_rows: int
    create_count: int
    update_count: int
    unchanged_count: int
    errors: list[ImportRowIssue]
    changes: list[ImportChange]
    expires_at: datetime


class ImportCommitResult(BaseModel):
    created: int
    updated: int
    audit_batch_id: int


class AuditUndoResult(BaseModel):
    audit_id: int
    undo_audit_id: int
    affected: int
    detail: str


class AdminUsersBulkUpdate(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=500)
    role_code: str | None = None
    squad_id: int | None = None
    status_code: str | None = None
    telegram_enabled: bool | None = None
    vk_enabled: bool | None = None
    web_push_enabled: bool | None = None
    in_app_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        changes = self.model_dump(exclude={"user_ids"}, exclude_none=True)
        if not changes:
            raise ValueError("At least one bulk change is required")
        if len(self.user_ids) != len(set(self.user_ids)):
            raise ValueError("Duplicate user_ids are not allowed")
        return self


class AdminUsersBulkResult(BaseModel):
    affected: int
    audit_batch_id: int
