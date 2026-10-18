import json
import unittest
from datetime import date, datetime, timedelta, timezone

from classlist import fetch

# The Next-Router-State-Tree header the browser really sent for this widget's action call.
BROWSER_TREE = "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22locale%22%2C%22en%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22widgets%22%2C%7B%22children%22%3A%5B%22schedules%22%2C%7B%22children%22%3A%5B%5B%22preview%22%2C%22view%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%5B%22widgetId%22%2C%22d2308654707%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22schedule%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D%7D%2Cnull%2Cnull%5D"
URL = "https://go.mindbodyonline.com/book/widgets/schedules/view/d2308654707/schedule"


def make_page(extra_flight=""):
    """A miniature widget page: two server actions, one long encrypted argument stored as a text chunk."""
    flight = (
        '23:{"id":"classesaction","bound":"$@24"}\n24:["$@36"]\n36:"$3a"\n3a:T7,LONGENC\n'
        '27:{"id":"availabilityaction","bound":"$@28"}\n28:["$@38"]\n38:"SHORTENC"\n'
        '1:{"fetchClasses":"$h23","fetchAndTransformAvailability":"$h27",'
        '"sessionTypes":[{"id":"ctype_1","name":"Wood Shop"}]}\n' + extra_flight
    )
    half = len(flight) // 2
    pushes = "".join(
        "<script>self.__next_f.push([1,%s])</script>" % json.dumps(part) for part in (flight[:half], flight[half:])
    )
    return "<html><body>%s</body></html>" % pushes


class WidgetIdTest(unittest.TestCase):
    def test_reads_id_from_url(self):
        self.assertEqual(fetch.widget_id(URL), "d2308654707")

    def test_rejects_other_urls(self):
        with self.assertRaises(fetch.FetchError):
            fetch.widget_id("https://example.com/")


class RouterTreeTest(unittest.TestCase):
    def test_matches_what_the_browser_sends(self):
        self.assertEqual(fetch.router_state_tree("d2308654707"), BROWSER_TREE)

    def test_widget_id_is_substituted(self):
        self.assertIn("dOTHER123", fetch.router_state_tree("dOTHER123"))
        self.assertNotIn("d2308654707", fetch.router_state_tree("dOTHER123"))


class PlanWindowsTest(unittest.TestCase):
    def setUp(self):
        self.windows = fetch.plan_windows(date(2026, 10, 17), 90, "America/Los_Angeles")

    def test_four_windows_for_ninety_days(self):
        self.assertEqual(len(self.windows), 4)

    def test_first_window_starts_at_local_midnight(self):
        self.assertEqual(self.windows[0][0], "2026-10-17T07:00:00.000Z")  # PDT is UTC-7

    def test_clock_change_is_respected(self):
        self.assertEqual(self.windows[1][0], "2026-11-14T08:00:00.000Z")  # PST is UTC-8

    def test_last_window_ends_on_the_ninetieth_day(self):
        self.assertEqual(self.windows[-1][1], "2027-01-15T07:59:59.999Z")

    def test_windows_are_contiguous_and_short_enough(self):
        parse = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        for (_, end), (start, _) in zip(self.windows, self.windows[1:]):
            self.assertEqual(parse(start) - parse(end), timedelta(milliseconds=1))
        for start, end in self.windows:
            self.assertLessEqual(parse(end) - parse(start), timedelta(days=fetch.MAX_WINDOW_DAYS, hours=1))  # +1h when the clocks go back


class EncodeMultipartTest(unittest.TestCase):
    def test_fields_in_order_with_closing_boundary(self):
        body = fetch.encode_multipart([("1", '"a"'), ("0", "[1]")]).decode()
        self.assertEqual(
            body,
            '--{b}\r\nContent-Disposition: form-data; name="1"\r\n\r\n"a"\r\n'
            '--{b}\r\nContent-Disposition: form-data; name="0"\r\n\r\n[1]\r\n--{b}--\r\n'.format(b=fetch.BOUNDARY),
        )


class TrimRecordTest(unittest.TestCase):
    def test_instructor_bios_and_photos_are_dropped(self):
        record = {"id": "c1", "staff": [{"id": "s1", "displayLabel": "Pat Smith", "bio": "Long bio", "imageUrl": "https://x/y.png"}]}
        self.assertEqual(fetch.trim_record(record)["staff"], [{"id": "s1", "displayLabel": "Pat Smith"}])
        self.assertIn("bio", record["staff"][0])  # the original is not modified

    def test_records_without_staff_pass_through(self):
        self.assertEqual(fetch.trim_record({"id": "c1", "staff": None}), {"id": "c1", "staff": None})


class ParsePageTest(unittest.TestCase):
    def test_finds_actions_and_encrypted_arguments(self):
        ctx = fetch.parse_page(make_page())
        self.assertEqual(ctx.action_id, "availabilityaction")
        self.assertEqual(ctx.action_bound, '"SHORTENC"')
        self.assertEqual(ctx.classes_id, "classesaction")
        self.assertEqual(ctx.classes_bound, '"LONGENC"')  # followed the pointer to the text chunk
        self.assertEqual(ctx.session_types, [{"id": "ctype_1", "name": "Wood Shop"}])

    def test_page_without_data_is_an_error(self):
        with self.assertRaises(fetch.FetchError):
            fetch.parse_page("<html></html>")

    def test_page_missing_an_action_is_an_error(self):
        page = make_page().replace("fetchClasses", "somethingElse")
        with self.assertRaises(fetch.FetchError):
            fetch.parse_page(page)


if __name__ == "__main__":
    unittest.main()
