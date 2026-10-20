import json
import re
import unittest
from pathlib import Path

from classlist import normalize, render

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
SNAPSHOT = json.loads((ROOT / "tests" / "fixtures" / "snapshot_2026-10-17.json").read_text(encoding="utf-8"))
TEMPLATE = ROOT / "templates" / "page.html"
ASSETS = ROOT / "assets"


def page_for(events, meta=None):
    return render.render_page(events, meta or SNAPSHOT["meta"], CONFIG, TEMPLATE, ASSETS)


def embedded(page, name):
    match = re.search(r"^const %s = (.*);$" % name, page, re.M)
    return json.loads(match.group(1))


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events, _ = normalize.build_events(SNAPSHOT, CONFIG)
        cls.page = page_for(cls.events)

    def test_is_a_complete_document_that_scales_on_phones(self):
        self.assertTrue(self.page.startswith("<!doctype html>"))
        self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1', self.page)
        self.assertIn('<html lang="en">', self.page)
        self.assertTrue(self.page.rstrip().endswith("</html>"))

    def test_has_a_theme_toggle_that_starts_from_the_system_setting(self):
        self.assertIn('id="themeToggle"', self.page)
        # A saved choice is applied in <head>, before the page paints; with none saved, the system setting rules.
        head = self.page.split("</head>")[0]
        self.assertIn('localStorage.getItem("theme")', head)
        self.assertIn("@media (prefers-color-scheme: dark)", self.page)
        self.assertIn(':root[data-theme="dark"]', self.page)

    def test_theme_icon_uses_the_hidden_attribute(self):
        # `hidden` is not a property of SVG elements, so assigning it changes nothing on screen.
        # (Ordinary elements such as buttons are fine.)
        self.assertNotIn('.i-moon").hidden', self.page)
        self.assertNotIn('.i-sun").hidden', self.page)
        self.assertIn('.toggleAttribute("hidden"', self.page)

    def test_filter_bar_is_pinned_on_every_screen_width(self):
        css = self.page.split("<style>")[1].split("</style>")[0]
        filters_rule = css.split(".filters {")[1].split("}")[0]
        self.assertIn("position: sticky", filters_rule)
        self.assertNotIn("min-width: 701px", css)

    def test_tile_label_names_the_type_before_the_shop(self):
        self.assertIn('const KIND_LABEL = { c: "Class", m: "Member Session", p: "Public Event" };', self.page)
        self.assertIn("${KIND_LABEL[c.kind]} :", self.page)

    def test_bug_icon_opens_the_issues_page_in_a_new_tab(self):
        link = re.search(r'<a class="icon-btn" href="([^"]+)" target="_blank" rel="noopener"', self.page)
        self.assertIsNotNone(link)
        self.assertEqual(link.group(1), CONFIG["repo_url"].rstrip("/") + "/issues")

    def test_bullet_paragraphs_become_an_indented_list(self):
        self.assertIn("function descriptionHtml(", self.page)
        css = self.page.split("<style>")[1].split("</style>")[0]
        rule = css.split(".desc ul {")[1].split("}")[0]
        self.assertIn("padding-left", rule)
        self.assertIn("list-style: disc", rule)  # nested lists would otherwise get hollow circles
        self.assertIn(".desc li {", css)

    def test_information_only_events_say_so_instead_of_full(self):
        self.assertIn('i: "Not bookable here"', self.page)
        self.assertIn('c.status === "x" || c.status === "i"', self.page)  # no fake "0 of 0" seats

    def test_no_unfilled_tokens(self):
        self.assertEqual(re.findall(r"__[A-Z_]{3,}__", self.page), [])

    def test_events_are_embedded_intact(self):
        descriptions = embedded(self.page, "DESCS")
        rebuilt = [dict(e, desc=descriptions[e["desc"]]) for e in embedded(self.page, "EVENTS")]
        self.assertEqual(rebuilt, self.events)

    def test_repeated_descriptions_are_stored_once(self):
        descriptions = embedded(self.page, "DESCS")
        self.assertEqual(len(descriptions), len({json.dumps(d) for d in descriptions}))
        self.assertLess(len(descriptions), len(self.events))

    def test_page_text_comes_from_config(self):
        self.assertIn("<title>Roundhouse Class List</title>", self.page)
        self.assertIn("<h1>Classes and Events</h1>", self.page)
        self.assertIn('href="https://www.truckeeroundhouse.org/"', self.page)

    def test_footer_date_is_the_snapshot_date_in_local_time(self):
        self.assertIn("Copied from their public Mindbody schedule on Oct 17, 2026.", self.page)

    def test_only_used_icons_are_embedded(self):
        icons = embedded(self.page, "ICONS")
        self.assertEqual(set(icons), {e["icon"] for e in self.events})
        for uri in icons.values():
            self.assertTrue(uri.startswith("data:image/png;base64,"))

    def test_same_input_gives_identical_page(self):
        self.assertEqual(self.page, page_for(self.events))

    def test_script_breaking_text_is_escaped(self):
        event = dict(self.events[0], title="</script><b>x", desc=["</script><i>y"])
        page = page_for([event])
        self.assertNotIn("</script><b>", page)
        self.assertNotIn("</script><i>", page)
        self.assertEqual(embedded(page, "EVENTS")[0]["title"], "</script><b>x")
        self.assertEqual(embedded(page, "DESCS")[0], ["</script><i>y"])

    def test_missing_icon_image_is_an_error(self):
        event = dict(self.events[0], icon="nonexistent")
        with self.assertRaises(ValueError):
            page_for([event])


if __name__ == "__main__":
    unittest.main()
