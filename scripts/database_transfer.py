import argparse
import base64
import gzip
import hashlib
import hmac
import json
import os
import sys
import tempfile
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Date, DateTime, LargeBinary, Numeric, Time, create_engine, delete, func, inspect, select, text
from sqlalchemy.engine import Engine, make_url


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import models  # noqa: F401
from app.config import database_url, normalize_database_url
from app.database import Base, engine_options


FORMAT_NAME = "personnel-evaluation-logical-backup"
FORMAT_VERSION = 1
EXCLUDED_TABLES = {"user_sessions"}


def transfer_tables():
    return [table for table in Base.metadata.sorted_tables if table.name not in EXCLUDED_TABLES]


def safe_url(url: str) -> str:
    return make_url(url).render_as_string(hide_password=True)


def make_engine(url: str) -> Engine:
    normalized = normalize_database_url(url)
    return create_engine(normalized, **engine_options(normalized))


def encode_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    return value


def decode_value(column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date):
        return date.fromisoformat(value)
    if isinstance(column.type, Time):
        return time.fromisoformat(value)
    if isinstance(column.type, Numeric):
        return Decimal(value)
    if isinstance(column.type, LargeBinary) and isinstance(value, dict) and "__bytes__" in value:
        return base64.b64decode(value["__bytes__"])
    return value


def canonical_json(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def collect_backup(source_engine: Engine) -> dict:
    available = set(inspect(source_engine).get_table_names())
    required = {table.name for table in transfer_tables()}
    missing = sorted(required - available)
    if missing:
        raise RuntimeError(f"源数据库缺少必要数据表：{', '.join(missing)}")

    table_payloads: list[dict] = []
    with source_engine.connect() as connection:
        for table in transfer_tables():
            primary_key = list(table.primary_key.columns)
            statement = select(table)
            if primary_key:
                statement = statement.order_by(*primary_key)
            rows = [
                {column.name: encode_value(row._mapping[column.name]) for column in table.columns}
                for row in connection.execute(statement)
            ]
            table_payloads.append({"name": table.name, "rows": rows})

    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_backend": source_engine.dialect.name,
        "excluded_tables": sorted(EXCLUDED_TABLES),
        "tables": table_payloads,
    }


def write_backup(payload: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload_bytes = canonical_json(payload)
    document = {
        "checksum": hashlib.sha256(payload_bytes).hexdigest(),
        "payload": payload,
    }
    content = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
    file_descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(file_descriptor, "wb") as raw_file:
        if output_path.suffix == ".gz":
            with gzip.GzipFile(fileobj=raw_file, mode="wb") as compressed:
                compressed.write(content)
        else:
            raw_file.write(content)


def read_backup(input_path: Path) -> dict:
    with input_path.open("rb") as source:
        signature = source.read(2)
    opener = gzip.open if signature == b"\x1f\x8b" else open
    with opener(input_path, "rt", encoding="utf-8") as source:
        document = json.load(source)
    payload = document.get("payload")
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME or payload.get("version") != FORMAT_VERSION:
        raise RuntimeError("不支持的备份文件格式。")
    expected = hashlib.sha256(canonical_json(payload)).hexdigest()
    if not hmac.compare_digest(document.get("checksum", ""), expected):
        raise RuntimeError("备份文件完整性校验失败。")
    return payload


def target_has_data(target_engine: Engine) -> bool:
    with target_engine.connect() as connection:
        return any(connection.scalar(select(func.count()).select_from(table)) for table in transfer_tables())


def clear_target(connection, tables) -> None:
    if connection.dialect.name == "mysql":
        connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    try:
        for table in reversed(tables):
            connection.execute(delete(table))
    finally:
        if connection.dialect.name == "mysql":
            connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))


