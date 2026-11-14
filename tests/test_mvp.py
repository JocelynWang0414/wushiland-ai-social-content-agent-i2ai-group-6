import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date, datetime
from unittest.mock import patch

from wushiland.agent import calendar, generate, load
from wushiland.web import render
from wushiland.llm import plan
from wushiland.brightdata import load_creative_signals


class WeeklyBriefTests(unittest.TestCase):
    def test_carnival(self):
        start = date(2027, 4, 12)
        result = generate(start, as_of=start)
        self.assertEqual(len(result["briefs"]), 3)
        self.assertEqual(len({brief["format"] for brief in result["briefs"]}), 3)
        self.assertTrue(all("Spring Carnival" in brief["concept"] for brief in result["briefs"]))
        self.assertTrue(all("indoors" in brief["concept"] for brief in result["briefs"]))
        self.assertIn("Templates", render(str(start), result=result))

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

    def test_model_replans_with_calendar_and_weather_feedback(self):
        start = date(2027, 4, 12)
        def planner(evidence, feedback, used_formats):
            self.assertEqual(evidence["events"][0]["name"], "Spring Carnival")
            self.assertEqual(evidence["weather"]["condition"], "rainy")
            if not feedback:
                return [{"product": "Invented tea", "format": "pour"}]
            self.assertIn("exact catalog product", feedback[0])
            return [
                {"product": "Boba Milk Tea", "event": "Spring Carnival", "format": format_name,
                 "hook": "A tea break between Booth visits",
                 "concept": "Film a handoff at the indoor counter.",
                 "script": ["Between Booth visits?", "Take a tea break", "Save for Carnival"],
                 "shots": ["Counter", "Pearl closeup", "Handoff"],
                 "why": "An indoor shoot fits the simulated rainy Carnival week."}
                for format_name in ("routine", "pour", "choice")
            ]
        result = generate(start, as_of=start, planner=planner)
        self.assertEqual(result["mode"], "LLM-assisted")
        self.assertEqual(len(result["briefs"]), 3)
        self.assertIn("indoor shoot", result["briefs"][0]["rationale"][-1])

    def test_model_failure_falls_back(self):
        start = date(2027, 7, 12)
        def planner(*args):
            raise ValueError("Model request failed.")
        result = generate(start, as_of=start, planner=planner)
        self.assertEqual(result["mode"], "Templates")
        self.assertEqual(len(result["briefs"]), 3)
        self.assertEqual(result["briefs"][0]["product"], "Jasmine Green Tea")
        self.assertIn("Model request failed.", result["trace"])

    def test_guardrail_retries_product(self):
        products = load("products")
        products[0]["shot"] = "Film strangers."
        with patch("wushiland.agent.load", side_effect=lambda name: products if name == "products" else load(name)):
            start = date(2027, 1, 4)
            result = generate(start, as_of=start)
        self.assertEqual(len(result["briefs"]), 3)
        self.assertFalse(any(brief["product"] == "Boba Milk Tea" for brief in result["briefs"]))
        self.assertTrue(any("Rejected" in step for step in result["trace"]))

    def test_minimal_form(self):
        page = render()
        self.assertIn('name="start"', page)
        self.assertNotIn("Trend reports", page)
        self.assertNotIn('name="demo"', page)


class GeminiAdapterTests(unittest.TestCase):
    @patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True)
    @patch("wushiland.llm.urlopen")
    def test_default_model_and_native_json_request(self, urlopen):
        response = {"candidates": [{"content": {"parts": [
            {"thought": True, "text": "hidden"},
            {"text": json.dumps({"briefs": [{"product": "Boba Milk Tea"}]})},
        ]}}]}
        urlopen.return_value.__enter__.return_value = io.BytesIO(json.dumps(response).encode())
        self.assertEqual(plan({}, [], []), [{"product": "Boba Milk Tea"}])
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/models/gemini-3.5-flash-lite:generateContent"))
        self.assertEqual(request.get_header("X-goog-api-key"), "test-key")
        self.assertEqual(json.loads(request.data)["generationConfig"]["responseMimeType"], "application/json")


class SavedCreativeTests(unittest.TestCase):
    def test_reload_uses_newest_export_and_tolerates_bad_files(self):
        seed = Path("wushiland/data/brightdata/signals.json")
        export = json.loads(seed.read_text())
        with TemporaryDirectory() as directory, patch.dict(
            "os.environ", {"WUSHILAND_BRIGHTDATA_DIR": directory}
        ):
            root = Path(directory)
            (root / "signals.json").write_text(json.dumps(export))
            newer = root / "newer"
            newer.mkdir()
            (newer / "signals.json").write_text("{")
            day = date(2027, 4, 12)
            refs = load_creative_signals(day, [])
            self.assertTrue(refs and all(ref["historical"] for ref in refs))
            export["generated_at"] = "2027-04-10T01:00:00Z"
            export["signals"] = []
            (newer / "signals.json").write_text(json.dumps(export))
            self.assertEqual(load_creative_signals(day, []), [])

    def test_template_brief_cites_saved_reference(self):
        result = generate(date(2027, 4, 12), as_of=date(2027, 4, 12))
        self.assertTrue(any(any("tiktok.com" in url for url in brief["sources"])
                            for brief in result["briefs"]))
        self.assertTrue(all("Spring Carnival" in brief["concept"] for brief in result["briefs"]))


if __name__ == "__main__":
    unittest.main()
