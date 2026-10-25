import json
import unittest
from pathlib import Path

from classlist import changelog

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def record(class_id, name, start, **extra):
    base = {
        "id": class_id, "name": name, "description": "", "classGroupId": "g1", "capacity": 5,
        "numberRegistered": 0, "sessionTypeId": "t1", "startDateTime": start + ".0000000Z", "duration": 180,
        "staff": [{"displayLabel": "Pat Smith"}], "bookable": True, "waitlistable": True, "cancelled": False,
    }
    base.update(extra)
    return base


def snapshot(classes, first_day="2026-10-17", days=90, fetched_at="2026-10-18T02:00:00Z"):
    return {
        "meta": {"fetched_at": fetched_at, "first_day": first_day, "days": days},
        "session_types": [],
        "classes": classes,
    }


def types_of(entries):
    return [e["type"] for e in entries]


class AddedRemovedTest(unittest.TestCase):
    def test_new_session_within_old_window_is_added(self):
        old = snapshot([])
        new = snapshot([record("c1", "Block Printing - 1 Day - $65", "2026-10-20T00:00:00")])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["added"])
        self.assertEqual(entries[0]["class_id"], "c1")
        self.assertEqual(entries[0]["name"], "Block Printing")

    def test_session_entering_only_because_the_window_rolled_forward_is_not_added(self):
        old = snapshot([], first_day="2026-10-17", days=90)  # window ends 2027-01-14
        new = snapshot([record("c1", "Future Thing", "2027-02-01T00:00:00")], first_day="2026-10-18", days=90)
        self.assertEqual(changelog.diff_snapshots(old, new, CONFIG), [])

    def test_session_removed_while_still_in_window_is_removed(self):
        old = snapshot([record("c1", "Block Printing - 1 Day - $65", "2026-10-20T00:00:00")])
        new = snapshot([], first_day="2026-10-18")
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["removed"])

    def test_session_disappearing_because_its_date_passed_is_not_removed(self):
        old = snapshot([record("c1", "Block Printing - 1 Day - $65", "2026-10-17T00:00:00")], first_day="2026-10-17")
        new = snapshot([], first_day="2026-10-20")  # c1's date is now before the new window
        self.assertEqual(changelog.diff_snapshots(old, new, CONFIG), [])

    def test_session_that_simply_started_between_fetches_is_not_removed(self):
        # Same day for both fetches; the session's start time (5pm Pacific = 00:00 UTC) falls
        # between them, so it drops out of Mindbody's own feed on its own, not because anything
        # was cancelled or deleted. (These are the real timestamps from the bug this reproduces.)
        old = snapshot(
            [record("c1", "Butcher Blocks - 1 Day - $115", "2026-10-25T00:00:00")],
            first_day="2026-10-24", fetched_at="2026-10-24T23:59:54Z",
        )
        new = snapshot([], first_day="2026-10-24", fetched_at="2026-10-25T00:07:36Z")
        self.assertEqual(changelog.diff_snapshots(old, new, CONFIG), [])

    def test_session_removed_before_it_was_due_to_start_is_still_removed(self):
        # Same day for both fetches, but the session hasn't started yet when it vanishes: a genuine
        # cancellation/deletion mid-day, not the session simply having happened.
        old = snapshot(
            [record("c1", "Butcher Blocks - 1 Day - $115", "2026-10-25T03:00:00")],
            first_day="2026-10-24", fetched_at="2026-10-24T23:59:54Z",
        )
        new = snapshot([], first_day="2026-10-24", fetched_at="2026-10-25T00:07:36Z")
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["removed"])


