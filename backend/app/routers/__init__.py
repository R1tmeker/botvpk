from . import (
    announcements,
    appeals,
    attendance,
    auth,
    dashboard,
    files,
    join,
    learning,
    normatives,
    notifications,
    promo,
    public,
    reports,
    schedule,
    squads,
    submissions,
    users,
    vk,
)
from .admin import audit as admin_audit
from .admin import applications as admin_applications
from .admin import dictionaries as admin_dictionaries
from .admin import learning as admin_learning
from .admin import menu as admin_menu
from .admin import promo as admin_promo
from .admin import settings as admin_settings
from .admin import users as admin_users

API_ROUTERS = [
    auth.router,
    vk.router,
    public.router,
    join.router,
    schedule.router,
    attendance.router,
    normatives.router,
    learning.router,
    notifications.router,
    announcements.router,
    appeals.router,
    squads.router,
    users.router,
    promo.router,
    dashboard.router,
    reports.router,
    files.router,
    submissions.router,
    admin_audit.router,
    admin_settings.router,
    admin_dictionaries.router,
    admin_menu.router,
    admin_users.router,
    admin_applications.router,
    admin_promo.router,
    admin_learning.router,
]
