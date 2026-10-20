import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from classlist import normalize

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SNAPSHOT = json.loads((ROOT / "tests" / "fixtures" / "snapshot_2026-10-17.json").read_text(encoding="utf-8"))
GOLDEN = json.loads((ROOT / "tests" / "golden" / "page_v1.json").read_text(encoding="utf-8"))


def record(name, start, group="g1", **extra):
    base = {
        "id": "id-" + start + group, "name": name, "description": "", "classGroupId": group, "capacity": 5,
        "numberRegistered": 0, "sessionTypeId": "t1", "startDateTime": start + ".0000000Z", "duration": 180,
        "staff": [{"displayLabel": "Pat Smith"}], "bookable": True, "waitlistable": True, "cancelled": False,
    }
    base.update(extra)
    return base


class NameTest(unittest.TestCase):
    def test_clean_name_drops_price_length_and_member_suffixes(self):
        cases = {
            "Block Printing - 1 Day - $65": "Block Printing",
            "Sewing 101 - Practical Sewing Fundamentals - 2 Days -$145": "Sewing 101 - Practical Sewing Fundamentals",
            "Butcher Blocks for Beginners- $115 all materials included-2 sessions ": "Butcher Blocks for Beginners",
            "Metal Shop Mentor Hours - Members Only": "Metal Shop Mentor Hours",
            "Crochet Open Studio - Free to Member, $45 Non-Members": "Crochet Open Studio",
            "Fall Mini Rustic Porch Pots - 1 Day - $100, materials included": "Fall Mini Rustic Porch Pots",
            "Free KTG Reuse & Repair Workshop: Electronics Repair ": "Free KTG Reuse & Repair Workshop: Electronics Repair",
            "Wood Shop 102:  Make a Picture Frame - 2 Days - $145": "Wood Shop 102: Make a Picture Frame",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize.clean_name(raw), expected, raw)

    def test_hyphens_inside_words_are_kept(self):
        self.assertEqual(normalize.clean_name("Handsew Family-Friendly Day - 1 Day - $55"), "Handsew Family-Friendly Day")

    def test_subtitle_from_second_segment(self):
        self.assertEqual(normalize.split_title("Sewing 101 - Practical Sewing Fundamentals", CONFIG),
                         ("Sewing 101", "Practical Sewing Fundamentals"))

    def test_parenthetical_becomes_subtitle(self):
        self.assertEqual(normalize.split_title("Handsew Gingerbread People (Family-Friendly!)", CONFIG),
                         ("Handsew Gingerbread People", "Family-friendly"))

    def test_with_becomes_subtitle(self):
        self.assertEqual(normalize.split_title("Mandala Drawing w/ Nicole Stirling", CONFIG),
                         ("Mandala Drawing", "with Nicole Stirling"))

    def test_series_prefix_moves_to_subtitle(self):
        self.assertEqual(normalize.split_title("Free KTG Reuse & Repair Workshop: Reusable Gift Bag", CONFIG),
                         ("Reusable Gift Bag", "Free KTG Reuse & Repair Workshop"))
        self.assertEqual(normalize.split_title("Jewelry: Beaded Necklaces and Bracelets", CONFIG),
                         ("Beaded Necklaces & Bracelets", "Jewelry"))

    def test_override_wins(self):
        self.assertEqual(normalize.split_title("Wood Shop 102: Make a Picture Frame", CONFIG),
                         ("Wood Shop 102", "Make a Picture Frame"))

    def test_plain_title_is_unchanged(self):
        self.assertEqual(normalize.split_title("Crochet 101: Make a Pot Holder", CONFIG), ("Crochet 101: Make a Pot Holder", None))

    def test_course_size(self):
        self.assertEqual(normalize.course_size("Sewing 101 - 2 Days -$145"), 2)
        self.assertEqual(normalize.course_size("Butcher Blocks for Beginners- $115-2 sessions"), 2)
        self.assertEqual(normalize.course_size("Block Printing - 1 Day - $65"), 1)
        self.assertEqual(normalize.course_size("Public Tour"), 1)


