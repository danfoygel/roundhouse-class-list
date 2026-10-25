"""Synthetic Mindbody data for the visual tests.

Everything the page shows comes from a raw snapshot (the shape `classlist.fetch` saves) plus the
change history `classlist.changelog` derives from consecutive snapshots. This module invents both,
modelled closely on the studio's real listings -- the same naming habits ("- 2 Days - $145",
"Members Only", "Free to Member, $45 Non-Members"), session-type spellings, policy boilerplate and
booking states -- so the page is exercised the way live data exercises it, but with every shop,
every kind of event, every status and every kind of change present, and nothing that moves with
the calendar. People's names are invented.

The "current" snapshot is written out by hand below. Older snapshots are made by *undoing*
specific changes in it (`_HISTORY`), and the change history is whatever the real
`changelog.diff_snapshots` reports between them, so the entries have exactly the shape the
production job writes.

    python3 -m tests.visual.synthetic        rewrite tests/visual/fixtures/*.json
"""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from classlist import changelog

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SNAPSHOT_FILE = FIXTURES / "snapshot.json"
CHANGELOG_FILE = FIXTURES / "changelog.json"

TZ = ZoneInfo("America/Los_Angeles")
WIDGET_URL = "https://go.mindbodyonline.com/book/widgets/schedules/view/d2308654707/schedule"

# The latest fetch. The page under test pretends it is shortly after this moment.
FETCHED_AT = "2026-10-24T17:00:00Z"
DAYS = 90

# ---------------------------------------------------------------- session types
# Spelled the way the studio's widget spells them, aliases and all (see config.json).
SESSION_TYPES = [
    "Announcment", "Ceramics", "Ceramics  Multi Day Workshops", "Ceramics Workshop_short",
    "Expert Hours", "Free Class", "Jewelry", "Kids Camp", "Metal", "Metal Shop", "Open House",
    "Public Tour", "Skill Share", "Skill-Share", "Tech Shop", "Technology", "Textiles",
    "Textiles Shop", "Wood Shop",
]
_TYPE_ID = {name: "ctype_SYN%03d" % i for i, name in enumerate(SESSION_TYPES, 1)}

# ---------------------------------------------------------------- descriptions
# The studio's standard closing wording, which the page strips (config.json: description_boilerplate).
_POLICY = (
    "<p>To register, click on the BOOK button. If the class is full, you can add your name to the "
    "waitlist. If there is no BOOK or WAITLIST button, the class and waitlist are full.</p>\n"
    "<p>Cancellations made 72 hours or more in advance will receive a Roundhouse class credit. "
    "Cancellations made 72 hours or less are non-refundable and non-transferable. Roundhouse class "
    "credit may be issued for medical or family emergencies. Due to our limited class sizes, we "
    "kindly ask that you give us as much advance notice as possible -- not showing up for a class "
    "without communication affects our ability to offer valuable programming to our community.</p>\n"
    "<p>Please note that we may take photos during the workshop to use for future marketing. If you "
    "do not wish to be photographed, please email info@truckeeroundhouse.org</p>"
)
_BLANK = "<div>&nbsp;</div>"


def _desc(headline, *blocks, policy=True):
    """Mindbody-style description markup: a bold headline, then divs, <p>s and <ul>s."""
    out = ["<div><strong>%s</strong></div>" % headline, _BLANK]
    for block in blocks:
        if isinstance(block, (list, tuple)):
            out.append("<ul>%s</ul>" % "".join("<li>%s</li>" % item for item in block))
        elif block.startswith("<p>"):
            out.append(block)
        else:
            out.extend(["<div>%s</div>" % block, _BLANK])
    if policy:
        out.append(_POLICY)
    return "\n".join(out)


# ---------------------------------------------------------------- records
LOCATION = {
    "id": "loc_SYN001",
    "name": "Truckee Roundhouse",
    "localeDetails": {
        "timeZone": "America/Los_Angeles",
        "cultureName": "en-US",
        "currency": {"currencyCode": "USD", "currencySymbol": "$$", "isoDecimalDigits": 2, "subUnitMultiplier": 100},
    },
}


def _utc(day, clock):
    """Local (Pacific) "2026-11-02", "09:00" -> Mindbody's "2026-11-02T17:00:00.0000000Z"."""
    local = datetime.strptime("%s %s" % (day, clock), "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")


