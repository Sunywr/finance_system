from decimal import Decimal
import json
from pathlib import Path
from django.contrib.auth import get_user_model
from django.db.models import Sum
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.accounts.services import cash_balance
from apps.debts.models import DebtItem
from apps.investments.services import portfolio_summary
from .archive import page
from .models import ArchiveShard, LegacyRecord, MigrationBatch
from .scope import household_owner_ids


class HistoryView(APIView):
    def get(self, request):
        return Response(page(request.user, request.query_params))


class HistoryTypesView(APIView):
    def get(self, request):
        from .ingest import PUBLIC_TABLES, SENSITIVE_TABLES
        from .archive import DICTIONARIES

        owners = set(household_owner_ids(request.user))
        tables = set()
        for s in ArchiveShard.objects.exclude(table__in=SENSITIVE_TABLES).only(
            "table", "owner_ids"
        ):
            if (
                owners.intersection(s.owner_ids)
                or s.table in PUBLIC_TABLES | DICTIONARIES
            ):
                tables.add(s.table)
        labels = json.loads(
            Path(__file__).with_name("table_labels.json").read_text(encoding="utf8")
        )
        return Response(
            {
                "tables": sorted(tables),
                "labels": {t: labels.get(t, t) for t in tables},
                "household_owner_ids": sorted(owners),
            }
        )


class HouseholdSummaryView(APIView):
    def get(self, request):
        result = []
        for user in get_user_model().objects.filter(
            pk__in=household_owner_ids(request.user)
        ):
            debts = DebtItem.objects.filter(owner=user).exclude(
                status__in=["PAID", "CANCELLED"]
            )
            debt = sum((d.payable_amount for d in debts), Decimal(0))
            result.append(
                {
                    "owner_id": user.pk,
                    "name": user.get_full_name() or user.username,
                    "cash_balance": cash_balance(user),
                    "pending_debt": debt,
                    "portfolio": portfolio_summary(user)["totals"],
                }
            )
        return Response(
            {
                "members": result,
                "cash_balance": sum((r["cash_balance"] for r in result), Decimal(0)),
                "pending_debt": sum((r["pending_debt"] for r in result), Decimal(0)),
            }
        )


class MigrationStatusView(APIView):
    def get(self, request):
        batch = MigrationBatch.objects.order_by("-pk").first()
        if not batch:
            return Response({"state": "EMPTY"})
        result = {
            "state": batch.state,
            "completed_at": batch.completed_at,
            "full_replacement_ready": False,
        }
        if request.user.is_staff:
            result.update(
                report=batch.report,
                issues=list(
                    batch.migrationissue_set.values(
                        "severity", "table", "reason"
                    ).distinct()
                ),
            )
        return Response(result)
