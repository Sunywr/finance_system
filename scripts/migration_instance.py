"""Own a dedicated migration MySQL instance. Never operate on project databases."""

import argparse
import gzip
import hashlib
import json
import os
import secrets
import socket
import subprocess
import time
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "backups" / "migration-20261021"
HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["start", "restore", "stop"])
    args = ap.parse_args()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    marker = PRIVATE / "instance.json"
    binary = Path(r"D:\Software\Env\mysql8\bin\mysqld.exe")
    mysql = binary.with_name("mysql.exe")
    data = PRIVATE / "mysql-data"
    if args.action == "start":
        if marker.exists():
            cfg = json.loads(marker.read_text())
            try:
                with pymysql.connect(**cfg["root"], connect_timeout=3) as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT @@server_uuid")
                        actual = cur.fetchone()[0]
                if actual != cfg["uuid"]:
                    raise RuntimeError("Instance identity mismatch")
                print("Owned rehearsal instance already running")
                return
            except pymysql.OperationalError:
                command = cfg["command"]
                if (
                    Path(command[0]).resolve() != binary.resolve()
                    or f"--datadir={data}" not in command
                    or "--bind-address=127.0.0.1" not in command
                    or "--event-scheduler=OFF" not in command
                ):
                    raise RuntimeError(
                        "Recorded launch command does not identify this rehearsal"
                    )
                if not data.is_dir():
                    raise RuntimeError(
                        "Owned data directory is missing; refusing reinitialization"
                    )
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", cfg["root"]["port"]))
                with (PRIVATE / "mysql-server.log").open("ab") as log:
                    p = subprocess.Popen(
                        command, stdout=log, stderr=log, creationflags=HIDDEN
                    )
                for _ in range(150):
                    try:
                        with pymysql.connect(**cfg["root"], connect_timeout=2) as conn:
                            with conn.cursor() as cur:
                                cur.execute("SELECT @@server_uuid,@@event_scheduler")
                                actual, events = cur.fetchone()
                        if actual != cfg["uuid"] or events.upper() != "OFF":
                            raise RuntimeError(
                                "Restarted instance identity/scheduler mismatch"
                            )
                        cfg["pid"] = p.pid
                        marker.write_text(json.dumps(cfg, indent=2), encoding="utf8")
                        print(
                            "Owned rehearsal restarted with existing data and scheduler disabled"
                        )
                        return
                    except pymysql.OperationalError:
                        if p.poll() is not None:
                            raise RuntimeError(
                                "Rehearsal restart failed; see private server log"
                            )
                        time.sleep(0.3)
                raise RuntimeError("Owned rehearsal restart readiness timed out")
        if data.exists():
            raise RuntimeError("Unregistered data directory; refusing initialization")
        with (PRIVATE / "mysql-init.log").open("wb") as log:
            subprocess.run(
                [
                    str(binary),
                    "--no-defaults",
                    "--initialize-insecure",
                    f"--datadir={data}",
                    "--console",
                ],
                stdout=log,
                stderr=log,
                check=True,
                creationflags=HIDDEN,
            )
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        command = [
            str(binary),
            "--no-defaults",
            f"--datadir={data}",
            f"--port={port}",
            "--bind-address=127.0.0.1",
            "--mysqlx=OFF",
            "--event-scheduler=OFF",
            "--innodb-buffer-pool-size=384M",
            "--innodb-redo-log-capacity=1G",
            "--max-connections=40",
            "--console",
        ]
        with (PRIVATE / "mysql-server.log").open("ab") as log:
            p = subprocess.Popen(command, stdout=log, stderr=log, creationflags=HIDDEN)
        for _ in range(100):
            try:
                conn = pymysql.connect(
                    host="127.0.0.1", port=port, user="root", connect_timeout=2
                )
                break
            except pymysql.OperationalError:
                if p.poll() is not None:
                    raise RuntimeError("MySQL failed; see private server log")
                time.sleep(0.3)
        else:
            raise RuntimeError("MySQL readiness timed out")
        password = secrets.token_urlsafe(28)
        with conn.cursor() as cur:
            cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", [password])
            cur.execute(
                "CREATE DATABASE pfm CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(
                "CREATE DATABASE finance_rehearsal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute("SELECT @@server_uuid")
            uuid = cur.fetchone()[0]
        conn.close()
        cfg = dict(
            pid=p.pid,
            uuid=uuid,
            command=command,
            root=dict(host="127.0.0.1", port=port, user="root", password=password),
            directory=str(PRIVATE),
        )
        marker.write_text(json.dumps(cfg, indent=2), encoding="utf8")
        (PRIVATE / "rehearsal.env").write_text(
            f'DB_ENGINE=mysql\nDB_HOST=127.0.0.1\nDB_PORT={port}\nDB_NAME=finance_rehearsal\nDB_USER=root\nDB_PASSWORD={password}\nDB_TEST_NAME=test_finance_rehearsal\nMIGRATION_REHEARSAL=1\nLEGACY_ARCHIVE_ROOT={PRIVATE / "archive"}\n',
            encoding="utf8",
        )
        print(f"Owned MySQL ready on 127.0.0.1:{port}; original databases unchanged")
        return
    cfg = json.loads(marker.read_text())
    with pymysql.connect(**cfg["root"]) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT @@server_uuid")
            actual = cur.fetchone()[0]
        if actual != cfg["uuid"]:
            raise RuntimeError("Instance identity mismatch")
    env = dict(os.environ, MYSQL_PWD=cfg["root"]["password"])
    client = [
        str(mysql),
        "--no-defaults",
        "--host=127.0.0.1",
        f'--port={cfg["root"]["port"]}',
        "--user=root",
        "--binary-mode=1",
        "--default-character-set=utf8mb4",
    ]
    if args.action == "stop":
        subprocess.run(
            [str(binary.with_name("mysqladmin.exe")), *client[1:5], "shutdown"],
            env=env,
            check=True,
        )
        print("Owned migration instance stopped; data retained")
        return
    if (PRIVATE / "restored.json").exists():
        print("Source restore already completed")
        return
    manifest = json.loads((PRIVATE / "manifest.json").read_text())
    sha = hashlib.sha256()
    size = 0
    print("Restoring the frozen production snapshot into isolated pfm...", flush=True)
    with (PRIVATE / "restore.log").open("wb") as log:
        p = subprocess.Popen(
            client + ["pfm"], env=env, stdin=subprocess.PIPE, stderr=log
        )
        try:
            with gzip.open(PRIVATE / "database.sql.gz", "rb") as h:
                for block in iter(lambda: h.read(1024 * 1024), b""):
                    sha.update(block)
                    size += len(block)
                    p.stdin.write(block)
            p.stdin.close()
            if p.wait():
                raise RuntimeError("Restore failed; see private restore log")
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
    if sha.hexdigest() != manifest["raw_sha256"]:
        raise RuntimeError("Restored SQL hash mismatch")
    with pymysql.connect(**cfg["root"], database="pfm") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE USER 'legacy_reader'@'127.0.0.1' IDENTIFIED BY %s",
                [secrets.token_urlsafe(28)],
            )
            reader_password = secrets.token_urlsafe(28)
            cur.execute(
                "ALTER USER 'legacy_reader'@'127.0.0.1' IDENTIFIED BY %s",
                [reader_password],
            )
            cur.execute(
                "GRANT SELECT, SHOW VIEW ON pfm.* TO 'legacy_reader'@'127.0.0.1'"
            )
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='pfm'"
            )
            tables = cur.fetchone()[0]
    (PRIVATE / "source.json").write_text(
        json.dumps(
            dict(
                host="127.0.0.1",
                port=cfg["root"]["port"],
                user="legacy_reader",
                password=reader_password,
                database="pfm",
                server_uuid=cfg["uuid"],
                snapshot_sha256=manifest["raw_sha256"],
            )
        ),
        encoding="utf8",
    )
    (PRIVATE / "restored.json").write_text(
        json.dumps(
            dict(
                raw_sha256=sha.hexdigest(),
                raw_bytes=size,
                tables=tables,
                events_enabled=False,
            )
        ),
        encoding="utf8",
    )
    print(
        f"Restored {tables} tables; decompressed SHA-256 verified; source account is SELECT-only",
        flush=True,
    )


if __name__ == "__main__":
    main()
