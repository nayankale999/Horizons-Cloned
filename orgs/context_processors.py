from django.conf import settings
from django.utils import timezone


def site(request):
    ctx = {"SITE_NAME": settings.SITE_NAME, "org": None, "full_access_minutes_left": None}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and hasattr(user, "profile"):
        org = user.profile.organization
        ctx["org"] = org
        if org.access_tier == org.Tier.FREE and org.full_access_until and org.full_access_until > timezone.now():
            ctx["full_access_minutes_left"] = int((org.full_access_until - timezone.now()).total_seconds() // 60)
    return ctx
