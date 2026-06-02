from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

from app.utils.telegram_auth import validate_init_data


def main() -> None:
    bot_token = "123456:test-token"
    params = {
        "auth_date": str(int(time.time())),
        "query_id": "AAEAAAE",
        "signature": "telegram-ed25519-signature-placeholder",
        "user": json.dumps(
            {"id": 795307805, "first_name": "Test", "username": "tester"},
            separators=(",", ":"),
        ),
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    parsed = validate_init_data(urlencode(params), bot_token, max_age_seconds=0)
    assert parsed.user.telegram_id == 795307805
    print("ok")


if __name__ == "__main__":
    main()
