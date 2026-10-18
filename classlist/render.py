"""Fills the page template with events, images and text."""
import base64
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def _data_uri(path):
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _script_json(value):
    """JSON that is safe inside an HTML <script> block."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _long_date(iso_utc, tz_name):
    moment = datetime.strptime(iso_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))
    return "%s %d, %d" % (moment.strftime("%b"), moment.day, moment.year)


def render_page(events, meta, config, template_path, assets_dir):
    """Return the finished HTML. Same inputs always give the same output."""
    assets = Path(assets_dir)
    icons = {p.stem: _data_uri(p) for p in sorted((assets / "icons").glob("*.png"))}
    used = {e["icon"] for e in events}
    missing = used - set(icons)
    if missing:
        raise ValueError("No icon image for: %s" % ", ".join(sorted(missing)))

    # Weekly sessions repeat the same description, so events point into one shared table.
    descriptions, positions, slim = [], {}, []
    for event in events:
        key = json.dumps(event["desc"], ensure_ascii=False)
        if key not in positions:
            positions[key] = len(descriptions)
            descriptions.append(event["desc"])
        slim.append(dict(event, desc=positions[key]))

    replacements = {
        "__TITLE__": html.escape(config["page"]["title"]),
        "__HEADING__": html.escape(config["page"]["heading"]),
        "__HOME_URL__": html.escape(config["home_url"], quote=True),
        "__FETCHED_DATE__": _long_date(meta["fetched_at"], config["timezone"]),
        "__TZ__": config["timezone"],
        "__EVENTS_JSON__": _script_json(slim),
        "__DESCS_JSON__": _script_json(descriptions),
        "__ICONS_JSON__": _script_json({name: icons[name] for name in sorted(used)}),
        "__LOGO__": _data_uri(assets / "logo.png"),
    }
    page = Path(template_path).read_text(encoding="utf-8")
    for token, value in replacements.items():
        if token not in page:
            raise ValueError("Template has no %s" % token)
        page = page.replace(token, value)
    leftover = re.findall(r"__[A-Z_]{3,}__", page)
    if leftover:
        raise ValueError("Unfilled template tokens: %s" % ", ".join(sorted(set(leftover))))
    return page
