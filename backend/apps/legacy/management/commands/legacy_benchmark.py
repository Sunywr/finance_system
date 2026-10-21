"""Read-only same-instance SQL comparison plus real-data native API checks.

This deliberately does not call an SQL timing an old application/API timing.
"""

import gzip
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
from apps.legacy.source import Source, assert_target


def profile(fn, repeats=25):
    samples = []
    for _ in range(3):
        fn()
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(sorted(samples)[int(0.95 * (len(samples) - 1))], 3),
        "samples": len(samples),
    }


class Command(BaseCommand):
    help = "在同一独立 MySQL 比较等价只读 SQL，并验证新系统真实数据 API；不压测生产"

    def add_arguments(self, p):
        p.add_argument("--source", required=True)
        p.add_argument("--output", required=True)

    def handle(self, *args, **o):
        assert_target()
        source = Source(o["source"])
        output = Path(o["output"])
        report = {
            "platform": platform.platform(),
            "comparison_scope": "same-instance SELECT workloads; old Rust API/runtime not measured",
            "production_performance_claim": False,
            "sql": {},
            "api": [],
        }
        try:
            with connection.cursor() as c:
                c.execute("SET SESSION information_schema_stats_expiry=0")
                c.execute(
                    "SELECT TABLE_SCHEMA,COUNT(*),SUM(DATA_LENGTH+INDEX_LENGTH) FROM information_schema.TABLES WHERE TABLE_SCHEMA IN ('pfm',DATABASE()) GROUP BY TABLE_SCHEMA"
                )
                report["estimated_table_index_bytes"] = {
                    r[0]: {"tables": r[1], "bytes": int(r[2])} for r in c.fetchall()
                }
            owner = (
                get_user_model()
                .objects.filter(is_active=True, is_superuser=False)
                .order_by("pk")
                .first()
                or get_user_model().objects.first()
            )
            cases = {
                "monthly_income_expense": (
                    "SELECT DATE_FORMAT(account_date,'%%Y-%%m'),SUM(COALESCE(income,0)),SUM(COALESCE(expenditure,0)) FROM account_account WHERE owner_id_id=%s GROUP BY 1",
                    "SELECT DATE_FORMAT(CONVERT_TZ(occurred_at,'+00:00','+08:00'),'%%Y-%%m'),SUM(IF(type IN ('INCOME','REFUND','TRANSFER_IN'),amount,0)),SUM(IF(type IN ('EXPENSE','TRANSFER_OUT'),amount,0)) FROM ledger_transaction WHERE owner_id=%s AND source='LEGACY' GROUP BY 1",
                ),
                "ledger_first_page": (
                    "SELECT id,account_date,income,expenditure FROM account_account WHERE owner_id_id=%s ORDER BY account_date DESC,id DESC LIMIT 50",
                    "SELECT id,occurred_at,type,amount FROM ledger_transaction WHERE owner_id=%s ORDER BY occurred_at DESC,id DESC LIMIT 50",
                ),
                "active_holdings": (
                    "SELECT code,share,cost,value,profit FROM account_invest WHERE owner_id_id=%s AND status=0",
                    "SELECT instrument_id,quantity,cost,market_value,profit FROM legacy_positionbasis WHERE owner_id=%s AND is_active=1",
                ),
            }

            def target(sql):
                with connection.cursor() as c:
                    c.execute(sql, [owner.pk])
                    return c.fetchall()

            for name, (old, new) in cases.items():
                report["sql"][name] = {
                    "source": profile(lambda: source.query(old, [owner.pk])),
                    "target": profile(lambda: target(new)),
                }
            client = APIClient()
            client.force_authenticate(owner)
            for path in [
                "/api/v1/health",
                "/api/v1/accounts/",
                "/api/v1/transactions/",
                "/api/v1/instruments/",
                "/api/v1/debts/",
                "/api/v1/loans/",
                "/api/v1/holdings",
                "/api/v1/household/summary",
                "/api/v1/history/types",
                "/api/v1/history/records?table=account_account&page_size=20",
                "/api/v1/migration/status",
            ]:
                with CaptureQueriesContext(connection) as captured:
                    response = client.get(path, HTTP_HOST="localhost")
                item = {
                    "path": path,
                    "status": response.status_code,
                    "queries": len(captured),
                }
                if response.status_code == 200:
                    item.update(
                        profile(lambda: client.get(path, HTTP_HOST="localhost"), 10)
                    )
                else:
                    item["error"] = str(getattr(response, "data", ""))[:200]
                report["api"].append(item)
            try:
                import sys

                private_tools = output / "tools"
                if private_tools.is_dir():
                    sys.path.insert(0, str(private_tools))
                import psutil

                proc = psutil.Process()
                report["benchmark_process_rss_bytes"] = proc.memory_info().rss
                instance = json.loads((output / "instance.json").read_text())
                report["mysql_process_rss_bytes"] = (
                    psutil.Process(instance["pid"]).memory_info().rss
                )
            except (ImportError, OSError):
                report["memory_measurement"] = "unavailable"
            report["limits"] = [
                "Old Rust application and background-job peak memory/P95 were not measured; SQL comparisons cannot establish end-to-end production improvements.",
                "Windows/MySQL 8.4 measurements do not establish Linux/MySQL 8.0 equivalence.",
                "Data/index figures are InnoDB estimates, not physical file reclamation.",
            ]
            (output / "benchmark.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
            )
            self.stdout.write(
                json.dumps(
                    {
                        "sql_workloads": len(cases),
                        "api_statuses": [
                            (r["path"], r["status"]) for r in report["api"]
                        ],
                        "production_performance_claim": False,
                    }
                )
            )
        finally:
            source.close()
