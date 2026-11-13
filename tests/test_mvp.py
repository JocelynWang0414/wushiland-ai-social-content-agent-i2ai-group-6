import unittest
from datetime import date, datetime
from unittest.mock import patch

from wushiland.agent import calendar, generate, load
from wushiland.web import render


class WeeklyBriefTests(unittest.TestCase):
    def test_carnival_with_demo_trends(self):
        start = date(2027, 4, 12)
        result = generate(start, as_of=start, demo=True)
        self.assertEqual(len(result["briefs"]), 3)
        self.assertEqual(len({brief["format"] for brief in result["briefs"]}), 3)
        self.assertTrue(all("Spring Carnival" in brief["concept"] for brief in result["briefs"]))
        self.assertTrue(all("indoors" in brief["concept"] for brief in result["briefs"]))
        self.assertTrue(all(trend["fixture"] for trend in result["trends"]))
        self.assertIn("Demo fixtures enabled", render(str(start), result=result))

    def test_winter_break_cross_year_and_holiday_conflicts(self):
        start = date(2026, 12, 25)
        events = calendar(start, date(2027, 1, 1))
        self.assertEqual([event["name"] for event in events], ["Christmas Day", "New Year's Day"])
        result = generate(start, as_of=start)
        self.assertTrue(result["weather"]["break_proxy"])
        self.assertEqual(result["briefs"][0]["product"], "Boba Milk Tea")
        self.assertTrue(all(datetime.fromisoformat(brief["posting_time"]).date() > start
                            for brief in result["briefs"]))
        self.assertTrue(all("neighbors" in brief["audience"] for brief in result["briefs"]))

    def test_tartan_day_available_as_observance(self):
        start = date(2028, 4, 3)
        self.assertEqual([event["name"] for event in calendar(start, date(2028, 4, 9))],
                         ["National Tartan Day"])

    def test_trend_eligibility_and_summer_catalog_fit(self):
        start = date(2027, 7, 12)
        reports = [{"title": title, "format": format_name, "published": day,
                    "source": "https://example.org/report"}
                   for title, format_name, day in [
                       ("Fresh pour", "pour", "2027-07-09"),
                       ("Older choice", "choice", "2027-05-01"),
                       ("Future routine", "routine", "2027-07-13"),
                   ]]
        result = generate(start, reports, as_of=start)
        self.assertEqual([trend["title"] for trend in result["trends"]], ["Fresh pour"])
        self.assertEqual(result["briefs"][0]["product"], "Jasmine Green Tea")
        self.assertEqual(result["briefs"][0]["format"], "pour")

    def test_guardrail_retries_product(self):
        products = load("products")
        products[0]["shot"] = "Film strangers."
        with patch("wushiland.agent.load", side_effect=lambda name: products if name == "products" else load(name)):
            start = date(2027, 1, 4)
            result = generate(start, as_of=start)
        self.assertEqual(len(result["briefs"]), 3)
        self.assertFalse(any(brief["product"] == "Boba Milk Tea" for brief in result["briefs"]))
        self.assertTrue(any("Rejected" in step for step in result["trace"]))

    def test_direct_social_link_and_bad_report_shape(self):
        start = date(2027, 4, 12)
        with self.assertRaisesRegex(ValueError, "outside TikTok and Instagram"):
            generate(start, [{"title": "Example", "format": "pour", "published": str(start),
                              "source": "https://www.tiktok.com/example"}], as_of=start)
        with self.assertRaisesRegex(ValueError, "JSON array"):
            generate(start, False, as_of=start)

    def test_html_escapes_input(self):
        self.assertIn("&lt;script&gt;", render(reports="<script>"))
        self.assertNotIn("<script>", render(reports="<script>"))


if __name__ == "__main__":
    unittest.main()
