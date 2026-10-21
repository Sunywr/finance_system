"""Back up and restore only the owned new rehearsal database, then hash every row."""

import gzip
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backups" / "migration-20261021"
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from dotenv import dotenv_values

os.environ.update(
    {k: v for k, v in dotenv_values(OUT / "rehearsal.env").items() if v is not None}
)
import django

django.setup()
from django.conf import settings
from apps.legacy.source import canonical, assert_target


def hashes(cfg, db):
    result = {}
    with pymysql.connect(**cfg, database=db, charset="utf8mb4") as conn:
        with conn.cursor() as c:
            c.execute("SHOW TABLES")
            tables = [r[0] for r in c.fetchall()]
        for t in tables:
            with conn.cursor(pymysql.cursors.DictCursor) as c:
                c.execute("SHOW INDEX FROM `" + t + "` WHERE Key_name='PRIMARY'")
                pk = [r["Column_name"] for r in c.fetchall()]
            if not pk:
                raise RuntimeError("No deterministic primary key: " + t)
            sha = hashlib.sha256()
            rows = 0
            with conn.cursor(pymysql.cursors.SSDictCursor) as c:
                c.execute(
                    "SELECT * FROM `"
                    + t
                    + "` ORDER BY "
                    + ",".join("`" + k + "`" for k in pk)
                )
                for r in c:
                    sha.update((canonical(r) + "\n").encode())
                    rows += 1
            result[t] = {"rows": rows, "sha256": sha.hexdigest()}
    return result


def main():
    assert_target()
    cfg = json.loads((OUT / "instance.json").read_text())
    root = cfg["root"]
    with pymysql.connect(**root) as conn:
        with conn.cursor() as c:
            c.execute("SELECT @@server_uuid")
            if c.fetchone()[0] != cfg["uuid"]:
                raise RuntimeError("Wrong MySQL instance")
            c.execute(
                "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='finance_rehearsal_roundtrip'"
            )
            if c.fetchone()[0]:
                raise RuntimeError(
                    "Roundtrip database already exists; keep the previous verification"
                )
    before = hashes(root, "finance_rehearsal")
    mysql = Path(r"D:\Software\Env\mysql8\bin\mysql.exe")
    flags = [
        "--no-defaults",
        "--host=127.0.0.1",
        f'--port={root["port"]}',
        "--user=root",
        "--default-character-set=utf8mb4",
    ]
    env = dict(os.environ, MYSQL_PWD=root["password"])
    destination = OUT / "new-database.sql.gz"
    raw = hashlib.sha256()
    if destination.exists():
        raise RuntimeError("Refusing to overwrite new database backup")
    with (OUT / "new-dump.log").open("wb") as log:
        p = subprocess.Popen(
            [
                str(mysql.with_name("mysqldump.exe")),
                *flags,
                "--single-transaction",
                "--quick",
                "--hex-blob",
                "--no-tablespaces",
                "--set-gtid-purged=OFF",
                "--column-statistics=0",
                "--routines",
                "--events",
                "--triggers",
                "finance_rehearsal",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=log,
        )
        with gzip.open(destination.with_suffix(".partial"), "wb") as z:
            for b in iter(lambda: p.stdout.read(1024 * 1024), b""):
                raw.update(b)
                z.write(b)
        if p.wait():
            raise RuntimeError("New database backup failed")
    destination.with_suffix(".partial").rename(destination)
    with pymysql.connect(**root) as conn:
        with conn.cursor() as c:
            c.execute(
                "CREATE DATABASE finance_rehearsal_roundtrip CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    with (OUT / "new-restore.log").open("wb") as log:
        p = subprocess.Popen(
            [str(mysql), *flags, "finance_rehearsal_roundtrip"],
            env=env,
            stdin=subprocess.PIPE,
            stderr=log,
        )
        with gzip.open(destination, "rb") as h:
            for b in iter(lambda: h.read(1024 * 1024), b""):
                p.stdin.write(b)
        p.stdin.close()
        if p.wait():
            raise RuntimeError("New database restore failed")
    after = hashes(root, "finance_rehearsal_roundtrip")
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    report = {
        "tables": len(before),
        "rows": sum(r["rows"] for r in before.values()),
        "all_table_hashes_match": before == after,
        "backup_bytes": destination.stat().st_size,
        "backup_sha256": checksum,
        "sql_sha256": raw.hexdigest(),
        "table_fingerprints": before,
        "restore_fingerprints": after,
        "archive_files_required_separately": True,
    }
    (OUT / "roundtrip.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    (OUT / "application-encryption.json").write_text(
        json.dumps(
            {
                "SECRET_KEY": settings.SECRET_KEY,
                "AI_ENCRYPTION_KEY": settings.AI_ENCRYPTION_KEY,
            }
        ),
        encoding="utf8",
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ("table_fingerprints", "restore_fingerprints")
            }
        )
    )
    if before != after:
        raise RuntimeError("Restored data does not match")


if __name__ == "__main__":
    main()
