"""Report generation with the same start → poll → download contract as the original.

Generation runs inline here; swap `_run` onto Celery/RQ when reports get slow.
"""

import csv
import io

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from analysis import search as svc

from .models import ReportTask

COLUMNS = [
    ("region", "Region"), ("active_substance", "Active substance"), ("brand", "Brand"),
    ("indication", "Indication"), ("dosage_form", "Dosage form"), ("strength", "Strength"),
    ("revenue_musd", "Revenue ($M)"), ("earliest_generic_launch", "Earliest generic launch"),
    ("marketing_exclusivity", "Marketing exclusivity"), ("data_exclusivity", "Data exclusivity"),
    ("main_patent_expiry", "Main patent expiry"), ("ftf_anda_filers", "FTF / ANDA filers"),
    ("api_manufacturers", "API manufacturers"), ("api_consumption_kg", "API consumption (kg)"),
]


def _org(user):
    profile = getattr(user, "profile", None)
    return profile.organization if profile else None


def _run(task):
    try:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([label for _, label in COLUMNS])
        for market in svc.search(task.params, _org(task.user)):
            row = svc.serialize(market)
            writer.writerow([row[key] if row[key] is not None else "" for key, _ in COLUMNS])
        task.content = buf.getvalue()
        task.status = ReportTask.Status.SUCCESS
    except Exception as exc:  # report the failure to the poller instead of a 500
        task.status = ReportTask.Status.FAILURE
        task.error = str(exc)
    task.save()


@login_required
def my_reports(request):
    return render(request, "reports/myreports.html", {"tasks": request.user.report_tasks.all()[:50]})


@login_required
@require_POST
def generate(request):
    task = ReportTask.objects.create(user=request.user, params=svc.normalize(request.POST))
    _run(task)
    return JsonResponse({"task_id": str(task.id)})


@login_required
def status(request, task_id):
    task = get_object_or_404(ReportTask, pk=task_id, user=request.user)
    data = {"task_id": str(task.id), "status": task.status, "error": task.error}
    if task.status == ReportTask.Status.SUCCESS:
        data["download_url"] = reverse("reports:download", args=[task.id])
    return JsonResponse(data)


@login_required
def download(request, task_id):
    task = get_object_or_404(ReportTask, pk=task_id, user=request.user, status=ReportTask.Status.SUCCESS)
    response = HttpResponse(task.content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="report-{task.created:%Y%m%d-%H%M}.csv"'
    return response
