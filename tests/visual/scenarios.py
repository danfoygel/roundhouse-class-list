"""What the visual tests do to the page, and which screenshot each one takes.

A scenario is a starting address, a way of arriving (viewport, light/dark, whether the visitor has
been here before), some clicks, and the picture to take afterwards. Its name is the baseline's file
name under tests/visual/baselines/. Nothing here imports Playwright: the steps only call methods on
the `page` they are handed, so the list can be inspected without a browser.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

# Pretend the page is opened shortly after the newest fetch in the synthetic data (see synthetic.py).
NOW = "2026-10-24T17:30:00Z"
# A returning visitor last looked between the two newest fetches, so the newest one's changes are "new".
LAST_SEEN = "2026-10-24T12:00:00Z"

DESKTOP = (1280, 900)
TABLET = (768, 1024)
MOBILE = (390, 844)


@dataclass(frozen=True)
class Scenario:
    name: str
    query: str = ""                       # appended to the page address, e.g. "?type=classes"
    viewport: tuple = DESKTOP
    scheme: str = "light"                 # the visitor's system setting: "light" or "dark"
    returning: bool = False               # has opened the page before, at LAST_SEEN
    steps: Optional[Callable] = None      # clicks to perform once the page has loaded
    element: Optional[Callable] = None    # picture just this element (given the page) instead of the window
    full_page: bool = False               # picture the whole scrolling page ...
    max_height: Optional[int] = None      # ... but no further down than this many pixels
    expect: dict = field(default_factory=dict)   # {"query": "?type=classes"} -- checked before the picture


# ---------------------------------------------------------------- helpers
def tile(title, nth=0):
    """The nth tile whose heading is exactly `title`."""
    def find(page):
        heading = page.locator("h3.title", has_text=re.compile(r"^%s$" % re.escape(title)))
        return page.locator("li.tile").filter(has=heading).nth(nth)
    return find


def click_type(label):
    return lambda page: page.locator("#seg button", has_text=re.compile(r"^%s" % re.escape(label))).click()


def click_shop(label):
    return lambda page: page.locator("#cats button", has_text=re.compile(r"^%s" % re.escape(label))).click()


def sequence(*steps):
    def run(page):
        for step in steps:
            step(page)
    return run


def set_checkbox(selector, checked):
    return lambda page: page.locator(selector).set_checked(checked)


def open_history(page):
    page.locator("#historyToggle").click()


def open_calendar(page):
    page.locator("#calendarToggle").click()


def scroll_history_to_bottom(page):
    page.evaluate("""() => {
        for (const el of [document.getElementById("historyList"), document.getElementById("historyDialog")]) el.scrollTop = el.scrollHeight;
    }""")


def click_history_link(name, nth=0):
    return lambda page: page.locator("#historyList .history-link", has_text=name).nth(nth).click()


def click_banner_link(name):
    return lambda page: page.locator("#newList .new-link", has_text=name).click()


def show_more(title):
    return lambda page: tile(title)(page).locator(".more").click()


def open_calendar_menu(title):
    return lambda page: tile(title)(page).locator(".cal-btn").click()


# ---------------------------------------------------------------- scenarios
def _build():
    s = []

    # The page as a first-time visitor sees it, in each theme and at three widths.
    s += [
        Scenario("home-desktop-light"),
        Scenario("home-desktop-dark", scheme="dark"),
        Scenario("home-tablet-light", viewport=TABLET),
        Scenario("home-mobile-light", viewport=MOBILE),
        Scenario("home-mobile-dark", viewport=MOBILE, scheme="dark"),
        Scenario("home-desktop-full-page", full_page=True, max_height=3600),
        Scenario("theme-toggle-light-to-dark", steps=lambda page: page.locator("#themeToggle").click(),
                 expect={"theme": "dark"}),
        Scenario("theme-toggle-dark-to-light", scheme="dark", steps=lambda page: page.locator("#themeToggle").click(),
                 expect={"theme": "light"}),
    ]

    # Filtering by type.
    for slug, label in (("classes", "Classes"), ("members", "Member Sessions"), ("public", "Public Events")):
        s.append(Scenario("filter-type-%s" % slug, steps=click_type(label), full_page=True, max_height=2000,
                          expect={"query": "?type=%s" % slug}))

    # Filtering by shop.
    for slug, label in (("textiles", "Textiles"), ("metal-shop", "Metal Shop"), ("wood-shop", "Wood Shop"),
                        ("skill-share", "Skill-Share"), ("jewelry", "Jewelry"), ("tech-shop", "Tech Shop"),
                        ("ceramics", "Ceramics"), ("other", "Other")):
        s.append(Scenario("filter-shop-%s" % slug, steps=click_shop(label), full_page=True, max_height=2000,
                          expect={"query": "?shop=%s" % slug}))

    # Combinations, the two checkboxes, and nothing matching.
    s += [
        Scenario("filter-classes-and-metal-shop", full_page=True,
                 steps=sequence(click_type("Classes"), click_shop("Metal Shop")),
                 expect={"query": "?type=classes&shop=metal-shop"}),
        Scenario("filter-waitlisted-hidden", full_page=True, max_height=2000,
                 steps=set_checkbox("#showWaitlisted", False), expect={"query": "?waitlisted=0"}),
        Scenario("filter-cancelled-shown", full_page=True, max_height=2000,
                 steps=set_checkbox("#showCancelled", True), expect={"query": "?cancelled=1"}),
        Scenario("filter-classes-bookable-only", full_page=True, max_height=2000,
                 steps=sequence(click_type("Classes"), set_checkbox("#showWaitlisted", False)),
                 expect={"query": "?type=classes&waitlisted=0"}),
        Scenario("filter-no-results", steps=sequence(click_type("Member Sessions"), click_shop("Jewelry")),
                 expect={"query": "?type=members&shop=jewelry"}),
        Scenario("filter-mobile-classes-wood-shop", viewport=MOBILE,
                 steps=sequence(click_type("Classes"), click_shop("Wood Shop"))),
    ]

    # Shared links: the filters are read back from the address.
    s += [
        Scenario("deeplink-members-wood-shop", query="?type=members&shop=wood-shop", full_page=True, max_height=2000),
        Scenario("deeplink-every-filter", query="?type=classes&shop=textiles&waitlisted=0&cancelled=1", full_page=True,
                 max_height=2000),
        Scenario("deeplink-unknown-values-ignored", query="?type=bogus&shop=basket-weaving",
                 expect={"query": ""}),
    ]

    # One tile for each way a listing can look.
    tiles = [
        ("tile-bookable", "Block Printing", ""),
        ("tile-waitlist", "Sewing 101", ""),
        ("tile-full", "Crochet 102: Working in the Round", ""),
        ("tile-cancelled", "Fall Mini Rustic Porch Pots", "?cancelled=1"),
        ("tile-info-only", "Holiday Open House", ""),
        ("tile-multi-session", "Wheel Throwing 101", ""),
        ("tile-three-sessions-camp", "Winter Break Maker Camp", ""),
        ("tile-free-members-with-price-tooltip", "Crochet Open Studio", ""),
        ("tile-age-with-adult", "Handsew Gingerbread People", ""),
        ("tile-materials-included", "Butcher Blocks for Beginners", ""),
        ("tile-per-unit-price", "Intro to 3D Printing", ""),
        ("tile-no-fee-listed", "Public Tour", ""),
        ("tile-public-sponsored-workshop", "Electronics Repair", ""),
        ("tile-spanish", "Taller gratuito: reparación y arreglo de ropa", ""),
        ("tile-title-override-and-info-only", "Free Senior Art Workshop: Make a Triangle Shelf", ""),
        ("tile-instructor-not-listed", "Closed for Thanksgiving", ""),
        ("tile-description-collapsed", "Wood Shop 101", ""),
    ]
    for name, title, query in tiles:
        s.append(Scenario(name, query=query, element=tile(title)))
    s += [
        Scenario("tile-description-expanded", element=tile("Wood Shop 101"), steps=show_more("Wood Shop 101")),
        Scenario("tile-waitlist-dark", scheme="dark", element=tile("Sewing 101")),
        Scenario("tile-cancelled-dark", scheme="dark", query="?cancelled=1", element=tile("Intro to MIG Welding")),
        Scenario("tile-mobile-multi-session", viewport=MOBILE, element=tile("Wheel Throwing 101")),
        Scenario("tile-mobile-description-expanded", viewport=MOBILE, element=tile("Wood Shop 101"),
                 steps=show_more("Wood Shop 101")),
        Scenario("calendar-menu-open", steps=open_calendar_menu("Block Printing")),
        Scenario("calendar-menu-open-multi-session", steps=open_calendar_menu("Wheel Throwing 101")),
    ]

    # The change history.
    s += [
        Scenario("history-first-visit", steps=open_history),
        Scenario("history-first-visit-scrolled-to-oldest", steps=sequence(open_history, scroll_history_to_bottom)),
        Scenario("history-returning-visitor", returning=True, steps=open_history),
        Scenario("history-returning-visitor-dark", returning=True, scheme="dark", steps=open_history),
        Scenario("history-mobile", viewport=MOBILE, returning=True, steps=open_history),
        Scenario("history-jump-to-event", returning=True,
                 steps=sequence(open_history, click_history_link("Mixed Metal Geometric Earrings"))),
        Scenario("history-jump-to-cancelled-event-shows-cancelled", returning=True,
                 steps=sequence(open_history, click_history_link("Intro to MIG Welding")),
                 expect={"query": "?cancelled=1"}),
        Scenario("history-jump-clears-filters-that-hide-the-event", query="?type=public&shop=other&waitlisted=0",
                 steps=sequence(open_history, click_history_link("Winter Terrarium Making")),
                 expect={"query": "?waitlisted=0"}),
    ]

    # The "new since your last visit" banner and the clock icon's dot.
    s += [
        Scenario("new-banner-returning-visitor", returning=True),
        Scenario("new-banner-returning-visitor-mobile", returning=True, viewport=MOBILE),
        Scenario("new-banner-dark", returning=True, scheme="dark"),
        Scenario("new-banner-dismissed", returning=True, steps=lambda page: page.locator("#newBannerClose").click()),
        Scenario("new-banner-jump-to-event", returning=True, steps=click_banner_link("Blacksmithing Basics")),
        Scenario("new-banner-show-all-changes", returning=True, steps=lambda page: page.locator("#newBannerAll").click()),
    ]

    # Subscribe to the calendar.
    s += [
        Scenario("calendar-dialog", steps=open_calendar),
        Scenario("calendar-dialog-dark", scheme="dark", steps=open_calendar),
        Scenario("calendar-dialog-mobile", viewport=MOBILE, steps=open_calendar),
    ]
    return s


SCENARIOS = _build()
