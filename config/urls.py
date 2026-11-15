from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from dashboard.views import dashboard
from orgs.views import my_profile
from reference.views import lookup_list

orgs_patterns = ([
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("myprofile/", my_profile, name="profile"),
], "orgs")

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("dashboard/", dashboard),
    path("orgs/", include(orgs_patterns)),
    path("login/", auth_views.LoginView.as_view(template_name="orgs/login.html"), name="login"),
    path("analysis/", include("analysis.urls")),
    path("newproducts/", include("products.urls")),
    path("myreports/", include("reports.urls")),
    path("ref/<slug:table>/", lookup_list, name="lookup"),
    path("admin/", admin.site.urls),
]