class PriceTest(unittest.TestCase):
    def test_price_from_name(self):
        self.assertEqual(normalize.parse_price("Block Printing - 1 Day - $65", ""), ("$65", None))

    def test_materials_note(self):
        self.assertEqual(normalize.parse_price("Winter Pots - 1 Day - $100, materials included", ""), ("$100", "materials included"))
        self.assertEqual(normalize.parse_price("Pajama Pants - 2 Days -$90", "All materials are provided."), ("$90", "materials included"))

    def test_per_person_note_beats_materials(self):
        self.assertEqual(
            normalize.parse_price("Gingerbread - 1 Day - $55", "1 Day - $55 per gingerbread-maker. All materials are provided"),
            ("$55", "per gingerbread-maker"))

    def test_free_for_members_costs_non_members(self):
        self.assertEqual(normalize.parse_price("Crochet Open Studio - Free to Member, $45 Non-Members", ""), ("Free", None))

    def test_non_member_price_goes_in_a_tooltip(self):
        self.assertEqual(normalize.price_tooltip("Crochet Open Studio - Free to Member, $45 Non-Members"), "$45 for non-members")
        self.assertIsNone(normalize.price_tooltip("Block Printing - 1 Day - $65"))
        self.assertIsNone(normalize.price_tooltip("Metal Shop Mentor Hours - Members Only"))

    def test_free_members_only_from_description(self):
        self.assertEqual(normalize.parse_price("Metal Shop Mentor Hours - Members Only", "Free to Members Only. You must book."),
                         ("Free", None))

    def test_free_in_name(self):
        self.assertEqual(normalize.parse_price("Free KTG Reuse & Repair Workshop: Electronics Repair", ""), ("Free", None))
        self.assertEqual(normalize.parse_price("Taller GRATUITO en español", ""), ("Free", None))

    def test_no_price(self):
        self.assertEqual(normalize.parse_price("Public Tour - Come Check Out the Space", "Check out the space."), (None, None))


class AgeTest(unittest.TestCase):
    def test_minimum_age_phrasings(self):
        cases = {
            "Ages 12 and over. Bring a hook.": 12,
            "Max 4 students Ages: 12 and above": 12,
            "Appropriate for students 12 and over.": 12,
            "Ages 12 - Adult": 12,
            "Ages: 12 to adult": 12,
            "Appropriate for ages 8 and above": 8,
            "Come down to crochet. 12 and over": 12,
            "12 - Adult. Students under 15 must be accompanied by an adult.": 12,
        }
        for text, expected in cases.items():
            self.assertEqual(normalize.parse_age(text)[0], expected, text)

    def test_no_minimum_age(self):
        self.assertEqual(normalize.parse_age("A tour of the space. Most tours last about 20 minutes."), (None, None))

    def test_accompaniment_notes(self):
        cases = {
            "All youth under the age of 16 must be chaperoned by an adult also taking the class": "Under 16 with an adult",
            "Students under 15 must be accompanied by an adult": "Under 15 with an adult",
            "Students under the age of 16 must attend with an adult also taking the course": "Under 16 with an adult",
        }
        for text, expected in cases.items():
            self.assertEqual(normalize.parse_age(text)[1], expected, text)

    def test_fifteen_and_under_means_under_sixteen(self):
        self.assertEqual(normalize.parse_age("Students 15 and under must be accompanied by adult also taking the class.")[1],
                         "Under 16 with an adult")

    def test_the_age_of_is_not_a_minimum(self):
        self.assertEqual(normalize.parse_age("All youth under the age of 16 must be chaperoned by an adult")[0], None)


