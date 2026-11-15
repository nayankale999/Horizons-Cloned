from django.contrib import admin

from .models import ListItem, Product, ProductCountry, ProductList


class ProductCountryInline(admin.TabularInline):
    model = ProductCountry
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("active_substance", "brand", "indication", "dosage_form")
    list_filter = ("indication", "dosage_form")
    search_fields = ("active_substance", "brand", "innovator")
    filter_horizontal = ("keywords", "excipients")
    inlines = [ProductCountryInline]


admin.site.register(ProductCountry)
admin.site.register(ProductList)
admin.site.register(ListItem)
