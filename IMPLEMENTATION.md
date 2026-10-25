# Implementation

Builds one self-contained HTML page listing the Roundhouse's upcoming classes and events from
the data behind their Mindbody booking widget. Python 3.9 or newer, standard library only.

```
python3 build.py build      # make classes.html from the saved snapshot (offline)
python3 build.py fetch      # download a fresh snapshot to data/snapshot.json
python3 build.py refresh    # fetch, then build
python3 -m unittest discover -s tests -t .
```

(Screenshot tests are separate; see Visual tests below.)

The same snapshot and config always produce the same page, byte for byte.

## How it works

```
Mindbody widget ──fetch──▶ data/snapshot.json ──normalize──▶ events ──render──▶ classes.html
  (classlist/fetch.py)        raw records          (classlist/normalize.py)  (classlist/render.py
                                 │                                            + templates/page.html
                                 └──diff against the old snapshot──▶ data/changelog.json
                                    (classlist/changelog.py)
                                                                              + assets/)
```

- **fetch** loads the widget page, reads the two server actions and their encrypted arguments
  that the page embeds, and calls the schedule action for consecutive 28-day windows (the server
  refuses ranges of about 31 days or more). For 90 days that is one page load and four requests.
  It also saves the list of class types (the shops). If a snapshot was already saved from a
  previous fetch, it is diffed against the new one (see below) before being overwritten.
- **normalize** turns raw records into events using rules, listed below.
- **render** fills `templates/page.html` with the events as JSON, the icons and logo as data
  URIs, and a few strings from `config.json`. The page itself (filters, tiles, sticky bar) is
  plain JavaScript in the template and renders from the embedded events.

## History (classlist/changelog.py)

Every `fetch` compares the new snapshot against whatever was at `data/snapshot.json` before, and
appends one entry per change to `data/changelog.json`. Changes are read per scheduled session
(a single Mindbody class instance), not per grouped event, so one session of a multi-day course
can change without affecting the others. Recognised changes:

| Type | When |
|---|---|
| `added` | A session that should already have been in the old snapshot's window now exists. |
| `removed` | A session that should still be in the new snapshot's window is gone. |
| `cancelled` / `uncancelled` | The session's cancelled flag flipped. |
| `time_changed` | Its start time and/or duration changed. |
| `capacity_changed` | Its seat count changed. |
| `fully_booked` / `spot_opened` | It became full (no longer bookable or waitlistable) or stopped being full. |
| `instructor_changed` | Its listed staff changed. |

A snapshot only covers a rolling window starting "today", so a session disappearing because its
date has passed, or appearing only because the window rolled forward far enough to reach it, is
not a real change — both are filtered out by checking that the session's date would also have
fallen inside the *other* snapshot's window. Plain registration-count changes that don't cross the
full/not-full line are not logged, to avoid an entry for every booking.

Each entry has an `at` (fetch time), `type` (the enum above), the session's `class_id`, `name` and
`start`, and for some types a `detail` object with the before/after values — never a pre-rendered
sentence; `classlist.changelog.TYPE_LABELS` maps each `type` to a short label ("New event added",
"Event cancelled", …) for anything that wants to display entries. `data/changelog.json` only
grows; nothing is ever removed from it.

The clock icon in the page header (see README) opens an overlay listing these entries, most
recent first. `render.py` embeds the entries plus `TYPE_LABELS` as page data (`CHANGELOG` /
`CHANGELOG_LABELS`), so the label text stays defined once, in `classlist/changelog.py`, instead
of being duplicated in the template. Clicking an entry's name closes the overlay and scrolls to
the matching tile, found via the session's `class_id`, which is carried into each event's
`sessions` list by `normalize.build_events`.

The first 14 entries in `data/changelog.json` were seeded by hand as a demo of the feature,
before any real fetch had run; each carries `"test": true` (nothing `diff_snapshots` produces
ever sets that field) so they stay visibly marked — a "Test data" badge in the overlay — instead
of being mistaken for real history once it accumulates. Remove them (and the field) once there's
enough genuine history to make the point on its own.

## The rules (classlist/normalize.py)