class DescribeTest(unittest.TestCase):
    def test_paragraphs_lists_and_entities(self):
        markup = "<div><strong>Wood Shop 101</strong></div><div>&nbsp;</div><p>Learn to saw &amp; plane.</p><ul><li>Safety</li><li>Tools</li></ul>"
        self.assertEqual(normalize.describe(markup, "Wood Shop 101 - 2 Days - $145"),
                         ["Learn to saw & plane.", "\u2022 Safety", "\u2022 Tools"])

    def test_leading_headline_lines_are_dropped(self):
        markup = "<div>Sewing 101 - Practical Sewing Fundamentals - $145</div><div>2 Days - 3 Hours each day</div><div>The broad goal is to help.</div>"
        self.assertEqual(normalize.describe(markup, "Sewing 101 - Practical Sewing Fundamentals - 2 Days -$145"), ["The broad goal is to help."])

    def test_price_and_length_lines_are_dropped_even_without_the_name(self):
        markup = "<p>Mandala Drawing</p><p>2-Day Class | 3 Hours per Day</p><p>$140</p><p>Join artist Nicole Stirling to draw mandalas.</p>"
        self.assertEqual(normalize.describe(markup, "Mandala Drawing w/ Nicole Stirling - 2 Days - $140"),
                         ["Join artist Nicole Stirling to draw mandalas."])

    def test_a_real_first_sentence_is_kept(self):
        markup = "<p>Make your own Gingerbread person with your loved ones!</p><p>All materials are provided.</p>"
        self.assertEqual(normalize.describe(markup, "Handsew Gingerbread People (Family-Friendly!)"), ["Make your own Gingerbread person with your loved ones!", "All materials are provided."])

    def test_single_paragraph_is_never_dropped(self):
        self.assertEqual(normalize.describe("<p>Public Tour - $0</p>", "Public Tour"), ["Public Tour - $0"])

    BOILERPLATE = CONFIG["description_boilerplate"]

    def test_seats_ages_and_adult_rules_are_dropped_when_the_page_shows_them(self):
        markup = ("<p>Learn to sew.</p><p>Max 4 students</p><p>Ages: 12 and above. Students under the age of 16 must attend "
                  "with an adult also taking the course.</p><p>Bring a project.</p>")
        self.assertEqual(normalize.describe(markup, "Sewing - 2 Days", self.BOILERPLATE, 12, "Under 16 with an adult"),
                         ["Learn to sew.", "Bring a project."])

    def test_age_sentences_stay_when_the_page_does_not_show_them(self):
        markup = "<p>Learn to sew.</p><p>Ages 12 and over.</p><p>Students under 15 must be accompanied by an adult.</p>"
        self.assertEqual(normalize.describe(markup, "Sewing", self.BOILERPLATE, None, None),
                         ["Learn to sew.", "Ages 12 and over.", "Students under 15 must be accompanied by an adult."])

    def test_an_age_sentence_inside_a_longer_paragraph_is_removed_alone(self):
        markup = "<p>Leave with a unique set of earrings handmade by you! Ages 12 and above</p>"
        self.assertEqual(normalize.describe(markup, "Earrings", self.BOILERPLATE, 12, None),
                         ["Leave with a unique set of earrings handmade by you!"])

    def test_booking_and_policy_wording_is_dropped(self):
        markup = ("<p>Make a frame.</p><p>To register, click on the BOOK button. If the class is full, you can add your name to the "
                  "waitlist. If there is no BOOK or WAITLIST button, the class and waitlist are full.</p>"
                  "<p>Cancellations made 72 hours or more in advance will receive a Roundhouse class credit.</p>"
                  "<p>Please note that we may take photos during the workshop to use for future marketing.</p>")
        self.assertEqual(normalize.describe(markup, "Frame", self.BOILERPLATE), ["Make a frame."])

    def test_missing_description(self):
        self.assertEqual(normalize.describe(None, "Anything"), [])


