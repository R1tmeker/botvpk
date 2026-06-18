from .application import ApplicationStatusHistory, CandidateEvent, CandidateEventResponse, JoinApplication
from .attendance import Attendance, AttendanceGrade, AttendanceHistory
from .audit import AuditLog
from .channel_link import ChannelLinkCode
from .file import File
from .learning import LearningCourse, LearningMaterial, LearningProgress
from .normative import Normative, NormativeSubmission, NormativeSubmissionFile, NormativeTarget
from .notification import Notification
from .announcement import Announcement
from .appeal import Appeal, AppealMessage
from .promo import MenuCard, PromoBlock, UserDashboardSetting
from .schedule import AbsenceReason, EventRecipient, EventResponse, ScheduleEvent, ScheduleTemplate
from .settings import BotChat, Setting
from .squad import Squad
from .user import User

__all__ = [
    "AbsenceReason",
    "Announcement",
    "Appeal",
    "AppealMessage",
    "ApplicationStatusHistory",
    "Attendance",
    "AttendanceGrade",
    "AttendanceHistory",
    "AuditLog",
    "BotChat",
    "ChannelLinkCode",
    "CandidateEvent",
    "CandidateEventResponse",
    "EventRecipient",
    "EventResponse",
    "File",
    "JoinApplication",
    "LearningCourse",
    "LearningMaterial",
    "LearningProgress",
    "MenuCard",
    "Normative",
    "NormativeSubmission",
    "NormativeSubmissionFile",
    "NormativeTarget",
    "Notification",
    "PromoBlock",
    "ScheduleEvent",
    "ScheduleTemplate",
    "Setting",
    "Squad",
    "User",
    "UserDashboardSetting",
]
