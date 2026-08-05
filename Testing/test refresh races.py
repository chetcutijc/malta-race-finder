"""
Sanity checks for scripts/refresh_races.py, run against the fixture in
test/sample_feed.ics rather than the live feed — no network needed.

Run with:  python3 test/test_refresh_races.py -v
(from the repo root)

Worth re-running these after touching refresh_races.py, and worth
checking again if racescalendar.com ever redesigns and the workflow
starts failing — a failing test here narrows down whether it's the
parsing logic or something upstream.
"""
import datetime as dt
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def load_module_with_fixed_today(fixed_date):
    """Import refresh_races fresh, with date.today() pinned, so fixture
    dates stay in the future regardless of when this test actually runs."""
    spec = importlib.util.spec_from_file_location(
        "refresh_races", os.path.join(ROOT, "scripts", "refresh_races.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(*fixed_date)

    mod.date = FixedDate
    return mod


class TestParsing(unittest.TestCase):
    def setUp(self):
        self.mod = load_module_with_fixed_today((2026, 8, 5))
        with open(os.path.join(ROOT, "test", "sample_feed.ics"), encoding="utf-8") as f:
            self.raw = f.read()
        self.races = self.mod.build_races(self.mod.parse_ics(self.raw))
        self.by_name = {r["name"]: r for r in self.races}

    def test_drops_past_events(self):
        # fixture includes one event dated 2025-08-15, which is before our fixed "today"
        self.assertNotIn("Past Event That Should Be Filtered Out", self.by_name)

    def test_expected_count(self):
        self.assertEqual(len(self.races), 5)

    def test_swimrun_beats_generic_categories(self):
        # name contains "SwimRun" even though CATEGORIES is Running/Swimming/Trail Running
        self.assertEqual(self.by_name["XTERRA Comino SwimRun & Trail"]["type"], "multisport")

    def test_triathlon_category_wins_over_cycling_running_swimming(self):
        self.assertEqual(self.by_name["Relay Tri 2027"]["type"], "multisport")

    def test_ocr_category_maps_to_obstacle(self):
        self.assertEqual(self.by_name["The Grid Sprint Weekend"]["type"], "obstacle")

    def test_road_running_category_maps_to_run(self):
        self.assertEqual(self.by_name["Zabbar 5K Series"]["type"], "run")

    def test_multiday_end_date_adjusted_for_exclusive_dtend(self):
        # DTSTART 2026-10-10, DTEND 2026-10-12 (exclusive) -> event actually ends 2026-10-11
        self.assertEqual(self.by_name["The Grid Sprint Weekend"]["endDate"], "2026-10-11")

    def test_single_day_event_has_no_end_date(self):
        self.assertIsNone(self.by_name["Zabbar 5K Series"]["endDate"])

    def test_timed_dtstart_is_parsed_to_date_only(self):
        # DTSTART:20260908T070000Z -> date should be 2026-09-08
        self.assertEqual(self.by_name["Triathlon Series - Race 4"]["date"], "2026-09-08")

    def test_distance_guess_extracts_km_tokens(self):
        self.assertIn("6km", self.by_name["The Grid Sprint Weekend"]["distance"])

    def test_no_category_and_no_keyword_defaults_to_run(self):
        events = self.mod.parse_ics(
            "BEGIN:VCALENDAR\n"
            "BEGIN:VEVENT\n"
            "DTSTART;VALUE=DATE:20270101\n"
            "UID:edge1@x\n"
            "SUMMARY:Mystery Village Fun Run\n"
            "URL:https://example.com/mystery\n"
            "LOCATION:Qormi, Malta\n"
            "END:VEVENT\n"
            "END:VCALENDAR"
        )
        races = self.mod.build_races(events)
        self.assertEqual(races[0]["type"], "run")


class TestSafety(unittest.TestCase):
    def setUp(self):
        self.mod = load_module_with_fixed_today((2026, 8, 5))
        with open(os.path.join(ROOT, "test", "sample_feed.ics"), encoding="utf-8") as f:
            self.sample = f.read()

    def _run_main_in(self, tmp_path, fetch_fn):
        cwd = os.getcwd()
        os.chdir(tmp_path)
        self.mod.fetch = fetch_fn
        try:
            self.mod.main()
            code = 0
        except SystemExit as e:
            code = e.code
        finally:
            os.chdir(cwd)
        return code

    def test_fetch_failure_does_not_touch_existing_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sentinel = os.path.join(tmp, "races-auto.json")
            with open(sentinel, "w") as f:
                f.write('{"races": ["SENTINEL"]}')

            def broken_fetch(url):
                raise RuntimeError("simulated failure")

            code = self._run_main_in(tmp, broken_fetch)
            self.assertEqual(code, 1)
            with open(sentinel) as f:
                self.assertEqual(f.read(), '{"races": ["SENTINEL"]}')

    def test_too_few_events_does_not_touch_existing_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            sentinel = os.path.join(tmp, "races-auto.json")
            with open(sentinel, "w") as f:
                f.write('{"races": ["SENTINEL"]}')

            tiny_feed = (
                "BEGIN:VCALENDAR\nBEGIN:VEVENT\n"
                "DTSTART;VALUE=DATE:20270101\nUID:only-one@x\n"
                "SUMMARY:Only One Event\nURL:https://example.com/one\n"
                "END:VEVENT\nEND:VCALENDAR"
            )
            code = self._run_main_in(tmp, lambda url: tiny_feed)
            self.assertEqual(code, 1)
            with open(sentinel) as f:
                self.assertEqual(f.read(), '{"races": ["SENTINEL"]}')

    def test_happy_path_writes_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            code = self._run_main_in(tmp, lambda url: self.sample)
            self.assertEqual(code, 0)
            out_path = os.path.join(tmp, "races-auto.json")
            self.assertTrue(os.path.exists(out_path))


if __name__ == "__main__":
    unittest.main()
