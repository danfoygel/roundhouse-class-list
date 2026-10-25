"""Diffs two snapshots and keeps a running log of what changed between them.

Changes are read at the level of a single scheduled session (a Mindbody class instance, keyed by
its id), not the grouped multi-session events the page shows: that keeps the diff exact and lets a
change to one session of a multi-day course be reported on its own.

A snapshot only covers a rolling window starting "today" (see `fetch.fetch_snapshot`), so a session
disappears from it just because its date has passed, and a session appears just because the window
rolled forward far enough to reach it. Neither is a real change, so both are filtered out: a session
is only reported as added/removed when its date falls inside the *other* snapshot's window too,
meaning it should have already been there (removed) or should still be there (added) if nothing
about it had changed.
"""
import json
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from . import normalize


def _display_name(record, config):
    cleaned = normalize.clean_name(record["name"])
    title, sub = normalize.split_title(cleaned, config)
    return "%s - %s" % (title, sub) if sub else title


def _instructor_label(record):
    staff = record.get("staff") or []
    return " / ".join(s["displayLabel"] for s in staff if s.get("displayLabel"))


def _horizon(meta):
    first_day = date.fromisoformat(meta["first_day"])
    return first_day, first_day + timedelta(days=meta["days"] - 1)


def _start_date(record, tz):
    return normalize.parse_utc(record["startDateTime"]).astimezone(tz).date()


def _fmt(iso, tz):
    text = normalize.parse_utc(iso).astimezone(tz).strftime("%a %b %d, %Y, %I:%M %p")
    return text.replace(" 0", " ")  # drop leading zeros from the day and the hour


# A short, fixed label for each `type` value, for a consumer that wants to display entries without
# hardcoding its own copy of this list. Entries themselves only ever carry the `type` enum value;
# nothing about what kind of change it was is encoded into free text.
TYPE_LABELS = {
    "added": "New event added",
    "removed": "Event removed",
    "cancelled": "Event cancelled",
    "uncancelled": "Event un-cancelled",
    "time_changed": "Event date/time changed",
    "capacity_changed": "Capacity changed",
    "fully_booked": "Event fully booked",
    "spot_opened": "Spot opened up",
    "instructor_changed": "Instructor changed",
}


def _entry(fetched_at, change_type, record, config, tz, detail=None):
    detail = dict(detail or {})
    entry = {
        "at": fetched_at,
        "type": change_type,
        "class_id": record["id"],
        "name": _display_name(record, config),
        "start": normalize.iso_utc(record["startDateTime"]),
    }
    if detail:
        entry["detail"] = detail
    return entry


def _field_changes(fetched_at, old_record, new_record, config, tz):
    changes = []
    old_cancelled, new_cancelled = bool(old_record.get("cancelled")), bool(new_record.get("cancelled"))
    if not old_cancelled and new_cancelled:
        changes.append(_entry(fetched_at, "cancelled", new_record, config, tz))
    elif old_cancelled and not new_cancelled:
        changes.append(_entry(fetched_at, "uncancelled", new_record, config, tz))

    time_detail = {}
    if old_record["startDateTime"] != new_record["startDateTime"]:
        time_detail["was_start"] = normalize.iso_utc(old_record["startDateTime"])
        time_detail["was_start_label"] = _fmt(old_record["startDateTime"], tz)
    if old_record.get("duration") != new_record.get("duration"):
        time_detail["was_duration"] = old_record.get("duration")
        time_detail["duration"] = new_record.get("duration")
    if time_detail:
        changes.append(_entry(fetched_at, "time_changed", new_record, config, tz, time_detail))

    if old_record.get("capacity") != new_record.get("capacity"):
        changes.append(_entry(fetched_at, "capacity_changed", new_record, config, tz, {
            "was_capacity": old_record.get("capacity"), "capacity": new_record.get("capacity"),
        }))

    if not new_cancelled:
        old_status, new_status = normalize.status_for(old_record), normalize.status_for(new_record)
        if old_status != "f" and new_status == "f":
            changes.append(_entry(fetched_at, "fully_booked", new_record, config, tz))
        elif old_status == "f" and new_status in ("b", "w"):
            changes.append(_entry(fetched_at, "spot_opened", new_record, config, tz))

    old_instructor, new_instructor = _instructor_label(old_record), _instructor_label(new_record)
    if old_instructor and new_instructor and old_instructor != new_instructor:
        changes.append(_entry(fetched_at, "instructor_changed", new_record, config, tz, {
            "was_instructor": old_instructor, "instructor": new_instructor,
        }))

    return changes


def diff_snapshots(old_snapshot, new_snapshot, config):
    """Return changelog entries for what changed from `old_snapshot` to `new_snapshot`, oldest first."""
    tz = ZoneInfo(config["timezone"])
    fetched_at = new_snapshot["meta"]["fetched_at"]
    old_classes = {record["id"]: record for record in old_snapshot["classes"]}
    new_classes = {record["id"]: record for record in new_snapshot["classes"]}
    old_first, old_last = _horizon(old_snapshot["meta"])
    new_first, new_last = _horizon(new_snapshot["meta"])

    entries = []
    for class_id, record in new_classes.items():
        if class_id not in old_classes and old_first <= _start_date(record, tz) <= old_last:
            entries.append(_entry(fetched_at, "added", record, config, tz))
    fetched_at_dt = normalize.parse_utc(fetched_at)
    for class_id, record in old_classes.items():
        if class_id in new_classes:
            continue
        # A session Mindbody has already started showing as past (even earlier today) drops out of
        # the feed on its own; that is not a removal. Catching this needs the exact fetch instant,
        # not just the day: a same-day session can start in the gap between two fetches.
        if normalize.parse_utc(record["startDateTime"]) <= fetched_at_dt:
            continue
        if new_first <= _start_date(record, tz) <= new_last:
            entries.append(_entry(fetched_at, "removed", record, config, tz))
    for class_id, new_record in new_classes.items():
        old_record = old_classes.get(class_id)
        if old_record is not None:
            entries.extend(_field_changes(fetched_at, old_record, new_record, config, tz))

    entries.sort(key=lambda e: (e["start"], e["class_id"], e["type"]))
    return entries


def load_entries(path):
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def append_entries(path, entries):
    """Add `entries` to the changelog data file at `path`, creating it if needed."""
    log = load_entries(path)
    log.extend(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return log
