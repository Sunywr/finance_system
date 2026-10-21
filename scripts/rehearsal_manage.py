"""Run Django commands against the owned rehearsal, leaving backend/.env untouched."""

import os
import subprocess
import sys
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
cfg = dotenv_values(root / "backups" / "migration-20261021" / "rehearsal.env")
if cfg.get("DB_NAME") != "finance_rehearsal":
    raise RuntimeError("Unexpected rehearsal database")
env = dict(
    os.environ,
    **{k: v for k, v in cfg.items() if v is not None},
    PYTHONIOENCODING="utf-8"
)
if __name__ == "__main__":
    sys.exit(
        subprocess.call(
            [sys.executable, str(root / "backend" / "manage.py"), *sys.argv[1:]],
            cwd=root / "backend",
            env=env,
        )
    )
