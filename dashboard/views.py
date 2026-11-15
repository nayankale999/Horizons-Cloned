from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone

from products.models import ProductCountry, ProductList

WINDOW_DAYS = 60
PANELS = [
    # (title, region name, date field)
    ("USA – earliest generic launch", "USA", "earliest_generic_launch"),
    ("Europe – earliest generic launch", "Europe", "earliest_generic_launch"),
    ("USA – NCE-1 date", "USA", "data_exclusivity"),
    ("Europe – data exclusivity expiry", "Europe", "data_exclusivity"),
]


@login_required
def dashboard(request):
    today = timezone.localdate()
    until = today + timedelta(days=WINDOW_DAYS)
    panels = []
    for title, region, field in PANELS:
        markets = (ProductCountry.objects.select_related("product__dosage_form")
                   .filter(region__name=region, **{f"{field}__range": (today, until)})
                   .order_by(field)[:25])
        panels.append({"title": title, "field": field, "markets": markets})

    profile = getattr(request.user, "profile", None)
    counts = {}
    if profile:
        for kind in ProductList.Kind:
            counts[kind.value] = sum(
                lst.items.count() for lst in profile.organization.product_lists.filter(kind=kind)
            )
    ticker = (ProductCountry.objects.select_related("product", "region")
              .filter(earliest_generic_launch__gte=today).order_by("earliest_generic_launch")[:12])
    return render(request, "dashboard/dashboard.html", {
        "panels": panels, "counts": counts, "ticker": ticker, "window_days": WINDOW_DAYS,
    })