| Output | Rule |
|---|---|
| Title, subtitle | Split the name at " - ". Drop later pieces that are a price, "N Days", "N sessions", "Free…" or "Members Only". The next piece is the subtitle. A trailing "(Family-Friendly!)" or "w/ Name" becomes the subtitle. A name starting with a configured series prefix ("Free KTG Reuse & Repair Workshop: …") moves the prefix to the subtitle. `display_overrides` in the config handle names no rule can. |
| Price | The first `$` amount in the name. "Free to Member, $45 Non-Members" gives Free, with "$45 for non-members" as a hover tooltip. "Free" or "gratuito" in the name gives Free. A members-only class whose description says "Free to members" gives Free. Otherwise none ("No fee listed"). |
| Price note | "per X" if the description says `$N per X`; otherwise "materials included" if the name or description says materials are included or provided. |
| Minimum age | `Ages N`, `students N and over`, `N - Adult`, or `N and over/above` in the description. |
| Age note | `under N … accompanied/chaperoned/attend with … adult` gives "Under N with an adult". |
| Shop | The widget's class type, merged through `category_aliases`. Anything not in `shops` is "Other". |
| Icon | `icons` maps a shop to an image in `assets/icons`; everything else uses the generic bulb. |
| Type | Public event if the listing has no seats (capacity 0: a drop-in or an event registered elsewhere), its class type is in `public_categories`, or its description matches `public_description_patterns` (an outside group's event, such as Keep Truckee Green's reuse & repair workshops); member session if the name matches `member_name_patterns`; otherwise class. |
| Multi-session course | A name that says "N Days" or "N sessions" (N of 2 or more) groups its sessions by series id into one event of N sessions. Runs more than `course_max_gap_days` apart stay separate. |
| Description | The class description as plain-text paragraphs (bullets kept). Opening lines that repeat the name or state the length or price are dropped, as are sentences the page already shows (seats; minimum age and adult accompaniment, only when the tile shows them) and the studio's booking and policy wording (`description_boilerplate` in the config). The page shows the rest, three lines at first with "Show more" to open it. Identical descriptions are stored once. |
| Status | cancelled, else bookable, else waitlistable, else "information only" if capacity is 0 (shown as "Not bookable here" with no seat count), else full. |
| Instructor | The listed staff; cancelled sessions borrow from another session with the same name; `instructor_names` fixes names; ALL CAPS becomes Title Case. |
| Booking link | Mindbody's classic booking page on the class's local date: Classes tab for single sessions, Multi-Day Classes tab for courses (linked on day one). Mindbody has no link to a single class. |

`python3 build.py build` prints a warning for anything it could not read, such as an unknown
class type or a price it could not parse. Fix those by adding a rule or a config entry.

## Light and dark mode

The page follows the visitor's system setting. The sun/moon button in the top right switches
it, and the choice is remembered in the browser (`localStorage`, key `theme`). The colours are
tokens in `templates/page.html`: the light set on `:root`, the dark set under
`prefers-color-scheme` and under `[data-theme="dark"]`.

## Report a problem

The bug icon next to the sun/moon button opens the repository's issues page in a new tab
(`repo_url` in `config.json`).

## Subscribe-to-calendar feed

`classlist/ics.py` builds a single `.ics` file covering every non-cancelled event (one `VEVENT`
per session), written by `do_build` next to the generated page — `calendar.ics` in `dist/`
alongside `index.html`, so `upload-pages-artifact` publishes it with no workflow change. Like the
page, it is a pure function of the snapshot: `DTSTAMP` comes from `meta.fetched_at`, not the
clock, so the same snapshot always produces the same feed. The calendar icon's overlay in
`templates/page.html` shows the feed's address (`site_url` + `calendar_filename` in
`config.json`, baked in at build time as `__CALENDAR_URL__`), a copy button, and a `webcal://`
link built client-side from that same address.

## Visual tests (tests/visual)

Screenshot tests for the page itself: a real browser opens the built page, uses every control, and
each result is compared with a committed picture.

```
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium          # once

.venv/bin/python -m tests.visual               # compare every scenario with its baseline
.venv/bin/python -m tests.visual -k history    # only scenarios whose name contains "history"
.venv/bin/python -m tests.visual --update      # accept the pictures just taken as the new baselines
```

Playwright and Pillow are needed only for this; the page and the other tests stay standard-library
only. A failing run writes what it saw to `tests/visual/output/actual`, a red-highlighted difference
to `output/diff`, and `output/report.html` shows baseline, actual and difference side by side
(`output/` is not committed). After an intended visual change, look at the report, then `--update`
and commit the changed pictures with the change.

- **Synthetic data** (`synthetic.py`, written out to `fixtures/`). A made-up schedule modelled on the
  real listings: the same naming habits, session-type spellings, policy boilerplate and booking
  states, with every shop, kind of event, status (bookable, waitlist, full, cancelled, information
  only), multi-session courses and several months. Names of people are invented. The older
  snapshots are made by undoing specific changes in the current one, and the change history is
  what the real `changelog.diff_snapshots` reports between them, so it covers all nine change
  types in the production format. Regenerate with `python3 -m tests.visual.synthetic`; a normal
  unit test fails if the committed fixtures and the generator disagree.
