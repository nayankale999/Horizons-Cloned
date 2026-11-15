from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from analysis.search import serialize

from .models import ListItem, ProductCountry, ProductList


def _org(request):
    profile = getattr(request.user, "profile", None)
    if profile is None:
        raise Http404("User has no organisation.")
    return profile.organization


def _lists(org, kind):
    lists = org.product_lists.filter(kind=kind)
    if not lists.exists():
        default = "My Portfolio" if kind == ProductList.Kind.PORTFOLIO else "Play Area"
        ProductList.objects.create(organization=org, kind=kind, name=default)
        lists = org.product_lists.filter(kind=kind)
    return lists


def _list_page(request, kind, list_id=None):
    org = _org(request)
    lists = _lists(org, kind)
    current = get_object_or_404(lists, pk=list_id) if list_id else lists.first()
    items = current.items.select_related(
        "market__product__indication", "market__product__dosage_form", "market__region", "added_by"
    )
    rows = []
    for item in items:
        row = serialize(item.market)
        row.update(item_id=item.id, notes=item.notes,
                   added_by=item.added_by.get_username() if item.added_by else "",
                   added_on=item.added_on.date().isoformat())
        rows.append(row)
    return render(request, "products/list.html", {
        "kind": kind, "kind_label": ProductList.Kind(kind).label,
        "lists": lists, "current": current, "rows": rows,
        "playareas": org.product_lists.filter(kind=ProductList.Kind.PLAYAREA),
    })


@login_required
def portfolio(request, list_id=None):
    return _list_page(request, ProductList.Kind.PORTFOLIO, list_id)


@login_required
def playarea(request, list_id=None):
    return _list_page(request, ProductList.Kind.PLAYAREA, list_id)


@login_required
@require_POST
def create_playarea(request):
    org = _org(request)
    name = request.POST.get("name", "").strip() or f"Play Area {org.product_lists.filter(kind='playarea').count() + 1}"
    lst, _ = ProductList.objects.get_or_create(organization=org, kind=ProductList.Kind.PLAYAREA, name=name)
    return redirect("products:playarea_detail", list_id=lst.pk)


@login_required
@require_POST
def add_to_list(request):
    """Add one or more ProductCountry rows (market_ids[]) to a list."""
    org = _org(request)
    target = get_object_or_404(ProductList, pk=request.POST.get("list_id"), organization=org)
    ids = request.POST.getlist("market_ids[]") or request.POST.getlist("market_ids")
    added = 0
    for market in ProductCountry.objects.filter(pk__in=ids):
        _, created = ListItem.objects.get_or_create(
            product_list=target, market=market, defaults={"added_by": request.user}
        )
        added += created
    return JsonResponse({"data": {"added": added, "list": target.name}})


@login_required
@require_POST
def item_note(request, item_id):
    item = get_object_or_404(ListItem, pk=item_id, product_list__organization=_org(request))
    item.notes = request.POST.get("notes", "")
    item.save(update_fields=["notes"])
    return JsonResponse({"data": {"id": item.id, "notes": item.notes}})


@login_required
@require_POST
def delete_item(request, item_id):
    item = get_object_or_404(ListItem, pk=item_id, product_list__organization=_org(request))
    item.delete()
    return JsonResponse({"data": {"deleted": item_id}})


@login_required
def org_products_count(request):
    org = _org(request)
    return JsonResponse({"data": {
        lst.name: lst.items.count() for lst in org.product_lists.all()
    }})
