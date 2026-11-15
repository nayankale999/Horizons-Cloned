from django.urls import path

from . import import_views, views

app_name = "products"

urlpatterns = [
    path("import/", import_views.import_page, name="import"),
    path("import/confirm/", import_views.import_confirm, name="import_confirm"),
    path("import/cancel/", import_views.import_cancel, name="import_cancel"),
    path("import/template.csv", import_views.import_template, name="import_template"),
    path("portfolio/", views.portfolio, name="portfolio"),
    path("portfolio/<int:list_id>/", views.portfolio, name="portfolio_detail"),
    path("playarea/", views.playarea, name="playarea"),
    path("playarea/<int:list_id>/", views.playarea, name="playarea_detail"),
    path("playarea/new/", views.create_playarea, name="playarea_create"),
    path("add/", views.add_to_list, name="add"),
    path("item/<int:item_id>/note/", views.item_note, name="item_note"),
    path("item/<int:item_id>/delete/", views.delete_item, name="item_delete"),
    path("count/", views.org_products_count, name="count"),
]
