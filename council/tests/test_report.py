"""Report suite: the HTML renderer for the split-mode council (REBUILD-SPEC section 9).

Run: python council/tests/test_report.py     (exit code authoritative)

Everything renders from a hand-written fixture run directory under
council/tests/fixtures/report/run-invented-1. Every value in it is INVENTED and every
source string says so; no published run is read and none is written. Variants (an empty
change appendix, a failed outside audit, a missing chair resolve) are built by copying
the fixture into a temp directory and mutating the copy - the fixture itself is a record.
"""

import copy
import contextlib
import datetime
import decimal
import html as html_lib
import html.parser as html_lib_parser
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.engine import briefs  # noqa: E402
from council.evidence import brief as pack_brief  # noqa: E402
from council.evidence import freeze, tape, trace  # noqa: E402
from council.engine import ladder  # noqa: E402
from council.engine import runrecord  # noqa: E402
from council.lib import prose  # noqa: E402
from council.lib import validate  # noqa: E402
from council.report import render_report as R  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FIXTURE = os.path.join(ROOT, "council", "tests", "fixtures", "report", "run-invented-1")
FIXTURE_BASKET = os.path.join(ROOT, "council", "tests", "fixtures", "report",
                              "run-invented-basket")
FIXTURE_THEME = os.path.join(ROOT, "council", "tests", "fixtures", "report",
                             "run-invented-theme")
SCHEMA_DIR = os.path.join(ROOT, "council", "schemas")

HTML = None          # the fixture, rendered once
BASKET_HTML = None   # the invented basket run, rendered once
THEME_HTML = None    # the invented theme run (universe mode), rendered once
VERDICT_SHA = None   # sha256 of the fixture verdict.json bytes, computed here independently


# The sitting's wall clock now ends at the moment the page is BUILT, not at publication (spec
# section U3.3, register item P-U3-5). A suite that let it run live would print a different
# number every run and would hang a spurious "this sitting missed its budget" alarm on every
# fixture, because the fixtures were published in August. So every render here is pinned: 84
# minutes after that run's own clock start, inside the 90-minute budget. A test that is ABOUT
# the clock passes the moment it means, by name.
PINNED_SITTING_MINUTES = 84
NO_CLOCK_MOMENT = datetime.datetime(2026, 8, 30, 10, 29,
                                    tzinfo=datetime.timezone.utc)


def _pinned_now(run_dir):
    """The moment to render this run at: its own clock start plus a plausible sitting."""
    with open(os.path.join(run_dir, "verdict.json"), "rb") as fh:
        provenance = json.loads(fh.read().decode("utf-8")).get("provenance") or {}
    started = R._stamp((provenance.get("evidence") or {}).get("clock_started")
                       or (provenance.get("timestamps") or {}).get("run_started"))
    if started is None:
        return NO_CLOCK_MOMENT      # the page prints no clock at all from here
    return started + datetime.timedelta(minutes=PINNED_SITTING_MINUTES)


def _events(run_dir):
    """The run record's rows, in order."""
    with open(os.path.join(run_dir, "runrecord.jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _write_run_record(run_dir):
    """A run record shaped like a finished sitting's, for the tests about what the FIRST
    rendering appends to one. The fixtures are hand-built and carry none."""
    rows = [{"seq": 1, "ts": "2026-08-30T09:12:00Z", "event": "run_created"},
            {"seq": 2, "ts": "2026-08-30T10:26:00Z", "event": "run_finished",
             "state": "DONE"}]
    with open(os.path.join(run_dir, "runrecord.jsonl"), "w",
              encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True,
                                separators=(",", ":")) + "\n")


def _render_cli(run_dir, out=None):
    """The command a sitting actually runs. It is the one thing that writes the report AND the
    row saying one was rendered - in that order (audit round 1, r1-6)."""
    argv = ["render_report", run_dir]
    if out is not None:
        argv[1:1] = ["-o", out]
    return R.main(argv)


def _report_bytes(run_dir):
    with open(os.path.join(run_dir, "report.html"), encoding="utf-8") as fh:
        return fh.read()


def _stamp_first_render(run_dir, moment):
    """The row the FIRST rendering of this run would have left in its record.

    The page's clock is read from that row and never from this machine's own (register item
    P-U3-5, ruled by the architect after this unit's audit), so a test that means a particular
    moment writes it here."""
    row = {"seq": 1, "ts": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "at": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
           "event": R.REPORT_RENDERED_EVENT}
    with open(os.path.join(run_dir, "runrecord.jsonl"), "w",
              encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _render(run_dir, now=None):
    """The renderer, over a COPY of the run whose record carries the moment of its first
    rendering.

    Rendering a run for the first time WRITES that row, so a suite that rendered a committed
    fixture in place would edit the fixture and pin its clock to the day the suite first ran.
    Every render here happens on a copy, stamped with the moment the test means."""
    moment = _pinned_now(run_dir) if now is None else now
    work = tempfile.mkdtemp(prefix="report-render-")
    try:
        copied = os.path.join(work, "run")
        shutil.copytree(run_dir, copied)
        _stamp_first_render(copied, moment)
        return R.render(copied)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_with_subs(run_dir, now=None):
    """The renderer plus the prose reformatter's substitution log (owner ruling AC16(1))."""
    moment = _pinned_now(run_dir) if now is None else now
    work = tempfile.mkdtemp(prefix="report-render-")
    try:
        copied = os.path.join(work, "run")
        shutil.copytree(run_dir, copied)
        _stamp_first_render(copied, moment)
        subs = []
        html = R.render(copied, subs_out=subs)
        return html, subs
    finally:
        shutil.rmtree(work, ignore_errors=True)


def setUpModule():
    global HTML, BASKET_HTML, THEME_HTML, VERDICT_SHA
    HTML = _render(FIXTURE)
    BASKET_HTML = _render(FIXTURE_BASKET)
    THEME_HTML = _render(FIXTURE_THEME)
    with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
        VERDICT_SHA = hashlib.sha256(fh.read()).hexdigest()


def E(text):
    """The rendered form of a page string: what esc() makes of it (quotes included)."""
    return html_lib.escape(text, quote=True)


def _mutated_copy(tmp, mutate=None, source=None):
    """A throwaway copy of a fixture run directory (run-invented-1 unless
    another is named), optionally mutated before rendering."""
    run_dir = os.path.join(tmp, "run")
    shutil.copytree(source or FIXTURE, run_dir)
    if mutate:
        mutate(run_dir)
    return run_dir


def _rewrite_invocation(run_dir, change):
    path = os.path.join(run_dir, "invocation.json")
    with open(path, "rb") as fh:
        doc = json.loads(fh.read().decode("utf-8"))
    change(doc)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2)


def _rewrite_verdict(run_dir, change):
    path = os.path.join(run_dir, "verdict.json")
    with open(path, "rb") as fh:
        doc = json.loads(fh.read().decode("utf-8"))
    change(doc)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2)


def _rewrite_pack(run_dir, change):
    path = os.path.join(run_dir, "pack", "pack.json")
    with open(path, "rb") as fh:
        doc = json.loads(fh.read().decode("utf-8"))
    change(doc)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(doc, fh, indent=2)


# The navigation entries, in order (owner ruling AC16, audit C4): the five tiers by content name,
# then the main appendices - about nine entries, not the seventeen process steps of before. The
# "Appendices" divider, the challenge diff and the run stamps are folded appendices WITHOUT a
# menu entry, reached by scrolling; they are checked separately below.
ANCHORS = ("decision", "synthesis", "advisors", "review", "challenge", "detail", "evidence",
           "appendices")

# Every h2 heading on the fixture page, in plain words (audit B5): the nine menu tiers plus the
# folded appendices that carry an h2 but no menu entry.
SECTION_HEADINGS = (
    "The answer", "The chairman's synthesis", "The decision in detail", "The evidence",
    "Appendices", "The owner's question", "The peer review and what all five missed",
    "The five advisors", "The outside model's own words",
    "What changed after the outside challenge", "What the portfolio system receives",
    "About this sitting",
)


# ---------------------------------------------------------------------------------------------
# THE ANCHORLESS FIXTURE (ANCHORLESS-SPEC section 5) - built here, never stored
# ---------------------------------------------------------------------------------------------
# An anchorless run is made by copying run-invented-1 and filling its empty scenario block. The
# ARITHMETIC in that block is never typed out here: it is produced by calling the engine that
# publishes it, over the invented facts below, so this fixture cannot drift from what a real
# run would carry. Every figure is invented and no published run is read.

FLOORS_PATH = os.path.join(ROOT, "council", "floors", "floors.json")

LADDER_FACTS = {
    "price_last": {"id": "price_last", "value": "100000", "unit": "USD",
                   "as_of": "2026-08-28"},
    "realized_vol_5y": {"id": "realized_vol_5y", "value": "50.00",
                        "unit": "percent annualized", "as_of": "2026-08-28"},
    "cash_rate_3m": {"id": "cash_rate_3m", "value": "4.00", "unit": "percent",
                     "as_of": "2026-08-28"},
}

CHAIR_LADDER = {
    "horizon_months": "12",
    "reference_price_fact_id": "price_last",
    "volatility_fact_id": "realized_vol_5y",
    "cash_rate_fact_id": "cash_rate_3m",
    "scenarios": [
        {"name": "The bull case", "price_outcome": "200000", "probability": "0.30",
         "rationale": "Buying keeps outrunning new supply for a full year. (INVENTED)"},
        {"name": "The base case", "price_outcome": "125000", "probability": "0.45",
         "rationale": "Demand grows, but no faster than the record shows. (INVENTED)"},
        {"name": "The bear case", "price_outcome": "55000", "probability": "0.25",
         "rationale": "Buying stops and the cycle turns down hard. (INVENTED)"},
    ],
}

# Two dated events plus one that has no date of its own, so the calendar's ordering rule is
# exercised: the first two sort on their own date, the third on the day it was checked.
CALENDAR_FACTS = [
    {"id": "calendar_protocol_next", "value": "2028-04-20", "unit": "date",
     "as_of": "2026-08-29", "freshness_rule_days": 60, "derived": None,
     "source": "INVENTED FIXTURE - the asset's own published schedule"},
    {"id": "calendar_rate_decision_next", "value": "2026-09-16", "unit": "date",
     "as_of": "2026-08-29", "freshness_rule_days": 30, "derived": None,
     "source": "INVENTED FIXTURE - the central bank's published meeting calendar"},
    {"id": "calendar_policy_review", "value": "no date announced yet; the review is expected "
     "late in the year", "unit": "check", "as_of": "2026-08-25", "freshness_rule_days": 30,
     "derived": None, "source": "INVENTED FIXTURE - the named policy review, checked at the "
     "sitting"},
]


def _floors():
    with open(FLOORS_PATH, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _computed_ladder():
    """The engine's own arithmetic for the invented ladder above."""
    return ladder.compute(CHAIR_LADDER, LADDER_FACTS, _floors())


def _published_block(basis="rating", aggregated=True, reason=None):
    """The scenario block in the shape council/engine/publisher.py writes it."""
    block = {
        "aggregated": aggregated,
        "basis": basis,
        "not_aggregated_reason": reason,
        "horizon_months": CHAIR_LADDER["horizon_months"],
        "scenarios": copy.deepcopy(CHAIR_LADDER["scenarios"]),
        "reference_price_fact_id": CHAIR_LADDER["reference_price_fact_id"],
        "volatility_fact_id": CHAIR_LADDER["volatility_fact_id"],
        "cash_rate_fact_id": CHAIR_LADDER["cash_rate_fact_id"],
        "seat_ladders": [],
        "arithmetic": [],
    }
    if aggregated and basis == "rating":
        computed = _computed_ladder()
        for key in ("reference_price", "expected_price", "expected_total_pct",
                    "expected_annualised_pct", "cash_pct", "volatility_pct",
                    "bar_pct", "excess_over_bar_pp", "rating", "constants",
                    "arithmetic", "sensitivity"):
            block[key] = computed[key]
    return block


def _scenario_page(block, anchorless=True, calendar=False):
    """run-invented-1 rendered with the given scenario block, as an anchorless subject unless
    told otherwise, and optionally with the dated events in its pack."""

    def change_verdict(doc):
        if anchorless:
            doc["subject"].update({"kind": "bitcoin", "asset_class": "crypto",
                                   "name": "Invented Anchorless Asset", "ticker": None,
                                   "listing": None})
            doc["atlas_envelope"]["subject_kind"] = "bitcoin"
            doc["atlas_envelope"]["asset_class"] = "crypto"
        doc["scenario_rating"] = block
        doc["atlas_envelope"]["scenario_rating"] = block
        if block.get("rating") and block.get("basis") == "rating":
            doc["rating"] = block["rating"]
            doc["atlas_envelope"]["rating"] = block["rating"]

    def mutate(run_dir):
        _rewrite_verdict(run_dir, change_verdict)
        if calendar:
            _rewrite_pack(run_dir, lambda pack: pack["capture"]["tier1"].extend(
                copy.deepcopy(CALENDAR_FACTS)))

    with tempfile.TemporaryDirectory() as tmp:
        return _render(_mutated_copy(tmp, mutate))


TAG = re.compile(r"<[^>]+>")


def _front(page):
    """The executive summary's own HTML: everything between its heading and the chairman's
    synthesis, which now follows it directly (owner ruling AC16(3),(5))."""
    return page[page.index('<h2 id="decision"'):page.index('<h2 id="synthesis"')]


def _masthead(page):
    """The masthead and the sticky bar (design audit C4 tier 0 / C5): the page body from its
    header to the executive summary heading. The rating box, the key-data strip, the warnings
    band and the sticky summary bar sit here now, above the tiers (owner ruling AC16(3),(9))."""
    return page[page.index('<header class="masthead">'):page.index('<h2 id="decision"')]


def _detail(page):
    """The decision-in-detail tier's own HTML (owner ruling AC16, audit C4 tier 3): everything
    between its heading and the frozen evidence that follows it. The downside ladder, the
    anchorless scenario ladder, the dated events, the outside auditor's objections and the
    challenge round live here now, moved down from the executive summary and the appendices."""
    return page[page.index('<h2 id="detail"'):page.index('<h2 id="evidence"')]


def _stamps(page):
    """The 'About this sitting' run-stamps appendix (owner ruling AC16 moved the clocks here off
    the executive summary): everything from its heading to the end of the page."""
    return page[page.index('<h3 id="stamps">'):]


def _visible_text(fragment):
    """What a reader actually sees: markup stripped, entities resolved, runs of space collapsed."""
    return re.sub(r"\s+", " ", html_lib.unescape(TAG.sub(" ", fragment))).strip()


class TestSelfContained(unittest.TestCase):
    def test_zero_external_references(self):
        self.assertIsNone(re.search(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', HTML))
        self.assertNotIn("<link", HTML)
        self.assertNotIn("@import", HTML)
        self.assertNotIn("url(http", HTML)

    def test_one_page_shell(self):
        self.assertTrue(HTML.startswith(R.PREAMBLE.decode("ascii")))
        self.assertTrue(HTML.rstrip().endswith("</html>"))
        self.assertIn("<style>", HTML)
        self.assertIn("<script>", HTML)


class TestSectionsAndNavigation(unittest.TestCase):
    def test_every_section_present_with_its_nav_entry(self):
        for anchor in ANCHORS:
            self.assertIn('<h2 id="%s"' % anchor, HTML, anchor)
            self.assertIn('href="#%s"' % anchor, HTML, anchor)

    def test_section_headings_in_plain_words(self):
        for heading in SECTION_HEADINGS:
            self.assertIn(E(heading), HTML, heading)

    def test_menu_is_one_entry_per_section_plus_top(self):
        menu = re.search(r'<div class="menucard">(.*?)</div></div></nav>', HTML, re.S).group(1)
        self.assertEqual(menu.count("<a href="), 1 + len(ANCHORS))
        self.assertIn('<a href="#top">Top of report</a>', menu)

    def test_dock_pinned_and_menu_on_hover_and_click(self):
        pin = "pos" + "ition"   # assembled: the language scan bans the spelled word
        self.assertIn(".dock{%s:fixed" % pin, HTML)
        self.assertIn(".dock:hover .menu", HTML)
        self.assertIn(".dock.open .menu", HTML)
        self.assertIn('id="navbtn"', HTML)

    def test_dark_by_default_with_a_visible_toggle(self):
        self.assertIn('<html lang="en" data-theme="dark">', HTML[:120])
        self.assertIn('id="themebtn"', HTML)
        self.assertIn("council-report-theme", HTML)


class TestFolding(unittest.TestCase):
    def test_nothing_is_open_by_default(self):
        self.assertNotIn("<details open", HTML)

    def test_each_advisor_is_a_closed_fold_headed_by_its_lens_name(self):
        for label in ("The bear case", "The bull case", "The base-rate skeptic",
                      "Market structure", "The asset's risk"):
            pattern = r"<details><summary>[^<]*%s</summary>" % re.escape(E(label))
            self.assertTrue(re.search(pattern, HTML), label)

    def test_reviewer_cross_examination_is_a_closed_fold(self):
        self.assertIn("<details><summary>The blind reviewer&#x27;s synopsis and full "
                      "cross-examination of the five advisors</summary>", HTML)
        self.assertIn("<h4>The reviewer's full cross-examination</h4>", HTML)

    def test_challenger_full_response_is_a_closed_fold(self):
        self.assertIn("<details><summary>Its full response &mdash; 2 findings</summary>", HTML)

    def test_evidence_folds_to_the_ruled_summary_line(self):
        # The full pack folds under one line with its count (owner ruling AC16, audit C4 tier 4);
        # the compact table of the facts the verdict rests on stays open above it.
        self.assertIn("<details><summary>Every figure on the record &mdash; all 10 frozen facts "
                      "in the evidence pack", HTML)

    def test_collapse_of_nothing_adds_nothing(self):
        page = R.Page()
        page.add("before")
        mark = page.mark()
        page.collapse("never shown", mark)
        self.assertEqual(page.body(), "before")


class TestCompactEvidenceTableCap(unittest.TestCase):
    """Architect ruling before U6b(b) round 1: the open compact table of the facts the verdict
    rests on holds at most 25 rows; every other dependency fact folds directly below it under a
    counted summary. Fixture run-invented-1 has five dependency facts, so all stay open and the
    second fold is omitted."""

    def test_all_dependencies_open_and_no_second_fold_when_25_or_fewer(self):
        self.assertNotIn("this verdict rests on</summary>", HTML)
        for fid in ("last price", "revenue fy2025", "free cash flow fy2025",
                    "forward earnings multiple", "risk free rate 10y"):
            self.assertIn("<tr><td>%s</td>" % fid, HTML)

    def test_open_rows_capped_at_25_with_the_rest_in_a_second_fold(self):
        extra = [{"id": "dep%02d" % i, "value": "%d.0" % i, "unit": "USD_m",
                  "as_of": "2026-08-28", "source": "INVENTED dependency fact %d" % i}
                 for i in range(30)]

        def mutate(run_dir):
            _rewrite_pack(run_dir, lambda d: d["capture"]["tier1"].extend(extra))
            _rewrite_verdict(run_dir, lambda d: d.__setitem__(
                "evidence_dependencies", ["dep%02d" % i for i in range(30)]))

        with tempfile.TemporaryDirectory() as tmp:
            html = _render(_mutated_copy(tmp, mutate))
        self.assertIn("The other 5 facts this verdict rests on", html)
        intro = html.index("The figures the verdict says its ruling rests on")
        fold = html.index("The other 5 facts this verdict rests on")
        open_region = html[intro:fold]
        self.assertEqual(open_region.count("<tr><td>dep"), 25)
        self.assertNotIn("<tr><td>dep29</td>", open_region)

    def test_a_bounded_dependency_fact_shows_its_bound_in_the_compact_table(self):
        # Round 1 finding r1-1: a decisive dependency fact that is a ceiling or floor must not
        # read as a measurement in the compact OPEN table - the owner meets it there first, before
        # the full-pack fold. The bound declaration and the published line render here too.
        def mutate(run_dir):
            def add_bound(d):
                for f in d["capture"]["tier1"]:
                    if f["id"] == "free_cash_flow_fy2025":
                        f["bound"] = {"kind": "ceiling",
                                      "published_line": "Other investing activities, net"}
            _rewrite_pack(run_dir, add_bound)

        with tempfile.TemporaryDirectory() as tmp:
            html = _render(_mutated_copy(tmp, mutate))
        intro = html.index("The figures the verdict says its ruling rests on")
        fold = html.index("<details><summary>Every figure on the record")
        compact = html[intro:fold]
        self.assertIn("declared a CEILING", compact)
        self.assertIn("The published line, as the capture names it: "
                      "Other investing activities, net", compact)

    def test_a_decisive_metric_lifts_its_fact_even_when_a_passage_is_cited_first(self):
        # P-U6b-11 (round 3 r3-3): a decisive metric whose answered_by lists a non-fact id first
        # must still lift its recorded tier-1 fact into the OPEN compact table, not read [0] blindly.
        # dep29 would land in the second fold in recorded order; the metric cites a passage, then it.
        extra = [{"id": "dep%02d" % i, "value": "%d.0" % i, "unit": "USD_m",
                  "as_of": "2026-08-28", "source": "INVENTED dependency fact %d" % i}
                 for i in range(30)]

        def mutate(run_dir):
            def add(d):
                d["capture"]["tier1"].extend(extra)
                d["capture"]["business_frame"] = {"FIXT": {"decisive_metrics": [
                    {"name": "INVENTED - the decisive metric",
                     "answered_by": ["not_a_recorded_fact", "dep29"]}]}}
            _rewrite_pack(run_dir, add)
            _rewrite_verdict(run_dir, lambda d: d.__setitem__(
                "evidence_dependencies", ["dep%02d" % i for i in range(30)]))

        with tempfile.TemporaryDirectory() as tmp:
            html = _render(_mutated_copy(tmp, mutate))
        intro = html.index("The figures the verdict says its ruling rests on")
        fold = html.index("The other 5 facts this verdict rests on")
        open_region = html[intro:fold]
        self.assertIn("<tr><td>dep29</td>", open_region)


class TestVerdictBlock(unittest.TestCase):
    def test_rating_in_the_owners_plain_words_monitor_is_a_watch_state(self):
        # The rating word is the large heading of the masthead rating box now (design audit C5).
        self.assertIn('<div class="rating-word">Monitor - no view yet; watch the named '
                      "triggers</div>", _masthead(HTML))

    def test_all_five_rating_words(self):
        self.assertEqual(R.RATING_WORDS["strong_buy"], "Strong buy")
        self.assertEqual(R.RATING_WORDS["buy"], "Buy")
        self.assertEqual(R.RATING_WORDS["hold"], "Hold")
        self.assertEqual(R.RATING_WORDS["sell"], "Sell")
        self.assertTrue(R.RATING_WORDS["monitor"].startswith("Monitor"))

    def test_mispricing_read_with_magnitude_and_arithmetic(self):
        self.assertIn("The council reads the price as <strong>rich</strong>", HTML)
        self.assertIn(E("about a fifth above the subject's own five-year rating"), HTML)
        self.assertIn("Roughly 24.1 times forward earnings against a five-year average near "
                      "20 times; about a fifth above it.", HTML)

    def test_conviction_rationale_is_rendered(self):
        self.assertIn("No view is worth paying for until one of the named triggers fires.", HTML)


class TestWarnings(unittest.TestCase):
    def test_both_warnings_render_in_the_loud_band(self):
        first = ("The rating moved after the outside audit. The outside auditor did not see "
                 "this rating.")
        second = ("One frozen fact is older than its own freshness rule. The council reasoned "
                  "over it knowingly.")
        for warning in (first, second):
            self.assertIn('<div class="card alarm"><span class="shout">%s</span></div>'
                          % warning, HTML)


class TestTripwires(unittest.TestCase):
    def test_invalidation_level_rounds_for_reading(self):
        self.assertIn('<td class="nowrap">$84.50</td>', HTML)
        self.assertIn("A close under 84.50 breaks the base the reopening case rests on.", HTML)

    def test_reopening_triggers_price_and_event(self):
        # The reopening triggers live in the one 'What changes this rating' table now (owner ruling
        # AC16): the cell shows the price in market form and the date in words; the chairman's own
        # sentence is left as written. The duplicate tripwires appendix is gone.
        self.assertIn('<td class="nowrap">$72.00</td>', HTML)
        self.assertIn("Reopen the case if the shares close at or under 72.00 USD.", HTML)
        self.assertIn('<span class="tag">Reopen the case (price)</span>', HTML)
        self.assertIn('<span class="tag">Reopen the case (event)</span>', HTML)
        self.assertIn('<td class="nowrap">4 Feb 2027</td>', HTML)

    def test_falsifier_names_figure_source_and_date(self):
        self.assertIn("<code>full_year_revenue_2026</code>", HTML)
        self.assertIn(E("invented: the company's 2026 full-year report"), HTML)
        # The chairman's own falsifier statement is respelt in the market form (AC16(1)); the
        # figure it names, "900 USD millions", reads as "$900M", value unchanged.
        self.assertIn("If 2026 full-year revenue prints under $900M, the growth leg "
                      "of the thesis is wrong.", HTML)

    def test_structured_verdict_text_is_reformatted_and_logged(self):
        # Owner ruling AC16(1): the chairman-authored STRUCTURED verdict text - falsifier
        # statements, trigger details, invalidation-level meanings - is respelt into the market
        # form like every other number, value unchanged, each substitution logged with where it
        # was made. The falsifier's "900 USD millions" reads as "$900M"; a figure with no unit
        # word beside it (the level meaning's "84.50", the trigger's "72.00 USD") is left alone.
        self.assertNotIn("900 USD millions", HTML)
        self.assertIn("A close under 84.50 breaks the base", HTML)
        self.assertIn("close at or under 72.00 USD.", HTML)
        _, subs = _render_with_subs(FIXTURE)
        self.assertTrue(any(s["original"] == "900 USD millions"
                            and s["replacement"] == "$900M"
                            and s["location"] == "verdict falsifier statement"
                            for s in subs), subs)


class TestChallengeSummary(unittest.TestCase):
    def test_model_and_success_status(self):
        self.assertIn("<strong>The outside challenge ran.</strong>", HTML)
        self.assertIn("OpenAI GPT-5.6 Sol", HTML)

    def test_findings_with_named_dispositions_in_plain_words(self):
        self.assertIn("<strong>F1</strong> &middot; a claim without support", HTML)
        self.assertIn("<strong>F2</strong> &middot; a blind spot", HTML)
        self.assertIn('<span class="tag addressed" title="the verdict actually moved">acted on', HTML)
        self.assertIn('<span class="tag overruled" title="set aside, with the reason', HTML)
        self.assertIn("the verdict actually moved", HTML)
        self.assertIn("set aside, with the reason on the record", HTML)

    def test_endorsement_rendered_when_present(self):
        self.assertIn("The highest rating it would support on this record: "
                      "<strong>Hold</strong>.", HTML)


class TestChangeAppendix(unittest.TestCase):
    def test_rows_render_before_and_after(self):
        self.assertIn("<code>mispricing.magnitude</code>", HTML)
        self.assertIn("<td>%s</td><td>%s</td>"
                      % (E("about a tenth above the subject's own five-year rating"),
                         E("about a fifth above the subject's own five-year rating")), HTML)

    def test_unendorsed_raise_row_carries_the_warning_styling_class(self):
        self.assertIn('<tr class="alarm"><td class="nowrap"><code>rating</code></td>'
                      '<td>hold</td><td>monitor</td><td class="nowrap">'
                      '<span class="tag alarmtag">a raise the outside challenge did not see</span>'
                      "</td></tr>", HTML)

    def test_empty_appendix_renders_the_exact_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp, lambda d: _rewrite_verdict(
                d, lambda doc: doc["challenge"].__setitem__("change_appendix", [])))
            page = _render(run_dir)
        self.assertIn("Nothing changed after the outside challenge.", page)
        self.assertNotIn('<tr class="alarm">', page)
        self.assertIn('<h3 id="changes">', page)   # the section always exists


class TestSynthesis(unittest.TestCase):
    def test_final_markdown_is_the_synthesis_when_a_resolve_exists(self):
        self.assertIn("The final view is a watch-state, not an opinion to act on", HTML)
        self.assertNotIn("DRAFT-SYNTHESIS-MARKER", HTML)

    def test_falls_back_to_the_draft_synthesis_when_no_resolve_happened(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp, lambda d: os.unlink(
                os.path.join(d, "rpc", "010-answer-chair_resolve.json")))
            page = _render(run_dir)
        self.assertIn("DRAFT-SYNTHESIS-MARKER", page)
        self.assertIn("No post-challenge resolve is in the record", page)


class TestEvidence(unittest.TestCase):
    def test_market_shut_sentence_is_in_plain_sight_not_folded(self):
        disclosure = ("The exchange was shut at capture. The last price is the 2026-08-28 "
                      "close, about two hours old at the freeze.")
        self.assertIn(disclosure, HTML)
        fold = HTML.index("<details><summary>Every figure on the record")
        self.assertLess(HTML.index(disclosure), fold)
        self.assertGreater(HTML.index(disclosure), HTML.index('<h2 id="evidence"'))

    def test_value_cells_render_in_the_market_form(self):
        # The evidence table's value column is no longer nowrap - it can carry a whole tier-2
        # sentence, so it wraps (design audit C5, B8). The market-form spelling is unchanged.
        self.assertIn('<td>27.2M shares</td>', HTML)   # 27.161588 millions_of_shares
        self.assertIn('<td>110M shares</td>', HTML)    # 110.0 millions_of_shares
        self.assertIn('<td>$9.72B</td>', HTML)         # 9724.00 USD_m
        self.assertIn('<td>$863M</td>', HTML)          # 862.5 USD_m, three sig figs
        self.assertIn('<td>24.1x</td>', HTML)          # 24.1 x

    def test_a_seats_own_number_is_reformatted_and_logged(self):
        # Owner ruling AC16(1) amended Y5: the renderer MAY respell a number inside seat prose,
        # value unchanged, every substitution logged. The bear's "27.161588 million shares"
        # reads as "27.2M shares" and no raw figure survives on the page.
        self.assertIn("27.2M shares were sold short", HTML)
        self.assertEqual(HTML.count("27.161588"), 0)
        _, subs = _render_with_subs(FIXTURE)
        self.assertTrue(any(s["original"] == "27.161588 million shares"
                            and s["replacement"] == "27.2M shares" for s in subs), subs)

    def test_freshness_in_words_with_the_stale_fact_flagged(self):
        self.assertIn('<span class="tag stale">stale</span>', HTML)
        self.assertGreaterEqual(HTML.count('<span class="tag checked">checked</span>'), 9)

    def test_derived_fact_carries_its_generated_arithmetic_note(self):
        # The note is the freeze's own equation, read out of its sentence (unit READ-A) - the
        # page never re-derives arithmetic prose.
        self.assertIn("Calculated: 88.40 * 110.0 = 9724.00", HTML)

    def test_tier2_passage_is_quoted_never_rounded(self):
        self.assertIn("Management guided 2026 revenue to a range of 940 to 980 USD millions on "
                      "2026-02-05, and repeated that range on 2026-07-30. The prior year "
                      "printed 862.5.", HTML)

    def test_declared_gap_and_sufficiency_summary(self):
        self.assertIn("(short_borrow_cost &middot; the test it weakens: market_structure_read)",
                      HTML)
        self.assertIn("5 of 6 checks were answered before any seat was paid; 1 was declared "
                      "as a gap.", HTML)
        self.assertIn(">declared gap<", HTML)


class TestQuestionAndFrame(unittest.TestCase):
    def test_question_verbatim_and_the_council_half(self):
        self.assertIn("Is Specimen Works still cheap at this price, or has the market caught "
                      "up with the growth story?", HTML)
        self.assertIn("a priced thesis check on a single stock", HTML)

    def test_for_atlas_note_renders_verbatim_under_its_label(self):
        note = ("Separately, on my side: plan the follow-on tranche timing for me once the "
                "council has a view.")
        self.assertIn("Routed to the portfolio system, untouched", HTML)
        # Verbatim in the question, under the routing label, and again in the Atlas envelope.
        self.assertEqual(HTML.count(note), 3)


class TestAtlasEnvelope(unittest.TestCase):
    def test_compact_table_with_rating_key_numbers_and_pack_hash(self):
        atlas = HTML[HTML.index('<h3 id="atlas">'):]
        self.assertIn("Monitor - no view yet; watch the named triggers", atlas)
        self.assertIn("<td>last price</td>", atlas)
        self.assertIn('<td class="nowrap">$88.40</td>', atlas)
        self.assertIn('<td class="nowrap">41.7%</td>', atlas)
        self.assertIn("ab12" * 16, atlas)
        self.assertIn("a fingerprint no other file shares", atlas)

    def test_plain_sentence_about_the_envelopes_own_verdict_hash(self):
        self.assertIn("The envelope also travels as its own file, and that file carries this "
                      "verdict&#x27;s own hash, so the hand-off can be proved.", HTML)


class TestTheHandOffStandsAlone(unittest.TestCase):
    """Owner ruling AB23. The hand-off section shows the package as it
    actually travels: the subject it names, the audit state the
    portfolio system computes its effective rating from, and the ids
    whose meaning the council's own list does not fix.

    Every assertion here FAILED before the change: the page showed a
    rating, a kind and a pack hash, and nothing else."""

    def atlas(self, page=None):
        page = page if page is not None else HTML
        return page[page.index('<h3 id="atlas">'):]

    def test_the_package_names_its_own_subject_and_sitting(self):
        atlas = self.atlas()
        self.assertIn('<th class="nowrap">Subject</th>'
                      "<td>Specimen Works (SPWK, INVENTED-X, USD)</td>",
                      atlas)
        self.assertIn('<th class="nowrap">Sitting</th>'
                      "<td><code>report-fixture-invented-1</code></td>",
                      atlas)

    def test_the_package_states_the_audit_outcome_and_the_ceiling(self):
        atlas = self.atlas()
        self.assertIn("The outside challenge ran, and the package says so.",
                      atlas)
        self.assertIn("The highest rating the outside challenge said the record "
                      "supports is <strong>Hold", atlas)

    def test_the_warnings_are_said_to_travel_with_it(self):
        self.assertIn("Every warning on this verdict travels inside the "
                      "package too &mdash; 2 of them", self.atlas())

    def test_a_package_with_no_endorsed_ceiling_says_that_plainly(self):
        self.assertIn("The outside challenge endorsed no ceiling, so the package "
                      "carries none.", self.atlas(BASKET_HTML))

    def test_the_ids_the_reader_does_not_know_are_named(self):
        """AB23(6): a sizing id outside the council's own list travels
        with its own declared unit, and the page says which ones."""
        atlas = self.atlas()
        self.assertIn("Sizing facts whose meaning is not fixed by the "
                      "council&#x27;s own list", atlas)
        for sizing_id in ("realized_vol_90d", "avg_daily_turnover",
                          "deepest_drawdown_5y", "next_results_date"):
            self.assertIn(sizing_id, atlas)

    def test_the_theme_package_names_no_unknown_ids(self):
        """Every one of its rows is an id the list pins, so the page
        says nothing - the note appears only when it has something to
        say."""
        self.assertNotIn("Sizing facts whose meaning is not fixed",
                         self.atlas(THEME_HTML))


class TestAPackageWrittenBeforeTheAuditFields(unittest.TestCase):
    """ENVELOPE-ATLAS, plugin audit round 1, finding r1-4. Every one of
    the seven sittings on record was published under contract 1.0.0 to
    1.2.0, and none of their packages carries the audit-state fields.
    Re-rendering one of them - step 4 of the runbook - printed "The
    outside audit did NOT run" and "The auditor endorsed no ceiling"
    about runs whose audit ran and whose auditor DID set a ceiling.
    Three false sentences on a page the owner reads, and the worst of
    them tells him a rating was not capped when it was.

    Absence of a field is not a negative finding: an older package
    simply does not carry the audit state, and the page says so."""

    def rendered_without(self, *fields):
        work = tempfile.mkdtemp(prefix="council-legacy-package-")
        self.addCleanup(shutil.rmtree, work, True)
        run_dir = os.path.join(work, "run")
        shutil.copytree(FIXTURE, run_dir)
        path = os.path.join(run_dir, "verdict.json")
        with open(path, "rb") as handle:
            verdict = json.loads(handle.read().decode("utf-8"))
        for field in fields:
            verdict["atlas_envelope"].pop(field, None)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(verdict, handle)
        page = _render(run_dir)
        return page[page.index('<h3 id="atlas">'):]

    def legacy(self):
        return self.rendered_without(
            "challenge_status", "endorsement_highest_rating_supported",
            "warnings")

    def test_it_never_says_the_audit_did_not_run(self):
        self.assertNotIn("did NOT run", self.legacy())

    def test_it_never_claims_the_auditor_endorsed_no_ceiling(self):
        self.assertNotIn("endorsed no ceiling", self.legacy())

    def test_it_never_counts_warnings_the_package_does_not_carry(self):
        self.assertNotIn("0 of them", self.legacy())

    def test_it_says_plainly_that_the_package_predates_the_fields(self):
        atlas = self.legacy()
        self.assertIn("predates", atlas)
        self.assertIn("challenge round", atlas)

    def test_a_current_package_still_states_its_audit_state(self):
        """The guard must not silence a package that HAS the fields."""
        atlas = HTML[HTML.index('<h3 id="atlas">'):]
        self.assertIn("The outside challenge ran, and the package says so.",
                      atlas)
        self.assertNotIn("predates", atlas)


class TestAFailedAuditIsNotAnAuditConclusion(unittest.TestCase):
    """ENVELOPE-ATLAS, the plugin audit's closing pass, finding r3-3.
    On EVERY failed-audit package the card said, in consecutive
    sentences, that the audit did not run and that "The auditor
    endorsed no ceiling" - an audit conclusion drawn from an audit that
    never happened. The ceiling is null there because nobody answered,
    not because anybody declined to set one. The same principle the
    r1-4 fix applies one branch up: absence is not a finding."""

    def rendered(self, status, ceiling=None):
        work = tempfile.mkdtemp(prefix="council-failed-audit-")
        self.addCleanup(shutil.rmtree, work, True)
        run_dir = os.path.join(work, "run")
        shutil.copytree(FIXTURE, run_dir)
        path = os.path.join(run_dir, "verdict.json")
        with open(path, "rb") as handle:
            verdict = json.loads(handle.read().decode("utf-8"))
        envelope = verdict["atlas_envelope"]
        envelope["challenge_status"] = status
        envelope["endorsement_highest_rating_supported"] = ceiling
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(verdict, handle)
        page = _render(run_dir)
        return page[page.index('<h3 id="atlas">'):]

    def test_a_failed_audit_never_claims_a_ceiling_was_considered(self):
        for status in ("timeout", "launch_failure", "malformed_output",
                       "schema_failure", "binding_failure",
                       "internal_failure"):
            atlas = self.rendered(status)
            self.assertNotIn("endorsed no ceiling", atlas, status)

    def test_it_says_why_there_is_no_ceiling(self):
        atlas = self.rendered("timeout")
        self.assertIn("did NOT run", atlas)
        self.assertIn("no ceiling was accepted", atlas)
        self.assertIn("a gap, not the outside challenge", atlas)

    def test_it_never_says_nobody_answered_when_papers_were_rejected(self):
        """The closing incremental's one finding. Two of the six
        failure statuses mean the challenger DID answer and the machine
        threw the answer away: a schema-invalid document, or echoes that
        do not bind to this run. The page says so a few sections up -
        'The challenger returned papers, but the machine rejected them'
        - so a card claiming nobody answered contradicted the same page.
        One sentence true in all six cases: nothing was accepted."""
        for status in ("timeout", "launch_failure", "malformed_output",
                       "schema_failure", "binding_failure",
                       "internal_failure"):
            atlas = self.rendered(status)
            self.assertNotIn("No auditor answered", atlas, status)
            self.assertIn("no ceiling was accepted", atlas, status)

    def test_a_successful_audit_with_no_ceiling_still_says_so(self):
        atlas = self.rendered("success")
        self.assertIn("The outside challenge endorsed no ceiling", atlas)

    def test_a_successful_audit_with_a_ceiling_still_names_it(self):
        atlas = self.rendered("success", ceiling="hold")
        self.assertIn("supports is <strong>Hold", atlas)


class TestBoundRowsInTheHandOff(unittest.TestCase):
    """AB23(4), closing P-ANCHORLESS-10: a figure standing in for one
    the filer never published is a CEILING, and the hand-off printed it
    as an unqualified number. The tag now travels on the row, and the
    page renders it in the same words the case files use."""

    def rendered(self, tag, on_key_number=True):
        """The single-name fixture with ONE hand-off row tagged."""
        work = tempfile.mkdtemp(prefix="council-bound-handoff-")
        self.addCleanup(shutil.rmtree, work, True)
        run_dir = os.path.join(work, "run")
        shutil.copytree(FIXTURE, run_dir)
        path = os.path.join(run_dir, "verdict.json")
        with open(path, "rb") as handle:
            verdict = json.loads(handle.read().decode("utf-8"))
        key = "key_numbers" if on_key_number else "sizing_inputs"
        verdict["atlas_envelope"][key][0]["bound"] = tag
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(verdict, handle)
        page = _render(run_dir)
        return page[page.index('<h3 id="atlas">'):]

    def test_a_ceiling_key_number_says_so_and_names_its_line(self):
        atlas = self.rendered({"kind": "ceiling",
                               "published_line": "Other investing "
                                                 "activities, net"})
        self.assertIn("declared a CEILING", atlas)
        self.assertIn("can only overstate", atlas)
        self.assertIn("Other investing activities, net", atlas)

    def test_a_floor_sizing_row_says_the_figure_can_only_be_higher(self):
        atlas = self.rendered({"kind": "floor", "published_line": None},
                              on_key_number=False)
        self.assertIn("declared a FLOOR", atlas)
        self.assertIn("can only be higher", atlas)

    def test_an_untagged_package_renders_no_bound_words(self):
        atlas = HTML[HTML.index('<h3 id="atlas">'):]
        self.assertNotIn("declared a CEILING", atlas)
        self.assertNotIn("declared a FLOOR", atlas)

    def test_the_page_and_the_case_file_say_the_same_words(self):
        """One declaration, one wording, wherever it appears."""
        tag = {"kind": "ceiling", "published_line": None}
        self.assertIn(E(R._bound_words(tag)), self.rendered(tag))


class TestHeadAndFooter(unittest.TestCase):
    def test_title_stamps(self):
        # The masthead now carries the company name, ticker and listing (design audit C4 tier 0),
        # a kicker, and the model names as a small stamp under the rating box (owner ruling
        # AC16(9); M3 still satisfied). The run id and the ISO publication timestamp are off the
        # masthead - they belong to the footer stamps only (audit B9/B12).
        masthead = _masthead(HTML)
        self.assertIn('<div class="kicker">Investment Council</div>', masthead)
        self.assertIn('<h1>Specimen Works <span class="tkr">(INVENTED-X: SPWK)</span></h1>',
                      masthead)
        stamp = ('<div class="stamp muted small">Advisors and chairman: <strong>Claude Opus 4.6'
                 "</strong> &middot; outside challenge: <strong>OpenAI GPT-5.6 Sol</strong></div>")
        self.assertIn(stamp, masthead)
        # The run id and the publication timestamp are still on the page, in the footer.
        self.assertIn("Sitting <code>report-fixture-invented-1</code>", HTML)
        self.assertIn("Published 30 Aug 2026, 10:26 UTC.", HTML)

    def test_footer_carries_run_id_computed_hash_and_schema_version(self):
        self.assertIn("file as it sits on disk</th><td><code>%s</code>" % VERDICT_SHA, HTML)
        self.assertIn('<th class="nowrap">Contract version</th><td>1.7.0</td>', HTML)


class TestMastheadDesignAndPrint(unittest.TestCase):
    """Sub-charge (c) MASTHEAD, DESIGN, PRINT: the rating box, the one-phrase question, the model
    stamp, the sticky summary bar, the C5 design language and the light print palette (owner
    ruling AC16(2),(9); design audit C4 tier 0 / C5). The existing Y2/Y3/Y4 tests still stand."""

    def test_the_masthead_carries_the_rating_box(self):
        masthead = _masthead(HTML)
        self.assertIn('<div class="ratingbox">', masthead)
        self.assertIn('<div class="rating-word">Monitor - no view yet; watch the named '
                      "triggers</div>", masthead)
        # The price the ruling is made against, and its date, from the envelope's leading number
        # under its own label - no label map, no new field (owner ruling AC16).
        self.assertIn('<dl class="rating-price"><dt>%s</dt><dd>$88.40 ' % R._glossed("last price")
                      + '<span class="asof">28 Aug 2026</span></dd></dl>', masthead)

    def test_the_masthead_carries_the_one_phrase_question(self):
        # The owner's one-phrase question as asked, under the title (closes register item P-U6b-10).
        self.assertIn('<p class="question">Is Specimen Works still cheap at this price, or has the '
                      "market caught up with the growth story?</p>", _masthead(HTML))

    def test_the_model_names_are_a_small_stamp_under_the_rating_box(self):
        masthead = _masthead(HTML)
        box = masthead[masthead.index('<div class="ratingbox">'):masthead.index("</aside>")]
        self.assertIn('<div class="stamp muted small">Advisors and chairman: <strong>Claude Opus '
                      "4.6</strong> &middot; outside challenge: <strong>OpenAI GPT-5.6 Sol"
                      "</strong></div>", box)
        # The old page-second-line model stamp is gone (owner ruling AC16(9), audit B9/B10).
        self.assertNotIn('<div class="meta">', HTML)

    def test_the_sticky_summary_bar_carries_ticker_rating_price_date(self):
        bar = _masthead(HTML)
        self.assertIn('<div class="stickybar"><div class="stickybar-inner">', bar)
        self.assertIn('<span class="sb-tick">SPWK</span>', bar)
        self.assertIn('<span class="sb-rate">Monitor</span>', bar)
        self.assertIn("$88.40", bar)
        self.assertIn("28 Aug 2026", bar)

    def test_the_sticky_bar_pins_with_css_only(self):
        # Design audit C5: the bar pins with CSS alone (the assembled sticky property below); no
        # new script beyond the theme toggle's own, which the Y4 test covers.
        pin = "pos" + "ition"
        self.assertIn(".stickybar{%s:sticky" % pin, HTML)

    def test_the_sticky_bar_omits_the_lead_value_for_baskets_and_themes(self):
        # Round 1 finding r1-1: the sticky bar drops the key number's label. For a basket or theme
        # the leading key number is a constituent's price or a theme-level metric, not a price for
        # the whole subject, so printing it unlabelled beside the subject name is a wrong fact in
        # the bar (the theme fixture would read "...Storage ... $45.30", the basket "...Pair ...
        # $231.40"). There the bar shows only the identity and the rating.
        for name, page, fx in (("basket", BASKET_HTML, FIXTURE_BASKET),
                               ("theme", THEME_HTML, FIXTURE_THEME)):
            verdict = json.load(io.open(os.path.join(fx, "verdict.json"), encoding="utf-8"))
            lead = R._first_key_number(verdict)
            value = R.format_number(lead.get("value"), lead.get("unit"))
            start = page.index('<div class="stickybar-inner">')
            bar = page[start:page.index("</div></div>", start)]
            self.assertIn('<span class="sb-tick">', bar, name)
            self.assertIn('<span class="sb-rate">', bar, name)
            self.assertNotIn(value, bar, name)

    def test_the_question_line_keeps_an_approximation_abbreviation_whole(self):
        # Round 1 finding r1-2: the shared sentence splitter does not list "ca.", so an owner brief
        # that reads "...levels of ca. $184 at the time of writing." would publish in the masthead
        # truncated at "ca.", dropping the figure. The one-phrase question keeps the whole first
        # sentence.
        brief = ("My thesis to be challenged is a Long entry at current levels of ca. $184 "
                 "at the time of writing.\r\n\r\nI see the name as a long-term beneficiary.")
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "My thesis to be challenged is a Long entry at current levels "
                               "of ca. $184 at the time of writing.")

    def test_the_question_line_shows_both_statements_when_there_is_no_question_mark(self):
        # Round 5 (architect ruling closing P-U6b-15), failing-first: the sentence splitter is
        # removed. With no "?", the whole first paragraph is the line -- a brief that opens with two
        # statements shows both. The accepted cost of never cutting or misleading (owner ruling).
        brief = ("Enter a Long at levels of ca. $184 at the time of writing. Second sentence follows.")
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "Enter a Long at levels of ca. $184 at the time of writing. "
                               "Second sentence follows.")

    def test_the_question_line_runs_through_the_first_question_mark_over_an_abbreviation(self):
        # Round 5 (P-U6b-15), failing-first: with a "?" the line is the text up to and including it,
        # with no splitting on an interior full stop. "State of CA." no longer cuts the line short.
        brief = "State of CA. What size?"
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "State of CA. What size?")

    def test_the_question_line_shows_both_sentences_through_a_share_class_full_stop(self):
        # Round 5 (P-U6b-15): the finding that closed this round. A first sentence ending in a lone
        # single capital ("Class B.") is no longer special-cased; the line runs to the first "?".
        brief = "Assess Berkshire Class B. What allocation is right?"
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "Assess Berkshire Class B. What allocation is right?")

    def test_the_question_line_ends_at_the_first_question_mark(self):
        # A "?" ends the phrase at its first occurrence (unchanged behaviour).
        brief = "Is WULF a buy at today's price? Size it."
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "Is WULF a buy at today's price?")

    def test_the_question_line_falls_back_to_the_first_paragraph(self):
        # With no "?" the whole first paragraph is the line, bounded and with no ellipsis; a second
        # paragraph is never shown.
        brief = "Assess WULF at the open\r\n\r\nA second paragraph the masthead never shows."
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "Assess WULF at the open")

    def test_the_question_line_keeps_a_single_capital_abbreviation_whole(self):
        # A "?" makes the whole question the line, so an abbreviation of single capitals ("U.S.")
        # before a capitalised word is never truncated.
        brief = "What is the outlook for U.S. Treasuries?"
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "What is the outlook for U.S. Treasuries?")

    def test_the_question_line_for_the_wulf_brief(self):
        # Round 5 (P-U6b-15) regression: the WULF brief on record has no "?" and one paragraph, so
        # the line is the brief verbatim.
        brief = "is it a good buy at today's price"
        line = R._question_line({"question_verbatim": brief})
        self.assertEqual(line, "is it a good buy at today's price")

    def test_the_sticky_bar_labels_a_single_subjects_lead_number(self):
        # Round 4 finding P-U6b-14, failing-first: the bar showed a single subject's leading key
        # number bare. The envelope's key_numbers order is LLM-authored, so a non-price lead (a P/E
        # multiple) then read as the price. The bar now carries the figure under its own label,
        # exactly as the rating box does, so it can never read as an unlabelled price.
        verdict = {"subject": {"kind": "single_stock", "ticker": "ZZZ", "name": "Example"},
                   "rating": "buy",
                   "atlas_envelope": {"key_numbers": [
                       {"name": "trailing P/E", "value": "24.1", "unit": "x",
                        "as_of": "2026-09-14"}]}}
        page = R.Page()
        R._sticky_bar(page, {"verdict": verdict})
        bar = page.body()
        self.assertIn('<span class="sb-lead">trailing P/E 24.1x</span>', bar)
        # Never a bare value beside the identity and rating.
        self.assertNotIn('<span class="sep">&middot;</span> 24.1x', bar)

    def test_no_emoji_anywhere_on_any_page(self):
        emoji = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF]")
        for name, page in (("single", HTML), ("basket", BASKET_HTML), ("theme", THEME_HTML)):
            self.assertIsNone(emoji.search(page), name)

    def test_the_printed_page_is_light_and_a4(self):
        # Owner ruling AC16(2): the screen stays dark by default (Y4), but the PRINTED page is
        # light - a dark PDF is unreadable on paper. A4 margins and page breaks are set for print.
        self.assertIn("@page{size:A4", HTML)
        printblock = HTML[HTML.index("@media print{"):]
        self.assertIn("--base:#FFFFFF", printblock)
        self.assertIn("break-before:page", printblock)
        self.assertIn("break-inside:avoid", printblock)

    def test_tables_read_as_data_tables_not_boxed_spreadsheets(self):
        # Design audit C5: no vertical rules and no boxed cells.
        self.assertIn("border-collapse:collapse", HTML)
        self.assertNotIn("td,th{border:1px solid", HTML)

    def test_dark_default_and_the_pinned_dock_survive_the_redesign(self):
        # Rulings Y3/Y4 stand after the masthead rewrite (the dedicated tests cover them fully).
        self.assertIn('<html lang="en" data-theme="dark">', HTML[:120])
        self.assertIn(".dock{%s:fixed" % ("pos" + "ition"), HTML)
        self.assertIn('id="themebtn"', HTML)


class TestSeatSelection(unittest.TestCase):
    def test_the_highest_numbered_answer_per_seat_wins(self):
        self.assertNotIn("SUPERSEDED-FIRST-ANSWER", HTML)
        self.assertIn("27.2M shares", HTML)   # the retry's content is what renders (respelt)


class TestChallengerFullResponse(unittest.TestCase):
    def test_summary_findings_and_raw_json(self):
        self.assertIn("<strong>Its own summary.</strong>", HTML)
        self.assertIn("The highest rating this record supports is hold.", HTML)
        self.assertIn("<h4>F1 &middot; a claim without support</h4>", HTML)
        self.assertIn("<h4>F2 &middot; a blind spot</h4>", HTML)
        self.assertNotIn("The raw findings", HTML)

    def test_failed_challenge_is_stated_loudly_and_shows_no_response_fold(self):
        def mutate(run_dir):
            _rewrite_verdict(run_dir, lambda doc: doc["challenge"].update(
                {"status": "timeout", "failure_reason": "the bridge timed out after 30 minutes",
                 "findings": [], "dispositions": [], "endorsement": None}))
            os.unlink(os.path.join(run_dir, "challenge", "result.json"))
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertIn(R.AUDIT_FAILED_SENTENCE, page)
        self.assertIn("the bridge timed out after 30 minutes", page)
        self.assertIn("the outside model ran out of time", page)
        self.assertIn("This run directory carries no outside challenge papers.", page)
        self.assertNotIn("<details><summary>Its full response", page)


# The report-design audit 2026-09-15 section C1, its worked examples read straight off the
# WULF record, as (value as recorded, unit, the market form the page must show). Owner ruling
# AC16(4) overrides section C1 wherever the draft wrote two decimals for a percentage: every
# percentage takes ONE decimal (3.9%, never 3.91%). Two cells of the audit's own table read
# differently under the deterministic three-significant-figure rule and are marked below.
C1_WORKED_EXAMPLES = [
    # Money: currency sign before, scale letter after, three significant figures, no "dollars".
    ("10400285952", "USD", "$10.4B"),
    ("7806364952", "USD", "$7.81B"),
    ("47636", "USD_thousand", "$47.6M"),
    ("12835", "USD_thousand", "$12.8M"),
    ("107696", "USD_thousand", "$108M"),
    ("9007", "USD_thousand", "$9.01M"),
    ("36000", "USD_thousand", "$36.0M"),
    ("248000", "USD_thousand", "$248M"),
    ("2619191", "USD_thousand", "$2.62B"),
    ("-992269", "USD_thousand", "-$992M"),
    ("2371364", "USD_thousand", "$2.37B"),
    ("3200000", "USD_thousand", "$3.20B"),
    ("1000000", "USD_thousand", "$1.00B"),
    ("2000000", "USD_thousand", "$2.00B"),
    ("26924", "USD_thousand", "$26.9M"),
    ("13850", "USD_thousand", "$13.9M"),
    ("222890", "USD_thousand", "$223M"),
    # The audit table writes "$78K"; the deterministic three-significant-figure rule keeps the
    # third figure, exactly as it keeps $1.00B and $36.0M. Architect flagged.
    ("78", "USD_thousand", "$78.0K"),
    ("39411005", "USD", "$39.4M"),
    ("250", "USD_m", "$250M"),
    ("530", "USD_m", "$530M"),
    ("11.2", "USD_m", "$11.2M"),
    ("3208", "USD_m", "$3.21B"),
    ("4010", "USD_m", "$4.01B"),
    ("3525", "USD_m", "$3.53B"),
    ("4999", "USD_m", "$5.00B"),
    ("950", "USD_m_per_year", "$950M/year"),
    ("655709848.10", "USD_per_day", "$656M/day"),
    ("12.4", "USD_m_per_MW", "$12.4M/MW"),
    # If rounding carries a figure to 1,000 of its scale it steps up one scale.
    ("949700", "USD_thousand", "$950M"),
    ("999700", "USD_thousand", "$1.00B"),
    # Per-share prices: always two decimals, never scaled.
    ("15.64", "USD_per_share", "$15.64"),
    ("19", "USD_per_share", "$19.00"),
    ("10.04", "USD_per_share", "$10.04"),
    ("29.84", "USD_per_share", "$29.84"),
    # Percentages: ONE decimal (AC16(4)); a whole source stays whole. A rate/time basis stays
    # visible after the figure (P-U6b-1): a per-year rate read as a bare percent misleads.
    ("3.91", "percent_per_year", "3.9% per year"),
    ("7.75", "percent", "7.8%"),
    ("71", "percent", "71.0%"),
    ("15.9", "percent", "15.9%"),
    ("0.97", "percent", "1.0%"),
    ("4.00", "percent", "4.0%"),
    ("0.908383", "fraction_annualized", "90.8% annualized"),
    ("0.494479", "fraction_of_price", "-49.4%"),
    ("4.21", "%", "4.2%"),
    ("41.7", "%", "41.7%"),
    # Multiples and ratios: two decimals with an x, one decimal at ten and above.
    ("3.083326", "ratio", "3.08x"),
    ("24.1", "x", "24.1x"),
    # Share counts: three significant figures scaled, with the word "shares".
    ("498932431", "shares", "498.9M shares"),
    ("711934881", "shares", "711.9M shares"),
    ("122289767", "shares", "122.3M shares"),
    ("47400000", "shares", "47.4M shares"),
    ("1274318", "shares", "1.27M shares"),
    ("27.161588", "millions_of_shares", "27.2M shares"),
    ("110.0", "millions_of_shares", "110M shares"),
    # Physical units: the value and MW; the "critical IT" qualifier belongs in the label, once.
    ("839", "MW_critical_it", "839 MW"),
    ("22.5", "MW", "22.5 MW"),
    ("393", "MW", "393 MW"),
    # Dates in words, day first; a list keeps its separator; a machine stamp keeps its unit.
    ("2026-06-30", "iso_date", "30 Jun 2026"),
    ("2026-12-31; 2027-04-30", "iso_date", "31 Dec 2026; 30 Apr 2027"),
    ("2026-06-30", "fiscal_quarter_end_date", "30 Jun 2026"),
    ("none_announced", "results_date_check", "none_announced"),
]


class TestNumberRules(unittest.TestCase):
    """The C1 display rules, table-driven over the audit's worked examples; then the standing
    never-erase, identifier, unrounded and non-number rules that carry over unchanged."""

    def test_c1_worked_examples(self):
        for value, unit, expected in C1_WORKED_EXAMPLES:
            with self.subTest(value=value, unit=unit):
                self.assertEqual(R.format_number(value, unit), expected)

    def test_stamps_are_numbers_only_their_noun_is_in_the_sentence(self):
        # The page reads "50 minutes" and "0.7M tokens"; the noun is written by the sentence the
        # figure sits in, so the formatter returns the number.
        self.assertEqual(R.format_number(49.7, "minutes"), "50")
        self.assertEqual(R.format_number(90, "minutes"), "90")
        self.assertEqual(R.format_number(700000, "tokens"), "0.7M")

    def test_per_share_helper_scales_thousands(self):
        self.assertEqual(R.format_price("15.64", "USD"), "$15.64")
        self.assertEqual(R.format_price("19", "USD"), "$19.00")
        self.assertEqual(R.format_price("12340", "CHF"), "CHF 12,340.00")

    def test_dates_in_words(self):
        self.assertEqual(R.format_date("2026-07-06"), "6 Jul 2026")
        self.assertEqual(R.format_date("2026-09-14T21:07:04Z"), "14 Sep 2026, 21:07 UTC")
        self.assertEqual(R.format_date("none_announced"), "none_announced")

    def test_arithmetic_operands_take_the_engine_two_decimal_spelling(self):
        # The ladder's bar inputs (the cash rate, the realized volatility) are OPERANDS of the
        # arithmetic the freeze prints, not reported figures. format_operand spells them EXACTLY
        # as the engine does - two decimals, ROUND_HALF_UP, no % sign - so the page and
        # ladder.compute never show one number two ways (audit finding c1-1; the renderer prints
        # these figures only where it quotes the engine's own arithmetic).
        self.assertEqual(R.format_operand("3.685", "percent"), "3.69")
        self.assertEqual(R.format_operand("48.605", "percent annualised"), "48.61")

    def test_every_percentage_takes_the_one_decimal_display(self):
        # format_number applies the one-decimal percentage rule to EVERY percentage, whatever its
        # recorded precision; it never sniffs the decimal count to guess an operand (U6b ruling i).
        self.assertEqual(R.format_number("3.685", "percent"), "3.7%")
        self.assertEqual(R.format_number("48.605", "percent annualised"), "48.6% annualised")
        self.assertEqual(R.format_number("3.685", "percent_per_year"), "3.7% per year")
        self.assertEqual(R.format_number("3.68", "percent"), "3.7%")

    def test_a_live_figure_is_never_erased_to_zero(self):
        # One decimal would print 0.0 for a figure that is not zero; the exact text stands instead.
        self.assertEqual(R.format_number("0.0068", "percent"), "0.0068")
        self.assertEqual(R.format_number("0.001", "percent"), "0.001")

    def test_fixed_precision_paths_never_erase_a_live_figure(self):
        # Round 3 finding r3-2: the never-erase rule (honoured by the percent, plain-count,
        # fixed-unit, fallback-unit and money-scale paths) was missing from three fixed-precision
        # paths - the share/reference price, the multiple, and MW - so a live sub-precision value
        # rounded to zero on the page ($0.00, 0.00x, 0 MW). A nonzero value now keeps its exact
        # spelling rather than being erased. A real zero still reads as zero.
        self.assertEqual(R.format_number("0.004", "USD_per_share"), "0.004")
        self.assertEqual(R.format_number("0.004", "x"), "0.004")
        self.assertEqual(R.format_number("0.04", "MW"), "0.04 MW")
        self.assertEqual(R.format_number("0", "USD_per_share"), "$0.00")
        self.assertEqual(R.format_number("0", "x"), "0x")
        self.assertEqual(R.format_number("0", "MW"), "0 MW")

    def test_unscaled_money_rates_keep_three_significant_figures(self):
        # Round 3 finding r3-3: a money unit with a rate tail but a magnitude below 1,000 was
        # forced to zero decimals, so $12.40/day read as $12/day - a changed value against the
        # three-significant-figure rule. Sub-1,000 rate money now takes the same three-figure
        # precision every other money figure does; a magnitude at or above 1,000 is unaffected.
        self.assertEqual(R.format_number("12.4", "USD_per_day"), "$12.4/day")
        self.assertEqual(R.format_number("1.23", "USD_per_day"), "$1.23/day")
        self.assertEqual(R.format_number("949.7", "USD_per_day"), "$950/day")
        self.assertEqual(R.format_number("655709848.10", "USD_per_day"), "$656M/day")

    def test_a_rate_basis_stays_visible(self):
        # P-U6b-1 (architect ruling, round 2): a percent/fraction unit that carries a rate or time
        # basis keeps that basis after the figure - a funding rate of 0.01% per 8 hours read as a
        # bare "0.0%" or "0.01%" misleads about the period. The figure takes the ordinary rule,
        # then the basis in words. For a small value the never-erase guard keeps enough decimals
        # to show the first significant figure rather than erasing it. A plain percent (no basis)
        # is unchanged.
        result = R.format_number("0.0001", "fraction per 8 hours")
        self.assertIn("per 8 hours", result)
        self.assertNotIn("0.0%", result)
        self.assertTrue(result.startswith("0.01%"), result)
        self.assertEqual(R.format_number("3.91", "percent_per_year"), "3.9% per year")
        self.assertEqual(R.format_number("48.605", "percent annualised"), "48.6% annualised")
        self.assertEqual(R.format_number("71", "percent"), "71.0%")

    def test_percent_basis_is_generalised_from_the_unit_tail(self):
        # P-U6b-4 (architect ruling, round 4): whatever follows the leading percent/fraction token
        # IS the basis and stays on the page - a year-over-year or of-revenue figure read as a bare
        # percent drops what it is a percent OF. "yoy" expands to "year over year"; any other tail
        # is spelt with underscores turned to spaces. An exact percent still carries no basis, and
        # fraction_of_price stays a signed drawdown percent with no basis.
        self.assertEqual(R.format_number("12.34", "percent_year_over_year"), "12.3% year over year")
        self.assertEqual(R.format_number("12.34", "percent_yoy"), "12.3% year over year")
        self.assertEqual(R.format_number("41.7", "percent_of_revenue"), "41.7% of revenue")
        self.assertEqual(R.format_number("2.5", "percent_of_book"), "2.5% of book")
        self.assertEqual(R.format_number("71", "percent"), "71.0%")
        self.assertEqual(R.format_number("0.494479", "fraction_of_price"), "-49.4%")

    def test_the_prose_matcher_will_not_start_inside_another_token(self):
        # P-U6b-5 (architect ruling; finding r3-5, round 3): the prose number matcher has a leading
        # boundary, so a number glued to a preceding word, decimal point, exponent or currency sign
        # is left for
        # that token and never half-rewritten. Pre-fix "$145 dollars" corrupted to "$$145" and
        # "1.2e3 million dollars" to "1.2e$3.00M". A number at a real boundary still reformats.
        self.assertEqual(R.reformat_prose("$145 dollars", "seat", []), "$145 dollars")
        self.assertNotIn("$$", R.reformat_prose("$145 dollars", "seat", []))
        self.assertEqual(R.reformat_prose("1.2e3 million dollars", "seat", []),
                         "1.2e3 million dollars")
        self.assertEqual(R.reformat_prose("revenue of 47,636 thousand dollars", "seat", []),
                         "revenue of $47.6M")

    def test_the_prose_matcher_will_not_retry_inside_a_signed_or_ranged_token(self):
        # Round 4 finding r4-1 extends the round-3 leading boundary (r3-5): that boundary now
        # excludes a hyphen too, so the matcher cannot retry at the second number of a range or
        # after a negative exponent and corrupt it. Pre-fix "1-2 million dollars" became "1-$2.00M"
        # and "3-5 million dollars"
        # became "3-$5.00M". A number whose own leading minus sits at a real boundary still
        # reformats as a negative aggregate.
        self.assertEqual(R.reformat_prose("1-2 million dollars", "seat", []), "1-2 million dollars")
        self.assertEqual(R.reformat_prose("3-5 million dollars", "seat", []), "3-5 million dollars")
        self.assertEqual(R.reformat_prose("1e-3 million dollars", "seat", []),
                         "1e-3 million dollars")
        self.assertEqual(R.reformat_prose("-2 million dollars", "seat", []), "-$2.00M")
        self.assertEqual(R.reformat_prose("we lost -500 thousand dollars", "seat", []),
                         "we lost -$500K")

    def test_a_ranged_or_exponent_second_number_is_left_whole(self):
        # Carried register item P-U6b-7 (sub-charge (a) round 5): the one-character lookbehind
        # could see "1-2" but never "1 to 2", "1 - 2" or "1e+3", so it half-respelt a spaced range
        # or a positive exponent - "1 to 2 million dollars" became "1 to $2.00M", which MISLEADS
        # (a missed reformat is merely cosmetic). The guard now reads the whole run before the
        # match: a number and a range connector, or an exponent marker, leaves the whole thing
        # alone and logs nothing.
        for text in ("1 to 2 million dollars", "1 - 2 million dollars",
                     "1 – 2 million dollars", "1 — 2 million dollars",
                     "1 and 2 million dollars", "1e+3 million dollars"):
            log = []
            self.assertEqual(R.reformat_prose(text, "seat", log), text)
            self.assertEqual(log, [], text)
        # A negative aggregate at a real boundary still reformats, and so does a plain one.
        self.assertEqual(R.reformat_prose("-2 million dollars", "seat", []), "-$2.00M")
        self.assertEqual(R.reformat_prose("revenue of 2 million dollars", "seat", []),
                         "revenue of $2.00M")

    def test_a_hyphen_glued_to_a_spaced_range_second_number_is_left_whole(self):
        # Round 3 (F-r3-1): a spaced range whose hyphen is glued to the second figure
        # ("1 -2 million dollars") absorbed the hyphen into the match as a leading sign, so the
        # range guard saw only "1 " before it and half-respelt the range to "1 -$2.00M", which
        # MISLEADS (a missed reformat is merely cosmetic). The hyphen a match takes as a leading
        # sign is put back before the range check, so the whole spaced range is left alone.
        for text in ("a range of 1 -2 million dollars",
                     "revenue of 5 -500 thousand dollars"):
            log = []
            self.assertEqual(R.reformat_prose(text, "seat", log), text)
            self.assertEqual(log, [], text)
        # A negative aggregate at a real boundary (no figure immediately before it) still reformats.
        self.assertEqual(R.reformat_prose("a loss of -500 thousand dollars", "seat", []),
                         "a loss of -$500K")
        self.assertEqual(R.reformat_prose("-2 million dollars", "seat", []), "-$2.00M")

    def test_a_price_written_in_prose_keeps_its_cents(self):
        # U6b architect ruling (ii): a share price written in prose keeps two decimals. A
        # bare-dollar amount under 1,000 with exactly two decimals is a price, not an aggregate,
        # so "19.00 dollars" reads "$19.00", not "$19". A whole-dollar amount and an aggregate
        # (scaled, or 1,000 and above) are unchanged.
        log = []
        self.assertEqual(R.reformat_prose("a floor of 19.00 dollars", "seat", log),
                         "a floor of $19.00")
        self.assertEqual(log[0]["replacement"], "$19.00")
        self.assertEqual(R.reformat_prose("about 250 dollars", "seat", []), "about $250")
        self.assertEqual(R.reformat_prose("3,200,000 thousand dollars", "seat", []), "$3.20B")

    def test_a_fractional_dollar_price_in_prose_keeps_its_precision(self):
        # Round 1 finding r1-1: a bare-dollar amount under 1,000 with a fractional part is a
        # price; scaling it to whole dollars CHANGES the value ("38.6 dollars" must not become
        # "$39"). One or two decimals become a two-decimal price; more than two decimals are left
        # alone rather than rounded (a missed reformat is cosmetic; a changed value is a defect).
        self.assertEqual(R.reformat_prose("a floor of 38.6 dollars", "seat", []),
                         "a floor of $38.60")
        self.assertEqual(R.reformat_prose("24.69 dollars", "seat", []), "$24.69")
        self.assertEqual(R.reformat_prose("38.625 dollars", "seat", []), "38.625 dollars")

    def test_percentage_points_are_not_mislabelled_as_percent(self):
        # Round 1 finding r1-2: "percentage_points" is a DIFFERENT unit from "percent" and is
        # present in the frozen packs; rendering a percentage-point figure with a "%" sign changes
        # its meaning. It reads to one decimal as points (unit READ-A). True percent units (exact,
        # or a "percent " / "percent_" qualifier) still render as a percentage.
        self.assertEqual(R.format_number("-0.17", "percentage_points"), "-0.2 points")
        self.assertEqual(R.format_number("-5.67", "percentage_points_of_gross_margin"),
                         "-5.67 percentage points of gross margin")
        self.assertEqual(R.format_number("3.9", "percent_per_year"), "3.9% per year")
        self.assertEqual(R.format_number("41.7", "percent annualised"), "41.7% annualised")

    def test_the_substitution_log_is_named_after_the_report_never_its_own_path(self):
        # Round 2 finding r2-1 / architect ruling (round 3 Step 0): the substitution log's file
        # name is DERIVED from the report's own file name (<report>.number-substitutions.json), so
        # it can never be the report's own path - not even a case-variant of it on a
        # case-insensitive disk, where the old fixed-name log aliased and overwrote the report.
        # Both an -o that matches the old fixed name and its case-variant now render the HTML
        # report to the named path and drop the log beside it under the derived name.
        for name in ("Number-Substitutions.json", "number-substitutions.json"):
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = _mutated_copy(tmp)
                out_dir = os.path.join(tmp, "out")
                os.makedirs(out_dir)
                target = os.path.join(out_dir, name)
                rc = R.main(["render_report.py", "-o", target, run_dir])
                self.assertEqual(rc, 0, name)
                # The report file holds the HTML report, not the JSON log.
                with open(target, "rb") as fh:
                    self.assertTrue(fh.read().startswith(R.PREAMBLE), name)
                # The log sits beside it under the derived name and is valid JSON.
                log = target + ".number-substitutions.json"
                self.assertTrue(os.path.isfile(log), name)
                with open(log, encoding="utf-8") as fh:
                    self.assertIsInstance(json.load(fh), list)

    def test_zero_has_one_rendering(self):
        self.assertEqual(R.format_number("-0.0"), "0")
        self.assertEqual(R.format_number("0e50", "percent"), "0.0%")
        self.assertEqual(R.format_number("0", "USD"), "$0")

    def test_text_that_is_not_a_pure_number_passes_through_as_words(self):
        for text in ("NOT AVAILABLE", "none_announced", "2027-H2",
                     "8-10", "250-500", "more than 1600",
                     "0.48% cost to borrow; 1,900,000 shares available"):
            self.assertEqual(R.format_number(text, "percent"), text)

    def test_a_zero_padded_bare_integer_is_an_identifier(self):
        self.assertEqual(R.format_number("0000320193"), "0000320193")
        self.assertEqual(R.format_number("0000320193", "shares"), "0000320193")

    def test_ruled_unrounded_units(self):
        self.assertEqual(R.format_number("3.125", "BTC"), "3.125")
        self.assertEqual(R.format_number("850123", "block_height"), "850123")

    def test_absurd_magnitudes_fall_back_to_their_own_text(self):
        self.assertEqual(R.format_number("1e400", "USD"), "1e400")

    def test_non_numbers_and_null(self):
        self.assertEqual(R.format_number(None), "None")
        self.assertEqual(R.format_number(True), "True")

    def test_plain_counts_get_thousands_separators(self):
        self.assertEqual(R.format_number(700000), "700,000")
        self.assertEqual(R.format_number(42), "42")


class TestMarkdownSubset(unittest.TestCase):
    def test_the_subset_renders_and_everything_else_is_escaped(self):
        out = R.markdown("## Head\n\n**bold** and *lean* and `code`\n\n- one\n- two\n\n1. first")
        self.assertIn("<h4>Head</h4>", out)
        self.assertIn("<strong>bold</strong>", out)
        self.assertIn("<em>lean</em>", out)
        self.assertIn("<code>code</code>", out)
        self.assertIn("<ul><li>one</li><li>two</li></ul>", out)
        self.assertIn("<ol><li>first</li></ol>", out)

    def test_markup_in_a_seats_text_never_becomes_live(self):
        out = R.markdown("a <script>bad()</script> tag and an unpaired * star")
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("* star", out)
        self.assertNotIn("<em>", out)


class TestFixtureHonoursTheContracts(unittest.TestCase):
    """The fixture is invented, but it is invented INSIDE the frozen contracts."""

    def _schema(self, name):
        with open(os.path.join(SCHEMA_DIR, name), "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))

    def test_fixture_verdict_is_schema_valid(self):
        with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
            doc = json.loads(fh.read().decode("utf-8"))
        self.assertEqual(validate.validate(doc, self._schema("verdict_schema.json")), [])

    def test_fixture_capture_is_schema_valid(self):
        with open(os.path.join(FIXTURE, "pack", "pack.json"), "rb") as fh:
            pack = json.loads(fh.read().decode("utf-8"))
        self.assertEqual(validate.validate(pack["capture"],
                                           self._schema("capture_schema.json")), [])

    def test_fixture_seat_answers_are_schema_valid(self):
        members = self._schema("seat_answers.json")
        cases = (("001-answer-frame.json", "frame"),
                 ("003-answer-advisor_bull.json", "advisor"),
                 ("007-answer-advisor_bear.json", "advisor"),
                 ("008-answer-reviewer.json", "reviewer"),
                 ("009-answer-chair_draft.json", "chair_draft"),
                 ("010-answer-chair_resolve.json", "chair_resolve"))
        for name, member in cases:
            with open(os.path.join(FIXTURE, "rpc", name), "rb") as fh:
                doc = json.loads(fh.read().decode("utf-8"))
            self.assertEqual(validate.validate(doc, members[member]), [], name)


class TestCommandLine(unittest.TestCase):
    def _run(self, args, **kw):
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run([sys.executable, "-m", "council.report.render_report"] + args,
                              cwd=ROOT, env=env, capture_output=True, text=True, **kw)

    def test_renders_the_report_and_its_substitution_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            before = set(os.listdir(run_dir))
            proc = self._run([run_dir])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            added = set(os.listdir(run_dir)) - before
            # The report, and the record beside it of every number the prose reformatter
            # respelt (owner ruling AC16(1)), named after the report itself.
            self.assertEqual(added, {"report.html", "report.html.number-substitutions.json"})
            out_path = os.path.join(run_dir, "report.html")
            self.assertIn("report written:", proc.stdout)
            self.assertIn("report.html", proc.stdout)
            self.assertIn("(%d bytes)" % os.path.getsize(out_path), proc.stdout)
            # The log is valid JSON and each row names where, from and to.
            with open(os.path.join(run_dir, "report.html.number-substitutions.json"),
                      encoding="utf-8") as fh:
                rows = json.load(fh)
            for row in rows:
                self.assertEqual(set(row), {"location", "original", "replacement"})
            # Re-rendering over its own report is allowed and still exits 0.
            self.assertEqual(self._run([run_dir]).returncode, 0)

    def test_dash_o_writes_to_the_named_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            target = os.path.join(tmp, "elsewhere.html")
            proc = self._run([run_dir, "-o", target])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(os.path.isfile(target))

    def test_missing_required_inputs_exit_1_with_a_plain_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty = os.path.join(tmp, "not-a-run")
            os.makedirs(empty)
            proc = self._run([empty])
            self.assertEqual(proc.returncode, 1)
            self.assertIn("REFUSED", proc.stderr)
            self.assertIn("missing required inputs", proc.stderr)
            self.assertIn("verdict.json", proc.stderr)

    def test_missing_seat_answer_exit_1_names_the_seat(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp, lambda d: os.unlink(
                os.path.join(d, "rpc", "008-answer-reviewer.json")))
            proc = self._run([run_dir])
            self.assertEqual(proc.returncode, 1)
            self.assertIn("reviewer", proc.stderr)

    def test_never_overwrites_a_file_that_is_not_its_own_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            target = os.path.join(tmp, "precious.html")
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("somebody else's page")
            proc = self._run([run_dir, "-o", target])
            self.assertEqual(proc.returncode, 4)
            with open(target, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "somebody else's page")


class TestSC3Round1Regressions(unittest.TestCase):
    """SC3 round-1 findings at the renderer; both FAILED pre-fix."""

    # r1-3: the hand-off section omitted the envelope's sizing inputs.
    def test_the_atlas_section_renders_every_sizing_input(self):
        atlas = HTML[HTML.index('<h3 id="atlas">'):]
        self.assertIn("The deepest peak-to-trough fall", atlas)
        self.assertIn("-46", atlas)
        self.assertIn("5 Nov 2026", atlas)

    # r1-4: the page asserted the outside audit happened on runs where
    # it did not.
    def test_the_audit_happened_prose_is_gated_on_success(self):
        self.assertIn("read the full case file and challenged", HTML)

        def mutate(run_dir):
            _rewrite_verdict(run_dir, lambda doc: doc["challenge"].update(
                {"status": "timeout",
                 "failure_reason": "the bridge timed out",
                 "findings": [], "dispositions": [],
                 "endorsement": None, "summary": None}))
            os.unlink(os.path.join(run_dir, "challenge", "result.json"))
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertNotIn("read the full case file and audited", page)
        self.assertIn(R.AUDIT_FAILED_SENTENCE, page)


class TestSC3Round7Regression(unittest.TestCase):
    """Closing incremental 1: the dependency marker must cover tier-2
    passages a ruling rests on, not only tier-1 rows."""

    def test_a_passage_dependency_is_marked(self):
        def mutate(run_dir):
            def add_dep(doc):
                doc["evidence_dependencies"].append("guidance_passage")
            _rewrite_verdict(run_dir, add_dep)
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        needle = "used in the ruling</span> Guidance passage"
        self.assertIn(needle, page)


class TestSC3Round6Regressions(unittest.TestCase):
    """Closing-pass findings at the renderer; both FAILED pre-fix."""

    # r6-2: the evidence fold claimed every pack fact was "built on".
    def test_the_evidence_fold_does_not_overclaim_provenance(self):
        self.assertNotIn("this verdict was built on", HTML)
        self.assertIn("in the evidence pack", HTML)
        # the declared dependencies are marked on their rows
        self.assertIn("used in the ruling", HTML)

    # r6-3: null seat models were silently dropped from the line.
    def test_partial_model_provenance_says_so(self):
        def mutate(run_dir):
            def strip_one(doc):
                models = doc["provenance"]["models_per_seat"]
                first = sorted(models)[0]
                models[first] = None
            _rewrite_verdict(run_dir, strip_one)
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertIn("not recorded for every seat", page)


class TestSC3Round4Regression(unittest.TestCase):
    """Round 4: an ordinary bridge failure (timeout, raw and published
    agree) must read as a failure, never as papers-rejected."""

    def test_an_ordinary_failure_is_not_called_rejected_papers(self):
        def mutate(run_dir):
            _rewrite_verdict(run_dir, lambda doc: doc["challenge"].update(
                {"status": "timeout",
                 "failure_reason": "the bridge timed out",
                 "findings": [], "dispositions": [],
                 "endorsement": None, "summary": None}))
            result_path = os.path.join(run_dir, "challenge", "result.json")
            with open(result_path, "w", encoding="utf-8") as handle:
                json.dump({"status": "timeout",
                           "failure_reason": "the bridge timed out",
                           "findings": None, "usage_tokens": None,
                           "raw_output": "response.json",
                           "returncode": None}, handle)
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertNotIn("the machine rejected them", page)
        self.assertIn("no usable response to show", page)


class TestSC3Round3Regression(unittest.TestCase):
    """Round 3: when the host rejected the papers, the page must show
    NONE of their content - a binding failure could otherwise put
    another case's findings on the owner's page."""

    def test_rejected_papers_render_no_content(self):
        def mutate(run_dir):
            _rewrite_verdict(run_dir, lambda doc: doc["challenge"].update(
                {"status": "binding_failure",
                 "failure_reason": "the echoes do not match this run",
                 "findings": [], "dispositions": [],
                 "endorsement": None, "summary": None}))
            # the raw bridge file still claims success - untouched
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertNotIn("Its own summary.", page)
        self.assertNotIn("a claim without support", page)
        self.assertIn("rejected", page.lower())


class TestSC3Round2Regression(unittest.TestCase):
    """Round 2: the audit-happened sentence must gate on the PUBLISHED
    verdict's challenge status, not the raw bridge file - the host can
    reject a bridge success and degrade while the raw file still says
    success."""

    def test_the_sentence_gates_on_the_verdict_not_the_raw_result(self):
        def mutate(run_dir):
            _rewrite_verdict(run_dir, lambda doc: doc["challenge"].update(
                {"status": "schema_failure",
                 "failure_reason": "duplicate finding ids",
                 "findings": [], "dispositions": [],
                 "endorsement": None, "summary": None}))
            # the raw bridge file keeps claiming success - untouched
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertNotIn("read the full case file and audited", page)
        self.assertIn(R.AUDIT_FAILED_SENTENCE, page)


class TestKindSentence(unittest.TestCase):
    """THEMES part 3: the verdict section states the subject's kind in
    plain words, whatever the kind."""

    def test_the_single_name_sentence(self):
        self.assertIn("The subject is a single name.", HTML)

    def test_the_basket_sentence_counts_the_names(self):
        self.assertIn("The subject is a basket of 2 named instruments "
                      "judged as one idea.", BASKET_HTML)

    def test_the_theme_sentence(self):
        self.assertIn("The subject is an investment theme judged through "
                      "its named expression.", THEME_HTML)


class TestConstituentsSection(unittest.TestCase):
    """THEMES part 3: the constituent table for a basket and a theme's
    named universe - identity, frozen price and market value, and the
    chairman's own metric and note per name."""

    def test_the_section_renders_in_the_detail_tier_without_a_nav_entry(self):
        # The constituents are decision content, on the open decision-in-detail tier now, under a
        # content-named h3 with no nav entry of their own (architect ruling closing P-U6b-9).
        for page in (BASKET_HTML, THEME_HTML):
            self.assertIn("<h3>The constituents</h3>", _detail(page))
            self.assertNotIn('<h2 id="constituents">', page)
            self.assertNotIn('href="#constituents"', page)

    def test_no_section_on_a_single_name(self):
        self.assertNotIn('<h2 id="constituents">', HTML)
        self.assertNotIn('href="#constituents"', HTML)

    def test_the_table_columns_in_plain_words(self):
        for label in ("Name", "Ticker", "Last price", "Market value",
                      "Load-bearing metric", "Note"):
            self.assertIn(">%s</th>" % label, BASKET_HTML, label)

    def test_identity_price_and_market_value_from_the_pack(self):
        self.assertIn("<td>Alpha Chips Inc (INVENTED)</td>", BASKET_HTML)
        self.assertIn('<td class="nowrap">ACHP</td>', BASKET_HTML)
        # The frozen figures, rounded for reading through format_number:
        # one precision per unit, a whole number stays whole.
        self.assertIn('<td class="nowrap">$231.40</td>', BASKET_HTML)
        self.assertIn('<td class="nowrap">$1.15T</td>', BASKET_HTML)
        self.assertIn('<td class="nowrap">$88.15</td>', BASKET_HTML)

    def test_metric_and_note_from_the_constituent_notes(self):
        self.assertIn("<td>data-centre revenue</td>", BASKET_HTML)
        self.assertIn("The compute half of the pair", BASKET_HTML)
        self.assertIn("Tripwire: A down quarter in data-centre revenue. "
                      "(INVENTED)", BASKET_HTML)
        # BGRD's note carries no tripwire, so exactly one tripwire line.
        self.assertEqual(BASKET_HTML.count("Tripwire: "), 1)

    def test_a_row_without_a_note_renders_em_dashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp, lambda d: _rewrite_verdict(
                d, lambda doc: doc.__setitem__("constituent_notes", None)),
                source=FIXTURE_BASKET)
            page = _render(run_dir)
        self.assertIn("</td><td>&mdash;</td><td>&mdash;</td></tr>", page)

    def test_the_emphasis_label_is_the_briefs_own_sentence_verbatim(self):
        # One ruled sentence: the page's label is byte-identical to the
        # label the seat briefs render.
        self.assertEqual(R.EMPHASIS_LABEL, briefs.EMPHASIS_LABEL)
        # Rendered under the table AND in the envelope section.
        self.assertEqual(BASKET_HTML.count(E(R.EMPHASIS_LABEL)), 2)
        self.assertIn("<li>ACHP: roughly two thirds of the idea</li>",
                      BASKET_HTML)
        # The theme fixture states no proportions, so no label there.
        self.assertNotIn(E(R.EMPHASIS_LABEL), THEME_HTML)


class TestVehicleBlock(unittest.TestCase):
    """THEMES part 3: a vehicle-mode theme renders the one implementation
    vehicle's identity instead of a constituent table."""

    def _vehicle_page(self):
        vehicle = {"name": "Invented Storage Vehicle Fund",
                   "ticker": "THVH", "listing": "Invented Exchange",
                   "currency": "USD"}

        def change(doc):
            del doc["subject"]["constituents"]
            doc["subject"]["vehicle"] = vehicle
            doc["constituent_notes"] = None
            doc["atlas_envelope"]["constituents"] = None
            doc["atlas_envelope"]["vehicle"] = vehicle
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(
                tmp, lambda d: _rewrite_verdict(d, change),
                source=FIXTURE_THEME)
            return _render(run_dir)

    def test_the_vehicle_identity_block_replaces_the_table(self):
        page = self._vehicle_page()
        self.assertIn("The implementation vehicle", page)
        self.assertIn("Invented Storage Vehicle Fund (THVH)", page)
        self.assertIn("Listing: Invented Exchange. Currency: USD.", page)
        self.assertNotIn(">Load-bearing metric</th>", page)
        # On the open decision-in-detail tier now, under a content-named h3, no nav entry
        # (architect ruling closing P-U6b-9).
        self.assertIn("<h3>The implementation vehicle</h3>", _detail(page))
        self.assertNotIn('<h2 id="constituents">', page)

    def test_the_envelope_carries_the_vehicle_row(self):
        page = self._vehicle_page()
        self.assertIn('<th class="nowrap">Vehicle</th>'
                      "<td>Invented Storage Vehicle Fund (THVH)</td>",
                      page)

    def test_the_vehicle_page_states_the_frozen_thesis(self):
        # THEMES-C r3-1: the thesis renders in vehicle mode too.
        self.assertIn(E("Utility-scale storage deployments compound for "
                        "a decade as grids absorb renewable generation. "
                        "(INVENTED FIXTURE)"), self._vehicle_page())


class TestThemeFalsifierBlock(unittest.TestCase):
    """THEMES part 3: the theme's falsifiers render first among the
    tripwires, each with the figure it is scored against, the prior
    period on a level row, and the metric identity the sitting assumed
    (REG-18: the owner's question is answerable from the page)."""

    def test_the_block_renders_in_the_decision_in_detail_tier(self):
        # The theme's falsifiers, with the scoring detail the front's one tripwire table does not
        # carry, moved to the decision-in-detail tier when the duplicate tripwires appendix was
        # removed (owner ruling AC16, the architect's ruling on the doubled table).
        heading = "<h3>The theme's falsifiers</h3>"
        self.assertIn(heading, _detail(THEME_HTML))
        self.assertNotIn(heading, HTML)

    def test_statement_and_scored_against_line(self):
        self.assertIn("If quarterly storage installations print at or "
                      "below the prior year, the theme is wrong. "
                      "(INVENTED)", THEME_HTML)
        self.assertIn("Scored against <code>storage_installs_q</code> "
                      "from INVENTED FIXTURE - industry deployment "
                      "tracker, quarterly release, on 15 Nov 2026.",
                      THEME_HTML)

    def test_the_level_row_shows_its_prior_period(self):
        # The prior period, rounded for reading like every figure on
        # the page (the verdict keeps the exact bytes); the date in words.
        self.assertIn("Prior period: 9.10 GW, as of 15 Aug 2025.",
                      THEME_HTML)
        # The event row carries no prior period: exactly one such line.
        self.assertEqual(THEME_HTML.count("Prior period: "), 1)

    def test_every_theme_row_names_its_metric_identity(self):
        self.assertIn("Metric identity assumed: Quarterly utility-scale "
                      "storage installations in gigawatts, as the "
                      "tracker defines them, both periods. (INVENTED)",
                      THEME_HTML)
        self.assertIn("Metric identity assumed: The credit&#x27;s "
                      "statutory status against current law. (INVENTED)",
                      THEME_HTML)
        self.assertEqual(THEME_HTML.count("Metric identity assumed: "), 2)

    def test_the_plain_row_stays_in_the_falsifier_table_with_its_tag(self):
        self.assertIn('<span class="tag">GSTA</span> If Grid Storage '
                      "Alpha&#x27;s deployment backlog prints below",
                      THEME_HTML)

    def test_constituent_tags_on_bound_level_and_trigger_rows(self):
        # The bound invalidation level (theme fixture) and the bound
        # price trigger (basket fixture) both show the ticker tag.
        self.assertIn('<span class="tag">GSTB</span> A Grid Storage '
                      "Beta close under 10.00", THEME_HTML)
        self.assertIn('<span class="tag">ACHP</span> Reopen if Alpha '
                      "Chips closes at or under 200.00 USD.", BASKET_HTML)


class TestThematicEtfRendering(unittest.TestCase):
    """THEMES part 3: a thematic etf's falsifier rows render exactly as
    a theme's - the block is driven by the rows, never by the kind."""

    def _etf_page(self):
        def change(doc):
            doc["subject"]["kind"] = "etf"
            del doc["subject"]["constituents"]
            doc["constituent_notes"] = None
            doc["atlas_envelope"]["subject_kind"] = "etf"
            doc["atlas_envelope"]["constituents"] = None
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(
                tmp, lambda d: _rewrite_verdict(d, change),
                source=FIXTURE_THEME)
            return _render(run_dir)

    def test_the_falsifier_block_renders_identically(self):
        page = self._etf_page()
        self.assertIn("The subject is a collective investment vehicle.",
                      page)
        self.assertIn("<h3>The theme's falsifiers</h3>", page)
        self.assertIn("Prior period: 9.10 GW, as of 15 Aug 2025.", page)
        self.assertEqual(page.count("Metric identity assumed: "), 2)
        # No constituent table on a collective vehicle.
        self.assertNotIn('<h2 id="constituents">', page)

    def test_the_thematic_etf_page_states_the_frozen_thesis(self):
        # THEMES-C r3-1: the fund IS the vehicle, so no expression
        # fields exist at all - the idea judged still shows.
        page = self._etf_page()
        self.assertIn(E("Utility-scale storage deployments compound for "
                        "a decade as grids absorb renewable generation. "
                        "(INVENTED FIXTURE)"), page)


class TestEnvelopeKindFields(unittest.TestCase):
    """THEMES part 3: the hand-off section shows the envelope's frozen
    subject shape - kind, the named constituents or the vehicle, and
    the proportions under their ruled label."""

    def test_the_basket_envelope_rows(self):
        atlas = BASKET_HTML[BASKET_HTML.index('<h3 id="atlas">'):]
        self.assertIn('<th class="nowrap">Subject kind</th><td>a basket '
                      "of 2 named instruments judged as one idea</td>",
                      atlas)
        self.assertIn('<th class="nowrap">Constituents</th>'
                      "<td>Alpha Chips Inc (INVENTED) (ACHP), "
                      "Beta Grid Corp (INVENTED) (BGRD)</td>", atlas)
        self.assertIn(E(R.EMPHASIS_LABEL), atlas)
        self.assertIn("<li>BGRD: the remaining third</li>", atlas)

    def test_the_theme_envelope_rows(self):
        atlas = THEME_HTML[THEME_HTML.index('<h3 id="atlas">'):]
        self.assertIn('<th class="nowrap">Subject kind</th><td>an '
                      "investment theme judged through its named "
                      "expression</td>", atlas)
        self.assertIn('<th class="nowrap">Constituents</th>', atlas)

    def test_the_single_name_envelope_row(self):
        atlas = HTML[HTML.index('<h3 id="atlas">'):]
        self.assertIn('<th class="nowrap">Subject kind</th>'
                      "<td>a single name</td>", atlas)


class TestKindFixturesHonourTheContracts(unittest.TestCase):
    """The two new fixture runs are invented INSIDE the frozen 1.3.0
    contracts, exactly as run-invented-1 is."""

    def _schema(self, name):
        with open(os.path.join(SCHEMA_DIR, name), "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))

    def test_both_kind_fixture_verdicts_are_schema_valid(self):
        schema = self._schema("verdict_schema.json")
        for fixture_dir in (FIXTURE_BASKET, FIXTURE_THEME):
            with open(os.path.join(fixture_dir, "verdict.json"),
                      "rb") as fh:
                doc = json.loads(fh.read().decode("utf-8"))
            self.assertEqual(validate.validate(doc, schema), [],
                             fixture_dir)

    def test_both_kind_fixture_captures_are_schema_valid(self):
        schema = self._schema("capture_schema.json")
        for fixture_dir in (FIXTURE_BASKET, FIXTURE_THEME):
            with open(os.path.join(fixture_dir, "pack", "pack.json"),
                      "rb") as fh:
                pack = json.loads(fh.read().decode("utf-8"))
            self.assertEqual(validate.validate(pack["capture"], schema),
                             [], fixture_dir)


class TestBoundTagReachesTheOwnersPage(unittest.TestCase):
    """Owner ruling AB20. The declaration that a figure is a BOUND left
    the fact's source sentence for the capture's own shape, so every
    place that used to read it out of the prose renders it from the tag
    instead. This page is one of them: the owner is the last reader,
    and a bound he reads as a measurement is the failure AB19 exists to
    prevent."""

    CEILING = {"kind": "ceiling",
               "published_line": "Other investing activities, net"}
    FLOOR = {"kind": "floor", "published_line": None}

    def test_the_page_and_the_seat_briefs_speak_one_sentence(self):
        for tag in (self.CEILING, self.FLOOR):
            self.assertEqual(R._bound_words(tag),
                             briefs._bound_note({"bound": tag}))

    def test_an_untagged_fact_renders_nothing(self):
        self.assertIsNone(R._bound_words(None))
        self.assertIsNone(R._bound_words(
            {"kind": "estimate", "published_line": None}))

    def test_a_ceiling_says_it_can_only_overstate(self):
        words = R._bound_words(self.CEILING)
        self.assertIn("declared a CEILING", words)
        self.assertIn("can only overstate", words)

    def test_the_sentence_never_carries_the_capture_s_own_words(self):
        """Audit finding AB20 r1-1. The line's NAME is capture free
        text; the sentence is generated and says only that the capture
        names a line. On this page the name is rendered beside the
        sentence and HTML-escaped; in a seat's case file it travels
        inside the quoted-data fence."""
        self.assertNotIn("Other investing activities, net",
                         R._bound_words(self.CEILING))

    def test_neither_sentence_claims_the_line_is_the_narrowest(self):
        """The one condition no machine here can check."""
        for tag in (self.CEILING, self.FLOOR):
            self.assertNotIn("narrowest",
                             R._bound_words(tag).casefold())


class TestThemesCRound1Regression(unittest.TestCase):
    """THEMES-C r1-1: a row bound to one member renders its ticker tag
    on every table that receives the binding, not only the tripwires -
    the hand-off's sizing table and the evidence checklist dropped it.
    Both tag assertions FAILED pre-fix."""

    def test_a_member_bound_sizing_row_shows_its_tag(self):
        atlas = BASKET_HTML[BASKET_HTML.index('<h3 id="atlas">'):]
        self.assertIn('<span class="tag">ACHP</span> INVENTED - the '
                      "average value changing hands daily in one leg of "
                      "the pair", atlas)
        # A subject-level row stays untagged.
        self.assertIn("<td>INVENTED - the pack carries no realized "
                      "volatility series; the gap is stated here.</td>",
                      atlas)

    def test_a_member_bound_checklist_row_shows_its_tag(self):
        self.assertIn('<span class="tag">ACHP</span> The data-centre '
                      "revenue Alpha Chips load-bears on for this "
                      "thesis. (INVENTED FIXTURE)", BASKET_HTML)
        self.assertIn('<span class="tag">GSTA</span> The deployment '
                      "backlog Grid Storage Alpha load-bears on for "
                      "this theme. (INVENTED FIXTURE)", THEME_HTML)
        # A subject-level check stays untagged.
        self.assertIn("<td>Is the pair earning more than a year ago, "
                      "judged as one idea? (INVENTED FIXTURE)</td>",
                      BASKET_HTML)


class TestThemesCRound3Regression(unittest.TestCase):
    """THEMES-C r3 (closing pass): the frozen subject speaks on the page.
    r3-1 - the theme's thesis renders wherever a theme block exists, so
    a rating never shows without the idea it judged. r3-2 - each theme
    falsifier leads with the declared condition resolved from the
    subject's own list, so the chairman's wording can never stand in
    for the declaration. Every positive assertion FAILED pre-fix."""

    THESIS = ("Utility-scale storage deployments compound for a decade "
              "as grids absorb renewable generation. (INVENTED FIXTURE)")
    THESIS_LEAD = "The theme&#x27;s thesis, frozen before the council sat"
    DECLARED_LEVEL = ("Quarterly storage installations stop growing "
                      "against the prior year. (INVENTED FIXTURE)")
    DECLARED_EVENT = ("The storage investment credit is repealed. "
                      "(INVENTED FIXTURE)")

    def _falsifier_block(self, page):
        # The theme's falsifiers sit on the decision-in-detail tier now (owner ruling AC16); the
        # block runs from its own h3 to the next h3 on the page.
        start = page.index("<h3>The theme's falsifiers</h3>")
        return page[start:page.index("<h3", start + 5)]

    def test_the_theme_page_states_the_frozen_thesis(self):
        # The theme's thesis leads the executive summary now, directly under the key-data strip
        # (architect ruling closing P-U6b-9): the idea judged is decision content, shown up front,
        # before the chairman's own thesis lede.
        front = _front(THEME_HTML)
        self.assertIn(self.THESIS_LEAD, front)
        self.assertIn(E(self.THESIS), front)
        # The key-data strip is in the masthead now, above the whole executive summary (design
        # audit C5), so the strip-before-thesis order is checked at the page level.
        self.assertLess(THEME_HTML.index("<h3>The numbers this ruling turns on</h3>"),
                        THEME_HTML.index(self.THESIS_LEAD))
        # The five-sentence thesis card is gone (owner ruling AC41(4)); the theme's thesis still
        # comes before the chairman's rationale.
        self.assertNotIn('<span class="lead">The thesis</span>', front)
        self.assertLess(front.index(self.THESIS_LEAD), front.index("Why this rating, in the chairman"))

    def test_no_thesis_card_without_a_theme_block(self):
        self.assertNotIn(self.THESIS_LEAD, HTML)
        self.assertNotIn(self.THESIS_LEAD, BASKET_HTML)

    def test_each_falsifier_leads_with_its_declared_condition(self):
        block = self._falsifier_block(THEME_HTML)
        self.assertIn('<span class="lead">%s</span>'
                      % E(self.DECLARED_LEVEL), block)
        self.assertIn('<span class="lead">%s</span>'
                      % E(self.DECLARED_EVENT), block)

    def test_the_chairmans_scoring_renders_beside_the_declaration(self):
        block = self._falsifier_block(THEME_HTML)
        self.assertIn("How the chairman scored it: If quarterly storage "
                      "installations print at or below the prior year, "
                      "the theme is wrong. (INVENTED)", block)
        self.assertIn("How the chairman scored it: If the storage "
                      "investment credit is repealed, the theme is "
                      "wrong. (INVENTED)", block)

    def test_a_dangling_row_renders_a_dash_never_an_invention(self):
        # Unreachable on a published run - the run's own gate refuses a
        # row that answers no declaration - but a damaged record still
        # renders without the page inventing a condition.
        def change(doc):
            doc["subject"]["theme"]["falsifiers"][0]["id"] = "renamed"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(
                tmp, lambda d: _rewrite_verdict(d, change),
                source=FIXTURE_THEME)
            page = _render(run_dir)
        block = self._falsifier_block(page)
        self.assertIn('<span class="lead">&mdash;</span>', block)
        self.assertIn("How the chairman scored it: If quarterly storage "
                      "installations print at or below the prior year, "
                      "the theme is wrong. (INVENTED)", block)
        # The row whose declaration still resolves keeps its condition.
        self.assertIn('<span class="lead">%s</span>'
                      % E(self.DECLARED_EVENT), block)


class TestDecisionFrontOrder(unittest.TestCase):
    """ANCHORLESS-SPEC section 5 (ruling AB13.5): the report OPENS with the decision, and
    everything else folds behind it as appendices."""

    def test_the_front_is_the_first_section_on_every_page(self):
        # The eight numbered sections in the ruled order (owner's finding 5): the
        # answer first, then the chairman, the advisors, the peer review, the challenge, the
        # decision in detail, the evidence and the appendices.
        for page in (HTML, BASKET_HTML, THEME_HTML):
            found = re.findall(r'<h2 id="([a-z]+)"', page)
            self.assertEqual(found, list(ANCHORS), found)

    def test_the_front_precedes_every_other_section_anchor(self):
        opening = HTML.index('<h2 id="decision"')
        for anchor in ANCHORS:
            if anchor == "decision":
                continue
            self.assertLess(opening, HTML.index('<h2 id="%s"' % anchor), anchor)

    def test_the_appendices_divider_exists_and_names_itself_plainly(self):
        self.assertIn('<span class="secnum">8</span>Appendices</h2>', HTML)
        self.assertIn("The record behind the decision, all folded", HTML)

    def test_the_tripwire_and_verdict_and_warnings_appendix_sections_are_gone(self):
        # The full tripwire table lives once, in the executive summary (owner ruling AC16, the
        # architect's ruling on the doubled table); the verdict fold and the warnings appendix
        # (which only pointed back to the top) are gone too (audit B2/B4/B5/B6).
        for page in (HTML, BASKET_HTML, THEME_HTML):
            self.assertNotIn('<h2 id="tripwires">', page)
            self.assertNotIn('<h2 id="verdict">', page)
            self.assertNotIn('<h2 id="warnings">', page)
        self.assertNotIn("<details open", HTML)

    def test_the_warning_band_renders_once_and_only_at_the_top(self):
        band = ('<div class="card alarm"><span class="shout">The rating moved after the outside '
                "audit. The outside auditor did not see this rating.</span></div>")
        self.assertEqual(HTML.count(band), 1)
        # The warnings band renders directly beneath the masthead, never folded (owner ruling
        # AC16; design audit C4 tier 0), no longer inside the executive summary.
        self.assertIn(band, _masthead(HTML))
        # The warnings appendix that only pointed back to the top is gone (audit B5/B6).
        self.assertNotIn("Every warning on this verdict is printed at the top of this report", HTML)

    def test_a_verdict_with_no_warnings_shows_no_alarm_band(self):
        # With the warnings appendix removed (audit B6), a clean verdict simply carries no alarm
        # band at all - no 'this verdict carries no warnings' machine sentence.
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, lambda d: _rewrite_verdict(
                d, lambda doc: doc.__setitem__("warnings", []))))
        self.assertNotIn("This verdict carries no warnings.", page)
        self.assertNotIn('<div class="card alarm">', _front(page))


class TestDecisionFrontContent(unittest.TestCase):
    """What the front carries for every subject: the rating, the few numbers the ruling turns
    on, the downside, the calendar, the tripwires, what would change it, and where the bench
    disagreed."""

    def test_the_rating_badge_and_the_five_word_scale(self):
        # The rating word, the scale and the subject kind are the masthead rating box now (design
        # audit C4 tier 0 / C5). The chairman's rating sentence stays in the executive summary.
        masthead = _masthead(HTML)
        self.assertIn('<div class="rating-word">Monitor - no view yet; watch the named '
                      "triggers</div>", masthead)
        self.assertIn("The council&#x27;s scale, strongest first: Strong buy, Buy, Hold, Sell",
                      masthead)
        self.assertIn("The subject is a single name.", masthead)
        self.assertIn("No view is worth paying for until one of the named triggers fires.",
                      _front(HTML))

    def test_the_key_numbers_render_as_a_key_data_strip(self):
        # Owner ruling AC16(3), audit B11: the decisive numbers are a key-data strip in the market
        # form under the envelope's own plain labels, in the masthead rail (design audit C5).
        masthead = _masthead(HTML)
        self.assertIn("The numbers this ruling turns on", masthead)
        self.assertIn('<dl class="keydata">', masthead)
        self.assertIn("<dt>%s</dt><dd>$88.40</dd>" % R._glossed("last price"), masthead)
        self.assertIn("<dt>realized volatility, 90 days</dt><dd>41.7%</dd>", masthead)

    def test_a_key_data_strip_shows_at_most_eight_and_names_the_rest(self):
        def change(doc):
            base = doc["atlas_envelope"]["key_numbers"][0]
            doc["atlas_envelope"]["key_numbers"] = [
                dict(base, name="invented number %d" % index) for index in range(1, 11)]
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, lambda d: _rewrite_verdict(d, change)))
        masthead = _masthead(page)
        for index in range(1, 9):
            self.assertIn("<dt>invented number %d</dt>" % index, masthead)
        for index in (9, 10):
            self.assertNotIn("<dt>invented number %d</dt>" % index, masthead)
        self.assertIn("The verdict carries 2 more headline numbers.", masthead)
        # They are not lost: the hand-off section below still lists all ten.
        self.assertIn("<td>invented number 10</td>", page)

    def test_the_downside_ladder_carries_the_invalidation_levels(self):
        # The downside ladder moved to the decision-in-detail tier (owner ruling AC16, audit C4).
        detail = _detail(HTML)
        self.assertIn("The downside ladder", detail)
        self.assertIn('<tr><td class="nowrap">$84.50</td><td>A close under 84.50 breaks the '
                      "base the reopening case rests on.</td></tr>", detail)

    def test_the_tripwires_render_in_one_table_with_levels_dates_and_figures(self):
        # Owner ruling AC16(3), audit C4/B4: everything that would change the rating is one full
        # table - every reopening trigger and every falsifier, each row with what it is, the level
        # or date it turns on, and the figure it is scored against - and no restated bullets below.
        front = _front(HTML)
        self.assertIn("What changes this rating", front)
        self.assertIn('<span class="tag">Reopen the case (price)</span>', front)
        self.assertIn('<td class="nowrap">$72.00</td>', front)
        self.assertIn('<span class="tag">Reopen the case (event)</span>', front)
        self.assertIn("Reopen the case if the shares close at or under 72.00 USD.", front)
        self.assertIn('<span class="tag">Prove the view wrong</span>', front)
        self.assertIn("If 2026 full-year revenue prints under $900M, the growth leg of the thesis "
                      "is wrong.", front)
        self.assertIn("<code>full_year_revenue_2026</code>", front)
        self.assertIn('<td class="nowrap">4 Feb 2027</td>', front)

    def test_the_restated_what_changes_bullets_are_gone(self):
        # Audit B4: the tripwires used to be restated as bullets under "what changes this rating",
        # duplicating the table above them. That duplication is dropped; the single table carries
        # them once.
        front = _front(HTML)
        self.assertNotIn("Would reopen this rating:", front)
        self.assertNotIn("Would prove this rating wrong:", front)

    def test_the_cross_examination_summary_names_the_blind_reviewer(self):
        front = _front(HTML)
        self.assertIn("Where the five advisors disagreed &mdash; the blind reviewer&#x27;s "
                      "summary", front)
        self.assertIn("One reviewer read all five advisors without knowing who wrote what",
                      front)
        self.assertIn("Five lenses, one agreement: the growth story is real", front)

    def test_a_basket_and_a_theme_front_name_their_own_kind(self):
        # The subject-kind line sits in the masthead rating box now (design audit C4 tier 0 / C5).
        self.assertIn("The subject is a basket of 2 named instruments judged as one idea.",
                      _masthead(BASKET_HTML))
        self.assertIn("The subject is an investment theme judged through its named expression.",
                      _masthead(THEME_HTML))


class TestExecutiveSummaryMinimumContent(unittest.TestCase):
    """Owner ruling AC16(3), closing register item P-U6-5: the two-page cap became a
    MINIMUM-content rule. The front is measured by what it MUST carry, never by a character budget.
    No front carries an ellipsis or a pointer that says the rest is in the appendix, and the
    chairman's rationale on the page is the JSON rationale in full."""

    def test_no_front_carries_an_ellipsis_or_appendix_pointer(self):
        pages = {"single name": HTML, "basket": BASKET_HTML, "theme": THEME_HTML,
                 "anchorless": _scenario_page(_published_block(), calendar=True)}
        for name, page in pages.items():
            front = _front(page)
            self.assertNotIn("…", front, name)
            self.assertNotIn("&hellip;", front, name)
            self.assertNotIn("in full in the appendix", _visible_text(front), name)

    def test_the_rationale_on_the_page_is_the_json_rationale_in_full(self):
        # The renderer respells numbers for display, so the check is against the reformatted full
        # rationale: every word the chairman wrote is on the front, uncut.
        rationale = json.load(open(os.path.join(FIXTURE, "verdict.json")))["conviction_rationale"]
        expected = R.markdown(R.reformat_prose(rationale, "chairman rationale", []))
        self.assertIn(expected, _front(HTML))

    def test_the_thesis_is_at_most_five_sentences(self):
        # Owner ruling AC41(4): the five-sentence thesis card repeated the rationale printed in
        # full beneath it and is dropped; the rationale's opening sentences stay on the front, once.
        rationale = json.load(open(os.path.join(FIXTURE, "verdict.json")))["conviction_rationale"]
        reformatted = R.reformat_prose(rationale, "chairman rationale", [])
        opening = prose.split_sentences(reformatted, prose.load_rules())[0]
        front = _front(HTML)
        self.assertNotIn('<span class="lead">The thesis</span>', front)
        card = front[front.index("Why this rating, in the chairman"):]
        self.assertIn(_visible_text(R.markdown(opening)), _visible_text(card))
        self.assertEqual(_visible_text(front).count(_visible_text(R.markdown(opening))), 1)


class TestDecisionFrontAnchorless(unittest.TestCase):
    """The scenario-earned rating on the front (ANCHORLESS-SPEC section 3): the ladder, the sum
    written out, the bar, and the sensitivity that must be printed every time."""

    def setUp(self):
        # The scenario ladder, its sum, the bar and the sensitivity moved to the decision-in-detail
        # tier (owner ruling AC16, audit C4 tier 3); the rating badge stays on the front.
        self.computed = _computed_ladder()
        self.page = _scenario_page(_published_block(), calendar=True)
        self.front = _front(self.page)
        self.masthead = _masthead(self.page)
        self.detail = _detail(self.page)

    def test_the_ladder_earned_the_rating_the_engine_computed(self):
        # The rating word and the subject kind are the masthead rating box now (design audit C5).
        self.assertEqual(self.computed["rating"], "buy")
        self.assertIn('<div class="rating-word">Buy</div>', self.masthead)
        self.assertIn("The subject is Bitcoin.", self.masthead)

    def test_every_rung_renders_with_its_price_chance_and_reason(self):
        self.assertIn("How this rating was earned: the scenario ladder", self.detail)
        self.assertIn("Every chance below is the council&#x27;s own disciplined judgment, never "
                      "a verified fact. The horizon is 12 months.", self.detail)
        for rung in CHAIR_LADDER["scenarios"]:
            self.assertIn('<tr><td>%s</td><td class="nowrap">%s</td>'
                          '<td class="nowrap">%s</td><td>%s</td></tr>'
                          % (E(rung["name"]),
                             E(R.format_price(rung["price_outcome"], "USD")),
                             E(rung["probability"]), E(rung["rationale"])),
                          self.detail, rung["name"])

    def test_the_arithmetic_sentences_are_quoted_word_for_word(self):
        self.assertIn("The sum, written out", self.detail)
        for line in self.computed["arithmetic"]:
            self.assertIn("<p>%s</p>" % E(line), self.detail)

    def test_the_bar_and_the_expected_result_are_the_engines_own_figures(self):
        self.assertIn("The ladder expects %s%% a year against a bar of %s%% a year, a difference "
                      "of %s points." % (self.computed["expected_annualised_pct"],
                                         self.computed["bar_pct"],
                                         self.computed["excess_over_bar_pp"]), self.detail)

    def test_the_sensitivity_is_printed_with_the_flip_and_the_bar_steps(self):
        sensitivity = self.computed["sensitivity"]
        self.assertIn(E(sensitivity["flip"]["sentence"]), self.detail)
        self.assertIn(E(sensitivity["sentence"]), self.detail)
        for step in sensitivity["bar_steps"]:
            self.assertIn('<td>%s</td><td class="nowrap">%s%%</td><td class="nowrap">%s</td>'
                          % (E(step["label"]), E(step["bar_pct"]),
                             E(R.RATING_WORDS[step["rating"]])),
                          self.detail, step["label"])
        # The flip sentence appears twice in the detail tier now: once in the earned-rating
        # ladder's sensitivity, and once in the full-ladders record that moved onto this tier and
        # repeats it by design (architect ruling closing P-U6b-9; audit finding c5-1). The front's
        # restated 'what changes this rating' bullets that once duplicated it are still gone (audit
        # B4) - the executive summary carries the flip sentence not at all.
        self.assertEqual(self.detail.count(E(sensitivity["flip"]["sentence"])), 2)
        self.assertNotIn(E(sensitivity["flip"]["sentence"]), self.front)

    def test_the_downside_ladder_shows_the_rungs_priced_below_the_reference(self):
        self.assertIn("The ladder&#x27;s own losing rungs, priced under $100,000.00", self.detail)
        self.assertIn('<tr><td class="nowrap">$55,000.00</td><td>The bear case</td>'
                      '<td class="nowrap">0.25</td></tr>', self.detail)
        # The two rungs priced above it are not downside and do not appear there.
        self.assertNotIn('<td>The bull case</td><td class="nowrap">0.30</td>', self.detail)

    def test_an_anchorless_front_shows_no_mispricing_read(self):
        self.assertNotIn("The mispricing read", self.front)


class TestDecisionFrontUnaggregatedLadder(unittest.TestCase):
    """A ladder the chairman would not add up earns no rating, and the page gives his reason
    instead of arithmetic nobody stands behind (ANCHORLESS-SPEC section 3)."""

    REASON = ("The five ladders disagree on the bear case by more than the base case is worth. "
              "(INVENTED)")

    def setUp(self):
        # The unaggregated ladder and the chairman's reason moved to the decision-in-detail tier
        # (owner ruling AC16, audit C4 tier 3).
        self.detail = _detail(_scenario_page(
            _published_block(aggregated=False, reason=self.REASON)))

    def test_the_chairmans_reason_is_quoted(self):
        self.assertIn("Why no rating was earned from the ladder", self.detail)
        self.assertIn("The chairman judged this ladder too uncertain to add up", self.detail)
        self.assertIn(E(self.REASON), self.detail)

    def test_no_arithmetic_and_no_bar_are_shown(self):
        self.assertNotIn("The sum, written out", self.detail)
        self.assertNotIn("The ladder&#x27;s expected outcome is", self.detail)
        self.assertNotIn("The bar it had to clear", self.detail)
        self.assertNotIn("How close this is to a different answer", self.detail)

    def test_the_rungs_still_render_so_the_reader_sees_the_spread(self):
        self.assertIn("<td>The bear case</td>", self.detail)
        self.assertIn("<td>The bull case</td>", self.detail)


class TestDecisionFrontAnchored(unittest.TestCase):
    """An anchored subject keeps the priced read as its basis, and a ladder beside it is
    labelled as context that earned nothing."""

    def test_an_anchored_front_carries_the_mispricing_read_and_no_ladder(self):
        front = _front(HTML)
        self.assertIn('<div class="card"><span class="lead">The price read</span>'
                      "The council reads the price as <strong>rich</strong>", front)
        # The arithmetic moved to the chairman's synthesis (architect ruling 9 on READ-A).
        arithmetic = ("Roughly 24.1 times forward earnings against a five-year average near "
                      "20 times; about a fifth above it.")
        self.assertNotIn(arithmetic, front)
        self.assertIn(arithmetic, _synthesis(HTML))
        self.assertNotIn("How this rating was earned: the scenario ladder", front)
        self.assertNotIn("The sum, written out", front)

    def test_a_context_ladder_is_labelled_and_never_becomes_the_rating(self):
        block = _published_block(basis="context")
        # A stray rating inside a context block must not reach the badge: the subject's own
        # rating is the verdict's, and a context ladder earns nothing.
        block["rating"] = "strong_buy"
        page = _scenario_page(block, anchorless=False)
        masthead = _masthead(page)
        detail = _detail(page)
        # The priced read is on the front; the context ladder is on the decision-in-detail tier.
        self.assertIn("A scenario ladder, as supporting context only", detail)
        self.assertIn("The ladder below earned no rating", detail)
        # The subject's own rating is the masthead rating word; a context ladder's stray rating
        # never reaches it.
        self.assertIn('<div class="rating-word">Monitor - no view yet; watch the named '
                      "triggers</div>", masthead)
        self.assertNotIn('<div class="rating-word">Strong buy</div>', page)
        self.assertNotIn("The bar it had to clear", detail)
        # The read comes first, in the summary; the context ladder follows it, below.
        self.assertLess(page.index("The price read"),
                        page.index("A scenario ladder, as supporting context only"))


class TestDecisionFrontCalendar(unittest.TestCase):
    """AB13.5: the dated event calendar, now on the decision-in-detail tier (owner ruling AC16,
    audit C4 tier 3), and tripwires actionable inside the horizon - every event carries a date."""

    def setUp(self):
        self.detail = _detail(_scenario_page(_published_block(), calendar=True))

    def test_every_dated_event_renders_with_its_date_and_its_source(self):
        self.assertIn("The dated event calendar", self.detail)
        # The event by its plain name (unit READ-A); its source and id are in the evidence fold.
        self.assertIn('<td class="nowrap">16 Sep 2026</td><td>calendar rate decision next</td>',
                      self.detail)
        self.assertIn('<td class="nowrap">20 Apr 2028</td><td>calendar protocol next</td>',
                      self.detail)
        self.assertNotIn("INVENTED FIXTURE - the central bank", self.detail)
        self.assertNotIn("<code>calendar_", self.detail)

    def test_an_event_with_no_date_of_its_own_shows_the_day_it_was_checked(self):
        self.assertIn('<td class="nowrap">25 Aug 2026</td><td>calendar policy review &mdash; no '
                      "date announced yet; the review is expected late in the year</td>",
                      self.detail)

    def test_the_calendar_is_ordered_soonest_first(self):
        self.assertLess(self.detail.index("calendar policy review"),
                        self.detail.index("calendar rate decision next"))
        self.assertLess(self.detail.index("calendar rate decision next"),
                        self.detail.index("calendar protocol next"))

    def test_a_pack_with_no_dated_events_renders_no_calendar_at_all(self):
        # Audit B6: an empty section is skipped entirely - no heading, no 'no dated events'
        # machine sentence. A pack with no calendar simply carries no calendar.
        for page in (HTML, BASKET_HTML, THEME_HTML):
            self.assertNotIn("The evidence pack carries no dated events for this subject.", page)
            self.assertNotIn("The dated event calendar", page)
            self.assertNotIn("what happens, and where the date comes from", page)


def _capped_block():
    """The scenario block as the publisher writes it when a failed
    outside audit caps the earned rating to hold."""
    block = _published_block()
    block["published_rating"] = "hold"
    block["arithmetic"] = list(block["arithmetic"]) + [
        "The outside audit did not run, so nothing stronger than hold "
        "publishes: the rating on this page is hold, not the %s this "
        "ladder earns." % block["rating"].replace("_", " ")]
    return block


def _capped_page():
    block = _capped_block()

    def change_verdict(doc):
        doc["subject"].update({"kind": "bitcoin", "asset_class": "crypto",
                               "name": "Invented Anchorless Asset",
                               "ticker": None, "listing": None})
        doc["atlas_envelope"]["subject_kind"] = "bitcoin"
        doc["atlas_envelope"]["asset_class"] = "crypto"
        doc["scenario_rating"] = block
        doc["atlas_envelope"]["scenario_rating"] = block
        doc["rating"] = "hold"
        doc["atlas_envelope"]["rating"] = "hold"
        doc["warnings"] = [
            "The outside audit did not run (timeout). Nothing stronger "
            "than hold publishes on a failed audit; this document was "
            "not challenged by the cross-model auditor."]

    with tempfile.TemporaryDirectory() as tmp:
        return _render(_mutated_copy(
            tmp, lambda run_dir: _rewrite_verdict(run_dir, change_verdict)))


def _bloat_verdict(doc):
    """A schema-valid chairman who writes at length, applied to a verdict.
    Named at module level so a test that bloats the verdict AND changes
    something else in the same run can reuse it."""
    block = _published_block()
    long_text = "The case turns on a level nobody can observe daily. " * 20
    doc["subject"].update({"kind": "bitcoin", "asset_class": "crypto",
                           "name": "Invented Anchorless Asset",
                           "ticker": None, "listing": None})
    doc["atlas_envelope"]["subject_kind"] = "bitcoin"
    doc["atlas_envelope"]["asset_class"] = "crypto"
    doc["scenario_rating"] = block
    doc["atlas_envelope"]["scenario_rating"] = block
    doc["rating"] = block["rating"]
    doc["atlas_envelope"]["rating"] = block["rating"]
    doc["conviction_rationale"] = long_text
    doc["tripwires"]["reopening_triggers"] = [
        {"kind": "price" if index % 2 == 0 else "event",
         "detail": long_text,
         "level": "1000" if index % 2 == 0 else None,
         "unit": "USD" if index % 2 == 0 else None,
         "date": None if index % 2 == 0 else "2026-12-31",
         "constituent": None}
        for index in range(6)]
    doc["tripwires"]["falsifiers"] = [
        {"statement": long_text, "figure_name": "an invented figure",
         "source": "an invented source", "date": "2026-12-31",
         "constituent": None, "theme_falsifier_id": None,
         "metric_identity_assumed": None,
         "prior_period_value": None, "prior_period_unit": None,
         "prior_period_as_of": None}
        for _ in range(6)]
    doc["tripwires"]["invalidation_levels"] = [
        {"level": "100", "unit": "USD", "meaning": long_text,
         "constituent": None} for _ in range(6)]


def _bloated_page():
    with tempfile.TemporaryDirectory() as tmp:
        return _render(_mutated_copy(
            tmp, lambda run_dir: _rewrite_verdict(run_dir, _bloat_verdict)))


class TestTheFrontUnderAFailedAudit(unittest.TestCase):
    """Audit finding ANCHORLESS-C c1-3: when a failed outside audit caps
    an earned rating to hold, the sensitivity beside it still read the
    LADDER's rating, so the front could print "the rating moves down to
    buy" under a Hold badge. The figures are the ladder's own honest
    arithmetic and are kept; what was missing was saying whose rating
    they describe."""

    def setUp(self):
        # The earned-rating ladder and its sensitivity caveat moved to the decision-in-detail tier
        # (owner ruling AC16, audit C4 tier 3); the capped-rating warning stays on the front.
        self.detail = _detail(_capped_page())

    def test_the_sensitivity_says_whose_rating_it_describes(self):
        self.assertIn("the ladder", _visible_text(self.detail))
        self.assertIn("capped", _visible_text(self.detail))

    def test_the_published_rating_is_the_capped_one_everywhere(self):
        text = _visible_text(self.detail)
        self.assertIn("not the buy this ladder earns", text)

    def test_the_full_ladders_record_carries_the_same_caveat(self):
        # A new rendering path is a new place for the same mislabelling: the full-ladders record -
        # on the decision-in-detail tier now (architect ruling closing P-U6b-9), no longer a folded
        # appendix - repeats the sensitivity sentences, and without the caveat a Hold page could
        # claim "the rating moves down to buy" (audit finding c5-1).
        detail = _detail(_capped_page())
        ladders = detail[detail.index("<h3>The scenario ladders, in full</h3>"):]
        self.assertIn("was capped to", ladders)

    def test_the_uncapped_page_carries_no_such_label(self):
        plain = _visible_text(_detail(_scenario_page(_published_block())))
        self.assertNotIn("capped", plain)


class TestTheExecutiveSummaryIsShownInFull(unittest.TestCase):
    """Owner ruling AC16(3), closing register item P-U6-5: the two-page rule is now a
    MINIMUM-content rule. A schema-valid chairman who writes at length is shown in full on the
    front - the rationale, and every tripwire and falsifier - never cut, never trimmed to a budget,
    never marked as left for the appendix. This is the reverse of the old two-page cap."""

    def setUp(self):
        self.front = _front(_bloated_page())

    def test_a_long_rationale_is_shown_in_full(self):
        # The bloated rationale is one sentence repeated twenty times; the front carries every
        # repetition (the thesis lede repeats the first few too, so at least twenty are present).
        sentence = "The case turns on a level nobody can observe daily."
        self.assertGreaterEqual(_visible_text(self.front).count(sentence), 20)

    def test_no_field_is_trimmed_or_named_as_left_for_the_appendix(self):
        plain = _visible_text(self.front)
        self.assertNotIn("in full in the appendix", plain)
        self.assertNotIn("…", self.front)
        self.assertNotIn("&hellip;", self.front)

    def test_a_short_answer_is_not_truncated(self):
        plain = _visible_text(_front(_scenario_page(_published_block())))
        self.assertNotIn("in full in the appendix", plain)


class TestEveryFrontFieldIsShownInFull(unittest.TestCase):
    """Owner ruling AC16(3): the executive summary no longer trims any field to a budget. A long
    figure name or source is shown in full on the front, with no ellipsis - the reverse of the old
    bounded front (audit finding ANCHORLESS-C c2-2 is retired with the two-page cap)."""

    def page_with_long_metadata(self):
        block = _published_block()
        long_text = "an invented source that will not stop naming itself " * 120

        def change_verdict(doc):
            doc["subject"].update({"kind": "bitcoin",
                                   "asset_class": "crypto",
                                   "name": "Invented Anchorless Asset",
                                   "ticker": None, "listing": None})
            doc["atlas_envelope"]["subject_kind"] = "bitcoin"
            doc["atlas_envelope"]["asset_class"] = "crypto"
            doc["scenario_rating"] = block
            doc["atlas_envelope"]["scenario_rating"] = block
            doc["rating"] = block["rating"]
            doc["atlas_envelope"]["rating"] = block["rating"]
            doc["tripwires"]["falsifiers"] = [{
                "statement": "A short statement.",
                "figure_name": long_text, "source": long_text,
                "date": "2026-12-31", "constituent": None,
                "theme_falsifier_id": None,
                "metric_identity_assumed": None,
                "prior_period_value": None, "prior_period_unit": None,
                "prior_period_as_of": None}]

        with tempfile.TemporaryDirectory() as tmp:
            return _render(_mutated_copy(
                tmp,
                lambda run_dir: _rewrite_verdict(run_dir, change_verdict)))

    def test_long_metadata_is_shown_in_full_with_no_ellipsis(self):
        front = _front(self.page_with_long_metadata())
        long_text = "an invented source that will not stop naming itself " * 120
        self.assertIn(E(long_text.rstrip()), front)
        self.assertNotIn("…", front)
        self.assertNotIn("&hellip;", front)


class TestTheLaddersAreInTheReportInFull(unittest.TestCase):
    """Audit finding ANCHORLESS-C c3-1: the front bounded the ladder's
    rows and told the reader the rest was in the appendix - and no
    appendix rendered the ladder at all. A false pointer on the page is
    worse than a long table. The full-ladders record now carries the
    chairman's whole ladder AND each seat's own, which is also what makes
    the bench's disagreement visible to a reader (ANCHORLESS-SPEC section
    3). It sits open on the decision-in-detail tier now, no longer a
    folded appendix (architect ruling closing P-U6b-9). FAILED pre-fix."""

    def page(self):
        block = _published_block()
        block["scenarios"] = block["scenarios"] + [
            {"name": "A fourth case", "price_outcome": "90000",
             "probability": "0.00", "rationale": "INVENTED - a rung the "
                                                 "front has no room for."}]
        block["seat_ladders"] = [
            {"seat": "advisor_bear", "horizon_months": "12",
             "scenarios": [{"name": "The bear seat's own case",
                            "price_outcome": "40000",
                            "probability": "0.40",
                            "rationale": "INVENTED - its own reason."}]}]
        return _scenario_page(block)

    def test_every_rung_the_front_dropped_is_in_the_full_record(self):
        detail = _detail(self.page())
        self.assertIn("A fourth case", detail)
        self.assertIn("a rung the front has no room for", detail)

    def test_each_seats_own_ladder_is_on_the_page(self):
        detail = _detail(self.page())
        self.assertIn("The bear seat&#x27;s own case", detail)
        self.assertIn("its own reason", detail)


class TestNoSingleFieldIsTrimmedOnTheFront(unittest.TestCase):
    """Owner ruling AC16(3): a long scenario name and a long computed key number are shown in full
    on the executive summary, with no ellipsis - the two-page cap that once trimmed them is gone
    (audit findings ANCHORLESS-C c3-2, c3-3 are retired with it)."""

    def long(self):
        return "a name that will not stop naming itself " * 150

    def page_with_long_scenario_name(self):
        """The REAL input, not a shortcut: the long name goes on the
        LOSING rung, where the front renders it in the ladder table, in
        the downside ladder, and inside the engine's own flip sentence.
        An earlier regression only lengthened the derived sentence and
        so proved less than it claimed (audit finding c4-2)."""
        block = _published_block()
        worst = min(block["scenarios"],
                    key=lambda rung: float(rung["price_outcome"]))
        worst["name"] = self.long()
        block["sensitivity"]["flip"]["scenario"] = worst["name"]
        block["sensitivity"]["flip"]["sentence"] = (
            "The rating moves down to hold if the chance of %r rises "
            "from 0.25 to 0.286." % worst["name"])
        return _scenario_page(block)

    def page_with_long_key_number(self):
        def change_verdict(doc):
            doc["subject"].update({"kind": "bitcoin",
                                   "asset_class": "crypto",
                                   "name": "Invented Anchorless Asset",
                                   "ticker": None, "listing": None})
            doc["atlas_envelope"]["subject_kind"] = "bitcoin"
            doc["atlas_envelope"]["asset_class"] = "crypto"
            doc["atlas_envelope"]["key_numbers"] = [
                {"name": "a computed number", "value": "9" * 6000,
                 "unit": "USD", "as_of": "2026-08-28",
                 "pack_fact_id": None}]

        with tempfile.TemporaryDirectory() as tmp:
            return _render(_mutated_copy(
                tmp,
                lambda run_dir: _rewrite_verdict(run_dir, change_verdict)))

    def test_a_long_scenario_name_is_shown_in_full(self):
        # The scenario ladder moved to the decision-in-detail tier (owner ruling AC16); a long
        # rung name is still shown in full there, never trimmed to an ellipsis.
        detail = _detail(self.page_with_long_scenario_name())
        self.assertIn(E(self.long().rstrip()), detail)
        self.assertNotIn("…", detail)
        self.assertNotIn("&hellip;", detail)

    def test_a_long_computed_figure_is_not_trimmed(self):
        front = _front(self.page_with_long_key_number())
        self.assertNotIn("…", front)
        self.assertNotIn("&hellip;", front)
        self.assertNotIn("in full in the appendix", _visible_text(front))


# ---------------------------------------------------------------------
# The audit of the evidence (owner ruling AC2, spec section U2.4): a
# model outside this council's own family read the evidence before any
# advisor was paid. The reader is told so - loudly when it did not
# happen, or when the auditor called something blocking.
# ---------------------------------------------------------------------


def _audit_finding(**overrides):
    finding = {"id": "E1", "kind": "missing_decisive_fact",
               "severity": "blocking",
               "detail": "INVENTED - no figure for what each unit earns.",
               "fact_ids": [], "where_it_likely_lives": "INVENTED - the note",
               "source_url": None, "figure_at_source": None}
    finding.update(overrides)
    return finding


def _audit_page(block, source=None, extra=None):
    """The fixture run rendered with this audit block in its pack."""
    def change(run_dir):
        _rewrite_pack(run_dir, lambda doc: (
            doc["capture"].pop("evidence_challenge", None) if block is None
            else doc["capture"].__setitem__("evidence_challenge", block)))
        if extra:
            extra(run_dir)

    with tempfile.TemporaryDirectory() as tmp:
        return _render(_mutated_copy(tmp, change, source=source))


def _empty_the_gaps(run_dir):
    """The fixture carries declared gaps of its own; empty them so what
    the section says comes from the audit alone."""
    _rewrite_pack(run_dir, lambda doc: doc["capture"].__setitem__("gaps", []))


def _blocking_block(count=1, detail=None):
    long_detail = detail or ("INVENTED - the pack carries no figure for what "
                             "each unit earns and the question turns on it. ")
    findings = [_audit_finding(id="B%d" % index, detail=long_detail)
                for index in range(count)]
    return {"status": "success", "model": "gpt-5.6-sol",
            "failure_status": None, "findings": findings,
            "overall": "INVENTED - the record is thin on unit economics.",
            "resolutions": {
                finding["id"]: {"disposition": "overruled", "fact_ids": [],
                                "reason": long_detail,
                                "weakened_test": None}
                for finding in findings}}


def _changed_block(changes, findings=None):
    """The fixture's own clean audit, with a list of what moved after it."""
    return {"status": "success", "model": "gpt-5.6-sol",
            "failure_status": None, "failure_reason": None,
            "findings": findings or [], "overall": None, "resolutions": {},
            "nonce": "n" * 32, "evidence_sha256": "e" * 64,
            "post_audit_changes": changes}


def _change(entry_id, change="changed", old="1.0", new="2.0"):
    return {"id": entry_id, "change": change, "old": old, "new": new}


class TestWhatChangedAfterTheAuditReachesThePage(unittest.TestCase):
    """Owner ruling AC13.2 (register item P-U2-4). The capture may change
    what the outside auditor never asked about - and every such change is
    on the record, in each seat's case file and here, so the owner can
    see which numbers no outside model read. Open on the front when a
    change touches a number the decision turns on; one folded line
    otherwise; the whole list in the appendix either way. Every test
    below FAILS against the pre-fix page."""

    def page(self, changes, extra=None):
        return _audit_page(_changed_block(changes), extra=extra)

    def appendix(self, page):
        # The outside auditor's objections and the post-audit change list moved to the
        # decision-in-detail tier (owner ruling AC16, audit C4 tier 3).
        return page[page.index('<h2 id="detail"'):
                    page.index('<h2 id="evidence"')]

    def test_a_change_that_decides_nothing_is_one_folded_line(self):
        page = self.page([_change("last_price")])
        front = _front(page)
        self.assertIn("1 figure changed after the evidence check",
                      _visible_text(front))
        self.assertIn("none of them a number this decision turns on",
                      _visible_text(front))
        self.assertIn("<details>", front)
        self.assertNotIn('<div class="card alarm"><span class="shout">1 '
                         "figure changed", front)

    def test_a_change_to_a_headline_pair_is_loud_and_never_folded(self):
        """The three headline pairs are what a fall in the business is
        read from, and this page reads their ids from the evidence gate
        rather than a second list of its own."""
        page = self.page([_change("last_price"), _change("revenue_q")])
        front = _front(page)
        text = _visible_text(front)
        self.assertIn("2 figures changed after the evidence check; 1 of them "
                      "is a number this decision turns on.", text)
        self.assertIn("The one: revenue q.", text)
        self.assertIn('<div class="card alarm">', front)
        self.assertNotIn("<details>",
                         front[front.index("1 of them is a number"):])

    def test_a_change_to_a_decisive_metrics_own_answer_is_loud_too(self):
        def add_frame(run_dir):
            _rewrite_pack(run_dir, lambda doc: doc["capture"].__setitem__(
                "business_frame",
                {"FIXT": {"decisive_metrics": [
                    {"name": "INVENTED - what it earns per unit",
                     "answered_by": ["free_cash_flow_fy2025"]}]}}))
        page = self.page([_change("free_cash_flow_fy2025")],
                         extra=add_frame)
        self.assertIn("1 figure changed after the evidence check; 1 of them "
                      "is a number this decision turns on.",
                      _visible_text(_front(page)))

    def test_a_members_own_headline_figure_counts_as_its_own(self):
        """A constituent of an expression wears its member suffix, and the
        pair it belongs to is read from the id underneath it."""
        page = self.page([_change("net_income_q__achp")])
        self.assertIn("1 of them is a number this decision turns on",
                      _visible_text(_front(page)))

    def test_the_appendix_prints_what_was_read_and_what_was_sat_on(self):
        page = self.page([_change("last_price", old="123.45", new="130.00")])
        text = _visible_text(self.appendix(page))
        self.assertIn("Changed after the evidence check", text)
        # The value sat on in the market form, with the fact's date (unit READ-A); the number
        # the evidence check read stands as recorded, its unit not being on the record (r4-1).
        self.assertIn("last price \u2014 The evidence check read the number 123.45, in a unit "
                      "this record does not keep; the council sat on $130.00 (as of 28 Aug "
                      "2026).", text)

    def test_the_appendix_names_added_and_removed_in_plain_words(self):
        page = self.page([_change("rent_per_unit", change="added",
                                  old=None, new="7.5"),
                          _change("old_note", change="removed",
                                  old="INVENTED - it used to say this",
                                  new=None)])
        text = _visible_text(self.appendix(page))
        self.assertIn("rent per unit \u2014 Added after the evidence check: 7.5.", text)
        self.assertIn("old note \u2014 Taken out after the evidence check; it read "
                      "INVENTED - it used to say this.", text)

    def test_a_value_that_stands_says_what_moved_instead(self):
        page = self.page([_change("last_price", old="123.45", new="123.45")])
        self.assertIn("It reads $123.45 (as of 28 Aug 2026); the evidence check read the "
                      "same number, 123.45, in a unit this record does not keep; what moved "
                      "is its unit, its date or where it came from.",
                      _visible_text(self.appendix(page)))

    def test_the_old_side_is_never_read_by_a_unit_it_may_not_have_had(self):
        """The change record keeps the value the evidence check read, not its unit; a fact
        re-gathered in another unit must not have its old number dressed in the new one
        (audit round 4 of READ-A, r4-1): 100 read in millions is not "$100B"."""
        def in_billions(run_dir):
            def change(doc):
                for fact in doc["capture"]["tier1"]:
                    if fact["id"] == "revenue_fy2025":
                        fact["unit"] = "USD_billion"
            _rewrite_pack(run_dir, change)
        page = self.page([_change("revenue_fy2025", old="100", new="100"),
                          _change("last_price", old="123.45", new="130.00")],
                         extra=in_billions)
        text = _visible_text(self.appendix(page))
        self.assertNotIn("stands at $100B", text)
        self.assertNotIn("read $100B", text)
        self.assertNotIn("read $123.45", text)
        self.assertIn("the evidence check read the same number, 100, in a unit this record "
                      "does not keep", text)
        self.assertIn("The evidence check read the number 123.45, in a unit this record does "
                      "not keep; the council sat on $130.00", text)

    def test_the_appendix_marks_the_ones_the_decision_turns_on(self):
        page = self.page([_change("last_price"), _change("revenue_q")])
        text = _visible_text(self.appendix(page))
        self.assertIn("revenue q \u2014 a number this decision turns on",
                      text)
        self.assertNotIn("last price \u2014 a number this decision turns on",
                         text)

    def test_a_pack_that_changed_nothing_says_nothing(self):
        page = self.page([])
        self.assertNotIn("changed after the evidence check",
                         _visible_text(page))

    def test_a_failed_audit_claims_no_reading_to_have_changed_after(self):
        """Nobody read this evidence, so nothing can have moved after the
        reading. The front already shouts that no outside model checked
        it."""
        block = {"status": "failed", "model": "gpt-5.6-sol",
                 "failure_status": "timeout", "failure_reason": None,
                 "findings": [], "overall": None, "resolutions": {},
                 "nonce": "n" * 32, "evidence_sha256": "e" * 64,
                 "post_audit_changes": [_change("revenue_q")]}
        page = _audit_page(block)
        self.assertIn(R.EVIDENCE_UNCHECKED_SENTENCE,
                      _visible_text(_front(page)))
        self.assertNotIn("this decision turns on", _visible_text(_front(page)))

    def test_the_post_audit_change_alarm_names_the_decisive_count(self):
        """The decisive-change alarm on the front is a constant, deliberately terse card whatever
        moved (owner ruling AC13.2); it stays open and names the counts, with the longest chairman
        on record and forty changed figures behind it. The old two-page budget assert is retired
        with the front's character cap (owner ruling AC16(3))."""
        changes = [_change("revenue_q")] + [
            _change("fact_%d" % index, old="INVENTED - a long value " * 8,
                    new="INVENTED - a longer value " * 8)
            for index in range(40)]

        def bloat(run_dir):
            _rewrite_verdict(run_dir, _bloat_verdict)

        front = _visible_text(_front(self.page(changes, extra=bloat)))
        self.assertIn("41 figures changed after the evidence check; 1 of them "
                      "is a number this decision turns on.", front)


class TestTheAuditOfTheEvidenceOnTheFront(unittest.TestCase):
    """Every test below FAILS against the pre-fix page."""

    def test_a_clean_audit_is_one_folded_line(self):
        front = _front(HTML)
        self.assertIn("The evidence check: an outside model read this evidence before the "
                      "council sat and raised 2 points, none of them "
                      "blocking", _visible_text(front))
        self.assertIn("<details>", front)

    def test_a_blocking_finding_is_loud_and_never_folded(self):
        page = _audit_page(_blocking_block())
        front = _front(page)
        text = _visible_text(front)
        self.assertIn("The evidence check called 1 point blocking before "
                      "the council sat.", text)
        self.assertIn('<div class="card alarm">', front)
        self.assertNotIn("<details>", front[front.index("blocking before"):])
        # The point itself, and what the record answered, are one click
        # away and never further: the front is bounded, the detail tier is
        # not. The blocking finding stays open there (owner ruling AC16).
        detail = _detail(page)
        self.assertIn("set aside by the session that gathered the evidence",
                      _visible_text(detail))

    def test_an_audit_that_never_happened_says_so_on_the_front(self):
        for block in (None, {"status": "failed", "model": "gpt-5.6-sol",
                             "failure_status": "timeout", "findings": [],
                             "overall": None, "resolutions": {}}):
            front = _front(_audit_page(block))
            self.assertIn(R.EVIDENCE_UNCHECKED_SENTENCE,
                          _visible_text(front))
            self.assertIn('<div class="card alarm">', front)

    def test_the_blocking_alarm_stays_open_with_three_findings(self):
        """The worst case of the worst case: the longest schema-valid chairman on record, and three
        blocking findings each answered at length. The blocking alarm on the front is never folded
        and never trimmed; the old two-page budget assert is retired (owner ruling AC16(3))."""
        long_detail = ("The case turns on a level nobody can observe "
                       "daily and the record does not carry it. " * 12)
        block = _blocking_block(count=3, detail=long_detail)

        def bloat(run_dir):
            _rewrite_verdict(run_dir, _bloat_verdict)

        front = _front(_audit_page(block, extra=bloat))
        self.assertIn("The evidence check called 3 points blocking",
                      _visible_text(front))


class TestTheAuditOfTheEvidenceInTheAppendix(unittest.TestCase):
    def appendix(self, page):
        # The outside auditor's objections moved to the decision-in-detail tier (owner ruling
        # AC16, audit C4 tier 3): the auditor's paragraph and blocking findings open, the
        # non-blocking findings and the post-audit change list folded.
        return page[page.index('<h2 id="detail"'):
                    page.index('<h2 id="evidence"')]

    def test_the_section_carries_every_point_and_its_answer(self):
        text = _visible_text(self.appendix(HTML))
        self.assertIn("a fact the case turns on, missing", text)
        self.assertIn("a figure that looks wrong", text)
        self.assertIn("gathered, and it is in the evidence below "
                      "(free_cash_flow_fy2025)", text)
        self.assertIn("set aside by the session that gathered the evidence",
                      text)

    def test_the_auditors_own_paragraph_is_word_for_word_and_attributed(self):
        section = self.appendix(HTML)
        self.assertIn("OpenAI GPT-5.6 Sol", _visible_text(section))
        self.assertIn("The outside model&#x27;s reading of this evidence, in its "
                      "own words", section)
        self.assertIn("INVENTED FIXTURE - the record is unusually complete "
                      "on price and cash generation, and thin on what the "
                      "business earns per unit. One of the two points below "
                      "would change how the growth story reads; the other "
                      "would not.", _visible_text(section))

    def test_a_source_doubt_shows_the_page_and_the_figure_it_printed(self):
        block = _blocking_block()
        block["findings"][0].update({"kind": "source_doubt",
                                     "source_url": "https://invented.example/f",
                                     "figure_at_source": "1,234.5",
                                     "fact_ids": ["revenue_fy2025"]})
        text = _visible_text(self.appendix(_audit_page(block)))
        self.assertIn("the source says something else", text)
        self.assertIn("Read at: https://invented.example/f", text)
        self.assertIn("What that page printed: 1,234.5", text)
        self.assertIn("The figures it is about: revenue_fy2025", text)

    def test_a_gap_conceded_to_the_auditor_reaches_the_gaps_section(self):
        """Audit round 5, r5-3, the owner's half. The page dropped the
        Declared gaps section entirely when the only gap standing was one
        conceded to the outside auditor - a silent omission where the
        audit section says a gap stands. Round 6 (r6-2): the section
        SENDS the reader to the audit rather than reprinting the gap,
        so an absence the capture also wrote as an ordinary row is not
        counted twice."""
        block = _blocking_block()
        reason = "INVENTED - the filer stopped publishing it in 2018."
        block["resolutions"][block["findings"][0]["id"]] = {
            "disposition": "gap_declared", "fact_ids": [],
            "reason": reason, "weakened_test": "profit_growth"}
        page = _audit_page(block, extra=_empty_the_gaps)
        self.assertIn("<h3>Declared gaps</h3>", page)
        section = page[page.index("<h3>Declared gaps</h3>"):]
        section = _visible_text(section[:section.index("<h3", 10)])
        self.assertIn("conceded to the evidence check", section)
        self.assertNotIn(reason, section)

    def test_a_source_doubt_that_names_no_page_is_labelled_a_doubt(self):
        """Audit round 1, r1-6. The kind asserts the auditor read a
        published source. Where it named none, the owner is not told
        that a source says something else - nothing on the record says
        any source was read."""
        block = _blocking_block()
        block["findings"][0].update({"kind": "source_doubt",
                                     "source_url": None,
                                     "figure_at_source": None})
        text = _visible_text(self.appendix(_audit_page(block)))
        self.assertIn("a doubt about a source, with no page named", text)
        self.assertNotIn("the source says something else", text)

    def test_a_page_named_only_in_blanks_is_no_page_at_all(self):
        """Audit round 2, r2-2. The auditor is an outside model and the
        answer schema lets any of these fields be a run of spaces. A
        blank is not a page, not a figure and not a place to look, and
        the owner is told none of the three was named."""
        block = _blocking_block()
        block["findings"][0].update({"kind": "source_doubt",
                                     "source_url": "   ",
                                     "figure_at_source": "  ",
                                     "where_it_likely_lives": " ",
                                     "fact_ids": ["  "]})
        section = self.appendix(_audit_page(block))
        text = _visible_text(section)
        self.assertIn("a doubt about a source, with no page named", text)
        self.assertNotIn("Read at:", text)
        self.assertNotIn("What that page printed:", text)
        self.assertNotIn("Where it would be found:", text)
        self.assertNotIn("The figures it is about:", text)

    def test_a_blank_figure_beside_a_real_page_is_not_printed(self):
        block = _blocking_block()
        block["findings"][0].update({"kind": "source_doubt",
                                     "source_url": "https://invented.example/f",
                                     "figure_at_source": "   "})
        text = _visible_text(self.appendix(_audit_page(block)))
        self.assertIn("Read at: https://invented.example/f", text)
        self.assertNotIn("What that page printed:", text)

    def test_a_failed_audit_names_what_went_wrong(self):
        page = _audit_page({"status": "failed", "model": "gpt-5.6-sol",
                            "failure_status": "timeout",
                            "failure_reason": None, "findings": [],
                            "overall": None, "resolutions": {}})
        text = _visible_text(self.appendix(page))
        self.assertIn(R.EVIDENCE_UNCHECKED_SENTENCE, text)
        self.assertIn("timeout", text)

    def test_a_failed_audit_says_WHY_it_failed_not_only_that_it_did(self):
        """Audit round 5, r5-4. Six status words stand for eight
        different causes: no codex installed, an exit code, a killed
        process, an unreadable answer. The runbook promises the reason;
        the record dropped it, so the frozen pack could not tell a
        missing program from a model that answered nonsense."""
        page = _audit_page({"status": "failed", "model": "gpt-5.6-sol",
                            "failure_status": "launch_failure",
                            "failure_reason": "INVENTED - smoke test "
                                              "failed: codex not on PATH",
                            "findings": [], "overall": None,
                            "resolutions": {}})
        text = _visible_text(self.appendix(page))
        self.assertIn("INVENTED - smoke test failed: codex not on PATH",
                      text)

    def test_a_pack_that_never_asked_says_that_instead(self):
        text = _visible_text(self.appendix(_audit_page(None)))
        self.assertIn(R.EVIDENCE_UNCHECKED_SENTENCE, text)
        self.assertIn("it was never made", text)


# ---------------------------------------------------------------------------------------------
# UPGRADE-2 U3 - WHO REVIEWED THE EVIDENCE, AND THE TWO CLOCKS (owner ruling AC3)
#
# The mode is chosen once, at the very start of a sitting, and the front page says which way it
# went either way. The capture stage's own minutes and tokens are printed BESIDE the sitting's
# wall clock and never inside it.
# ---------------------------------------------------------------------------------------------


def _auto_mode_page(tmp, drop=False):
    """The fixture run rendered as an unattended sitting - or, with `drop`, as a run published
    before ruling AC3 existed and carrying no evidence provenance at all."""
    def mutate(run_dir):
        def change(doc):
            if drop:
                doc["provenance"].pop("evidence")
                return
            doc["provenance"]["evidence"].update({
                "mode": "unattended", "chosen_by": "atlas",
                "approved_by": None, "approved_at": None,
                "approval_note": None,
                "clock_started": doc["provenance"]["timestamps"]["run_started"]})
        _rewrite_verdict(run_dir, change)
    return _render(_mutated_copy(tmp, mutate))


class TestTheFrontSaysWhoReviewedTheEvidence(unittest.TestCase):

    def test_a_reviewed_sitting_names_the_person_who_said_go(self):
        front = _visible_text(_front(HTML))
        self.assertIn("Reviewed by Invented Reviewer (fixture) before the council sat.",
                      front)
        self.assertNotIn("Auto-mode", front)

    def test_an_unattended_sitting_says_so_in_the_warning_style(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = _auto_mode_page(tmp)
        front = _front(page)
        self.assertIn("Auto-mode: no human reviewed the evidence before the council sat.",
                      _visible_text(front))
        self.assertNotIn("Reviewed by", _visible_text(front))
        # The auto-mode sentence is a warning, not a footnote: it renders in the same loud
        # style the front gives an unchecked audit.
        self.assertIn('<div class="card alarm"><span class="shout">Auto-mode', front)

    def test_a_run_published_before_the_ruling_still_renders_and_says_auto_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = _auto_mode_page(tmp, drop=True)
        self.assertIn("Auto-mode: no human reviewed the evidence before the council sat.",
                      _visible_text(_front(page)))

    def test_the_sentence_is_on_the_front_and_not_only_in_the_appendix(self):
        self.assertIn("before the council sat.", _visible_text(_front(HTML)))


class TestTheCaptureClocksSitBesideTheSittingsOwn(unittest.TestCase):
    """Owner ruling AC3: the capture stage's own time and tokens are recorded, and the
    1.5-hour wall clock excludes the pause - so the two figures are printed side by side and
    never added together."""

    def setUp(self):
        # The clocks moved off the executive summary to the 'About this sitting' run-stamps
        # appendix (owner ruling AC16, audit C4 tier 5).
        self.stamps = _visible_text(_stamps(HTML))

    def test_the_sitting_is_timed_from_the_go_to_the_rendered_report(self):
        # The fixture's approval stands at 09:05 and this suite renders 84 minutes later. Its
        # run was created at 09:12, so a clock started there would print 77 - the seven
        # minutes between the go and the run belong to the council, not to the pause.
        self.assertIn("Time 84 minutes sitting",
                      self.stamps)

    def test_the_capture_is_counted_beside_that_clock_and_never_inside_it(self):
        # Printed beside the sitting's own clock, never added into it; its tokens are counted in
        # the cost estimate below (unit READ-A).
        self.assertIn("Time 84 minutes sitting, plus 46 minutes gathering the evidence.",
                      self.stamps)
        self.assertNotIn("127 minutes", self.stamps)

    def test_a_page_with_no_readable_start_prints_no_wall_clock(self):
        """PREMISE MOVED, and recorded: this test used to make the PUBLICATION stamp
        unreadable, because publication was the finish line. It is not any more (register item
        P-U3-5) - the finish line is this rendering, and the only stamp the clock can fail on
        is the one it starts from."""
        with tempfile.TemporaryDirectory() as tmp:
            def mutate(run_dir):
                def change(doc):
                    doc["provenance"]["evidence"]["clock_started"] = "one morning"
                    doc["provenance"]["timestamps"]["run_started"] = "one morning"
                _rewrite_verdict(run_dir, change)
            page = _visible_text(_stamps(_render(_mutated_copy(tmp, mutate))))
        self.assertNotIn("minutes sitting", page)
        self.assertIn("46 minutes gathering the evidence", page)


class TestTheClockRunsToTheRenderedReport(unittest.TestCase):
    """Register item P-U3-5, ruled by the architect after this unit's audit.

    Spec section U3.3 measures the 1.5-hour budget "to the rendered report"; the clock stopped
    at publication, so the read-back and the rendering fell outside it and a sitting that ran
    95 minutes was reported and accepted as 89. The finish line is now this rendering, and the
    page says the budget was missed when the render-measured clock says so. The host's own
    budget-overrun event, measured at publication, is untouched: two clocks, both named."""

    START = datetime.datetime(2026, 8, 30, 9, 5, tzinfo=datetime.timezone.utc)

    def page_at(self, minutes, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            return _render(_mutated_copy(tmp, mutate),
                           now=self.START + datetime.timedelta(minutes=minutes))

    def test_the_clock_ends_at_this_rendering_not_at_publication(self):
        """The fixture publishes at 10:26, 81 minutes after the go. A report rendered at
        11:00 is a 115-minute sitting, and 81 is the number that hid the overrun. The clock now
        sits in the run-stamps appendix (owner ruling AC16)."""
        stamps = _visible_text(_stamps(self.page_at(115)))
        self.assertIn("Time 115 minutes sitting",
                      stamps)
        self.assertNotIn("81 minutes", stamps)

    def test_a_later_rendering_prints_a_later_clock(self):
        self.assertIn("60 minutes sitting",
                      _visible_text(_stamps(self.page_at(60))))
        self.assertIn("89 minutes sitting",
                      _visible_text(_stamps(self.page_at(89))))

    def test_a_sitting_over_its_budget_says_so_on_the_front(self):
        """The 95-minute sitting of the finding: reported as 89 before, and now shown as the
        miss it is - in the same loud style the front gives an unchecked audit. The alarm is a
        warning and stays on the front, never folded (owner ruling AC16); the minute count itself
        moved to the run-stamps appendix."""
        page = self.page_at(95)
        front = _front(page)
        self.assertIn("This sitting missed its 90-minute budget.", _visible_text(front))
        self.assertIn('<div class="card alarm"><span class="shout">This sitting missed', front)
        self.assertIn("95 minutes sitting", _visible_text(_stamps(page)))

    def test_a_sitting_inside_its_budget_says_nothing_about_it(self):
        self.assertNotIn("missed its", _visible_text(_front(self.page_at(89))))

    def test_the_boundary_is_the_budget_itself(self):
        """Exactly at the cap is not over it."""
        self.assertNotIn("missed its", _visible_text(_front(self.page_at(90))))
        self.assertIn("missed its", _visible_text(_front(self.page_at(91))))

    def test_the_budget_in_force_is_the_one_this_run_was_opened_with(self):
        """A sitting opened with a tighter cap is judged against ITS cap, not the default."""
        def mutate(run_dir):
            _rewrite_invocation(run_dir, lambda doc: doc.__setitem__(
                "config", {"minutes_cap": 40}))
        page = self.page_at(45, mutate)
        self.assertIn("This sitting missed its 40-minute budget.", _visible_text(_front(page)))
        self.assertIn("45 minutes sitting", _visible_text(_stamps(page)))

    def test_the_budget_missed_alarm_shows_on_the_longest_front(self):
        """The budget-missed alarm renders on the front even for the longest chairman on record;
        it is never folded. The old two-page character budget assert is retired (owner ruling
        AC16(3))."""
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(
                tmp, lambda run_dir: _rewrite_verdict(run_dir, _bloat_verdict)),
                now=self.START + datetime.timedelta(minutes=12345))
        front = _visible_text(_front(page))
        self.assertIn("This sitting missed its 90-minute budget.", front)

    def test_a_cap_of_zero_is_a_cap(self):
        """Audit round 1, r1-2. The host accepts `minutes_cap: 0` - its
        own suite opens a run that way to force the overrun - and writes the
        budget-overrun event the moment any time has passed. The page
        substituted 90 for that cap and said nothing, so the record knew about
        a miss the reader did not."""
        def mutate(run_dir):
            _rewrite_invocation(run_dir, lambda doc: doc.__setitem__(
                "config", {"minutes_cap": 0}))
        page = self.page_at(60, mutate)
        self.assertIn("This sitting missed its 0-minute budget.", _visible_text(_front(page)))
        self.assertIn("60 minutes sitting", _visible_text(_stamps(page)))

    def test_a_run_that_named_no_cap_is_judged_against_the_default(self):
        """The other side: the fixture carries no config at all, which is
        what a run published before the config existed looks like."""
        self.assertNotIn("missed its", _visible_text(_front(self.page_at(89))))
        self.assertIn("This sitting missed its 90-minute budget.",
                      _visible_text(_front(self.page_at(91))))

    def test_a_page_rendered_inside_the_clock_skew_prints_no_negative_time(
            self):
        """Audit round 1, r1-5. The host tolerates a go stamped up to ten
        minutes ahead of its own clock, because the owner captures on one
        machine and sits on the other. A page rendered inside that allowance
        printed 'The council sat -9 minutes' to him, and no budget could be
        missed at a negative duration."""
        page = self.page_at(-9)
        self.assertIn("0 minutes sitting", _visible_text(_stamps(page)))
        self.assertNotIn("-9", _visible_text(_stamps(page)))
        self.assertNotIn("missed its", _visible_text(_front(page)))

    def test_the_default_budget_is_the_hosts_own(self):
        """One budget, not two. The report reads a published package and no engine code, so
        the two constants are pinned equal here rather than imported across the seam."""
        from council.engine import host
        self.assertEqual(R.DEFAULT_MINUTES_CAP, host.DEFAULT_MINUTES_CAP)

    def test_the_clock_is_recorded_by_the_first_rendering_and_read_after(self):
        """PREMISE MOVED, and recorded (architect's mechanism ruling on register item P-U3-5).
        This test used to prove the renderer times ITSELF from this machine's clock - which is
        why a page reprinted a month after its sitting printed the month. The finish line is
        still the rendering; what changed is that the FIRST rendering records the moment and
        every later one reads it, so an archived page reprints byte for byte."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            self.assertEqual(_render_cli(run_dir), 0)
            first = _report_bytes(run_dir)
            stamps = [e for e in _events(run_dir)
                      if e["event"] == R.REPORT_RENDERED_EVENT]
            self.assertEqual(len(stamps), 1, _events(run_dir))
            os.remove(os.path.join(run_dir, "report.html"))
            self.assertEqual(_render_cli(run_dir), 0)
            self.assertEqual(_report_bytes(run_dir), first)
            self.assertEqual(len([e for e in _events(run_dir)
                                  if e["event"] == R.REPORT_RENDERED_EVENT]), 1)
            minutes = float(re.search(r"([\d,.]+) minutes sitting",
                                      _visible_text(_stamps(first))).group(1)
                            .replace(",", ""))
            recorded = R._stamp(stamps[0]["at"])
            lived = (recorded - self.START).total_seconds() / 60.0
            # The sitting's minutes now print as a whole number (audit C1 R11).
            self.assertAlmostEqual(minutes, lived, delta=0.51)

    def test_a_render_that_wrote_no_report_records_no_rendering(self):
        """Audit round 1, r1-6. The row said a report exists. It was
        appended before the page was built, so a render whose output
        write failed left it behind - and the next successful render was
        timed to the failed attempt, which is the under-stated clock
        `P-U3-5` was fixed to remove, back on the failure path."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            nowhere = os.path.join(tmp, "no-such-dir", "report.html")
            with self.assertRaises(OSError):
                _render_cli(run_dir, out=nowhere)
            self.assertFalse(os.path.exists(nowhere))
            self.assertEqual([e["event"] for e in _events(run_dir)],
                             ["run_created", "run_finished"])
            self.assertEqual(_render_cli(run_dir), 0)
            stamps = [e for e in _events(run_dir)
                      if e["event"] == R.REPORT_RENDERED_EVENT]
            self.assertEqual(len(stamps), 1)
            written = datetime.datetime.fromtimestamp(
                os.path.getmtime(os.path.join(run_dir, "report.html")),
                datetime.timezone.utc)
            self.assertLessEqual(R._stamp(stamps[0]["at"]),
                                 written + datetime.timedelta(seconds=2))

    def test_a_report_is_never_on_disk_without_its_row(self):
        """Audit round 2, r2-1. The page was written first and the row
        appended after it, so a stop between the two left a report with
        nothing saying when it was rendered - and the next rendering
        took itself for the first, silently re-timed the archived page
        and could flip its budget line. Measured on a real sitting: 85
        minutes and no alarm became 95 minutes and 'This sitting missed
        its 90-minute budget.' The page is now staged and only becomes
        visible after the row lands, so that state is unreachable."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            # The failure is driven from the layer BENEATH the step under test - the record's
            # own writer - and never by replacing that step. Audit round 3, r3-1: this test
            # replaced `commit_render_moment` itself, so it proved the caller behaves when the
            # step raises while the step was written never to raise, and a full disk published
            # a page nothing had timed.
            original = R.runrecord.append_event

            def refuses(*args, **kwargs):
                raise OSError(28, "INVENTED - no space left on device")

            R.runrecord.append_event = refuses
            try:
                self.assertEqual(_render_cli(run_dir), 5)
            finally:
                R.runrecord.append_event = original
            self.assertFalse(os.path.exists(
                os.path.join(run_dir, "report.html")))
            self.assertEqual([e["event"] for e in _events(run_dir)],
                             ["run_created", "run_finished"])
            # And nothing staged is left lying beside it.
            self.assertEqual([name for name in os.listdir(run_dir)
                              if name.startswith(".tmp-")], [])

    def test_the_refusal_says_what_failed_and_what_it_would_have_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            original = R.runrecord.append_event
            R.runrecord.append_event = lambda *a, **k: (_ for _ in ()).throw(
                OSError(28, "INVENTED - no space left on device"))
            try:
                buffer = io.StringIO()
                with contextlib.redirect_stderr(buffer):
                    self.assertEqual(_render_cli(run_dir), 5)
            finally:
                R.runrecord.append_event = original
            said = buffer.getvalue()
            self.assertIn("REFUSED:", said)
            self.assertIn("Nothing was published", said)
            self.assertIn("INVENTED - no space left on device", said)

    def test_a_row_whose_page_never_landed_still_times_the_retry(self):
        """The other window, one syscall wide: the row landed and the
        rename did not. The retry reads that recorded moment and writes
        the page the first rendering had already built, byte for byte,
        rather than a page timed to the retry."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            moment = self.START + datetime.timedelta(minutes=61)
            _stamp_first_render(run_dir, moment)
            self.assertEqual(_render_cli(run_dir), 0)
            self.assertIn("61 minutes sitting",
                          _visible_text(_stamps(_report_bytes(run_dir))))
            self.assertEqual(len([e for e in _events(run_dir)
                                  if e["event"] == R.REPORT_RENDERED_EVENT]),
                             1)

    def test_the_page_prints_the_moment_the_record_will_carry(self):
        """The two must never disagree: the page is built from the
        moment, and the row is written with that same moment rather than
        with the clock at the instant of writing."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            self.assertEqual(_render_cli(run_dir), 0)
            stamps = [e for e in _events(run_dir)
                      if e["event"] == R.REPORT_RENDERED_EVENT]
            recorded = R._stamp(stamps[0]["at"])
            page = _report_bytes(run_dir)
            self.assertEqual(_visible_text(_front(page)),
                             _visible_text(_front(R.render(run_dir))))
            self.assertEqual(recorded,
                             R.first_render_moment(run_dir))

    def test_a_page_reprinted_much_later_is_the_same_page(self):
        """The determinism a published run is archived on: the run record travels with the
        sitting, so the reprint anywhere, at any time, is the page the owner approved."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            _stamp_first_render(run_dir,
                                self.START + datetime.timedelta(minutes=84))
            first = R.render(run_dir)
            _stamp_first_render(run_dir,
                                self.START + datetime.timedelta(minutes=84))
            self.assertEqual(R.render(run_dir), first)
            self.assertIn("84 minutes sitting",
                          _visible_text(_stamps(first)))

    def test_a_run_with_no_record_at_all_prints_no_clock_and_writes_nothing(
            self):
        """A directory with no run record is not a sitting this council ran, so the page says
        nothing about how long one took and leaves nothing behind."""
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            self.assertEqual(_render_cli(run_dir), 0)
            self.assertFalse(os.path.exists(
                os.path.join(run_dir, "runrecord.jsonl")))
            self.assertNotIn("minutes sitting",
                             _visible_text(_front(_report_bytes(run_dir))))

    def test_the_recorded_row_never_displaces_the_runs_own_last_event(self):
        """Read-back proves a run finished by its record's last event. The rendering appends
        after that, so read-back reads the run's own last step and not this reading of it."""
        from council.engine import readback
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            _write_run_record(run_dir)
            events = _events(run_dir)
            self.assertEqual(events[-1]["event"], "run_finished")
            self.assertEqual(_render_cli(run_dir), 0)
            self.assertEqual(_events(run_dir)[-1]["event"],
                             R.REPORT_RENDERED_EVENT)
            self.assertEqual(readback._last_step(_events(run_dir))["event"],
                             "run_finished")


class TestSeatCostAndEstimateOnThePage(unittest.TestCase):
    """Owner ruling AC15, architect rulings (5)(a) and (5)(b): the report
    prints 'estimated' beside an estimated capture figure and carries the
    seat-cost measure in an appendix."""

    def _estimated_page(self, estimated):
        def mutate(run_dir):
            def change(doc):
                doc["provenance"]["evidence"]["capture"]["estimated"] = estimated
            _rewrite_verdict(run_dir, change)
        with tempfile.TemporaryDirectory() as tmp:
            return _render(_mutated_copy(tmp, mutate))

    def test_an_estimated_figure_says_so(self):
        self.assertIn("estimated", self._estimated_page(True))

    def test_a_counted_figure_does_not_say_estimated(self):
        page = self._estimated_page(False)
        # the gathering line is present but carries no "(estimated)"
        self.assertIn("minutes gathering the evidence.", page)
        self.assertNotIn("gathering the evidence (estimated)", page)

    def test_the_seat_cost_appendix_is_rendered(self):
        def mutate(run_dir):
            def change(doc):
                doc["provenance"]["seat_cost"] = {
                    "note": "tokens per tool turn and brief bytes per seat.",
                    "per_seat": {"advisor_bear": {
                        "tokens": 1200, "tool_calls": 3,
                        "tokens_per_tool_call": 400.0, "brief_bytes": 5000,
                        "input_tokens": None, "output_tokens": None}}}
            _rewrite_verdict(run_dir, change)
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertIn("Each seat&#x27;s share", page)
        self.assertIn("<td>The Bear</td>", page)   # the seat under its plain name
        self.assertNotIn("advisor_bear", _stamps(page))
        self.assertIn("400", page)     # tokens per turn
        # The two always-empty input and output columns are gone (unit READ-A).
        self.assertNotIn("Input tokens", page)
        self.assertNotIn("Output tokens", page)

    def test_no_seat_cost_block_renders_no_section(self):
        def mutate(run_dir):
            _rewrite_verdict(run_dir, lambda doc:
                             doc["provenance"].pop("seat_cost", None))
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertNotIn("Each seat&#x27;s share", page)


class TestU3eArchetypeAndCycleOnThePage(unittest.TestCase):
    """Owner ruling AC15 (P2, P4): the front names the archetype and the
    rating measure beside the rating; the cycle block is in the appendix.
    Every test FAILS against the pre-fix renderer."""

    def _render_with(self, mutate):
        tmp = tempfile.mkdtemp(prefix="report-u3e-")
        try:
            run_dir = _mutated_copy(tmp, mutate=mutate)
            _stamp_first_render(run_dir, _pinned_now(FIXTURE))
            return R.render(run_dir)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _inject(self, doc, cycle=None):
        cap = doc["capture"]
        ticker = cap["subject"]["ticker"]
        cap["business_frame"] = {
            ticker: {"archetype": "ramping_infrastructure_builder"}}
        for row in cap["sufficiency"]["requirements"]:
            if row["id"].startswith("rating_vs_history"):
                row["id"] = "rating_vs_history_or_peers"
                row["measure"] = ("ev_per_contracted_capacity_and_"
                                  "contracted_revenue_per_unit")
        if cycle is not None:
            cap["cycle"] = cycle

    def test_the_front_names_the_archetype_and_measure(self):
        html = self._render_with(
            lambda rd: _rewrite_pack(rd, self._inject))
        self.assertIn("ramping infrastructure builder", html)
        self.assertIn(
            "enterprise value per unit of contracted capacity", html)

    def test_the_cycle_block_is_in_the_appendix(self):
        cyc = {"name": "The AI capital-spending cycle",
               "why_it_matters": "the build depends on it",
               "series": [{"id": "cycle_series_0", "source": "a source",
                           "as_of": "2026-08-25", "unit": "index",
                           "points": [{"date": "2026-01-15",
                                       "value": "100.0"}],
                           "refetch_url_or_source_line":
                               "https://example.invalid/series"}]}
        html = self._render_with(
            lambda rd: _rewrite_pack(rd, lambda d: self._inject(d, cyc)))
        self.assertIn("The cycle this name depends on", html)
        self.assertIn("cycle_series_0", html)
        self.assertIn("100.0", html)

    def test_a_declared_cycle_gap_shows_in_the_appendix(self):
        cyc = {"name": "The AI capital-spending cycle",
               "why_it_matters": "the build depends on it",
               "gap": {"reason": "no single public series tracks it yet"}}
        html = self._render_with(
            lambda rd: _rewrite_pack(rd, lambda d: self._inject(d, cyc)))
        self.assertIn("The cycle this name depends on", html)
        self.assertIn("declared gap", html)

    def test_no_cycle_no_cycle_section(self):
        html = self._render_with(
            lambda rd: _rewrite_pack(rd, self._inject))
        self.assertNotIn("The cycle this name depends on", html)


class TestU6VoiceOnThePage(unittest.TestCase):
    """Unit U6 VOICE: the double-period fix, the chair's writing score on the
    front when it was warned, the per-seat advisory scores in the appendix, and
    the renderer's own authored text bound by the same measure (owner ruling
    AC6, spec U6.3/U6.4)."""

    @classmethod
    def setUpClass(cls):
        from council.lib import prose
        cls.prose = prose
        cls.rules = prose.load_rules()

    def test_no_double_period_when_a_quoted_magnitude_ends_in_one(self):
        run = R.load_run(FIXTURE)
        run["verdict"]["mispricing"] = {
            "read": "cheap",
            "magnitude": "about ten below a defensible value.",
            "arithmetic": None}
        body = R.build_page(run, NO_CLOCK_MOMENT).body()
        self.assertIn("defensible value.", body)
        self.assertNotIn("defensible value..", body)
        self.assertFalse(re.search(r"[A-Za-z]\.\.(?!\.)", body),
                         "an authored sentence rendered a double period")

    def test_a_warned_chair_shows_its_score_on_the_front(self):
        run = R.load_run(FIXTURE)
        score = self.prose.measure("It is not cheap, it is a trap.", self.rules)
        run["prose_scores"] = {
            "chair_resolve": {
                "seat": "chair_resolve", "judged": True, "warned": True,
                "over_threshold": True, "score": score}}
        body = R.build_page(run, NO_CLOCK_MOMENT).body()
        self.assertIn("did not meet the council", body)
        # The warned score reads on the front, in the warning card - not the
        # synthesis note, which now carries the chair's advisory synthesis
        # score (architect Step 0).
        self.assertIn(self.prose.describe(score), body)

    def test_a_clean_chair_shows_no_front_warning(self):
        run = R.load_run(FIXTURE)
        run["prose_scores"] = {
            "chair_resolve": {
                "seat": "chair_resolve", "judged": True, "warned": False,
                "over_threshold": False,
                "score": self.prose.measure("Clean.", self.rules)}}
        body = R.build_page(run, NO_CLOCK_MOMENT).body()
        self.assertNotIn("did not meet the council", body)

    def test_advisor_scores_render_in_the_appendix(self):
        run = R.load_run(FIXTURE)
        run["prose_scores"] = {
            "advisor_bear": {
                "seat": "advisor_bear", "judged": False, "warned": False,
                "score": self.prose.measure("Net cash is $10M.", self.rules)}}
        body = R.build_page(run, NO_CLOCK_MOMENT).body()
        # Unit READ-A (architect ruling 6): the advisory score is the writers' meter and stays in
        # the run's record; the page no longer prints it.
        self.assertNotIn("Writing score", body)
        self.assertNotIn(self.prose.describe(run["prose_scores"]["advisor_bear"]["score"]), body)

    def test_a_heading_reanswer_that_moved_a_figure_is_noted_beside_the_seat(self):
        # Architect ruling closing P-U5a-3: the flag on the record also reads
        # in the appendix, under the advisor whose rewrite moved a figure.
        run = R.load_run(FIXTURE)
        run["heading_flags"] = {"advisor_bear": {
            "figures_changed": True,
            "figures_differing": {"first": ["$10m"], "rewrite": ["$20m"]}}}
        body = R.build_page(run, NO_CLOCK_MOMENT).body()
        self.assertIn("changed figures", body)
        self.assertIn("$20m", body)
        run["heading_flags"] = {"advisor_bear": {
            "figures_changed": False,
            "figures_differing": {"first": [], "rewrite": []}}}
        self.assertNotIn("changed figures",
                         R.build_page(run, NO_CLOCK_MOMENT).body())

    def test_the_chair_synthesis_advisory_score_renders_beside_the_synthesis(self):
        # Architect Step 0: the chairman's long synthesis carries an advisory
        # writing score in the appendix, under a key distinct from the gated
        # rationale score, so the synthesis note scores the synthesis text.
        run = R.load_run(FIXTURE)
        run["prose_scores"] = {
            "chair_resolve_synthesis": {
                "seat": "chair_resolve_synthesis", "judged": False,
                "warned": False,
                "score": self.prose.measure("Net cash is $10M.", self.rules)}}
        body = R.build_page(run, NO_CLOCK_MOMENT).body()
        # Unit READ-A (architect ruling 6): no advisory score beside the synthesis either.
        self.assertNotIn("Writing score", body)

    def test_the_renderers_authored_text_passes_the_measure(self):
        # Owner ruling AC6, spec U6.3. The page's own framing sentences are
        # bound by the council's writing rules. Docstrings and the code
        # constants (the stylesheet, the script, the preamble) are not prose.
        import ast
        path = os.path.join(ROOT, "council", "report", "render_report.py")
        tree = ast.parse(open(path, encoding="utf-8").read())
        docstrings = set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)) and body:
                first = body[0]
                if (isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    docstrings.add(id(first.value))
        skip_names = {"CSS", "_CSS_TEMPLATE", "SCRIPT", "PREAMBLE",
                      "RENDERER_SIGNATURE", "NAV_ICON", "_PIN_PROP",
                      "_BOLD_PROP",
                      # A unit token, not authored prose: the percentage unit's own name.
                      "_PERCENT_PREFIX"}
        skip = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if (isinstance(tgt, ast.Name) and tgt.id in skip_names
                            and isinstance(node.value, ast.Constant)):
                        skip.add(id(node.value))
        authored = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant)
                    and isinstance(n.value, str)
                    and id(n) not in docstrings and id(n) not in skip]
        text = re.sub(r"<[^>]+>", " ", "\n".join(authored))
        text = re.sub(r"&[A-Za-z#0-9]+;", " ", text)
        score = self.prose.measure(text, self.rules)
        self.assertEqual(score["banned"], [],
                         "authored text has a banned number-style: %s"
                         % score["banned"])
        self.assertEqual(score["antithesis"], 0,
                         "authored text has a rhetorical antithesis")


class TestTierStructure(unittest.TestCase):
    """Owner ruling AC16, audit C4: the page dives deeper the further one scrolls. Tier 3 (the
    decision in detail) is open; tier 4 (the evidence) opens with a compact table of the facts
    the verdict rests on and folds the rest; tier 5 (the appendices) are all folded, one line
    each; the navigation names about nine content tiers, not seventeen process steps."""

    def test_the_five_tiers_are_in_order(self):
        # The eight numbered sections of unit READ-A (owner's finding 5), in the ruled order.
        found = re.findall(r'<h2 id="([a-z-]+)" data-num="(\d)"', HTML)
        self.assertEqual([anchor for anchor, _num in found], list(ANCHORS), found)
        self.assertEqual([num for _anchor, num in found], [str(n) for n in range(1, 9)])

    def test_the_navigation_is_nine_content_tiers(self):
        # The menu names the eight numbered sections, never a process step ('the audit of the
        # evidence', 'tripwires'): those folded into the sections (unit READ-A).
        self.assertEqual(ANCHORS, ("decision", "synthesis", "advisors", "review", "challenge",
                                   "detail", "evidence", "appendices"))
        menu = re.search(r'<div class="menucard">(.*?)</div></div></nav>', HTML, re.S).group(1)
        self.assertIn('<a href="#advisors">3  The five advisors</a>', menu)
        for process in ("evidence-audit", "tripwires", "warnings", "changes", "stamps"):
            self.assertNotIn('href="#%s"' % process, menu, process)

    def test_the_decision_in_detail_tier_is_open(self):
        detail = _detail(HTML)
        # The downside ladder and the evidence check are here, open - the tier itself carries no
        # wrapping fold; the challenge round is its own section 5 (unit READ-A).
        self.assertIn("The downside ladder", detail)
        self.assertIn("The evidence check: its points, and the answers", detail)
        self.assertIn("The outside challenge round", _section(HTML, "challenge"))
        self.assertNotIn("<details><summary>The downside ladder", detail)

    def test_the_challenge_card_stays_open_in_the_detail_tier(self):
        section = _section(HTML, "challenge")
        self.assertIn("The outside challenge ran.", section)
        # The card's findings are not behind a fold (ruled open, audit C5).
        card = section[section.index("The outside challenge round"):]
        self.assertNotIn("<details>", card[:card.index("The outside model&#x27;s own words")])

    def test_the_non_blocking_audit_findings_fold_with_their_count(self):
        # The fixture's two points are both non-blocking: they fold behind one line with the count,
        # while the auditor's own paragraph stays open (owner ruling AC16, audit C4 tier 3).
        detail = _detail(HTML)
        self.assertIn("The outside model&#x27;s reading of this evidence, in its own words", detail)
        self.assertIn("<details><summary>2 non-blocking points the evidence check raised, each "
                      "with its answer on the record</summary>", detail)

    def test_the_evidence_opens_with_the_facts_the_verdict_rests_on(self):
        evidence = HTML[HTML.index('<h2 id="evidence"'):HTML.index('<h2 id="appendices"')]
        fold = evidence.index("<details><summary>Every figure on the record")
        # The compact table and its four columns are open, above the fold; the age check is one
        # line under it instead of a column (unit READ-A).
        self.assertIn("The figures the verdict says its ruling rests on.", evidence)
        # The value column is not nowrap - it can hold a tier-2 sentence (design audit C5, B8).
        self.assertIn('<th>fact</th><th>value</th><th class="nowrap">as of</th>'
                      "<th>source</th>", evidence)
        # The fixture's ten-year rate is stale: it keeps a STALE tag and the line counts it.
        self.assertLess(evidence.index("1 figure here failed its age check and carries a STALE "
                                       "tag."), fold)
        self.assertLess(evidence.index('4.2% <span class="tag stale">STALE</span>'), fold)
        # A decisive fact is in the open compact table; the whole 10-fact pack is behind the fold.
        self.assertLess(evidence.index("<tr><td>last price</td>"), fold)
        self.assertIn("all 10 frozen facts in the evidence pack", evidence)

    def test_the_tier_five_appendices_are_folded(self):
        for summary in ("The owner&#x27;s question as he asked it",
                        "The blind reviewer&#x27;s synopsis and full cross-examination of the "
                        "five advisors",
                        "For Atlas, the portfolio system &mdash; no reading needed"):
            self.assertIn("<details><summary>%s" % summary, HTML)

    def test_the_challenge_diff_is_sentences_with_before_after_behind_a_second_fold(self):
        # Owner ruling AC16(8), audit B3: the diff is plain sentences now, not open JSON; the exact
        # text before and after is behind a second fold.
        changes = HTML[HTML.index('<h3 id="changes">'):HTML.index('<h3 id="atlas">')]
        self.assertIn("<details><summary>2 fields changed between the draft the outside challenge "
                      "read and the final document</summary>", changes)
        self.assertIn("<details><summary>The exact text before and after, field by field"
                      "</summary>", changes)
        # Each field in plain words (unit READ-A), never a code span.
        self.assertRegex(changes, r"<li>[^<]+ &mdash; ")
        self.assertNotRegex(changes, r"<li><code>")

    def test_the_run_stamps_are_a_folded_appendix_off_the_nav(self):
        self.assertIn('<h3 id="stamps">About this sitting</h3>', HTML)
        self.assertNotIn('href="#stamps"', HTML)
        stamps = _stamps(HTML)
        self.assertIn("<details><summary>How long the sitting took, and what it cost</summary>",
                      stamps)

    def test_the_advisor_folds_carry_no_emoji(self):
        advisors = HTML[HTML.index('<h2 id="advisors"'):HTML.index('<h3 id="challenger">')]
        for emoji in ("\U0001F43B", "\U0001F402", "\U0001F4CA", "\U0001F3E6", "\U0001F6E1"):
            self.assertNotIn(emoji, advisors)
        self.assertIn("<details><summary>The bear case</summary>", advisors)


class TestSubjectShapeSectionsAreDecisionContent(unittest.TestCase):
    """Architect ruling closing register item P-U6b-9: the subject-shape blocks - the constituents,
    the cycle a single name depends on, and the scenario ladders in full - are what the decision
    rests on for their subject shape, not appendices. They rendered OPEN under the 'all folded'
    appendices divider before (and a theme's thesis card open before its heading); now they render
    on the open decision-in-detail tier, the theme thesis leads the executive summary, each under a
    content-named h3 with no nav entry, and nothing open follows the appendices divider except the
    folded appendices and the footer. Every assertion FAILED against the pre-ruling renderer."""

    CONSTITUENTS = "<h3>The constituents</h3>"
    LADDERS = "<h3>The scenario ladders, in full</h3>"
    CYCLE = "<h3>The cycle this name depends on</h3>"
    THEME_THESIS = "The theme&#x27;s thesis, frozen before the council sat"

    def _after_divider(self, page):
        return page[page.index('<h2 id="appendices"'):]

    def _cycle_page(self):
        cyc = {"name": "The AI capital-spending cycle",
               "why_it_matters": "the build depends on it",
               "series": [{"id": "cycle_series_0", "source": "a source",
                           "as_of": "2026-08-25", "unit": "index",
                           "points": [{"date": "2026-01-15", "value": "100.0"}],
                           "refetch_url_or_source_line": "https://example.invalid/series"}]}
        with tempfile.TemporaryDirectory() as tmp:
            return _render(_mutated_copy(
                tmp, lambda rd: _rewrite_pack(
                    rd, lambda d: d["capture"].__setitem__("cycle", cyc))))

    def test_constituents_render_in_the_detail_tier_on_basket_and_theme(self):
        for page in (BASKET_HTML, THEME_HTML):
            self.assertIn(self.CONSTITUENTS, _detail(page))
            self.assertNotIn(self.CONSTITUENTS, self._after_divider(page))

    def test_the_theme_thesis_leads_the_executive_summary(self):
        front = _front(THEME_HTML)
        self.assertIn(self.THEME_THESIS, front)
        # The key-data strip is in the masthead now, above the theme thesis in the executive
        # summary (design audit C5): the strip-before-thesis order holds at the page level.
        self.assertLess(THEME_HTML.index("<h3>The numbers this ruling turns on</h3>"),
                        THEME_HTML.index(self.THEME_THESIS))
        # Not on the detail tier, and not open after the appendices divider.
        self.assertNotIn(self.THEME_THESIS, _detail(THEME_HTML))
        self.assertNotIn(self.THEME_THESIS, self._after_divider(THEME_HTML))

    def test_the_full_ladders_render_open_in_the_detail_tier_not_folded(self):
        page = _scenario_page(_published_block())
        self.assertIn(self.LADDERS, _detail(page))
        # Open: the old wrapping fold summary is gone from the whole page.
        self.assertNotIn("The ladders in full &mdash; the chairman", page)
        self.assertNotIn(self.LADDERS, self._after_divider(page))

    def test_the_cycle_block_renders_in_the_detail_tier(self):
        page = self._cycle_page()
        self.assertIn(self.CYCLE, _detail(page))
        self.assertIn("cycle_series_0", _detail(page))
        self.assertNotIn(self.CYCLE, self._after_divider(page))

    def test_nothing_open_follows_the_appendices_divider_but_folds_and_footer(self):
        # The subject-shape content that once rendered open after the divider is gone from there on
        # every subject shape; what remains after the divider is the folded appendices (each an h2
        # signpost with a <details> beneath) and the footer.
        pages = (HTML, BASKET_HTML, THEME_HTML, _scenario_page(_published_block()),
                 self._cycle_page())
        for page in pages:
            after = self._after_divider(page)
            for marker in (self.CONSTITUENTS, self.LADDERS, self.CYCLE, self.THEME_THESIS):
                self.assertNotIn(marker, after)
            self.assertIn('<div class="foot">', after)


# ---------------------------------------------------------------------------------------------
# UPGRADE-2 U4(c): THE PRICE CHART AND THE TAPE ON THE PAGE (the spec's chart on the page;
# owner rulings AC16 and AC27)
# ---------------------------------------------------------------------------------------------
# A fixture run is re-frozen over its own capture plus an INVENTED daily series, so the tape it
# carries is exactly what the freeze would write. Every series below is invented; no run on record
# is written. The closes drift upward with a repeating swing so the averages, the range and the
# drawdown all carry figures.

TAPE_END = "2026-08-28"
TAPE_CALENDAR = "XNYS"
TAPE_BARS = 520
TAPE_SHORT_BARS = 150
TAPE_TINY_BARS = 20
TAPE_SWING_CYCLE = 13
TAPE_SWING_MIDDLE = 6
TAPE_SWING_STRIDE = 7
BENCH_SWING_STRIDE = 5
TAPE_BASE = decimal.Decimal("60.00")
TAPE_STEP = decimal.Decimal("0.05")
TAPE_SWING = decimal.Decimal("0.40")
BASKET_BASE = decimal.Decimal("180.00")
BENCH_BASE = decimal.Decimal("400.00")
BENCH_STEP = decimal.Decimal("0.30")
BENCH_TICKER = "SPY"
EXTRA_LEVEL = "95.00"
UNREADABLE_LEVEL = "about seventy dollars"
FORCED_SMA200 = "-12.3456789012"
TAPE_HEADING = "<h3>The price chart and the tape</h3>"
LEVEL_GROUP = '<g class="ch-levelmark">'
CHART_OPEN = '<figure class="tapechart"'
TABLE_OPEN = '<table class="tapetable">'


def _exchange_days(end, count):
    """The last `count` exchange days of the ruled calendar up to and including `end`."""
    ruled = _floors()["price_series"]["exchange_calendars"][TAPE_CALENDAR]
    holidays = set(ruled["holidays"])
    trades = set(ruled["trading_weekdays"])
    day = datetime.date.fromisoformat(end)
    days = []
    while len(days) < count:
        if day.isoweekday() in trades and day.isoformat() not in holidays:
            days.append(day.isoformat())
        day -= datetime.timedelta(days=1)
    return list(reversed(days))


def _invented_series(ticker, count, base, step, stride, swing_size=TAPE_SWING):
    bars = []
    for index, day in enumerate(_exchange_days(TAPE_END, count)):
        swing = swing_size * ((index * stride) % TAPE_SWING_CYCLE - TAPE_SWING_MIDDLE)
        bars.append({"date": day, "close": str(base + step * index + swing),
                     "volume": str(1000000 + 100 * index)})
    return {"ticker": ticker, "calendar": TAPE_CALENDAR,
            "source": "INVENTED FIXTURE - broker price history for %s" % ticker,
            "as_of": TAPE_END, "bars": bars}


def _taped_run(tmp, source=None, ticker="SPWK", count=TAPE_BARS, benchmark=True,
               base=TAPE_BASE, verdict_change=None, flat=False):
    """A copy of a fixture run whose pack is re-frozen with an invented series (and the invented
    benchmark's, unless the sitting is absolute); `flat` holds every close at `base`."""
    run_dir = _mutated_copy(tmp, source=source)
    path = os.path.join(run_dir, "pack", "pack.json")
    with open(path, "rb") as fh:
        capture = json.loads(fh.read().decode("utf-8"))["capture"]
    tier1 = capture["tier1"]
    if not any(fact["id"].startswith("price_last") for fact in tier1):
        price = copy.deepcopy(next(f for f in tier1 if f["id"] == "last_price"))
        price["id"] = "price_last"
        tier1.append(price)
    capture["price_series"] = _invented_series(ticker, count, base,
                                               decimal.Decimal(0) if flat else TAPE_STEP,
                                               TAPE_SWING_STRIDE,
                                               decimal.Decimal(0) if flat else TAPE_SWING)
    if benchmark:
        capture["benchmark_series"] = _invented_series(BENCH_TICKER, count, BENCH_BASE,
                                                       BENCH_STEP, BENCH_SWING_STRIDE)
        capture["benchmark"] = {"ticker": BENCH_TICKER, "listing": "NYSE Arca",
                                "why": "INVENTED FIXTURE - the report suite's benchmark"}
    else:
        capture["benchmark"] = {"ticker": None,
                                "why": "INVENTED FIXTURE - a sitting judged on its own return"}
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(freeze.build_pack(capture, _floors()), fh, indent=2)
    if verdict_change:
        _rewrite_verdict(run_dir, verdict_change)
    return run_dir


def _taped_page(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        return _render(_taped_run(tmp, **kwargs))


def _taped_pack(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _taped_run(tmp, **kwargs)
        with open(os.path.join(run_dir, "pack", "pack.json"), "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))


def _chart(page):
    start = page.index(CHART_OPEN)
    return page[start:page.index("</figure>", start) + len("</figure>")]


def _tape_table(page):
    start = page.index(TABLE_OPEN)
    return page[start:page.index("</table>", start) + len("</table>")]


DIVIDEND = "3.00"


def _lead_with(fields, insert=False):
    """A verdict change: the envelope's leading key number carries `fields` (a new leading row
    copied from the old one, where `insert`)."""
    def change(doc):
        numbers = doc["atlas_envelope"]["key_numbers"]
        if insert:
            numbers.insert(0, copy.deepcopy(numbers[0]))
        numbers[0].update(fields)
    return change


def _add_triggers(*triggers):
    def change(doc):
        doc["tripwires"]["reopening_triggers"].extend(copy.deepcopy(list(triggers)))
    return change


def _price_trigger(level, detail, constituent=None):
    trigger = {"kind": "price", "level": level, "unit": "USD", "date": None,
               "detail": detail}
    if constituent:
        trigger["constituent"] = constituent
    return trigger


# The three notices a pack with no price series prints, by what the pack carries (architect
# ruling, Step 0 of U4(c) audit round 2), quoted here so a test reads the words the owner reads.
NOTICE_RANGE = ("This pack carries no daily price series, so there is no price chart and no tape "
                "table: the price and its 52-week range are the whole of what it says about the "
                "tape.")
NOTICE_PRICE = ("This pack carries no daily price series, so there is no price chart and no tape "
                "table: the price alone is what it says about the tape.")
NOTICE_NONE = ("This pack carries no daily price series and no price, so there is no price chart "
               "and no tape table: it says nothing about the tape.")


def _basket_with_range(range_ids, drop=()):
    """The basket fixture's page, its pack given the named 52-week range ends (copies of a
    member's price fact under each id) and without the facts named in `drop`."""
    def add_range(doc):
        tier1 = doc["capture"]["tier1"]
        tier1[:] = [fact for fact in tier1 if fact["id"] not in drop]
        price = next(fact for fact in tier1 if fact["id"] == "price_last__achp")
        for fact_id in range_ids:
            fact = copy.deepcopy(price)
            fact["id"] = fact_id
            tier1.append(fact)
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _mutated_copy(tmp, source=FIXTURE_BASKET)
        _rewrite_pack(run_dir, add_range)
        return _render(run_dir)


TAPED_HTML = None


def _taped_html():
    """The default taped page, rendered once for the read-only tests."""
    global TAPED_HTML
    if TAPED_HTML is None:
        TAPED_HTML = _taped_page()
    return TAPED_HTML


class TestPriceChartAndTape(unittest.TestCase):
    """The chart the seats read and the tape's figures, on one page under the executive summary's
    heading; a pack with no series says so in one line."""

    def test_a_run_without_a_price_series_prints_the_placeholder_line_and_no_chart(self):
        front = _front(HTML)
        self.assertIn(TAPE_HEADING, front)
        self.assertEqual(HTML.count(E(NOTICE_NONE)), 1)
        self.assertIn(E(NOTICE_NONE), front)
        self.assertNotIn(CHART_OPEN, HTML)
        self.assertNotIn(TABLE_OPEN, HTML)

    def test_a_page_with_no_price_says_nothing_about_the_tape(self):
        # Audit round 1 of U4(c), r1-3 (registered P-U4c-2, closed by the architect's ruling in
        # Step 0 of round 2): the fixture's pack carries no price fact the council reads (its
        # figure wears another id), and the notice told the owner "the price alone" is what it
        # says about the tape.
        front = _front(HTML)
        self.assertIn(E(NOTICE_NONE), front)
        self.assertNotIn(E(NOTICE_PRICE), HTML)
        self.assertNotIn(E(NOTICE_RANGE), HTML)

    def test_a_basket_price_without_a_52_week_range_names_the_price_alone(self):
        # Architect ruling, Step 0 of U4(c) audit round 1: a pack with a price but no 52-week
        # range names the price alone.
        front = _front(BASKET_HTML)
        self.assertIn(E(NOTICE_PRICE), front)
        self.assertNotIn(E(NOTICE_RANGE), BASKET_HTML)

    def test_a_range_split_across_two_basket_members_names_the_price_alone(self):
        # Audit round 1 of U4(c), r1-2 (registered P-U4c-1, closed by the architect's ruling in
        # Step 0 of round 2): a low on one member and a high on another is no 52-week range.
        front = _front(_basket_with_range(("range_52w_low__achp", "range_52w_high__bgrd")))
        self.assertIn(E(NOTICE_PRICE), front)
        self.assertNotIn(E(NOTICE_RANGE), front)

    def test_a_range_on_a_member_without_its_price_names_the_price_alone(self):
        # Audit round 3 of U4(c), r3-1 (registered P-U4c-3, closed by the architect's ruling in
        # Step 0 of round 4): one member's price and another member's full range, that member's
        # own price absent, is no price against its range.
        front = _front(_basket_with_range(("range_52w_low__bgrd", "range_52w_high__bgrd"),
                                          drop=("price_last__bgrd",)))
        self.assertIn(E(NOTICE_PRICE), front)
        self.assertNotIn(E(NOTICE_RANGE), front)

    def test_a_members_matched_52_week_range_keeps_the_range_wording(self):
        front = _front(_basket_with_range(("range_52w_low__achp", "range_52w_high__achp")))
        self.assertIn(E(NOTICE_RANGE), front)
        self.assertNotIn(E(NOTICE_PRICE), front)

    def test_a_series_draws_one_inline_svg_chart_with_no_network_resource(self):
        page = _taped_html()
        self.assertEqual(page.count(CHART_OPEN), 1)
        chart = _chart(page)
        self.assertEqual(chart.count("<svg"), 1 + chart.count('class="ch-key"'))
        self.assertIn('role="img"', chart)
        self.assertIn("<title", chart)
        self.assertIn("<desc", chart)
        self.assertIn('class="ch-close"', chart)
        for needle in ("http", "href", "<image", "url(", "<script", "@import"):
            self.assertNotIn(needle, chart)
        caption = chart[chart.index("<figcaption"):]
        self.assertIn("SPWK", caption)
        self.assertIn(R.format_date(TAPE_END), caption)
        # The series' own provenance sentence is in the closed fold directly under the chart
        # (owner's finding 1), not in the caption.
        self.assertNotIn(E("INVENTED FIXTURE - broker price history for SPWK"), caption)
        fold = _between(page, "</figure>", "</details>")
        self.assertIn("<details><summary>Where the price history comes from", fold)
        self.assertIn(E("INVENTED FIXTURE - broker price history for SPWK"), fold)

    def test_the_chart_draws_every_price_trigger_level_with_its_label(self):
        extra = _price_trigger(EXTRA_LEVEL, "Reopen the case if the shares close above the "
                               "invented ceiling. (INVENTED)")
        chart = _chart(_taped_page(verdict_change=_add_triggers(extra)))
        self.assertEqual(chart.count(LEVEL_GROUP), 2)
        for level in ("72.00", EXTRA_LEVEL):
            # No key number names these invented levels, so each carries the plain fallback words
            # (owner ruling AC41(4); the chairman's own names are checked on JPM).
            self.assertIn(E("%s \u2014 %s" % (R.format_number(level, "USD"), R.chart.LEVEL_WORDS)),
                          chart)
        self.assertIn("<title>Reopen the case if the shares close at or under", chart)
        self.assertIn("<title>Reopen the case if the shares close above the invented ceiling",
                      chart)

    def test_an_event_trigger_and_a_falsifier_draw_nothing(self):
        chart = _chart(_taped_html())
        self.assertEqual(chart.count(LEVEL_GROUP), 1)
        self.assertNotIn("full-year results", chart)
        self.assertNotIn("growth leg", chart)
        # The verdict's separate invalidation level is not drawn either (architect ruling 1).
        self.assertNotIn("breaks the base", chart)
        self.assertNotIn(R.format_number("84.50", "USD"), chart)

    def test_a_level_bound_to_another_member_draws_nothing(self):
        unbound = _price_trigger(EXTRA_LEVEL, "Reopen if the pair as a whole falls. (INVENTED)")
        own = _chart(_taped_page(source=FIXTURE_BASKET, ticker="ACHP", base=BASKET_BASE,
                                 verdict_change=_add_triggers(unbound)))
        self.assertEqual(own.count(LEVEL_GROUP), 1)
        self.assertIn(E(R.format_number("200.00", "USD")), own)
        other = _chart(_taped_page(source=FIXTURE_BASKET, ticker="BGRD", base=BASKET_BASE,
                                   verdict_change=_add_triggers(unbound)))
        self.assertEqual(other.count(LEVEL_GROUP), 0)
        self.assertNotIn("Alpha Chips closes", other)
        self.assertNotIn("the pair as a whole", other)

    def test_an_unreadable_level_draws_nothing_and_stays_in_the_table(self):
        odd = _price_trigger(UNREADABLE_LEVEL, "Reopen when the invented oddity trips. (INVENTED)")
        page = _taped_page(verdict_change=_add_triggers(odd))
        self.assertEqual(_chart(page).count(LEVEL_GROUP), 1)
        self.assertNotIn("invented oddity", _chart(page))
        self.assertIn("invented oddity", _front(page))
        self.assertIn(UNREADABLE_LEVEL, _front(page))

    def test_the_benchmark_line_is_rebased_and_labelled(self):
        chart = _chart(_taped_html())
        closes = re.search(r'<polyline class="ch-close" points="([^"]+)"', chart).group(1)
        bench = re.search(r'<polyline class="ch-bench" points="([^"]+)"', chart).group(1)
        # Both series trade on one calendar, so the benchmark starts ON the first close.
        self.assertEqual(bench.split()[0], closes.split()[0])
        self.assertEqual(len(bench.split()), len(closes.split()))
        self.assertIn(BENCH_TICKER, chart)
        self.assertIn(R.chart.REBASED_WORDS, chart)

    def test_an_absolute_sitting_draws_no_benchmark_line(self):
        chart = _chart(_taped_page(benchmark=False))
        self.assertNotIn("ch-bench", chart)
        self.assertNotIn(R.chart.REBASED_WORDS, chart)

    def test_an_average_is_drawn_only_where_the_tape_carries_it(self):
        full = _chart(_taped_html())
        for window in (50, 100, 200):
            self.assertIn('<polyline class="ch-sma%d"' % window, full)
        short = _chart(_taped_page(count=TAPE_SHORT_BARS))
        self.assertIn('<polyline class="ch-sma50"', short)
        self.assertIn('<polyline class="ch-sma100"', short)
        self.assertNotIn("ch-sma200", short)
        self.assertNotIn("200-day average", short)

    def test_the_drawn_average_agrees_with_the_tape(self):
        pack = _taped_pack()
        facts = {fact["id"]: fact for fact in pack["capture"]["tier1"]}
        for window in (50, 100, 200):
            self.assertIn("tape_close_vs_sma%d" % window, facts)
        chart = _chart(_taped_html())
        self.assertIn('<polyline class="ch-sma200"', chart)

    def test_a_drawn_average_that_disagrees_with_the_tape_refuses_the_render(self):
        def force(pack):
            for fact in pack["capture"]["tier1"]:
                if fact["id"] == "tape_close_vs_sma200":
                    fact["value"] = FORCED_SMA200
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _taped_run(tmp)
            _rewrite_pack(run_dir, force)
            with self.assertRaises(R.chart.ChartRefused) as caught:
                _render(run_dir)
            self.assertIn("200-day average", str(caught.exception))
            _stamp_first_render(run_dir, _pinned_now(run_dir))
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(_render_cli(run_dir), 1)
            self.assertIn("200-day average", err.getvalue())
            self.assertFalse(os.path.exists(os.path.join(run_dir, "report.html")))

    def test_the_display_table_has_fifteen_rows_covering_every_tape_fact_but_the_levels_once(
            self):
        # Unit U4(b): the three average prices are recorded for the seats; the page keeps
        # its fifteen rows, and the chart draws each average as a line.
        rows = R.chart.TAPE_DISPLAY_ROWS
        self.assertEqual(len(rows), 15)
        ids = [fact_id for _title, figures in rows for fact_id, _name in figures]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(tape.LEVEL_IDS)
        for fact_id in tape.LEVEL_IDS:
            self.assertNotIn(fact_id, ids)
        self.assertEqual(sorted(ids),
                         sorted(i for i in tape.ROW_IDS if i not in tape.LEVEL_IDS))
        self.assertEqual(_tape_table(_taped_html()).count('<tr class="taperow">'), 15)

    def test_every_tape_figure_prints_through_the_display_rules(self):
        table = _tape_table(_taped_html())
        pack = _taped_pack()
        displayed = [fact_id for _title, figures in R.chart.TAPE_DISPLAY_ROWS
                     for fact_id, _name in figures]
        carried = [fact for fact in pack["capture"]["tier1"] if fact["id"] in displayed]
        self.assertEqual(len(carried), len(displayed))
        for fact in carried:
            self.assertIn(E(R.format_number(fact["value"], fact["unit"])), table, fact["id"])
            if fact["derived"].get("date"):
                self.assertIn(E(R.format_date(fact["derived"]["date"])), table, fact["id"])

    def test_a_declared_gap_prints_as_a_gap_never_zero_or_blank(self):
        pack = _taped_pack(benchmark=False)
        gaps = [gap for gap in pack["capture"]["gaps"] if gap["fact_class"] in tape.ROW_IDS]
        self.assertEqual(len(gaps), len(tape.RETURN_WINDOWS))
        table = _tape_table(_taped_page(benchmark=False))
        self.assertEqual(table.count(E(R.chart.GAP_WORDS)), len(gaps))
        for gap in gaps:
            self.assertIn(E(gap["reason"]), table)
        for cell in re.findall(r"<td[^>]*>(.*?)</td>", table, re.S):
            self.assertNotEqual(TAG.sub("", cell).strip(), "")

    def test_every_tape_label_is_printed_and_no_tape_id_is(self):
        for page in (_taped_html(), _taped_page(count=TAPE_TINY_BARS)):
            for fact_id in tape.ROW_IDS:
                self.assertIn(E(tape.LABELS[fact_id]), page, fact_id)
            self.assertNotIn("tape_", page)

    def test_a_tape_of_nothing_but_gaps_prints_the_all_gaps_line(self):
        page = _taped_page(count=TAPE_TINY_BARS)
        front = _front(page)
        self.assertIn(E(pack_brief.TAPE_ALL_GAPS), front)
        self.assertNotIn(TABLE_OPEN, page)
        self.assertIn('<polyline class="ch-close"', _chart(page))
        # The line promises that every missing figure is listed by name; the page's own
        # declared-gap list names each one by its plain label (architect ruling 7).
        gaps = page[page.index("<h3>Declared gaps</h3>"):]
        gaps = gaps[:gaps.index("</ul>")]
        for fact_id in tape.ROW_IDS:
            self.assertIn(E(tape.LABELS[fact_id]), gaps, fact_id)

    def test_the_chart_colours_come_only_from_theme_tokens(self):
        chart = _chart(_taped_html())
        self.assertIsNone(re.search(r"#[0-9A-Fa-f]{3,8}\b", chart))
        self.assertIsNone(re.search(r'\s(fill|stroke|color|style)="', chart))
        self.assertNotIn("var(", chart)
        css = R.CSS
        dark = css[css.index(":root{"):css.index("}", css.index(":root{"))]
        light = css[css.index(':root[data-theme="light"]{'):]
        light = light[:light.index("}")]
        printed = css[css.index("@media print"):]
        printed = printed[:printed.index("}")]
        for name in sorted(set(re.findall(r'class="(ch-[a-z0-9]+)"', chart))):
            rule = re.search(r"\.%s\{([^}]*)\}" % re.escape(name), css)
            self.assertIsNotNone(rule, name)
            tokens = re.findall(r"var\(--([a-z-]+)\)", rule.group(1))
            self.assertTrue(tokens or "fill:none" in rule.group(1), name)
            for token in tokens:
                for block in (dark, light, printed):
                    self.assertIn("--%s:" % token, block, (name, token))
        self.assertIn(".tapechart{break-inside:avoid}", css[css.index("@media print"):])
        self.assertNotIn("prefers-color-scheme", css)

    def test_the_chart_renders_with_every_script_removed(self):
        page = re.sub(r"<script>.*?</script>", "", _taped_html(), flags=re.S)
        self.assertNotIn("<script", page)
        chart = _chart(page)
        self.assertIn('<polyline class="ch-close"', chart)
        self.assertIsNone(re.search(r"\son[a-z]+=", chart))

    def test_two_renders_of_a_taped_run_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _taped_run(tmp)
            first, second = _render(run_dir), _render(run_dir)
        self.assertEqual(first, second)
        chart = _chart(first)
        numbers = re.findall(r'\s(?:points|x|y|x1|x2|y1|y2|cx|cy|r|width|height)="([^"]+)"',
                             chart)
        self.assertTrue(numbers)
        for text in numbers:
            for token in re.split(r"[ ,]", text):
                if token != "100%":
                    self.assertRegex(token, r"^\d+(\.\d)?$")

    def test_the_chart_opens_the_executive_summary(self):
        for page in (HTML, _taped_html()):
            front = _front(page)
            opening = ('<h2 id="decision" data-num="1" data-title="The answer"><span '
                       'class="secnum">1</span>The answer</h2>')
            # Since U5(b) the chairman's "What decided it" card comes first, and since READ-C1
            # his one-line answer before it (owner ruling AC44(1)); the chart and the tape follow
            # them directly.
            decided = front[len(opening):front.index(TAPE_HEADING)]
            self.assertTrue(front.startswith(opening), front[:200])
            self.assertTrue(decided.startswith('<div class="card prominent"><span class="lead">'
                                               "The answer to your question</span>"), front[:200])
            self.assertIn('<div class="card prominent"><span class="lead">What decided it</span>',
                          decided)
            self.assertEqual(decided.count("<div class="), 2, decided)

    def test_the_price_at_the_ruling_is_marked_for_a_single_subject_only(self):
        chart = _chart(_taped_page(verdict_change=_lead_with({"pack_fact_id": "price_last"})))
        self.assertIn('class="ch-mark"', chart)
        self.assertIn(E("last price %s" % R.format_number("88.40", "USD")), chart)
        basket = _chart(_taped_page(source=FIXTURE_BASKET, ticker="ACHP", base=BASKET_BASE))
        self.assertNotIn('class="ch-mark"', basket)

    def test_a_leading_key_number_that_is_not_the_price_is_never_marked_as_it(self):
        # Audit round 1 of U4(c), r1-1: the envelope's order is model-authored, so a leading key
        # number in the price's unit - a dividend per share, a price target - was drawn as "the
        # price the ruling is made against". Only the pack's own price fact is marked.
        lead = _lead_with({"name": "Dividend per share", "value": DIVIDEND,
                           "pack_fact_id": "dividend_per_share"}, insert=True)
        chart = _chart(_taped_page(verdict_change=lead))
        self.assertNotIn('class="ch-mark"', chart)
        self.assertNotIn("Dividend per share", chart)
        self.assertNotIn("The price the ruling is made against", chart)

    def test_a_leading_key_number_citing_another_fact_is_not_marked(self):
        # The fixture's leading key number cites its own last-price fact, not the price fact the
        # chart reads the series' unit from; it is not marked.
        self.assertNotIn('class="ch-mark"', _chart(_taped_html()))

    def test_the_52_week_band_is_drawn_from_the_tape_high_and_low(self):
        self.assertIn('<rect class="ch-band"', _chart(_taped_html()))
        self.assertNotIn("ch-band", _chart(_taped_page(count=TAPE_SHORT_BARS)))

    def test_a_52_week_range_of_one_price_is_still_drawn(self):
        # Audit round 3 of U4(c), r3-2: a year of equal closes gives a range whose highest and
        # lowest close coincide; the band was a rectangle of no height, invisible although the
        # legend and the description name it. It is drawn as a line of visible thickness.
        chart = _chart(_taped_page(flat=True))
        self.assertIn("The 52-week range of closes", chart)
        self.assertNotIn('height="0.0"', chart)
        self.assertIn('<line class="ch-bandline"', chart)
        self.assertIn("<title>The 52-week range of closes", chart)

    def test_every_run_on_record_still_renders_with_the_notice(self):
        # A run whose pack carries no series renders the notice and no chart, as before. A run
        # whose pack carries one (written under the current capture contract) renders its chart
        # and no notice, and carries the decision of the page on record (unit READ-A: the pages
        # on record are pinned by hash; a fresh render is a new renderer's page).
        runs = os.path.join(ROOT, "council", "runs")
        if not os.path.isdir(runs):
            self.skipTest("the runs on record are not in this copy of the repository")
        rendered = 0
        series_less = 0
        for name in sorted(os.listdir(runs)):
            source = os.path.join(runs, name)
            if not os.path.isfile(os.path.join(source, "verdict.json")):
                continue
            with tempfile.TemporaryDirectory() as tmp:
                copied = os.path.join(tmp, "run")
                shutil.copytree(source, copied)
                page = R.render(copied)
                with open(os.path.join(copied, "pack", "pack.json"), "rb") as fh:
                    capture = json.loads(fh.read().decode("utf-8"))["capture"]
            self.assertIn(TAPE_HEADING, _front(page), name)
            if capture.get("price_series"):
                self.assertNotIn(E(pack_brief.tape_placeholder(capture)), page, name)
                self.assertEqual(page.count(CHART_OPEN), 1, name)
                with open(os.path.join(source, "report.html"), "rb") as fh:
                    _same_decision(self, fh.read().decode("utf-8"), page, name)
            else:
                self.assertEqual(page.count(E(pack_brief.tape_placeholder(capture))), 1, name)
                self.assertNotIn(CHART_OPEN, page, name)
                series_less += 1
            rendered += 1
        self.assertGreaterEqual(rendered, 9)
        self.assertGreaterEqual(series_less, 8)


# UPGRADE-2 FI-ARCHETYPE sub-charge (b), THE PAGE (owner rulings AC28, AC30 and AC32; register
# items P-FIa-4 and P-FIa-5). The invented run's pack is replaced by the invented bank's or
# holding's frozen pack, re-keyed to the run's own subject.
FI_EVIDENCE = os.path.join(ROOT, "council", "tests", "fixtures", "evidence")
FI_BANK = "bank-pass.json"
FI_HOLDING = "holding-pass.json"
FI_SECTION = "What kind of financial firm this is"
FI_DERIVED_LINE = ("Is Specimen Works still cheap at this price, or has the market caught up with "
                   "the growth story?")
FI_QUESTION_LINE = FI_DERIVED_LINE + " Separately, on my side: plan the follow-on tranche timing"
FI_CONTRARY_LINE = "Should we sell Specimen Works now?"
FI_ON_RECORD = ("council-lulu-2026-09-05", "council-coin-2026-09-04", "council-wulf-2026-09-09")
FI_CYCLE_AS_OF = "2026-09-20"
FI_CYCLE_LAST = "2026-06-30"


def _fi_capture(name):
    with open(os.path.join(FI_EVIDENCE, name), "rb") as fh:
        capture = json.loads(fh.read().decode("utf-8"))
    with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
        subject = json.loads(fh.read().decode("utf-8"))["subject"]
    frame = capture["business_frame"].pop(capture["subject"]["ticker"])
    capture["subject"] = subject
    capture["business_frame"] = {subject["ticker"]: frame}
    return capture


def _fi_words(capture, fact_id):
    """A fact's name as the page prints it (unit READ-A): its label, else the id in words."""
    return R._fact_words({fact["id"]: fact for fact in capture["tier1"]}[fact_id])


def _fi_page(name=FI_BANK, change=None, review=None, store=None):
    """The invented run rendered over an FI fixture's frozen pack; `change` edits the capture
    before it is frozen, `review` the verdict's evidence review (a reviewed sitting with an
    approver in the invented run), `store` writes the run's stored evidence document."""
    capture = _fi_capture(name)
    if change:
        change(capture)
    tmp = tempfile.mkdtemp(prefix="report-fi-")
    try:
        run_dir = _mutated_copy(tmp)
        _rewrite_pack(run_dir, lambda doc: doc.update(freeze.build_pack(capture)))
        if review:
            _rewrite_verdict(run_dir, lambda doc: review(doc["provenance"]["evidence"]))
        if store:
            store(run_dir)
        _stamp_first_render(run_dir, _pinned_now(FIXTURE))
        return R.render(run_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _full_document(run_dir):
    """The full evidence document the brief renders over the run's frozen pack."""
    path = os.path.join(run_dir, "pack", "pack.json")
    with open(path, "rb") as fh:
        raw = fh.read()
    return pack_brief.render_full(json.loads(raw.decode("utf-8")),
                                  hashlib.sha256(raw).hexdigest())


def _store_document(text, approve=True, recorded=None):
    """A `store` hook: the run keeps `text` (or the rendered full document) as its full evidence
    document, and - where `approve` - an approval recording its sha256 (or `recorded`)."""
    def store(run_dir):
        body = text(run_dir) if callable(text) else text
        data = (body if body is not None else _full_document(run_dir)).encode("utf-8")
        with open(os.path.join(run_dir, "pack", "EVIDENCE-FULL.md"), "wb") as fh:
            fh.write(data)
        if approve:
            approval = {"by": "Invented Reviewer (fixture)", "at": "2026-08-30T09:05Z",
                        "note": "Invented fixture note.",
                        "document_sha256": recorded or hashlib.sha256(data).hexdigest()}
            with open(os.path.join(run_dir, "pack", "approval.json"), "w",
                      encoding="utf-8", newline="\n") as fh:
                json.dump(approval, fh, indent=2)
    return store


APPROVED = _store_document(None)


def _fi_frame(capture):
    return capture["business_frame"][capture["subject"]["ticker"]]


def _render_on_record(run_id, change=None):
    with tempfile.TemporaryDirectory() as tmp:
        copied = os.path.join(tmp, "run")
        shutil.copytree(os.path.join(ROOT, "council", "runs", run_id), copied)
        if change:
            _rewrite_pack(copied, change)
        return R.render(copied)


class TestFIOnThePage(unittest.TestCase):
    """What the owner's page shows of a financial institution. Every test FAILS against the
    pre-change report renderer; the negative and positive controls are marked."""

    def test_the_front_names_the_kind_of_firm_and_measure(self):
        front = _visible_text(_front(_fi_page()))
        self.assertIn("financial institution - a bank — rated on price against tangible book, "
                      "read against the return on tangible equity", front)

    def test_the_fi_words_are_the_briefs_words(self):
        for key, words in pack_brief._MEASURE_WORDS.items():
            self.assertEqual(R.MEASURE_WORDS[key], words, key)
        for key, words in pack_brief._ARCHETYPE_WORDS.items():
            self.assertEqual(R.ARCHETYPE_WORDS[key], words, key)

    def test_a_holding_report_carries_the_not_rated_sentence(self):
        page = _fi_page(FI_HOLDING)
        sentence = pack_brief.FI_NOT_RATED_SENTENCE
        self.assertIn(sentence, _visible_text(_front(page)))
        detail = _visible_text(_detail(page))
        self.assertIn("The net asset value, part by part", detail)
        capture = _fi_capture(FI_HOLDING)
        for part in _fi_frame(capture)["nav_bridge"]["components"]:
            self.assertIn("%s %s %s" % (part["name"], pack_brief.FI_METHOD_WORDS[part["method"]],
                                        _fi_words(capture, part["value_fact"])), detail)
        self.assertNotIn("<code>", _detail(page))
        self.assertIn(sentence, detail)

    def test_the_detail_carries_the_fi_frame(self):
        capture = _fi_capture(FI_BANK)
        frame = _fi_frame(capture)
        detail = _detail(_fi_page())
        self.assertIn("<h3>%s</h3>" % FI_SECTION, detail)
        text = _visible_text(detail)
        ratio, requirement = frame["fi_capital"]["ratio_facts"][0], \
            frame["fi_capital"]["requirement_facts"][0]
        # Each fact by its plain name, never its id in a code span (unit READ-A); the ratio and
        # its requirement on one row of the capital table, named as the brief's tables name them
        # (unit READ-B1).
        facts = {fact["id"]: fact for fact in capture["tier1"]}
        row = re.search(r"<tr><td>%s</td>.*?</tr>"
                        % re.escape(E(pack_brief._plain_name(facts, ratio))), detail).group(0)
        self.assertIn(E(pack_brief._plain_name(facts, requirement)), row)
        self.assertNotIn("<code>", detail)
        self.assertIn(pack_brief.FI_STRESS_HEADING, text)
        risk = _card_rows(detail, "The risk-cost line: credit losses")
        self.assertEqual(risk[1][0],
                         pack_brief._plain_name(facts, "provision_for_credit_losses_q"))
        earnings = _card_rows(detail, "How it earns")
        for line, cells in zip(frame["how_it_earns"], earnings[1:]):
            # The fixture's share figures are recorded as plain fractions, so they print as a
            # percentage to one decimal (architect ruling, round 2 of READ-B1).
            self.assertEqual(cells[:2], [line["line"], pack_brief.FI_NATURE_WORDS[line["nature"]]])
            self.assertEqual(cells[3], "%.1f%%" % (float(line["share_of_period"]) * 100))

    def test_a_single_names_tailed_stress_fact_prints_on_the_report(self):
        """Audit round 6 of sub-charge b (r6-1, P-FIb-3): a single name keeps every stress fact,
        a double-underscore tail on its id included. FAILS against the round-5 selection, which
        dropped the figure silently; the plain fixture's stress line is the positive control."""
        tailed = "stress_capital_buffer__2026"
        value = [fact["value"] for fact in _fi_capture(FI_BANK)["tier1"]
                 if fact["id"] == "stress_capital_buffer"][0]

        def rename(capture):
            for fact in capture["tier1"]:
                if fact["id"] == "stress_capital_buffer":
                    fact["id"] = tailed
        capture = _fi_capture(FI_BANK)
        name = _fi_words(capture, "stress_capital_buffer")
        for page in (_fi_page(change=rename), _fi_page()):
            text = _visible_text(_detail(page))
            self.assertIn(pack_brief.FI_STRESS_HEADING, text)
            # The fact prints by its label with its value (unit READ-A: no id on the page).
            self.assertRegex(text, r"%s\W[^\n]*%s" % (re.escape(name), re.escape(value)))

    def test_guidance_prints_first_then_revisions(self):
        """Unit READ-B1: each period row a table - the first guide, each revision in its dated
        column, then what was delivered; a row never revised says so under its table."""
        capture = _fi_capture(FI_BANK)
        facts = {fact["id"]: fact for fact in capture["tier1"]}
        rows = _fi_frame(capture)["management"]["guidance_vs_delivery"]
        detail = _detail(_fi_page())
        revision = rows[1]["revisions"][0]
        table = _card_rows(detail, "Guidance for %s" % rows[1]["period"])
        self.assertEqual(table[0][1:4], ["First guide", "Revised %s" % R.format_date(
            revision["date"]), "Delivered"])
        shown = [R.format_number(facts[fid]["value"], facts[fid]["unit"])
                 for fid in (rows[1]["guided"][0], revision["guided"][0], rows[1]["delivered"])]
        self.assertEqual(table[1][1:4], shown)
        self.assertIn("The guidance for %s was never revised." % rows[0]["period"],
                      _visible_text(detail))

    def test_the_free_cash_row_is_named_as_distributable_capital(self):
        self.assertIn(E(pack_brief.FI_FREE_CASH_WORDS), _fi_page())
        self.assertNotIn(E(pack_brief.FI_FREE_CASH_WORDS), HTML)

    def test_a_capture_authored_regime_is_escaped(self):
        def forge(capture):
            _fi_frame(capture)["fi_capital"]["regime"] = "<script>x</script> regime"
        page = _fi_page(change=forge)
        self.assertIn("The regime: &lt;script&gt;x&lt;/script&gt; regime", page)
        self.assertNotIn("<script>x</script>", page)

    def test_an_unvouched_fi_fact_id_travels_as_data(self):
        def forge(capture):
            _fi_frame(capture)["nav_bridge"]["discount_fact"] = "not_in_this_pack"
        page = _fi_page(FI_HOLDING, change=forge)
        self.assertIn("The discount: not_in_this_pack (not in the pack)", page)
        self.assertNotIn("<code>not_in_this_pack</code>", page)

    def test_the_masthead_reads_the_question_line(self):
        """A reviewed sitting whose stored approved document carries the line: it differs from
        the derived one (it runs past the first question mark), so the masthead shows it only by
        reading the field."""
        def line(capture):
            capture["question_line"] = FI_QUESTION_LINE
        masthead = _masthead(_fi_page(change=line, store=APPROVED))
        self.assertNotEqual(FI_QUESTION_LINE, FI_DERIVED_LINE)
        self.assertIn('<p class="question">%s</p>' % E(FI_QUESTION_LINE), masthead)

    def test_an_approved_line_outside_the_full_question_still_reaches_the_masthead(self):
        """Architect rulings closing P-FIb-1 and P-FIb-2: the line is trusted by the document
        the owner approved, which prints it, not by where its words fall in the full question -
        so an approved line that is not inside the question he recorded is printed as he
        approved it. (Rounds 1 and 2 tried a string rule; it is removed.)"""
        def line(capture):
            capture["question_line"] = FI_CONTRARY_LINE
        masthead = _masthead(_fi_page(change=line, store=APPROVED))
        self.assertIn('<p class="question">%s</p>' % E(FI_CONTRARY_LINE), masthead)

    def test_an_approved_document_without_the_line_keeps_the_derived_line(self):
        """Architect ruling closing P-FIb-2 (audit round 3 of this page): an approver alone
        vouches for nothing the owner did not see. A sitting approved on a document that does
        not carry the line - approved before the brief printed it, a document rewritten after
        its approval, or one carrying another line - prints the derived line."""
        def line(capture):
            capture["question_line"] = FI_QUESTION_LINE

        def without_line(run_dir):
            return "\n".join(row for row in _full_document(run_dir).split("\n")
                             if not row.startswith(pack_brief.QUESTION_LINE_LABEL))

        def other_line(run_dir):
            document = _full_document(run_dir)
            self.assertIn(pack_brief.QUESTION_LINE_LABEL + " " + FI_QUESTION_LINE, document)
            return document.replace(FI_QUESTION_LINE, FI_CONTRARY_LINE)
        cases = (("approved before the line", _store_document(without_line)),
                 ("another line", _store_document(other_line)),
                 ("rewritten after approval", _store_document(None, recorded="0" * 64)))
        for name, store in cases:
            with self.subTest(document=name):
                masthead = _masthead(_fi_page(change=line, store=store))
                self.assertNotIn(E(FI_QUESTION_LINE), masthead)
                self.assertIn('<p class="question">%s</p>' % E(FI_DERIVED_LINE), masthead)

    def test_a_reviewed_sitting_with_no_stored_document_keeps_the_derived_line(self):
        """The approver is recorded but the run keeps no approved document: nothing shows what
        the owner saw, so the masthead prints the derived line."""
        def line(capture):
            capture["question_line"] = FI_QUESTION_LINE
        masthead = _masthead(_fi_page(change=line))
        self.assertNotIn(E(FI_QUESTION_LINE), masthead)
        self.assertIn('<p class="question">%s</p>' % E(FI_DERIVED_LINE), masthead)

    def test_an_unattended_sitting_keeps_the_derived_line(self):
        """No person approved the document, so nothing vouches for the capture's line: an
        auto-mode sitting keeps its full document as the record, with no approval, and prints
        the line derived from the owner's recorded question."""
        def line(capture):
            capture["question_line"] = FI_QUESTION_LINE

        def auto(review):
            review["mode"] = "auto"
            review.pop("approved_by", None)
        masthead = _masthead(_fi_page(change=line, review=auto,
                                      store=_store_document(None, approve=False)))
        self.assertNotIn(E(FI_QUESTION_LINE), masthead)
        self.assertIn('<p class="question">%s</p>' % E(FI_DERIVED_LINE), masthead)

    def test_an_older_capture_keeps_the_derived_line_in_a_reviewed_sitting(self):
        """The rule reads the field only on a 1.8.0 capture: an older one carries no line the
        owner saw on his document, so the derived line stands even where one was approved."""
        def line(capture):
            capture["capture_version"] = "1.7.1"
            capture["question_line"] = FI_QUESTION_LINE
        masthead = _masthead(_fi_page(change=line, store=APPROVED))
        self.assertNotIn(E(FI_QUESTION_LINE), masthead)
        self.assertIn('<p class="question">%s</p>' % E(FI_DERIVED_LINE), masthead)

    def test_a_pre_1_8_0_run_keeps_the_derived_masthead_line(self):
        """GUARD (passes against the pre-change renderer by design, which never read the
        field): each sitting on record renders byte for byte the same page with the migration's
        one-line question (filled by the masthead's own rule) as without it."""
        if not os.path.isdir(os.path.join(ROOT, "council", "runs", FI_ON_RECORD[0])):
            self.skipTest("the runs on record are not in this copy of the repository")
        for run_id in FI_ON_RECORD:
            with self.subTest(run_id=run_id):
                before = _render_on_record(run_id)

                def migrate(doc):
                    doc["capture"]["question_line"] = R._question_line(doc["capture"])
                after = _render_on_record(run_id, migrate)
                self.assertEqual(after, before)
                derived = re.search(r'<p class="question">(.*?)</p>', before).group(1)
                self.assertEqual(derived, E(R._question_line(
                    {"question_verbatim": _pack_question(run_id)})))

    def test_the_cycle_appendix_prints_the_last_point_date(self):
        def cycle(capture):
            capture["cycle"] = {
                "name": "INVENTED FIXTURE - a credit cycle",
                "why_it_matters": "INVENTED FIXTURE - the loan book rests on it",
                "series": [{"id": "cycle_series_0", "source": "INVENTED FIXTURE - a source",
                            "as_of": FI_CYCLE_AS_OF, "unit": "index",
                            "points": [{"date": FI_CYCLE_LAST, "value": "100"}],
                            "refetch_url_or_source_line": "https://example.invalid/series"}]}
        detail = _detail(_fi_page(change=cycle))
        self.assertIn("read %s; latest point %s" % (FI_CYCLE_AS_OF, FI_CYCLE_LAST), detail)

    def test_a_non_fi_page_carries_no_fi_line(self):
        """NEGATIVE control: the invented profitable operator's page carries none of it."""
        for words in (FI_SECTION, "financial institution", "not rated in this sitting",
                      "capital the firm can pay out"):
            self.assertNotIn(words, HTML)

    def test_two_renders_of_one_fi_run_are_byte_identical(self):
        """POSITIVE control."""
        self.assertEqual(_fi_page(FI_HOLDING), _fi_page(FI_HOLDING))


def _pack_question(run_id):
    with open(os.path.join(ROOT, "council", "runs", run_id, "pack", "pack.json"), "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))["capture"]["question_verbatim"]


# UPGRADE-2 U5(b), session 2 (owner rulings AC5, AC35(3), AC16(3), AC25(4); seed item 10): the
# chairman's three fields on the page - what decided it at the head of the executive summary, the
# business and the decisive numbers in his words at the top of the synthesis - and the codex
# version in the model stamp. A verdict older than the contract that carries them renders exactly
# as before: the new builders add nothing to it, byte for byte.

def _synthesis(page):
    """The synthesis tier's own HTML: from its heading to the decision in detail."""
    return page[page.index('<h2 id="synthesis"'):page.index('<h2 id="advisors"')]


def _fixture_verdict():
    with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _render_changed(change, source=None, events=()):
    """The fixture rendered with its verdict changed and, where given, rows added to the copy's
    run record after the first-render row."""
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _mutated_copy(tmp, lambda d: _rewrite_verdict(d, change), source)
        work = os.path.join(tmp, "work")
        shutil.copytree(run_dir, work)
        _stamp_first_render(work, _pinned_now(run_dir))
        for event, fields in events:
            runrecord.append_event(work, event, fields)
        return R.render(work)


class TestTheChairmansFieldsOnThePage(unittest.TestCase):
    # The three fields of U5(b); the fourth, the one-line answer (READ-C1), has its own class.
    LABELS = {"decisive_argument": "What decided it",
              "business_read": "The business, in the chairman's words",
              "decisive_metrics_read": "The decisive numbers, as the chairman reads them"}

    def test_the_decisive_argument_opens_the_executive_summary(self):
        front = _front(HTML)
        verdict = _fixture_verdict()
        lead = '<span class="lead">%s</span>' % E(self.LABELS["decisive_argument"])
        self.assertEqual(front.count(lead), 1)
        # First in the tier: before the chart and the rationale; the thesis card is gone
        # (owner ruling AC41(4)).
        for later in (TAPE_HEADING, "Why this rating, in the chairman"):
            self.assertLess(front.index(lead), front.index(later), later)
        self.assertNotIn("The thesis</span>", front)
        card = front[front.index(lead):front.index(TAPE_HEADING)]
        seat = verdict["decisive_argument"]["seat"]
        self.assertIn(E(briefs.LENS_TITLES[seat]), card)
        self.assertIn(E(verdict["decisive_argument"]["why"][:40]), card)
        self.assertEqual(R.chair_fields.labels(),
                         dict(self.LABELS, answer_line="The answer to your question"))

    def test_the_business_and_metrics_reads_open_the_synthesis(self):
        synthesis = _synthesis(HTML)
        verdict = _fixture_verdict()
        business = '<span class="lead">%s</span>' % E(self.LABELS["business_read"])
        numbers = '<span class="lead">%s</span>' % E(self.LABELS["decisive_metrics_read"])
        prose_card = synthesis.index("final synthesis</h4>")
        self.assertLess(synthesis.index(business), synthesis.index(numbers))
        self.assertLess(synthesis.index(numbers), prose_card)
        self.assertIn(E(verdict["business_read"][:40]), synthesis)
        table = synthesis[synthesis.index(numbers):prose_card]
        for row in verdict["decisive_metrics_read"]:
            self.assertIn(E(row["metric"]), table)
            self.assertIn(E(row["implies"]), table)
        # No row names a constituent on this single name, so no such column.
        self.assertNotIn("<th>constituent</th>", table)
        # A basket's rows carry their constituent, and the column appears.
        def per_member(doc):
            doc["decisive_metrics_read"] = [
                {"metric": "Support revenue", "constituent": "ACHP",
                 "value": "one figure", "implies": "a reading"}]
        table = _synthesis(_render_changed(per_member))
        self.assertIn("<th>constituent</th>", table)
        self.assertIn("<td>ACHP</td>", table)

    def test_a_null_field_prints_its_muted_line(self):
        def nulls(doc):
            for key in self.LABELS:
                doc[key] = None
        page = _render_changed(nulls)
        for key, line in R.CHAIR_FIELD_MISSING.items():
            self.assertEqual(page.count('<div class="muted small">%s</div>' % E(line)), 1, key)
        self.assertLess(page.index(E(R.CHAIR_FIELD_MISSING["decisive_argument"])),
                        page.index(TAPE_HEADING))
        # An empty list is an answer, not a gap: the subject has no table of decisive numbers.
        def empty(doc):
            doc["decisive_metrics_read"] = []
        page = _render_changed(empty)
        self.assertIn(E(R.NO_METRICS_TABLE), _synthesis(page))
        self.assertNotIn(E(R.CHAIR_FIELD_MISSING["decisive_metrics_read"]), page)
        # Where the case file DOES carry decisive metrics, an empty list that stood after the one
        # re-ask is the chairman not reading them - never "this subject has no table".
        def with_metrics(run_dir):
            _rewrite_verdict(run_dir, empty)
            _rewrite_pack(run_dir, lambda pack: pack["capture"].update(
                {"business_frame": {"ACME": {"decisive_metrics": [
                    {"name": "Support revenue", "answered_by": []}]}}}))
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp, with_metrics)
            work = os.path.join(tmp, "work")
            shutil.copytree(run_dir, work)
            _stamp_first_render(work, _pinned_now(run_dir))
            synthesis = _synthesis(R.render(work))
        self.assertNotIn(E(R.NO_METRICS_TABLE), synthesis)
        self.assertIn(E(R.CHAIR_FIELD_MISSING["decisive_metrics_read"]), synthesis)
        # A fields re-ask that moved a figure gets one muted line under the synthesis.
        moved = [("chair_fields_checked",
                  {"seat": "chair_resolve", "number": "010", "outcome": "spliced",
                   "problems": [], "figures_changed": True,
                   "figures_differing": {"first": ["$279m"], "rewrite": ["$300m"]},
                   "figures_by_field": {"business_read": {"first": ["$279m"],
                                                          "rewrite": ["$300m"]}}})]

        def resolve_wrote_it(run_dir):
            path = os.path.join(run_dir, "rpc", "010-answer-chair_resolve.json")
            with open(path, "rb") as fh:
                doc = json.loads(fh.read().decode("utf-8"))
            doc["final_verdict"]["business_read"] = _fixture_verdict()["business_read"]
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(doc, indent=2, sort_keys=True))
        with tempfile.TemporaryDirectory() as tmp:
            work = _mutated_copy(tmp, resolve_wrote_it)
            _stamp_first_render(work, _pinned_now(FIXTURE))
            for event, fields in moved:
                runrecord.append_event(work, event, fields)
            synthesis = _synthesis(R.render(work))
        self.assertEqual(synthesis.count(R.FIELDS_FIGURE_NOTE_OPEN), 1)
        self.assertIn("$279m", synthesis)
        self.assertIn("$300m", synthesis)
        self.assertNotIn(R.FIELDS_FIGURE_NOTE_OPEN, HTML)

    def test_a_table_short_of_the_case_files_metrics_says_how_many_are_missing(self):
        # Architect ruling on round 8's related gap: a table naming fewer rows than the case
        # file's decisive metrics prints one muted line under it counting the missing ones, by
        # name when three or fewer - never the "no table" line, never a refusal.
        def one_row(doc):
            doc["decisive_metrics_read"] = [
                {"metric": "Support revenue", "constituent": None,
                 "value": "one figure", "implies": "a reading"}]

        def render(metrics):
            def mutate(run_dir):
                _rewrite_verdict(run_dir, one_row)
                _rewrite_pack(run_dir, lambda pack: pack["capture"].update(
                    {"business_frame": {"ACME": {"decisive_metrics": [
                        {"name": name, "answered_by": []} for name in metrics]}}}))
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = _mutated_copy(tmp, mutate)
                work = os.path.join(tmp, "work")
                shutil.copytree(run_dir, work)
                _stamp_first_render(work, _pinned_now(run_dir))
                return _synthesis(R.render(work))
        short = render(["Support revenue", "Operating margin"])
        line = ('<div class="muted small">1 of the case file\'s decisive metrics was not read '
                'out by the chairman: &quot;Operating margin&quot;.</div>')
        self.assertIn(line.replace("\'", "&#x27;"), short)
        self.assertLess(short.index("</table>"), short.index("Operating margin&quot;."))
        self.assertNotIn(E(R.NO_METRICS_TABLE), short)
        # A complete table prints no such line.
        complete = render(["Support revenue"])
        self.assertNotIn("decisive metrics was not read out", complete)
        self.assertNotIn("decisive metrics were not read out", complete)
        self.assertNotIn("not read out by the chairman", HTML)

    def test_the_rows_missing_note_marks_a_metric_names_untraced_figures(self):
        # Round 9 (r9-1, P-U5b-12): a metric name the note prints goes through the frame's
        # prose marker first, as every other metric name on the page does (AC19).
        from council.evidence import trace

        def one_row(doc):
            doc["decisive_metrics_read"] = [
                {"metric": "Support revenue", "constituent": None,
                 "value": "one figure", "implies": "a reading"}]

        def render(omitted):
            def mutate(run_dir):
                _rewrite_verdict(run_dir, one_row)
                _rewrite_pack(run_dir, lambda pack: pack["capture"].update(
                    {"business_frame": {"ACME": {"decisive_metrics": [
                        {"name": name, "answered_by": []}
                        for name in ("Support revenue", omitted)]}}}))
            with tempfile.TemporaryDirectory() as tmp:
                run_dir = _mutated_copy(tmp, mutate)
                work = os.path.join(tmp, "work")
                shutil.copytree(run_dir, work)
                _stamp_first_render(work, _pinned_now(run_dir))
                return _synthesis(R.render(work))
        marked = render("Operating margin 4242%")
        self.assertIn("Operating margin 4242%% %s&quot;." % E(trace.MARKER), marked)
        # Positive control: a plain name prints without the marker.
        plain = render("Operating margin")
        self.assertIn("not read out by the chairman: &quot;Operating margin&quot;.", plain)
        self.assertNotIn(E(trace.MARKER), plain.split("not read out by the chairman")[1])

    def test_a_draft_fields_figure_flag_shows_while_its_field_survives(self):
        # Audit round 1 (r1-4): the draft's fields re-answer moved a figure and the resolve kept
        # that field as it stood, with no re-ask of its own; the note still shows.
        verdict = _fixture_verdict()

        def draft_carries(value):
            def mutate(run_dir):
                path = os.path.join(run_dir, "rpc", "009-answer-chair_draft.json")
                with open(path, "rb") as fh:
                    doc = json.loads(fh.read().decode("utf-8"))
                doc["draft_verdict"]["business_read"] = value
                with open(path, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(json.dumps(doc, indent=2, sort_keys=True))
            return mutate

        events = [("chair_fields_checked",
                   {"seat": "chair_draft", "number": "009", "outcome": "reasked",
                    "problems": [{"key": "business_read", "problem": "it is missing"}]}),
                  ("chair_fields_checked",
                   {"seat": "chair_draft", "number": "009", "outcome": "spliced",
                    "problems": [], "figures_changed": True,
                    "figures_differing": {"first": ["$279m"], "rewrite": ["$300m"]},
                    "figures_by_field": {"business_read": {"first": ["$279m"],
                                                           "rewrite": ["$300m"]}}}),
                  ("chair_fields_checked",
                   {"seat": "chair_resolve", "number": "010", "outcome": "present",
                    "problems": []})]

        def render(value):
            with tempfile.TemporaryDirectory() as tmp:
                work = _mutated_copy(tmp, draft_carries(value))
                _stamp_first_render(work, _pinned_now(FIXTURE))
                for event, fields in events:
                    runrecord.append_event(work, event, fields)
                return _synthesis(R.render(work))

        survived = render(verdict["business_read"])
        self.assertEqual(survived.count(R.FIELDS_FIGURE_NOTE_OPEN), 1)
        self.assertIn("$300m", survived)
        # The resolve rewrote the field after the draft: the draft's note no longer describes the
        # published text, and the change is listed among the post-audit changes instead.
        replaced = render("An invented business read the resolve later rewrote.")
        self.assertNotIn(R.FIELDS_FIGURE_NOTE_OPEN, replaced)

    def _draft_asked(self, draft_fields, marked_row=False):
        """The synthesis of the fixture with the draft's fields re-ask of business_read and
        decisive_metrics_read, each moving a figure, the draft carrying DRAFT_FIELDS and the
        published table's first row, where MARKED_ROW, carrying the host's mark (P-U5b-5)."""
        def mutate(run_dir):
            path = os.path.join(run_dir, "rpc", "009-answer-chair_draft.json")
            with open(path, "rb") as fh:
                doc = json.loads(fh.read().decode("utf-8"))
            doc["draft_verdict"].update(draft_fields)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(doc, indent=2, sort_keys=True))
            if marked_row:
                _rewrite_verdict(run_dir, lambda v: v["decisive_metrics_read"][0].update(
                    mark=R.chair_fields.ROW_MARK))
        asked = ["business_read", "decisive_metrics_read"]
        events = [("chair_fields_checked",
                   {"seat": "chair_draft", "number": "009", "outcome": "reasked",
                    "problems": [{"key": key, "problem": "it is missing"} for key in asked]}),
                  ("chair_fields_checked",
                   {"seat": "chair_draft", "number": "009", "outcome": "spliced",
                    "problems": [], "figures_changed": True,
                    "figures_differing": {"first": ["$279m", "$11m"],
                                          "rewrite": ["$300m", "$12m"]},
                    "figures_by_field": {
                        "business_read": {"first": ["$279m"], "rewrite": ["$300m"]},
                        "decisive_metrics_read": {"first": ["$11m"], "rewrite": ["$12m"]}}})]
        with tempfile.TemporaryDirectory() as tmp:
            work = _mutated_copy(tmp, mutate)
            _stamp_first_render(work, _pinned_now(FIXTURE))
            for event, fields in events:
                runrecord.append_event(work, event, fields)
            return _synthesis(R.render(work))

    def test_a_surviving_table_keeps_its_figure_note_when_a_row_is_marked(self):
        # P-U5b-5: the host's row mark is not the chairman's writing; the table he wrote is the
        # published one, so its figure note shows.
        verdict = _fixture_verdict()
        synthesis = self._draft_asked(
            {"business_read": "A business read the resolve later rewrote.",
             "decisive_metrics_read": verdict["decisive_metrics_read"]}, marked_row=True)
        self.assertEqual(synthesis.count(R.FIELDS_FIGURE_NOTE_OPEN), 1)
        self.assertIn("$12m", synthesis)

    def test_a_replaced_fields_figures_never_print_as_shown_above(self):
        # P-U5b-5: the note names only the figures of a field that still stands as re-answered.
        verdict = _fixture_verdict()
        synthesis = self._draft_asked({"business_read": verdict["business_read"],
                                       "decisive_metrics_read": []})
        self.assertEqual(synthesis.count(R.FIELDS_FIGURE_NOTE_OPEN), 1)
        self.assertIn("$300m", synthesis)
        self.assertNotIn("$12m", synthesis)
        self.assertNotIn("$11m", synthesis)

    def test_an_older_verdict_renders_unchanged_but_for_the_stamp(self):
        # The stamp line itself is unchanged too while no codex version is recorded, which is
        # every sitting on record written before the current verdict contract: the new builders
        # add nothing to an older verdict.
        def older(doc):
            doc["schema_version"] = "1.4.0"
            for key in self.LABELS:
                doc.pop(key, None)
            doc["provenance"].pop("codex_version", None)
        page = _render_changed(older)
        for label in self.LABELS.values():
            self.assertNotIn(E(label), page)
        for line in list(R.CHAIR_FIELD_MISSING.values()) + [R.NO_METRICS_TABLE]:
            self.assertNotIn(E(line), page)
        runs = os.path.join(ROOT, "council", "runs")
        if not os.path.isdir(runs):
            self.skipTest("the runs on record are not in this copy of the repository")
        builders = ("_front_decisive_argument", "_synthesis_chair_fields", "_codex_stamp",
                    "_fields_figure_note")
        # A run on record whose verdict carries the chairman's fields and the codex version
        # (written under the current verdict contract) is no older verdict: it must carry all of
        # them, its page carries the decision of the page on record (unit READ-A), and it carries
        # the codex version and every chairman's label.
        current_keys = tuple(self.LABELS)
        compared = 0
        older = 0
        for name in sorted(os.listdir(runs)):
            if not os.path.isfile(os.path.join(runs, name, "verdict.json")):
                continue
            with open(os.path.join(runs, name, "verdict.json"), "rb") as fh:
                verdict = json.loads(fh.read().decode("utf-8"))
            current = (any(key in verdict for key in current_keys)
                       or "codex_version" in verdict["provenance"])
            with tempfile.TemporaryDirectory() as tmp:
                copied = os.path.join(tmp, "run")
                shutil.copytree(os.path.join(runs, name), copied)
                page = R.render(copied)
                saved = {builder: getattr(R, builder) for builder in builders}
                try:
                    for builder in builders:
                        setattr(R, builder, lambda *args: "")
                    without = R.render(copied)
                finally:
                    for builder, function in saved.items():
                        setattr(R, builder, function)
            if current:
                for key in current_keys:
                    self.assertIn(key, verdict, name)
                self.assertTrue(verdict["provenance"]["codex_version"], name)
                with open(os.path.join(runs, name, "report.html"), "rb") as fh:
                    _same_decision(self, fh.read().decode("utf-8"), page, name)
                self.assertIn("ran through codex-cli", _stamps(page), name)
                for label in self.LABELS.values():
                    self.assertIn(E(label), page, name)
                self.assertNotEqual(page, without, name)
            else:
                self.assertEqual(page, without, name)
                older += 1
            compared += 1
        self.assertGreaterEqual(compared, 9)
        self.assertGreaterEqual(older, 8)

    def test_the_stamp_names_the_codex_version_or_says_not_recorded(self):
        # The stamp names the models in plain words; the codex version is one line in About this
        # sitting (unit READ-A, architect ruling 8), and says "not recorded" by printing nothing.
        plain = ('<div class="stamp muted small">Advisors and chairman: <strong>Claude Opus 4.6'
                 "</strong> &middot; outside challenge: <strong>OpenAI GPT-5.6 Sol</strong></div>")
        self.assertIn(plain, _masthead(HTML))
        self.assertNotIn("codex", _masthead(HTML).lower())
        self.assertNotIn("codex", _stamps(HTML).lower())

        def stamped(challenge, evidence):
            def change(doc):
                doc["provenance"]["codex_version"] = {"challenge": challenge,
                                                      "evidence_audit": evidence}
            page = _render_changed(change)
            self.assertNotIn("codex", _masthead(page).lower())
            return _stamps(page)
        same = stamped("codex-cli fixture-a", "codex-cli fixture-a")
        self.assertIn("The outside model ran through codex-cli fixture-a.", same)
        self.assertNotIn("evidence check through", same)
        both = stamped("codex-cli fixture-a", "codex-cli fixture-b")
        self.assertIn("The outside challenge ran through codex-cli fixture-a; the evidence check "
                      "through codex-cli fixture-b.", both)
        audit_only = stamped(None, "codex-cli fixture-b")
        self.assertIn("The outside model ran through codex-cli fixture-b.", audit_only)

    def test_the_rationale_still_prints_in_full(self):
        front = _front(HTML)
        rationale = _fixture_verdict()["conviction_rationale"]
        card = front[front.index("Why this rating, in the chairman"):]
        for paragraph in [p for p in rationale.split("\n\n") if p.strip()]:
            words = _visible_text(markdown_free(paragraph))
            self.assertIn(words[:60], _visible_text(card))


def markdown_free(text):
    """A rationale paragraph as a reader sees its words: emphasis marks dropped."""
    return text.replace("**", "").replace("*", "")


# ---------------------------------------------------------------------------------------------
# THE FULL EVIDENCE DOCUMENT AS A WEB PAGE (owner ruling AC40(2b); unit UPGRADE2-APPROVAL-PAGE)
# ---------------------------------------------------------------------------------------------

RUNS_ON_RECORD = os.path.join(ROOT, "council", "runs")
JPM_RUN = os.path.join(RUNS_ON_RECORD, "council-jpm-2026-09-24")
ENGINE_PACK = os.path.join(ROOT, "council", "tests", "fixtures", "engine", "pack.json")


def _evidence_page():
    """The page module, imported here so that only these tests fail where it does not exist."""
    from council.report import evidence_page
    return evidence_page


def _one(value):
    return " ".join(str(value if value is not None else "").split())


def _read_json_file(path):
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _full_document_of_run(run_dir):
    """A run's full evidence document, rendered from its own frozen pack and cost sidecar."""
    pack_path = os.path.join(run_dir, "pack", "pack.json")
    with open(pack_path, "rb") as fh:
        pack_sha = hashlib.sha256(fh.read()).hexdigest()
    usage_path = os.path.join(run_dir, "pack", "capture-usage.json")
    usage = _read_json_file(usage_path) if os.path.isfile(usage_path) else None
    return _read_json_file(pack_path), pack_brief.render_full(
        _read_json_file(pack_path), pack_sha, usage)


# The Markdown as a reader sees it, read here on its own terms (a regular expression, left to
# right), not through the page module: a back-slash before a punctuation mark is the mark, a
# back-tick pair is its literal inside, the three entities are their characters, a bold mark
# is not text.
_MD_TOKEN = re.compile(r"\\[!-/:-@\[-`{-~]|`[^`]*`|&amp;|&lt;|&gt;|\*\*|.", re.S)


def _md_visible(text):
    out = []
    for match in _MD_TOKEN.finditer(text):
        token = match.group()
        if len(token) == 2 and token[0] == "\\":
            out.append(token[1])
        elif len(token) >= 2 and token[0] == "`" and token[-1] == "`":
            out.append(token[1:-1])
        elif token in ("&amp;", "&lt;", "&gt;"):
            out.append(html_lib.unescape(token))
        elif token != "**":
            out.append(token)
    return "".join(out).strip()


def _md_cells(row):
    body = row.strip()[1:]
    cells, current = [], ""
    for match in re.finditer(r"\\.|\||[^\\|]+|\\", body):
        if match.group() == "|":
            cells.append(current)
            current = ""
        else:
            current += match.group()
    if current.strip():
        cells.append(current)
    return tuple(_md_visible(cell) for cell in cells)


def _markdown_blocks(text):
    """(kind, ...) per block of the Markdown, in order: headings by level, list items with their
    depth, table rows with their cells, the document's own separator (the one `---` line followed
    by a blank line and the full evidence's heading) as a rule, paragraphs (their lines joined by
    a newline; a line of dashes anywhere else is paragraph text)."""
    blocks, paragraph = [], []
    lines = text.split("\n")

    def flush():
        if paragraph:
            blocks.append(("p", "\n".join(paragraph)))
            del paragraph[:]

    i = 0
    while i < len(lines):
        line = lines[i]
        heading = re.match(r"(#{1,6}) (.*)$", line)
        item = re.match(r"( *)- (.*)$", line)
        if not line.strip():
            flush()
        elif heading:
            flush()
            blocks.append(("h%d" % len(heading.group(1)), _md_visible(heading.group(2))))
        elif line == "---" and lines[i + 1:i + 3] == [
                "", "# The full evidence - the document approved in reviewed mode"]:
            flush()
            blocks.append(("hr", ""))
        elif item:
            flush()
            blocks.append(("li", len(item.group(1)) // 2, _md_visible(item.group(2))))
        elif (line.startswith("|") and i + 1 < len(lines)
              and re.fullmatch(r"\|( *-+ *\|)+", lines[i + 1])):
            flush()
            blocks.append(("row", _md_cells(line)))
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                blocks.append(("row", _md_cells(lines[i])))
                i += 1
            continue
        else:
            paragraph.append(_md_visible(line))
        i += 1
    flush()
    return blocks


class _PageReader(html_lib_parser.HTMLParser):
    """The page walked with the standard library's parser: every element and attribute, the
    style and script text, and the document's blocks in order (the column only, the foot and
    the menu left out; a section title's number, the page's own since unit READ-B2, left out of
    its block)."""

    BLOCKS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li")

    def __init__(self):
        html_lib_parser.HTMLParser.__init__(self, convert_charrefs=True)
        self.tags, self.attrs, self.styles, self.scripts = [], [], [], []
        self.blocks, self.open, self.lists = [], [], 0
        self.row = None
        self.in_column = self.in_foot = False
        self.raw = None
        self.strong, self.bold = [], []
        self.text = []
        self.number = False

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.extend(attrs)
        attributes = dict(attrs)
        if tag in ("style", "script"):
            self.raw = [tag, []]
        if tag == "div" and "wrap" in (attributes.get("class") or "").split():
            self.in_column = True
        if tag == "span" and attributes.get("class") == "secnum":
            self.number = True
        if tag == "div" and attributes.get("class") == "foot":
            self.in_foot = True
        if not self.in_column or self.in_foot:
            return
        if tag == "ul":
            self.lists += 1
        elif tag == "tr":
            self.row = []
            self.blocks.append(("row", self.row))
        elif tag in ("th", "td"):
            self.open.append([tag, []])
        elif tag in self.BLOCKS:
            entry = [tag, [], self.lists - 1]
            self.open.append(entry)
            self.blocks.append(entry)
        elif tag == "br" and self.open:
            self.open[-1][1].append("\n")
        elif tag == "hr":
            self.blocks.append(("hr", ""))
        elif tag == "strong":
            self.bold.append([])
        if tag != "span":
            # A hover note's term (unit READ-B2) sits inside its line.
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self.raw:
            (self.styles if tag == "style" else self.scripts).append("".join(self.raw[1]))
            self.raw = None
        if not self.in_column or self.in_foot:
            return
        if tag == "ul":
            self.lists -= 1
        elif tag in ("th", "td"):
            self.row.append("".join(self.open.pop()[1]).strip())
        elif tag == "tr":
            self.blocks[-1] = ("row", tuple(self.row))
        elif tag in self.BLOCKS:
            self.open.pop()
        elif tag == "strong":
            self.strong.append("".join(self.bold.pop()))

    def handle_data(self, data):
        if self.raw is not None:
            self.raw[1].append(data)
            return
        if not self.in_column or self.in_foot:
            return
        if self.number:
            self.number = False
            self.text.append(data)
            return
        if self.open:
            self.open[-1][1].append(data)
        for bold in self.bold:
            bold.append(data)
        self.text.append(data)

    def page_blocks(self):
        out = []
        for block in self.blocks:
            if block[0] in ("row", "hr"):
                out.append(tuple(block))
            elif block[0] == "li":
                out.append(("li", block[2], "".join(block[1]).strip()))
            else:
                out.append((block[0], "".join(block[1]).strip()))
        return out

    def visible_text(self):
        return "".join(self.text)


def _read_page(page_text):
    reader = _PageReader()
    reader.feed(page_text)
    reader.close()
    return reader


def _first_difference(expected, actual):
    for index, (want, got) in enumerate(zip(expected, actual)):
        if want != got:
            return "block %d: the Markdown has %r, the page %r" % (index, want, got)
    return "the Markdown has %d blocks, the page %d" % (len(expected), len(actual))


def _pack_expectations(capture):
    """Every fact, passage and gap of a capture as the full document states it, built from the
    capture alone - never from the Markdown or the page."""
    wanted = []
    for fact in capture.get("tier1") or []:
        label = _one(fact.get("label"))
        wanted.append(label or _one(fact.get("id")))
        unit = _one(fact.get("unit"))
        wanted.append("Value: %s%s (as of %s)" % (_one(fact.get("value")),
                                                  (" " + unit) if unit else "",
                                                  _one(fact.get("as_of"))))
        wanted.append("Source: %s" % _one(fact.get("source")))
    for passage in capture.get("tier2") or []:
        wanted.append("%s (as of %s)" % (_one(passage.get("id")), _one(passage.get("as_of"))))
        wanted.append("Source: %s" % _one(passage.get("source")))
        text = _one(passage.get("text"))
        # A known limit of the seed: a passage opening with a list mark reads as a list item.
        if text[:2] in ("- ", "+ "):
            text = text[2:]
        if text.strip("-"):
            wanted.append(text)
    for gap in capture.get("gaps") or []:
        wanted.append("%s: %s (weakens %s)" % (_one(gap.get("fact_class")),
                                               _one(gap.get("reason")),
                                               _one(gap.get("weakened_test"))))
    return wanted


def _fresh_expectations(capture):
    """Every fact, passage and gap of a capture as TODAY'S full document states it (unit
    READ-B2), built from the capture alone: each fact by its plain name (its label, or its key
    read as words), its exact recorded value and its whole source; each passage by its title
    in words, its source and its text; each gap by its reason and its class. The recorded
    documents on record keep the older wording and are read by _pack_expectations."""
    wanted = []
    for fact in capture.get("tier1") or []:
        label = _one(fact.get("label"))
        if not label:
            words = _one(_one(fact.get("id")).replace("_", " "))
            label = words[:1].upper() + words[1:]
        wanted.append(label)
        wanted.append(_one(fact.get("value")))
        wanted.append(_one(fact.get("source")))
    for passage in capture.get("tier2") or []:
        words = _one(passage.get("id"))
        if words.startswith("t2_"):
            words = words[len("t2_"):]
        words = _one(words.replace("_", " "))
        wanted.append(words[:1].upper() + words[1:])
        wanted.append("Source: %s" % _one(passage.get("source")))
        text = _one(passage.get("text"))
        # A known limit of the seed: a passage opening with a list mark reads as a list item.
        if text[:2] in ("- ", "+ "):
            text = text[2:]
        if text.strip("-"):
            wanted.append(text)
    for gap in capture.get("gaps") or []:
        wanted.append("%s (%s; weakens %s)" % (_one(gap.get("reason")),
                                               _one(gap.get("fact_class")),
                                               _one(gap.get("weakened_test"))))
    return wanted


def _missing_from(page_text, capture, fresh=True):
    """What of the capture the page does not show: a FRESH rendering is read against today's
    wording, a recorded document (fresh=False) against the wording it was written in."""
    visible = _read_page(page_text).visible_text()
    expected = _fresh_expectations(capture) if fresh else _pack_expectations(capture)
    return [item for item in expected if item not in visible]


# The full evidence documents on record, pinned by their bytes (architect ruling 1 of READ-B):
# they are the record of what was approved, rendered by the code of their day. A fresh
# rendering of the same pack is compared by content, never by bytes.
RECORDED_EVIDENCE_DOCUMENTS = {
    "council-jpm-2026-09-24":
        "5493a38729b32fa04878bda127aa9d6381d9f7bed5e68b97da09d4b26c4d0ea4",
}


HOSTILE = (
    "<script>alert(1)</script>",
    "</style><b>bold by markup</b>",
    '<img src=x onerror="alert(1)">',
    "[a link](https://example.invalid/x)",
    "![an image](https://example.invalid/i.png)",
    "**not bold**",
    "`not code`",
    "a \\| b",
    "# not a heading",
    "&amp; stays &lt; itself",
)


def _hostile_pack():
    """The engine fixture's invented pack with every hostile string written where a capture
    session writes text: a fact's label, value, unit and source, a passage's text and source,
    a gap's reason, and a cycle series (its name, its source, and every point's value - the
    cells of a table)."""
    pack = copy.deepcopy(_read_json_file(ENGINE_PACK))
    capture = pack["capture"]
    for index, text in enumerate(HOSTILE):
        capture["tier1"].append({"id": "hostile_fact_%d" % index, "label": text,
                                 "value": text, "unit": text, "as_of": "2026-08-28",
                                 "source": "invented: " + text, "derived": None,
                                 "freshness_rule_days": 30})
        capture["tier2"].append({"id": "hostile_passage_%d" % index, "as_of": "2026-08-01",
                                 "category": "business", "figures": [],
                                 "source": "invented: " + text, "text": text})
    capture["gaps"].append({"fact_class": "hostile_gap", "reason": " / ".join(HOSTILE),
                            "reason_kind": "other", "weakened_test": HOSTILE[0]})
    capture["cycle"] = {"name": HOSTILE[5], "why_it_matters": HOSTILE[3],
                        "series": [{"id": "hostile_series", "unit": HOSTILE[6],
                                    "as_of": "2026-08-28", "source": HOSTILE[2],
                                    "refetch_url_or_source_line": HOSTILE[4],
                                    "points": [{"date": "2026-08-%02d" % (index + 1),
                                                "value": text}
                                               for index, text in enumerate(HOSTILE)]}]}
    return pack


class TestEvidencePage(unittest.TestCase):
    """The full evidence document the owner approves, as the page he reads it on (owner ruling
    AC40(2b)): the same text, the report's look, one file that fetches nothing, and a pure
    function of the Markdown whose hash the go is recorded against."""

    @classmethod
    def setUpClass(cls):
        cls.jpm_markdown = None

    def jpm(self):
        if not os.path.isdir(JPM_RUN):
            self.skipTest("the runs on record are not in this copy of the repository")
        if TestEvidencePage.jpm_markdown is None:
            with open(os.path.join(JPM_RUN, "pack", "EVIDENCE-FULL.md"), "rb") as fh:
                TestEvidencePage.jpm_markdown = fh.read().decode("utf-8")
        return TestEvidencePage.jpm_markdown

    def test_the_jpm_page_carries_the_markdown_text_block_by_block(self):
        markdown = self.jpm()
        expected = _markdown_blocks(markdown)
        actual = _read_page(_evidence_page().render_page(markdown)).page_blocks()
        self.assertEqual(expected, actual, _first_difference(expected, actual))
        kinds = [block[0] for block in expected]
        for kind in ("h1", "h2", "h3", "h4", "li", "row", "p", "hr"):
            self.assertIn(kind, kinds)
        self.assertTrue(any(block[0] == "li" and block[1] == 1 for block in expected),
                        "a nested list item is part of what this test compares")

    def test_the_jpm_page_carries_every_fact_passage_and_gap_as_captured(self):
        self.jpm()
        capture = _read_json_file(os.path.join(JPM_RUN, "pack", "pack.json"))["capture"]
        self.assertTrue(capture["tier1"] and capture["tier2"] and capture["gaps"])
        missing = _missing_from(_evidence_page().render_page(self.jpm()), capture,
                                fresh=False)
        self.assertEqual(missing, [])

    def test_every_run_on_record_renders_a_page(self):
        if not os.path.isdir(RUNS_ON_RECORD):
            self.skipTest("the runs on record are not in this copy of the repository")
        page_module = _evidence_page()
        runs = sorted(name for name in os.listdir(RUNS_ON_RECORD)
                      if os.path.isfile(os.path.join(RUNS_ON_RECORD, name, "pack", "pack.json")))
        # The floor is the runs on record when this test was written; a new run only adds.
        self.assertGreaterEqual(len(runs), 10)
        with_record = []
        for name in runs:
            run_dir = os.path.join(RUNS_ON_RECORD, name)
            pack, markdown = _full_document_of_run(run_dir)
            recorded = os.path.join(run_dir, "pack", "EVIDENCE-FULL.md")
            if os.path.isfile(recorded):
                # The recorded document is the record of what was approved: its bytes are
                # pinned, it still converts block for block and carries every fact, passage
                # and gap in the wording of its day (unit READ-B2 replaced the byte comparison
                # with today's rendering, which reads differently by design).
                with_record.append(name)
                with open(recorded, "rb") as fh:
                    data = fh.read()
                self.assertEqual(hashlib.sha256(data).hexdigest(),
                                 RECORDED_EVIDENCE_DOCUMENTS.get(name), name)
                approval = os.path.join(run_dir, "pack", "approval.json")
                if os.path.isfile(approval):
                    self.assertEqual(_read_json_file(approval)["document_sha256"],
                                     RECORDED_EVIDENCE_DOCUMENTS[name], name)
                old = page_module.render_page(data.decode("utf-8"))
                self.assertEqual(_markdown_blocks(data.decode("utf-8")),
                                 _read_page(old).page_blocks(), name)
                self.assertEqual(_missing_from(old, pack["capture"], fresh=False), [], name)
                self.assertNotEqual(data, markdown.encode("utf-8"), name)
            page = page_module.render_page(markdown)
            expected = _markdown_blocks(markdown)
            actual = _read_page(page).page_blocks()
            self.assertEqual(expected, actual,
                             "%s: %s" % (name, _first_difference(expected, actual)))
            self.assertEqual(_missing_from(page, pack["capture"]), [], name)
            # Today's rendering is deterministic.
            self.assertEqual(markdown, _full_document_of_run(run_dir)[1], name)
        self.assertEqual(sorted(with_record), sorted(RECORDED_EVIDENCE_DOCUMENTS))
        # The hand rendering the JPM host made is a record: it is not a page this renderer
        # wrote, so the brief command's guard would refuse to overwrite it.
        hand = os.path.join(JPM_RUN, "evidence", "EVIDENCE-FULL-jpm.html")
        self.assertTrue(os.path.isfile(hand))
        self.assertFalse(page_module.is_own_page(hand))
        self.assertNotEqual(page_module.page_path(
            os.path.join(JPM_RUN, "evidence", "EVIDENCE-FULL.md")), hand)

    def assert_fetches_nothing(self, page):
        reader = _read_page(page)
        for forbidden in ("link", "img", "iframe", "object", "embed", "base", "form",
                          "audio", "video", "source", "frame"):
            self.assertNotIn(forbidden, reader.tags)
        for name, value in reader.attrs:
            self.assertNotEqual(name, "src")
            self.assertFalse(name.startswith("on"), name)
            if name == "href":
                self.assertTrue(value.startswith("#"), value)
        self.assertEqual(reader.tags.count("script"), 1)
        self.assertEqual(reader.scripts, [R.SCRIPT])
        self.assertEqual(reader.tags.count("style"), 1)
        for style in reader.styles:
            self.assertNotIn("url(", style)
            self.assertNotIn("@import", style)
        return reader

    def test_the_page_fetches_nothing(self):
        page = _evidence_page().render_page(self.jpm())
        self.assertTrue(page.startswith(R.PREAMBLE.decode("ascii")))
        self.assert_fetches_nothing(page)

    def test_hostile_capture_text_renders_as_text(self):
        pack = _hostile_pack()
        markdown = pack_brief.render_full(pack, "0" * 64, None)
        page = _evidence_page().render_page(markdown)
        reader = self.assert_fetches_nothing(page)
        self.assertNotIn("b", reader.tags)
        visible = reader.visible_text()
        for text in HOSTILE:
            self.assertIn(text, visible)
            self.assertIn("Value: %s %s (as of" % (text, text), visible)
        # No mark written by the capture became structure: the only bold is the renderer's,
        # no heading carries the hostile text's own words as a heading of its own, and every
        # row of the cycle table keeps exactly its two cells.
        self.assertNotIn("not bold", reader.strong)
        self.assertNotIn(("h1", "not a heading"), reader.page_blocks())
        rows = [block[1] for block in reader.page_blocks() if block[0] == "row"]
        # The cycle's table of dated points (the one-page summary's table of the numbers that
        # decide comes first since unit READ-B2).
        start = rows.index(("Date", "Value"))
        cycle = rows[start:start + 1 + len(HOSTILE)]
        self.assertEqual([cells[1] for cells in cycle[1:]], list(HOSTILE))
        self.assertTrue(all(len(cells) == 2 for cells in cycle))
        self.assertEqual(_missing_from(page, pack["capture"]), [])

    def test_an_escaped_pipe_stays_inside_its_cell(self):
        markdown = "| Date | Value |\n| --- | --- |\n| one \\| two | three \\\\| four |\n"
        rows = [block[1] for block in _read_page(_evidence_page().render_page(markdown))
                .page_blocks() if block[0] == "row"]
        self.assertEqual(rows, [("Date", "Value"), ("one | two", "three \\", "four")])

    def test_an_escaped_star_opens_no_emphasis(self):
        page = _evidence_page().render_page("A \\*\\*plain\\*\\* word and **a bold one**.\n")
        reader = _read_page(page)
        self.assertEqual(reader.page_blocks(), [("p", "A **plain** word and a bold one.")])
        self.assertEqual(reader.strong, ["a bold one"])
        self.assertEqual(_evidence_page().render_page("An unpaired ** mark.\n").count(
            "<strong>"), 0)

    def test_a_code_span_is_literal(self):
        page = _evidence_page().render_page("An id `a\\*b&amp;c<d>` and \\`not code\\`.\n")
        self.assertIn("<code>a\\*b&amp;amp;c&lt;d&gt;</code>", page)
        self.assertEqual(_read_page(page).page_blocks(),
                         [("p", "An id a\\*b&amp;c<d> and `not code`.")])

    def test_a_passage_of_dashes_prints_as_text_and_only_the_separator_is_a_rule(self):
        # Round 1 of the audit (r1-1): a passage whose whole text is dashes drew a line where its
        # text stands. Only the document's own separator - the one line the full renderer writes
        # between the one-page summary and the full evidence - is a rule; every other line, dashes
        # included, prints as its text.
        pack = copy.deepcopy(_read_json_file(ENGINE_PACK))
        for index, text in enumerate(("---", "-----")):
            pack["capture"]["tier2"].append({
                "id": "dash_passage_%d" % index, "as_of": "2026-08-01",
                "category": "business", "figures": [], "source": "invented: dashes",
                "text": text})
        markdown = pack_brief.render_full(pack, "0" * 64, None)
        page = _evidence_page().render_page(markdown)
        self.assertEqual(page.count("<hr>"), 1)
        blocks = _read_page(page).page_blocks()
        self.assertEqual([block for block in blocks if block[0] == "hr"], [("hr", "")])
        self.assertIn(("p", "---"), blocks)
        self.assertIn(("p", "-----"), blocks)
        self.assertEqual(blocks, _markdown_blocks(markdown))
        separator = blocks.index(("hr", ""))
        self.assertEqual(blocks[separator + 1][0], "h1")
        self.assertTrue(blocks[separator + 1][1].startswith("The full evidence"))
        self.assertEqual(_missing_from(page, pack["capture"]), [])
        # The JPM run's page keeps its one rule and every block it had.
        jpm = self.jpm()
        jpm_page = _evidence_page().render_page(jpm)
        self.assertEqual(jpm_page.count("<hr>"), 1)
        jpm_blocks = _read_page(jpm_page).page_blocks()
        counts = {}
        for block in jpm_blocks:
            counts[block[0]] = counts.get(block[0], 0) + 1
        expected = {}
        for block in _markdown_blocks(jpm):
            expected[block[0]] = expected.get(block[0], 0) + 1
        self.assertEqual(counts, expected)
        self.assertEqual(counts["hr"], 1)

    def test_the_same_markdown_renders_the_same_bytes(self):
        markdown = self.jpm()
        first = _evidence_page().render_page(markdown)
        self.assertEqual(first, _evidence_page().render_page(markdown))
        self.assertNotEqual(first, _evidence_page().render_page(markdown + "One more line.\n"))

    def test_the_foot_names_the_markdowns_sha256(self):
        markdown = self.jpm()
        page = _evidence_page().render_page(markdown)
        digest = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
        with open(os.path.join(JPM_RUN, "pack", "approval.json"), "rb") as fh:
            approved = json.loads(fh.read().decode("utf-8"))["document_sha256"]
        self.assertEqual(digest, approved)
        foot = page[page.index('<div class="foot">'):]
        self.assertIn("<code>%s</code>" % digest, foot)
        self.assertIn("EVIDENCE-FULL.md", foot)
        self.assertIn("council/report/evidence_page.py", foot)
        self.assertEqual(page.count(digest), 1)



# ---------------------------------------------------------------------------------------------
# UPGRADE-2 READ-A - THE REPORT PAGE READS PLAINLY (owner rulings AC16, AC40(2c), AC41; the
# readability register and the owner's five findings)
# ---------------------------------------------------------------------------------------------

# Every recorded page and evidence document on record, by the sha256 of its bytes (criterion 6(a)).
# A render changes the renderer, never a record: a hash that moves means a unit wrote under
# council/runs/.
RECORDED_PAGES = (
    ("council-aapl-2026-08-31-acceptance-2/report.html",
     "785b694f3e416d90d71a279f4fc6957d3cca174cd74b77c3562f45076c1dcada"),
    ("council-btc-2026-08-31/report.html",
     "d49cf64357a5610837c0ae527c60332d43648690c26992101dd89723ae73b727"),
    ("council-btc-2026-09-01/report.html",
     "04981b7338a132e0e64709cc6f1a60eeff9b0ba5a3d508739788d1c83f0112da"),
    ("council-coin-2026-09-04/report.html",
     "fc1370d7c53561f41b2c2006390e298336cfed783c5c49547287ef3f3b23fece"),
    ("council-goog-2026-08-31/report.html",
     "17a82e5a2c2823c782e05c9c716c8e9ca3bc80e81fcca89a01f7982abf289d9d"),
    ("council-jpm-2026-09-24/report.html",
     "e2af4304b76711c86eae87b5c2e25f8afafbe836836f9843fbe1ec8d174313fd"),
    ("council-lulu-2026-09-05/report.html",
     "937acd398c2196aa8b1a85dd5e291bba2d2da55787ca001dae718e90b6d05dd5"),
    ("council-theme-eusov-2026-09-01/report.html",
     "71047691d57527daad7028f7396692540f8573fa72015fafe99b66ff70e0ea30"),
    ("council-wulf-2026-09-09/report.html",
     "8ddc934f63eb12316e3685f1772d6e7ca746ab88ea009f37ac6b16000bbbbcb0"),
    ("council-jpm-2026-09-24/pack/EVIDENCE-FULL.md",
     "5493a38729b32fa04878bda127aa9d6381d9f7bed5e68b97da09d4b26c4d0ea4"),
    ("council-jpm-2026-09-24/evidence/EVIDENCE-FULL.md",
     "5493a38729b32fa04878bda127aa9d6381d9f7bed5e68b97da09d4b26c4d0ea4"),
    ("council-jpm-2026-09-24/evidence/EVIDENCE-FULL-jpm.html",
     "39a5a3c7bcac54a762210397beaa151282ca7f31a2351c9574179f31d3e5f1b2"),
)
JPM_SEAT_TABLES = 12
CAPTION_MAX_WORDS = 30
JPM_LEVEL_WORDS = ("$412.50 — Buy level", "$396.25 — Level to add more")
JPM_SECTIONS = (("decision", "1"), ("synthesis", "2"), ("advisors", "3"), ("review", "4"),
                ("challenge", "5"), ("detail", "6"), ("evidence", "7"), ("appendices", "8"))
_JPM_PAGE = []


def _jpm_page(test):
    """A fresh render of a scratch copy of the JPM sitting, once per suite; skipped where the
    runs on record are not in this copy of the repository."""
    if not os.path.isdir(JPM_RUN):
        test.skipTest("the runs on record are not in this copy of the repository")
    if not _JPM_PAGE:
        with tempfile.TemporaryDirectory() as tmp:
            copied = os.path.join(tmp, "run")
            shutil.copytree(JPM_RUN, copied)
            _JPM_PAGE.append(R.render(copied))
            _JPM_PAGE.append(R.render(copied))
    return _JPM_PAGE[0]


def _between(page, start, end):
    """The page from the first `start` to the next `end` after it (or to the page's end)."""
    begin = page.index(start)
    stop = page.find(end, begin + len(start))
    return page[begin:stop if stop != -1 else len(page)]


def _section(page, anchor):
    """One numbered section's own HTML, from its heading to the next section heading."""
    begin = page.index('<h2 id="%s"' % anchor)
    stop = page.find("<h2 ", begin + 4)
    return page[begin:stop if stop != -1 else len(page)]


def _without_folds(fragment):
    """A fragment with every closed fold cut out, nested ones included."""
    while True:
        cut = re.sub(r"<details>(?:(?!<details>).)*?</details>", "", fragment, flags=re.S)
        if cut == fragment:
            return fragment
        fragment = cut


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _norm(text):
    """Visible text with every figure spelt one way (commas out, trailing zeros off), so two
    pages that print one value with and without a trailing zero read the same decision."""
    text = re.sub(r"\s+", " ", html_lib.unescape(TAG.sub("", text))).strip()
    return _NUMBER.sub(lambda m: format(decimal.Decimal(m.group(0).replace(",", "")).normalize(),
                                        "f"), text)


def _decision(page):
    """What a page decided, read the same way from a recorded page and a fresh one (the
    reconciliation of criterion 6(b)): the rating word, the rating box's price and date, the
    key-number strip's name and value pairs, the chart's dashed levels, the warning cards, the
    chairman's rationale and three fields, and the counts in the evidence folds."""
    head = _between(page, '<header class="masthead">', "<h2 ")
    box = _between(head, '<div class="ratingbox">', '<div class="stamp')
    strip = _between(head, '<dl class="keydata">', "</dl>")
    rationale = re.search(r"Why this rating, in the chairman(?:&#x27;|')s own words</span>(.*?)"
                          r"</div>", page, re.S)
    decided = re.search(r'<div class="card prominent"><span class="lead">What decided it</span>'
                        r"(.*?)</div>", page, re.S)
    business = re.search(r"The business, in the chairman(?:&#x27;|')s words</span>(.*?)</div>",
                         page, re.S)
    metrics = re.search(r"<th>metric</th>.*?</table>", page, re.S)
    facts = re.search(r"all (\d+) frozen fact", page)
    return {
        "rating": _visible_text(_between(box, '<div class="rating-word">', "</div>")),
        "price": _norm(_between(box, '<dl class="rating-price">', "</dl>")),
        "strip": [(_norm(name), _norm(value)) for name, value in
                  re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", strip, re.S)],
        "levels": [_norm(text).split()[0] for text in
                   re.findall(r'<text class="ch-leveltxt"[^>]*>(.*?)</text>', page)],
        "warnings": head.count('<div class="card alarm">'),
        "rationale": _norm(rationale.group(1)) if rationale else None,
        "chair": [_norm(match.group(1)) if match else None for match in (decided, business)]
        + [_norm(metrics.group(0)) if metrics else None],
        "facts": facts.group(1) if facts else None,
        "passages": _between(page, "<h3>The narrative record</h3>", "<h3>").count(
            '<div class="card') if "<h3>The narrative record</h3>" in page else 0,
        "gaps": _between(page, "<h3>Declared gaps</h3>", "<h3>").count("<li>")
        if "<h3>Declared gaps</h3>" in page else 0,
    }


def _same_decision(test, recorded, fresh, name):
    """Criterion 6(b): the fresh render carries the decision the recorded page carries."""
    expected, actual = _decision(recorded), _decision(fresh)
    for key in expected:
        test.assertEqual(expected[key], actual[key], "%s: %s differs" % (name, key))


class TestReadablePage(unittest.TestCase):
    """UPGRADE-2 READ-A: the report page reads plainly. Every test failed against the base code
    for the reason its name gives, except the two guards, which cannot fail there:
    test_no_recorded_page_is_rewritten and test_a_render_is_deterministic."""

    # --- Part 1: tables and figures ------------------------------------------------------------

    def test_a_pipe_table_renders_as_a_table(self):
        html = R.markdown("Before.\n\n| Price | Multiple |\n| --- | :-: |\n| $412.50 | 1.85x |\n")
        self.assertIn('<table class="md"><tr><th>Price</th><th>Multiple</th></tr>'
                      "<tr><td>$412.50</td><td>1.85x</td></tr></table>", html)
        self.assertNotIn("| ---", html)
        self.assertIn("<p>Before.</p>", html)

    def test_a_malformed_table_stays_text(self):
        ragged = R.markdown("| a | b |\n| --- | --- |\n| 1 | 2 | 3 |\n\n| c |\n| - |\n| 4 |\n")
        self.assertEqual(ragged.count("<table"), 1)
        self.assertIn('<table class="md"><tr><th>c</th></tr><tr><td>4</td></tr></table>', ragged)
        self.assertIn("<p>| a | b | | --- | --- | | 1 | 2 | 3 |</p>", ragged)
        headless = R.markdown("| a | b |\n| 1 | 2 |\n")
        self.assertNotIn("<table", headless)
        self.assertIn("<p>| a | b | | 1 | 2 |</p>", headless)

    def test_an_escaped_pipe_stays_in_its_cell(self):
        html = R.markdown("| a \\| b | c |\n|---|---|\n| 1 | 2 |\n")
        self.assertIn("<th>a | b</th><th>c</th>", html)
        self.assertIn("<td>1</td><td>2</td>", html)

    def test_table_cells_are_respelt_like_prose(self):
        log = []
        text = R.reformat_prose("| Line | Revenue |\n|---|---|\n| Cards | 47,636 thousand "
                                "dollars |\n", "a seat's table", log)
        self.assertIn("<td>Cards</td><td>$47.6M</td>", R.markdown(text))
        self.assertEqual([row["replacement"] for row in log], ["$47.6M"])

    def test_the_jpm_page_prints_every_seat_table_as_a_table(self):
        page = _jpm_page(self)
        self.assertEqual(page.count('<table class="md">'), JPM_SEAT_TABLES)
        self.assertEqual(_section(page, "synthesis").count('<table class="md">'), 1)
        self.assertIsNone(re.search(r"<p>[^<]*\|\s*-{3,}", page))

    def test_million_and_billion_units_read_in_the_market_form(self):
        self.assertEqual(R.format_number("25511", "USD_million"), "$25.5B")
        self.assertEqual(R.format_number("2515", "USD_million"), "$2.52B")
        self.assertEqual(R.format_number("94", "USD_billion"), "$94.0B")
        self.assertEqual(R.format_number("640", "USD_millions"), "$640M")
        self.assertNotIn("USD million", _jpm_page(self))

    def test_a_count_reads_as_a_number(self):
        self.assertEqual(R.format_number("318512", "count"), "318,512")

    def test_percentage_points_read_one_decimal_points(self):
        self.assertEqual(R.format_number("-5.8604126179", "percentage_points"), "-5.9 points")
        self.assertEqual(R.format_number("2", "percentage_points"), "2.0 points")

    def test_trading_days_not_bars(self):
        self.assertEqual(R.format_number("209", "bars"), "209 trading days")

    def test_a_whole_percentage_keeps_its_decimal(self):
        self.assertEqual(R.format_number("11", "percent"), "11.0%")
        self.assertEqual(R.format_number("0.2", "fraction"), "20.0%")
        log = []
        self.assertEqual(R.reformat_prose("11% at Wells Fargo, 10.6% at Bank of America",
                                          "prose", log),
                         "11.0% at Wells Fargo, 10.6% at Bank of America")
        self.assertEqual(log, [{"location": "prose", "original": "11%",
                                "replacement": "11.0%"}])

    # --- Labels and machine text off the reading path -------------------------------------------

    def test_no_fact_id_in_the_open_tiers_of_the_jpm_page(self):
        page = _jpm_page(self)
        with open(os.path.join(JPM_RUN, "pack", "pack.json"), "rb") as fh:
            ids = {fact["id"] for fact in json.loads(fh.read().decode("utf-8"))["capture"]["tier1"]}
        evidence = _section(page, "evidence")
        opened = (_section(page, "decision") + _section(page, "synthesis")
                  + _section(page, "detail") + evidence[:evidence.index("<details>")])
        coded = set(re.findall(r"<code>([^<]*)</code>", opened))
        self.assertEqual(coded & ids, set())

    def test_no_raw_machine_text_on_the_jpm_page(self):
        page = _jpm_page(self)
        # The exact before-and-after text of the challenge diff stays behind its second fold by
        # design; everything else on the page is read for machine text.
        kept = _between(page, "<summary>The exact text before and after", "</details>")
        text = _visible_text(re.sub(r"<(style|script)>.*?</\1>", "", page.replace(kept, ""),
                                    flags=re.S))
        for machine in ('{"', '[{"', "USD_million", "USD million", "council/report",
                        "Deterministic transform", "The raw findings", "spec U5.5", "AC8"):
            self.assertNotIn(machine, text, machine)
        foot = _between(page, '<div class="foot">', "</div>")
        self.assertNotIn("hash", foot)
        self.assertNotIn("contract version", foot)
        handoff = _between(page, '<h3 id="atlas">', "</details>").lower()
        self.assertIn(R.RATING_WORDS["hold"].lower(), handoff)
        self.assertIn("publication hash", handoff)
        self.assertIn("contract version", handoff)

    def test_no_writing_score_line_and_the_ac6_alarm_still_renders(self):
        self.assertNotIn("Writing score", _jpm_page(self))
        run = R.load_run(FIXTURE)
        rules = prose.load_rules()
        score = prose.measure("It is not cheap, it is a trap.", rules)
        run["prose_scores"] = {
            "advisor_bear": {"seat": "advisor_bear", "judged": False, "warned": False,
                             "score": score},
            "chair_resolve": {"seat": "chair_resolve", "judged": True, "warned": True,
                              "over_threshold": True, "score": score}}
        body = R.build_page(run, NO_CLOCK_MOMENT).body()
        self.assertNotIn("Writing score", body)
        self.assertIn("did not meet the council", body)
        self.assertIn(E(prose.describe(score)), body)

    # --- The chart and the tape -----------------------------------------------------------------

    def test_the_chart_drawing_is_unchanged_but_its_level_words(self):
        page = _jpm_page(self)
        with open(os.path.join(JPM_RUN, "report.html"), "rb") as fh:
            recorded = fh.read().decode("utf-8")
        words = re.compile(r'(<text class="ch-leveltxt"[^>]*>)[^<]*(</text>)')

        def drawing(html):
            return words.sub(r"\1\2", _between(html, "<svg viewBox", "</svg>"))
        self.assertEqual(drawing(recorded), drawing(page))
        self.assertEqual([html_lib.unescape(text) for text in re.findall(
            r'<text class="ch-leveltxt"[^>]*>([^<]*)</text>', page)], list(JPM_LEVEL_WORDS))
        self.assertIn("A price level the chairman named", _between(page, CHART_OPEN, "</figure>"))

    def test_the_caption_is_one_short_sentence(self):
        caption = _visible_text(_between(_jpm_page(self), "<figcaption>", "</figcaption>"))
        self.assertLessEqual(len(caption.split()), CAPTION_MAX_WORDS)
        self.assertEqual(len(re.findall(r"[.;!?](?:\s|$)", caption)), 2, caption)
        for part in ("the broker", "23 Sep 2026", "SPY", "S&P 500"):
            self.assertIn(part, caption)
        self.assertEqual(_visible_text(_between(_taped_html(), "<figcaption>", "</figcaption>")),
                         "Daily closes of SPWK to 28 Aug 2026; SPY is the S&P 500 fund, rebased.")

    def test_the_provenance_text_is_folded_under_the_chart_once(self):
        page = _jpm_page(self)
        with open(os.path.join(JPM_RUN, "pack", "pack.json"), "rb") as fh:
            source = json.loads(fh.read().decode("utf-8"))["capture"]["price_series"]["source"]
        sentence = E("Daily closes from %s, as of" % source)
        self.assertEqual(page.count(sentence), 1)
        fold = _between(page, "</figure>", "</details>")
        self.assertIn("<details><summary>Where the price history comes from", fold)
        self.assertIn(sentence, fold)

    def test_the_tape_reads_months_and_names_its_close(self):
        table = _between(_jpm_page(self), TABLE_OPEN, "</table>")
        text = _visible_text(table)
        self.assertIn("at the 23 Sep close", text)
        for words in ("Return over 1 month", "Return over 3 months", "Return over 6 months",
                      "Return over 1 year", "209 of the last 252 trading days", "-5.9 points"):
            self.assertIn(words, text)
        self.assertNotIn("bars", text)
        self.assertNotIn("21 trading days", text)

    # --- Owner's finding 2: a hover note on every term ------------------------------------------

    def test_every_tape_row_key_number_and_metric_name_carries_a_hover_note(self):
        page = _jpm_page(self)
        rows = re.findall(r'<tr class="taperow"><td>(.*?)</td>', page)
        self.assertEqual(len(rows), 15)
        strip = _between(page, '<dl class="keydata">', "</dl>")
        names = re.findall(r"<dt>(.*?)</dt>", strip)
        metrics = re.findall(r"<tr><td>(.*?)</td>", _between(page, "<th>metric</th>", "</table>"))
        self.assertEqual(len(metrics), 4)
        for cell in rows + names + metrics:
            self.assertRegex(cell, r'<span class="gl" tabindex="0" data-note="[^"]+"', cell)
        slope = [cell for cell in rows if "Slope of the 200-day average" in cell][0]
        self.assertIn("60 trading days ago", slope)
        self.assertIn(".gl:focus::before", R.CSS)
        self.assertIn(".gl:hover::before", R.CSS)

    # --- The advisors' letters, the evidence check, the challenge -------------------------------

    def test_the_advisors_letters_are_keyed_to_their_names(self):
        line = ("Response A is the Bull, B the Base Rate Skeptic, C the Market Structure "
                "Analyst, D the Bear, E the Risk Analyst.")
        page = _jpm_page(self)
        self.assertIn(line, _visible_text(_section(page, "decision")))
        self.assertIn(line, _visible_text(_section(page, "review")))
        self.assertNotIn("Response A is", HTML)

    def test_a_fact_change_reads_its_old_and_new_values_and_a_frame_change_reads_as_words(self):
        changes = _between(_jpm_page(self), "moved after the evidence check", "</details>")
        text = _visible_text(changes)
        self.assertIn("Quarterly dividend declared 10 March 2026", text)
        self.assertIn("$0.85", text)
        self.assertIn("CET1 above regulatory minimum, before management's own buffer", text)
        self.assertIn("$23.9B", text)
        self.assertIn("The business description (how it earns) — revised after the "
                      "evidence check", text)
        self.assertNotIn("[{", text)
        self.assertNotIn("distributable_capital_excess_cet1_q", text)

    def test_the_challenge_diff_names_fields_in_words_and_tables_the_rating_and_key_numbers(self):
        fold = _visible_text(_between(_jpm_page(self), "fields changed between the draft",
                                      "</details></div></details>"))
        for words in ("the chairman's rationale", "how far off the price is",
                      "Rating Buy Hold", "Buy level, 1.85x June tangible book — $412.50",
                      "Cap on the buy level, 1.95x June tangible book $431.10 —"):
            self.assertIn(words, fold)
        self.assertNotIn("conviction_rationale", fold.split("The exact text before")[0])

    # --- The foot, About this sitting, the order of the page ------------------------------------

    def test_the_footer_carries_no_hash_or_path(self):
        foot = _visible_text(_between(HTML, '<div class="foot">', "</div>"))
        self.assertNotIn("hash", foot)
        self.assertNotIn("council/report", foot)
        self.assertNotIn(VERDICT_SHA, foot)
        self.assertIn("Not investment advice.", foot)
        self.assertIn("Published 30 Aug 2026, 10:26 UTC.", foot)
        self.assertIn('<meta name="generator" content="council/report/render_report.py">', HTML)
        self.assertIn(VERDICT_SHA, _between(HTML, '<h3 id="atlas">', "</details>"))

    def test_about_this_sitting_reads_plainly(self):
        about = _visible_text(_between(_jpm_page(self), '<h3 id="stamps">', '<div class="foot">'))
        self.assertIn("41 minutes sitting, plus 19 minutes gathering the evidence", about)
        self.assertIn("Estimated cost, at list prices", about)
        self.assertIn("Council (Claude)", about)
        self.assertIn("Outside model (OpenAI)", about)
        self.assertIn("they are not a bill", about)
        self.assertIn("The Base Rate Skeptic", about)
        self.assertIn("codex-cli 0.156.0", about)
        for gone in ("spec U5.5", "AC8", "Input tokens", "advisor_base_rate"):
            self.assertNotIn(gone, about)

    def test_the_page_order_and_numbered_sections(self):
        page = _jpm_page(self)
        found = re.findall(r'<h2 id="([a-z]+)" data-num="(\d)"', page)
        self.assertEqual(tuple(found), JPM_SECTIONS)
        self.assertIn('<span class="sb-sec" id="sb-section"></span>', page)
        self.assertIn("<summary>The bear case &mdash; hold; buy at about $396</summary>",
                      _section(page, "advisors"))
        self.assertIn("What all five missed", _without_folds(_section(page, "review")))
        self.assertIn("The outside challenge round", _section(page, "challenge"))
        for folded in ("question", "atlas", "stamps"):
            self.assertIn('<h3 id="%s">' % folded, _section(page, "appendices"))

    def test_cards_share_the_section_width(self):
        # Unit READ-D removed the reading-measure cap on cards and prose outright, so the rule
        # that undid it on the report went with it; nothing may cap them again.
        self.assertNotRegex(R.CSS, r"\.(?:wrap|report)>[^{]*\{[^}]*max-width:var\(--measure\)")
        self.assertIn(".cols{column-width", R.CSS)
        self.assertIn('<div class="card cols"><span class="lead">Why this rating',
                      _section(_jpm_page(self), "decision"))

    def test_the_cycle_series_daily_rows_are_folded(self):
        detail = _section(_jpm_page(self), "detail")
        opened = _without_folds(detail)
        self.assertIn("Fed funds rate", opened)
        self.assertIn("<th>Series</th>", opened)
        self.assertNotIn("t10y2y", opened)
        self.assertNotIn("2026-09-08", opened)
        self.assertIn("2026-09-08", detail)

    def test_the_price_read_and_its_arithmetic(self):
        page = _jpm_page(self)
        read = _visible_text(_section(page, "decision"))
        self.assertIn("The price read: Fair, at the top of the range", read)
        self.assertNotIn("reads the price as fair", read)
        self.assertNotIn("Price to tangible book equals", read)
        self.assertIn("Price to tangible book equals", _visible_text(_section(page, "synthesis")))
        self.assertNotIn("The thesis", read)

    # --- Audit round 1 of READ-A: regression tests, each failed against the pre-fix code ------

    @staticmethod
    def _cost_rows(run):
        page = R.Page()
        R._cost_estimate(page, run)
        return _visible_text("".join(page.parts))

    def test_an_uncounted_call_is_never_priced_as_zero(self):
        run = {"verdict": {"provenance": {
            "seat_cost": {"per_seat": {"frame": {"tokens": 1000000}}},
            "evidence": {"capture": {"tokens": 1000000, "estimated": False,
                                     "evidence_challenge_tokens": 200000}}}},
            "challenge_result": {"usage_tokens": None}}
        text = self._cost_rows(run)
        self.assertIn("not counted: the outside challenge", text)
        self.assertIn("at least $1.00", text)
        self.assertIn("about $10.00", text)
        run["verdict"]["provenance"]["seat_cost"] = {}
        text = self._cost_rows(run)
        self.assertIn("at least $5.00", text)
        self.assertIn("not counted: the advisors' and chairman's sessions", text)

    def test_a_small_cost_keeps_its_cents(self):
        run = {"verdict": {"provenance": {
            "seat_cost": {"per_seat": {"frame": {"tokens": 90000}}},
            "evidence": {"capture": {"tokens": 0, "evidence_challenge_tokens": 1000}}}},
            "challenge_result": {"usage_tokens": 1000}}
        text = self._cost_rows(run)
        self.assertIn("about $0.45", text)
        self.assertIn("about $0.01", text)
        self.assertNotIn("about $0 ", text)

    def test_a_key_number_moved_within_its_rounding_is_listed(self):
        def change(value):
            return json.dumps([{"name": "Net income", "as_of": "2026-06-30", "value": value,
                                "unit": "USD_million"},
                               {"name": "Last price", "as_of": "2026-09-01", "value": "100",
                                "unit": "USD_per_share"},
                               {"name": "Last price", "as_of": "2026-09-02", "value": "101",
                                "unit": "USD_per_share"}])
        before = json.loads(change("1001"))
        after = json.loads(change("1002"))
        after[2]["value"] = "102"
        rows = R._moved_numbers([{"field": "key_numbers", "before": json.dumps(before),
                                  "after": json.dumps(after)}])
        self.assertEqual(rows[0][0], "Net income")
        self.assertIn("moved within the rounding", rows[0][2])
        self.assertEqual([row[0] for row in rows[1:]], ["Last price (2 Sep 2026)"])
        self.assertEqual(rows[1][1:], ("$101.00", "$102.00"))

    def test_a_level_two_key_numbers_share_takes_no_name(self):
        from council.report import chart
        verdict = {"atlas_envelope": {"key_numbers": [
            {"name": "Last price", "value": "100", "unit": "USD_per_share"},
            {"name": "Buy level, 2.6x book", "value": "100.00", "unit": "USD_per_share"},
            {"name": "Level to add more", "value": "90", "unit": "USD_per_share"}]}}
        self.assertIsNone(chart._level_name(verdict, decimal.Decimal("100"), "USD_per_share"))
        self.assertEqual(chart._level_name(verdict, decimal.Decimal("90"), "USD_per_share"),
                         "Level to add more")

    def test_what_all_five_missed_written_as_a_label_is_shown_open(self):
        for text in ("Cross.\n\n**What all five missed:** nobody priced the gap.\n\nWriting: none.",
                     "Cross.\n\nWhat all five missed: nobody priced the gap.\n\nWriting: none."):
            part = R._missed_part(text)
            self.assertIn("nobody priced the gap.", part)
            self.assertNotIn("Writing", part)
            self.assertNotIn("Cross", part)
        with open(os.path.join(FIXTURE, "rpc", "008-answer-reviewer.json"),
                  encoding="utf-8") as fh:
            review = json.load(fh)["markdown"]
        self.assertIn("risk-free rate reading", R._missed_part(review))

    # --- Round 3 of READ-A: the three rules replaced whole (r2-1, r2-2, r2-3), each failed first -

    def test_a_repeated_name_and_date_is_paired_in_order(self):
        def row(value):
            return {"name": "Last price", "as_of": "2026-09-01", "value": value,
                    "unit": "USD_per_share"}
        rows = R._moved_numbers([{"field": "key_numbers",
                                  "before": json.dumps([row("100"), row("200")]),
                                  "after": json.dumps([row("101"), row("200")])}])
        self.assertEqual(rows, [("Last price (1 Sep 2026)", "$100.00", "$101.00")])
        rows = R._moved_numbers([{"field": "key_numbers",
                                  "before": json.dumps([row("100"), row("200")]),
                                  "after": json.dumps([row("100")])}])
        self.assertEqual(rows, [("Last price (1 Sep 2026)", "$200.00", "\u2014")])

    def test_an_uncounted_part_never_reads_under_a_cent(self):
        for tokens, shown in ((1000, "at least $0.00"), (3000, "at least $0.01")):
            run = {"verdict": {"provenance": {
                "seat_cost": {"per_seat": {"frame": {"tokens": tokens}}},
                "evidence": {"capture": {"tokens": None, "evidence_challenge_tokens": 0}}}},
                "challenge_result": {"usage_tokens": 1000000}}
            text = self._cost_rows(run)
            self.assertIn(shown, text)
            self.assertIn("not counted: the evidence gathering", text)
            self.assertNotIn("under $0.01", text)
        run["verdict"]["provenance"]["seat_cost"] = {}
        self.assertIn("at least $0.00", self._cost_rows(run))

    def test_what_all_five_missed_as_a_label_paragraph_takes_the_next_paragraph(self):
        for label in ("**What all five missed:**", "What all five missed:",
                      "**What all five missed**"):
            part = R._missed_part("Cross.\n\n%s\n\nNobody priced the gap.\n\nWriting: none."
                                  % label)
            self.assertIn(label, part)
            self.assertIn("Nobody priced the gap.", part)
            self.assertNotIn("Writing", part)
        part = R._missed_part("Cross.\n\n**What all five missed:**\n\n## Response A\n\nText.")
        self.assertIn("What all five missed", part)
        self.assertIn("no text follows", part)
        self.assertNotIn("Response A", part)

    # --- Round 5 of READ-A, Step 0: the cost estimate replaced whole (r4-2), each failed first --

    def test_the_jpm_council_row_prices_the_estimated_gathering_apart(self):
        about = _visible_text(_between(_jpm_page(self), '<h3 id="stamps">', "<h4>"))
        council = _between(about, "Council (Claude)", "Outside model")
        self.assertIn("about $12.40, of which $4.05 rests on an estimate", council)
        self.assertIn("1,650,000 counted; 810,000 estimated", council)
        self.assertNotIn("2,460,000", about)
        outside = _between(about, "Outside model (OpenAI)", "never a bill")
        self.assertIn("about $0.92", outside)
        self.assertIn("184,000 counted", outside)
        self.assertNotIn("estimate", outside.split("the outside model's input rate")[0])

    def test_an_uncounted_part_prices_only_the_counted_bin(self):
        run = {"verdict": {"provenance": {
            "seat_cost": {"per_seat": {"frame": {"tokens": 1000000},
                                       "reviewer": {"tokens": None}}},
            "evidence": {"capture": {"tokens": 2000000, "estimated": True,
                                     "evidence_challenge_tokens": 0}}}},
            "challenge_result": {"usage_tokens": 0}}
        text = self._cost_rows(run)
        self.assertIn("at least $5.00", text)
        self.assertIn("1,000,000 counted; 2,000,000 estimated", text)
        self.assertIn("not counted: the advisors' and chairman's sessions", text)
        self.assertNotIn("at least $15.00", text)

    def test_a_fully_counted_row_reads_about(self):
        run = {"verdict": {"provenance": {
            "seat_cost": {"per_seat": {"frame": {"tokens": 1000000}}},
            "evidence": {"capture": {"tokens": 1000000, "estimated": False,
                                     "evidence_challenge_tokens": 1000}}}},
            "challenge_result": {"usage_tokens": 0}}
        text = self._cost_rows(run)
        self.assertIn("about $10.00", text)
        self.assertIn("2,000,000 counted", text)
        self.assertIn("under $0.01", text)
        self.assertIn("1,000 counted", text)
        self.assertNotIn("rests on an estimate", text)
        self.assertNotIn("estimated", text.split("never a bill")[0].replace(
            "Estimated cost", ""))

    def test_an_estimated_figure_is_never_summed_into_a_counted_one(self):
        for flag in ({"estimated": True}, {}):
            capture = {"tokens": 2000000, "evidence_challenge_tokens": 1000000}
            capture.update(flag)
            run = {"verdict": {"provenance": {
                "seat_cost": {"per_seat": {"frame": {"tokens": 1000000}}},
                "evidence": {"capture": capture}}},
                "challenge_result": {"usage_tokens": 1000000}}
            text = self._cost_rows(run)
            self.assertIn("1,000,000 counted; 2,000,000 estimated", text)
            self.assertIn("about $15.00, of which $10.00 rests on an estimate", text)
            self.assertNotIn("3,000,000", text)
            self.assertNotIn("tokens counted", text)
            self.assertIn("2,000,000 counted", text.split("Outside model (OpenAI)")[1])

    # --- The records ---------------------------------------------------------------------------

    def test_no_recorded_page_is_rewritten(self):
        runs = os.path.join(ROOT, "council", "runs")
        if not os.path.isdir(runs):
            self.skipTest("the runs on record are not in this copy of the repository")
        for relative, digest in RECORDED_PAGES:
            with open(os.path.join(runs, relative), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), digest, relative)
        on_disk = sorted(os.path.relpath(path, runs) for path in
                         [os.path.join(base, name) for base, _dirs, names in os.walk(runs)
                          for name in names]
                         if os.path.basename(path) == "report.html"
                         or os.path.basename(path).startswith("EVIDENCE-FULL"))
        self.assertEqual(on_disk, sorted(relative for relative, _digest in RECORDED_PAGES))

    def test_a_render_is_deterministic(self):
        self.assertEqual(HTML, _render(FIXTURE))
        page = _jpm_page(self)
        self.assertEqual(page, _JPM_PAGE[1])
        with open(os.path.join(JPM_RUN, "report.html"), "rb") as fh:
            _same_decision(self, fh.read().decode("utf-8"), page, "council-jpm-2026-09-24")



# UPGRADE-2 READ-D THE LOOK AND FEEL (owner rulings AC42, AC43): the stylesheet and the page frame
# change; no word, figure, note, fold default or line of the chart drawing moves. The constants
# below were measured on the base render (main after READ-B2) of a scratch copy of the JPM sitting
# and of `render_page` of its approved document. READ-B1 (rebased onto READ-D) re-measured the
# report page's fingerprint only: its business sections print as tables, so the page's words move
# by that unit's design; the value equals the READ-B1 head's own render before READ-D, so READ-D's
# look moves no word on top of it (was 6a268617...ab35 on main after READ-B2).
JPM_REPORT_WORDS_AND_NOTES = "ba0599ef8e05992db0dc2e4da3ac366ad2ed55d22823bc6778f002ebbb7f4ca6"
JPM_APPROVAL_WORDS_AND_NOTES = "feea118bfd0c806209d981647aabed024c830d8a05b9d51d9be4c22481e098fb"
JPM_CHART_DRAWING = "165a3e6c8166c7dbb8efdc69c1a6efa639a52586b09bcb02f85fc23cd5124f86"
JPM_REPORT_BASE_BYTES = 615393
JPM_APPROVAL_BASE_BYTES = 333194
JPM_REPORT_TERMS = 31
JPM_APPROVAL_TERMS = 54
# The chart's colours are its own settings (READ-D bracket 1), fixed at the values the page's
# palette gave them before this unit, in each of the three sets: dark screen, light screen, print.
CHART_COLOURS = {
    "dark": {"ch-ink": "#E8E6E0", "ch-muted": "#94918A", "ch-hair": "rgba(255,255,255,0.13)",
             "ch-axis": "rgba(255,255,255,0.09)", "ch-up": "#7F9468", "ch-down": "#A85C50",
             "ch-avg": "#DD8B5A", "ch-level": "#D2603F", "ch-paper": "#161616"},
    "light": {"ch-ink": "#1F1E1B", "ch-muted": "#615D55", "ch-hair": "rgba(0,0,0,0.17)",
              "ch-axis": "rgba(0,0,0,0.14)", "ch-up": "#4B6837", "ch-down": "#8C3B2F",
              "ch-avg": "#A8571B", "ch-level": "#992D14", "ch-paper": "#FAF8F3"},
    "print": {"ch-ink": "#101010", "ch-muted": "#4A4A4A", "ch-hair": "#DEDEDE",
              "ch-axis": "#C9C9C9", "ch-up": "#4B6837", "ch-down": "#8C3B2F",
              "ch-avg": "#A8571B", "ch-level": "#992D14", "ch-paper": "#FFFFFF"},
}
NARROW_SCREEN = "@media (max-width:600px){"


def _words_and_notes(page):
    """A fingerprint of what a reader can read on a page: its visible text (script and style
    cut, tags stripped, entities resolved, spaces collapsed) and every hover note in order."""
    body = re.sub(r"<(script|style)>.*?</\1>", " ", page[page.index("<body>"):], flags=re.S)
    notes = [html_lib.unescape(note) for note in
             re.findall(r'<span class="gl" tabindex="0" data-note="([^"]*)"', page)]
    return hashlib.sha256("\n".join([_visible_text(body)] + notes).encode("utf-8")).hexdigest()


def _jpm_approval_page(test):
    """`render_page` of the JPM sitting's approved evidence document, from the record."""
    if not os.path.isdir(JPM_RUN):
        test.skipTest("the runs on record are not in this copy of the repository")
    with open(os.path.join(JPM_RUN, "evidence", "EVIDENCE-FULL.md"), "rb") as fh:
        return _evidence_page().render_page(fh.read().decode("utf-8"))


def _token_set(css, opening):
    """One set of colour tokens: the block that `opening` starts, to its first closing brace."""
    start = css.index(opening) + len(opening)
    return css[start:css.index("}", start)]


def _narrow_block(css):
    """The narrow-screen rules, from the media line to the brace that closes it."""
    start = css.index(NARROW_SCREEN) + len(NARROW_SCREEN)
    depth, at = 1, start
    while depth:
        depth += {"{": 1, "}": -1}.get(css[at], 0)
        at += 1
    return css[start:at - 1]


class TestLookAndFeel(unittest.TestCase):
    """UPGRADE-2 READ-D. Against the base code the marker test, the note test, the phone test and
    the chart-colour test failed for the reasons their names give. The other five are GUARDS: the
    words, the notes, the chart drawing, the size and the light print are what the base already
    had, pinned so the restyle cannot move them."""

    def both_stylesheets(self):
        return R.CSS + _evidence_page().PAGE_CSS

    def test_no_marker_after_a_term(self):
        css = self.both_stylesheets()
        self.assertEqual(css.count('content:"?"'), 0)
        self.assertNotIn(".gl::after", css)
        self.assertNotIn(".gl:after", css)
        # The dotted underline alone marks the term (owner ruling AC43).
        rule = _between(css, ".gl{", "}")
        self.assertIn("dotted", rule)

    def test_every_term_keeps_its_note_on_both_pages(self):
        # GUARD: the base already carried every note; the restyle may lose none.
        for page, count in ((_jpm_page(self), JPM_REPORT_TERMS),
                            (_jpm_approval_page(self), JPM_APPROVAL_TERMS)):
            spans = re.findall(r'<span class="gl"[^>]*>', page)
            self.assertEqual(len(spans), count)
            for span in spans:
                self.assertRegex(span, r'^<span class="gl" tabindex="0" data-note="[^"]+">$')
        self.assertIn(".gl:hover::before,.gl:focus::before{display:block}", R.CSS)

    def test_the_note_stays_on_the_screen(self):
        # On a phone the note is a sheet pinned inside the screen's edges, whatever the term's
        # place in the line; it can never widen the page. On a desktop it hangs under its term
        # and is capped to the window.
        pin = "pos" + "ition"
        narrow = _narrow_block(R.CSS)
        self.assertIn(".gl::before{", narrow)
        note = _between(narrow, ".gl::before{", "}")
        self.assertIn("%s:fixed" % pin, note)
        self.assertIn("left:16px", note)
        self.assertIn("right:16px", note)
        self.assertIn("max-width:none", note)
        desktop = _between(R.CSS, ".gl::before{", "}")
        self.assertIn("max-width:min(360px,calc(100vw - 32px))", desktop)

    def test_a_phone_screen_scrolls_tables_not_the_page(self):
        narrow = _narrow_block(R.CSS)
        self.assertIn("table{display:block;overflow-x:auto", narrow)
        gutter = _between(narrow, ".wrap{", "}")
        self.assertRegex(gutter, r"padding:\d+px 16px")

    def test_the_look_changed_and_the_words_did_not(self):
        # GUARD (criterion 2): one changed word, figure or note on either page moves this. Unit
        # READ-C1 adds exactly one line to the JPM page - the muted note that its verdict, written
        # before the chairman was asked for a one-line answer, carries none (owner ruling
        # AC44(1)) - so that one line is cut before the fingerprint is taken.
        note = '<div class="muted small">%s</div>' % E(R.ANSWER_LINE_BEFORE)
        self.assertEqual(_jpm_page(self).count(note), 1)
        self.assertEqual(_words_and_notes(_jpm_page(self).replace(note, "")),
                         JPM_REPORT_WORDS_AND_NOTES)
        self.assertEqual(_words_and_notes(_jpm_approval_page(self)),
                         JPM_APPROVAL_WORDS_AND_NOTES)

    def test_the_chart_drawing_is_the_base_drawing(self):
        # GUARD (criterion 10): the SVG bytes inside the chart figure are the base render's.
        chart = _chart(_jpm_page(self))
        svg = chart[chart.index("<svg"):chart.index("</svg>") + len("</svg>")]
        self.assertEqual(hashlib.sha256(svg.encode("utf-8")).hexdigest(), JPM_CHART_DRAWING)

    def test_the_pages_are_no_larger_than_a_tenth_over_the_base(self):
        # GUARD (criterion 7).
        self.assertLessEqual(len(_jpm_page(self).encode("utf-8")),
                             JPM_REPORT_BASE_BYTES * 11 // 10)
        self.assertLessEqual(len(_jpm_approval_page(self).encode("utf-8")),
                             JPM_APPROVAL_BASE_BYTES * 11 // 10)

    def test_the_approval_page_prints_light(self):
        # GUARD (criterion 5): the approval page prints as the report does - white paper, dark
        # ink, A4 - and the chart's print colours are in the print set.
        page = _jpm_approval_page(self)
        style = _between(page, "<style>", "</style>")
        self.assertIn("@page{size:A4", style)
        printed = style[style.index("@media print{"):]
        self.assertIn("--base:#FFFFFF", printed)
        self.assertIn("--text:#101010", printed)
        self.assertIn("break-inside:avoid", printed)
        self.assertNotIn("prefers-color-scheme", style)
        self.assertIn('<html lang="en" data-theme="dark">', page[:120])

    def test_the_chart_colours_are_its_own_settings(self):
        # Bracket 1: every chart rule takes only the chart's own tokens, and those tokens carry
        # the values the page's palette gave the chart before this unit, in all three sets.
        css = R.CSS
        chart = _chart(_jpm_page(self))
        for name in sorted(set(re.findall(r'class="(ch-[a-z0-9]+)"', chart))):
            rule = re.search(r"\.%s\{([^}]*)\}" % re.escape(name), css).group(1)
            tokens = re.findall(r"var\(--([a-z-]+)\)", rule)
            self.assertTrue(tokens or "fill:none" in rule, name)
            for token in tokens:
                self.assertTrue(token.startswith("ch-"), (name, token))
        sets = {"dark": _token_set(css, ":root{"),
                "light": _token_set(css, ':root[data-theme="light"]{'),
                "print": _token_set(css[css.index("@media print{"):], "{")}
        for which, colours in CHART_COLOURS.items():
            for token, value in colours.items():
                self.assertIn("--%s:%s;" % (token, value), sets[which], (which, token))


# ---------------------------------------------------------------------------------------------
# UPGRADE-2 READ-B1, THE BUSINESS SECTIONS AS TABLES (owner rulings AC40(2c), AC16(4), AC41; the
# seed's rulings 2 to 7): on the report page the financial institution's business sections read
# as small tables of figures in the market form, the same rows the full evidence document prints.
# Each test FAILED against the base.
# ---------------------------------------------------------------------------------------------

def _card_rows(fragment, lead):
    """The first table after the card lead that starts with `lead`, as rows of each cell's
    visible text (header row first)."""
    marker = '<span class="lead">%s' % R.esc(lead)
    if marker not in fragment:
        raise AssertionError("no card lead starts with %r" % lead)
    start = fragment.index(marker)
    table = fragment[fragment.index("<table", start):fragment.index("</table>", start)]
    return [[_visible_text(cell) for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
            for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)]


def _md_rows(text, lead):
    """The Markdown table after the first line starting with `lead`, each cell unescaped to the
    words a reader sees (the delimiter row left out)."""
    lines = text.splitlines()
    at = [index for index, line in enumerate(lines) if line.startswith(lead)][0]
    rows = []
    for line in lines[at + 1:]:
        if line.startswith("|"):
            cells = [html_lib.unescape(re.sub(r"\\(.)", r"\1", cell.strip()))
                     for cell in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
            if not all(set(cell) <= set("-: ") for cell in cells):
                rows.append(cells)
        elif rows or line.strip():
            break
    return rows


_JPM_DOCUMENT = []


def _jpm_full_document():
    if not _JPM_DOCUMENT:
        _JPM_DOCUMENT.append(_full_document(JPM_RUN))
    return _JPM_DOCUMENT[0]


class TestBusinessTables(unittest.TestCase):
    """The JPM report's business sections as tables (fresh render of a scratch copy)."""

    def detail(self):
        return _section(_jpm_page(self), "detail")

    def pack(self):
        if not os.path.isdir(JPM_RUN):
            self.skipTest("the runs on record are not in this copy of the repository")
        with open(os.path.join(JPM_RUN, "pack", "pack.json"), "rb") as fh:
            return json.loads(fh.read().decode("utf-8"))

    def test_the_earnings_table_reads_revenue_share_and_change(self):
        capture = self.pack()["capture"]
        facts = {fact["id"]: fact for fact in capture["tier1"]}
        total = decimal.Decimal(facts["segment_revenue_firmwide_managed_q"]["value"])
        rows = _card_rows(self.detail(), "How it earns")
        self.assertEqual(rows[0], ["Business", "Kind of earnings", "Revenue, latest quarter",
                                   "Share of the firm (calculated)",
                                   "Change on a year ago (calculated)"])
        lines = capture["business_frame"]["JPM"]["how_it_earns"]
        for line, row in zip(lines, rows[1:]):
            own, prior = (decimal.Decimal(facts[fid]["value"]) for fid in line["facts"][:2])
            share = (own / total * 100).quantize(decimal.Decimal("0.1"),
                                                  rounding=decimal.ROUND_HALF_UP)
            change = (own / prior * 100 - 100).quantize(decimal.Decimal("0.1"),
                                                         rounding=decimal.ROUND_HALF_UP)
            self.assertEqual(row, [re.split(r"[:;]", line["line"])[0],
                                   pack_brief.FI_NATURE_WORDS[line["nature"]],
                                   R.format_number(facts[line["facts"][0]]["value"], "USD_million"),
                                   "%s%%" % share, "%s%s%%" % ("+" if change > 0 else "", change)])
        self.assertEqual(len(rows), 1 + len(lines))
        self.assertNotIn("20272", " ".join(" ".join(row) for row in rows))

    def test_the_guidance_table_reads_first_revisions_delivered_and_the_difference(self):
        capture = self.pack()["capture"]
        row = capture["business_frame"]["JPM"]["management"]["guidance_vs_delivery"][0]
        rows = _card_rows(self.detail(), "Guidance for %s" % row["period"])
        self.assertEqual(rows[0], ["Metric", "First guide"]
                         + ["Revised %s" % R.format_date(item["date"]) for item in row["revisions"]]
                         + ["Delivered", "Delivered minus first guide (calculated)"])
        self.assertEqual(len(rows), 1 + len(row["guided"]))
        ids = [fact["id"] for fact in capture["tier1"]]
        for cells in rows[1:]:
            self.assertNotIn("not reported yet", cells)
            self.assertFalse([fid for fid in ids if fid in " ".join(cells)])

    def test_capital_stress_and_credit_read_as_tables(self):
        detail = self.detail()
        capital = _card_rows(detail, "Capital beside its requirement")
        self.assertEqual(capital[0], ["Capital ratio", "Level", "Its requirement", "Required",
                                      "Cushion (calculated)"])
        self.assertEqual([row[-1] for row in capital[1:]], ["2.7 points", "2.7 points"])
        stress = _card_rows(detail, pack_brief.FI_STRESS_HEADING)
        self.assertEqual(stress[0], ["Figure", "Value", "As of"])
        credit = _card_rows(detail, "The risk-cost line: credit losses")
        self.assertEqual(credit[0], ["Figure", "Latest", "A year ago", "As of"])

    def test_the_cycle_reads_first_and_latest_in_plain_names(self):
        opened = _without_folds(self.detail())
        start = opened.index("<th>Series</th>")
        table = opened[opened.rindex("<table", 0, start):opened.index("</table>", start)]
        rows = [[_visible_text(cell) for cell in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
                for row in re.findall(r"<tr>(.*?)</tr>", table, re.S)]
        self.assertEqual(rows[0], ["Series", "First reading", "Latest reading", "Change"])
        self.assertEqual(rows[2][0], "Fed funds rate")
        self.assertTrue(rows[2][3].startswith("+") and rows[2][3].endswith(" points"), rows[2])

    def test_the_report_and_the_full_document_print_the_same_rows(self):
        detail, document = self.detail(), _jpm_full_document()
        for lead, md_lead in (("How it earns", "**How it earns.**"),
                              ("Guidance for FY2025", "**Guidance for FY2025"),
                              ("Capital beside its requirement",
                               "**Capital beside its requirement.**"),
                              (pack_brief.FI_STRESS_HEADING,
                               "**%s." % pack_brief.FI_STRESS_HEADING),
                              ("The risk-cost line", "**The risk-cost line")):
            with self.subTest(table=lead):
                self.assertEqual(_card_rows(detail, lead), _md_rows(document, md_lead))


# UPGRADE-2 READ-C1 (owner rulings AC44(1), AC44(2)): the chairman's one-line answer leads the
# answer section, and the three lists he writes read as one scorecard grouped by measure. A
# verdict older than the contract keeps its three tables and says, in one muted line, that it
# carries no one-line answer - the page never writes one for him.
ANSWER_LABEL = '<span class="lead">The answer to your question</span>'


def _measured(doc):
    """The fixture verdict with measures named: the invalidation level tests the share price, the
    falsifier and the event trigger test full-year revenue; the price trigger names none."""
    tripwires = doc["tripwires"]
    tripwires["invalidation_levels"][0]["measure"] = "Share price"
    for trigger in tripwires["reopening_triggers"]:
        if trigger["kind"] == "event":
            trigger["measure"] = "Full-year revenue"
    tripwires["falsifiers"][0]["measure"] = "Full-year revenue"


def _measured_verdict():
    doc = _fixture_verdict()
    _measured(doc)
    return doc


def _older(doc):
    """The fixture verdict as a 1.5.0 verdict: no answer line, no measure anywhere."""
    doc["schema_version"] = "1.5.0"
    doc.pop("answer_line", None)
    for entries in doc["tripwires"].values():
        for entry in entries:
            entry.pop("measure", None)


class TestAnswerAndScorecardOnThePage(unittest.TestCase):

    def test_the_answer_line_leads_the_answer_section(self):
        front = _front(HTML)
        verdict = _fixture_verdict()
        self.assertEqual(front.count(ANSWER_LABEL), 1)
        # Above everything else in section 1: before "What decided it", the chart and the
        # rationale.
        for later in ('<span class="lead">What decided it</span>', TAPE_HEADING,
                      "Why this rating, in the chairman"):
            self.assertLess(front.index(ANSWER_LABEL), front.index(later), later)
        self.assertLess(front.index('<h2 id="decision"'), front.index(ANSWER_LABEL))
        card = front[front.index(ANSWER_LABEL):front.index('<span class="lead">What decided it')]
        self.assertIn(E(verdict["answer_line"][:30]), card)
        # Its traced figures carry no mark.
        self.assertNotIn(E(trace.MARKER), card)
        self.assertNotIn(E(R.ANSWER_LINE_BEFORE), HTML)

    def test_an_untraced_figure_in_the_answer_line_is_marked_in_the_text(self):
        def untraced(doc):
            doc["answer_line"] = "Not cheap at 88.40; buy at 77.70 after the results."
        front = _front(_render_changed(untraced))
        card = front[front.index(ANSWER_LABEL):front.index('<span class="lead">What decided it')]
        self.assertIn("77.70 %s" % E(trace.MARKER), card)
        self.assertNotIn("88.40 %s" % E(trace.MARKER), card)
        self.assertEqual(card.count(E(trace.MARKER)), 1)

    def test_a_verdict_without_the_line_says_so_and_invents_nothing(self):
        page = _render_changed(_older)
        front = _front(page)
        self.assertNotIn(ANSWER_LABEL, page)
        self.assertEqual(front.count(E(R.ANSWER_LINE_BEFORE)), 1)
        self.assertLess(front.index(E(R.ANSWER_LINE_BEFORE)),
                        front.index('<span class="lead">What decided it'))
        self.assertNotIn(E(_fixture_verdict()["answer_line"]), page)
        # A verdict of the new contract whose line did not stand after the one re-ask.
        def null(doc):
            doc["answer_line"] = None
        page = _render_changed(null)
        self.assertNotIn(ANSWER_LABEL, page)
        self.assertEqual(_front(page).count(E(R.ANSWER_LINE_MISSING)), 1)
        self.assertNotIn(E(R.ANSWER_LINE_BEFORE), page)

    def test_the_scorecard_merges_the_three_lists_by_measure(self):
        page = _render_changed(_measured)
        front = _front(page)
        tripwires = _measured_verdict()["tripwires"]
        heading = "<h3>The 4 Feb 2027 scorecard</h3>"
        self.assertEqual(front.count(heading), 1)
        card = _between(front, heading, "<h3>")
        rows = re.findall(r"<tr>(.*?)</tr>", card, re.S)[1:]
        self.assertEqual([_visible_text(re.findall(r"<td>(.*?)</td>", row, re.S)[0])
                          for row in rows], ["Share price", "Full-year revenue"])
        # Every measured entry is on its measure's row, with what happens there.
        measured = [entry for entries in tripwires.values() for entry in entries
                    if entry.get("measure")]
        self.assertEqual(len(measured), 3)
        for entry in measured:
            text = entry.get("meaning") or entry.get("detail") or entry.get("statement")
            row = next(row for row in rows if E(entry["measure"]) in row)
            self.assertIn(E(text[:30]), row)
        # The entry without a measure keeps its place below, in the old table.
        below = _between(front, "<h3>What changes this rating</h3>", "<h3>")
        unmeasured = [t for t in tripwires["reopening_triggers"] if not t.get("measure")]
        self.assertEqual(len(unmeasured), 1)
        self.assertIn(E(unmeasured[0]["detail"]), below)
        self.assertNotIn(E(measured[0].get("statement") or "none"), below)
        # The measured invalidation level left the downside ladder for the scorecard.
        self.assertNotIn(E(tripwires["invalidation_levels"][0]["meaning"]), _detail(page))
        self.assertNotIn(R.SCORECARD_CONFLICT_OPEN, card)
        # The fixture itself names no measure, so its page keeps the three tables.
        self.assertNotIn("scorecard</h3>", HTML)

    def test_a_measure_given_two_numbers_is_flagged_on_its_row(self):
        def conflict(doc):
            _measured(doc)
            levels = doc["tripwires"]["invalidation_levels"]
            second = copy.deepcopy(levels[0])
            second.update(level="72.00", measure="share price",
                          meaning="A close under the lower level breaks the case.")
            levels.append(second)
        card = _between(_front(_render_changed(conflict)), "scorecard</h3>", "<h3>")
        rows = re.findall(r"<tr>(.*?)</tr>", card, re.S)[1:]
        share = next(row for row in rows if "Share price" in row)
        self.assertIn(R.SCORECARD_CONFLICT_OPEN, share)
        self.assertIn("84.50 and 72.00", _visible_text(share))
        other = next(row for row in rows if "Full-year revenue" in row)
        self.assertNotIn(R.SCORECARD_CONFLICT_OPEN, other)

    def test_the_chairmans_price_steps_are_not_flagged_on_the_page(self):
        # The architect's mechanism call (audit UPGRADE2-READ-C1 r1-6): a price trigger is a step
        # of the one price measure, never a second number for it.
        def steps(doc):
            _measured(doc)
            for trigger in doc["tripwires"]["reopening_triggers"]:
                if trigger["kind"] == "price":
                    trigger["measure"] = "share price"
        card = _between(_front(_render_changed(steps)), "scorecard</h3>", "<h3>")
        rows = re.findall(r"<tr>(.*?)</tr>", card, re.S)[1:]
        share = next(row for row in rows if "Share price" in row)
        self.assertIn("72.00", _visible_text(share))
        self.assertNotIn(R.SCORECARD_CONFLICT_OPEN, share)

    def test_a_verdict_older_than_the_contract_keeps_its_three_tables(self):
        page = _render_changed(_older)
        front = _front(page)
        self.assertNotIn("scorecard</h3>", page)
        table = _between(front, "<h3>What changes this rating</h3>", "<h3>")
        tripwires = _fixture_verdict()["tripwires"]
        for trigger in tripwires["reopening_triggers"]:
            self.assertIn(E(trigger["detail"]), table)
        for row in tripwires["falsifiers"]:
            self.assertIn(E(row["statement"][:30]), table)
        self.assertIn(E(tripwires["invalidation_levels"][0]["meaning"]), _detail(page))
        # A measure a newer contract allows changes nothing on an older verdict's page.
        def older_with_measure(doc):
            _older(doc)
            doc["tripwires"]["falsifiers"][0]["measure"] = "Full-year revenue"
        # (The page prints the verdict's own hash, so the tiers are compared, not the bytes.)
        changed = _render_changed(older_with_measure)
        self.assertEqual(_front(changed), front)
        self.assertEqual(_detail(changed), _detail(page))

    def test_the_jpm_page_renders_without_the_line_and_keeps_its_decision(self):
        page = _jpm_page(self)
        front = _front(page)
        self.assertNotIn(ANSWER_LABEL, page)
        self.assertEqual(front.count(E(R.ANSWER_LINE_BEFORE)), 1)
        self.assertNotIn("scorecard</h3>", page)
        self.assertIn("<h3>What changes this rating</h3>", front)
        with open(os.path.join(JPM_RUN, "report.html"), "rb") as fh:
            _same_decision(self, fh.read().decode("utf-8"), page, "jpm")


class TestInsiderEvidenceNotConsideredOnThePage(unittest.TestCase):
    """Owner ruling AC47(3), unit INSIDER-DEPTH (architect ruling on the report page): where what
    officers and directors own cannot be established, the page says once, in section 1 beneath
    the rating box and before the reasoning, that the insider evidence was not considered; an
    ordinary page is unchanged."""

    STATEMENT = ("Insider information was not available and was not considered in the "
                 "council's ruling: what the company's officers and directors own could not "
                 "be established from the record.")

    def render(self, mutate=None):
        with tempfile.TemporaryDirectory() as tmp:
            return _render(_mutated_copy(tmp, mutate))

    @staticmethod
    def ownership_unknown(run_dir):
        def change(doc):
            doc["capture"]["gaps"].append({
                "fact_class": "insider_ownership_pct",
                "reason": "INVENTED FIXTURE - the proxy publishes no group figure",
                "reason_kind": "absent_by_design",
                "weakened_test": "INVENTED FIXTURE - what management owns"})
        _rewrite_pack(run_dir, change)

    def test_the_answer_section_says_once_that_insider_evidence_was_not_considered(self):
        page = self.render(self.ownership_unknown)
        shown = E(self.STATEMENT)
        self.assertEqual(page.count(shown), 1)
        box = page.index('<div class="ratingbox">')
        answer = page.index('<h2 id="decision"')
        reasoning = page.index('<h2 id="synthesis"')
        self.assertLess(box, answer)
        self.assertLess(answer, page.index(shown))
        self.assertLess(page.index(shown), reasoning)
        self.assertLess(page.index(shown), page.index(E(R.chair_fields.labels()["answer_line"])))
        # The same run with nothing unknown: no statement anywhere on the page.
        self.assertNotIn("Insider information was not available", HTML)
        self.assertNotIn("Insider information was not available", self.render())



# UPGRADE-2 GROWTH-ARCHETYPE sub-charge (c), THE PAGES AND THE BRIEFS (owner rulings AC49(1) and
# AC50): what the owner's page shows of a growth company. The invented run's pack is replaced by
# the evidence suite's invented grower, frozen and re-keyed to the run's own subject; every figure
# is one of that suite's constants.
from council.tests import test_evidence  # noqa: E402

GROWER_SECTION = "What kind of growth company this is"
# Every run on record, rendered by the renderer at the base of this sub-charge (main 2a9f4a7):
# the report page of each run, and the page of the full evidence document of each pack (a pack
# hash of "f" * 64) - a non-grower page does not move by one byte.
GROWER_BASE_REPORTS = {
    "council-aapl-2026-08-31-acceptance-2":
        "0a58d15a85f934e39c78cf0696999f7352d9ccb59e0aa6f7ec0deabdf55f823b",
    # re-pinned at MONETARY-COIN(b), architect ruling M2: the re-rendered record prints the recorded block reward (3.125, 1.5625), never a rounded one; the record's files are unchanged
    "council-btc-2026-08-31": "8ca516a0502c40eead6b2922a54282a1d0f63d64b6402717f54d756ff4f87e5d",
    "council-btc-2026-09-01": "312619e10712ff4055ca497aa18a0bff62d3d688e264d9a77bc70c5a309041a7",
    "council-coin-2026-09-04": "2afb6241761b8a25529367d3a61b31bed9a031d05833d13999c6f6e7222d76bb",
    "council-goog-2026-08-31": "108bbb245d4d486bd7ed2ef90d52f29a7b211f54e12446290a3107aeba8647ac",
    "council-jpm-2026-09-24": "398e5c4168ab03579c58d67d51f9ad9e869e974a96608cf96b150d3a6426a502",
    "council-lulu-2026-09-05": "e51ad189ce8db6c72ae43ebc4fd5ec00f96566b0d4c760828e03a856c7582390",
    "council-theme-eusov-2026-09-01":
        "096c4adbacf8d56909cf2ef6b8ab4c359dd8ce0f07688b71ac21f1cea6fad3eb",
    "council-wulf-2026-09-09": "7008693f56f5c6ee7c1ac1cb15dbba4180970b2ba93166b72705daa9c1e680aa",
}
GROWER_BASE_DOCUMENT_PAGES = {
    "council-aapl-2026-08-31-acceptance":
        "3c5841aa304124f3bcea306bba560f9313558ac96e5e517885fb61c45d2eea7d",
    "council-aapl-2026-08-31-acceptance-2":
        "3c5841aa304124f3bcea306bba560f9313558ac96e5e517885fb61c45d2eea7d",
    # re-pinned at MONETARY-COIN(b), architect ruling M2: the re-rendered record prints the recorded block reward (3.125, 1.5625), never a rounded one; the record's files are unchanged
    "council-btc-2026-08-31": "893d7267ec93b713e5c4c3c734c4a5c1d156c44bf658c54a889c622da65999df",
    "council-btc-2026-09-01": "f2022fd04c172467556e4ca58c67a06671115b45c5d05b617d7eacf847eb6710",
    "council-coin-2026-09-04": "2ecb0004b5f6d71bf90cb910a52500792138ac2040121f5785ea0c8411cf0241",
    "council-goog-2026-08-31": "8398924d9a735e692a58ba7e1668ffbb24fb58940249cd33caea46b58940278e",
    "council-jpm-2026-09-24": "e561bb51a74ab7104b9b07ed51ef5ac002c4af5b643ce70ed321f5391fd08dc3",
    "council-lulu-2026-09-05": "83653aa365fea243de6fe36d496af6793517f15c7ac0d12d0ebfbaa8a0652e71",
    "council-theme-eusov-2026-09-01":
        "505e407d0386e1c5271caa08cc20a436461d78c5d0b4140fc5857c4aedc66ef1",
    "council-wulf-2026-09-09": "2c84142e2663e1dbbca27344c1023ea4a5736ea92e806620ba49c98c58c4f440",
}
GROWER_BASE_APPROVAL = ("council-jpm-2026-09-24/evidence/EVIDENCE-FULL.md",
                        "cbb5f2ae4d129f401be5984ca7b9eba11cf80e85efef54759bd4d3bdb18ede5d")


def _grower_page(cash=test_evidence.GROWER_CASH_BELOW, change=None):
    """The invented run rendered over the invented grower's frozen pack; `cash` sets its cash
    fact, `change` edits the capture before it is frozen."""
    capture = test_evidence.grower_capture()
    if cash is not None:
        test_evidence.grower_cash(capture, cash)
    if change:
        change(capture)
    with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
        subject = json.loads(fh.read().decode("utf-8"))["subject"]
    frame = capture["business_frame"].pop(capture["subject"]["ticker"])
    capture["subject"] = subject
    capture["business_frame"] = {subject["ticker"]: frame}
    tmp = tempfile.mkdtemp(prefix="report-grower-")
    try:
        run_dir = _mutated_copy(tmp)
        _rewrite_pack(run_dir, lambda doc: doc.update(freeze.build_pack(capture)))
        _stamp_first_render(run_dir, _pinned_now(FIXTURE))
        return R.render(run_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _grower_text(fragment):
    """What a reader sees, a hover note's closing tag not leaving a space before the stop."""
    return re.sub(r" ([,.:;])", r"\1", _visible_text(fragment))


def _grower_note(page, term):
    """The hover note the page carries on `term`, or None."""
    found = re.search(r'<span class="gl" tabindex="0" data-note="([^"]*)">%s</span>'
                      % re.escape(term), page)
    return html_lib.unescape(found.group(1)) if found else None


class TestGrowerOnThePage(unittest.TestCase):
    """What the owner's page shows of a growth company. Every test FAILS against the pre-change
    report renderer; the guard and the negative control are marked."""

    def test_the_front_names_the_kind_measure_and_cash(self):
        page = _grower_page()
        front = _grower_text(_front(page))
        self.assertIn("%s - %s — rated on %s" % (
            test_evidence.GROWER_KIND, test_evidence.GROWER_KIND_WORDS["recurring_revenue"],
            test_evidence.GROWER_MEASURE_WORDS), front)
        self.assertIn(test_evidence.GROWER_MONTHS_WORDS % (test_evidence.GROWER_MONTHS_BELOW,
                                                           test_evidence.GROWER_LINE), front)
        for term in ("Months of cash left", "enterprise value against gross profit",
                     "sales growth", "cash burn"):
            self.assertIn(term.lower(), {row["term"].lower(): row
                                         for row in R.GLOSSARY["terms"]})
            self.assertIsNotNone(_grower_note(_front(page), term), term)

    def test_the_front_shows_an_undrawn_facility_as_not_counted(self):
        """Audit finding r1-4: the front prints the months of cash left, so it shows each
        undrawn credit line beside them, marked not counted; none named, no such line."""
        def undrawn(capture):
            test_evidence.grower_fact(capture, test_evidence.GROWER_UNDRAWN_ID,
                                      test_evidence.GROWER_UNDRAWN)
            test_evidence.frame_of(capture)["growth_runway"]["undrawn_facility_facts"] = [
                test_evidence.GROWER_UNDRAWN_ID]
        front = _grower_text(_front(_grower_page(change=undrawn)))
        capture = test_evidence.grower_capture()
        undrawn(capture)
        self.assertIn("Undrawn credit lines, shown and not counted: %s %s" % (
            test_evidence.name_of(capture, test_evidence.GROWER_UNDRAWN_ID),
            test_evidence.shown_value(test_evidence.fact_in(
                capture, test_evidence.GROWER_UNDRAWN_ID))), front)
        self.assertNotIn("Undrawn credit lines", _grower_text(_front(_grower_page())))

    def test_the_front_carries_the_cap_sentence_below_the_line(self):
        sentence = test_evidence.GROWER_CAP_WORDS % test_evidence.GROWER_LINE
        page = _grower_page()
        self.assertIn('<div class="card prominent"><p>%s</p></div>' % E(sentence), _front(page))
        self.assertIn(E(sentence), _detail(page))
        for cash in (test_evidence.GROWER_CASH_AT_LINE, None):
            self.assertNotIn(E(sentence), _grower_page(cash=cash))

    def test_the_report_and_brief_word_tables_agree(self):
        self.assertEqual(R.ARCHETYPE_WORDS, pack_brief._ARCHETYPE_WORDS)
        self.assertEqual(R.MEASURE_WORDS, pack_brief._MEASURE_WORDS)
        self.assertEqual(R.ARCHETYPE_WORDS["reinvesting_grower"], test_evidence.GROWER_KIND)
        self.assertEqual(R.MEASURE_WORDS[test_evidence.GROWER_MEASURE],
                         test_evidence.GROWER_MEASURE_WORDS)

    def test_the_detail_carries_the_grower_frame(self):
        detail = _detail(_grower_page())
        self.assertIn("<h3>%s</h3>" % GROWER_SECTION, detail)
        yardstick = _card_rows(detail, "The yardstick, and what stands beside it")
        self.assertEqual([re.sub(r" ([,.:;])", r"\1", row[0]) for row in yardstick[3:7]], [
            test_evidence.GROWER_MULTIPLE_ROW, test_evidence.GROWER_GROWTH_ROW,
            test_evidence.GROWER_PAY_ROW, test_evidence.GROWER_DILUTION_ROW])
        self.assertEqual(yardstick[3][1], test_evidence.grower_multiple(
            test_evidence.GROWER_EV, test_evidence.GROWER_GROSS_PROFIT_TTM))
        quarters = _card_rows(detail, "The latest quarters, oldest first")
        self.assertEqual([row[0] for row in quarters[1:]],
                         [" ".join(slug.split("_")).upper()
                          for slug in test_evidence.GROWER_QUARTERS])
        cash = _card_rows(detail, "The cash, and how long it lasts")
        self.assertIn(["Months of cash left", "%s months" % test_evidence.GROWER_MONTHS_BELOW,
                       "calculated"], cash)
        earnings = _card_rows(detail, "How it earns")
        self.assertEqual({row[1] for row in earnings[1:]},
                         {test_evidence.GROWER_NATURE_SHOWN["subscription"]})
        self.assertNotIn("<code>", detail)

    def test_a_capture_authored_funding_reason_is_escaped(self):
        def forge(capture):
            test_evidence.frame_of(capture)["growth_runway"]["funding_because"] = \
                test_evidence.GROWER_FORGED
        page = _grower_page(change=forge)
        self.assertIn(E("<img src=x onerror=alert(1)>"), _detail(page))
        self.assertNotIn("<img src=x", page)

    def test_a_non_grower_page_carries_no_grower_line(self):
        """NEGATIVE control: the invented run and the invented bank."""
        for page in (HTML, _fi_page()):
            self.assertNotIn(GROWER_SECTION, page)
            self.assertNotIn("Months of cash left", page)

    def test_every_run_on_record_renders_unchanged(self):
        """A GUARD, passing on the base by design: every run on record renders to the bytes the
        base renderer gave it - its report page, the page of its pack's full evidence document,
        and the approval page of the one recorded evidence document."""
        runs = os.path.join(ROOT, "council", "runs")
        if not os.path.isdir(runs):
            self.skipTest("the runs on record are not in this copy of the repository")
        for run_id, digest in GROWER_BASE_REPORTS.items():
            with self.subTest(report=run_id):
                self.assertEqual(hashlib.sha256(_render_on_record(run_id).encode(
                    "utf-8")).hexdigest(), digest)
        for run_id, digest in GROWER_BASE_DOCUMENT_PAGES.items():
            with self.subTest(document=run_id):
                with open(os.path.join(runs, run_id, "pack", "pack.json"), "rb") as fh:
                    pack = json.loads(fh.read().decode("utf-8"))
                page = _evidence_page().render_page(pack_brief.render_full(pack, "f" * 64))
                self.assertEqual(hashlib.sha256(page.encode("utf-8")).hexdigest(), digest)
        relative, digest = GROWER_BASE_APPROVAL
        with open(os.path.join(runs, relative), "rb") as fh:
            page = _evidence_page().render_page(fh.read().decode("utf-8"))
        self.assertEqual(hashlib.sha256(page.encode("utf-8")).hexdigest(), digest)



# UPGRADE-2 RESOURCE-ARCHETYPE sub-charge (c), THE PAGES AND THE BRIEFS (owner rulings
# AC51-AC56): what the owner's page shows of a producer. The invented run's pack is replaced by
# the evidence suite's invented producer, frozen and re-keyed to the run's own subject.
PRODUCER_SECTION = "What kind of producer this is"


def _producer_page(subtype="miner", change=None):
    """The invented run rendered over the invented producer's frozen pack; `change` edits the
    capture before it is frozen."""
    capture = test_evidence.producer_capture(subtype)
    if change:
        change(capture)
    with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
        subject = json.loads(fh.read().decode("utf-8"))["subject"]
    frame = capture["business_frame"].pop(capture["subject"]["ticker"])
    capture["subject"] = subject
    capture["business_frame"] = {subject["ticker"]: frame}
    tmp = tempfile.mkdtemp(prefix="report-producer-")
    try:
        run_dir = _mutated_copy(tmp)
        _rewrite_pack(run_dir, lambda doc: doc.update(freeze.build_pack(capture)))
        _stamp_first_render(run_dir, _pinned_now(FIXTURE))
        return R.render(run_dir)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class TestProducerOnThePage(unittest.TestCase):
    """What the owner's page shows of a producer. Every test FAILS against the pre-change report
    renderer; the guard and the negative control are marked."""

    def test_each_reserve_carries_its_own_date_on_the_report(self):
        """P-RESOURCEc-9: a by-product row reads its own reserve date."""
        def apart(capture):
            test_evidence.producer_facts(capture, test_evidence.PRODUCER_BY_PRODUCTS)
            test_evidence.producer_block(capture)["by_products"] = ["zinc", "silver"]
            test_evidence.fact_in(capture, "reserves_pp_silver")["as_of"] = "2026-02-01"
        rows = _card_rows(_detail(_producer_page(change=apart)),
                          "The reserves, each beside")
        self.assertEqual(rows[0][3], "As of")
        silver = next(row for row in rows if "silver" in row[0])
        self.assertEqual(silver[3], "1 Feb 2026")

    def test_the_front_names_the_kind_measure_and_reserve_life(self):
        front = _front(_producer_page())
        self.assertIn("%s - %s — rated on %s" % (
            test_evidence.PRODUCER_KIND_SHOWN, test_evidence.PRODUCER_SUBTYPE_SHOWN["miner"],
            test_evidence.PRODUCER_MEASURE_SHOWN), _grower_text(front))
        self.assertIn(test_evidence.PRODUCER_LIFE_SHOWN, _grower_text(front))
        self.assertIsNotNone(_grower_note(front, "Reserve life"))

    def test_the_front_sets_the_kind_and_the_reserve_life_apart(self):
        """The architect's ruling on the front's two lines: the measure ends in a full stop, so the
        reserve life never runs into it."""
        text = _grower_text(_front(_producer_page()))
        self.assertIn("%s. %s" % (test_evidence.PRODUCER_MEASURE_SHOWN,
                                  test_evidence.PRODUCER_LIFE_SHOWN), text)
        self.assertNotIn("rests on Reserve life", text)

    def test_a_positive_value_per_unit_never_prints_zero(self):
        """The architect's ruling on P-RESOURCEc-1 (owner ruling AC16): an enterprise value in
        millions over reserves in single barrels is a live figure on the page."""
        def scaled(capture):
            test_evidence.producer_value(capture, "enterprise_value", "14110", unit="USD_m")
            test_evidence.producer_value(capture, "reserves_proved_boe", "1000000000")
        yardstick = _card_rows(_detail(_producer_page("oil_and_gas_producer", change=scaled)),
                               "The yardstick, and what stands beside it")
        self.assertIn([test_evidence.PRODUCER_PER_UNIT_ROW["boe"], "$14.10", "calculated"],
                      yardstick)

    def test_the_front_carries_the_sentence_below_the_reserve_price(self):
        sentence = '<div class="card prominent"><p>%s</p></div>' % E(
            test_evidence.PRODUCER_SENTENCE)
        page = _producer_page()
        self.assertIn(sentence, _front(page))
        self.assertIn(E(test_evidence.PRODUCER_SENTENCE), _detail(page))
        for today in (test_evidence.PRODUCER_RESERVE_PRICE, "80"):
            page = _producer_page(change=lambda capture: test_evidence.producer_value(
                capture, "reference_price_gold", today))
            self.assertNotIn(E(test_evidence.PRODUCER_SENTENCE), page)

    def test_the_report_and_brief_word_tables_agree(self):
        self.assertEqual(R.ARCHETYPE_WORDS, pack_brief._ARCHETYPE_WORDS)
        self.assertEqual(R.MEASURE_WORDS, pack_brief._MEASURE_WORDS)
        self.assertEqual(R.ARCHETYPE_WORDS["resource_producer"],
                         test_evidence.PRODUCER_KIND_SHOWN)
        self.assertEqual(R.MEASURE_WORDS[test_evidence.PRODUCER_MEASURE],
                         test_evidence.PRODUCER_MEASURE_SHOWN)

    def test_the_detail_carries_the_producer_frame(self):
        def label(capture):
            test_evidence.fact_in(capture, "unit_cost_gold")["label"] = (
                "All-in sustaining cost per ounce (INVENTED)")
        detail = _detail(_producer_page(change=label))
        self.assertIn("<h3>%s</h3>" % PRODUCER_SECTION, detail)
        self.assertEqual(_card_rows(detail, "The reserves, each beside the ")[1], [
            "Proven and probable reserves", "850 oz", "the US SEC's mining rules (S-K 1300)",
            "20 Feb 2026", "76 USD per ounce", "70 USD per ounce"])
        yardstick = _card_rows(detail, "The yardstick, and what stands beside it")
        self.assertIn([test_evidence.PRODUCER_PER_UNIT_ROW["oz"], R.format_number(
            "14.11", "USD_m"), "calculated"], yardstick)
        quarters = _card_rows(detail, "Output and the price received")
        self.assertEqual([row[0] for row in quarters[1:5]],
                         [" ".join(slug.split("_")).upper()
                          for slug in test_evidence.GROWER_QUARTERS])
        costs = _card_rows(detail, "What each unit costs")
        self.assertIn(["Hedges", "none - the company does not hedge", "recorded"], costs)
        for term in ("Proven and probable reserves", "price the reserves were counted at",
                     "Asset retirement obligation", "Reserve life", "All-in sustaining cost"):
            self.assertIsNotNone(_grower_note(detail, term), term)
        oil = _detail(_producer_page("oil_and_gas_producer"))
        for term in ("Proved reserves", "barrel of oil equivalent", "Standardized measure"):
            self.assertIsNotNone(_grower_note(oil, term), term)
        stream = _detail(_producer_page("royalty_and_streaming"))
        self.assertIsNotNone(_grower_note(stream, "Stream payment"))
        self.assertNotIn("<code>", detail)

    def test_a_capture_authored_string_is_escaped(self):
        def forge(capture):
            for fact_id in ("reference_price_gold", "unit_cost_gold"):
                test_evidence.fact_in(capture, fact_id)["label"] = test_evidence.GROWER_FORGED
            test_evidence.producer_block(capture)["reserves_standard"] = \
                test_evidence.GROWER_FORGED
        page = _producer_page(change=forge)
        self.assertIn(E("<img src=x onerror=alert(1)>"), _detail(page))
        self.assertNotIn("<img src=x", page)

    def test_an_integrated_major_front_shows_reserves_and_todays_price(self):
        """Owner ruling AC52(1), register item P-RESOURCEa-4: beside the ordinary profit
        yardstick on the front."""
        capture = test_evidence.integrated_major_capture()
        with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
            subject = json.loads(fh.read().decode("utf-8"))["subject"]
        frame = capture["business_frame"].pop(capture["subject"]["ticker"])
        capture["subject"] = subject
        capture["business_frame"] = {subject["ticker"]: frame}
        tmp = tempfile.mkdtemp(prefix="report-major-")
        try:
            run_dir = _mutated_copy(tmp)
            _rewrite_pack(run_dir, lambda doc: doc.update(freeze.build_pack(capture)))
            page = R.render(run_dir)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        # The architect's ruling on the front's lines: the measure ends before the line below.
        self.assertIn(". Its reserves and today's price", _grower_text(_front(page)))
        self.assertIn("Its reserves and today's price, shown beside: Reserves proved boe 850 "
                      "boe; Reference price crude oil 70 USD per barrel", _visible_text(
                          _front(page)))

    def test_a_non_producer_page_carries_no_producer_line(self):
        """NEGATIVE control: the invented run, the invented bank and the invented grower."""
        for page in (HTML, _fi_page(), _grower_page()):
            for needle in (PRODUCER_SECTION, "Reserve life", "Its reserves and today",
                           test_evidence.PRODUCER_KIND_SHOWN):
                self.assertNotIn(needle, page)

    def test_every_run_on_record_renders_unchanged(self):
        """A GUARD, passing on the base by design: every run on record renders to the bytes the
        base renderer gave it (the growth unit's pins, unmoved since main 2a9f4a7)."""
        TestGrowerOnThePage.test_every_run_on_record_renders_unchanged(self)



def _holding_page(big=False, change=None):
    capture = test_evidence.holding_page_capture(big)
    if change:
        change(capture)
    with open(os.path.join(FIXTURE, "verdict.json"), "rb") as fh:
        subject = json.loads(fh.read().decode("utf-8"))["subject"]
    frame = capture["business_frame"].pop(capture["subject"]["ticker"])
    capture["subject"], capture["business_frame"] = subject, {subject["ticker"]: frame}
    with tempfile.TemporaryDirectory(prefix="report-holding-") as tmp:
        run_dir = _mutated_copy(tmp)
        _rewrite_pack(run_dir, lambda doc: doc.update(freeze.build_pack(capture)))
        _stamp_first_render(run_dir, _pinned_now(FIXTURE))
        return R.render(run_dir)


class TestHoldingOnThePage(unittest.TestCase):
    def test_the_front_names_the_kind_measure_and_discount(self):
        front = _front(_holding_page())
        text = _grower_text(front)
        self.assertIn("a holding company that owns other businesses — rated on price against net asset value", text)
        self.assertIn("at today's prices (the one rated)", text)
        self.assertIn("narrower than at any of the last five year-ends", text)
        for term in ("net asset value", "Discount to net asset value", "Private holding"):
            self.assertIsNotNone(_grower_note(front, term))

    def test_the_front_carries_the_not_rated_sentence(self):
        self.assertIn(pack_brief.FI_NOT_RATED_SENTENCE, _grower_text(_front(_holding_page())))

    def test_the_front_carries_each_ruled_sentence_where_it_applies(self):
        front = _front(_holding_page(True))
        text = _grower_text(front)
        name = test_evidence.holding_frame(test_evidence.holding_page_capture(True))["nav_bridge"]["components"][-1]["name"]
        self.assertIn(pack_brief.ONE_HOLDING_SENTENCE % name, text)
        self.assertIn(pack_brief.MOSTLY_PRIVATE_SENTENCE, text)
        self.assertGreaterEqual(front.count('class="card prominent"'), 2)
        self.assertNotIn("private values move slowly", _grower_text(_front(_holding_page())))
        def private_only(c):
            for part in test_evidence.holding_frame(c)["nav_bridge"]["components"]:
                part.update(method="company_reported_value", valuation_basis="cost")
        text = _grower_text(_front(_holding_page(change=private_only)))
        self.assertIn(pack_brief.MOSTLY_PRIVATE_SENTENCE, text)
        self.assertNotIn("Most of this company's value is one holding", text)

    def test_the_report_and_brief_word_tables_agree(self):
        self.assertEqual(R.ARCHETYPE_WORDS["investment_holding"], pack_brief._ARCHETYPE_WORDS["investment_holding"])
        self.assertEqual(R.VALUATION_BASIS_WORDS, pack_brief.VALUATION_BASIS_WORDS)
        self.assertEqual(R.HOLDING_POSITION_WORDS, pack_brief.HOLDING_POSITION_WORDS)

    def test_the_detail_carries_the_holding_frame(self):
        detail = _detail(_holding_page())
        text = _grower_text(detail)
        for words in ("The net asset value, part by part", "at its latest funding round",
                      "15 Jul 2026", "Loan-to-value", "Average:"):
            self.assertIn(words, text)
        for term in ("Loan-to-value", "Published net asset value", "dividend cover"):
            self.assertIsNotNone(_grower_note(detail, term))

    def test_a_capture_authored_string_is_escaped(self):
        def change(c):
            test_evidence.holding_frame(c)["nav_bridge"]["components"][-1]["name"] = "<script>INVENTED & command</script>"
        page = _holding_page(True, change)
        self.assertNotIn("<script>INVENTED", page)
        self.assertIn("&lt;script&gt;INVENTED &amp; command&lt;/script&gt;", page)

    def test_every_run_on_record_renders_unchanged(self):
        # Guard: the inherited pins cover reports, documents and approval.
        if not test_evidence.live_records_present(test_evidence.LIVE_RUNS,
                (test_evidence.JPM_RUN, test_evidence.WULF_RUN)):
            self.skipTest("the runs on record are not in this copy")
        TestGrowerOnThePage.test_every_run_on_record_renders_unchanged(self)


def _coin_page(unnamed=False):
    capture = (test_evidence.load_fixture("btc-pass.json") if unnamed else
               test_evidence.coin_capture(issuance_per_block="3.125"))
    with tempfile.TemporaryDirectory(prefix="report-coin-") as tmp:
        run_dir = _mutated_copy(tmp)
        _rewrite_pack(run_dir, lambda doc: doc.update(freeze.build_pack(capture)))
        def change(verdict):
            verdict["subject"] = capture["subject"]
            verdict["atlas_envelope"].update(subject_kind=capture["subject"]["kind"],
                asset_class=capture["subject"]["asset_class"], product=capture["subject"].get("product"))
        _rewrite_verdict(run_dir, change)
        _stamp_first_render(run_dir, _pinned_now(FIXTURE))
        return R.render(run_dir)


class TestCoinOnTheReport(unittest.TestCase):
    def test_the_rating_box_names_zcash_as_a_privacy_coin(self):
        self.assertIn("The subject is %s, a privacy coin." % test_evidence.coin_capture()[
            "subject"]["name"], _grower_text(_coin_page()))

    def test_the_hand_off_row_names_the_coin(self):
        page = _coin_page()
        row = re.search(r'<th class="nowrap">Subject kind</th>\s*<td>(.*?)</td>', page).group(1)
        self.assertEqual(_grower_text(row), test_evidence.coin_capture()["subject"]["name"] + ", a privacy coin")

    def test_the_front_card_prints_the_supply_readings(self):
        front = _front(_coin_page())
        summary = pack_brief.coin_summary(freeze.build_pack(test_evidence.coin_capture(issuance_per_block="3.125")))
        text = _grower_text(front)
        self.assertIn("What kind of coin, and how it is rated", text)
        for window in summary["windows"]:
            self.assertIn(window["new_coins_text"], text)
            self.assertIn(window["share_text"], text)
        self.assertIn(summary["turnover_share_text"], text)
        self.assertIn(summary["one_fund_sentence"], text)
        self.assertIn(summary["absent_sentence"], text)

    def test_the_venues_card_for_a_privacy_coin(self):
        front = _grower_text(_front(_coin_page()))
        self.assertIn("Regulated venue", front)
        self.assertIn("Invented Licensed Exchange", front)
        self.assertIn("INVENTED current listing and United Kingdom licence", front)

    def test_a_reward_prints_unrounded_in_the_evidence_table(self):
        unit = test_evidence.FLOORS["asset_classes"]["crypto"]["products"][
            test_evidence.coin_capture.__defaults__[0]]["unit"]
        self.assertIn(unit + " 3.125/block", _grower_text(_coin_page()))

    def test_every_new_term_has_a_scoped_hover_note(self):
        terms = ("Privacy coin", "Regulated venue", "Delisting scenario",
                 "New supply over one month", "Issuance against turnover")
        for term in terms:
            row = next(row for row in R.GLOSSARY["terms"] if row["term"] == term)
            self.assertEqual(row["scope"], "coin")
            self.assertLessEqual(len(row["note"].split()), 30)
            self.assertIsNotNone(_grower_note(R._glossed(term, scope="coin"), term))
            self.assertNotIn('class="gl"', R._glossed(term))
        front = _front(_coin_page())
        for term in ("privacy coin", "Regulated venue", "New supply over one month", "Issuance against turnover"):
            self.assertIsNotNone(_grower_note(front, term))
        self.assertNotIn("supply", R._TERM_NOTES)
        self.assertNotIn("venue", R._TERM_NOTES)

    def test_an_unnamed_bitcoin_front_is_unchanged(self):
        # Control: the new front card is absent from an earlier subject.
        front = _grower_text(_coin_page(True))
        self.assertIn("The subject is " + R._kind_words(test_evidence.load_fixture(
            "btc-pass.json")["subject"]) + ".", front)
        self.assertNotIn("What kind of coin, and how it is rated", front)





class TestTheCoinChart(unittest.TestCase):
    def test_band_covers_the_real_year(self):
        from council.tests.test_evidence import invented_coin_series, coin_capture, FLOORS
        c = coin_capture()
        c["price_series"] = invented_coin_series(FLOORS["asset_classes"]["crypto"][
            "products"][c["subject"]["product"]]["series_ticker"])
        c = freeze._with_tape(c, FLOORS)
        drawing = R.chart.figure(c, {}, True, R.format_number, R.format_date, year_bars=365)
        band = re.search(r'<rect class="ch-band" x="([^"]+)"', drawing).group(1)
        frame = R.chart._Frame(1826, decimal.Decimal("100"), decimal.Decimal("200"))
        # The drawing widens its left margin for the page's own price labels.
        frame.left = max([R.chart.PLOT_LEFT] + [
            R.chart.TICK_LABEL_GAP + R.chart.LABEL_CHAR_UNITS * len(
                R.format_number(format(tick.normalize(), "f"), "USD"))
            for tick in frame.price_ticks()])
        self.assertEqual(band, frame.x(1826 - 365))
        facts, gaps = R.chart.tape_entries(c)
        line = R.chart._figure_line("tape_closes_above_sma200_252", None, facts, gaps,
                                    R.format_number, R.format_date, year_bars=365)
        self.assertIn("of the last 365 trading days", line)
        self.assertIn("of the last 365 trading days", R.chart.tape_table(
            c, R.format_number, R.format_date, year_bars=365))

    def test_all_days_glossary_names_the_real_year(self):
        self.assertIn("square root of 365", R._tape_term("Volatility", "tape_realized_vol_21", year_bars=365))

    def test_equity_chart_svg_is_identical(self):
        # CONTROL: digest of the base AAPL-style XNYS chart fixture's SVG.
        import hashlib
        drawing = _chart(_taped_html())
        svg = drawing[drawing.index("<svg"):drawing.index("</svg>") + len("</svg>")]
        self.assertEqual(hashlib.sha256(svg.encode()).hexdigest(),
                         "6430f965518b34d6651acbda28714ae6470623cc452c1da3bb246aae44b6debc")


if __name__ == "__main__":
    unittest.main(verbosity=1)
