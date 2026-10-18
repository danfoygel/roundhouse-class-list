"""Talks to Mindbody. Skipped unless LIVE_MINDBODY=1, so the normal test run stays offline.

    LIVE_MINDBODY=1 python3 -m unittest tests.test_live

It makes two requests: the widget page and one seven-day class list. Run it when a refresh
starts failing, to see whether Mindbody changed the page.
"""
import json
import os
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from classlist import fetch

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "config.json").read_text(encoding="utf-8"))


@unittest.skipUnless(os.environ.get("LIVE_MINDBODY") == "1", "set LIVE_MINDBODY=1 to run")
class LiveTest(unittest.TestCase):
    def test_widget_page_and_one_week(self):
        client = fetch.Client(CONFIG["widget_url"])
        ctx = client.load_page()
        self.assertTrue(ctx.session_types)
        today = datetime.now(ZoneInfo(CONFIG["timezone"])).date()
        start, end = fetch.plan_windows(today, 7, CONFIG["timezone"])[0]
        classes = client.fetch_window(ctx, start, end)
        self.assertIsInstance(classes, list)
        for record in classes:
            for key in ("id", "name", "startDateTime", "duration", "capacity", "numberRegistered", "sessionTypeId", "classGroupId"):
                self.assertIn(key, record)


if __name__ == "__main__":
    unittest.main()
