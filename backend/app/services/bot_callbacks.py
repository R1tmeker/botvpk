from __future__ import annotations

import re


def callback_ids(data: str | None, prefix: str, count: int) -> list[int] | None:
    parts = (data or "").split(":")
    if len(parts) != count + 1 or parts[0] != prefix:
        return None
    if any(re.fullmatch(r"[0-9]{1,10}", part) is None for part in parts[1:]):
        return None
    values = [int(part) for part in parts[1:]]
    return values if all(0 < value <= 2_147_483_647 for value in values) else None
