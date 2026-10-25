#!/usr/bin/env python3
"""Builds the Truckee Roundhouse class list page.

    python3 build.py build      Make the page from the saved snapshot (offline).
    python3 build.py fetch      Download a fresh snapshot from Mindbody's widget.
    python3 build.py refresh    Fetch, then build.

Settings live in config.json. See README.md.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from classlist import changelog, fetch, ics, normalize, render  # noqa: E402


def load_config(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def do_fetch(config):
    snapshot = fetch.fetch_snapshot(config["widget_url"], config["timezone"], config["horizon_days"])
    target = ROOT / config["snapshot_path"]
    old_snapshot = None
    if target.exists():
        try:
            old_snapshot = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            old_snapshot = None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("Saved %d sessions to %s" % (len(snapshot["classes"]), target.relative_to(ROOT)))

    if old_snapshot is not None:
        entries = changelog.diff_snapshots(old_snapshot, snapshot, config)
        if entries:
            log_path = ROOT / config["changelog_path"]
            changelog.append_entries(log_path, entries)
            print("Logged %d change%s to %s" % (
                len(entries), "" if len(entries) == 1 else "s", log_path.relative_to(ROOT)))


def do_build(config, output=None):
    source = ROOT / config["snapshot_path"]
    if not source.exists():
        sys.exit("No snapshot at %s. Run: python3 build.py fetch" % source.relative_to(ROOT))
    snapshot = json.loads(source.read_text(encoding="utf-8"))
    events, warnings = normalize.build_events(snapshot, config)
    history = changelog.load_entries(ROOT / config["changelog_path"])
    page = render.render_page(events, snapshot["meta"], config, ROOT / "templates" / "page.html", ROOT / "assets", history)
    target = Path(output) if output else ROOT / config["output_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    sessions = sum(len(e["sessions"]) for e in events)
    print("Wrote %s: %d events (%d sessions), snapshot from %s" % (target, len(events), sessions, snapshot["meta"]["fetched_at"]))
    for warning in warnings:
        print("warning: " + warning)

    feed = ics.build_feed(events, snapshot["meta"])
    feed_target = target.parent / config["calendar_filename"]
    feed_target.write_text(feed, encoding="utf-8")
    print("Wrote %s" % feed_target)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["build", "fetch", "refresh"])
    parser.add_argument("--config", default=str(ROOT / "config.json"))
    parser.add_argument("--out", help="write the page here instead of the path in config.json")
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command in ("fetch", "refresh"):
        do_fetch(config)
    if args.command in ("build", "refresh"):
        do_build(config, args.out)


if __name__ == "__main__":
    main()