class _Builder:
    def __init__(self):
        self.records = []
        self._series = {}
        self._staff = {}

    def _staff_entry(self, label):
        sid = self._staff.setdefault(label, "sspec_SYN%03d" % (len(self._staff) + 1))
        return {"id": sid, "displayLabel": label}

    def add(self, name, kind, description, day, clock, minutes, capacity, registered=0, instructor=None,
            waitlist=False, cancelled=False, series=None):
        """One scheduled session. Booking flags follow the live data: seats left -> bookable;
        none left -> waitlistable if the class has a waitlist, else full; no seats at all -> neither."""
        series_id = self._series.setdefault(series or name, "csch_SYN%03d" % (len(self._series) + 1))
        start = _utc(day, clock)
        end = (datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
        full = capacity > 0 and registered >= capacity
        bookable = capacity > 0 and not full
        booking_open = datetime.strptime(start[:10], "%Y-%m-%d") - timedelta(days=60)
        self.records.append({
            "id": "cinst_SYN%04d" % (len(self.records) + 1),
            "name": name,
            "description": description,
            "classGroupId": series_id,
            "capacity": capacity,
            "numberRegistered": registered,
            "sessionTypeId": _TYPE_ID[kind],
            "startDateTime": start,
            "duration": minutes,
            "endDateTime": end,
            # A cancelled session comes through with no staff, as the live feed sends it.
            "staff": [] if cancelled or not instructor else [self._staff_entry(instructor)],
            "location": copy.deepcopy(LOCATION),
            "bookable": bookable,
            "waitlistable": full and waitlist,
            "cancelled": cancelled,
            "isBookableOnline": capacity > 0,
            "bookingWindowStart": booking_open.strftime("%Y-%m-%dT07:00:00Z"),
            "bookingWindowEnd": start[:19] + "Z",
            "earlyAccessOpensAt": None,
            "earlyAccessUpToDays": None,
            "earlyAccessMembershipIds": [],
            "type": "Class",
            "pickASpotEnabled": False,
            "room": None,
            "roomLayout": None,
            "PASClassId": None,
            "roomName": None,
            "themeName": None,
            "isTbd": False,
            "restrictedToMemberships": [],
        })
        return self.records[-1]


def _weekly(first, count, every=7):
    day = datetime.strptime(first, "%Y-%m-%d")
    return [(day + timedelta(days=every * i)).strftime("%Y-%m-%d") for i in range(count)]


# ---------------------------------------------------------------- the current schedule
def _current_records():
    b = _Builder()

    # --- Wood Shop -----------------------------------------------------------------------------
    wood_101 = _desc(
        "Wood Shop 101", "<strong>2 Days - $145</strong>",
        "Everything you need to start working safely in the wood shop. Over two mornings you will learn "
        "how the major machines work, how to read grain, and how to build a small project from rough lumber.",
        "At the end of the course, students will be able to:",
        ["Identify and safely operate the table saw, miter saw, band saw and drill press",
         "Mill a board flat and square with the jointer and planer",
         "Choose the right wood and fasteners for a project",
         "Clean up the shop thoroughly and be a steward of the space"],
        "This course counts as a safety checkout for members.",
        "Ages 16 and above. Maximum 4 students.",
    )
    for day, taken in (("2026-11-16", 4), ("2026-11-17", 4)):
        b.add("Wood Shop 101 - 2 Days - $145", "Wood Shop", wood_101, day, "09:00", 240, 4, taken, "Terry Quillen",
              waitlist=True)

    wood_102 = _desc(
        "Wood Shop 102: Make a Picture Frame", "<strong>2 Days - $145</strong>",
        "<strong>Prerequisites: Wood Shop 101 or previous wood shop experience</strong>",
        "The broad goal for this 2-day course is to help students cultivate the skills, knowledge, and "
        "attitudes necessary to start and troubleshoot intermediate woodshop projects.",
        "The course includes the fundamental woodshop machines: Planer, Jointer, Router, and Drum Sander. "
        "Students will get hands-on experience with these tools and learn how to make a picture frame by "
        "the end of the workshop.",
        "<p>-Square a rough sawn or reclaimed piece of wood with the jointer and planer<br>"
        "-Set up and use a router to finish an edge<br>-Use the biscuit joiner to add strength to a wood joint"
        "<br>-Select and apply finishes to woods (teak or linseed oil)</p>",
        "Ages 12 and above. All youth under the age of 16 must be chaperoned by an adult also taking the class.",
        "Maximum 4 students.",
    )
    for day in ("2026-10-26", "2026-10-27"):
        b.add("Wood Shop 102:  Make a Picture Frame - 2 Days - $145", "Wood Shop", wood_102, day, "17:00", 180, 4, 2,
              "Brent Farrow", waitlist=True)

    butcher = _desc(
        "Butcher Blocks for Beginners", "$115 all materials included", "2 sessions",
        "This two-day class will walk you through all the steps in making a beautiful butcher block cutting board.",
        "The course will cover the different types of wood you can use and address the difference between "
        "domestic and exotic, light and dark wood species.",
        "The second session is focused on finishing: planer action, orbital sander, mineral oil, cleaning, "
        "how to attach handles, and maintenance.",
        "This is a project-based class and does not qualify as a wood shop safety checkout for members.",
        "Ages 14 and over. Maximum 5 students.",
    )
    for first, taken in (("2026-11-21", 3), ("2027-01-09", 0)):
        for day in (first, (datetime.strptime(first, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")):
            b.add("Butcher Blocks for Beginners- $115 all materials included-2 sessions ", "Wood Shop", butcher, day,
                  "09:00", 240, 5, taken, "ALIN LUCHIAN", series="Butcher Blocks %s" % first)

    open_wood = _desc(
        "Wood Shop Open Hours - Members Only",
        "Reserve a bench and a block of time to work on your own projects. Bring your own materials or "
        "buy offcuts from the shop. A shop monitor is on site but will not be teaching.",
        "Active members who have been safety checked out in the wood shop only. Free to members. "
        "Ages 18 and over. Maximum 6 members.",
    )
    for day, taken in zip(_weekly("2026-11-07", 6, 14), (3, 6, 1, 0, 0, 2)):
        b.add("Woodshop Open Hours - Members Only", "Wood Shop", open_wood, day, "10:00", 240, 6, taken, "Mateo Rinaldi",
              waitlist=True)

    # --- Textiles ------------------------------------------------------------------------------
    sewing_101 = _desc(
        "Sewing 101 - Practical Sewing Fundamentals", "<strong>2 Days -$145</strong>",
        "Learn to thread, wind a bobbin, sew straight and curved seams, and finish edges on our "
        "sewing machines. You will leave with a finished tote bag and the confidence to sew on your own.",
        "This course counts as a safety checkout for the textiles shop.",
        "Ages 14 and over. Students under 16 must attend with an adult. Maximum 4 students.",
    )
    for day in ("2026-10-27", "2026-10-28"):
        b.add("Sewing 101 - Practical Sewing Fundamentals - 2 Days -$145", "Textiles", sewing_101, day, "17:00", 180, 4,
              4, "Judi Morales", waitlist=True)

    pajama = _desc(
        "Learn to Sew Pajama Pants", "<strong>2 Days -$90</strong>",
        "A project-based class for people who have used a sewing machine before. We will cut, pin and "
        "sew a comfortable pair of pajama pants, adding an elastic waistband and a hem.",
        "Bring a flat sheet or 2 yards of mid-weight cotton. Fabric can also be purchased in the shop.",
        "Ages 13 and over. Maximum 5 students.",
    )
    for day in ("2026-11-10", "2026-11-17"):
        b.add("Learn to Sew Pajama Pants - 2 Days -$90", "Textiles", pajama, day, "17:00", 180, 5, 3, "Bella Hartmann")

    pot_holder = _desc(
        "Crochet 101: Make a Pot Holder", "<strong>1 Day - $55</strong>",
        "Never held a hook? Start here. You will learn the chain, single crochet and how to turn a "
        "corner, and finish a sturdy pot holder to take home. Yarn and hooks are provided.",
        "Ages 12 and over. Maximum 5 students.",
    )
    b.add("Crochet 101: Make a Pot Holder - 1 Day - $55", "Textiles Shop", pot_holder, "2026-11-13", "17:00", 150, 5, 0,
          "Jane Radcliffe-Bloom")

    trinket = _desc(
        "Crochet 102: Working in the Round, Trinket Basket", "<strong>1 Day - $65</strong>",
        "Build on your crochet basics by working in the round. We will make a sturdy little trinket "
        "basket and learn how to shape the base and the sides.",
        "<strong>Prerequisite: Crochet 101 or a beginner crochet class.</strong>",
        "Ages 12 and over. Maximum 4 students.",
    )
    b.add("Crochet 102: Working in the Round, Trinket Basket - 1 Day - $65", "Textiles Shop", trinket, "2026-10-26",
          "17:00", 180, 4, 4, "Jane Radcliffe-Bloom")

    beanie = _desc(
        "Crochet 102: Make a Beanie", "<strong>1 Day - $65</strong>",
        "Make a cozy beanie in time for the first snow. You will learn to crochet in the round and "
        "shape the crown, and leave with a finished hat.",
        "Ages 12 and over. Maximum 5 students.",
    )
    b.add("Crochet 102: Make a Beanie - 1 Day - $65", "Textiles Shop", beanie, "2026-11-23", "17:00", 180, 5, 2,
          "Jane Radcliffe-Bloom")

    gingerbread = _desc(
        "Handsew Gingerbread People (Family-Friendly!)", "<strong>1 Day - $55</strong>",
        "Bring the whole family to stitch a felt gingerbread person to hang on the tree. No sewing "
        "experience needed, just patience and a love of the holidays. Hand-sewing needles are used, "
        "so little ones will need a grown-up close by.",
        "Ages 6 and over. Children under 10 must be accompanied by an adult. Maximum 10 students.",
    )
    b.add("Handsew Gingerbread People (Family-Friendly!) - 1 Day - $55", "Textiles Shop", gingerbread, "2026-11-27",
          "17:00", 120, 10, 3, "Judi Morales")

    open_textiles = _desc(
        "Textiles Open Studio - Members Only",
        "Come down to sew with our textiles guru. Bring your own projects and get mentored help, or be "
        "set up with a fun project using our large fabric supply.",
        "<p>This class is for active Roundhouse members who have been safety checked out in the "
        "textiles shop. If you are new to sewing, please take Sewing 101 first.</p>",
        "<p>We kindly request you only book ONE Open Studio session per Friday to leave space for all to enjoy.</p>",
        "<p>Limited to two people per session. Free to members only.</p>",
        "Ages 12 and over. Students under 15 must be accompanied by an adult. Maximum 2 students.",
    )
    for day, taken, wait in zip(_weekly("2026-10-30", 12), (0, 2, 1, 0, 2, 0, 0, 0, 1, 0, 0, 0),
                                (False, False, False, False, True, False, False, False, False, False, False, False)):
        b.add("Textiles Open Studio - Members Only", "Textiles", open_textiles, day, "14:00", 180, 2, taken,
              "Judi Morales", waitlist=wait)

    crochet_open = _desc(
        "Crochet Open Studio - Free to Member, $45 Non-Members",
        "Come down to crochet with our volunteer instructor. Bring your own projects and get mentored "
        "help, or just enjoy some company while you crochet.",
        "<p>This session is for those who have some crochet experience. If you are new to crochet, please "
        "take Crochet 101 or a beginning level crochet class.</p>",
        "<p>First Sundays of every month from 5pm - 8pm.</p>",
        "<p>12 and over. Under 15 must be accompanied by an adult.</p><p>Maximum 4 students</p>",
    )
    for day, taken in (("2026-11-01", 2), ("2026-12-06", 0), ("2027-01-03", 0)):
        b.add("Crochet Open Studio - Free to Member, $45 Non-Members", "Textiles", crochet_open, day, "17:00", 180, 4,
              taken, "Jane Radcliffe-Bloom")

    spanish = _desc(
        "Taller GRATUITO en español sobre reparación y arreglo de ropa",
        "Aprenda a coser botones, arreglar dobladillos y remendar su ropa favorita. Traiga la prenda que "
        "quiera reparar. No se necesita experiencia previa.",
        "Sponsored by Keep Truckee Green. Free and open to the public.",
        "Ages 10 and over. Maximum 10 students.",
    )
    b.add("Taller GRATUITO en español sobre reparación y arreglo de ropa", "Textiles", spanish, "2026-11-20", "17:00",
          120, 10, 4, "Maria Soto Cecilia Ibarra")

    # --- Metal Shop ----------------------------------------------------------------------------
    tig = _desc(
        "Intro to Gas Tungsten Arc Welding (TIG)", "<strong>2 Days -$145</strong>",
        "TIG welding gives clean, precise welds on steel, stainless and aluminum. You will learn the "
        "equipment, set-up and safety, and practice laying beads on flat and corner joints.",
        "This course counts as a safety checkout for members.",
        "Ages 16 and over. Maximum 4 students.",
    )
    for day in ("2026-12-06", "2026-12-07"):
        b.add("Intro to Gas Tungsten Arc Welding (TIG) - 2 Days -$145", "Metal Shop", tig, day, "17:00", 180, 6, 2,
              "Chris Nakamura")

    mig = _desc(
        "Intro to MIG Welding", "<strong>2 Days - $145</strong>",
        "Learn the fundamentals of wire-feed welding: machine set-up, safety, and running beads on "
        "mild steel. The second session is spent building a small welded project.",
        "This course counts as a safety checkout for members.",
        "Ages 16 and over. Maximum 4 students.",
    )
    for day in ("2026-10-31", "2026-11-01"):
        b.add("Intro to MIG Welding - 2 Days - $145", "Metal", mig, day, "09:00", 240, 4, 1, "Chris Nakamura",
              cancelled=True)

    forge = _desc(
        "Blacksmithing Basics: Forge a Bottle Opener", "<strong>1 Day - $95</strong>",
        "Light the forge and shape hot steel. You will learn fire management, hammer technique, and "
        "how to draw out, bend and twist a piece of bar stock into a bottle opener.",
        "Wear cotton or wool clothing and closed-toe leather shoes. Safety gear is provided.",
        "Ages 16 and over. Maximum 6 students.",
    )
    b.add("Blacksmithing Basics: Forge a Bottle Opener - 1 Day - $95", "Metal Shop", forge, "2026-12-12", "17:00", 240, 6,
          1, "Dario Okafor")

    mentor = _desc(
        "Metal Shop Mentor Hours - Members Only",
        "Get one-on-one help with a metal project from one of our shop mentors. Come with a plan and "
        "any materials you need.",
        "Active members who have been safety checked out in the metal shop only. Free to members. "
        "Ages 18 and over. Maximum 1 student.",
    )
    for i, day in enumerate(_weekly("2026-10-27", 12)):
        b.add("Metal Shop Mentor Hours - Members Only", "Metal Shop", mentor, day, "14:00", 120, 1,
              1 if i == 3 else 0, "Chris Nakamura", cancelled=(i == 6))

    # --- Jewelry -------------------------------------------------------------------------------
    beads = _desc(
        "Jewelry: Beaded Necklaces and Bracelets", "<strong>1 Day - $65</strong>",
        "Design and string your own necklace and bracelet set. We provide a huge selection of glass, "
        "stone and metal beads, plus clasps, wire and findings.",
        "Ages 10 and over. Maximum 10 students.",
    )
    b.add("Jewelry: Beaded Necklaces and Bracelets - 1 Day - $65", "Jewelry", beads, "2026-11-07", "17:00", 180, 10, 5,
          "Aurora Pinkham")

    earrings = _desc(
        "Mixed Metal Geometric Earrings", "<strong>1 Day - $85</strong>",
        "Cut, texture and layer copper, brass and sterling silver into a pair of geometric earrings. "
        "You will learn to saw, file, pierce and solder.",
        "Ages 14 and over. Maximum 10 students.",
    )
    b.add("Mixed Metal Geometric Earrings - 1 Day - $85", "Jewelry", earrings, "2026-11-14", "17:00", 180, 10, 9,
          "Aurora Pinkham")

    silver = _desc(
        "Intermediate Silversmithing: Bezel Making and Stone Setting", "<strong>1 Day - $140</strong>",
        "<strong>Prerequisite: Intro to Silversmithing or equivalent experience.</strong>",
        "Make a fine silver bezel, solder it to a ring or pendant base and set a cabochon stone. "
        "Stones and silver are included in the price.",
        "Ages 16 and over. Maximum 8 students.",
    )
    b.add("Intermediate Silversmithing: Bezel Making and Stone Setting - 1 Day - $140", "Jewelry", silver, "2026-12-07",
          "13:00", 240, 8, 8, "Aurora Pinkham", waitlist=True)

    # --- Skill-Share ---------------------------------------------------------------------------
    block_print = _desc(
        "Block Printing", "<strong>1 Day - $65</strong>",
        "Carve a linoleum block and print your design on paper and fabric. All materials are included.",
        "Ages 12 and over. Maximum 6 students.",
    )
    b.add("Block Printing - 1 Day - $65", "Skill-Share", block_print, "2026-10-27", "17:00", 180, 6, 2,
          "Sarita Simmons")

    encaustic = _desc(
        "Encaustic Photo Art", "<strong>2 Days - $85</strong>",
        "Encaustic is the ancient art of painting with heated, pigmented beeswax. Over two sessions you "
        "will transfer your own photographs into a layered, luminous wax piece.",
        "Ages 14 and over. Maximum 8 students.",
    )
    for day in ("2026-11-06", "2026-11-07"):
        b.add("Encaustic Photo Art - 2 Days - $85", "Skill Share", encaustic, day, "17:00", 180, 8, 0, "Nancy Holloway")

    mandala = _desc(
        "Mandala Drawing w/ Pia Lindqvist", "<strong>2 Days - $140</strong>",
        "Use a compass, ruler and fine pens to build up intricate, symmetrical mandalas. A calm, "
        "meditative course suitable for any skill level.",
        "Ages 12 and over. Maximum 12 students.",
    )
    for day in ("2026-11-16", "2026-11-17"):
        b.add("Mandala Drawing w/ Pia Lindqvist - 2 Days - $140", "Skill Share", mandala, day, "17:00", 120, 12, 0,
              "Pia Lindqvist")

    terrarium = _desc(
        "Winter Terrarium Making", "<strong>1 Day - $95</strong>",
        "Build a miniature winter landscape in glass using moss, small plants, stones and figurines. "
        "All materials are included.",
        "Ages 10 and over. Maximum 6 students.",
    )
    b.add("Winter Terrarium Making - 1 Day - $95", "Skill-Share", terrarium, "2026-12-05", "17:00", 150, 6, 6,
          "Chandler Bertrand")

    pots = _desc(
        "Fall Mini Rustic Porch Pots", "<strong>1 Day - $100, materials included</strong>",
        "Fill a rustic mini planter with seasonal greens, berries and pinecones for your porch.",
        "Ages 12 and over. Maximum 8 students.",
    )
    b.add("Fall Mini Rustic Porch Pots - 1 Day - $100, materials included", "Skill Share", pots, "2026-10-28", "17:00",
          150, 8, 3, "Chandler Bertrand", cancelled=True)

    # --- Tech Shop -----------------------------------------------------------------------------
    printing = _desc(
        "Intro to 3D Printing", "<strong>1 Day - $55</strong>",
        "From file to finished print: slice a model, level the bed, load filament and troubleshoot the "
        "most common failures on our fleet of printers. You will take home your first print.",
        "<p>This class counts as a safety checkout for members, and you will pay $15 per spool for any filament beyond the first.</p>",
        "Ages 12 and over. Maximum 6 students.",
    )
    b.add("Intro to 3D Printing - 1 Day - $55", "Technology", printing, "2026-11-19", "17:00", 150, 6, 3, "Ravi Chaudhary")

    laser = _desc(
        "Laser Cutter Safety Checkout", "<strong>1 Day - $40</strong>",
        "Required before using the laser cutter independently. We cover ventilation, fire safety, "
        "materials you may and may not cut, and run a small test job together.",
        "Ages 16 and over. Maximum 5 students.",
    )
    b.add("Laser Cutter Safety Checkout - 1 Day - $40", "Tech Shop", laser, "2026-12-03", "17:00", 90, 5, 1,
          "Ravi Chaudhary")

    ktg = _desc(
        "Free KTG Reuse & Repair Workshop: Electronics Repair",
        "Bring a broken toaster, lamp, radio or other small electronic and volunteer fixers will help "
        "you work out what is wrong and mend it.",
        "Sponsored by Keep Truckee Green.",
        "All ages welcome. Maximum 6 students.",
    )
    b.add("Free KTG Reuse & Repair Workshop: Electronics Repair ", "Tech Shop", ktg, "2026-11-15", "17:00", 150, 6, 1,
          "Josh Buchanan Seth Itow")

    ktg_bag = _desc(
        "Free KTG Reuse & Repair Workshop: Reusable Gift Bag",
        "Make a reusable fabric gift bag from donated scraps, and keep a little wrapping paper out of "
        "the landfill this season.",
        "Sponsored by Keep Truckee Green.",
        "Ages 8 and over. Maximum 10 students.",
    )
    b.add("Free KTG Reuse & Repair Workshop: Reusable Gift Bag", "Textiles", ktg_bag, "2026-12-19", "17:00", 150, 10, 1,
          "Judi Morales")

    # --- Ceramics ------------------------------------------------------------------------------
    wheel = _desc(
        "Wheel Throwing 101", "<strong>3 Days - $210</strong>",
        "Center clay, pull walls and trim a foot. Over three evenings you will make a cylinder, a bowl "
        "and a mug, and learn how glazing and firing work. Clay and firing are included.",
        "Ages 16 and over. Maximum 6 students.",
    )
    for day in ("2026-11-04", "2026-11-11", "2026-11-18"):
        b.add("Wheel Throwing 101 - 3 Days - $210", "Ceramics  Multi Day Workshops", wheel, day, "18:30", 150, 6, 4,
              "Odessa Whitfield")

    ornaments = _desc(
        "Hand-Built Holiday Ornaments", "<strong>1 Day - $45</strong>",
        "Roll, cut and stamp clay into a handful of ornaments. We will glaze and fire them for you to "
        "pick up the following week.",
        "Ages 8 and over. Children under 12 must attend with an adult. Maximum 8 students.",
    )
    b.add("Hand-Built Holiday Ornaments - 1 Day - $45", "Ceramics Workshop_short", ornaments, "2026-12-13", "10:00", 120,
          8, 2, "Odessa Whitfield")

    open_ceramics = _desc(
        "Ceramics Open Studio - Members Only",
        "Work on your own pieces, trim, glaze or hand-build. Clay can be purchased in the shop.",
        "Active members who have completed a ceramics orientation only. Free to members. "
        "Ages 18 and over. Maximum 6 members.",
    )
    for day, taken in zip(_weekly("2026-11-05", 4, 14), (1, 6, 0, 0)):
        b.add("Ceramics Open Studio - Members Only", "Ceramics", open_ceramics, day, "18:00", 180, 6, taken,
              "Odessa Whitfield", waitlist=True)

    # --- Other (class types that are not one of the shops) -------------------------------------
    camp = _desc(
        "Winter Break Maker Camp (Ages 8-12)", "<strong>3 Days - $225</strong>",
        "Three mornings of making: woodworking, textiles and electronics sampled in one fun camp. "
        "Kids bring home something from every shop. Snacks included.",
        "Ages 8 and over. Maximum 12 students.",
    )
    for day in ("2026-12-28", "2026-12-29", "2026-12-30"):
        b.add("Winter Break Maker Camp (Ages 8-12) - 3 Days - $225", "Kids Camp", camp, day, "09:00", 180, 12, 7,
              "Taylor Brandt")

    expert = _desc(
        "Expert Hours: Electronics Troubleshooting - Members Only",
        "Stuck on a circuit? A volunteer electronics expert will help you debug your project.",
        "Free to members. Ages 18 and over. Maximum 3 members.",
    )
    for day in ("2026-11-12", "2026-12-10"):
        b.add("Expert Hours: Electronics Troubleshooting - Members Only", "Expert Hours", expert, day, "18:00", 120, 3, 1,
              "Ravi Chaudhary")

    # --- Public events -------------------------------------------------------------------------
    tour = _desc(
        "Public Tour - Come Check Out the Space",
        "This is a great opportunity to check out the space and learn about the great equipment, classes "
        "and community that we offer at the Roundhouse. Most tours last about 20 minutes.",
        policy=False,
    )
    for i, day in enumerate(_weekly("2026-10-31", 12)):
        b.add("Public Tour - Come Check Out the Space", "Public Tour", tour, day, "13:00", 60, 10,
              (0, 0, 3, 0, 0, 0, 0, 10, 0, 0, 0, 0)[i], "Volunteer Volunteer", cancelled=(i == 4), waitlist=(i == 7))

    open_house = _desc(
        "Holiday Open House",
        "Join us for cider, cookies and demonstrations from every shop. Meet the instructors, try your "
        "hand at a few projects and see what members have been making. Free and open to everyone, no "
        "reservation needed.",
        policy=False,
    )
    b.add("Holiday Open House", "Open House", open_house, "2026-12-12", "16:00", 180, 0, 0, None)

    announcement = _desc(
        "Closed for Thanksgiving",
        "The Roundhouse will be closed Thursday and Friday for Thanksgiving. All shops, classes and "
        "open sessions resume on Saturday.",
        policy=False,
    )
    b.add("Closed for Thanksgiving", "Announcment", announcement, "2026-11-26", "09:00", 1440, 0, 0, None)

    seniors_name = ("Free Senior Art Workshop: Make a Triangle Shelf - Register at Free Senior Art Workshop: Make a "
                    "Triangle Shelf Register for all Senior Art Workshops at the Truckee-Donner Rec & Park")
    seniors = _desc(
        "Free Senior Art Workshop: Make a Triangle Shelf",
        "A relaxed morning of woodworking for adults 55 and over. Registration is handled by the "
        "Truckee-Donner Recreation & Park District, not here; call them or sign up on their website.",
        policy=False,
    )
    b.add(seniors_name, "Free Class", seniors, "2026-11-18", "10:00", 120, 0, 0, "Mateo Rinaldi")

    return b.records


# ---------------------------------------------------------------- history
# Each fetch happens a few hours after the one before. Steps run newest to oldest; each one
# *undoes* the changes that fetch picked up, so what is left is the schedule as the previous
# fetch saw it. Comparing the two with the real diff then yields the change entries.

def _find(records, name_start, nth=0):
    return [r for r in records if r["name"].startswith(name_start)][nth]


def _drop(records, name_start, nth=0):
    records.remove(_find(records, name_start, nth))


def _was_full(record):
    record["numberRegistered"] = record["capacity"]
    record["bookable"] = False
    record["waitlistable"] = False


def _shift(record, hours=0, minutes=None):
    start = datetime.strptime(record["startDateTime"][:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=hours)
    record["startDateTime"] = start.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    if minutes is not None:
        record["duration"] = minutes


def _undo_latest(r):
    # New listings, a seat freed up, and a cancelled course (both of its days).
    _drop(r, "Blacksmithing Basics")
    _drop(r, "Holiday Open House")
    _drop(r, "Woodshop Open Hours", 2)
    _was_full(_find(r, "Mixed Metal Geometric Earrings"))
    for session in (0, 1):
        _find(r, "Intro to MIG Welding", session)["cancelled"] = False


def _undo_morning(r):
    # A class that sold out, and a substitute teacher.
    terrarium = _find(r, "Winter Terrarium Making")
    terrarium["numberRegistered"] = 5
    terrarium["bookable"] = True
    terrarium["waitlistable"] = False
    _find(r, "Textiles Open Studio", 2)["staff"] = [{"id": "sspec_SYN900", "displayLabel": "Hollis Brandt"}]


def _undo_yesterday(r):
    # A tour moved to the afternoon, a class that got shorter, bigger welding classes.
    _shift(_find(r, "Public Tour", 2), hours=-2)
    beanie = _find(r, "Crochet 102: Make a Beanie")
    beanie["duration"] = 120
    for session in (0, 1):
        _find(r, "Intro to Gas Tungsten", session)["capacity"] = 4
    _find(r, "Hand-Built Holiday Ornaments")["capacity"] = 6
    mandala = _find(r, "Mandala Drawing", 0)
    _shift(mandala, hours=2, minutes=90)


def _undo_earlier(r):
    # A session cancelled and then reinstated, and one that was dropped from the schedule.
    _find(r, "Block Printing")["cancelled"] = True
    r.append(_ceramics_glazing())


def _undo_older(r):
    # Two public workshops that were added.
    _drop(r, "Free KTG Reuse & Repair Workshop: Electronics")
    _drop(r, "Taller GRATUITO")


def _ceramics_glazing():
    """A class that was on the schedule at an earlier fetch and has since been removed."""
    record = _Builder().add(
        "Intro to Glazing - 1 Day - $75", "Ceramics",
        _desc("Intro to Glazing", "<strong>1 Day - $75</strong>",
              "Learn how glazes behave in the kiln and glaze a set of bisque-fired pieces.",
              "Ages 14 and over. Maximum 6 students."),
        "2026-11-22", "10:00", 120, 6, 2, "Odessa Whitfield")
    record["id"] = "cinst_SYN0900"   # clear of the ids in the current schedule
    return record


# (fetched_at, how that fetch's schedule differed from the one before it), newest first.
_HISTORY = [
    (FETCHED_AT, _undo_latest),
    ("2026-10-24T11:00:00Z", _undo_morning),
    ("2026-10-23T17:00:00Z", _undo_yesterday),
    ("2026-10-21T17:00:00Z", _undo_earlier),
    ("2026-10-19T23:00:00Z", _undo_older),
]
_FIRST_FETCH = "2026-10-17T17:00:00Z"   # the oldest fetch on record; nothing before it to compare with


def _snapshot(fetched_at, records):
    first_day = datetime.strptime(fetched_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(TZ).date()
    return {
        "meta": {
            "fetched_at": fetched_at,
            "widget_url": WIDGET_URL,
            "timezone": "America/Los_Angeles",
            "first_day": first_day.isoformat(),
            "days": DAYS,
            "windows": [],
        },
        "session_types": [
            {"id": _TYPE_ID[name], "name": name, "type": "Class", "serviceGroupId": "sgrp_SYN%03d" % i,
             "serviceId": "csvc_SYN%03d" % i}
            for i, name in enumerate(SESSION_TYPES, 1)
        ],
        "classes": sorted(records, key=lambda r: (r["startDateTime"], r["id"])),
    }


def build(config):
    """(current snapshot, change history) -- `config` is the page's config.json."""
    records = _current_records()
    snapshots = [(FETCHED_AT, copy.deepcopy(records))]
    for (_, undo), (previous_fetch, _) in zip(_HISTORY, _HISTORY[1:] + [(_FIRST_FETCH, None)]):
        records = copy.deepcopy(records)
        undo(records)
        snapshots.append((previous_fetch, records))
    snapshots.reverse()   # oldest first

    entries = []
    for (old_at, old_records), (new_at, new_records) in zip(snapshots, snapshots[1:]):
        entries.extend(changelog.diff_snapshots(_snapshot(old_at, old_records), _snapshot(new_at, new_records), config))
    return _snapshot(*snapshots[-1]), entries


def _dump(value):
    return json.dumps(value, ensure_ascii=False, indent=1) + "\n"


def render_fixtures(config):
    snapshot, entries = build(config)
    return _dump(snapshot), _dump(entries)


def main():
    config = json.loads((Path(__file__).resolve().parents[2] / "config.json").read_text(encoding="utf-8"))
    snapshot, entries = render_fixtures(config)
    FIXTURES.mkdir(exist_ok=True)
    SNAPSHOT_FILE.write_text(snapshot, encoding="utf-8")
    CHANGELOG_FILE.write_text(entries, encoding="utf-8")
    print("Wrote %s and %s" % (SNAPSHOT_FILE, CHANGELOG_FILE))


if __name__ == "__main__":
    main()
