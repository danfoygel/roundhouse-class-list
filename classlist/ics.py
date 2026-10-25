"""Builds the public .ics feed: every upcoming event, for subscribing in Google Calendar and
others. Mirrors the single-event download built client-side in templates/page.html (icsDataUrl),
but as one VCALENDAR covering every non-cancelled event, so same inputs always give the same feed.
"""
from datetime import timedelta

from .normalize import parse_utc

# One venue, so events are plain UTC instants; no per-event timezone to carry. Matches CAL_LOCATION
# in templates/page.html.
LOCATION = "Truckee Roundhouse"


def _escape(text):
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _stamp(moment):
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _details(event):
    return "\n\n".join([*event["desc"], "Book: %s" % event["link"]])


def _vevent(event, session, stamp):
    start = parse_utc(session["start"])
    end = start + timedelta(minutes=session["mins"])
    return "\r\n".join([
        "BEGIN:VEVENT",
        "UID:rh-%s@roundhouse-class-list" % session["id"],
        "DTSTAMP:%s" % stamp,
        "DTSTART:%s" % _stamp(start),
        "DTEND:%s" % _stamp(end),
        "SUMMARY:%s" % _escape(event["title"]),
        "LOCATION:%s" % _escape(LOCATION),
        "DESCRIPTION:%s" % _escape(_details(event)),
        "END:VEVENT",
    ])


def build_feed(events, meta):
    """The .ics text for every session of every non-cancelled event."""
    stamp = _stamp(parse_utc(meta["fetched_at"]))
    body = [
        _vevent(event, session, stamp)
        for event in events if event["status"] != "x"
        for session in event["sessions"]
    ]
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Roundhouse Class List//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Truckee Roundhouse Classes",
        *body,
        "END:VCALENDAR",
    ]) + "\r\n"
