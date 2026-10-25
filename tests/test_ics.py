import json
import unittest
from pathlib import Path

from classlist import ics, normalize

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SNAPSHOT = json.loads((ROOT / "tests" / "fixtures" / "snapshot_2026-10-17.json").read_text(encoding="utf-8"))


def event(**over):
    base = {
        "title": "Beginning Pottery", "sub": None, "kind": "c", "cat": "Ceramics", "icon": "ceramics",
        "price": "$45", "pnote": None, "ptip": None, "desc": ["Throw your first pots."], "age": None,
        "anote": None, "cap": 10, "reg": 2, "status": "b", "inst": "Pat Smith",
        "link": "https://clients.mindbodyonline.com/classic/ws?studioid=1",
        "sessions": [{"start": "2026-11-01T18:00:00Z", "mins": 120, "id": "s1"}],
    }
    base.update(over)
    return base


class IcsTest(unittest.TestCase):
    def test_wraps_one_event_in_a_valid_calendar(self):
        feed = ics.build_feed([event()], {"fetched_at": "2026-10-17T00:00:00Z"})
        self.assertTrue(feed.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(feed.endswith("END:VCALENDAR\r\n"))
        self.assertIn("VERSION:2.0", feed)
        self.assertIn("BEGIN:VEVENT\r\n", feed)
        self.assertIn("END:VEVENT\r\n", feed)

    def test_one_vevent_per_session(self):
        two_sessions = event(sessions=[
            {"start": "2026-11-01T18:00:00Z", "mins": 120, "id": "s1"},
            {"start": "2026-11-08T18:00:00Z", "mins": 120, "id": "s2"},
        ])
        feed = ics.build_feed([two_sessions], {"fetched_at": "2026-10-17T00:00:00Z"})
        self.assertEqual(feed.count("BEGIN:VEVENT"), 2)
        self.assertIn("UID:rh-s1@roundhouse-class-list", feed)
        self.assertIn("UID:rh-s2@roundhouse-class-list", feed)

    def test_start_and_end_come_from_the_session(self):
        feed = ics.build_feed([event()], {"fetched_at": "2026-10-17T00:00:00Z"})
        self.assertIn("DTSTART:20261101T180000Z", feed)
        self.assertIn("DTEND:20261101T200000Z", feed)  # 120 minutes later

    def test_description_is_the_paragraphs_then_the_booking_link(self):
        feed = ics.build_feed([event(desc=["Para one.", "Para two."])], {"fetched_at": "2026-10-17T00:00:00Z"})
        self.assertIn("DESCRIPTION:Para one.\\n\\nPara two.\\n\\nBook: https://clients.mindbodyonline.com/classic/ws?studioid=1", feed)

    def test_cancelled_events_are_left_out(self):
        feed = ics.build_feed([event(status="x")], {"fetched_at": "2026-10-17T00:00:00Z"})
        self.assertNotIn("BEGIN:VEVENT", feed)

    def test_special_characters_are_escaped(self):
        feed = ics.build_feed([event(title="Comma, Semicolon; Back\\slash")], {"fetched_at": "2026-10-17T00:00:00Z"})
        self.assertIn("SUMMARY:Comma\\, Semicolon\\; Back\\\\slash", feed)

    def test_dtstamp_comes_from_the_snapshot_not_the_clock(self):
        feed = ics.build_feed([event()], {"fetched_at": "2026-10-17T08:00:00.0000000Z"})
        self.assertIn("DTSTAMP:20261017T080000Z", feed)

    def test_same_input_gives_identical_feed(self):
        meta = {"fetched_at": "2026-10-17T00:00:00Z"}
        self.assertEqual(ics.build_feed([event()], meta), ics.build_feed([event()], meta))

    def test_builds_from_a_real_snapshot(self):
        events, _ = normalize.build_events(SNAPSHOT, CONFIG)
        feed = ics.build_feed(events, SNAPSHOT["meta"])
        non_cancelled_sessions = sum(len(e["sessions"]) for e in events if e["status"] != "x")
        self.assertEqual(feed.count("BEGIN:VEVENT"), non_cancelled_sessions)


if __name__ == "__main__":
    unittest.main()