class SmallRulesTest(unittest.TestCase):
    def test_plain_decodes_markup(self):
        self.assertEqual(normalize.plain("<div>Ages&nbsp;12 &amp; over</div><p>Fun</p>"), "Ages 12 & over Fun")

    def test_status_priority(self):
        self.assertEqual(normalize.status_for({"cancelled": True, "bookable": True}), "x")
        self.assertEqual(normalize.status_for({"bookable": True, "waitlistable": True}), "b")
        self.assertEqual(normalize.status_for({"bookable": False, "waitlistable": True}), "w")
        self.assertEqual(normalize.status_for({"bookable": False, "waitlistable": False, "capacity": 5}), "f")
        # No seats at all: not full, just not bookable here (a drop-in, or registered elsewhere).
        self.assertEqual(normalize.status_for({"bookable": False, "waitlistable": False, "capacity": 0}), "i")
        self.assertEqual(normalize.status_for({"cancelled": True, "capacity": 0}), "x")

    def test_kind_rules(self):
        self.assertEqual(normalize.kind_for("Public Tour", "Public Tour", CONFIG), "p")
        self.assertEqual(normalize.kind_for("Textiles Open Studio - Members Only", "Textiles", CONFIG), "m")
        self.assertEqual(normalize.kind_for("Metal Shop Mentor Hours", "Metal Shop", CONFIG), "m")
        self.assertEqual(normalize.kind_for("Block Printing - 1 Day - $65", "Skill-Share", CONFIG), "c")
        self.assertEqual(normalize.kind_for("Open House", "Open House", CONFIG), "p")

    def test_a_listing_with_no_seats_is_a_public_event(self):
        # The Fixit Clinic and a Rec & Park workshop are listed in Mindbody with capacity 0.
        self.assertEqual(normalize.kind_for("Fixit Clinic - No Registration, just drop in", "Other", CONFIG, 0), "p")
        self.assertEqual(normalize.kind_for("Free Senior Art Workshop: Make a Triangle Shelf", "Wood Shop", CONFIG, 0), "p")
        self.assertEqual(normalize.kind_for("Block Printing - 1 Day - $65", "Skill-Share", CONFIG, 6), "c")

    def test_categories_merge_and_unknown_become_other(self):
        types = [{"id": "a", "name": "Textiles Shop"}, {"id": "b", "name": "Skillshare"},
                 {"id": "c", "name": "Public Tour"}, {"id": "d", "name": "Wood Shop"}]
        result = normalize.category_names(types, CONFIG)
        self.assertEqual(result["a"], ("Textiles", "Textiles"))
        self.assertEqual(result["b"], ("Skill-Share", "Skill-Share"))
        self.assertEqual(result["c"], ("Public Tour", "Other"))
        self.assertEqual(result["d"], ("Wood Shop", "Wood Shop"))

    def test_booking_link_uses_local_day_and_course_tab(self):
        start = datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)  # 5 PM the day before in Truckee
        tz = ZoneInfo("America/Los_Angeles")
        self.assertEqual(normalize.booking_link(317649, start, tz, False),
                         "https://clients.mindbodyonline.com/classic/ws?studioid=317649&stype=-7&sView=day&sDate=10/18/2026")
        self.assertIn("stype=-8", normalize.booking_link(317649, start, tz, True))

    def test_instructor_names(self):
        self.assertEqual(normalize.instructor_for({"staff": [{"displayLabel": "ALIN LUCHIAN"}]}, "", CONFIG), "Alin Luchian")
        self.assertEqual(normalize.instructor_for({"staff": [{"displayLabel": "Volunteer Volunteer"}]}, "", CONFIG), "Volunteer guide")
        self.assertEqual(normalize.instructor_for({"staff": None}, "Pat Smith", CONFIG), "Pat Smith")
        self.assertEqual(normalize.instructor_for({"staff": None}, "", CONFIG), "Instructor not listed")


