import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, session_scope
from app.models import User
from app.security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update the system administrator.")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--name", default="系统管理员")
    args = parser.parse_args()

    init_db()
    with session_scope() as db:
        user = db.query(User).filter(User.username == args.username).first()
        if user:
            user.full_name = args.name
            user.password_hash = hash_password(args.password)
            user.role = "admin"
            user.is_active = True
            print(f"Updated administrator: {args.username}")
        else:
            db.add(
                User(
                    username=args.username,
                    full_name=args.name,
                    password_hash=hash_password(args.password),
                    role="admin",
                    is_active=True,
                )
            )
            print(f"Created administrator: {args.username}")


if __name__ == "__main__":
    main()
