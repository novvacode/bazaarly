"""Create or promote a platform admin (SPEC §23 runbook).

    python -m scripts.create_admin --email you@example.com --name "Your Name"

The password is read from $ADMIN_PASSWORD or prompted for (never passed on the command line).
An existing user keeps their password and is just promoted.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os

from app.core.security import hash_password, password_problem
from app.db import dispose_engine, get_sessionmaker
from app.repositories import users as user_repo


async def create_admin(email: str, name: str, password: str | None) -> str:
    async with get_sessionmaker()() as session:
        user = await user_repo.get_by_email(session, email)
        if user is None:
            if not password:
                raise SystemExit("A password is required to create a new user.")
            if problem := password_problem(password):
                raise SystemExit(problem)
            user = await user_repo.create(
                session, email=email, name=name, password_hash=hash_password(password)
            )
            outcome = "created"
        else:
            outcome = "promoted"
        user.is_platform_admin = True
        await session.commit()
    return outcome


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default="Platform Admin")
    args = parser.parse_args()
    password = os.environ.get("ADMIN_PASSWORD")
    if password is None and os.isatty(0):
        password = getpass.getpass("Password for new admin (leave empty if the user exists): ")
    try:
        outcome = await create_admin(args.email.strip().lower(), args.name, password or None)
    finally:
        await dispose_engine()
    print(f"Admin {outcome}: {args.email}")


if __name__ == "__main__":
    asyncio.run(main())
