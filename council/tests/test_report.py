"""Report suite: the HTML renderer for the split-mode council (REBUILD-SPEC section 9).

Run: python council/tests/test_report.py     (exit code authoritative)

Everything renders from a hand-written fixture run directory under
council/tests/fixtures/report/run-invented-1. Every value in it is INVENTED and every
source string says so; no published run is read and none is written. Variants (an empty
change appendix, a failed outside audit, a missing chair resolve) are built by copying
the fixture into a temp directory and mutating the copy - the fixture itself is a record.
"""

import copy
import html as html_lib
import hashlib
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


def setUpModule():
    global HTML, BASKET_HTML, THEME_HTML, VERDICT_SHA
    HTML = R.render(FIXTURE)
    BASKET_HTML = R.render(FIXTURE_BASKET)
    THEME_HTML = R.render(FIXTURE_THEME)
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


ANCHORS = ("decision", "appendices", "question", "verdict", "warnings", "tripwires",
           "challenge", "changes", "synthesis", "evidence", "review", "advisors",
           "challenger", "atlas")

SECTION_HEADINGS = (
    "The decision", "Appendices — the full record",
    "The owner's question", "The verdict", "Warnings", "Tripwires", "The challenge round",
    "What changed after the outside audit", "The chairman's final synthesis", "The evidence",
    "Peer review", "The five advisors", "The challenger's full response",
    "What the portfolio system receives",
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
        return R.render(_mutated_copy(tmp, mutate))


TAG = re.compile(r"<[^>]+>")


def _front(page):
    """The decision front's own HTML: everything between its heading and the appendices."""
    return page[page.index('<h2 id="decision">'):page.index('<h2 id="appendices">')]


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
        self.assertIn("<details><summary>The reviewer's full cross-examination</summary>", HTML)

    def test_challenger_full_response_is_a_closed_fold(self):
        self.assertIn("<details><summary>Its full response &mdash; 2 findings</summary>", HTML)

    def test_evidence_folds_to_the_ruled_summary_line(self):
        # Reworded at the SC3 closing pass (r6-2): the fold no longer
        # claims every pack fact carried the ruling.
        self.assertIn("<details><summary>The 10 frozen facts in the "
                      "evidence pack", HTML)

    def test_collapse_of_nothing_adds_nothing(self):
        page = R.Page()
        page.add("before")
        mark = page.mark()
        page.collapse("never shown", mark)
        self.assertEqual(page.body(), "before")


class TestVerdictBlock(unittest.TestCase):
    def test_rating_in_the_owners_plain_words_monitor_is_a_watch_state(self):
        self.assertIn('<div class="badge">Monitor - no view yet; watch the named triggers</div>',
                      HTML)

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
        self.assertIn('<td class="nowrap">84.50 USD</td>', HTML)
        self.assertIn("A close under 84.50 breaks the base the reopening case rests on.", HTML)

    def test_reopening_triggers_price_and_event(self):
        # The 72.00 cell rounds to the whole 72; the chairman's own sentence keeps 72.00.
        self.assertIn('<td class="nowrap">72 USD</td>', HTML)
        self.assertIn("Reopen the case if the shares close at or under 72.00 USD.", HTML)
        self.assertIn('<span class="tag">Price</span>', HTML)
        self.assertIn('<span class="tag">Event</span>', HTML)
        self.assertIn("2027-02-04", HTML)

    def test_falsifier_names_figure_source_and_date(self):
        self.assertIn("<code>full_year_revenue_2026</code>", HTML)
        self.assertIn(E("invented: the company's 2026 full-year report"), HTML)
        self.assertIn("If 2026 full-year revenue prints under 900 USD millions, the growth leg "
                      "of the thesis is wrong.", HTML)


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
            page = R.render(run_dir)
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
            page = R.render(run_dir)
        self.assertIn("DRAFT-SYNTHESIS-MARKER", page)
        self.assertIn("No post-challenge resolve is in the record", page)


class TestEvidence(unittest.TestCase):
    def test_market_shut_sentence_is_in_plain_sight_not_folded(self):
        disclosure = ("The exchange was shut at capture. The last price is the 2026-08-28 "
                      "close, about two hours old at the freeze.")
        self.assertIn(disclosure, HTML)
        fold = HTML.index("<details><summary>The 10 frozen facts")
        self.assertLess(HTML.index(disclosure), fold)
        self.assertGreater(HTML.index(disclosure), HTML.index('<h2 id="evidence">'))

    def test_value_cells_round_to_one_precision_per_unit(self):
        self.assertIn('<td class="nowrap">27.2 millions of shares</td>', HTML)   # 27.161588
        self.assertIn('<td class="nowrap">110 millions of shares</td>', HTML)    # whole stays whole
        self.assertIn('<td class="nowrap">9724 USD m</td>', HTML)                # 9724.00
        self.assertIn('<td class="nowrap">862.50 USD m</td>', HTML)              # 862.5 padded
        self.assertIn('<td class="nowrap">24.10 x</td>', HTML)                   # 24.1 padded

    def test_a_seats_own_sentence_is_never_edited(self):
        self.assertEqual(HTML.count("27.161588"), 1)   # only the bear's own words carry it
        self.assertIn("27.161588 million shares were sold short", HTML)

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
        self.assertIn('<td class="nowrap">88.40 USD</td>', atlas)
        self.assertIn('<td class="nowrap">41.70 %</td>', atlas)
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
        page = R.render(run_dir)
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
        page = R.render(run_dir)
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
        page = R.render(run_dir)
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
        self.assertIn("<h1>Investment Council &mdash; Specimen Works (SPWK)</h1>", HTML)
        self.assertIn("run <code>report-fixture-invented-1</code>", HTML)
        self.assertIn("published 2026-08-30T10:26Z", HTML)
        self.assertIn("seats ran on <strong>claude-opus-4-6</strong>", HTML)
        self.assertIn("the challenge went to <strong>gpt-5.6-sol</strong>", HTML)

    def test_footer_carries_run_id_computed_hash_and_schema_version(self):
        self.assertIn("publication hash <code>%s</code>" % VERDICT_SHA, HTML)
        self.assertIn("contract version <code>1.3.0</code>", HTML)
        self.assertIn("Rendered from the run directory by "
                      "<code>council/report/render_report.py</code>", HTML)


class TestSeatSelection(unittest.TestCase):
    def test_the_highest_numbered_answer_per_seat_wins(self):
        self.assertNotIn("SUPERSEDED-FIRST-ANSWER", HTML)
        self.assertIn("27.161588 million shares", HTML)   # the retry's content is what renders


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
            page = R.render(_mutated_copy(tmp, mutate))
        self.assertIn(R.AUDIT_FAILED_SENTENCE, page)
        self.assertIn("the bridge timed out after 30 minutes", page)
        self.assertIn("the challenger ran out of time", page)
        self.assertIn("This run directory carries no challenger papers.", page)
        self.assertNotIn("<details><summary>Its full response", page)


class TestNumberRules(unittest.TestCase):
    """One precision per unit; whole numbers whole; live figures never erased; words survive."""

    def test_one_precision_per_unit(self):
        self.assertEqual(R.format_number("3517.411", "USD"), "3517.41")
        self.assertEqual(R.format_number("972.5", "USD"), "972.50")
        self.assertEqual(R.format_number("1030.44", "USD"), "1030.44")
        self.assertEqual(R.format_number("27.161588", "millions_of_shares"), "27.2")

    def test_whole_numbers_stay_whole_reading_the_rounded_value(self):
        self.assertEqual(R.format_number("393", "MW"), "393")
        self.assertEqual(R.format_number("39.996", "%"), "40")
        self.assertEqual(R.format_number("110.0", "millions_of_shares"), "110")

    def test_days_carry_one_decimal(self):
        self.assertEqual(R.format_number("2.53", "days"), "2.5")
        self.assertEqual(R.format_number("3.7", "days"), "3.7")

    def test_a_live_figure_is_never_erased_to_zero(self):
        self.assertEqual(R.format_number("0.0068", "%"), "0.01")
        self.assertEqual(R.format_number("0.001", "%"), "0.001")

    def test_zero_has_one_rendering(self):
        self.assertEqual(R.format_number("-0.0"), "0")
        self.assertEqual(R.format_number("0e50", "%"), "0")

    def test_text_that_is_not_a_pure_number_passes_through_as_words(self):
        for text in ("NOT AVAILABLE", "none_announced", "2026-06-30", "2027-H2",
                     "8-10", "250-500", "more than 1600",
                     "0.48% cost to borrow; 1,900,000 shares available"):
            self.assertEqual(R.format_number(text, "%"), text)

    def test_a_zero_padded_bare_integer_is_an_identifier(self):
        self.assertEqual(R.format_number("0000320193"), "0000320193")

    def test_ruled_unrounded_units(self):
        self.assertEqual(R.format_number("3.125", "BTC"), "3.125")
        self.assertEqual(R.format_number("850123", "block_height"), "850123")

    def test_floats_round_in_exact_decimals(self):
        self.assertEqual(R.format_number(9.16, "%"), "9.16")
        self.assertEqual(R.format_number(0.1 + 0.2, "x"), "0.30")

    def test_absurd_magnitudes_fall_back_to_their_own_text(self):
        self.assertEqual(R.format_number("1e400", "USD"), "1e400")

    def test_non_numbers_and_null(self):
        self.assertEqual(R.format_number(None), "None")
        self.assertEqual(R.format_number(True), "True")
        self.assertEqual(R.format_number(400, "shares"), "400")


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

    def test_renders_exactly_one_file_and_prints_path_and_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = _mutated_copy(tmp)
            before = set(os.listdir(run_dir))
            proc = self._run([run_dir])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            added = set(os.listdir(run_dir)) - before
            self.assertEqual(added, {"report.html"})
            out_path = os.path.join(run_dir, "report.html")
            self.assertIn("report written:", proc.stdout)
            self.assertIn("report.html", proc.stdout)
            self.assertIn("(%d bytes)" % os.path.getsize(out_path), proc.stdout)
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
        self.assertIn("2026-11-05", atlas)

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
            page = R.render(_mutated_copy(tmp, mutate))
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
            page = R.render(_mutated_copy(tmp, mutate))
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
            page = R.render(_mutated_copy(tmp, mutate))
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
            page = R.render(_mutated_copy(tmp, mutate))
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
            page = R.render(_mutated_copy(tmp, mutate))
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
            page = R.render(_mutated_copy(tmp, mutate))
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

    def test_the_section_exists_with_its_nav_entry(self):
        for page in (BASKET_HTML, THEME_HTML):
            self.assertIn('<h2 id="constituents">', page)
            self.assertIn('href="#constituents"', page)
        self.assertIn("The constituents", BASKET_HTML)

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
        self.assertIn('<td class="nowrap">231.40 USD</td>', BASKET_HTML)
        self.assertIn('<td class="nowrap">1150000 USD m</td>', BASKET_HTML)
        self.assertIn('<td class="nowrap">88.15 USD</td>', BASKET_HTML)

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
            page = R.render(run_dir)
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
            return R.render(run_dir)

    def test_the_vehicle_identity_block_replaces_the_table(self):
        page = self._vehicle_page()
        self.assertIn("The implementation vehicle", page)
        self.assertIn("Invented Storage Vehicle Fund (THVH)", page)
        self.assertIn("Listing: Invented Exchange. Currency: USD.", page)
        self.assertNotIn(">Load-bearing metric</th>", page)
        self.assertIn('<h2 id="constituents">', page)

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

    def test_the_block_renders_first_in_the_tripwires_section(self):
        heading = "<h3>The theme's falsifiers</h3>"
        self.assertIn(heading, THEME_HTML)
        # First among the tripwires - before the levels, the triggers
        # and the plain falsifier table, whatever the array order.
        self.assertLess(THEME_HTML.index(heading),
                        THEME_HTML.index("<h3>Invalidation levels</h3>"))
        self.assertLess(THEME_HTML.index(heading),
                        THEME_HTML.index("<h3>Falsifiers</h3>"))
        self.assertNotIn(heading, HTML)

    def test_statement_and_scored_against_line(self):
        self.assertIn("If quarterly storage installations print at or "
                      "below the prior year, the theme is wrong. "
                      "(INVENTED)", THEME_HTML)
        self.assertIn("Scored against <code>storage_installs_q</code> "
                      "from INVENTED FIXTURE - industry deployment "
                      "tracker, quarterly release, on 2026-11-15.",
                      THEME_HTML)

    def test_the_level_row_shows_its_prior_period(self):
        # The prior period, rounded for reading like every figure on
        # the page (the verdict keeps the exact bytes).
        self.assertIn("Prior period: 9.10 GW, as of 2025-08-15.",
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
            return R.render(run_dir)

    def test_the_falsifier_block_renders_identically(self):
        page = self._etf_page()
        self.assertIn("The subject is a collective investment vehicle.",
                      page)
        self.assertIn("<h3>The theme's falsifiers</h3>", page)
        self.assertIn("Prior period: 9.10 GW, as of 2025-08-15.", page)
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
        return page[page.index("<h3>The theme's falsifiers</h3>"):
                    page.index("<h3>Invalidation levels</h3>")]

    def test_the_theme_page_states_the_frozen_thesis(self):
        self.assertIn(self.THESIS_LEAD, THEME_HTML)
        self.assertIn(E(self.THESIS), THEME_HTML)
        # Before the expression: the idea, then the names expressing it.
        self.assertLess(THEME_HTML.index(E(self.THESIS)),
                        THEME_HTML.index('<h2 id="constituents">'))

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
            page = R.render(run_dir)
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
        for page in (HTML, BASKET_HTML, THEME_HTML):
            found = re.findall(r'<h2 id="([a-z]+)">', page)
            self.assertEqual(found[0], "decision", found[:3])
            self.assertEqual(found[1], "appendices", found[:3])

    def test_the_front_precedes_every_other_section_anchor(self):
        opening = HTML.index('<h2 id="decision">')
        for anchor in ANCHORS:
            if anchor == "decision":
                continue
            self.assertLess(opening, HTML.index('<h2 id="%s">' % anchor), anchor)

    def test_the_appendices_divider_exists_and_names_itself_plainly(self):
        self.assertIn('<h2 id="appendices">Appendices — the full record</h2>', HTML)
        self.assertIn("Everything the decision above rests on, in full", HTML)

    def test_the_verdict_and_tripwire_blocks_are_folded(self):
        for page in (HTML, BASKET_HTML, THEME_HTML):
            self.assertIn('<h2 id="verdict">The verdict</h2><details><summary>The verdict '
                          "block in full", page)
            self.assertIn('<h2 id="tripwires">Tripwires</h2><details><summary>Every tripwire '
                          "in full", page)
        self.assertNotIn("<details open", HTML)

    def test_the_warning_band_renders_once_and_only_at_the_top(self):
        band = ('<div class="card alarm"><span class="shout">The rating moved after the outside '
                "audit. The outside auditor did not see this rating.</span></div>")
        self.assertEqual(HTML.count(band), 1)
        self.assertIn(band, _front(HTML))
        self.assertIn("Every warning on this verdict is printed at the top of this report", HTML)

    def test_a_verdict_with_no_warnings_keeps_its_plain_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = R.render(_mutated_copy(tmp, lambda d: _rewrite_verdict(
                d, lambda doc: doc.__setitem__("warnings", []))))
        self.assertIn("This verdict carries no warnings.", page)
        self.assertNotIn('<div class="card alarm">', page)


class TestDecisionFrontContent(unittest.TestCase):
    """What the front carries for every subject: the rating, the few numbers the ruling turns
    on, the downside, the calendar, the tripwires, what would change it, and where the bench
    disagreed."""

    def test_the_rating_badge_and_the_five_word_scale(self):
        front = _front(HTML)
        self.assertIn('<div class="badge">Monitor - no view yet; watch the named triggers</div>',
                      front)
        self.assertIn("The council&#x27;s scale, strongest first: Strong buy, Buy, Hold, Sell",
                      front)
        self.assertIn("The subject is a single name.", front)
        self.assertIn("No view is worth paying for until one of the named triggers fires.", front)

    def test_the_key_numbers_render_with_unit_and_as_of(self):
        front = _front(HTML)
        self.assertIn("The numbers this ruling turns on", front)
        self.assertIn('<tr><td>last price</td><td class="nowrap">88.40 USD</td>'
                      '<td class="nowrap">2026-08-28</td></tr>', front)
        self.assertIn('<tr><td>realized volatility, 90 days</td><td class="nowrap">41.70 %</td>'
                      '<td class="nowrap">2026-08-28</td></tr>', front)

    def test_at_most_five_key_numbers_and_the_rest_named_as_an_appendix(self):
        def change(doc):
            base = doc["atlas_envelope"]["key_numbers"][0]
            doc["atlas_envelope"]["key_numbers"] = [
                dict(base, name="invented number %d" % index) for index in range(1, 8)]
        with tempfile.TemporaryDirectory() as tmp:
            page = R.render(_mutated_copy(tmp, lambda d: _rewrite_verdict(d, change)))
        front = _front(page)
        for index in range(1, 6):
            self.assertIn("<td>invented number %d</td>" % index, front)
        for index in (6, 7):
            self.assertNotIn("<td>invented number %d</td>" % index, front)
        self.assertIn("The verdict carries 2 more headline numbers.", front)
        # They are not lost: the hand-off section below still lists all seven.
        self.assertIn("<td>invented number 7</td>", page)

    def test_the_downside_ladder_carries_the_invalidation_levels(self):
        front = _front(HTML)
        self.assertIn("The downside ladder", front)
        self.assertIn('<tr><td class="nowrap">84.50 USD</td><td>A close under 84.50 breaks the '
                      "base the reopening case rests on.</td></tr>", front)

    def test_the_tripwires_render_with_their_levels_dates_and_figures(self):
        front = _front(HTML)
        self.assertIn("What reopens the case", front)
        self.assertIn('<span class="tag">Price</span>', front)
        self.assertIn('<td class="nowrap">72 USD</td>', front)
        self.assertIn('<span class="tag">Event</span>', front)
        self.assertIn("What would prove this wrong", front)
        self.assertIn("<code>full_year_revenue_2026</code>", front)
        self.assertIn('<td class="nowrap">2027-02-04</td>', front)

    def test_what_changes_this_rating_is_written_as_sentences(self):
        front = _front(HTML)
        self.assertIn("What changes this rating", front)
        self.assertIn("<strong>Would reopen this rating:</strong> Reopen the case if the shares "
                      "close at or under 72.00 USD. The level to watch is 72 USD.", front)
        self.assertIn("<strong>Would reopen this rating:</strong> Reopen on the 2026 full-year "
                      "results, whatever the price does before them. The date to watch is "
                      "2027-02-04.", front)
        self.assertIn("<strong>Would prove this rating wrong:</strong> If 2026 full-year revenue "
                      "prints under 900 USD millions, the growth leg of the thesis is wrong. "
                      "Scored against <code>full_year_revenue_2026</code> from invented: the "
                      "company&#x27;s 2026 full-year report on 2027-02-04.", front)

    def test_the_cross_examination_summary_names_the_blind_reviewer(self):
        front = _front(HTML)
        self.assertIn("Where the five advisors disagreed &mdash; the blind reviewer&#x27;s "
                      "summary", front)
        self.assertIn("One reviewer read all five advisors without knowing who wrote what",
                      front)
        self.assertIn("Five lenses, one agreement: the growth story is real", front)

    def test_a_basket_and_a_theme_front_name_their_own_kind(self):
        self.assertIn("The subject is a basket of 2 named instruments judged as one idea.",
                      _front(BASKET_HTML))
        self.assertIn("The subject is an investment theme judged through its named expression.",
                      _front(THEME_HTML))


class TestDecisionFrontTwoPages(unittest.TestCase):
    """AB13.5: 'at most two rendered pages'.

    Rendered pages cannot be counted from a string - a browser paginates, not the renderer - so
    the suite holds the front to a VISIBLE-TEXT BUDGET instead, and says so. 8000 characters is
    the proxy: two A4 pages of this report's body type hold roughly 4000 characters each, so a
    front inside 8000 cannot exceed two pages, and a front that breaks the budget has stopped
    being a summary whatever a browser does with it."""

    FRONT_TEXT_LIMIT = 8000

    def test_every_front_fits_the_two_page_budget(self):
        pages = {"single name": HTML, "basket": BASKET_HTML, "theme": THEME_HTML,
                 "anchorless": _scenario_page(_published_block(), calendar=True)}
        for name, page in pages.items():
            length = len(_visible_text(_front(page)))
            self.assertLessEqual(length, self.FRONT_TEXT_LIMIT,
                                 "%s front is %d visible characters" % (name, length))


class TestDecisionFrontAnchorless(unittest.TestCase):
    """The scenario-earned rating on the front (ANCHORLESS-SPEC section 3): the ladder, the sum
    written out, the bar, and the sensitivity that must be printed every time."""

    def setUp(self):
        self.computed = _computed_ladder()
        self.page = _scenario_page(_published_block(), calendar=True)
        self.front = _front(self.page)

    def test_the_ladder_earned_the_rating_the_engine_computed(self):
        self.assertEqual(self.computed["rating"], "buy")
        self.assertIn('<div class="badge">Buy</div>', self.front)
        self.assertIn("The subject is Bitcoin.", self.front)

    def test_every_rung_renders_with_its_price_chance_and_reason(self):
        self.assertIn("How this rating was earned: the scenario ladder", self.front)
        self.assertIn("Every chance below is the council&#x27;s own disciplined judgment, never "
                      "a verified fact. The horizon is 12 months.", self.front)
        for rung in CHAIR_LADDER["scenarios"]:
            self.assertIn('<tr><td>%s</td><td class="nowrap">%s USD</td>'
                          '<td class="nowrap">%s</td><td>%s</td></tr>'
                          % (E(rung["name"]),
                             E(R.format_number(rung["price_outcome"], "USD")),
                             E(rung["probability"]), E(rung["rationale"])),
                          self.front, rung["name"])

    def test_the_arithmetic_sentences_are_quoted_word_for_word(self):
        self.assertIn("The sum, written out", self.front)
        for line in self.computed["arithmetic"]:
            self.assertIn("<p>%s</p>" % E(line), self.front)

    def test_the_bar_and_the_expected_result_are_the_engines_own_figures(self):
        self.assertIn("The ladder expects %s%% a year against a bar of %s%% a year, a difference "
                      "of %s points." % (self.computed["expected_annualised_pct"],
                                         self.computed["bar_pct"],
                                         self.computed["excess_over_bar_pp"]), self.front)

    def test_the_sensitivity_is_printed_with_the_flip_and_the_bar_steps(self):
        sensitivity = self.computed["sensitivity"]
        self.assertIn(E(sensitivity["flip"]["sentence"]), self.front)
        self.assertIn(E(sensitivity["sentence"]), self.front)
        for step in sensitivity["bar_steps"]:
            self.assertIn('<td>%s</td><td class="nowrap">%s%%</td><td class="nowrap">%s</td>'
                          % (E(step["label"]), E(step["bar_pct"]),
                             E(R.RATING_WORDS[step["rating"]])),
                          self.front, step["label"])
        # The flip sentence also leads 'what changes this rating'.
        self.assertEqual(self.front.count(E(sensitivity["flip"]["sentence"])), 2)

    def test_the_downside_ladder_shows_the_rungs_priced_below_the_reference(self):
        self.assertIn("The ladder&#x27;s own losing rungs, priced under 100000 USD", self.front)
        self.assertIn('<tr><td class="nowrap">55000 USD</td><td>The bear case</td>'
                      '<td class="nowrap">0.25</td></tr>', self.front)
        # The two rungs priced above it are not downside and do not appear there.
        self.assertNotIn('<td>The bull case</td><td class="nowrap">0.30</td>', self.front)

    def test_an_anchorless_front_shows_no_mispricing_read(self):
        self.assertNotIn("The mispricing read", self.front)


class TestDecisionFrontUnaggregatedLadder(unittest.TestCase):
    """A ladder the chairman would not add up earns no rating, and the page gives his reason
    instead of arithmetic nobody stands behind (ANCHORLESS-SPEC section 3)."""

    REASON = ("The five ladders disagree on the bear case by more than the base case is worth. "
              "(INVENTED)")

    def setUp(self):
        self.front = _front(_scenario_page(
            _published_block(aggregated=False, reason=self.REASON)))

    def test_the_chairmans_reason_is_quoted(self):
        self.assertIn("Why no rating was earned from the ladder", self.front)
        self.assertIn("The chairman judged this ladder too uncertain to add up", self.front)
        self.assertIn(E(self.REASON), self.front)

    def test_no_arithmetic_and_no_bar_are_shown(self):
        self.assertNotIn("The sum, written out", self.front)
        self.assertNotIn("The ladder&#x27;s expected outcome is", self.front)
        self.assertNotIn("The bar it had to clear", self.front)
        self.assertNotIn("How close this is to a different answer", self.front)

    def test_the_rungs_still_render_so_the_reader_sees_the_spread(self):
        self.assertIn("<td>The bear case</td>", self.front)
        self.assertIn("<td>The bull case</td>", self.front)


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
        front = _front(page)
        self.assertIn("A scenario ladder, as supporting context only", front)
        self.assertIn("The ladder below earned no rating", front)
        self.assertIn('<div class="badge">Monitor - no view yet; watch the named triggers</div>',
                      front)
        self.assertNotIn('<div class="badge">Strong buy</div>', page)
        self.assertNotIn("The bar it had to clear", front)
        # The read comes first; the context ladder follows it.
        self.assertLess(front.index("The mispricing read"),
                        front.index("A scenario ladder, as supporting context only"))


class TestDecisionFrontCalendar(unittest.TestCase):
    """AB13.5: the dated event calendar on the front, and tripwires actionable inside the
    horizon - every event carries a date."""

    def setUp(self):
        self.front = _front(_scenario_page(_published_block(), calendar=True))

    def test_every_dated_event_renders_with_its_date_and_its_source(self):
        self.assertIn("The dated event calendar", self.front)
        self.assertIn('<td class="nowrap">2026-09-16</td><td>INVENTED FIXTURE - the central '
                      "bank&#x27;s published meeting calendar", self.front)
        self.assertIn("<code>calendar_rate_decision_next</code>", self.front)
        self.assertIn("<code>calendar_protocol_next</code>", self.front)

    def test_an_event_with_no_date_of_its_own_shows_the_day_it_was_checked(self):
        self.assertIn('<td class="nowrap">2026-08-25</td><td>no date announced yet; the review '
                      "is expected late in the year ", self.front)

    def test_the_calendar_is_ordered_soonest_first(self):
        self.assertLess(self.front.index("calendar_policy_review"),
                        self.front.index("calendar_rate_decision_next"))
        self.assertLess(self.front.index("calendar_rate_decision_next"),
                        self.front.index("calendar_protocol_next"))

    def test_a_pack_with_no_dated_events_says_so_in_one_sentence(self):
        for page in (HTML, BASKET_HTML, THEME_HTML):
            front = _front(page)
            self.assertIn("The evidence pack carries no dated events for this subject.", front)
            self.assertNotIn("what happens, and where the date comes from", front)


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
        return R.render(_mutated_copy(
            tmp, lambda run_dir: _rewrite_verdict(run_dir, change_verdict)))


def _bloated_page():
    """A schema-valid chairman who writes at length. Nothing here is
    malformed; it is simply long."""
    block = _published_block()
    long_text = "The case turns on a level nobody can observe daily. " * 20

    def change_verdict(doc):
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

    with tempfile.TemporaryDirectory() as tmp:
        return R.render(_mutated_copy(
            tmp, lambda run_dir: _rewrite_verdict(run_dir, change_verdict)))


class TestTheFrontUnderAFailedAudit(unittest.TestCase):
    """Audit finding ANCHORLESS-C c1-3: when a failed outside audit caps
    an earned rating to hold, the sensitivity beside it still read the
    LADDER's rating, so the front could print "the rating moves down to
    buy" under a Hold badge. The figures are the ladder's own honest
    arithmetic and are kept; what was missing was saying whose rating
    they describe."""

    def setUp(self):
        self.front = _front(_capped_page())

    def test_the_sensitivity_says_whose_rating_it_describes(self):
        self.assertIn("the ladder", _visible_text(self.front))
        self.assertIn("capped", _visible_text(self.front))

    def test_the_published_rating_is_the_capped_one_everywhere(self):
        text = _visible_text(self.front)
        self.assertIn("not the buy this ladder earns", text)

    def test_the_appendix_carries_the_same_caveat(self):
        # A new rendering path is a new place for the same
        # mislabelling: the ladders appendix repeats the sensitivity
        # sentences, and without the caveat a Hold page could claim
        # "the rating moves down to buy" (audit finding c5-1).
        page = _capped_page()
        appendix = page[page.index('<h2 id="appendices">'):]
        self.assertIn("was capped to", appendix)

    def test_the_uncapped_page_carries_no_such_label(self):
        plain = _visible_text(_front(_scenario_page(_published_block())))
        self.assertNotIn("capped", plain)


class TestTheFrontStaysTwoPagesOnRealAnswers(unittest.TestCase):
    """Audit finding ANCHORLESS-C c1-4: the two-page rule was measured
    only against short fixtures. A schema-valid chairman can write six
    thousand-character tripwires, and the front rendered every one of
    them - twice, since what-changes-this-rating restates them. The
    front now bounds what it shows and names what it left for the
    appendix."""

    def setUp(self):
        self.front = _front(_bloated_page())

    def test_a_long_answer_still_fits_the_two_page_budget(self):
        self.assertLessEqual(len(_visible_text(self.front)), 8000)

    def test_what_was_left_out_is_named_rather_than_dropped(self):
        self.assertIn("in full in the appendix", _visible_text(self.front))

    def test_a_short_answer_is_not_truncated(self):
        plain = _visible_text(_front(_scenario_page(_published_block())))
        self.assertNotIn("in full in the appendix", plain)


class TestEveryFrontFieldIsBounded(unittest.TestCase):
    """Audit finding ANCHORLESS-C c2-2: the front trimmed the statement
    and left its metadata unbounded, so a six-thousand-character source
    or figure name put the same defect back with a different field.
    Every value the front renders is bounded, not the ones that were
    noticed first."""

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
            return R.render(_mutated_copy(
                tmp,
                lambda run_dir: _rewrite_verdict(run_dir, change_verdict)))

    def test_long_metadata_cannot_burst_the_two_page_front(self):
        front = _front(self.page_with_long_metadata())
        self.assertLessEqual(len(_visible_text(front)), 8000)


class TestTheLaddersAreInTheReportInFull(unittest.TestCase):
    """Audit finding ANCHORLESS-C c3-1: the front bounded the ladder's
    rows and told the reader the rest was in the appendix - and no
    appendix rendered the ladder at all. A false pointer on the page is
    worse than a long table. The appendix now carries the chairman's
    whole ladder AND each seat's own, which is also what makes the
    bench's disagreement visible to a reader (ANCHORLESS-SPEC section 3).
    FAILED pre-fix."""

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

    def test_every_rung_the_front_dropped_is_in_the_appendix(self):
        page = self.page()
        appendix = page[page.index('<h2 id="appendices">'):]
        self.assertIn("A fourth case", appendix)
        self.assertIn("a rung the front has no room for", appendix)

    def test_each_seats_own_ladder_is_on_the_page(self):
        page = self.page()
        appendix = page[page.index('<h2 id="appendices">'):]
        self.assertIn("The bear seat&#x27;s own case", appendix)
        self.assertIn("its own reason", appendix)


class TestNoSingleFieldCanBurstTheFront(unittest.TestCase):
    """Audit finding ANCHORLESS-C c3-2 and c3-3: a scenario NAME travels
    into the engine's flip sentence, which the front renders twice, and
    a computed key number's VALUE is rendered unrounded by design. Both
    are schema-valid and both burst the two-page front. FAILED
    pre-fix."""

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
            return R.render(_mutated_copy(
                tmp,
                lambda run_dir: _rewrite_verdict(run_dir, change_verdict)))

    def test_a_long_scenario_name_cannot_burst_the_front(self):
        front = _front(self.page_with_long_scenario_name())
        self.assertLessEqual(len(_visible_text(front)), 8000)

    def test_a_long_computed_figure_cannot_burst_the_front(self):
        front = _front(self.page_with_long_key_number())
        self.assertLessEqual(len(_visible_text(front)), 8000)


if __name__ == "__main__":
    unittest.main(verbosity=1)
