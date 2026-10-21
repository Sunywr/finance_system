import gzip
import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core import signing
from rest_framework.exceptions import ValidationError, PermissionDenied
from .ingest import PUBLIC_TABLES, SENSITIVE_TABLES
from .models import ArchiveShard
from .scope import household_owner_ids
from .source import SECRET_WORDS

DICTIONARIES = {
    "account_category",
    "account_label",
    "account_investcategory",
    "account_assetcategory",
    "account_debtcategory",
    "cash_account_category",
}


def redact(value):
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, dict):
        return value
    if "__encrypted__" in value:
        return "[已保护]"
    return {
        k: (
            "[已保护]" if any(word in k.lower() for word in SECRET_WORDS) else redact(v)
        )
        for k, v in value.items()
    }


def path_for(shard):
    root = Path(settings.LEGACY_ARCHIVE_ROOT).resolve()
    path = (root / shard.relative_path).resolve()
    if not path.is_relative_to(root):
        raise RuntimeError("Archive path outside configured root")
    return path


def page(user, params):
    table = params.get("table", "")
    if table in SENSITIVE_TABLES:
        raise PermissionDenied("该资料包含认证配置，请使用专用设置页面")
    if not ArchiveShard.objects.filter(table=table).exists():
        raise ValidationError({"table": "请选择有效资料类型"})
    try:
        limit = min(max(int(params.get("page_size", 50)), 1), 100)
    except ValueError:
        raise ValidationError({"page_size": "无效页大小"})
    filters = {
        k: str(params.get(k, "")).strip()
        for k in ("table", "code", "start_date", "end_date", "source_pk")
    }
    for name in ("start_date", "end_date"):
        if filters[name]:
            from datetime import date

            try:
                date.fromisoformat(filters[name])
            except ValueError:
                raise ValidationError({name: "日期格式应为 YYYY-MM-DD"})
    shard_id = 0
    offset = 0
    cursor = params.get("cursor")
    if cursor:
        try:
            state = signing.loads(cursor, salt="legacy-archive", max_age=86400)
            if state["user"] != user.pk or state["filters"] != filters:
                raise ValueError()
            shard_id, offset = state["shard"], state["offset"]
        except Exception:
            raise ValidationError({"cursor": "游标已失效，请重新查询"})
    owners = set(household_owner_ids(user))
    items = []
    scanned = 0
    next_state = None
    shards = ArchiveShard.objects.filter(table=table, pk__gte=shard_id).order_by("pk")
    if filters["start_date"]:
        shards = shards.exclude(max_date__lt=filters["start_date"])
    if filters["end_date"]:
        shards = shards.exclude(min_date__gt=filters["end_date"])
    for shard in shards.iterator():
        if table not in PUBLIC_TABLES | DICTIONARIES and not owners.intersection(
            shard.owner_ids
        ):
            continue
        path = path_for(shard)
        # Every opened shard is authenticated before any row is returned.
        sha = hashlib.sha256()
        with path.open("rb") as h:
            for b in iter(lambda: h.read(1024 * 1024), b""):
                sha.update(b)
        if sha.hexdigest() != shard.sha256:
            raise ValidationError("资料校验失败，已停止读取")
        with gzip.open(path, "rt", encoding="utf8") as h:
            for line_no, line in enumerate(h):
                if shard.pk == shard_id and line_no < offset:
                    continue
                scanned += 1
                r = json.loads(line)
                visible = r["owner_id"] in owners or (
                    r["owner_id"] is None and table in PUBLIC_TABLES | DICTIONARIES
                )
                match = (
                    visible
                    and (not filters["code"] or r["code"] == filters["code"])
                    and (
                        not filters["source_pk"]
                        or r["source_pk"] == filters["source_pk"]
                    )
                )
                day = r["business_date"]
                if filters["start_date"]:
                    match = match and day is not None and day >= filters["start_date"]
                if filters["end_date"]:
                    match = match and day is not None and day <= filters["end_date"]
                if match:
                    items.append(
                        dict(
                            source_pk=r["source_pk"],
                            business_date=day,
                            code=r["code"],
                            owner_id=r["owner_id"],
                            payload=redact(r["payload"]),
                        )
                    )
                if len(items) >= limit or scanned >= 5000:
                    next_state = dict(
                        user=user.pk,
                        filters=filters,
                        shard=shard.pk,
                        offset=line_no + 1,
                    )
                    break
        if next_state:
            break
    return {
        "results": items,
        "next_cursor": (
            signing.dumps(next_state, salt="legacy-archive", compress=True)
            if next_state
            else None
        ),
        "scanned": scanned,
    }
