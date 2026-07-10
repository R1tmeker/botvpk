from __future__ import annotations

import asyncio

from sqlalchemy import select

from ..config import get_settings
from ..database import AsyncSessionLocal
from ..models import User
from ..services.totp_secrets import encrypt_totp_secret


async def run() -> int:
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        users = list(
            (
                await session.scalars(
                    select(User).where(
                        User.totp_secret.is_not(None),
                        User.totp_secret_encrypted.is_(None),
                    )
                )
            ).all()
        )
        for user in users:
            user.totp_secret_encrypted = encrypt_totp_secret(
                user.totp_secret or "",
                settings.effective_totp_encryption_key,
            )
            user.totp_secret = None
        await session.commit()
        return len(users)


def main() -> None:
    count = asyncio.run(run())
    print(f"Encrypted {count} TOTP secret(s).")


if __name__ == "__main__":
    main()