- **Scenarios** (`scenarios.py`). Each is a starting address, a way of arriving (width, light or
  dark, first visit or returning visitor) and some clicks: type and shop filters, the waitlisted and
  cancelled checkboxes, shared links, one tile for each way a listing can look, "Show more", the add
  to calendar menu, the change history (and jumping from it to an event, loosening the filters that
  hide it), the "new since your last visit" banner, the subscribe dialog and the theme toggle. Some
  also check the page address or theme the click should have produced. The scenario's name is its
  baseline's file name; the unit tests fail for a scenario with no baseline and a baseline with no
  scenario.
- **Built the real way.** `runner.py` runs `build.py build` with a config pointing at the fixtures,
  serves the result over HTTP, and drives Chromium.
- **Deterministic.** The browser's clock is fixed (`NOW`, just after the newest fetch) and a returning
  visitor's "last seen" time is seeded, so what counts as new never moves. The page loads its
  typefaces from Google Fonts; the first response for each is saved in `fonts/` and replayed, and any
  other outside request is refused, so a run never touches the network. Animations are disabled and
  time is allowed to settle (fonts, scrolling, the jump highlight) before each picture. Repeated runs
  produce byte-identical files.
- **Comparison.** Identical bytes pass; otherwise a picture passes if fewer than 0.02% of its pixels
  differ by more than 16 per colour channel (anti-aliasing noise), and fails on any size change.
- **One set of baselines per operating system.** Text is rasterized differently on each, so pictures live
  in `baselines/darwin` (macOS, for local work) and `baselines/linux` (what CI compares against). The
  runner uses the set for the system it is on; both are checked for completeness by the unit tests.
- **In CI** (`.github/workflows/ci.yml`, job `visual`). Pull requests run `python -m tests.visual` on
  Ubuntu with the Chromium that the pinned Playwright installs; a failure uploads `output/`
  (including `report.html`) as the `visual-report` artifact. After an intended visual change, update
  both sets: `--update` locally for macOS, and for Linux run the CI workflow by hand
  (Actions, "CI", "Run workflow", tick *Take new Linux screenshots*), download the `linux-baselines`
  artifact into `tests/visual/baselines/linux`, and commit it with the change.

## Hosting (GitHub Actions + Pages)

`.github/workflows/pages.yml` runs the tests, then `python build.py refresh --out dist/index.html`,
and publishes `dist/` to GitHub Pages. It runs every 6 hours, on every push to `main`, and on
demand (Actions tab, "Update class list", "Run workflow").

- If the fetch or the tests fail, nothing is deployed, so the last good page stays up, and
  GitHub emails the repository owner about the failed run.
- The generated page (`classes.html`/`dist/`) is not committed, but the fetched
  `data/snapshot.json` and the entries it adds to `data/changelog.json` are: after a successful
  fetch, the workflow commits both back to `main` (as `github-actions[bot]`, message tagged
  `[skip ci]`) so the next scheduled run has a real previous snapshot to diff against and the
  changelog keeps growing. That commit is excluded from the push trigger (`paths-ignore:
  data/**`) so it doesn't retrigger the workflow.
- To change how often it runs, edit the `cron` line. Each run makes five requests to Mindbody.

`.github/workflows/ci.yml` checks pull requests: it runs the same offline test suite and builds
the page from the committed snapshot (`python build.py build`), without touching Mindbody or
deploying anything. The live test (`tests/test_live.py`) stays skipped there.
- One-time setup: Settings, Pages, Source: "GitHub Actions".

## Limits to know about

- **The data source is unofficial.** The widget's server action is undocumented. Mindbody can
  change it at any time, and the encrypted arguments only work for the page they came from, so
  the fetcher always loads the page first. If a fetch fails, run
  `LIVE_MINDBODY=1 python3 -m unittest tests.test_live` to see whether the page changed.
- **Terms of service.** Mindbody's terms restrict automated retrieval. Keep refreshes occasional
  and small. The supported route is the official Public API (`GET /public/v6/class/classes`),
  which needs the Roundhouse to activate your developer account. Because `normalize` only reads a
  snapshot dictionary, an API-based fetcher could replace `fetch.py` without touching the rest.
- **The page is a snapshot.** Spots left and cancellations are as of the fetch time. The footer
  says when that was. Weekly sessions continue past the last date shown.
- **Descriptions are free text.** Price and age come from text people typed, so a rewritten
  description can change what the rules find. The regression test in `tests/test_normalize.py`
  compares the rules with the hand-built page the project started from.

## Files

- `config.json`: studio, widget, timezone, shops, icons, rules' lists, overrides, page text.
- `data/snapshot.json`: the last fetch, unmodified.
- `data/changelog.json`: one entry per change seen between fetches (see History above).
- `templates/page.html`: the page's markup, styles and script, with `__TOKENS__`.
- `assets/`: logo and shop icons (the Roundhouse's artwork; see `assets/README.md`).
- `tests/`: unit tests, a frozen snapshot, and the original hand-built values.
