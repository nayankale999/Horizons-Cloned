from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render

from .models import DosageForm, Excipient, Indication, Region, Year

TABLES = {
    "indications": (Indication, "Indications", True),
    "regions": (Region, "Available Regions", True),
    "dosages": (DosageForm, "Finished Dosages", True),
    "years": (Year, "Years", True),
    "excipients": (Excipient, "Excipients", False),
}


@login_required
def lookup_list(request, table):
    if table not in TABLES:
        raise Http404
    model, title, show_color = TABLES[table]
    q = request.GET.get("q", "").strip()
    qs = model.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "reference/list.html", {
        "title": title, "page": page, "q": q, "show_color": show_color, "table": table,
    })
