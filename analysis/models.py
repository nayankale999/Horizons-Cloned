from django.conf import settings
from django.db import models


class SavedSearch(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches")
    name = models.CharField(max_length=120)
    params = models.JSONField(default=dict)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "name")]
        ordering = ["name"]

    def __str__(self):
        return self.name
