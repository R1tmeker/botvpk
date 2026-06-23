from __future__ import annotations

import logging

from ..config import Settings

logger = logging.getLogger(__name__)


def init_sentry(settings: Settings, *, service_name: str) -> None:
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logger.warning("SENTRY_DSN is set, but sentry-sdk is not installed")
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.release_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=0.0,
        send_default_pii=False,
        server_name=service_name,
    )
