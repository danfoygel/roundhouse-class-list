# Truckee Roundhouse class list

Builds one self-contained HTML page listing the Roundhouse's upcoming classes and events from
the data behind their Mindbody booking widget. Python 3.9 or newer, standard library only.

```
python3 build.py build      # make classes.html from the saved snapshot (offline)
python3 build.py fetch      # download a fresh snapshot to data/snapshot.json
python3 build.py refresh    # fetch, then build
python3 -m unittest discover -s tests -t .
```

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
| Type | Public event if the listing has no seats (capacity 0: a drop-in or an event registered elsewhere) or its class type is in `public_categories`; member session if the name matches `member_name_patterns`; otherwise class. |
| Multi-session course | A name that says "N Days" or "N sessions" (N of 2 or more) groups its sessions by series id into one event of N sessions. Runs more than `course_max_gap_days` apart stay separate. |
| Description | The class description as plain-text paragraphs (bullets kept). Opening lines that repeat the name or state the length or price are dropped, as are sentences the page already shows (seats; minimum age and adult accompaniment, only when the tile shows them) and the studio's booking and policy wording (`description_boilerplate` in the config). The page shows the rest, three lines at first with "Show more" to open it. Identical descriptions are stored once. |
| Status | cancelled, else bookable, else waitlistable, else "information only" if capacity is 0 (shown as "Not bookable here" with no seat count), else full. |
| Instructor | The listed staff; cancelled sessions borrow from another session with the same name; `instructor_names` fixes names; ALL CAPS becomes Title Case. |
| Booking link | Mindbody's classic booking page on the class's local date: Classes tab for single sessions, Multi-Day Classes tab for courses (linked on day one). Mindbody has no link to a single class. |

`python3 build.py build` prints a warning for anything it could not read, such as an unknown
class type or a price it could not parse. Fix those by adding a rule or a config entry.

## Change history

The clock icon, left of the others, opens an overlay listing `data/changelog.json` (see History
above), most recent first, in a scrollable dialog. It reads `TYPE_LABELS` from the page's embedded
`CHANGELOG_LABELS`, so the label text lives in one place (`classlist/changelog.py`) rather than
being duplicated in the template.

## Light and dark mode

The page follows the visitor's system setting. The sun/moon button in the top right switches
it, and the choice is remembered in the browser (`localStorage`, key `theme`). The colours are
tokens in `templates/page.html`: the light set on `:root`, the dark set under
`prefers-color-scheme` and under `[data-theme="dark"]`.

## Report a problem

The bug icon next to the sun/moon button opens the repository's issues page in a new tab
(`repo_url` in `config.json`).

## Links to a filtered view

The filters are kept in the page address, so a view can be shared. The address updates as you
change filters, and opening a link restores them. Unknown values are ignored, and other
parameters in the link are left alone.

| Parameter | Values | Default |
|---|---|---|
| `type` | `classes`, `members`, `public` | all types |
| `shop` | `textiles`, `metal-shop`, `wood-shop`, `skill-share`, `jewelry`, `tech-shop`, `ceramics`, `other` (whichever shops have events) | all shops |
| `waitlisted` | `0` hides waitlisted events | shown |
| `cancelled` | `1` shows cancelled events | hidden |

For example, `?type=classes&waitlisted=0` is the classes you can still book directly, and
`?type=members&shop=wood-shop` is the wood shop's member sessions.

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
