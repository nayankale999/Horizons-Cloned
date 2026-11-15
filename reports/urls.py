from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.my_reports, name="home"),
    path("generatereports/", views.generate, name="generate"),
    path("reports/status/<uuid:task_id>/", views.status, name="status"),
    path("reports/download/<uuid:task_id>/", views.download, name="download"),
]
