import json
from pathlib import Path
from django.core.management.base import BaseCommand
from apps.legacy.source import Source, assert_target


class Command(BaseCommand):
    help = "从固定的只读本地生产副本迁移、归档并验证；拒绝生产和现有 finance 库"

    def add_arguments(self, p):
        p.add_argument("--source", required=True)
        p.add_argument("--output", required=True)
        p.add_argument(
            "--phase",
            choices=["inspect", "ingest", "project", "verify", "all"],
            default="all",
        )
        p.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **o):
        source = Source(o["source"])
        output = Path(o["output"]).resolve()
        try:
            if o["dry_run"] or o["phase"] == "inspect":
                self.stdout.write(
                    json.dumps(
                        {
                            "tables": source.tables,
                            "source_uuid": source.config["server_uuid"],
                            "source_read_only": True,
                        }
                    )
                )
                return
            assert_target()
            from apps.legacy.models import MigrationBatch
            from apps.legacy.ingest import ingest

            if o["phase"] in ("ingest", "all"):
                batch, _ = ingest(source, output)
            else:
                batch = MigrationBatch.objects.get(
                    snapshot_sha256=source.config["snapshot_sha256"]
                )
            if "snapshot_finished_at" not in batch.source_identity:
                manifest = json.loads((output / "manifest.json").read_text())
                batch.source_identity.update(
                    snapshot_finished_at=manifest["finished_at"],
                    source_server=manifest["identity"],
                )
                batch.save(update_fields=["source_identity"])
            if o["phase"] in ("project", "all"):
                from apps.legacy.project import Projector

                self.stdout.write(json.dumps(Projector(source, batch).run()))
            if o["phase"] in ("verify", "all"):
                from apps.legacy.verify import verify

                report = verify(source, batch, output)
                self.stdout.write(json.dumps(report, ensure_ascii=False, default=str))
        finally:
            source.close()