class GroupingTest(unittest.TestCase):
    def test_weekly_series_stays_separate(self):
        records = [record("Public Tour - Come Check Out", "2026-10-%02dT20:00:00" % d, group="tour") for d in (3, 10, 17, 24)]
        self.assertEqual([len(g) for g in normalize.group_sessions(records, CONFIG)], [1, 1, 1, 1])

    def test_course_sessions_merge(self):
        records = [record("Sewing 101 - 2 Days -$145", "2026-10-24T00:00:00", group="s"),
                   record("Sewing 101 - 2 Days -$145", "2026-10-27T00:00:00", group="s")]
        groups = normalize.group_sessions(records, CONFIG)
        self.assertEqual([len(g) for g in groups], [2])

    def test_repeat_runs_of_a_course_stay_apart(self):
        starts = ["2026-10-24T00:00:00", "2026-10-25T00:00:00", "2026-11-21T00:00:00", "2026-11-22T00:00:00"]
        records = [record("Butcher Blocks- $115-2 sessions", s, group="b") for s in starts]
        self.assertEqual([len(g) for g in normalize.group_sessions(records, CONFIG)], [2, 2])

    def test_course_cut_by_the_date_range_is_still_one_event(self):
        records = [record("Wood Shop 101 - 2 Days - $145", "2027-01-15T17:00:00", group="w")]
        self.assertEqual([len(g) for g in normalize.group_sessions(records, CONFIG)], [1])


