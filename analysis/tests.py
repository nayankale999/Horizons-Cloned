from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from orgs.models import Organization, Profile
from products.models import ListItem, ProductCountry, ProductList
from reference.models import Region

from . import search as svc


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", products=40, password="test-pass-123", verbosity=0)
        cls.user = get_user_model().objects.get(username="demo")

    def setUp(self):
        self.client.force_login(self.user)

    def test_region_filter(self):
        usa = Region.objects.get(name="USA")
        results = list(svc.search({"regions": [str(usa.pk)]}))
        self.assertTrue(results)
        self.assertTrue(all(m.region_id == usa.pk for m in results))

    def test_revenue_band_filter(self):
        results = list(svc.search({"revenue": ["gt1000"]}))
        self.assertTrue(all(float(m.revenue_musd) >= 1000 for m in results))
        mid = list(svc.search({"revenue": ["10-50"]}))
        self.assertTrue(all(10 <= float(m.revenue_musd) < 50 for m in mid))

    def test_year_filter_uses_selected_date_field(self):
        year = ProductCountry.objects.exclude(main_patent_expiry=None).first().main_patent_expiry.year
        results = list(svc.search({"years": [str(year)], "date_field": "patent"}))
        self.assertTrue(results)
        self.assertTrue(all(m.main_patent_expiry.year == year for m in results))

    def test_data_endpoint_requires_parameters(self):
        data = self.client.post(reverse("analysis:data"), {}).json()["data"]
        self.assertFalse(data["IsRepSearchSet"])

    def test_data_endpoint_returns_rows_and_charts(self):
        usa = Region.objects.get(name="USA")
        data = self.client.post(reverse("analysis:data"), {"regions": [usa.pk]}).json()["data"]
        self.assertTrue(data["IsRepSearchSet"])
        self.assertEqual(data["numproducts"], len(data["repdata"]))
        self.assertIn("value_by_year", data["charts"])

    def test_saved_search_round_trip(self):
        usa = Region.objects.get(name="USA")
        created = self.client.post(reverse("analysis:saved_create"), {"name": "US only", "regions": [usa.pk]}).json()
        pk = created["data"]["id"]
        params = self.client.get(reverse("analysis:saved_get", args=[pk])).json()["data"]["params"]
        self.assertEqual(params["regions"], [str(usa.pk)])
        self.client.post(reverse("analysis:saved_delete", args=[pk]))
        self.assertEqual(self.client.get(reverse("analysis:saved_get", args=[pk])).status_code, 404)

    def test_my_org_filter(self):
        results = list(svc.search({"my_org": "1"}, self.user.profile.organization))
        listed = set(ListItem.objects.values_list("market_id", flat=True))
        self.assertEqual({m.id for m in results}, listed)

    def test_report_flow(self):
        usa = Region.objects.get(name="USA")
        task_id = self.client.post(reverse("reports:generate"), {"regions": [usa.pk]}).json()["task_id"]
        status = self.client.get(reverse("reports:status", args=[task_id])).json()
        self.assertEqual(status["status"], "SUCCESS")
        csv = self.client.get(status["download_url"])
        self.assertEqual(csv["Content-Type"], "text/csv")
        self.assertIn(b"Active substance", csv.content)

    def test_pages_render(self):
        for name, args in [("dashboard", []), ("analysis:home", []), ("products:portfolio", []),
                           ("products:playarea", []), ("reports:home", []), ("orgs:profile", []),
                           ("lookup", ["indications"]), ("lookup", ["excipients"])]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 200)


class AccessTests(TestCase):
    def test_login_required(self):
        response = self.client.get(reverse("analysis:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_other_org_cannot_touch_items(self):
        call_command("seed_demo", products=10, password="test-pass-123", verbosity=0)
        other_org = Organization.objects.create(name="Other Org")
        intruder = get_user_model().objects.create_user("intruder", password="x-test-pass-9")
        Profile.objects.create(user=intruder, organization=other_org)
        item = ListItem.objects.first()
        self.client.force_login(intruder)
        response = self.client.post(reverse("products:item_delete", args=[item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ListItem.objects.filter(pk=item.pk).exists())
