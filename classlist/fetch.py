"""Reads class data from Mindbody's public booking widget, the same way the widget's own page does.

The widget page embeds two server-action references and their encrypted arguments. Calling the
action with a date range returns the classes in that range. Nothing here uses credentials, but
it relies on an undocumented interface and can break whenever Mindbody redeploys; the official
Public API is the supported route. Mindbody's terms of service also restrict automated access,
so keep this to occasional, low-volume refreshes (a few requests per run).
"""
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import rsc

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
# The server rejects ranges of about 31 days or more (36 days failed, 29 worked).
MAX_WINDOW_DAYS = 28
BOUNDARY = "----classlistFormBoundary"


class FetchError(RuntimeError):
    pass


def widget_id(url):
    match = re.search(r"/view/([A-Za-z0-9]+)/schedule", url)
    if not match:
        raise FetchError("Could not find the widget id in %r" % url)
    return match.group(1)


# The route tree the browser sends with this action call, as captured from the widget page
# (URL-encoded, with the widget id as the only variable part).
_SAMPLE_WIDGET_ID = "d2308654707"
_ROUTER_TREE_ENCODED = (
    "%5B%22%22%2C%7B%22children%22%3A%5B%5B%22locale%22%2C%22en%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22widgets%22%2C"
    "%7B%22children%22%3A%5B%22schedules%22%2C%7B%22children%22%3A%5B%5B%22preview%22%2C%22view%22%2C%22d%22%5D%2C%7B%22children%22%3A"
    "%5B%5B%22widgetId%22%2C%22d2308654707%22%2C%22d%22%5D%2C%7B%22children%22%3A%5B%22schedule%22%2C%7B%22children%22%3A%5B%22__PAGE__%22"
    "%2C%7B%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D"
    "%2Cnull%2Cnull%2Ctrue%5D%7D%2Cnull%2Cnull%5D"
)


def router_state_tree(wid):
    """The `Next-Router-State-Tree` header value for the widget's schedule page."""
    return _ROUTER_TREE_ENCODED.replace(_SAMPLE_WIDGET_ID, wid)


