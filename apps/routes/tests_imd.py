from django.test import TestCase
from django.core.cache import cache
from unittest.mock import patch, MagicMock
from apps.routes.services.imd_service import IMDWarningService, parse_warning_codes, IMD_WARNING_LABELS
from rest_framework.test import APIClient

class IMDWarningServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.sample_imd_records = [
            {
                "Obj_id": "573",
                "District": "East Khasi Hills",
                "Date": "2026-09-08",
                "UTC": "00:00",
                "Day_1": "16",
                "Day1_Color": 1,
                "Day_2": "2,4",
                "Day2_Color": 2,
                "Day_3": "1",
                "Day3_Color": 4,
                "Day_4": 1,
                "Day4_Color": 4,
                "Day_5": "1",
                "Day5_Color": 4,
            },
            {
                "Obj_id": "301",
                "District": "Kamrup Metropolitan",
                "Date": "2026-09-08",
                "UTC": "00:00",
                "Day_1": "2",
                "Day1_Color": 2,
                "Day_2": "1",
                "Day2_Color": 4,
                "Day_3": "1",
                "Day3_Color": 4,
                "Day_4": "1",
                "Day4_Color": 4,
                "Day_5": "1",
                "Day5_Color": 4,
            },
            {
                "Obj_id": "999",
                "District": "Jaipur",  # Non-NER district
                "Date": "2026-09-08",
                "UTC": "00:00",
                "Day_1": "2",
                "Day1_Color": 1,
            },
        ]

    def test_parse_warning_codes(self):
        # Code 1 should be excluded
        self.assertEqual(parse_warning_codes(1), [])
        self.assertEqual(parse_warning_codes("1"), [])
        self.assertEqual(parse_warning_codes("1,1"), [])

        # Multiple codes
        self.assertEqual(parse_warning_codes("2,4"), [2, 4])
        self.assertEqual(parse_warning_codes("16"), [16])
        self.assertEqual(parse_warning_codes([2, 4, 1]), [2, 4])

    def test_normalize_records_filtering_and_severity(self):
        alerts = IMDWarningService.normalize_records(self.sample_imd_records)
        
        # Verify Non-NER district "Jaipur" is filtered out
        districts_in_alerts = {a["district"] for a in alerts}
        self.assertNotIn("Jaipur", districts_in_alerts)
        self.assertIn("East Khasi Hills", districts_in_alerts)
        self.assertIn("Kamrup Metropolitan", districts_in_alerts)

        # Verify Day 1 Very Heavy Rain for East Khasi Hills (Code 16, Color 1 -> High)
        d1_ekh = next(a for a in alerts if a["district"] == "East Khasi Hills" and a["day"] == "Day 1")
        self.assertEqual(d1_ekh["warning_code"], 16)
        self.assertEqual(d1_ekh["warning_type"], "Very Heavy Rain")
        self.assertEqual(d1_ekh["severity"], "High")
        self.assertEqual(d1_ekh["severity_label"], "HIGH")
        self.assertEqual(d1_ekh["color_code"], 1)
        self.assertEqual(d1_ekh["source"], "IMD")
        self.assertEqual(d1_ekh["issue_date"], "2026-09-08")
        self.assertEqual(d1_ekh["issue_time"], "00:00")

        # Verify Day 2 multi-code for East Khasi Hills ("2,4" -> 2 distinct alerts)
        d2_alerts = [a for a in alerts if a["district"] == "East Khasi Hills" and a["day"] == "Day 2"]
        self.assertEqual(len(d2_alerts), 2)
        d2_codes = {a["warning_code"] for a in d2_alerts}
        self.assertEqual(d2_codes, {2, 4})
        for a in d2_alerts:
            self.assertEqual(a["severity"], "Medium")
            self.assertEqual(a["color_code"], 2)

        # Verify Code 1 is not in any alerts
        for a in alerts:
            self.assertNotEqual(a["warning_code"], 1)

    @patch("apps.routes.services.imd_service.requests.get")
    def test_fetch_warnings_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_imd_records
        mock_get.return_value = mock_resp

        res = IMDWarningService.fetch_warnings(force_refresh=True)
        self.assertTrue(res["success"])
        self.assertFalse(res["cached"])
        self.assertGreater(res["total"], 0)
        self.assertEqual(res["source"], "India Meteorological Department (IMD)")

        # Subsequent call should return cached
        res_cached = IMDWarningService.fetch_warnings(force_refresh=False)
        self.assertTrue(res_cached["success"])
        self.assertEqual(res_cached["total"], res["total"])

    @patch("apps.routes.services.imd_service.requests.get")
    def test_fetch_warnings_failure_no_cache(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"error": "Unauthorized"}'
        mock_get.return_value = mock_resp

        res = IMDWarningService.fetch_warnings(force_refresh=True)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "IMD_API_UNAVAILABLE")
        self.assertEqual(res["error"]["message"], "Unable to load live IMD alerts")

    def test_api_view_success_and_filtering(self):
        client = APIClient()
        cache.set("imd_live_district_warnings", IMDWarningService.normalize_records(self.sample_imd_records), 600)
        cache.set("imd_live_district_warnings_timestamp", "2026-09-08T00:00:00Z", 600)

        # GET /api/v1/alerts/
        response = client.get("/api/v1/alerts/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["total"], 0)

        # Filter by severity High
        res_high = client.get("/api/v1/alerts/?severity=High")
        self.assertEqual(res_high.status_code, 200)
        data_high = res_high.json()
        for a in data_high["alerts"]:
            self.assertEqual(a["severity"], "High")

        # Filter by district
        res_dist = client.get("/api/v1/alerts/?district=Kamrup")
        self.assertEqual(res_dist.status_code, 200)
        data_dist = res_dist.json()
        for a in data_dist["alerts"]:
            self.assertIn("Kamrup", a["district"])
