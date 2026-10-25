"""Builds the page from the synthetic data, drives it in Chromium and compares screenshots.

    python3 -m tests.visual                 compare every scenario with its baseline
    python3 -m tests.visual -k history      only scenarios whose name contains "history"
    python3 -m tests.visual --update        (re)write the baselines for the selected scenarios
    python3 -m tests.visual --list          print the scenario names

Needs Playwright and Pillow (requirements-dev.txt); see IMPLEMENTATION.md. Pictures taken this run
go to tests/visual/output/actual, differences to tests/visual/output/diff, and report.html there
puts baseline, actual and difference side by side.
"""
import argparse
import functools
import html
import http.server
import hashlib
import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from urllib.parse import urlsplit

from . import scenarios as scenario_module

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIXTURES = HERE / "fixtures"
# Text is rasterized differently on each operating system, so each keeps its own set of baselines.
PLATFORM = sys.platform if sys.platform in ("darwin", "linux") else "other"
BASELINES = HERE / "baselines" / PLATFORM
OUTPUT = HERE / "output"
FONTS = HERE / "fonts"

# A pixel counts as different when any colour channel is off by more than this ...
CHANNEL_TOLERANCE = 16
# ... and a picture fails when more than this fraction of its pixels are different. Anti-aliasing
# jitter stays well under it; a moved, resized or recoloured element does not.
MAX_DIFFERENT_FRACTION = 0.0002


# ---------------------------------------------------------------- building and serving the page
def build_site(site_dir):
    """Run the real build.py against the synthetic snapshot and history; return the page's directory."""
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    config["snapshot_path"] = str(FIXTURES / "snapshot.json")
    config["changelog_path"] = str(FIXTURES / "changelog.json")
    site_dir.mkdir(parents=True, exist_ok=True)
    config_path = site_dir.parent / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "build.py"), "build", "--config", str(config_path), "--out", str(site_dir / "index.html")],
        capture_output=True, text=True,
    )
    if result.returncode:
        sys.exit("build.py failed:\n%s%s" % (result.stdout, result.stderr))
    warnings = [line for line in result.stdout.splitlines() if line.startswith("warning:")]
    if warnings:
        sys.exit("The synthetic data produced build warnings:\n" + "\n".join(warnings))
    return site_dir


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(directory):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(directory)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


# ---------------------------------------------------------------- keeping the browser offline
FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")


class FontCache:
    """The page loads its typefaces from Google Fonts. Pictures must not depend on the network (or on
    whatever Google serves that day), so the first response for each font URL is saved under
    tests/visual/fonts and served from there ever after. Any other outside request is refused."""

    def __init__(self, directory):
        self.directory = directory
        self.index_path = directory / "index.json"
        self.index = json.loads(self.index_path.read_text()) if self.index_path.exists() else {}

    def handle(self, route):
        url = route.request.url
        host = urlsplit(url).hostname
        if host in ("127.0.0.1", "localhost"):
            route.continue_()
        elif host not in FONT_HOSTS:
            route.abort()
        elif url in self.index:
            entry = self.index[url]
            route.fulfill(status=200, body=(self.directory / entry["file"]).read_bytes(),
                          headers={"content-type": entry["type"], "access-control-allow-origin": "*"})
        else:
            response = route.fetch()
            body = response.body()
            name = hashlib.sha1(url.encode()).hexdigest()[:16] + (".css" if host == "fonts.googleapis.com" else ".woff2")
            self.directory.mkdir(exist_ok=True)
            (self.directory / name).write_bytes(body)
            self.index[url] = {"file": name, "type": response.headers.get("content-type", "application/octet-stream")}
            self.index_path.write_text(json.dumps(self.index, indent=1, sort_keys=True) + "\n")
            route.fulfill(response=response)


