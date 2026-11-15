from django.conf import settings
from django.db import models
from django.utils import timezone


class Organization(models.Model):
    class Tier(models.TextChoices):
        FREE = "free", "Free"
        FULL = "full", "Full"

    name = models.CharField(max_length=200, unique=True)
    access_tier = models.CharField(max_length=10, choices=Tier.choices, default=Tier.FREE)
    # Time-boxed full access for free orgs (e.g. a trial window).
    full_access_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name

    def has_full_access(self, now=None):
        now = now or timezone.now()
        if self.access_tier == self.Tier.FULL:
            return True
        return bool(self.full_access_until and self.full_access_until > now)


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="members")

    def __str__(self):
        return f"{self.user} @ {self.organization}"
