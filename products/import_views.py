"""Staff-only upload → preview (dry run) → confirm flow for product imports."""

import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .importer import ImportFileError, import_file, template_csv

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".txt", ".xlsx", ".xlsm"}
SESSION_KEY = "pending_import"


def _upload_dir():
    path = Path(settings.IMPORT_UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _discard_pending(request):
    pending = request.session.pop(SESSION_KEY, None)
    if pending:
        Path(pending["path"]).unlink(missing_ok=True)


def _run(path, name, opts, dry_run):
    with open(path, "rb") as fh:
        return import_file(fh, name, dry_run=dry_run, **opts)


@staff_member_required
def import_page(request):
    context = {"opts": {"create_lookups": False, "skip_invalid": False}}
    if request.method == "POST":
        upload = request.FILES.get("file")
        opts = {"create_lookups": bool(request.POST.get("create_lookups")),
                "skip_invalid": bool(request.POST.get("skip_invalid"))}
        context["opts"] = opts
        suffix = Path(upload.name).suffix.lower() if upload else ""
        if not upload:
            messages.error(request, "Choose a file to upload.")
        elif suffix not in ALLOWED_SUFFIXES:
            messages.error(request, "Upload a .csv or .xlsx file.")
        elif upload.size > MAX_UPLOAD_BYTES:
            messages.error(request, "File is larger than 20 MB.")
        else:
            _discard_pending(request)
            path = _upload_dir() / f"{uuid.uuid4().hex}{suffix}"
            with open(path, "wb") as out:
                for chunk in upload.chunks():
                    out.write(chunk)
            try:
                result = _run(path, upload.name, opts, dry_run=True)
            except ImportFileError as exc:
                path.unlink(missing_ok=True)
                messages.error(request, str(exc))
            else:
                can_apply = (result.rows_imported > 0) and (not result.errors or opts["skip_invalid"])
                if can_apply:
                    request.session[SESSION_KEY] = {"path": str(path), "name": upload.name, "opts": opts}
                else:
                    path.unlink(missing_ok=True)
                context.update(result=result, filename=upload.name, can_apply=can_apply,
                               errors=result.errors[:300])
    return render(request, "products/import.html", context)


@staff_member_required
@require_POST
def import_confirm(request):
    pending = request.session.get(SESSION_KEY)
    if not pending or not Path(pending["path"]).is_file():
        messages.error(request, "That upload has expired; upload the file again.")
        return redirect("products:import")
    try:
        result = _run(pending["path"], pending["name"], pending["opts"], dry_run=False)
    except ImportFileError as exc:
        messages.error(request, str(exc))
    else:
        level = messages.SUCCESS if result.applied else messages.ERROR
        messages.add_message(request, level, f"{pending['name']}: {result.summary()}")
    _discard_pending(request)
    return redirect("products:import")


@staff_member_required
@require_POST
def import_cancel(request):
    _discard_pending(request)
    return redirect("products:import")


@staff_member_required
def import_template(request):
    response = HttpResponse(template_csv(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="product-import-template.csv"'
    return response