# ---------------------------------------------------------------- taking the picture
def settle(page):
    """Wait until nothing is moving: fonts loaded, scrolling finished, jump highlight faded."""
    page.evaluate("document.fonts.ready.then(() => null)")
    # A jump to an event adds its highlight on the next frame; let that happen before checking it has faded.
    page.evaluate("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
    page.wait_for_function("!document.querySelector('.jump-highlight')", timeout=5000)
    last = None
    for _ in range(50):
        now = page.evaluate("[window.scrollX, window.scrollY, document.documentElement.scrollHeight]")
        if now == last:
            return
        last = now
        page.wait_for_timeout(120)


def check_expectations(page, scenario):
    for what, wanted in scenario.expect.items():
        if what == "query":
            got = page.evaluate("location.search")
        elif what == "theme":
            got = page.evaluate("document.documentElement.getAttribute('data-theme')")
        else:
            raise ValueError("Unknown expectation %r" % what)
        if got != wanted:
            raise AssertionError("expected %s %r, page has %r" % (what, wanted, got))


def capture(browser, base_url, fonts, scenario, path):
    width, height = scenario.viewport
    context = browser.new_context(
        viewport={"width": width, "height": height},
        color_scheme=scenario.scheme,
        device_scale_factor=1,
        locale="en-US",
        timezone_id="America/Los_Angeles",
        reduced_motion="reduce",
    )
    try:
        context.route("**/*", fonts.handle)
        page = context.new_page()
        page.clock.set_fixed_time(scenario_module.NOW)
        if scenario.returning:
            context.add_init_script("try { localStorage.setItem('changelogSeenAt', %s); } catch (e) {}"
                                    % json.dumps(scenario_module.LAST_SEEN))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(base_url + scenario.query, wait_until="load")
        page.wait_for_selector("#out li.tile, #out .empty")
        if scenario.steps:
            scenario.steps(page)
        settle(page)
        page.mouse.move(1, 1)   # no tile or button left in its hover state
        check_expectations(page, scenario)
        if errors:
            raise AssertionError("the page logged errors: " + "; ".join(errors))
        options = {"path": str(path), "animations": "disabled", "caret": "hide"}
        if scenario.element:
            scenario.element(page).screenshot(**options)
        elif scenario.full_page:
            total = page.evaluate("document.documentElement.scrollHeight")
            clip = {"x": 0, "y": 0, "width": width, "height": min(total, scenario.max_height or total)}
            page.screenshot(full_page=True, clip=clip, **options)
        else:
            page.screenshot(**options)
    finally:
        context.close()


# ---------------------------------------------------------------- comparing
def compare(actual, baseline, diff):
    """(ok, message). Writes a highlighted difference image to `diff` when they don't match."""
    from PIL import Image, ImageChops

    if actual.read_bytes() == baseline.read_bytes():
        return True, "identical"
    a, b = Image.open(actual).convert("RGB"), Image.open(baseline).convert("RGB")
    if a.size != b.size:
        return False, "size changed from %dx%d to %dx%d" % (b.size + a.size)
    delta = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > CHANNEL_TOLERANCE else 0)
    different = delta.histogram()[255]
    fraction = different / float(a.size[0] * a.size[1])
    if fraction <= MAX_DIFFERENT_FRACTION:
        return True, "%d pixels differ within tolerance" % different
    highlight = Image.blend(b.convert("L").convert("RGB"), Image.new("RGB", a.size, (255, 255, 255)), 0.6)
    highlight.paste(Image.new("RGB", a.size, (230, 30, 30)), mask=delta)
    diff.parent.mkdir(parents=True, exist_ok=True)
    highlight.save(diff)
    return False, "%d pixels differ (%.3f%%)" % (different, fraction * 100)


