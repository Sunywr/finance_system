from django.db.models import Q, Sum

from apps.common.utils.money import D

from .models import Asset


def linked_transactions(asset):
    from apps.ledger.models import Transaction

    return (
        Transaction.objects.filter(asset=asset, status=Transaction.Status.POSTED)
        .select_related("category", "account")
        .order_by("-occurred_at", "-id")
    )


def asset_value(asset):
    if asset.valuation_mode == Asset.ValuationMode.MANUAL:
        latest = asset.valuations.order_by("-valued_at", "-id").first()
        return D(latest.value) if latest else D(asset.manual_value)
    from apps.ledger.models import Transaction

    agg = linked_transactions(asset).aggregate(
        expense=Sum("asset_amount", filter=Q(type=Transaction.Type.EXPENSE)),
        refund=Sum("asset_amount", filter=Q(type=Transaction.Type.REFUND)),
    )
    return D(agg["expense"] or 0) - D(agg["refund"] or 0)


def asset_summary(asset):
    return {
        "current_value": asset_value(asset),
        "linked_count": linked_transactions(asset).count(),
        "valuation_mode": asset.valuation_mode,
    }
