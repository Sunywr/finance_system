"""Serve the existing frontend build and the owned rehearsal, on loopback only.

Use --benchmark-clone only for UI testing with disposable clone credentials.
The original backend/.env and frontend configuration are never rewritten.
"""

import argparse
import http.client
import json
import os
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from rehearsal_manage import cfg, root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-clone", action="store_true")
    args = parser.parse_args()
    env = dict(
        os.environ,
        **{k: v for k, v in cfg.items() if v is not None},
        PYTHONIOENCODING="utf-8"
    )
    if args.benchmark_clone:
        env["DB_NAME"] = "finance_rehearsal_runtime"
    log_path = root / "backups/migration-20261021/preview.log"
    with log_path.open("ab") as log:
        api = subprocess.Popen(
            [
                sys.executable,
                str(root / "backend/manage.py"),
                "runserver",
                "127.0.0.1:8001",
                "--noreload",
            ],
            cwd=root / "backend",
            env=env,
            stdout=log,
            stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(root / "frontend/dist"), **kw)

        def proxy(self):
            size = int(self.headers.get("Content-Length", "0"))
            if size > 2 * 1024 * 1024:
                self.send_error(413)
                return
            headers = {
                k: v
                for k, v in self.headers.items()
                if k.lower() not in {"host", "connection"}
            }
            connection = http.client.HTTPConnection("127.0.0.1", 8001, timeout=120)
            try:
                connection.request(
                    self.command,
                    self.path,
                    body=self.rfile.read(size) if size else None,
                    headers=headers,
                )
                response = connection.getresponse()
                body = response.read()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in {
                        "connection",
                        "transfer-encoding",
                        "content-length",
                    }:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                self.send_error(502, "Rehearsal API is starting or unavailable")
            finally:
                connection.close()

        def do_GET(self):
            if self.path.startswith("/api/"):
                return self.proxy()
            if not self.path.startswith("/assets/") and self.path.split("?")[0] not in {
                "/",
                "/index.html",
                "/favicon.ico",
            }:
                self.path = "/index.html"
            return super().do_GET()

        def do_POST(self):
            return (
                self.proxy() if self.path.startswith("/api/") else self.send_error(405)
            )

        def do_PATCH(self):
            return (
                self.proxy() if self.path.startswith("/api/") else self.send_error(405)
            )

        def do_DELETE(self):
            return (
                self.proxy() if self.path.startswith("/api/") else self.send_error(405)
            )

        def do_PUT(self):
            return (
                self.proxy() if self.path.startswith("/api/") else self.send_error(405)
            )

        def log_message(self, *a):
            pass

    try:
        with ThreadingHTTPServer(("127.0.0.1", 5174), Handler) as server:
            (log_path.parent / "preview-process.json").write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "api_pid": api.pid,
                        "database": env["DB_NAME"],
                        "url": "http://127.0.0.1:5174/history",
                    },
                    indent=2,
                )
            )
            print("Rehearsal preview at http://127.0.0.1:5174/history", flush=True)
            server.serve_forever()
    finally:
        api.terminate()
        api.wait(timeout=15)


if __name__ == "__main__":
    main()
