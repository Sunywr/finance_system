"""Compare every new database table before and after repeating projection."""

import json
import subprocess
import sys
from migration_roundtrip import OUT, ROOT, hashes, assert_target


def main():
    assert_target()
    cfg = json.loads((OUT / "instance.json").read_text())
    before = hashes(cfg["root"], "finance_rehearsal")
    with (OUT / "idempotence.log").open("wb") as log:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "rehearsal_manage.py"),
                "legacy_migrate",
                "--source",
                str(OUT / "source.json"),
                "--output",
                str(OUT),
                "--phase",
                "project",
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    after = hashes(cfg["root"], "finance_rehearsal")
    changed = [t for t in before if before[t] != after.get(t)]
    report = {
        "passed": before == after,
        "tables": len(before),
        "rows_before": sum(v["rows"] for v in before.values()),
        "rows_after": sum(v["rows"] for v in after.values()),
        "changed_tables": changed,
        "before": before,
        "after": after,
    }
    (OUT / "idempotence.json").write_text(json.dumps(report, indent=2), encoding="utf8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("before", "after")}))
    if changed:
        raise RuntimeError("Repeated projection changed existing records")


if __name__ == "__main__":
    main()
