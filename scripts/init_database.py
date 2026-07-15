import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import select


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import (  # noqa: E402
    DATABASE_BACKEND,
    check_database_connection,
    database_display_url,
    init_db,
    migrate_db,
    session_scope,
)
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize the configured SQLite, MySQL, or PostgreSQL database."
    )
    parser.add_argument("--check-only", action="store_true", help="Only verify the configured database connection.")
    parser.add_argument("--skip-admin", action="store_true", help="Create tables without creating an administrator.")
    parser.add_argument(
        "--preserve-existing-admin",
        action="store_true",
        help="Create the administrator only when the username does not already exist.",
    )
    parser.add_argument("--admin-username", default=os.getenv("INITIAL_ADMIN_USERNAME", "admin"))
    parser.add_argument("--admin-name", default=os.getenv("INITIAL_ADMIN_NAME", "系统管理员"))
    parser.add_argument("--admin-password", default=os.getenv("INITIAL_ADMIN_PASSWORD", "password!"))
    args = parser.parse_args()

    print(f"Database backend: {DATABASE_BACKEND}")
    print(f"Database URL: {database_display_url()}")
    check_database_connection()
    print("Database connection: OK")
    if args.check_only:
        return

    migrate_db()
    init_db()
    print("Database schema: ready")
    if args.skip_admin:
        return
    if not args.admin_password:
        parser.error("--admin-password is required unless --skip-admin is used.")

    with session_scope() as db:
        user = db.scalar(select(User).where(User.username == args.admin_username))
        if user:
            if args.preserve_existing_admin:
                action = "preserved"
            else:
                user.full_name = args.admin_name
                user.password_hash = hash_password(args.admin_password)
                user.role = "admin"
                user.is_active = True
                user.must_change_password = True
                action = "updated"
        else:
            db.add(
                User(
                    username=args.admin_username,
                    full_name=args.admin_name,
                    password_hash=hash_password(args.admin_password),
                    role="admin",
                    is_active=True,
                    must_change_password=True,
                )
            )
            action = "created"
    print(f"Administrator {action}: {args.admin_username}")


if __name__ == "__main__":
    main()