def sync_postgresql_sequences(connection, tables) -> None:
    if connection.dialect.name != "postgresql":
        return
    for table in tables:
        primary_keys = list(table.primary_key.columns)
        if len(primary_keys) != 1:
            continue
        column = primary_keys[0]
        sequence = connection.scalar(
            text("SELECT pg_get_serial_sequence(:table_name, :column_name)"),
            {"table_name": table.name, "column_name": column.name},
        )
        if not sequence:
            continue
        maximum = connection.scalar(select(func.max(column)))
        if maximum is None:
            connection.execute(text("SELECT setval(CAST(:sequence AS regclass), 1, false)"), {"sequence": sequence})
        else:
            connection.execute(
                text("SELECT setval(CAST(:sequence AS regclass), :value, true)"),
                {"sequence": sequence, "value": maximum},
            )


def restore_backup(target_engine: Engine, payload: dict, clear_existing: bool = False) -> int:
    Base.metadata.create_all(bind=target_engine)
    tables = transfer_tables()
    table_by_name = {table.name: table for table in tables}
    payload_tables = {item["name"]: item.get("rows", []) for item in payload.get("tables", [])}
    unknown = sorted(set(payload_tables) - set(table_by_name))
    if unknown:
        raise RuntimeError(f"备份包含当前版本不识别的数据表：{', '.join(unknown)}")
    if target_has_data(target_engine) and not clear_existing:
        raise RuntimeError("目标数据库不为空；如需要覆盖，请显式使用 --clear-existing。")

    imported_rows = 0
    with target_engine.begin() as connection:
        session_table = Base.metadata.tables.get("user_sessions")
        if session_table is not None:
            connection.execute(delete(session_table))
        if clear_existing:
            clear_target(connection, tables)
        for table in tables:
            raw_rows = payload_tables.get(table.name, [])
            rows = [
                {
                    column.name: decode_value(column, raw_row[column.name])
                    for column in table.columns
                    if column.name in raw_row
                }
                for raw_row in raw_rows
            ]
            if rows:
                connection.execute(table.insert(), rows)
                imported_rows += len(rows)
        sync_postgresql_sequences(connection, tables)
    return imported_rows


def default_backup_path() -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path("backups") / f"personnel-evaluation-{timestamp}.json.gz"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup, restore, or migrate the personnel evaluation database.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a compressed logical backup.")
    backup.add_argument("--database-url", default=os.getenv("SOURCE_DATABASE_URL") or database_url())
    backup.add_argument("--output", type=Path, default=None)

    restore = subparsers.add_parser("restore", help="Restore a logical backup into a configured database.")
    restore.add_argument("backup_file", type=Path)
    restore.add_argument("--database-url", default=os.getenv("TARGET_DATABASE_URL") or database_url())
    restore.add_argument("--clear-existing", action="store_true")

    migrate = subparsers.add_parser("migrate", help="Migrate data directly between two database URLs.")
    migrate.add_argument("--source-url", default=os.getenv("SOURCE_DATABASE_URL"), required=os.getenv("SOURCE_DATABASE_URL") is None)
    migrate.add_argument("--target-url", default=os.getenv("TARGET_DATABASE_URL"), required=os.getenv("TARGET_DATABASE_URL") is None)
    migrate.add_argument("--clear-target", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "backup":
        output = args.output or default_backup_path()
        source = make_engine(args.database_url)
        payload = collect_backup(source)
        write_backup(payload, output)
        total = sum(len(table["rows"]) for table in payload["tables"])
        print(f"Backup created: {output} ({total} rows, sessions excluded)")
        return

    if args.command == "restore":
        target = make_engine(args.database_url)
        payload = read_backup(args.backup_file)
        total = restore_backup(target, payload, clear_existing=args.clear_existing)
        print(f"Restore completed: {safe_url(args.database_url)} ({total} rows, sessions revoked)")
        return

    source = make_engine(args.source_url)
    target = make_engine(args.target_url)
    with tempfile.TemporaryDirectory() as directory:
        temporary_backup = Path(directory) / "migration.json.gz"
        payload = collect_backup(source)
        write_backup(payload, temporary_backup)
        verified_payload = read_backup(temporary_backup)
        total = restore_backup(target, verified_payload, clear_existing=args.clear_target)
    print(f"Migration completed: {safe_url(args.source_url)} -> {safe_url(args.target_url)} ({total} rows, sessions revoked)")


if __name__ == "__main__":
    main()
