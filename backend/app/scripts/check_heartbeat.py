from __future__ import annotations

import sys

from ..services.heartbeat import heartbeat_is_fresh


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m app.scripts.check_heartbeat PATH [MAX_AGE_SECONDS]")
    max_age = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
    raise SystemExit(0 if heartbeat_is_fresh(sys.argv[1], max_age_seconds=max_age) else 1)


if __name__ == "__main__":
    main()
