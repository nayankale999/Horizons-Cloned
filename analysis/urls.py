from django.urls import path

from . import views

app_name = "analysis"

urlpatterns = [
    path("", views.analysis_home, name="home"),
    path("getanalysisdata/", views.get_analysis_data, name="data"),
    path("getproductnames/", views.get_product_names, name="product_names"),
    path("getsinglepdt/<int:market_id>/", views.get_single_product, name="single_product"),
    path("savedsearch/<int:pk>/", views.get_saved_search, name="saved_get"),
    path("savedsearch/create/", views.create_saved_search, name="saved_create"),
    path("savedsearch/<int:pk>/update/", views.update_saved_search, name="saved_update"),
    path("savedsearch/<int:pk>/delete/", views.delete_saved_search, name="saved_delete"),
]
