from django.contrib import admin

from .models import ReportTask

admin.site.register(ReportTask, list_display=("id", "user", "status", "created"))