class SnapshotRegressionTest(unittest.TestCase):
    """The rules must reproduce the hand-built page of Oct 17, 2026 (see tests/golden/page_v1.json)."""

    # Rules read more from the descriptions than the hand-built table did.
    EXPECTED_DIFFERENCES = {
        "Beaded Necklaces & Bracelets": {"pnote": "materials included"},
        "Encaustic Photo Art": {"pnote": "materials included"},
        "Mandala Drawing": {"pnote": "materials included"},
        "Learn to Sew Pajama Pants": {"pnote": "materials included"},
        "Handsew Gingerbread People": {"pnote": "per gingerbread-maker", "anote": "Under 16 with an adult"},
        # "Students 15 and under must be accompanied by adult": missed by the hand-built page, found by the rules.
        "Block Printing": {"anote": "Under 16 with an adult"},
        "Fall Mini Rustic Porch Pots": {"anote": "Under 16 with an adult"},
        "Winter Terrarium Making": {"anote": "Under 16 with an adult"},
        # The type label ("Member Session") now says it, so the "members only" note and badge are gone.
        "Crochet Open Studio": {"pnote": None, "ptip": "$45 for non-members"},  # now a hover tooltip on "Free"
        "Metal Shop Mentor Hours": {"pnote": None},
        "Textiles Open Studio": {"pnote": None},
    }

    @classmethod
    def setUpClass(cls):
        cls.events, cls.warnings = normalize.build_events(SNAPSHOT, CONFIG)

    def test_no_warnings(self):
        self.assertEqual(self.warnings, [])

    def test_every_session_appears_once(self):
        self.assertEqual(sum(len(e["sessions"]) for e in self.events), len(SNAPSHOT["classes"]))

    def test_same_titles_as_the_hand_built_page(self):
        self.assertEqual({e["title"] for e in self.events}, set(GOLDEN["T"]))

    def test_attributes_match_the_hand_built_page(self):
        T, CAT, TYPE, ICON_FOR = GOLDEN["T"], GOLDEN["CAT"], GOLDEN["TYPE"], GOLDEN["ICON_FOR"]
        checked = set()
        for event in self.events:
            title = event["title"]
            if title in checked:
                continue
            checked.add(title)
            expected = {
                "sub": T[title].get("sub"), "kind": TYPE.get(title, "c"), "cat": CAT[title],
                "price": T[title]["price"], "pnote": T[title].get("pnote"), "age": T[title]["age"],
                "anote": T[title].get("anote"), "icon": ICON_FOR.get(CAT[title], "generic"),
            }
            expected.update(self.EXPECTED_DIFFERENCES.get(title, {}))
            actual = {key: event[key] for key in expected}
            self.assertEqual(actual, expected, title)

    def test_multi_session_events(self):
        sizes = sorted(len(e["sessions"]) for e in self.events if len(e["sessions"]) > 1)
        self.assertEqual(sizes, [2] * 8)
        for event in self.events:
            self.assertEqual("stype=-8" in event["link"], len(event["sessions"]) > 1, event["title"])

    def test_descriptions_no_longer_repeat_what_the_page_shows(self):
        import re
        policy = [re.compile(p, re.I) for p in CONFIG["description_boilerplate"]]
        for event in self.events:
            for paragraph in event["desc"]:
                for sentence in normalize._SENTENCE_END.split(paragraph):
                    self.assertFalse(any(p.search(sentence) for p in policy), sentence)
                    self.assertIsNone(normalize._MAX_STUDENTS.search(sentence), sentence)
                    if event["age"] is not None:
                        self.assertFalse(any(p.search(sentence) for p in normalize._AGE_SENTENCE), sentence)
                    if event["anote"] is not None:
                        self.assertIsNone(normalize._ACCOMPANY_SENTENCE.search(sentence), sentence)

    def test_every_event_has_a_description_that_does_not_repeat_its_name(self):
        for event in self.events:
            self.assertTrue(event["desc"], event["title"])
            self.assertFalse(event["desc"][0].lower().startswith(event["title"].lower()[:12]) and len(event["desc"][0]) <= 120, event["title"])
            self.assertTrue(all(isinstance(p, str) and p.strip() for p in event["desc"]))

    def test_seatless_listings_become_information_only_public_events(self):
        snapshot = json.loads(json.dumps(SNAPSHOT))
        sample = dict(snapshot["classes"][0], id="fixit", name="Fixit Clinic with Keep Truckee Green - No Registration, just drop in 4 - 7pm!",
                      classGroupId="csch_fixit", capacity=0, numberRegistered=0, bookable=False, waitlistable=False, cancelled=False,
                      startDateTime="2026-10-19T23:00:00.0000000Z", duration=180)
        snapshot["classes"].append(sample)
        events, _ = normalize.build_events(snapshot, CONFIG)
        fixit = next(e for e in events if e["title"].startswith("Fixit Clinic"))
        self.assertEqual((fixit["kind"], fixit["status"], fixit["cap"]), ("p", "i", 0))
        self.assertEqual(fixit["sub"], "No Registration, just drop in 4 - 7pm!")
        # nothing that has seats changed type
        self.assertEqual([e["kind"] for e in events if e["title"] == "Block Printing"], ["c"])

    def test_only_crochet_open_studio_has_a_price_tooltip(self):
        self.assertEqual({e["title"] for e in self.events if e["ptip"]}, {"Crochet Open Studio"})

    def test_cancelled_events(self):
        cancelled = sorted(e["title"] for e in self.events if e["status"] == "x")
        self.assertEqual(cancelled, ["Fall Mini Rustic Porch Pots", "Metal Shop Mentor Hours", "Public Tour", "Textiles Open Studio"])

    def test_every_event_is_complete(self):
        for event in self.events:
            self.assertNotIn("tag", event)
            self.assertIn(event["status"], "bwfxi")
            self.assertIn(event["kind"], "cmp")
            self.assertTrue(event["sessions"] and event["inst"] and event["icon"], event["title"])
            self.assertTrue(event["link"].startswith("https://clients.mindbodyonline.com/classic/ws?studioid=317649"))

    def test_output_is_deterministic(self):
        again, _ = normalize.build_events(json.loads(json.dumps(SNAPSHOT)), CONFIG)
        self.assertEqual(json.dumps(again), json.dumps(self.events))


if __name__ == "__main__":
    unittest.main()
