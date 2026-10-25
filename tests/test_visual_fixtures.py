"""Guards for the visual tests that need no browser: the synthetic data and the scenario list."""
import json
import unittest
from collections import Counter
from pathlib import Path

from classlist import changelog, normalize
from tests.visual import synthetic
from tests.visual.scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
BASELINES = ROOT / "tests" / "visual" / "baselines"


class SyntheticDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads(synthetic.SNAPSHOT_FILE.read_text(encoding="utf-8"))
        cls.history = json.loads(synthetic.CHANGELOG_FILE.read_text(encoding="utf-8"))
        cls.events, cls.warnings = normalize.build_events(cls.snapshot, CONFIG)

    def test_committed_fixtures_match_the_generator(self):
        snapshot, entries = synthetic.render_fixtures(CONFIG)
        self.assertEqual(snapshot, synthetic.SNAPSHOT_FILE.read_text(encoding="utf-8"),
                         "run: python3 -m tests.visual.synthetic, then python3 -m tests.visual --update")
        self.assertEqual(entries, synthetic.CHANGELOG_FILE.read_text(encoding="utf-8"),
                         "run: python3 -m tests.visual.synthetic, then python3 -m tests.visual --update")

    def test_builds_without_warnings(self):
        self.assertEqual(self.warnings, [])

    def test_every_shop_kind_and_status_appears(self):
        self.assertEqual({e["cat"] for e in self.events}, set(CONFIG["shops"]) | {"Other"})
        self.assertEqual({e["kind"] for e in self.events}, {"c", "m", "p"})
        self.assertEqual({e["status"] for e in self.events}, {"b", "w", "f", "x", "i"})

    def test_has_multi_session_events_and_several_months(self):
        self.assertTrue({2, 3} <= {len(e["sessions"]) for e in self.events})
        months = {s["start"][:7] for e in self.events for s in e["sessions"]}
        self.assertGreaterEqual(len(months), 3)

    def test_every_kind_of_change_is_in_the_history(self):
        self.assertEqual({e["type"] for e in self.history}, set(changelog.TYPE_LABELS))
        self.assertEqual({e["kind"] for e in self.history}, {"c", "m", "p"})

    def test_history_links_to_both_live_and_vanished_sessions(self):
        live = {s["id"] for e in self.events for s in e["sessions"]}
        linked = {e["class_id"] in live for e in self.history}
        self.assertEqual(linked, {True, False})

    def test_history_is_oldest_first_across_several_days(self):
        stamps = [e["at"] for e in self.history]
        self.assertEqual(stamps, sorted(stamps))
        self.assertGreaterEqual(len({s[:10] for s in stamps}), 4)


class ScenarioListTest(unittest.TestCase):
    def test_names_are_unique_file_names(self):
        names = [s.name for s in SCENARIOS]
        self.assertEqual([n for n, c in Counter(names).items() if c > 1], [])
        for name in names:
            self.assertRegex(name, r"^[a-z0-9-]+$")

    def test_every_platform_with_baselines_has_all_of_them_and_no_orphans(self):
        wanted = {"%s.png" % s.name for s in SCENARIOS}
        platforms = [p for p in BASELINES.iterdir() if p.is_dir()]
        self.assertTrue(platforms, "no baselines: run python3 -m tests.visual --update")
        for platform in platforms:
            have = {p.name for p in platform.glob("*.png")}
            self.assertEqual(sorted(wanted - have), [], "%s: run python3 -m tests.visual --update" % platform.name)
            self.assertEqual(sorted(have - wanted), [], "%s: baseline for a scenario that no longer exists" % platform.name)


if __name__ == "__main__":
    unittest.main()
