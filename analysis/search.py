"""Search over ProductCountry rows, driven by the Analysis page's parameters.

Parameters arrive as a QueryDict (form POST) or a plain dict (saved searches),
so every getter accepts both.
"""

from collections import Counter, defaultdict
from datetime import date

from django.db.models import Q

from products.models import API_MANUFACTURER_BANDS, REVENUE_BANDS, ProductCountry

DATE_FIELDS = {
    "launch": "earliest_generic_launch",
    "me": "marketing_exclusivity",
    "de": "data_exclusivity",
    "patent": "main_patent_expiry",
}
FILTER_KEYS = ("product", "regions", "indications", "dosages", "keywords", "excipients",
               "years", "revenue", "apis", "solubility", "my_org")


def _list(params, key):
    if hasattr(params, "getlist"):
        values = params.getlist(key) or params.getlist(key + "[]")
    else:
        values = params.get(key) or []
        if not isinstance(values, list):
            values = [values]
    return [v for v in values if v not in ("", None)]


def _one(params, key, default=""):
    value = params.get(key, default)
    return value[0] if isinstance(value, list) and value else (value or default)


def normalize(params):
    """Reduce request params to a JSON-safe dict (used for saved searches and reports)."""
    out = {key: _list(params, key) for key in FILTER_KEYS if key not in ("product", "my_org", "date_field")}
    out["product"] = _one(params, "product").strip()
    out["my_org"] = _one(params, "my_org") in ("1", "true", "on", True)
    out["date_field"] = _one(params, "date_field", "launch")
    return out


def is_search_set(params):
    p = normalize(params)
    return bool(p["product"] or p["my_org"] or any(p[k] for k in FILTER_KEYS if k not in ("product", "my_org")))


def _band_q(field, bands, selected):
    q = Q()
    for code, _label, low, high in bands:
        if code in selected:
            part = Q(**{f"{field}__gte": low})
            if high is not None:
                part &= Q(**{f"{field}__lte" if field == "api_manufacturers" else f"{field}__lt": high})
            q |= part
    return q


def search(params, organization=None):
    p = normalize(params)
    qs = ProductCountry.objects.select_related(
        "product", "product__indication", "product__dosage_form", "region"
    )
    if p["product"]:
        text = p["product"]
        qs = qs.filter(Q(product__active_substance__icontains=text) | Q(product__brand__icontains=text))
    if p["regions"]:
        qs = qs.filter(region_id__in=p["regions"])
    if p["indications"]:
        qs = qs.filter(product__indication_id__in=p["indications"])
    if p["dosages"]:
        qs = qs.filter(product__dosage_form_id__in=p["dosages"])
    if p["keywords"]:
        qs = qs.filter(product__keywords__in=p["keywords"])
    if p["excipients"]:
        qs = qs.filter(product__excipients__in=p["excipients"])
    if p["solubility"]:
        qs = qs.filter(product__solubility__in=p["solubility"])
    if p["years"]:
        field = DATE_FIELDS.get(p["date_field"], "earliest_generic_launch")
        qs = qs.filter(**{f"{field}__year__in": [int(y) for y in p["years"] if str(y).isdigit()]})
    if p["revenue"]:
        qs = qs.filter(_band_q("revenue_musd", REVENUE_BANDS, p["revenue"]))
    if p["apis"]:
        qs = qs.filter(_band_q("api_manufacturers", API_MANUFACTURER_BANDS, p["apis"]))
    if p["my_org"] and organization is not None:
        qs = qs.filter(list_items__product_list__organization=organization)
    return qs.distinct()


def _iso(value):
    return value.isoformat() if isinstance(value, date) else None


def serialize(market):
    product = market.product
    return {
        "id": market.id,
        "region": market.region.name,
        "region_color": market.region.bg_color,
        "active_substance": product.active_substance,
        "brand": product.brand,
        "innovator": product.innovator,
        "indication": product.indication.name,
        "indication_color": product.indication.bg_color,
        "therapeutic_category": product.therapeutic_category,
        "dosage_form": product.dosage_form.name,
        "dosage_color": product.dosage_form.bg_color,
        "strength": product.strength,
        "revenue_musd": float(market.revenue_musd) if market.revenue_musd is not None else None,
        "revenue_band": market.revenue_band,
        "earliest_generic_launch": _iso(market.earliest_generic_launch),
        "marketing_exclusivity": _iso(market.marketing_exclusivity),
        "data_exclusivity": _iso(market.data_exclusivity),
        "main_patent_expiry": _iso(market.main_patent_expiry),
        "ftf_anda_filers": market.ftf_anda_filers,
        "post_generic_6m": market.post_generic_6m,
        "api_manufacturers": market.api_manufacturers,
        "api_consumption_kg": float(market.api_consumption_kg) if market.api_consumption_kg is not None else None,
        "suggested_strategy": market.suggested_strategy,
    }


def chart_data(markets):
    """Aggregates for the Analysis chart panels."""
    value_by_year = defaultdict(float)
    off_patent_by_year = Counter()
    by_indication = Counter()
    by_dosage = Counter()
    revenue_vs_apis = []
    for m in markets:
        launch = m.earliest_generic_launch
        if launch:
            off_patent_by_year[launch.year] += 1
            if m.revenue_musd is not None:
                value_by_year[launch.year] += float(m.revenue_musd)
        by_indication[m.product.indication.name] += 1
        by_dosage[m.product.dosage_form.name] += 1
        if m.revenue_musd is not None:
            revenue_vs_apis.append({"x": m.api_manufacturers, "y": float(m.revenue_musd),
                                    "label": f"{m.product.active_substance} ({m.region.name})"})
    years = sorted(set(value_by_year) | set(off_patent_by_year))
    return {
        "years": years,
        "value_by_year": [round(value_by_year[y], 1) for y in years],
        "off_patent_by_year": [off_patent_by_year[y] for y in years],
        "top_indications": by_indication.most_common(10),
        "dosage_forms": by_dosage.most_common(),
        "revenue_vs_apis": revenue_vs_apis[:500],
    }
