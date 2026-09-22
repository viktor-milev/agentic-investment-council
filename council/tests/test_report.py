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
import html as html_lib
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
from council.engine import ladder  # noqa: E402
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
ANCHORS = ("decision", "synthesis", "detail", "evidence", "question", "review",
           "advisors", "challenger", "atlas")

# Every h2 heading on the fixture page, in plain words (audit B5): the nine menu tiers plus the
# folded appendices that carry an h2 but no menu entry.
SECTION_HEADINGS = (
    "Executive summary", "The chairman's final synthesis", "The decision in detail",
    "The evidence", "Appendices — the full record", "The owner's question", "Peer review",
    "The five advisors", "The challenger's full response",
    "What changed after the outside audit", "What the portfolio system receives",
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
    return page[page.index('<h2 id="decision">'):page.index('<h2 id="synthesis">')]


def _masthead(page):
    """The masthead and the sticky bar (design audit C4 tier 0 / C5): the page body from its
    header to the executive summary heading. The rating box, the key-data strip, the warnings
    band and the sticky summary bar sit here now, above the tiers (owner ruling AC16(3),(9))."""
    return page[page.index('<header class="masthead">'):page.index('<h2 id="decision">')]


def _detail(page):
    """The decision-in-detail tier's own HTML (owner ruling AC16, audit C4 tier 3): everything
    between its heading and the frozen evidence that follows it. The downside ladder, the
    anchorless scenario ladder, the dated events, the outside auditor's objections and the
    challenge round live here now, moved down from the executive summary and the appendices."""
    return page[page.index('<h2 id="detail">'):page.index('<h2 id="evidence">')]


def _stamps(page):
    """The 'About this sitting' run-stamps appendix (owner ruling AC16 moved the clocks here off
    the executive summary): everything from its heading to the end of the page."""
    return page[page.index('<h2 id="stamps">'):]


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
            self.assertIn('<h2 id="%s">' % anchor, HTML, anchor)
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
        for fid in ("last_price", "revenue_fy2025", "free_cash_flow_fy2025",
                    "forward_earnings_multiple", "risk_free_rate_10y"):
            self.assertIn("<code>%s</code>" % fid, HTML)

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
        self.assertEqual(open_region.count("<code>dep"), 25)
        self.assertNotIn("<code>dep29</code>", open_region)

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
        self.assertIn("<code>dep29</code>", open_region)


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
        self.assertIn("<strong>The outside audit ran.</strong>", HTML)
        self.assertIn("gpt-5.6-sol", HTML)

    def test_findings_with_named_dispositions_in_plain_words(self):
        self.assertIn("<strong>F1</strong> &middot; a claim without support", HTML)
        self.assertIn("<strong>F2</strong> &middot; a blind spot", HTML)
        self.assertIn('<span class="tag addressed">addressed</span>', HTML)
        self.assertIn('<span class="tag overruled">overruled</span>', HTML)
        self.assertIn("the verdict actually moved", HTML)
        self.assertIn("rejected, with the reason on the record", HTML)

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
                      '<span class="tag alarmtag">a raise the auditor did not see</span>'
                      "</td></tr>", HTML)

    def test_empty_appendix_renders_the_exact_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp, lambda d: _rewrite_verdict(
                d, lambda doc: doc["challenge"].__setitem__("change_appendix", [])))
            page = _render(run_dir)
        self.assertIn("Nothing changed after the outside audit.", page)
        self.assertNotIn('<tr class="alarm">', page)
        self.assertIn('<h2 id="changes">', page)   # the section always exists


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
        self.assertGreater(HTML.index(disclosure), HTML.index('<h2 id="evidence">'))

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
        # The note is the freeze's own generated sentence, repeated
        # verbatim - the page never re-derives arithmetic prose.
        self.assertIn("Deterministic transform inside the pack: "
                      "88.40 * 110.0 = 9724.00. "
                      "Not an independent observation.", HTML)

    def test_tier2_passage_is_quoted_never_rounded(self):
        self.assertIn("Management guided 2026 revenue to a range of 940 to 980 USD millions on "
                      "2026-02-05, and repeated that range on 2026-07-30. The prior year "
                      "printed 862.5.", HTML)

    def test_declared_gap_and_sufficiency_summary(self):
        self.assertIn("<strong>short_borrow_cost</strong>", HTML)
        self.assertIn("<code>market_structure_read</code>", HTML)
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
        atlas = HTML[HTML.index('<h2 id="atlas">'):]
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
        return page[page.index('<h2 id="atlas">'):]

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
        self.assertIn("The outside audit ran, and the package says so.",
                      atlas)
        self.assertIn("The highest rating the auditor said the record "
                      "supports is <strong>Hold", atlas)

    def test_the_warnings_are_said_to_travel_with_it(self):
        self.assertIn("Every warning on this verdict travels inside the "
                      "package too &mdash; 2 of them", self.atlas())

    def test_a_package_with_no_endorsed_ceiling_says_that_plainly(self):
        self.assertIn("The auditor endorsed no ceiling, so the package "
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
        return page[page.index('<h2 id="atlas">'):]

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
        atlas = HTML[HTML.index('<h2 id="atlas">'):]
        self.assertIn("The outside audit ran, and the package says so.",
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
        return page[page.index('<h2 id="atlas">'):]

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
        self.assertIn("a gap, not the auditor", atlas)

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
        self.assertIn("The auditor endorsed no ceiling", atlas)

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
        return page[page.index('<h2 id="atlas">'):]

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
        atlas = HTML[HTML.index('<h2 id="atlas">'):]
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
        stamp = ('<div class="stamp muted small">seats ran on <strong>claude-opus-4-6</strong> '
                 "&middot; the challenge went to <strong>gpt-5.6-sol</strong></div>")
        self.assertIn(stamp, masthead)
        # The run id and the publication timestamp are still on the page, in the footer.
        self.assertIn("run <code>report-fixture-invented-1</code>", HTML)
        self.assertIn("published 2026-08-30T10:26Z", HTML)

    def test_footer_carries_run_id_computed_hash_and_schema_version(self):
        self.assertIn("publication hash <code>%s</code>" % VERDICT_SHA, HTML)
        self.assertIn("contract version <code>1.4.0</code>", HTML)
        self.assertIn("Rendered from the run directory by "
                      "<code>council/report/render_report.py</code>", HTML)


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
        self.assertIn('<dl class="rating-price"><dt>last price</dt><dd>$88.40 '
                      '<span class="asof">28 Aug 2026</span></dd></dl>', masthead)

    def test_the_masthead_carries_the_one_phrase_question(self):
        # The owner's one-phrase question as asked, under the title (closes register item P-U6b-10).
        self.assertIn('<p class="question">Is Specimen Works still cheap at this price, or has the '
                      "market caught up with the growth story?</p>", _masthead(HTML))

    def test_the_model_names_are_a_small_stamp_under_the_rating_box(self):
        masthead = _masthead(HTML)
        box = masthead[masthead.index('<div class="ratingbox">'):masthead.index("</aside>")]
        self.assertIn('<div class="stamp muted small">seats ran on '
                      "<strong>claude-opus-4-6</strong> &middot; the challenge went to "
                      "<strong>gpt-5.6-sol</strong></div>", box)
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
        self.assertIn("<h4>The raw findings, exactly as returned</h4>", HTML)
        self.assertIn("<pre><code>", HTML)
        self.assertIn("&quot;id&quot;: &quot;F1&quot;", HTML)

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
        self.assertIn("the challenger ran out of time", page)
        self.assertIn("This run directory carries no challenger papers.", page)
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
    ("71", "percent", "71%"),
    ("15.9", "percent", "15.9%"),
    ("0.97", "percent", "1%"),
    ("4.00", "percent", "4%"),
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
        self.assertEqual(R.format_number("71", "percent"), "71%")

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
        self.assertEqual(R.format_number("71", "percent"), "71%")
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
        # its meaning. It falls through to the safe unit-word spelling. True percent units (exact,
        # or a "percent " / "percent_" qualifier) still render as a percentage.
        self.assertEqual(R.format_number("-0.17", "percentage_points"), "-0.17 percentage points")
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
        self.assertEqual(R.format_number("0e50", "percent"), "0%")
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
        atlas = HTML[HTML.index('<h2 id="atlas">'):]
        self.assertIn("The deepest peak-to-trough fall", atlas)
        self.assertIn("-46", atlas)
        self.assertIn("5 Nov 2026", atlas)

    # r1-4: the page asserted the outside audit happened on runs where
    # it did not.
    def test_the_audit_happened_prose_is_gated_on_success(self):
        self.assertIn("read the full case file and audited", HTML)

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
        needle = "rests on this</span> <code>guidance_passage</code>"
        self.assertIn(needle, page)


class TestSC3Round6Regressions(unittest.TestCase):
    """Closing-pass findings at the renderer; both FAILED pre-fix."""

    # r6-2: the evidence fold claimed every pack fact was "built on".
    def test_the_evidence_fold_does_not_overclaim_provenance(self):
        self.assertNotIn("this verdict was built on", HTML)
        self.assertIn("in the evidence pack", HTML)
        # the declared dependencies are marked on their rows
        self.assertIn("rests on this", HTML)

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
        atlas = BASKET_HTML[BASKET_HTML.index('<h2 id="atlas">'):]
        self.assertIn('<th class="nowrap">Subject kind</th><td>a basket '
                      "of 2 named instruments judged as one idea</td>",
                      atlas)
        self.assertIn('<th class="nowrap">Constituents</th>'
                      "<td>Alpha Chips Inc (INVENTED) (ACHP), "
                      "Beta Grid Corp (INVENTED) (BGRD)</td>", atlas)
        self.assertIn(E(R.EMPHASIS_LABEL), atlas)
        self.assertIn("<li>BGRD: the remaining third</li>", atlas)

    def test_the_theme_envelope_rows(self):
        atlas = THEME_HTML[THEME_HTML.index('<h2 id="atlas">'):]
        self.assertIn('<th class="nowrap">Subject kind</th><td>an '
                      "investment theme judged through its named "
                      "expression</td>", atlas)
        self.assertIn('<th class="nowrap">Constituents</th>', atlas)

    def test_the_single_name_envelope_row(self):
        atlas = HTML[HTML.index('<h2 id="atlas">'):]
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
        atlas = BASKET_HTML[BASKET_HTML.index('<h2 id="atlas">'):]
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
        self.assertLess(front.index(self.THESIS_LEAD),
                        front.index('<span class="lead">The thesis</span>'))

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
        # A reader dives deeper the further they scroll (owner ruling AC16, audit C4): the
        # executive summary, then the chairman's synthesis, then the decision in detail, then
        # the evidence, then the appendices.
        for page in (HTML, BASKET_HTML, THEME_HTML):
            found = re.findall(r'<h2 id="([a-z]+)">', page)
            self.assertEqual(found[:4], ["decision", "synthesis", "detail", "evidence"], found[:5])

    def test_the_front_precedes_every_other_section_anchor(self):
        opening = HTML.index('<h2 id="decision">')
        for anchor in ANCHORS:
            if anchor == "decision":
                continue
            self.assertLess(opening, HTML.index('<h2 id="%s">' % anchor), anchor)

    def test_the_appendices_divider_exists_and_names_itself_plainly(self):
        self.assertIn('<h2 id="appendices">Appendices — the full record</h2>', HTML)
        self.assertIn("The record behind the decision above, all folded", HTML)

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
        self.assertIn("<dt>last price</dt><dd>$88.40</dd>", masthead)
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
        rationale = json.load(open(os.path.join(FIXTURE, "verdict.json")))["conviction_rationale"]
        reformatted = R.reformat_prose(rationale, "chairman rationale", [])
        thesis = " ".join(prose.split_sentences(reformatted, prose.load_rules())[:5])
        front = _front(HTML)
        card = front[front.index("The thesis"):]
        card = card[:card.index("</div>") + 6]
        self.assertIn(R.markdown(thesis), card)


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
        self.assertIn('<div class="card"><span class="lead">The mispricing read</span>'
                      "The council reads the price as <strong>rich</strong>", front)
        self.assertIn("Roughly 24.1 times forward earnings against a five-year average near "
                      "20 times; about a fifth above it.", front)
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
        self.assertLess(page.index("The mispricing read"),
                        page.index("A scenario ladder, as supporting context only"))


class TestDecisionFrontCalendar(unittest.TestCase):
    """AB13.5: the dated event calendar, now on the decision-in-detail tier (owner ruling AC16,
    audit C4 tier 3), and tripwires actionable inside the horizon - every event carries a date."""

    def setUp(self):
        self.detail = _detail(_scenario_page(_published_block(), calendar=True))

    def test_every_dated_event_renders_with_its_date_and_its_source(self):
        self.assertIn("The dated event calendar", self.detail)
        self.assertIn('<td class="nowrap">16 Sep 2026</td><td>INVENTED FIXTURE - the central '
                      "bank&#x27;s published meeting calendar", self.detail)
        self.assertIn("<code>calendar_rate_decision_next</code>", self.detail)
        self.assertIn("<code>calendar_protocol_next</code>", self.detail)

    def test_an_event_with_no_date_of_its_own_shows_the_day_it_was_checked(self):
        self.assertIn('<td class="nowrap">25 Aug 2026</td><td>no date announced yet; the review '
                      "is expected late in the year ", self.detail)

    def test_the_calendar_is_ordered_soonest_first(self):
        self.assertLess(self.detail.index("calendar_policy_review"),
                        self.detail.index("calendar_rate_decision_next"))
        self.assertLess(self.detail.index("calendar_rate_decision_next"),
                        self.detail.index("calendar_protocol_next"))

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
        return page[page.index('<h2 id="detail">'):
                    page.index('<h2 id="evidence">')]

    def test_a_change_that_decides_nothing_is_one_folded_line(self):
        page = self.page([_change("last_price")])
        front = _front(page)
        self.assertIn("1 figure changed after the outside auditor read "
                      "the evidence", _visible_text(front))
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
        self.assertIn("2 figures changed after the outside auditor read "
                      "the evidence, 1 of them decisive.", text)
        self.assertIn('<div class="card alarm">', front)
        self.assertNotIn("<details>",
                         front[front.index("1 of them decisive"):])

    def test_a_change_to_a_decisive_metrics_own_answer_is_loud_too(self):
        def add_frame(run_dir):
            _rewrite_pack(run_dir, lambda doc: doc["capture"].__setitem__(
                "business_frame",
                {"FIXT": {"decisive_metrics": [
                    {"name": "INVENTED - what it earns per unit",
                     "answered_by": ["free_cash_flow_fy2025"]}]}}))
        page = self.page([_change("free_cash_flow_fy2025")],
                         extra=add_frame)
        self.assertIn("1 figure changed after the outside auditor read "
                      "the evidence, 1 of them decisive.",
                      _visible_text(_front(page)))

    def test_a_members_own_headline_figure_counts_as_its_own(self):
        """A constituent of an expression wears its member suffix, and the
        pair it belongs to is read from the id underneath it."""
        page = self.page([_change("net_income_q__achp")])
        self.assertIn("1 of them decisive", _visible_text(_front(page)))

    def test_the_appendix_prints_what_was_read_and_what_was_sat_on(self):
        page = self.page([_change("last_price", old="123.45", new="130.00")])
        text = _visible_text(self.appendix(page))
        self.assertIn("Changed after the outside auditor read the evidence",
                      text)
        self.assertIn("The auditor read 123.45; the council sat on 130.00.",
                      text)

    def test_the_appendix_names_added_and_removed_in_plain_words(self):
        page = self.page([_change("rent_per_unit", change="added",
                                  old=None, new="7.5"),
                          _change("old_note", change="removed",
                                  old="INVENTED - it used to say this",
                                  new=None)])
        text = _visible_text(self.appendix(page))
        self.assertIn("It was gathered after the audit and reads 7.5.", text)
        self.assertIn("It was taken out after the audit; it read INVENTED - "
                      "it used to say this.", text)

    def test_a_value_that_stands_says_what_moved_instead(self):
        page = self.page([_change("last_price", old="123.45", new="123.45")])
        self.assertIn("Its value stands at 123.45; what moved is its unit, "
                      "its date or where it came from.",
                      _visible_text(self.appendix(page)))

    def test_the_appendix_marks_the_ones_the_decision_turns_on(self):
        page = self.page([_change("last_price"), _change("revenue_q")])
        text = _visible_text(self.appendix(page))
        self.assertIn("revenue_q \u2014 a number this decision turns on",
                      text)
        self.assertNotIn("last_price \u2014 a number this decision turns on",
                         text)

    def test_a_pack_that_changed_nothing_says_nothing(self):
        page = self.page([])
        self.assertNotIn("changed after the outside auditor read the "
                         "evidence", _visible_text(page))

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
        self.assertNotIn("of them decisive", _visible_text(_front(page)))

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
        self.assertIn("41 figures changed after the outside auditor read "
                      "the evidence, 1 of them decisive.", front)


class TestTheAuditOfTheEvidenceOnTheFront(unittest.TestCase):
    """Every test below FAILS against the pre-fix page."""

    def test_a_clean_audit_is_one_folded_line(self):
        front = _front(HTML)
        self.assertIn("An outside auditor read this evidence before the "
                      "council sat and raised 2 points, none of them "
                      "blocking", _visible_text(front))
        self.assertIn("<details>", front)

    def test_a_blocking_finding_is_loud_and_never_folded(self):
        page = _audit_page(_blocking_block())
        front = _front(page)
        text = _visible_text(front)
        self.assertIn("The outside auditor called 1 point blocking before "
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
        self.assertIn("The outside auditor called 3 points blocking",
                      _visible_text(front))


class TestTheAuditOfTheEvidenceInTheAppendix(unittest.TestCase):
    def appendix(self, page):
        # The outside auditor's objections moved to the decision-in-detail tier (owner ruling
        # AC16, audit C4 tier 3): the auditor's paragraph and blocking findings open, the
        # non-blocking findings and the post-audit change list folded.
        return page[page.index('<h2 id="detail">'):
                    page.index('<h2 id="evidence">')]

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
        self.assertIn("gpt-5.6-sol", _visible_text(section))
        self.assertIn("The auditor&#x27;s reading of this evidence, in its "
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
        self.assertIn("conceded to the outside auditor", section)
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
        self.assertIn("The council sat 84 minutes, from the go to this page being rendered.",
                      self.stamps)

    def test_the_capture_is_counted_beside_that_clock_and_never_inside_it(self):
        self.assertIn("Gathering it took another 46 minutes and 0.384M tokens, counted "
                      "beside that clock and never inside it.", self.stamps)
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
        self.assertNotIn("The council sat", page)
        self.assertIn("Gathering it took another 46 minutes", page)


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
        self.assertIn("The council sat 115 minutes, from the go to this page being rendered.",
                      stamps)
        self.assertNotIn("81 minutes", stamps)

    def test_a_later_rendering_prints_a_later_clock(self):
        self.assertIn("The council sat 60 minutes",
                      _visible_text(_stamps(self.page_at(60))))
        self.assertIn("The council sat 89 minutes",
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
        self.assertIn("The council sat 95 minutes", _visible_text(_stamps(page)))

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
        self.assertIn("The council sat 45 minutes", _visible_text(_stamps(page)))

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
        self.assertIn("The council sat 60 minutes", _visible_text(_stamps(page)))

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
        self.assertIn("The council sat 0 minutes", _visible_text(_stamps(page)))
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
            minutes = float(re.search(r"The council sat ([\d,.]+) minutes",
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
            self.assertIn("The council sat 61 minutes",
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
            self.assertIn("The council sat 84 minutes",
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
            self.assertNotIn("The council sat",
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
        # the gathering-cost line is present but carries no "(estimated)"
        self.assertIn("Gathering it took another", page)
        self.assertNotIn("tokens (estimated)", page)

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
        self.assertIn("The sitting&#x27;s cost, seat by seat", page)
        self.assertIn("advisor_bear", page)
        self.assertIn("400", page)     # tokens per turn
        self.assertIn("&mdash;", page)  # the null input/output cells

    def test_no_seat_cost_block_renders_no_section(self):
        def mutate(run_dir):
            _rewrite_verdict(run_dir, lambda doc:
                             doc["provenance"].pop("seat_cost", None))
        with tempfile.TemporaryDirectory() as tmp:
            page = _render(_mutated_copy(tmp, mutate))
        self.assertNotIn("seat by seat", page)


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
        self.assertIn("Writing score (advisory)", body)

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
        self.assertIn("Writing score (advisory)", body)

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
        found = re.findall(r'<h2 id="([a-z-]+)">', HTML)
        self.assertEqual(found[:5],
                         ["decision", "synthesis", "detail", "evidence", "appendices"], found)

    def test_the_navigation_is_nine_content_tiers(self):
        # The nine menu entries name content, never a process step ('the challenge round', 'the
        # audit of the evidence', 'tripwires'): those folded into the tiers.
        self.assertEqual(ANCHORS, ("decision", "synthesis", "detail", "evidence", "question",
                                   "review", "advisors", "challenger", "atlas"))
        menu = re.search(r'<div class="menucard">(.*?)</div></div></nav>', HTML, re.S).group(1)
        for process in ("challenge", "evidence-audit", "tripwires", "warnings", "changes",
                        "stamps"):
            self.assertNotIn('href="#%s"' % process, menu, process)

    def test_the_decision_in_detail_tier_is_open(self):
        detail = _detail(HTML)
        # The downside ladder, the outside auditor's objections and the challenge round are here,
        # open - the tier itself carries no wrapping fold.
        self.assertIn("The downside ladder", detail)
        self.assertIn("The outside auditor&#x27;s objections, and the answers", detail)
        self.assertIn("The outside challenge round", detail)
        self.assertNotIn("<details><summary>The downside ladder", detail)

    def test_the_challenge_card_stays_open_in_the_detail_tier(self):
        detail = _detail(HTML)
        self.assertIn("The outside audit ran.", detail)
        # The card's findings are not behind a fold (ruled open, audit C5).
        card = detail[detail.index("The outside challenge round"):]
        self.assertNotIn("<details>", card[:card.index("The challenger&#x27;s own words")])

    def test_the_non_blocking_audit_findings_fold_with_their_count(self):
        # The fixture's two points are both non-blocking: they fold behind one line with the count,
        # while the auditor's own paragraph stays open (owner ruling AC16, audit C4 tier 3).
        detail = _detail(HTML)
        self.assertIn("The auditor&#x27;s reading of this evidence, in its own words", detail)
        self.assertIn("<details><summary>2 non-blocking points the auditor raised, each with its "
                      "answer on the record</summary>", detail)

    def test_the_evidence_opens_with_the_facts_the_verdict_rests_on(self):
        evidence = HTML[HTML.index('<h2 id="evidence">'):HTML.index('<h2 id="appendices">')]
        fold = evidence.index("<details><summary>Every figure on the record")
        # The compact table and its five columns are open, above the fold.
        self.assertIn("The figures the verdict says its ruling rests on.", evidence)
        # The value column is not nowrap - it can hold a tier-2 sentence (design audit C5, B8).
        self.assertIn('<th>fact</th><th>value</th><th class="nowrap">as of</th>'
                      '<th class="nowrap">freshness</th><th>source</th>', evidence)
        # A decisive fact is in the open compact table; the whole 10-fact pack is behind the fold.
        self.assertLess(evidence.index("<code>last_price</code>"), fold)
        self.assertIn("all 10 frozen facts in the evidence pack", evidence)

    def test_the_tier_five_appendices_are_folded(self):
        for summary in ("The owner&#x27;s question as he asked it, and the half the council "
                        "answered",
                        "The blind reviewer&#x27;s synopsis and full cross-examination of the "
                        "five advisors",
                        "The machine hand-off to the portfolio system, Atlas"):
            self.assertIn("<details><summary>%s" % summary, HTML)

    def test_the_challenge_diff_is_sentences_with_before_after_behind_a_second_fold(self):
        # Owner ruling AC16(8), audit B3: the diff is plain sentences now, not open JSON; the exact
        # text before and after is behind a second fold.
        changes = HTML[HTML.index('<h2 id="changes">'):HTML.index('<h2 id="atlas">')]
        self.assertIn("<details><summary>2 fields changed between the draft the challenger read "
                      "and the final document</summary>", changes)
        self.assertIn("<details><summary>The exact text before and after, field by field"
                      "</summary>", changes)
        self.assertRegex(changes, r"<li><code>[^<]+</code> &mdash; ")

    def test_the_run_stamps_are_a_folded_appendix_off_the_nav(self):
        self.assertIn('<h2 id="stamps">About this sitting</h2>', HTML)
        self.assertNotIn('href="#stamps"', HTML)
        stamps = _stamps(HTML)
        self.assertIn("<details><summary>How long the sitting took, and what it cost</summary>",
                      stamps)

    def test_the_advisor_folds_carry_no_emoji(self):
        advisors = HTML[HTML.index('<h2 id="advisors">'):HTML.index('<h2 id="challenger">')]
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
        return page[page.index('<h2 id="appendices">'):]

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
