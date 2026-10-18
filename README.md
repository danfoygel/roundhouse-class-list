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
                                                                              + templates/page.html
                                                                              + assets/)
```

- **fetch** loads the widget page, reads the two server actions and their encrypted arguments
  that the page embeds, and calls the schedule action for consecutive 28-day windows (the server
  refuses ranges of about 31 days or more). For 90 days that is one page load and four requests.
  It also saves the list of class types (the shops).
- **normalize** turns raw records into events using rules, listed below.
- **render** fills `templates/page.html` with the events as JSON, the icons and logo as data
  URIs, and a few strings from `config.json`. The page itself (filters, tiles, sticky bar) is
  plain JavaScript in the template and renders from the embedded events.

## The rules (classlist/normalize.py)

| Output | Rule |
|---|---|
| Title, subtitle | Split the name at " - ". Drop later pieces that are a price, "N Days", "N sessions", "Free…" or "Members Only". The next piece is the subtitle. A trailing "(Family-Friendly!)" or "w/ Name" becomes the subtitle. A name starting with a configured series prefix ("Free KTG Reuse & Repair Workshop: …") moves the prefix to the subtitle. `display_overrides` in the config handle names no rule can. |
| Price | The first `$` amount in the name. "Free to Member, $45 Non-Members" gives Free with a note. "Free" or "gratuito" in the name gives Free. A members-only class whose description says "Free to members" gives Free. Otherwise none ("No fee listed"). |
| Price note | "per X" if the description says `$N per X`; otherwise "materials included" if the name or description says materials are included or provided. |
| Minimum age | `Ages N`, `students N and over`, `N - Adult`, or `N and over/above` in the description. |
| Age note | `under N … accompanied/chaperoned/attend with … adult` gives "Under N with an adult". |
| Shop | The widget's class type, merged through `category_aliases`. Anything not in `shops` is "Other". |
| Icon | `icons` maps a shop to an image in `assets/icons`; everything else uses the generic bulb. |
| Type | Public event if the class type is in `public_categories`; member session if the name matches `member_name_patterns`; otherwise class. |
| Multi-session course | A name that says "N Days" or "N sessions" (N of 2 or more) groups its sessions by series id into one event of N sessions. Runs more than `course_max_gap_days` apart stay separate. |
| Status | cancelled, else bookable, else waitlistable, else full. |
| Instructor | The listed staff; cancelled sessions borrow from another session with the same name; `instructor_names` fixes names; ALL CAPS becomes Title Case. |
| Booking link | Mindbody's classic booking page on the class's local date: Classes tab for single sessions, Multi-Day Classes tab for courses (linked on day one). Mindbody has no link to a single class. |

`python3 build.py build` prints a warning for anything it could not read, such as an unknown
class type or a price it could not parse. Fix those by adding a rule or a config entry.

## Light and dark mode

The page follows the visitor's system setting. The sun/moon button in the top right switches
it, and the choice is remembered in the browser (`localStorage`, key `theme`). The colours are
tokens in `templates/page.html`: the light set on `:root`, the dark set under
`prefers-color-scheme` and under `[data-theme="dark"]`.

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
- The generated page is not committed. `data/snapshot.json` in the repo is only a seed for
  offline builds; the workflow replaces it with a fresh fetch on every run.
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
- `templates/page.html`: the page's markup, styles and script, with `__TOKENS__`.
- `assets/`: logo and shop icons (the Roundhouse's artwork; see `assets/README.md`).
- `tests/`: unit tests, a frozen snapshot, and the original hand-built values.
