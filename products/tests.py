import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from reference.models import DosageForm, Excipient, Indication, Keyword, Region

from .importer import ImportFileError, import_file, template_csv
from .models import Product, ProductCountry

HEADER = "active_substance,dosage_form,region,indication,revenue_musd,earliest_generic_launch,keywords\n"


def run(text, name="data.csv", **kw):
    return import_file(io.BytesIO(text.encode()), name, **kw)


class ImporterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tablet = DosageForm.objects.create(name="Tablet")
        cls.hiv = Indication.objects.create(name="HIV")
        cls.usa = Region.objects.create(name="USA")
        cls.eu = Region.objects.create(name="Europe")
        Keyword.objects.create(name="Long-acting")
        Excipient.objects.create(name="Povidone")

    def test_creates_product_and_markets(self):
        result = run(HEADER + "Examplevir,Tablet,USA,HIV,\"$1,234.5M\",2029-06-30,Long-acting\n"
                              "Examplevir,tablet,europe,,50,05-Mar-2030,\n")
        self.assertTrue(result.applied, result.errors)
        self.assertEqual((result.products_created, result.markets_created), (1, 2))
        product = Product.objects.get()
        self.assertEqual(product.indication, self.hiv)
        self.assertEqual(list(product.keywords.values_list("name", flat=True)), ["Long-acting"])
        us = ProductCountry.objects.get(region=self.usa)
        self.assertEqual(us.revenue_musd, Decimal("1234.50"))
        self.assertEqual(ProductCountry.objects.get(region=self.eu).earliest_generic_launch, date(2030, 3, 5))

    def test_update_only_touches_present_non_empty_cells(self):
        run(HEADER + "Examplevir,Tablet,USA,HIV,100,2029-06-30,\n")
        result = run("active_substance,dosage_form,region,revenue_musd,earliest_generic_launch\n"
                     "EXAMPLEVIR,Tablet,USA,200,\n")
        self.assertEqual((result.products_created, result.markets_updated), (0, 1))
        market = ProductCountry.objects.get()
        self.assertEqual(market.revenue_musd, Decimal("200.00"))
        self.assertEqual(market.earliest_generic_launch, date(2029, 6, 30))  # empty cell kept it

    def test_reimport_is_idempotent(self):
        text = HEADER + "Examplevir,Tablet,USA,HIV,100,2029-06-30,Long-acting\n"
        run(text)
        result = run(text)
        self.assertEqual((result.products_updated, result.markets_updated, result.markets_created), (0, 0, 0))

    def test_errors_block_the_whole_file(self):
        result = run(HEADER + "Goodvir,Tablet,USA,HIV,10,2029-01-01,\n"
                              "Badvir,Tablet,Mars,HIV,lots,31/02/2029,Unknown kw\n")
        self.assertFalse(result.applied)
        self.assertEqual(Product.objects.count(), 0)
        cols = {e.column for e in result.errors}
        self.assertEqual(cols, {"region", "revenue_musd", "earliest_generic_launch", "keywords"})
        self.assertTrue(all(e.row == 3 for e in result.errors))

    def test_skip_invalid_imports_good_rows(self):
        result = run(HEADER + "Goodvir,Tablet,USA,HIV,10,2029-01-01,\nBadvir,Tablet,Mars,HIV,,,\n", skip_invalid=True)
        self.assertTrue(result.applied)
        self.assertEqual(list(Product.objects.values_list("active_substance", flat=True)), ["Goodvir"])
        self.assertEqual(len(result.errors), 1)

    def test_new_product_needs_indication_on_some_row(self):
        result = run("active_substance,dosage_form,region\nNovir,Tablet,USA\nNovir,Tablet,Europe\n", skip_invalid=True)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual({e.row for e in result.errors}, {2, 3})

    def test_create_lookups(self):
        result = run(HEADER + "Newvir,Inhaler,Japan,Asthma,,,\n", create_lookups=True)
        self.assertTrue(result.applied, result.errors)
        self.assertEqual(result.lookups_created, {"indications": 1, "dosage forms": 1, "regions": 1})

    def test_dry_run_counts_without_saving(self):
        result = run(HEADER + "Newvir,Inhaler,Japan,Asthma,,,\n", create_lookups=True, dry_run=True)
        self.assertEqual((result.products_created, result.markets_created), (1, 1))
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Region.objects.filter(name="Japan").exists())

    def test_missing_required_column(self):
        with self.assertRaises(ImportFileError):
            run("active_substance,region\nX,USA\n")

    def test_report_csv_headers_are_accepted(self):
        text = ("Region,Active substance,Indication,Dosage form,Revenue ($M),Earliest generic launch,FTF / ANDA filers\n"
                "USA,Examplevir,HIV,Tablet,12.5,2029-06-30,4\n")
        result = run(text)
        self.assertTrue(result.applied, result.errors)
        self.assertEqual(ProductCountry.objects.get().ftf_anda_filers, 4)

    def test_xlsx_with_native_dates(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["Active Substance", "Dosage Form", "Region", "Indication", "Main patent expiry", "API manufacturers"])
        ws.append(["Xlsvir", "Tablet", "USA", "HIV", date(2031, 1, 15), 3])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        result = import_file(buf, "data.xlsx")
        self.assertTrue(result.applied, result.errors)
        market = ProductCountry.objects.get()
        self.assertEqual((market.main_patent_expiry, market.api_manufacturers), (date(2031, 1, 15), 3))

    def test_template_round_trips(self):
        result = run(template_csv(), create_lookups=True)
        self.assertTrue(result.applied, result.errors)
        product = Product.objects.get(active_substance="Examplevir")
        self.assertEqual(product.excipients.count(), 2)


@override_settings(IMPORT_UPLOAD_DIR="/tmp/launchscope-test-imports")
class ImportViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        DosageForm.objects.create(name="Tablet")
        Indication.objects.create(name="HIV")
        Region.objects.create(name="USA")
        User = get_user_model()
        cls.staff = User.objects.create_user("staff", password="x-test-pass-1", is_staff=True)
        cls.plain = User.objects.create_user("plain", password="x-test-pass-2")

    def upload(self, text):
        return self.client.post(reverse("products:import"),
                                {"file": SimpleUploadedFile("d.csv", text.encode(), content_type="text/csv")})

    def test_non_staff_is_redirected(self):
        self.client.force_login(self.plain)
        self.assertEqual(self.client.get(reverse("products:import")).status_code, 302)

    def test_preview_then_confirm(self):
        self.client.force_login(self.staff)
        response = self.upload(HEADER + "Webvir,Tablet,USA,HIV,10,2029-01-01,\n")
        self.assertContains(response, "Import 1 row")
        self.assertFalse(Product.objects.exists())  # preview only
        response = self.client.post(reverse("products:import_confirm"), follow=True)
        self.assertTrue(Product.objects.filter(active_substance="Webvir").exists())
        self.assertContains(response, "Imported 1/1 rows")

    def test_preview_with_errors_cannot_confirm(self):
        self.client.force_login(self.staff)
        response = self.upload(HEADER + "Webvir,Tablet,Mars,HIV,,,\n")
        self.assertNotContains(response, "Import 1 row")
        self.assertContains(response, "unknown region")
        response = self.client.post(reverse("products:import_confirm"), follow=True)
        self.assertContains(response, "expired")
        self.assertFalse(Product.objects.exists())
