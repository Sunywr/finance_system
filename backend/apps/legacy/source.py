"""Lossless row serialization and SELECT-only access to a frozen local source."""

import base64
import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pymysql
from django.conf import settings
from django.db import connection
from django.utils import timezone
from zoneinfo import ZoneInfo

SECRET_WORDS = (
    "password",
    "secret",
    "api_key",
    "authorization",
    "access_token",
    "refresh_token",
)


def normalized(value):
    if isinstance(value, timedelta):
        return {"__mysql_time_microseconds__": value // timedelta(microseconds=1)}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return {"__binary__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): normalized(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    return value


def canonical(value):
    return json.dumps(
        normalized(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def money(value):
    return Decimal(str(value if value is not None else 0)).quantize(
        Decimal(".01"), rounding=ROUND_HALF_UP
    )


def number(value):
    return Decimal(str(value if value is not None else 0))


def business_time(value):
    """Legacy account input parser stores naive Shanghai wall time, not UTC."""
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    return (
        timezone.make_aware(value, ZoneInfo("Asia/Shanghai"))
        if timezone.is_naive(value)
        else value
    )


def assert_target():
    cfg = connection.settings_dict
    if (
        not settings.MIGRATION_REHEARSAL
        or cfg["ENGINE"] != "django.db.backends.mysql"
        or cfg["HOST"] not in ("127.0.0.1", "localhost")
        or not cfg["NAME"].startswith("finance_rehearsal")
    ):
        raise RuntimeError(
            "Import only accepts MIGRATION_REHEARSAL=1 and a loopback finance_rehearsal* MySQL database"
        )
    marker = Path(
        getattr(
            settings,
            "MIGRATION_INSTANCE_FILE",
            settings.BASE_DIR.parent / "backups/migration-20261021/instance.json",
        )
    )
    owned = json.loads(marker.read_text(encoding="utf8"))
    if int(cfg["PORT"]) != int(owned["root"]["port"]):
        raise RuntimeError("Import target is not the managed rehearsal port")
    with connection.cursor() as cursor:
        cursor.execute("SELECT @@server_uuid,@@event_scheduler")
        actual, events = cursor.fetchone()
    if actual != owned["uuid"] or str(events).upper() != "OFF":
        raise RuntimeError(
            "Import target identity/scheduler does not match the managed rehearsal"
        )


class Source:
    def __init__(self, path):
        self.config = json.loads(Path(path).read_text(encoding="utf8"))
        if (
            self.config["host"] not in ("127.0.0.1", "localhost")
            or self.config["user"] != "legacy_reader"
        ):
            raise RuntimeError("Only the isolated SELECT-only source is accepted")
        cfg = {
            k: self.config[k] for k in ("host", "port", "user", "password", "database")
        }
        self.conn = pymysql.connect(
            **cfg,
            charset="utf8mb4",
            autocommit=True,
            read_timeout=120,
            cursorclass=pymysql.cursors.DictCursor
        )
        with self.conn.cursor() as c:
            c.execute("SELECT @@server_uuid AS uuid,@@event_scheduler AS events")
            identity = c.fetchone()
            if (
                identity["uuid"] != self.config["server_uuid"]
                or str(identity["events"]).upper() != "OFF"
            ):
                raise RuntimeError(
                    "Frozen source identity/event-scheduler check failed"
                )
            c.execute("SET SESSION TRANSACTION READ ONLY")
            c.execute(
                "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME"
            )
            self.tables = [r["TABLE_NAME"] for r in c.fetchall()]

    def query(self, sql, args=None):
        if sql.lstrip().split(None, 1)[0].upper() not in ("SELECT", "SHOW"):
            raise RuntimeError("Source only accepts SELECT/SHOW")
        with self.conn.cursor() as c:
            c.execute(sql, args)
            return c.fetchall()

    def rows(self, table):
        if table not in self.tables or not table.replace("_", "").isalnum():
            raise ValueError("Unknown source table")
        pk = [
            r["Column_name"]
            for r in self.query(
                "SHOW INDEX FROM `" + table + "` WHERE Key_name='PRIMARY'"
            )
        ]
        order = " ORDER BY " + ",".join("`" + k + "`" for k in pk) if pk else ""
        with self.conn.cursor(pymysql.cursors.SSDictCursor) as c:
            c.execute("SELECT * FROM `" + table + "`" + order)
            for ordinal, row in enumerate(c, 1):
                key = canonical([row[k] for k in pk]) if pk else "row:" + str(ordinal)
                if len(pk) == 1:
                    key = str(row[pk[0]])
                yield key, row

    def all(self, table):
        return [row for _, row in self.rows(table)] if table in self.tables else []

    def close(self):
        self.conn.close()
