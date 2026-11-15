from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST

from products.models import API_MANUFACTURER_BANDS, REVENUE_BANDS, Product, ProductCountry
from reference.models import DosageForm, Excipient, Indication, Keyword, Region, Year

from . import search as svc
from .models import SavedSearch

PAGE_LIMIT = 2000


def _org(request):
    profile = getattr(request.user, "profile", None)
    return profile.organization if profile else None


@login_required
def analysis_home(request):
    context = {
        "regions": Region.objects.all(),
        "indications": Indication.objects.all(),
        "dosages": DosageForm.objects.all(),
        "years": Year.objects.all(),
        "keywords": Keyword.objects.all(),
        "excipients": Excipient.objects.all(),
        "revenue_bands": REVENUE_BANDS,
        "api_bands": API_MANUFACTURER_BANDS,
        "solubility_choices": Product.Solubility.choices,
        "date_fields": [("launch", "Earliest generic launch"), ("me", "Marketing exclusivity"),
                        ("de", "Data exclusivity"), ("patent", "Main patent expiry")],
        "saved_searches": request.user.saved_searches.all(),
        "product_lists": _org(request).product_lists.all() if _org(request) else [],
    }
    return render(request, "analysis/analysis.html", context)


@login_required
@require_POST
def get_analysis_data(request):
    if not svc.is_search_set(request.POST):
        return JsonResponse({"data": {
            "IsRepSearchSet": False, "showpanel": True, "numproducts": 0, "repdata": [],
            "panelmessage": "Set at least one search parameter, then press Search.",
        }})
    markets = list(svc.search(request.POST, _org(request))[:PAGE_LIMIT])
    message = "" if markets else "No products match these parameters."
    return JsonResponse({"data": {
        "IsRepSearchSet": True, "showpanel": not markets, "panelmessage": message,
        "numproducts": len(markets), "truncated": len(markets) == PAGE_LIMIT,
        "repdata": [svc.serialize(m) for m in markets],
        "charts": svc.chart_data(markets),
    }})


@login_required
@require_GET
def get_product_names(request):
    term = request.GET.get("term", "").strip()
    names = []
    if len(term) >= 2:
        names = list(Product.objects.filter(active_substance__icontains=term)
                     .values_list("active_substance", flat=True).distinct()[:20])
    return JsonResponse({"results": [{"id": n, "text": n} for n in names]})


@login_required
@require_GET
def get_single_product(request, market_id):
    market = get_object_or_404(ProductCountry.objects.select_related("product"), pk=market_id)
    product = market.product
    siblings = product.markets.select_related("region").order_by("region__name")
    return JsonResponse({"data": {
        "market": svc.serialize(market),
        "properties": {
            "XLogP": product.xlogp, "LogP": product.logp,
            "Molecular weight": product.molecular_weight, "Solubility": product.get_solubility_display(),
            "Keywords": ", ".join(product.keywords.values_list("name", flat=True)),
            "Excipients": ", ".join(product.excipients.values_list("name", flat=True)),
        },
        "markets": [svc.serialize(m) for m in siblings],
    }})


# ---- Saved searches ----------------------------------------------------------

@login_required
@require_GET
def get_saved_search(request, pk):
    saved = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    return JsonResponse({"data": {"id": saved.pk, "name": saved.name, "params": saved.params}})


@login_required
@require_POST
def create_saved_search(request):
    name = request.POST.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Name is required."}, status=400)
    saved, created = SavedSearch.objects.update_or_create(
        user=request.user, name=name, defaults={"params": svc.normalize(request.POST)}
    )
    return JsonResponse({"data": {"id": saved.pk, "name": saved.name, "created": created}})


@login_required
@require_POST
def update_saved_search(request, pk):
    saved = get_object_or_404(SavedSearch, pk=pk, user=request.user)
    saved.params = svc.normalize(request.POST)
    saved.save(update_fields=["params", "updated"])
    return JsonResponse({"data": {"id": saved.pk, "name": saved.name}})


@login_required
@require_POST
def delete_saved_search(request, pk):
    get_object_or_404(SavedSearch, pk=pk, user=request.user).delete()
    return JsonResponse({"data": {"deleted": pk}})
