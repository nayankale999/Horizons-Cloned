from django.contrib import admin

from .models import DosageForm, Excipient, Indication, Keyword, Region, Year

for model in (Indication, Region, DosageForm, Year, Excipient, Keyword):
    admin.site.register(model, list_display=("name", "bg_color", "description"), search_fields=("name",))
