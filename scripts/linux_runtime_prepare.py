"""Prepare disposable API benchmark schemas and an SSH tunnel to the owned MySQL.

Both APIs run on Linux with identical CPU/memory limits. The shared database
remains Windows MySQL 8.4; this is explicitly not a production-stack benchmark.
"""

import gzip
import json
import os
import secrets
import subprocess
import time
from pathlib import Path
import pymysql
from migration_roundtrip import OUT, ROOT, assert_target
from django.contrib.auth.hashers import make_password


def main():
    assert_target()
    instance = json.loads((OUT / "instance.json").read_text())
    root = instance["root"]
    state_path = OUT / "linux-bench-state.json"
    state = (
        json.loads(state_path.read_text())
        if state_path.exists()
        else {
            "password": secrets.token_urlsafe(24),
            "web_password": secrets.token_urlsafe(24),
            "schemas": {},
        }
    )
    state_path.write_text(json.dumps(state, indent=2))
    mysql = Path(r"D:\Software\Env\mysql8\bin\mysql.exe")
    flags = [
        "--no-defaults",
        "--host=127.0.0.1",
        f'--port={root["port"]}',
        "--user=root",
        "--default-character-set=utf8mb4",
    ]
    for schema, backup in [
        ("pfm_runtime_bench", "database.sql.gz"),
        ("finance_rehearsal_runtime", "new-database.sql.gz"),
    ]:
        if state["schemas"].get(schema) == "restored":
            continue
        with pymysql.connect(**root) as conn:
            with conn.cursor() as c:
                c.execute("SELECT @@server_uuid")
                if c.fetchone()[0] != instance["uuid"]:
                    raise RuntimeError("Wrong benchmark instance")
                c.execute(
                    "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s",
                    [schema],
                )
                exists = c.fetchone()[0]
                if exists and state["schemas"].get(schema) != "restoring":
                    raise RuntimeError("Unowned benchmark schema already exists")
                if not exists:
                    c.execute(
                        "CREATE DATABASE `"
                        + schema
                        + "` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
        state["schemas"][schema] = "restoring"
        state_path.write_text(json.dumps(state, indent=2))
        print("Restoring disposable API benchmark schema " + schema, flush=True)
        with (OUT / (schema + "-restore.log")).open("wb") as log:
            p = subprocess.Popen(
                [str(mysql), *flags, "--binary-mode=1", schema],
                env=dict(os.environ, MYSQL_PWD=root["password"]),
                stdin=subprocess.PIPE,
                stderr=log,
            )
            try:
                with gzip.open(OUT / backup, "rb") as h:
                    for b in iter(lambda: h.read(1024 * 1024), b""):
                        p.stdin.write(b)
                p.stdin.close()
                if p.wait():
                    raise RuntimeError("Benchmark restore failed; private log retained")
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait()
        state["schemas"][schema] = "restored"
        state_path.write_text(json.dumps(state, indent=2))
    with pymysql.connect(**root, autocommit=True) as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT id,username FROM finance_rehearsal_runtime.users_user WHERE is_active=1 AND is_superuser=0 ORDER BY id LIMIT 1"
            )
            uid, username = c.fetchone()
            state.update(user_id=uid, username=username)
            encoded = make_password(state["web_password"])
            for schema, table in [
                ("pfm_runtime_bench", "auth_user"),
                ("finance_rehearsal_runtime", "users_user"),
            ]:
                c.execute(
                    "UPDATE `"
                    + schema
                    + "`.`"
                    + table
                    + "` SET password=%s WHERE id=%s",
                    [encoded, uid],
                )
            c.execute("UPDATE pfm_runtime_bench.stock_ai_model_config SET enabled=0")
            for name, schema in [
                ("finance_bench_old", "pfm_runtime_bench"),
                ("finance_bench_new", "finance_rehearsal_runtime"),
            ]:
                c.execute(
                    "CREATE USER IF NOT EXISTS '"
                    + name
                    + "'@'127.0.0.1' IDENTIFIED BY %s",
                    [state["password"]],
                )
                c.execute(
                    "ALTER USER '" + name + "'@'127.0.0.1' IDENTIFIED BY %s",
                    [state["password"]],
                )
                c.execute(
                    "GRANT ALL ON `" + schema + "`.* TO '" + name + "'@'127.0.0.1'"
                )
    inspect = json.loads(
        subprocess.check_output(["podman", "machine", "inspect"], text=True)
    )[0]
    ssh = inspect["SSHConfig"]
    tunnel = [
        "ssh",
        "-i",
        ssh["IdentityPath"],
        "-p",
        str(ssh["Port"]),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "UserKnownHostsFile=" + str(OUT / "vm-known-hosts"),
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=15",
        "-N",
        "-R",
        f'127.0.0.1:33106:127.0.0.1:{root["port"]}',
        ssh["RemoteUsername"] + "@127.0.0.1",
    ]
    with (OUT / "tunnel.log").open("ab") as log:
        p = subprocess.Popen(
            tunnel,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    time.sleep(2)
    if p.poll() is not None:
        raise RuntimeError("VM tunnel failed; private log retained")
    state.update(tunnel_pid=p.pid, vm_started_by_this_task=True)
    state_path.write_text(json.dumps(state, indent=2))
    (OUT / "old-api.env").write_text(
        f'PFM_DATABASE_URL=mysql://finance_bench_old:{state["password"]}@127.0.0.1:33106/pfm_runtime_bench\nPFM_API_HOST=127.0.0.1\nPFM_API_PORT=18081\nRUST_LOG=error\nPFM_STRICT_STANDALONE=true\n'
    )
    (OUT / "new-api.env").write_text(
        f'DB_ENGINE=mysql\nDB_HOST=127.0.0.1\nDB_PORT=33106\nDB_NAME=finance_rehearsal_runtime\nDB_USER=finance_bench_new\nDB_PASSWORD={state["password"]}\nSECRET_KEY={secrets.token_urlsafe(48)}\nDEBUG=0\nALLOWED_HOSTS=127.0.0.1,localhost\nMIGRATION_REHEARSAL=1\nLEGACY_ARCHIVE_ROOT=/archive\n'
    )
    subprocess.run(
        [
            "podman",
            "run",
            "--rm",
            "--network",
            "host",
            "--entrypoint",
            "python",
            "docker.io/library/python:3.12.13-slim-bookworm",
            "-c",
            "import socket; s=socket.create_connection(('127.0.0.1',33106),5); s.close(); print('Owned MySQL tunnel ready')",
        ],
        check=True,
    )
    print(
        "Disposable schemas, benchmark-only credentials and VM tunnel prepared",
        flush=True,
    )


if __name__ == "__main__":
    main()
