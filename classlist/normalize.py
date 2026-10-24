"""Turns raw Mindbody class records into the events shown on the page.

Every decision is a rule applied to the raw data (names, descriptions, class types, booking
flags). Anything a rule can't express lives in config.json, so the same snapshot and config
always produce the same events.
"""
import html
import re
from html.parser import HTMLParser
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------- text helpers

def plain(markup):
    """Visible text of an HTML fragment, with entities decoded and whitespace collapsed."""
    text = re.sub(r"<[^>]+>", " ", markup or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


class _ParagraphReader(HTMLParser):
    """Splits an HTML fragment into paragraphs of plain text; list items start with a bullet."""

    BLOCKS = {"p", "div", "li", "ul", "ol", "br", "tr", "h1", "h2", "h3", "h4"}

    def __init__(self):
        super().__init__()
        self.paragraphs = []
        self.current = []

    def _flush(self):
        text = clean("".join(self.current))
        self.current = []
        if text and text != "\u2022":
            self.paragraphs.append(text)

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKS:
            self._flush()
            if tag == "li":
                self.current.append("\u2022 ")

    def handle_endtag(self, tag):
        if tag in self.BLOCKS:
            self._flush()

    def handle_data(self, data):
        self.current.append(data)

    def close(self):
        super().close()
        self._flush()


# A short opening line that repeats the class name, or states its length or price, is a headline.
_HEADLINE_FACT = re.compile(r"\$\s?\d|^\d+[\s-]*(?:days?|sessions?)\b|\b\d+(?:\.\d+)?[\s-]*(?:hours?|hrs?)\b", re.I)


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_MAX_STUDENTS = re.compile(r"\bmax(?:imum)?\b[^.]{0,20}\bstudents?\b|\b\d+\s+students?\s+max(?:imum)?\b", re.I)
_AGE_SENTENCE = [
    re.compile(r"\bages?\b\s*:?\s*\d", re.I),
    re.compile(r"^appropriate for (?:students|ages?)\b[^.]*\d", re.I),
    re.compile(r"\b\d{1,2}\s*(?:and|&)\s*(?:over|above|up|older)\b", re.I),
    re.compile(r"\b\d{1,2}\s*(?:-|to)\s*adult\b", re.I),
]
_ACCOMPANY_SENTENCE = re.compile(r"(?:accompanied|chaperoned|attend with)\b[^.]*\badult", re.I)


def _repeats_the_page(sentence, boilerplate, min_age, age_note):
    """True for a sentence the page already says: booking and policy wording, seats, minimum age."""
    if any(p.search(sentence) for p in boilerplate):
        return True
    if _MAX_STUDENTS.search(sentence):
        return True
    if min_age is not None and any(p.search(sentence) for p in _AGE_SENTENCE):
        return True
    return age_note is not None and bool(_ACCOMPANY_SENTENCE.search(sentence))


def describe(markup, raw_name, boilerplate=(), min_age=None, age_note=None):
    """The class description as plain-text paragraphs.

    Left out: the repeated name/length/price headline, the studio's booking and policy wording
    (`boilerplate`, regular expressions), and sentences about seats and ages that the page already
    shows. Age sentences go only when `min_age` / `age_note` show that fact elsewhere.
    """
    reader = _ParagraphReader()
    reader.feed(markup or "")
    reader.close()
    patterns = [re.compile(p, re.I) for p in boilerplate]
    paragraphs = []
    for paragraph in reader.paragraphs:
        kept = [s for s in _SENTENCE_END.split(paragraph) if not _repeats_the_page(s, patterns, min_age, age_note)]
        if kept:
            paragraphs.append(" ".join(kept))
    lead = clean_name(raw_name).lower()[:12]
    start = 0
    while start < len(paragraphs) - 1:
        line = paragraphs[start]
        if len(line) <= 120 and (line.lower().startswith(lead) or _HEADLINE_FACT.search(line)):
            start += 1
        else:
            break
    return paragraphs[start:]


# ------------------------------------------------------------------- names

_SEGMENT_SPLIT = re.compile(r"\s+-\s*|\s*-\s+")
# After the first segment, these are pricing/length details, not part of the class name.
_DROP_SEGMENT = re.compile(r"^(?:\$|free\b|\d+\s*(?:days?|sessions?)\b|members? only\b)", re.I)


def clean_name(raw_name):
    """The class name without price, length, or "Members Only" suffixes: "Sewing 101 - Practical Sewing Fundamentals"."""
    segments = [s.strip() for s in _SEGMENT_SPLIT.split(clean(raw_name)) if s.strip()]
    kept = segments[:1] + [s for s in segments[1:] if not _DROP_SEGMENT.match(s)]
    return " - ".join(kept)


def split_title(cleaned, config):
    """(title, subtitle) for a cleaned class name."""
    override = config.get("display_overrides", {}).get(cleaned)
    if override:
        return override["title"], override.get("sub")

    title, _, sub = cleaned.partition(" - ")
    sub = sub or None

    if sub is None:
        for prefix in config.get("series_prefixes", []):
            if title.startswith(prefix + ": "):
                return title[len(prefix) + 2:].replace(" and ", " & "), prefix
        paren = re.search(r"\s*\(([^)]*)\)\s*$", title)
        if paren:
            sub = paren.group(1).strip().rstrip("!").strip()
            sub = sub[:1].upper() + sub[1:].lower()
            title = title[:paren.start()].strip()
        else:
            with_match = re.match(r"^(.*?)\s+w/\s+(.+)$", title)
            if with_match:
                title, sub = with_match.group(1), "with " + with_match.group(2)
    return title.replace(" and ", " & ") if " & " in title else title, sub


def course_size(raw_name):
    """How many sessions a multi-session course has, from names like "... - 2 Days" or "-2 sessions"."""
    match = re.search(r"\b(\d+)\s*(?:days?|sessions?)\b", raw_name, re.I)
    count = int(match.group(1)) if match else 1
    return count if count >= 2 else 1


# ------------------------------------------------------------- price and age

_FREE_FOR_MEMBERS = re.compile(r"free to members?\b[^$]*\$\s?(\d+)\s*non-?members?", re.I)


def price_tooltip(raw_name):
    """For "Free to Member, $45 Non-Members": the non-member price, shown on hover over "Free"."""
    match = _FREE_FOR_MEMBERS.search(clean(raw_name))
    return "$%s for non-members" % match.group(1) if match else None


def parse_price(raw_name, description):
    """(price, note). Prices come from the name; free and members-only classes are recognised by wording."""
    name = clean(raw_name)
    if _FREE_FOR_MEMBERS.search(name):
        return "Free", None

    priced = re.search(r"\$\s?(\d+(?:\.\d{2})?)", name)
    if priced:
        price = "$" + priced.group(1)
        unit = re.search(r"\$\s?\d+(?:\.\d{2})?\s+per\s+([a-z-]+)", description, re.I)
        if unit:
            return price, "per " + unit.group(1).lower()
        if re.search(r"materials?\s+(?:are\s+)?(?:included|provided)|all materials", name + " " + description, re.I):
            return price, "materials included"
        return price, None

    if re.search(r"\bfree\b|\bgratuito\b", name, re.I):
        return "Free", None
    if re.search(r"free to members?( only)?", description, re.I):
        return "Free", None
    return None, None


_AGE_PATTERNS = [
    re.compile(r"\bages?\s*:?\s*(\d{1,2})\b", re.I),
    re.compile(r"\bstudents\s+(\d{1,2})\s+and\s+(?:over|above|up|older)\b", re.I),
    re.compile(r"\b(\d{1,2})\s*(?:-|to)\s*adult\b", re.I),
    re.compile(r"\b(\d{1,2})\s+and\s+(?:over|above|up|older)\b", re.I),
]
_ACCOMPANY = re.compile(
    r"\b(?:under|younger than)\s+(?:the age of\s+)?(\d{1,2})\b[^.]{0,90}?"
    r"(?:accompanied|chaperoned|attend with)\s+(?:by\s+)?(?:an\s+)?adult",
    re.I,
)


_ACCOMPANY_AND_UNDER = re.compile(
    r"\b(\d{1,2})\s+and\s+under\b[^.]{0,90}?(?:accompanied|chaperoned|attend with)\s+(?:by\s+)?(?:an\s+)?adult",
    re.I,
)


def parse_age(description):
    """(minimum age or None, note about younger participants or None)."""
    minimum = None
    for pattern in _AGE_PATTERNS:
        match = pattern.search(description)
        if match:
            minimum = int(match.group(1))
            break
    accompany = _ACCOMPANY.search(description)
    and_under = _ACCOMPANY_AND_UNDER.search(description)
    if accompany:
        note = "Under %s with an adult" % accompany.group(1)
    elif and_under:
        note = "Under %d with an adult" % (int(and_under.group(1)) + 1)
    else:
        note = None
    return minimum, note


# ------------------------------------------------------- category and kind

def category_names(session_types, config):
    """{session type id: (name after aliases, shop shown on the page)}."""
    aliases = config.get("category_aliases", {})
    shops = set(config["shops"])
    result = {}
    for entry in session_types:
        name = clean(aliases.get(entry["name"], entry["name"]))
        result[entry["id"]] = (name, name if name in shops else "Other")
    return result


def kind_for(raw_name, category_name, config, capacity=None, description=""):
    """c = class, m = member session (open studio, mentor hours), p = public event.

    A listing with no seats at all (capacity 0) can't be booked through Mindbody: it is a drop-in or
    an event registered elsewhere, such as the Fixit Clinic or a Rec & Park workshop. Those are public events.
    A listing whose description matches public_description_patterns is run by an outside group, such as
    Keep Truckee Green's reuse & repair workshops: open to the public rather than a Roundhouse-taught
    class. The name varies (English and Spanish listings of the same series), so this matches on the
    sponsorship boilerplate in the description rather than the name.
    """
    if (
        capacity == 0
        or category_name in config.get("public_categories", [])
        or any(re.search(p, description, re.I) for p in config.get("public_description_patterns", []))
    ):
        return "p"
    if any(re.search(p, raw_name, re.I) for p in config.get("member_name_patterns", [])):
        return "m"
    return "c"


# ------------------------------------------------------------ small details

def iso_utc(raw):
    """"2026-10-19T00:00:00.0000000Z" -> "2026-10-19T00:00:00Z"."""
    return re.sub(r"\.\d+Z$", "Z", raw)


def parse_utc(raw):
    return datetime.strptime(iso_utc(raw), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def status_for(record):
    if record.get("cancelled"):
        return "x"
    if record.get("bookable"):
        return "b"
    if record.get("waitlistable"):
        return "w"
    if record.get("capacity") == 0:
        return "i"  # no seats to book: information only
    return "f"


def instructor_for(record, fallback, config):
    staff = record.get("staff") or []
    label = clean(" / ".join(s["displayLabel"] for s in staff if s.get("displayLabel"))) or fallback
    if not label:
        return config.get("missing_instructor", "")
    label = config.get("instructor_names", {}).get(label, label)
    return label.title() if label.isupper() else label


def booking_link(studio_id, start_utc, tz, course):
    """Mindbody's classic booking page, opened on the day of the class (course: multi-day tab)."""
    day = start_utc.astimezone(tz)
    return "https://clients.mindbodyonline.com/classic/ws?studioid=%s&stype=%s&sView=day&sDate=%s" % (
        studio_id, -8 if course else -7, day.strftime("%m/%d/%Y"))


# ------------------------------------------------------------------ events

def group_sessions(records, config):
    """Group raw records into events: one per class, or one per run of a multi-session course."""
    gap = timedelta(days=config.get("course_max_gap_days", 21))
    by_series = defaultdict(list)
    for record in records:
        by_series[record["classGroupId"]].append(record)

    groups = []
    for series in by_series.values():
        series.sort(key=lambda r: r["startDateTime"])
        size = course_size(series[0]["name"])
        if size == 1:
            groups.extend([r] for r in series)
            continue
        run = []
        for record in series:
            if run and (len(run) == size or parse_utc(record["startDateTime"]) - parse_utc(run[-1]["startDateTime"]) > gap):
                groups.append(run)
                run = []
            run.append(record)
        if run:
            groups.append(run)
    groups.sort(key=lambda g: (g[0]["startDateTime"], g[0]["name"]))
    return groups


def build_events(snapshot, config):
    """Return (events, warnings) for a raw snapshot."""
    tz = ZoneInfo(config["timezone"])
    categories = category_names(snapshot["session_types"], config)
    records = snapshot["classes"]
    warnings = []

    staff_by_name = {}
    for record in records:
        if record.get("staff"):
            staff_by_name.setdefault(clean(record["name"]), record)

    events = []
    for group in group_sessions(records, config):
        first = group[0]
        raw_name = clean(first["name"])
        cleaned = clean_name(raw_name)
        title, sub = split_title(cleaned, config)
        description = plain(first.get("description"))
        category_name, shop = categories.get(first["sessionTypeId"], ("", "Other"))
        if not category_name:
            warnings.append("%s: unknown class type %s" % (raw_name, first["sessionTypeId"]))
        price, price_note = parse_price(raw_name, description)
        min_age, age_note = parse_age(description)
        course = course_size(raw_name) > 1

        sibling = staff_by_name.get(raw_name)
        fallback = clean(" / ".join(s["displayLabel"] for s in (sibling or {}).get("staff") or []))
        instructor = instructor_for(first, fallback, config)

        statuses = {status_for(r) for r in group}
        if len(statuses) > 1:
            warnings.append("%s: sessions differ in booking status (%s)" % (raw_name, ", ".join(sorted(statuses))))
        if "$" in raw_name and price is None:
            warnings.append("%s: could not read a price" % raw_name)

        events.append({
            "title": title,
            "sub": sub,
            "kind": kind_for(raw_name, category_name, config, first["capacity"], description),
            "cat": shop,
            "icon": config["icons"].get(shop, config["generic_icon"]),
            "price": price,
            "pnote": price_note,
            "ptip": price_tooltip(raw_name),
            "desc": describe(first.get("description"), raw_name, config.get("description_boilerplate", []), min_age, age_note),
            "age": min_age,
            "anote": age_note,
            "cap": first["capacity"],
            "reg": first["numberRegistered"],
            "status": status_for(first),
            "inst": instructor,
            "link": booking_link(config["studio_id"], parse_utc(first["startDateTime"]), tz, course),
            "sessions": [{"start": iso_utc(r["startDateTime"]), "mins": r["duration"], "id": r["id"]} for r in group],
        })
    return events, warnings
