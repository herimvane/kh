import getpass
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.security import hash_password  # noqa: E402


def main() -> None:
    password = getpass.getpass("请输入评分详情查看密码：")
    confirmation = getpass.getpass("请再次输入：")
    if not password:
        raise SystemExit("密码不能为空。")
    if password != confirmation:
        raise SystemExit("两次输入的密码不一致。")
    print(hash_password(password))


if __name__ == "__main__":
    main()
