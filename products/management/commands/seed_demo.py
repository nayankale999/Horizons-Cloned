"""Populate the database with synthetic demo data.

All product names, companies and figures are randomly generated; nothing here
comes from any real dataset.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from orgs.models import Organization, Profile
from products.models import ListItem, Product, ProductCountry, ProductList
from reference.models import DosageForm, Excipient, Indication, Keyword, Region, Year

PALETTE = ["#0d6efd", "#6610f2", "#6f42c1", "#d63384", "#dc3545", "#fd7e14", "#ffc107",
           "#198754", "#20c997", "#0dcaf0", "#6c757d", "#795548"]

REGIONS = ["USA", "Europe", "UK", "Canada", "Australia", "Brazil", "Mexico", "Turkey"]
INDICATIONS = ["Oncology", "HIV", "Hepatitis", "Diabetes", "Cardiovascular", "Respiratory", "Immunology",
               "Neurology", "Psychiatry", "Rare Disease", "Dermatology", "Ophthalmology", "Infectious Disease",
               "Pain", "Haematology", "Endocrinology", "Gastroenterology", "Nephrology", "Women's Health", "Urology"]
DOSAGES = ["Tablet", "Capsule", "Oral Solution", "Injection (Vial)", "Injection (PFS)", "Infusion",
           "Inhaler", "Topical Cream", "Ophthalmic Solution", "Transdermal Patch", "Sublingual Tablet"]
KEYWORDS = ["Biologic", "BLA", "Complex generic", "Controlled substance", "Cytotoxic", "Peptide", "Long-acting",
            "Orphan", "Sterile", "Paragraph IV", "505(b)(2)", "Device combination", "Liposomal", "Lyophilised"]
EXCIPIENTS = ["Microcrystalline cellulose", "Lactose monohydrate", "Magnesium stearate", "Croscarmellose sodium",
              "Povidone", "Hypromellose", "Mannitol", "Sucrose", "Polysorbate 80", "Sodium chloride",
              "Colloidal silicon dioxide", "Talc", "Titanium dioxide", "Sodium starch glycolate",
              "Polyethylene glycol 400", "Benzyl alcohol", "Citric acid", "Trehalose", "Histidine", "Glycine"]
CATEGORIES = ["Antiviral", "Kinase inhibitor", "Monoclonal antibody", "GLP-1 agonist", "Anticoagulant",
              "Antipsychotic", "Corticosteroid", "Enzyme replacement", "Immunosuppressant", "Analgesic"]
STRATEGIES = ["Monitor FTF activity", "Early API sourcing recommended", "Partner for device component",
              "Low competition – prioritise", "Watch patent litigation", "Consider 505(b)(2) route", ""]

PREFIXES = ["Zen", "Vor", "Lum", "Tri", "Ox", "Cal", "Nef", "Bri", "Dax", "Pel", "Sor", "Ver", "Mir", "Tal", "Quin"]
MIDDLES = ["a", "e", "i", "o", "u", "ari", "eto", "ilo", "ova", "uri"]
SUFFIXES = ["vir", "tinib", "mab", "glutide", "xaban", "pril", "sartan", "zolam", "cept", "parin", "statin", "lukast"]
COMPANIES = ["Northwind Pharma", "Bluepeak Bio", "Corvane Therapeutics", "Alder & Finch", "Helix Meridian",
             "Stonebridge Labs", "Quayside Biologics", "Orrin Health"]


def _lookup(model, names, with_color=True):
    for i, name in enumerate(names):
        defaults = {"description": f"{name} (demo reference value)"}
        if with_color:
            defaults["bg_color"] = PALETTE[i % len(PALETTE)]
        model.objects.update_or_create(name=name, defaults=defaults)
    return list(model.objects.all())


def _maybe(rng, value, p=0.85):
    return value if rng.random() < p else None


class Command(BaseCommand):
    help = "Create synthetic reference data, products, a demo organisation and a demo user."

    def add_arguments(self, parser):
        parser.add_argument("--products", type=int, default=400)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo-pass-123")
        parser.add_argument("--flush", action="store_true", help="Delete existing products first.")

    @transaction.atomic
    def handle(self, *args, **opts):
        rng = random.Random(opts["seed"])
        today = timezone.localdate()

        regions = _lookup(Region, REGIONS)
        indications = _lookup(Indication, INDICATIONS)
        dosages = _lookup(DosageForm, DOSAGES)
        keywords = _lookup(Keyword, KEYWORDS)
        excipients = _lookup(Excipient, EXCIPIENTS, with_color=False)
        _lookup(Year, [str(y) for y in range(today.year - 2, today.year + 21)])

        if opts["flush"]:
            Product.objects.all().delete()

        names = set()
        while len(names) < opts["products"]:
            names.add(rng.choice(PREFIXES) + rng.choice(MIDDLES) + rng.choice(SUFFIXES))

        for name in sorted(names):
            product, created = Product.objects.get_or_create(
                active_substance=name.capitalize(),
                defaults=dict(
                    brand=(rng.choice(PREFIXES) + rng.choice(["ra", "lix", "dor", "vant", "qua"])).capitalize(),
                    innovator=rng.choice(COMPANIES),
                    therapeutic_category=rng.choice(CATEGORIES),
                    indication=rng.choice(indications),
                    dosage_form=rng.choice(dosages),
                    strength=f"{rng.choice([5, 10, 20, 25, 50, 100, 150, 200, 300])} mg",
                    xlogp=round(rng.uniform(-2, 7), 2),
                    logp=round(rng.uniform(-2, 7), 2),
                    molecular_weight=round(rng.uniform(150, 1200), 1),
                    solubility=rng.choice([c for c, _ in Product.Solubility.choices]),
                ),
            )
            if not created:
                continue
            product.keywords.set(rng.sample(keywords, rng.randint(0, 3)))
            product.excipients.set(rng.sample(excipients, rng.randint(2, 6)))

            base_revenue = rng.lognormvariate(4, 1.3)  # skewed: most small, a few blockbusters
            patent = today + timedelta(days=rng.randint(-365, 365 * 18))
            for region in rng.sample(regions, rng.randint(2, len(regions))):
                shift = timedelta(days=rng.randint(-400, 400))
                launch = patent + shift + timedelta(days=rng.randint(0, 180))
                if rng.random() < 0.06:  # keep the dashboard's "next 60 days" panels populated
                    launch = today + timedelta(days=rng.randint(0, 60))
                    patent = launch - timedelta(days=rng.randint(0, 90))
                    shift = timedelta(0)
                ProductCountry.objects.create(
                    product=product, region=region,
                    revenue_musd=Decimal(str(round(base_revenue * rng.uniform(0.05, 1.0), 2))),
                    earliest_generic_launch=launch,
                    marketing_exclusivity=_maybe(rng, launch - timedelta(days=rng.randint(0, 900))),
                    data_exclusivity=_maybe(rng, launch - timedelta(days=rng.randint(200, 1800))),
                    main_patent_expiry=patent + shift,
                    patent_extension=_maybe(rng, patent + shift + timedelta(days=rng.randint(90, 1800)), 0.3),
                    other_blocking_patent=rng.choice(["", "", "Formulation patent", "Polymorph patent"]),
                    key_patents=", ".join(f"XX{rng.randint(1000000, 9999999)}" for _ in range(rng.randint(1, 3))),
                    ftf_anda_filers=rng.randint(0, 12) if region.name == "USA" else 0,
                    post_generic_6m=rng.randint(0, 8),
                    api_manufacturers=rng.choice([0, 1, 2, 3, 4, 5, 7, 9, 12, 15]),
                    api_consumption_kg=Decimal(str(round(rng.uniform(1, 25000), 1))),
                    suggested_strategy=rng.choice(STRATEGIES),
                )

        org, _ = Organization.objects.get_or_create(
            name="Demo Generics Ltd",
            defaults={"access_tier": Organization.Tier.FREE, "full_access_until": timezone.now() + timedelta(days=30)},
        )
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=opts["username"], defaults={"first_name": "Demo", "last_name": "User", "is_staff": True}
        )
        if created:
            user.set_password(opts["password"])
            user.save()
        Profile.objects.get_or_create(user=user, defaults={"organization": org})

        portfolio, _ = ProductList.objects.get_or_create(organization=org, kind="portfolio", name="My Portfolio")
        playarea, _ = ProductList.objects.get_or_create(organization=org, kind="playarea", name="Play Area")
        ProductList.objects.get_or_create(organization=org, kind="playarea", name="Play Area 2")
        markets = list(ProductCountry.objects.order_by("?")[:30])
        for market in markets[:20]:
            ListItem.objects.get_or_create(product_list=portfolio, market=market, defaults={"added_by": user})
        for market in markets[20:]:
            ListItem.objects.get_or_create(product_list=playarea, market=market, defaults={"added_by": user})

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Product.objects.count()} products / {ProductCountry.objects.count()} markets. "
            f"Login: {opts['username']} (password set from --password; default documented in README)."
        ))
