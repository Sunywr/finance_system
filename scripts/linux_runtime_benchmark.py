"""Run inside the disposable Linux native API container, against benchmark clones.

Credentials are read from /tmp/benchstate.json and never included in the report.
This measures warm local HTTP, not browser rendering or production performance.
"""

import json
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote

import requests


def main():
    state = json.loads(Path("/tmp/benchstate.json").read_text())
    credentials = {"username": state["username"], "password": state["web_password"]}
    report = {
        "production_performance_claim": False,
        "cpu_limit_each": 1,
        "shared_application_memory_limit_bytes": 1073741824,
        "database": "shared owned Windows MySQL 8.4.7 via SSH tunnel; 384MiB buffer pool",
        "workload": "3 warmups, 25 sequential requests, then 20 requests with 4 clients; loopback HTTP",
        "apis": {},
    }
    for name, port, cases in [
        (
            "old",
            18081,
            [
                ("ledger", "/api/account/accounts?page=1&page_size=50"),
                ("holdings", "/api/account/invests?page=1&page_size=50&ignore_sold=1"),
                ("summary", "/api/account/index"),
            ],
        ),
        (
            "new",
            18082,
            [
                ("ledger", "/api/v1/transactions/?page_size=50"),
                ("holdings", "/api/v1/holdings"),
                ("summary", "/api/v1/household/summary"),
            ],
        ),
    ]:
        base = f"http://127.0.0.1:{port}"
        client = requests.Session()
        if name == "old":
            challenge = client.get(base + "/api/utils/captcha", timeout=30)
            svg = unquote(challenge.json()["data"])
            match = re.search(r"<text[^>]*>([^<]+)</text>", svg)
            if not match:
                raise RuntimeError("Benchmark-only captcha could not be parsed")
            response = client.post(
                base + "/api/utils/login",
                json=dict(credentials, code=match[1]),
                timeout=30,
            )
            body = response.json()
            token = body.get("data", {}).get("token")
        else:
            response = client.post(
                base + "/api/v1/auth/token", json=credentials, timeout=30
            )
            body = response.json()
            token = body.get("access")
        if response.status_code != 200 or not token:
            raise RuntimeError(
                f"{name} benchmark-only authentication failed (HTTP {response.status_code}, fields {list(body)})"
            )
        headers = {"Authorization": "Bearer " + token}
        client.headers.update(headers)
        measured = []
        for label, path in cases:
            url = base + path
            first = client.get(url, timeout=120)
            body = first.json()
            item = {
                "label": label,
                "path": path,
                "status": first.status_code,
                "business_code": body.get("code"),
                "response_bytes": len(first.content),
            }
            if first.status_code != 200 or body.get("code", 0) not in (0, 200):
                item["valid_workload"] = False
                measured.append(item)
                continue

            def request(session=client):
                start = time.perf_counter()
                r = session.get(url, timeout=120)
                r.raise_for_status()
                b = r.json()
                if b.get("code", 0) not in (0, 200):
                    raise RuntimeError("Business failure during measured workload")
                return (time.perf_counter() - start) * 1000

            for _ in range(3):
                request()
            sequential = [request() for _ in range(25)]

            def concurrent_request(_):
                with requests.Session() as s:
                    s.headers.update(headers)
                    return request(s)

            with ThreadPoolExecutor(max_workers=4) as pool:
                concurrent = list(pool.map(concurrent_request, range(20)))

            def metrics(values):
                return {
                    "samples": len(values),
                    "median_ms": round(statistics.median(values), 3),
                    "p95_ms": round(sorted(values)[int(0.95 * (len(values) - 1))], 3),
                }

            item.update(
                valid_workload=True,
                sequential=metrics(sequential),
                concurrent_4=metrics(concurrent),
            )
            measured.append(item)
        report["apis"][name] = measured
    report["limits"] = [
        "Endpoints have differing business scope and payloads; this is not feature parity.",
        "Warm API responses only; browser page P95 and heavy background jobs are not measured.",
        "Old binary is a local release artifact; live production binary SHA could not be rechecked.",
        "Linux APIs share one constrained application slice; database remains Windows, not production MySQL 8.0.",
    ]
    Path("/tmp/linux-runtime-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
