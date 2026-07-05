import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import init_db, SessionLocal
from app.models import Department, Position, User
from app.security import hash_password


UNIT_NAME = "毕节金融监管分局"
DEFAULT_PASSWORD = "123456"

DEPARTMENTS = [
    "办公室",
    "政策法规科",
    "统计信息与风险监测科",
    "银行机构监管科",
    "非银行机构监管科",
    "保险机构监管科",
    "普惠金融科",
    "消费者权益保护科",
    "人事教育科",
    "纪检监察室",
]

REQUIRED_POSITIONS = {
    "director": "局长",
    "leader": "其他局领导",
    "department_head": "部门主要负责人",
    "cadre": "其他干部",
}


def get_position_map(db):
    positions = {position.name: position for position in db.query(Position).all()}
    missing = [name for name in REQUIRED_POSITIONS.values() if name not in positions]
    if missing:
        raise RuntimeError("缺少职位数据：" + "、".join(missing))
    return {key: positions[name] for key, name in REQUIRED_POSITIONS.items()}


def get_or_create_department(db, name, parent=None):
    department = db.query(Department).filter(Department.name == name).first()
    if department is None:
        department = Department(name=name)
        db.add(department)
        db.flush()
    department.parent_id = parent.id if parent else None
    return department


def upsert_user(db, username, full_name, position, department):
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        user = User(
            username=username,
            full_name=full_name,
            password_hash=hash_password(DEFAULT_PASSWORD),
            role="user",
            is_active=True,
        )
        db.add(user)
    user.full_name = full_name
    user.role = "user"
    user.is_active = True
    user.department_id = department.id
    user.position_id = position.id
    return user


def main():
    init_db()
    db = SessionLocal()
    try:
        positions = get_position_map(db)
        unit = get_or_create_department(db, UNIT_NAME)
        child_departments = [get_or_create_department(db, name, unit) for name in DEPARTMENTS]

        upsert_user(db, "jz001", "测试局长", positions["director"], unit)

        for index in range(1, 5):
            upsert_user(
                db,
                f"ld{index:02d}",
                f"测试局领导{index}",
                positions["leader"],
                unit,
            )

        for dept_index, department in enumerate(child_departments, start=1):
            upsert_user(
                db,
                f"fzr{dept_index:02d}",
                f"{department.name}负责人",
                positions["department_head"],
                department,
            )
            for cadre_index in range(1, 4):
                upsert_user(
                    db,
                    f"gb{dept_index:02d}{cadre_index:02d}",
                    f"{department.name}干部{cadre_index}",
                    positions["cadre"],
                    department,
                )

        db.commit()

        unit_count = db.query(Department).filter(Department.name == UNIT_NAME).count()
        child_count = db.query(Department).filter(Department.parent_id == unit.id).count()
        test_user_count = (
            db.query(User)
            .filter(
                User.username.in_(
                    ["jz001"]
                    + [f"ld{i:02d}" for i in range(1, 5)]
                    + [f"fzr{i:02d}" for i in range(1, 11)]
                    + [f"gb{i:02d}{j:02d}" for i in range(1, 11) for j in range(1, 4)]
                )
            )
            .count()
        )
        print(f"单位部门：{unit_count}")
        print(f"下级部门：{child_count}")
        print(f"测试人员：{test_user_count}")
        print(f"默认密码：{DEFAULT_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