class FieldChangeTest(unittest.TestCase):
    def test_cancelled(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00")])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", cancelled=True)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["cancelled"])

    def test_uncancelled(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", cancelled=True)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00")])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["uncancelled"])

    def test_time_changed(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00")])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T03:00:00")])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["time_changed"])
        self.assertEqual(entries[0]["detail"]["was_start"], "2026-10-20T00:00:00Z")

    def test_duration_changed_is_also_a_time_change(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", duration=180)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", duration=120)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["time_changed"])
        self.assertEqual(entries[0]["detail"]["was_duration"], 180)

    def test_capacity_changed(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", capacity=4)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", capacity=6)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["capacity_changed"])
        self.assertEqual(entries[0]["detail"], {"was_capacity": 4, "capacity": 6})

    def test_fully_booked(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=True, waitlistable=False)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=False, waitlistable=False)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["fully_booked"])

    def test_spot_opened(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=False, waitlistable=False)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=True, waitlistable=False)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["spot_opened"])

    def test_cancelled_session_is_not_also_reported_full(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=True, waitlistable=False)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=False, waitlistable=False, cancelled=True)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["cancelled"])

    def test_instructor_changed(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", staff=[{"displayLabel": "Pat Smith"}])])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", staff=[{"displayLabel": "Jo Lee"}])])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["instructor_changed"])
        self.assertEqual(entries[0]["detail"], {"was_instructor": "Pat Smith", "instructor": "Jo Lee"})

    def test_no_changes_means_no_entries(self):
        rec = record("c1", "Woodworking", "2026-10-20T00:00:00")
        old = snapshot([rec])
        new = snapshot([dict(rec)])
        self.assertEqual(changelog.diff_snapshots(old, new, CONFIG), [])

    def test_unchanged_registration_count_is_not_logged(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", numberRegistered=1)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", numberRegistered=3)])
        self.assertEqual(changelog.diff_snapshots(old, new, CONFIG), [])

    def test_entries_are_ordered_by_session_start(self):
        old = snapshot([
            record("c1", "Later", "2026-10-25T00:00:00"),
            record("c2", "Earlier", "2026-10-20T00:00:00"),
        ])
        new = snapshot([
            record("c1", "Later", "2026-10-25T00:00:00", cancelled=True),
            record("c2", "Earlier", "2026-10-20T00:00:00", cancelled=True),
        ])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual([e["class_id"] for e in entries], ["c2", "c1"])


class KindTest(unittest.TestCase):
    def test_added_entry_records_its_kind(self):
        old = snapshot([])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00")])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(entries[0]["kind"], "c")

    def test_member_session_name_pattern_gives_a_member_kind(self):
        old = snapshot([])
        new = snapshot([record("c1", "Metal Shop Mentor Hours", "2026-10-20T00:00:00")])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(entries[0]["kind"], "m")

    def test_seatless_listing_gives_a_public_kind(self):
        old = snapshot([])
        new = snapshot([record("c1", "Community Open House", "2026-10-20T00:00:00", capacity=0)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(entries[0]["kind"], "p")

    def test_removed_entry_uses_the_old_snapshot_s_record(self):
        old = snapshot([record("c1", "Metal Shop Mentor Hours", "2026-10-20T00:00:00")])
        new = snapshot([], first_day="2026-10-18")
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(types_of(entries), ["removed"])
        self.assertEqual(entries[0]["kind"], "m")

    def test_spot_opened_entry_records_its_kind(self):
        old = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=False, waitlistable=False)])
        new = snapshot([record("c1", "Woodworking", "2026-10-20T00:00:00", bookable=True, waitlistable=False)])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertEqual(entries[0]["kind"], "c")


class AppendEntriesTest(unittest.TestCase):
    def test_creates_file_and_appends_across_calls(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "changelog.json"
            changelog.append_entries(path, [{"type": "added"}])
            changelog.append_entries(path, [{"type": "cancelled"}])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [{"type": "added"}, {"type": "cancelled"}])


class TypeLabelsTest(unittest.TestCase):
    def test_every_type_a_diff_can_produce_has_a_label(self):
        producible = {
            "added", "removed", "cancelled", "uncancelled", "time_changed",
            "capacity_changed", "fully_booked", "spot_opened", "instructor_changed",
        }
        self.assertEqual(set(changelog.TYPE_LABELS), producible)

    def test_entries_do_not_carry_their_own_label_text(self):
        old = snapshot([])
        new = snapshot([record("c1", "Block Printing - 1 Day - $65", "2026-10-20T00:00:00")])
        entries = changelog.diff_snapshots(old, new, CONFIG)
        self.assertNotIn("message", entries[0])


if __name__ == "__main__":
    unittest.main()
