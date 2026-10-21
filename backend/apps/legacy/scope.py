from .models import Membership


def household_owner_ids(user):
    """Same active membership scope for users and superusers; no global bypass."""
    groups = Membership.objects.filter(
        user=user, is_active=True, household__is_active=True
    ).values("household_id")
    ids = list(
        Membership.objects.filter(
            household_id__in=groups, is_active=True, user__is_active=True
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    return sorted(set(ids or [user.pk]))
