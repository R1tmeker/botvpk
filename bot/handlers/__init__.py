"""Routers grouped by access level and functionality."""

from . import (
    common,
    link,
    roster,
    admin_polls,
    admin_roster,
    admin_broadcast,
    super_admin,
)

ALL_ROUTERS = [
    common.router,
    link.router,
    roster.router,
    admin_polls.router,
    admin_roster.router,
    admin_broadcast.router,
    super_admin.router,
]