def encode_multipart(fields):
    chunks = []
    for name, value in fields:
        chunks.append('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (BOUNDARY, name, value))
    chunks.append("--%s--\r\n" % BOUNDARY)
    return "".join(chunks).encode("utf-8")


def _utc_iso(local_dt):
    utc = local_dt.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (utc.microsecond // 1000)


def plan_windows(start_date, days, tz_name, window_days=MAX_WINDOW_DAYS):
    """Split `days` days from `start_date` into local-midnight-to-23:59:59.999 ranges, as UTC strings."""
    tz = ZoneInfo(tz_name)
    end_date = start_date + timedelta(days=days - 1)
    windows = []
    cursor = start_date
    while cursor <= end_date:
        last = min(cursor + timedelta(days=window_days - 1), end_date)
        first_dt = datetime(cursor.year, cursor.month, cursor.day, tzinfo=tz)
        last_dt = datetime(last.year, last.month, last.day, 23, 59, 59, 999000, tzinfo=tz)
        windows.append((_utc_iso(first_dt), _utc_iso(last_dt)))
        cursor = last + timedelta(days=1)
    return windows


class PageContext:
    """What the widget page tells us: the action to call, its encrypted arguments, and class types."""

    def __init__(self, action_id, action_bound, classes_id, classes_bound, session_types):
        self.action_id = action_id
        self.action_bound = action_bound
        self.classes_id = classes_id
        self.classes_bound = classes_bound
        self.session_types = session_types


def _server_reference(chunks, flight, prop):
    """Find a server action passed to the page as `"<prop>":"$h<chunk>"`; return (id, encrypted args)."""
    match = re.search(r'"%s":"\$h([0-9a-f]+)"' % re.escape(prop), flight)
    if not match:
        raise FetchError("The widget page has no %r action; Mindbody may have changed the page." % prop)
    ref = json.loads(chunks[match.group(1)][1])
    bound_list = json.loads(chunks[ref["bound"][2:]][1])
    kind, text = chunks[bound_list[0][2:]]
    # A long encrypted argument may itself be a pointer ("$3a") to a text chunk.
    pointer = re.fullmatch(r'"\$([0-9a-f]+)"', text) if kind == "J" else None
    if pointer and pointer.group(1) in chunks:
        kind, text = chunks[pointer.group(1)]
    encrypted = json.dumps(text) if kind == "T" else text
    return ref["id"], encrypted


def parse_page(html):
    pushes = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    if not pushes:
        raise FetchError("The widget page has no embedded data; Mindbody may have changed the page.")
    flight = "".join(json.loads(p) for p in pushes)
    chunks = rsc.parse_chunks(flight.encode("utf-8"))
    action_id, action_bound = _server_reference(chunks, flight, "fetchAndTransformAvailability")
    classes_id, classes_bound = _server_reference(chunks, flight, "fetchClasses")
    session_types = rsc.json_after(flight, '"sessionTypes":')
    if not session_types:
        raise FetchError("The widget page lists no class types.")
    return PageContext(action_id, action_bound, classes_id, classes_bound, session_types)


class Client:
    def __init__(self, page_url, delay=1.0, log=print):
        self.page_url = page_url
        self.delay = delay
        self.log = log
        self.origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(page_url))
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _open(self, request):
        for attempt in (1, 2):
            try:
                with self.opener.open(request, timeout=45) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                detail = error.read(300).decode("utf-8", "replace").replace("\n", " ")
                raise FetchError("%s returned HTTP %s: %s" % (request.full_url, error.code, detail))
            except urllib.error.URLError as error:
                if attempt == 2:
                    raise FetchError("Could not reach %s: %s" % (request.full_url, error.reason))
                time.sleep(2)

    def load_page(self):
        request = urllib.request.Request(
            self.page_url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
        )
        return parse_page(self._open(request).decode("utf-8"))

    def fetch_window(self, ctx, from_iso, to_iso):
        fields = [
            ("1", ctx.action_bound),
            ("3", ctx.classes_bound),
            ("2", '["$@3"]'),
            ("4", json.dumps({"id": ctx.classes_id, "bound": "$@2"}, separators=(",", ":"))),
            ("0", json.dumps(["$@1", {"fromDate": from_iso, "toDate": to_iso, "fetchClasses": "$h4"}], separators=(",", ":"))),
        ]
        request = urllib.request.Request(
            self.page_url,
            data=encode_multipart(fields),
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/x-component",
                "Content-Type": "multipart/form-data; boundary=" + BOUNDARY,
                "Next-Action": ctx.action_id,
                "Next-Router-State-Tree": router_state_tree(widget_id(self.page_url)),
                "Origin": self.origin,
                "Referer": self.page_url,
            },
        )
        chunks = rsc.parse_chunks(self._open(request))
        data = rsc.find_json_chunk(chunks, '{"classes"')
        if data is None:
            raise FetchError("Mindbody rejected the request for %s to %s." % (from_iso, to_iso))
        return data["classes"]


def trim_record(record):
    """Keep only what the page uses from each instructor (names are public; bios and photos are not needed)."""
    staff = record.get("staff")
    if isinstance(staff, list):
        record = dict(record, staff=[{"id": m.get("id"), "displayLabel": m.get("displayLabel")} for m in staff])
    return record


def fetch_snapshot(widget_url, tz_name, horizon_days, today=None, delay=1.0, log=print):
    """Download every class from `today` for `horizon_days` days and return the raw snapshot."""
    client = Client(widget_url, delay=delay, log=log)
    log("Loading %s" % widget_url)
    ctx = client.load_page()
    tz = ZoneInfo(tz_name)
    today = today or datetime.now(tz).date()
    windows = plan_windows(today, horizon_days, tz_name)
    classes = {}
    for index, (from_iso, to_iso) in enumerate(windows, 1):
        log("Window %d of %d: %s to %s" % (index, len(windows), from_iso, to_iso))
        for record in client.fetch_window(ctx, from_iso, to_iso):
            classes[record["id"]] = trim_record(record)
        if index < len(windows):
            time.sleep(delay)
    ordered = sorted(classes.values(), key=lambda c: (c["startDateTime"], c["id"]))
    return {
        "meta": {
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "widget_url": widget_url,
            "timezone": tz_name,
            "first_day": today.isoformat(),
            "days": horizon_days,
            "windows": windows,
        },
        "session_types": ctx.session_types,
        "classes": ordered,
    }
