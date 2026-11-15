from django.db import models


class Lookup(models.Model):
    """Reference value with a display colour used for badges and chart series."""

    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    bg_color = models.CharField(max_length=7, default="#6c757d")

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Indication(Lookup):
    pass


class Region(Lookup):
    pass


class DosageForm(Lookup):
    pass


class Year(Lookup):
    class Meta(Lookup.Meta):
        ordering = ["name"]


class Excipient(Lookup):
    pass


class Keyword(Lookup):
    pass