def write_report(results):
    rows = []
    for name, ok, message in results:
        cells = ""
        for label, src in (("baseline", "../baselines/%s/%s.png" % (PLATFORM, name)), ("actual", "actual/%s.png" % name),
                           ("difference", "diff/%s.png" % name)):
            if label == "difference" and ok:
                continue
            cells += '<figure><figcaption>%s</figcaption><a href="%s"><img src="%s" loading="lazy"></a></figure>' % (label, src, src)
        rows.append((ok, '<section class="%s"><h2>%s <small>%s</small></h2><div>%s</div></section>'
                     % ("ok" if ok else "bad", html.escape(name), html.escape(message), cells)))
    failed = sum(1 for _, ok, _ in results if not ok)
    page = """<!doctype html><meta charset="utf-8"><title>Visual test report</title>
<style>
body { font: 14px system-ui; margin: 24px; } h1 small, h2 small { font-weight: normal; color: #666; }
section { margin: 0 0 28px; } section.bad h2 { color: #b00020; } section > div { display: flex; gap: 12px; align-items: flex-start; flex-wrap: wrap; }
figure { margin: 0; max-width: 32%%; } figcaption { color: #666; margin-bottom: 4px; } img { max-width: 100%%; border: 1px solid #ccc; }
</style><h1>Visual test report <small>%d of %d scenarios differ</small></h1>%s""" % (failed, len(results), "\n".join(row for _, row in sorted(rows, key=lambda r: r[0])))
    (OUTPUT / "report.html").write_text(page, encoding="utf-8")


# ---------------------------------------------------------------- command line
def main(argv=None):
    parser = argparse.ArgumentParser(prog="python3 -m tests.visual", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-k", dest="match", help="only scenarios whose name contains this text")
    parser.add_argument("--update", action="store_true", help="write the pictures taken as the new baselines")
    parser.add_argument("--list", action="store_true", help="print scenario names and exit")
    args = parser.parse_args(argv)

    selected = [s for s in scenario_module.SCENARIOS if not args.match or args.match in s.name]
    if args.list:
        print("\n".join(s.name for s in selected))
        return 0
    if not selected:
        sys.exit("No scenario name contains %r" % args.match)

    try:
        from playwright.sync_api import sync_playwright
        import PIL  # noqa: F401
    except ImportError:
        sys.exit("Visual tests need Playwright and Pillow:\n"
                 "  python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt\n"
                 "  .venv/bin/playwright install chromium\n"
                 "  .venv/bin/python -m tests.visual")

    if not BASELINES.exists() and not args.update:
        sys.exit("No baselines for %s yet (tests/visual/baselines/%s). Create them with --update." % (PLATFORM, PLATFORM))

    for folder in ("actual", "diff"):
        if not args.match:
            shutil.rmtree(OUTPUT / folder, ignore_errors=True)
        (OUTPUT / folder).mkdir(parents=True, exist_ok=True)
    site = build_site(OUTPUT / "site")
    server = serve(site)
    base_url = "http://127.0.0.1:%d/index.html" % server.server_address[1]

    fonts = FontCache(FONTS)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for scenario in selected:
            actual = OUTPUT / "actual" / ("%s.png" % scenario.name)
            baseline = BASELINES / ("%s.png" % scenario.name)
            diff = OUTPUT / "diff" / ("%s.png" % scenario.name)
            diff.unlink(missing_ok=True)
            try:
                capture(browser, base_url, fonts, scenario, actual)
            except Exception as error:   # a broken scenario should not hide the others
                results.append((scenario.name, False, "error: %s" % str(error).splitlines()[0]))
                print("ERROR  %-55s %s" % (scenario.name, results[-1][2]))
                continue
            if args.update:
                BASELINES.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(actual, baseline)
                results.append((scenario.name, True, "baseline written"))
                print("wrote  %s" % scenario.name)
                continue
            if not baseline.exists():
                results.append((scenario.name, False, "no baseline (run with --update)"))
                print("MISSING %-54s no baseline (run with --update)" % scenario.name)
                continue
            ok, message = compare(actual, baseline, diff)
            results.append((scenario.name, ok, message))
            print("%s %-55s %s" % ("ok    " if ok else "FAIL  ", scenario.name, message))
        browser.close()
    server.shutdown()

    write_report(results)
    failed = [name for name, ok, _ in results if not ok]
    if args.update:
        print("\nWrote %d of %d baselines. Report: %s" % (len(results) - len(failed), len(results), OUTPUT / "report.html"))
    else:
        print("\n%d of %d scenarios failed. Report: %s" % (len(failed), len(results), OUTPUT / "report.html"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
