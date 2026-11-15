from django.conf import settings
from django.db import models

from orgs.models import Organization
from reference.models import DosageForm, Excipient, Indication, Keyword, Region

REVENUE_BANDS = [
    ("lt10", "< $10M", 0, 10),
    ("10-50", "$10–50M", 10, 50),
    ("50-100", "$50–100M", 50, 100),
    ("100-250", "$100–250M", 100, 250),
    ("250-500", "$250–500M", 250, 500),
    ("500-1000", "$500M–1B", 500, 1000),
    ("gt1000", "> $1B", 1000, None),
]

API_MANUFACTURER_BANDS = [
    ("0", "None", 0, 0),
    ("1-2", "1–2", 1, 2),
    ("3-5", "3–5", 3, 5),
    ("6-10", "6–10", 6, 10),
    ("gt10", "> 10", 11, None),
]


class Product(models.Model):
    class Solubility(models.TextChoices):
        HIGH = "high", "High"
        MODERATE = "moderate", "Moderate"
        LOW = "low", "Low"
        VERY_LOW = "very_low", "Very low"
        UNKNOWN = "unknown", "Unknown"

    active_substance = models.CharField(max_length=200)
    brand = models.CharField(max_length=200, blank=True)
    innovator = models.CharField(max_length=200, blank=True)
    therapeutic_category = models.CharField(max_length=200, blank=True)
    indication = models.ForeignKey(Indication, on_delete=models.PROTECT, related_name="products")
    dosage_form = models.ForeignKey(DosageForm, on_delete=models.PROTECT, related_name="products")
    strength = models.CharField(max_length=120, blank=True)
    keywords = models.ManyToManyField(Keyword, blank=True, related_name="products")
    excipients = models.ManyToManyField(Excipient, blank=True, related_name="products")
    xlogp = models.FloatField(null=True, blank=True)
    logp = models.FloatField(null=True, blank=True)
    molecular_weight = models.FloatField(null=True, blank=True)
    solubility = models.CharField(max_length=10, choices=Solubility.choices, default=Solubility.UNKNOWN)

    class Meta:
        ordering = ["active_substance"]

    def __str__(self):
        return f"{self.active_substance} ({self.dosage_form})"


class ProductCountry(models.Model):
    """Market-specific facts for a product in one region."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="markets")
    region = models.ForeignKey(Region, on_delete=models.PROTECT, related_name="markets")
    revenue_musd = models.DecimalField("Revenue ($M)", max_digits=10, decimal_places=2, null=True, blank=True)
    earliest_generic_launch = models.DateField(null=True, blank=True)
    marketing_exclusivity = models.DateField("Marketing exclusivity (ME/NCE/NDA)", null=True, blank=True)
    data_exclusivity = models.DateField("Data exclusivity (DE/NCE-1)", null=True, blank=True)
    main_patent_expiry = models.DateField(null=True, blank=True)
    patent_extension = models.DateField(null=True, blank=True)
    other_blocking_patent = models.CharField(max_length=255, blank=True)
    key_patents = models.TextField(blank=True)
    ftf_anda_filers = models.PositiveIntegerField("FTF / ANDA filers", default=0)
    post_generic_6m = models.PositiveIntegerField("Post-generic tracker (6M)", default=0)
    api_manufacturers = models.PositiveIntegerField(default=0)
    api_consumption_kg = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    suggested_strategy = models.TextField(blank=True)

    class Meta:
        unique_together = [("product", "region")]
        ordering = ["earliest_generic_launch"]

    def __str__(self):
        return f"{self.product.active_substance} – {self.region}"

    @property
    def revenue_band(self):
        if self.revenue_musd is None:
            return None
        value = float(self.revenue_musd)
        for code, label, low, high in REVENUE_BANDS:
            if value >= low and (high is None or value < high):
                return label
        return None


class ProductList(models.Model):
    """An organisation's portfolio or one of its play areas."""

    class Kind(models.TextChoices):
        PORTFOLIO = "portfolio", "Portfolio"
        PLAYAREA = "playarea", "Play Area"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="product_lists")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    name = models.CharField(max_length=120)

    class Meta:
        unique_together = [("organization", "kind", "name")]
        ordering = ["-kind", "name"]  # portfolio before play areas

    def __str__(self):
        return f"{self.organization}: {self.name}"


class ListItem(models.Model):
    product_list = models.ForeignKey(ProductList, on_delete=models.CASCADE, related_name="items")
    market = models.ForeignKey(ProductCountry, on_delete=models.CASCADE, related_name="list_items")
    notes = models.TextField(blank=True)
    added_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    added_on = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("product_list", "market")]
        ordering = ["-added_on"]
