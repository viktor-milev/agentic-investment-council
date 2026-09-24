"""The sufficiency gate (REBUILD-SPEC section 5): refuse before any
seat is paid.

This is the stage that makes the AAPL failure structurally impossible.
The pack carries its own checklist of what the question needs, the
floors data carries the ruled minimums per subject, and this check
verifies every item resolves to a present, in-rule fact BEFORE the
council convenes. A refusal costs the capture - never three hours of
seats - and its message is itself a product: what is missing, why the
question cannot be answered without it, and where each item likely
lives.

A theme is judged sittable here too (THEMES-BASKETS-SPEC, ruled
2026-08-31): without an investable expression, a measurable falsifier,
and the prior period beside a level, the refusal states the shopping
list - what would make the question sittable - at capture cost.

Sufficiency is judged PER ASSET CLASS (ANCHORLESS-SPEC section 4, owner
ruling AB13.4). An equity answers the four canonical tests. An asset
with no earnings - a coin, bullion, a commodity contract, or a fund
wrapping one of them - answers its own ruled anchor set instead, and a
missing anchor without a declared, reasoned gap refuses the sitting with
the same shopping list. Two of those anchors are the rating bar's own
inputs (the cash rate and five-year realized volatility): without them
no rating could ever be earned, and the sitting could only say hold -
which is the failure this check exists to prevent.

One floor can be answered by a STAND-IN rather than by the thing
itself (owner ruling AB19): where a filer publishes no capital-spending
line at all, the narrowest line that contains it may stand in its
place. That licence is not free. The capture must declare it, strike
the stand-in the same way in both years out of the SAME published line,
tag each figure a ceiling, and tag the free cash flow built on it a
floor - and this check refuses, at capture cost, when it does not.

Owner ruling AB20 moved that declaration out of PROSE and into the
capture's own shape: the figure carries a bound tag naming what it is
and which published line it was struck from, rather than this gate
hunting for particular words in a source sentence. Naming a line is a
CLAIM about the filer's statements, not a reading of them - so the one
condition a machine still cannot know is unchanged by the tag: whether
the line chosen really is the NARROWEST one published stays with the
sitting host, and nothing here checks it.

Owner ruling AC1 adds the last stage this check was missing: the pack
must SAY WHAT THE BUSINESS IS. The cold read of 2026-09-08 found that
the checklist below is written by the capturing session itself, so the
single number that decides a case can simply be left off it and nothing
notices - a miner converting to data-centre leasing cleared every floor
and every canonical test while contracted capacity and rent per unit
were demanded by nothing. A priced business now carries a business
frame, and each of its three to five decisive numbers resolves here to
a present, in-rule fact or to an honest gap, before a seat is paid.

CLI:
    python -m council.evidence.sufficiency <pack.json>
        [--floors <floors.json>] [--out <sufficiency-result.json>]
Exit codes: 0 pass, 3 refuse, 1 crash.
"""

import os
import sys
from datetime import datetime

from council.evidence import gate
from council.lib import canonical, subjects

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
_DEFAULT_FLOORS_PATH = os.path.join(_REPO_ROOT, "council", "floors",
                                    "floors.json")

CANONICAL_TEST_IDS = ("profit_growth", "free_cash_flow",
                      "rating_vs_history_or_peers", "yield_vs_risk_free")

# Why each canonical test exists and where its facts likely live, in
# plain words - used when a pack leaves a test out entirely, so the
# refusal can still point somewhere useful.
_CANONICAL_GUIDE = {
    "profit_growth": (
        "the first canonical test - is the business earning more than "
        "it did a year ago?",
        "the latest quarterly report read beside its prior-year "
        "comparative column"),
    "free_cash_flow": (
        "the second canonical test - how much cash the business "
        "generates after the spending it cannot avoid",
        "the cash-flow statement of the latest report: operating cash "
        "flow and capital spending, this year and last"),
    "rating_vs_history_or_peers": (
        "the third canonical test - is the price expensive or cheap "
        "against the subject's own history or its peers?",
        "the current rating from a dated market-data page, beside the "
        "subject's own multi-year record or a peer set"),
    "yield_vs_risk_free": (
        "the fourth canonical test - does the earnings or cash yield "
        "beat what a Treasury bill pays without risk?",
        "the pack's yield facts beside the risk-free rate (the Federal "
        "Reserve H.15 release, or the convention the question names)"),
}

# The ruled price-freshness ceiling for a named expression member's
# own last price (THEMES-BASKETS-SPEC section 4: the same 3-day
# ceiling the floors give the subject-level price).
_MEMBER_PRICE_CEILING_DAYS = 3

# Owner ruling AC1: a priced business states the three to five numbers
# that decide THIS question. Below three there is no set to argue over
# - one number is a thesis and two are a preference.
_DECISIVE_METRIC_MINIMUM = 3

# The fact class a capture declares when it carries no honest peer set
# (the same class the gate names). Owner ruling AC15 (P2): a declared
# peer gap lifts the requirement that the rating measure be computable
# for every peer.
_PEER_GAP_CLASS = "peer_"

# Owner rulings AC28 and AC30: a financial institution declares its
# capital a gap only where it holds no regulatory capital of its own -
# the two managers of clients' capital. A financial holding may do so
# only where no principal holding is itself a regulated institution,
# which the capture states by declaring this fact class absent by design.
_FI_CAPITAL_GAP_SUBTYPES = ("traditional_asset_manager",
                            "alternative_asset_manager")
_FI_HOLDING = "financial_holding"
_FI_HOLDING_CAPITAL_GAP_CLASS = "subsidiary_capital_ratio_"

# The plain words a rating-measure component fails on, keyed by the fault
# measure_component_fault returns. Owner ruling AC15 (P2); architect
# ruling 2026-09-20: the peer half of a ratio is brought to the same bar as
# the subject's - a tier-1 reading, fresh, and a number.
_FAULT_WORDS = {
    "absent": "is nowhere in the pack as a tier-1 reading",
    "stale": "is present but stale at capture",
    "nan": "is present but its value is not a number",
    "zero": "is zero, and a ratio cannot be divided by zero",
}

# The ruled sentence a pack without a business frame is refused with
# (UPGRADE-2 spec section U1.2). It is quoted, not paraphrased: the
# owner ruled the words.
FRAME_REFUSAL = ("the pack does not say what this business is or which "
                 "numbers decide the case")

_FRAME_LIKELY_SOURCE = (
    "the capturer's own reading, written BEFORE the filings are "
    "gathered (council/RUNBOOK.md section 1): the business description "
    "and segment note of the latest annual report, the last results "
    "call, and a peer screen of the closest listed comparables")

# Owner ruling AC2, spec section U2.3: every point the outside auditor
# raised is answered on the record before sufficiency passes, and a
# point that the capture session simply disagrees with is answered in at
# least twenty-five words. Twenty-five words is what it takes to say why
# a specific objection is wrong; "disagree" is not an answer, it is a
# refusal to give one. (Architect ruling, 2026-09-08: the bar is section
# U2.3's own DEFINITION of an overrule, so it governs every severity -
# the refusal clause named the blocking one as an instance of it.)
_OVERRULE_WORDS = 25

# Architect ruling, 2026-09-08, reading AC2: the auditor "audits the
# evidence before any seat is paid" and "every finding is resolved on
# record before sufficiency passes". A sitting that simply never made
# the call has neither a success nor a recorded failure to show, so the
# block is REQUIRED here - while the capture GATE stays tolerant of its
# absence, because the capture is written and checked before the call is
# made.
_UNCHECKED_LIKELY_SOURCE = (
    "the outside auditor itself: 'python -m council.bridge.codex_bridge "
    "evidence <capture.json> <out_dir>' makes the call, and "
    "'evidence-record' writes its answer - or the failure it returned - "
    "into the capture (council/RUNBOOK.md section 1a)")

_CHANGES_LIKELY_SOURCE = (
    "'python -m council.bridge.codex_bridge evidence-record', which "
    "holds both readings of the evidence and writes the list itself: "
    "record the audit AFTER the gathering it sent you to do, and every "
    "figure that moved is listed for you (council/RUNBOOK.md section 1a)")

_RESOLUTION_LIKELY_SOURCE = (
    "the capture session's own answer, written into "
    "evidence/challenge-resolution.json and recorded with 'python -m "
    "council.bridge.codex_bridge evidence-record': capture what the "
    "auditor asked for, declare an honest gap, or say in your own words "
    "why the auditor is wrong")

# Owner ruling AC15 (P8): a user correction that only NARROWS a claim
# needs no outside re-audit, but one that REBUILDS what the seats reason
# from is sent back to the auditor as a delta before the council may sit.
# The correction command classifies each and the delta re-audit clears
# it; this is where an un-re-audited rebuilding correction stops.
_REBUILDING_LIKELY_SOURCE = (
    "a delta re-audit: 'python -m council.bridge.codex_bridge evidence "
    "--delta <capture.json> <run>/evidence/challenge' shows the outside "
    "auditor only what the correction changed and the prior findings, "
    "then 'evidence-record' writes its answer back and clears the "
    "correction (council/RUNBOOK.md section 1a)")


def _arithmetic_mismatch(entry, fact):
    """Why this fact is not the arithmetic its anchor requires, or None
    where it is.

    Demanding that a divergence declare SOME arithmetic is not the same
    as demanding it declare THE arithmetic: a capture could ADD the two
    PBoC figures instead of subtracting them, and the gate would
    faithfully verify its own wrong sum (audit finding ANCHORLESS-C
    c1-2). So the anchor names the operation and the facts it must be
    built from, and both are checked."""
    derived = fact.get("derived")
    if not derived:
        return ("this figure IS built from other facts in this pack, so "
                "it declares that arithmetic and the gate recomputes it "
                "- stated on its own it is asserted rather than shown")
    wanted = entry.get("arithmetic") or {}
    operation = wanted.get("operation")
    if operation and derived.get("operation") != operation:
        return ("this figure is declared as a %r of its operands, but "
                "the anchor is the %r of them - the sum the gate "
                "recomputed is not the figure the anchor asks for"
                % (derived.get("operation"), operation))
    operands = wanted.get("operands")
    if operands:
        named = [item.get("fact_id")
                 for item in derived.get("operands") or ()]
        if named != list(operands):
            return ("this figure is declared over %s, but the anchor is "
                    "built from %s in that order - a difference between "
                    "the wrong two facts is arithmetic nobody asked for"
                    % (", ".join(repr(item) for item in named) or "no "
                       "named facts",
                       ", ".join(repr(item) for item in operands)))
    return None


def _text_key(text):
    """A declared gap's fact class, or a published line's name, as this
    gate matches it. Case and runs of whitespace carry no meaning in
    either, so a substitute is not waved through unchecked over a
    capital letter, and two years are not called two lines over a
    doubled space."""
    return " ".join(str(text).split()).casefold()


def _bound_tag(fact, kind):
    """This fact's bound tag where it declares the named kind, or None.
    A capture may tag any figure a bound; only the tags the ruled terms
    ask about are read here."""
    tag = (fact or {}).get("bound")
    if isinstance(tag, dict) and tag.get("kind") == kind:
        return tag
    return None


def _unsourced_leaf(fact_id, facts_by_id, seen=None):
    """The first figure in this fact's derivation chain that rests on a
    number written into the capture rather than on a reading taken off
    a filing - as (the fact that does it, the operand's own label) - or
    None where every branch bottoms out in an observed fact.

    An operand may legally be an inline constant, and for an ordinary
    derived figure that is fine. A stand-in for a line the filer never
    published is the case where it is not: checking only the immediate
    operands leaves the chain one step longer than the check, and the
    figures it bottoms out in can still be invented (audit finding
    r2-1). The chain may be as long as the filer's statements require;
    what it may not do is end in nothing."""
    if seen is None:
        seen = set()
    if fact_id in seen:
        return None
    seen.add(fact_id)
    derived = (facts_by_id.get(fact_id) or {}).get("derived")
    if not derived:
        return None
    for operand in derived.get("operands") or ():
        reference = operand.get("fact_id")
        if reference not in facts_by_id:
            return (fact_id, operand.get("label") or "one of its operands")
        deeper = _unsourced_leaf(reference, facts_by_id, seen)
        if deeper is not None:
            return deeper
    return None


def _substitute_failures(entry, facts_by_id, gap_kinds):
    """Why this DECLARED capital-spending substitute breaks the owner's
    terms - one refusal per broken term - or nothing where it holds.

    Owner ruling AB19: a filer that publishes no capital-spending line
    of its own no longer stops the council. The sitting stands the
    narrowest line that CONTAINS the item in its place. But a
    substitute the five advisors cannot see is worse than a refusal,
    so the ruling binds four conditions on it, and three of them are
    things this gate can know: the same line, named, struck the same
    way in BOTH years; the figure tagged a ceiling; and any free cash
    flow built on it tagged a floor.

    The fourth - that the line chosen is the NARROWEST one the filer
    publishes - is deliberately NOT checked. This gate cannot see the
    filer's statements, so a proxy for it would give false assurance,
    which is worse than no check at all; it stays the sitting host's
    judgement under council/RUNBOOK.md section 1. The tag added by
    ruling AB20 does not change that one inch: a fact naming the line
    it was read from is making a CLAIM about the filer's statements,
    and this gate can compare two such claims to each other but can
    never check either against a filing.

    None of it applies unless the capture DECLARES the substitution by
    naming the ruled gap class as absent by design. A sitting on a
    filer that reports capital spending normally never gets past the
    arming statement below. The one thing judged UNDECLARED is the
    mirror image: a figure tagged as standing in for an unpublished
    line while no gap row says so. AB19 requires the gap row alongside,
    and a stand-in nobody declared is the omission the ruling exists to
    stop - so it refuses rather than passing in silence."""
    terms = entry.get("substitute")
    if not terms:
        return []
    # ANY row declaring the class absent by design arms this, so that
    # appending a second row for the same class cannot switch the
    # ruling off (audit finding r1-5).
    wanted = _text_key(terms["armed_by_gap_class"])
    armed = False
    for fact_class, reasons in gap_kinds.items():
        if _text_key(fact_class) == wanted:
            armed = armed or "absent_by_design" in reasons

    failures = []

    def broken(what, because, where):
        failures.append((what, "%s (%s)" % (because, terms["why"]), where))

    ceiling_ids = (entry["id"], terms["paired_id"])

    if not armed:
        # A stand-in with no declaration behind it. The tag says this
        # figure was struck from a wider line because the filer
        # publishes none of its own - which is exactly the case AB19
        # says must be declared in the gaps, so that the weakened test
        # is named and reaches the seats. Passing it in silence would
        # let a capture claim the licence and skip every term of it.
        for fact_id in ceiling_ids:
            tag = _bound_tag(facts_by_id.get(fact_id), "ceiling")
            if tag is None or not tag.get("published_line"):
                continue
            broken("the undeclared stand-in on '%s'" % fact_id,
                   "this figure is tagged as a ceiling struck from the "
                   "published line %r, which says the filer publishes "
                   "no line of its own for it - but the capture "
                   "declares no such gap, so nothing tells the "
                   "advisors that the cash test they are reading is a "
                   "bound rather than a measurement"
                   % tag.get("published_line"),
                   "a gap row naming the fact class %r with "
                   "reason_kind 'absent_by_design', saying which test "
                   "is weakened and how"
                   % terms["armed_by_gap_class"])
        return failures

    # AB19 condition 2: struck identically in both years. A capture
    # that derives one year and observes the other, or strikes them by
    # different arithmetic, is manufacturing growth rather than
    # measuring it.
    if terms["paired_id"] not in facts_by_id:
        broken(terms["paired_id"],
               "this capture stands a wider published line in place of "
               "capital spending, but carries that stand-in for one "
               "year only - the change between the two years would be "
               "an artefact of the two figures being struck "
               "differently, not something the business did",
               "the same containing line in the comparative column of "
               "the same filing, struck by the same arithmetic")
    strikes = {}
    for fact_id in ceiling_ids:
        fact = facts_by_id.get(fact_id)
        if fact is None:
            continue
        if fact.get("derived"):
            strikes[fact_id] = fact["derived"]
            # The whole chain, not just the first step: a stand-in must
            # bottom out in readings taken off the filing (r1-1, r2-1).
            unsourced = _unsourced_leaf(fact_id, facts_by_id)
            if unsourced:
                holder, label = unsourced
                broken("the published line behind '%s'" % fact_id,
                       "this figure stands in for capital spending, so "
                       "it must be struck out of a line the filer "
                       "actually published. Followed down, '%s' rests "
                       "on %r - a number written into the capture, "
                       "resting on no captured reading at all. The "
                       "arithmetic would recompute exactly and still "
                       "show nothing" % (holder, label),
                       "capture the containing line itself as a fact, "
                       "dated and sourced, and strike the figure from "
                       "it")
        else:
            broken(fact_id,
                   "this figure stands in for a capital-spending line "
                   "the filer does not publish, so it must SHOW how it "
                   "was struck out of the containing line - stated on "
                   "its own it is asserted, and nothing here proves "
                   "both years were struck the same way",
                   "declare the arithmetic - the operation and the "
                   "containing-line facts it runs over - so the gate "
                   "recomputes it")
    if len(strikes) == len(ceiling_ids):
        this_year, last_year = (strikes[fact_id] for fact_id in ceiling_ids)
        here = len(this_year.get("operands") or ())
        there = len(last_year.get("operands") or ())
        if this_year.get("operation") != last_year.get("operation"):
            broken("the two capital-spending figures, struck two ways",
                   "'%s' is struck by a %r and '%s' by a %r. The "
                   "substitute must be struck IDENTICALLY in both "
                   "years: two different operations measure two "
                   "different things, and the growth between them "
                   "would be manufactured"
                   % (ceiling_ids[0], this_year.get("operation"),
                      ceiling_ids[1], last_year.get("operation")),
                   "the same containing line in both years, by the "
                   "same arithmetic")
        elif here != there:
            broken("the two capital-spending figures, struck over "
                   "different numbers of figures",
                   "'%s' is struck out of %d figure(s) and '%s' out of "
                   "%d. A strike over a different number of pieces is "
                   "not the same strike, so the two years are not "
                   "comparable"
                   % (ceiling_ids[0], here, ceiling_ids[1], there),
                   "the same containing line in both years, by the "
                   "same arithmetic")

    # AB19 condition 3 as AB20 reshapes it: the figure DECLARES itself
    # a ceiling in the capture's own shape, and names the published
    # line it was struck from. The tag is what the case file renders
    # for every seat, so a substitute the advisors cannot see is a
    # refusal here rather than a lie by omission at the sitting.
    named_lines = {}
    for fact_id in ceiling_ids:
        fact = facts_by_id.get(fact_id)
        if fact is None:
            continue
        tag = _bound_tag(fact, "ceiling")
        if tag is None:
            broken("the stand-in tag on '%s'" % fact_id,
                   "this figure is the WHOLE of a wider line, so it can "
                   "only overstate what the company spends and the cash "
                   "test it feeds is harsher than the truth, never "
                   "kinder - but the capture does not tag it a ceiling, "
                   "so nothing the five advisors read says the figure "
                   "is a bound at all",
                   "a bound tag on the fact, kind 'ceiling', naming the "
                   "published line the figure was struck from")
            continue
        if not tag.get("published_line"):
            broken("the line named by the stand-in tag on '%s'" % fact_id,
                   "this figure is tagged a ceiling but names no "
                   "published line, so there is nothing to compare the "
                   "two years against - the whole point of naming the "
                   "line is that both years must come off the SAME one",
                   "the bound tag's published_line - the line's name as "
                   "the filer prints it")
            continue
        named_lines[fact_id] = tag["published_line"]

    # AB19 condition 2, the half prose could never carry (registered
    # finding P-AB19-1): matching operations over matching operand
    # counts says the two strikes have the same SHAPE, never that they
    # came off the same LINE. A capture could strike the prior year out
    # of an unrelated line and show a year-on-year change that the
    # business never had. Now that each year names its line, the two
    # names must agree.
    if len(named_lines) == len(ceiling_ids):
        first, second = (named_lines[fact_id] for fact_id in ceiling_ids)
        if _text_key(first) != _text_key(second):
            broken("the two capital-spending figures, struck off two "
                   "different published lines",
                   "'%s' is struck from %r and '%s' from %r. The "
                   "substitute must come off the SAME line in both "
                   "years: two different lines hold two different sets "
                   "of items, so the change between them is an artefact "
                   "of the choice of line and not something the "
                   "business did"
                   % (ceiling_ids[0], first, ceiling_ids[1], second),
                   "the same containing line in the comparative column "
                   "of the same filing, named identically in both bound "
                   "tags")

    # AB19 condition 4: free cash flow BUILT ON a ceiling is a FLOOR,
    # and says so where it will be read. Both halves are checked - the
    # label alone, whether a word in a sentence or a tag in the file,
    # would let an ordinary cash flow wear it (audit finding r1-3).
    # Only the figures named here are judged: a rule reaching every
    # figure that rests on a ceiling refuses the ruling's own worked
    # example, whose year-on-year CHANGE rests on both and is neither
    # a floor nor a ceiling.
    #
    # Owner ruling AB22 (registered finding P-AB19-2): these figures
    # must be PRESENT, both years. Judging them only where the capture
    # happened to carry them left the caveat one silent step from
    # vanishing - leave the cash flow out and the council answers the
    # cash question off some other line, with nothing anywhere on the
    # page saying the answer rests on a bound. The capturing session
    # already holds the numbers, so this costs it nothing but the
    # writing down.
    for fact_id, ceiling_id in terms["floors_built_on"].items():
        fact = facts_by_id.get(fact_id)
        if fact is None:
            broken(fact_id,
                   "the figure standing in for capital spending is "
                   "'%s', which can only be too high, so the cash flow "
                   "struck against it is a bound and not a "
                   "measurement. This capture does not carry that cash "
                   "flow at all, so the council would answer the cash "
                   "question with nothing on the page telling the five "
                   "advisors they are reading a bound" % ceiling_id,
                   "the same filing the containing line was read from: "
                   "strike this cash flow by subtracting '%s' from the "
                   "period's operating cash flow, and tag it a floor"
                   % ceiling_id)
            continue
        derived = fact.get("derived") or {}
        names = [item.get("fact_id")
                 for item in derived.get("operands") or ()]
        # CONTAINING the ceiling is not RESTING on it. A figure that is
        # too high only makes the result too low when it is taken away:
        # added, or subtracted the other way round, the result is a
        # ceiling wearing the word floor - the opposite of what the
        # seats would read (audit finding r4-2).
        if derived.get("operation") != "subtract" or (
                ceiling_id not in names[1:]):
            broken("'%s', which is published as a floor but does not "
                   "rest on the ceiling" % fact_id,
                   "the figure standing in for capital spending is "
                   "'%s', and this cash flow is a bound only if that "
                   "figure is SUBTRACTED from the cash the business "
                   "generated. Here it is not, so the arithmetic does "
                   "not support the word the advisors would read"
                   % ceiling_id,
                   "strike this cash flow by subtracting '%s' from the "
                   "period's operating cash flow, or drop the floor "
                   "language from its source" % ceiling_id)
            continue
        if _bound_tag(fact, "floor") is None:
            broken("the bound tag on '%s'" % fact_id,
                   "this cash flow is struck against a capital-spending "
                   "figure that can only be too high, so the cash flow "
                   "itself can only be too low - a floor, not a "
                   "measurement - but the capture does not tag it one, "
                   "so the advisors would read a bound as a fact",
                   "a bound tag on the fact, kind 'floor'")
    return failures


def _as_of_moment(text):
    """An as_of string as a moment for ordering; a date-only value
    means midnight that day (the same reading the gate gives a capture
    timestamp)."""
    if text.endswith("Z"):
        return datetime.fromisoformat(text[:-1])
    return datetime.fromisoformat(text)


def _subject_label(subject):
    if subject.get("ticker"):
        return "%s (%s)" % (subject["name"], subject["ticker"])
    return subject["name"]


def _subtyped_archetype(floors, capture):
    """(the archetype, the sub-type) where a single name's frame declares
    an archetype whose row carries sub-types - the financial institution
    (owner rulings AC28 and AC30) - or None. The sub-type is None where
    the frame names none or one the row does not know; the archetype
    block of check() refuses that in plain words."""
    subject = capture["subject"]
    if subject["kind"] != "single_stock":
        return None
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    archetype = frame.get("archetype") if isinstance(frame, dict) else None
    row = (((floors.get("archetype_measures") or {}).get("table") or {})
           .get(archetype) if isinstance(archetype, str) else None)
    if not isinstance(row, dict) or not row.get("subtypes"):
        return None
    subtype = frame.get(row.get("subtype_field"))
    if not isinstance(subtype, str) or subtype not in row["subtypes"]:
        subtype = None
    return archetype, subtype


def _archetype_lifts(floors, declared):
    """The lifts block (owner ruling AC30(1), G1) where it applies to
    the declared sub-type, else an empty dict."""
    if not declared:
        return {}
    lifts = (((floors.get("archetype_floors") or {}).get(declared[0]) or {})
             .get("lifts") or {})
    return lifts if declared[1] in (lifts.get("subtypes") or ()) else {}


def _merged_floors(floors, subject, capture=None):
    entries = list(floors["classes"][subject["kind"]]["floors"])
    declared = _subtyped_archetype(floors, capture) if capture else None
    # Owner ruling AC30(1) (G1): the one SUBTRACTIVE step in the merge.
    # For a lifted sub-type the class floors named in the lifts block are
    # dropped - the class's own list only, so no per-name ruling is ever
    # undone by it.
    lifted = set(_archetype_lifts(floors, declared)
                 .get("single_stock_floor_ids_lifted") or ())
    entries = [entry for entry in entries
               if not (entry.get("kind") == "id"
                       and entry.get("id") in lifted)]
    ticker = subject.get("ticker")
    named = floors.get("names", {})
    if ticker and ticker in named:
        entries += list(named[ticker]["floors"])
    # Owner rulings AC28 and AC30: the third source, merged on top of the
    # class and the name - what every financial institution carries,
    # then what its own sub-type carries.
    if declared:
        block = (floors.get("archetype_floors") or {}).get(declared[0]) or {}
        entries += list(block.get("all_subtypes") or [])
        if declared[1]:
            entries += list(block.get(declared[1]) or [])
    return entries


def _rests_on(fact_id, targets, facts_by_id, seen=None):
    """The first fact of `targets` this one rests on - itself or an
    operand, transitively - or None. Operands without a fact reference
    are inline constants and rest on nothing."""
    if seen is None:
        seen = set()
    if fact_id in seen:
        return None
    seen.add(fact_id)
    if fact_id in targets:
        return fact_id
    derived = (facts_by_id.get(fact_id) or {}).get("derived")
    if derived:
        for operand in derived.get("operands") or ():
            reference = operand.get("fact_id")
            if reference is not None and reference in facts_by_id:
                hit = _rests_on(reference, targets, facts_by_id, seen)
                if hit is not None:
                    return hit
    return None


def _contributions(fact_id, facts_by_id, sign=1, path=()):
    """{fact id: the list of signed contributions it makes to this fact}
    - +1 added, -1 taken off, None reached through multiplication or
    division - walked down every route, each route counted once, so a
    part reached twice shows twice (audit round three, r3-1)."""
    found = {fact_id: [sign]}
    derived = (facts_by_id.get(fact_id) or {}).get("derived")
    if fact_id in path or not derived:
        return found
    operation = derived.get("operation")
    for place, operand in enumerate(derived.get("operands") or ()):
        reference = operand.get("fact_id")
        if reference is None or reference not in facts_by_id:
            continue
        step = None if sign is None or operation not in (
            "add", "sum", "subtract") else (
            -sign if operation == "subtract" and place else sign)
        deeper = _contributions(reference, facts_by_id, step,
                                path + (fact_id,))
        for fid, steps in deeper.items():
            found.setdefault(fid, []).extend(steps)
    return found


def _miscount(steps, want):
    """Why a part's signed contributions are not exactly one `want` -
    in plain words - or None where they are."""
    times = "twice" if len(steps) == 2 else "%d times" % len(steps)
    if None in steps:
        return "reached by multiplication or division"
    if len(steps) > 1:
        return "counted " + times + (
            "" if set(steps) == {want} else ", added and taken off")
    if steps != [want]:
        return "added" if want == -1 else "taken off"
    return None


def _nav_bridge_failures(frame, rating, facts_by_id):
    """Why a financial holding's net-asset-value bridge is not a real
    chain of captured facts - one (what, why, where) per breach - or
    nothing where it holds (owner rulings AC28 and AC30 (G3)).

    The holding is rated on its discount to what it owns at today's
    prices, so the one figure the rating divides by must be the total
    the bridge strikes; that total must show its arithmetic; every part
    the bridge names - each holding and the holding company's own net
    debt - must be inside it, however many steps down; and the chain
    must end in readings the capture recorded. The discount's own
    history is a floor in the data (archetype_floors), not code here.
    What this cannot check is that the bridge lists EVERY holding: no
    machine reads the list of what a company owns, so the outside
    auditor and the owner carry that."""
    bridge = frame.get("nav_bridge")
    if not isinstance(bridge, dict):
        return [(
            "the bridge a financial holding's net asset value is struck "
            "through",
            "owner rulings AC28 and AC30 (G3): a financial holding is rated "
            "on its discount to what it owns at today's prices, and this "
            "frame names no nav_bridge, so nothing shows what that value "
            "is made of",
            "the business frame's nav_bridge: each holding with its value "
            "fact, the holding company's net debt and the total")]
    failures = []
    total = bridge.get("nav_total_fact")
    denominators = (rating or {}).get("subject_denominator_facts") or []
    if denominators != [total]:
        failures.append((
            "the net asset value the rating divides by, struck through the "
            "bridge",
            "owner rulings AC28 and AC30 (G3): a financial holding is rated "
            "on its discount to what it owns at today's prices, so the one "
            "figure the rating divides by is the total its bridge strikes - "
            "the rating names %s and the bridge's total is '%s'"
            % (", ".join("'%s'" % fid for fid in denominators) or "nothing",
               total),
            "the rating_vs_history_or_peers row: 'subject_denominator_facts' "
            "naming the nav_bridge's nav_total_fact alone"))
    if not (facts_by_id.get(total) or {}).get("derived"):
        failures.append((
            "a net asset value struck from its parts",
            "owner rulings AC28 and AC30 (G3): '%s' carries no arithmetic - "
            "a total typed in shows nothing of the holdings and the debt it "
            "claims to add up, so the discount would rest on a figure no "
            "one can follow" % total,
            "a derived fact for the total: the holdings' values less the "
            "holding company's net debt, arithmetic shown"))
    else:
        parts = [(component.get("value_fact"), "the value of the holding "
                  "'%s'" % component.get("name"))
                 for component in bridge.get("components") or ()]
        parts.append((bridge.get("holdco_net_debt_fact"),
                      "the holding company's net debt"))
        outside = ["'%s' (%s)" % (fid, words) for fid, words in parts
                   if _rests_on(total, {fid}, facts_by_id) is None]
        if outside:
            failures.append((
                "every part of the bridge inside the net asset value",
                "owner rulings AC28 and AC30 (G3): the bridge names %s, and "
                "'%s' is not struck from it at any step - a part left out "
                "of the total makes the discount a figure of some other "
                "company" % ("; ".join(outside), total),
                "the total's arithmetic, directly or through a subtotal, "
                "taking in every holding and the holding company's net "
                "debt"))
        # Inside is not enough: the value is the holdings LESS the net
        # debt, so each holding must be added and the debt taken off,
        # by every route the chain takes (audit round one, r1-2).
        # Each holding must enter exactly once with a plus and the debt
        # exactly once with a minus (round three, r3-1). A part outside
        # the total is refused above. The net debt is the last part.
        found = _contributions(total, facts_by_id)
        wants = [1] * (len(parts) - 1) + [-1]
        wrong = ["'%s' (%s: %s)" % (fid, words, _miscount(found[fid], want))
                 for (fid, words), want in zip(parts, wants)
                 if fid in found and _miscount(found[fid], want)]
        if wrong:
            failures.append((
                "every holding added into the net asset value and the "
                "holding company's net debt taken off it",
                "owner rulings AC28 and AC30 (G3): the net asset value is "
                "the holdings' values less the holding company's net debt, "
                "and '%s' does not strike %s that way - the total would "
                "recompute exactly and still be the wrong figure to divide "
                "by" % (total, "; ".join(wrong)),
                "the total's arithmetic, in sums and subtractions: every "
                "holding added, the holding company's net debt subtracted"))
        unsourced = _unsourced_leaf(total, facts_by_id)
        if unsourced:
            holder, label = unsourced
            failures.append((
                "a net asset value resting on recorded readings",
                "owner rulings AC28 and AC30 (G3): followed down, '%s' "
                "rests on %r - a number written into the capture, resting "
                "on no captured reading at all. The arithmetic would "
                "recompute exactly and still show nothing" % (holder, label),
                "capture the figure itself as a fact, dated and sourced, "
                "and strike the total from it"))
    return failures


def _fi_failures(floors, declared, row, frame, rating, changing, gap_kinds,
                 decisive_ids, facts_by_id):
    """Why a financial institution's frame breaks the rule the floors
    set for it (owner rulings AC28 and AC30) - one (what, why, where)
    per breach - or nothing where it holds. The frame's SHAPE is the
    provenance gate's; this is the rule against the floors data."""
    subtype = declared[1]
    failures = []
    families = floors.get("fi_families") or {}
    capital = frame.get("fi_capital")
    capital = capital if isinstance(capital, dict) else {}
    risk_cost = frame.get("fi_risk_cost")
    risk_cost = risk_cost if isinstance(risk_cost, dict) else {}

    # A financial holding is rated on its net asset value, so the bridge
    # that value is struck through is checked whole.
    if row.get("requires_nav_bridge"):
        failures.extend(_nav_bridge_failures(frame, rating, facts_by_id))

    # Where the capital may be a gap: a manager holds no regulatory
    # capital of its own; a holding only where no principal holding is
    # regulated; a bank, insurer or reinsurer never.
    if "gap" in capital:
        declared_classes = gap_kinds.get(_FI_HOLDING_CAPITAL_GAP_CLASS) or ()
        holding_exempt = (subtype == _FI_HOLDING and declared_classes
                          and all(reason == "absent_by_design"
                                  for reason in declared_classes))
        if subtype not in _FI_CAPITAL_GAP_SUBTYPES and not holding_exempt:
            failures.append((
                "the capital a %s must hold, beside its requirement"
                % subtype.replace("_", " "),
                "owner rulings AC28 and AC30: the headroom above the "
                "regulator's minimum decides what a %s can pay out and "
                "whether it survives a bad year, so its capital is never "
                "a gap - only a manager of clients' capital, or a holding "
                "none of whose principal holdings is regulated (the fact "
                "class '%s' declared absent by design), may declare one"
                % (subtype.replace("_", " "), _FI_HOLDING_CAPITAL_GAP_CLASS),
                "the capital section of the latest results: the capital "
                "ratio beside its requirement, named in fi_capital"))

    # The capital ratio is always decisive (architect ruling 6).
    ratio_facts = [fid for fid in capital.get("ratio_facts") or ()
                   if isinstance(fid, str)]
    if ratio_facts and not set(ratio_facts) & decisive_ids:
        failures.append((
            "a decisive metric resting on the capital ratio",
            "owner rulings AC28 and AC30: a financial institution's "
            "capital beside its requirement always decides the case, and "
            "no decisive metric in the business frame rests on %s"
            % ", ".join("'%s'" % fid for fid in ratio_facts),
            "name the capital ratio in the 'answered_by' of a decisive "
            "metric"))

    # The families (fi_families): a capital line cites capital, a
    # requirement line a requirement, a risk-cost line a cost of risk.
    for key, prefixes_key, words in (
            ("ratio_facts", "capital_ratio_prefixes", "capital ratio"),
            ("requirement_facts", "capital_requirement_prefixes",
             "capital requirement")):
        prefixes = tuple(families.get(prefixes_key) or ())
        for fid in capital.get(key) or ():
            if isinstance(fid, str) and not fid.startswith(prefixes):
                failures.append((
                    "a %s in its own fact family" % words,
                    "owner rulings AC28 and AC30: fi_capital names '%s' as "
                    "a %s, and a %s's id starts with one of %s - a capital "
                    "line cannot cite a fact that is not one"
                    % (fid, words, words, ", ".join(prefixes)),
                    "the %s fact itself, named in its family" % words))
    # Each ratio stands beside the requirement FOR THAT RATIO (the
    # contract's own words), and each requirement beside its ratio: the
    # two family lists run in parallel, and 'cet1_ratio_<x>' pairs with
    # 'cet1_requirement_<x>' - the suffix rule the prefix_pairs floors
    # already read. A ratio set beside another ratio's minimum shows a
    # headroom that is not there.
    requirement_ids = [fid for fid in capital.get("requirement_facts") or ()
                       if isinstance(fid, str)]
    prefix_pairs = list(zip(families.get("capital_ratio_prefixes") or (),
                            families.get("capital_requirement_prefixes")
                            or ()))
    for fids, others, mine, theirs, words, other_words in (
            (ratio_facts, requirement_ids, 0, 1, "ratio", "requirement"),
            (requirement_ids, ratio_facts, 1, 0, "requirement", "ratio")):
        for fid in fids:
            pair = next((pair for pair in prefix_pairs
                         if fid.startswith(pair[mine])), None)
            if pair is None:
                continue
            partner = pair[theirs] + fid[len(pair[mine]):]
            if partner not in others:
                failures.append((
                    "a capital %s beside its own %s" % (words, other_words),
                    "owner rulings AC28 and AC30: fi_capital shows '%s' "
                    "beside %s, and the %s for that %s is '%s' - a capital "
                    "line set beside another line's figure shows a "
                    "headroom that is not there"
                    % (fid, ", ".join("'%s'" % item for item in others)
                       or "nothing", other_words, words, partner),
                    "fi_capital: '%s' named beside '%s'" % (partner, fid)))
    risk_ids = set(families.get("risk_cost_ids") or ())
    risk_prefixes = tuple(families.get("risk_cost_prefixes") or ())
    for fid in risk_cost.get("facts") or ():
        if (isinstance(fid, str) and fid not in risk_ids
                and not fid.startswith(risk_prefixes)):
            failures.append((
                "a cost of risk in its own fact family",
                "owner rulings AC28 and AC30: fi_risk_cost names '%s', and "
                "a cost of risk is one of %s or starts with one of %s - a "
                "risk-cost line cannot cite a fact that is not a cost of "
                "risk" % (fid, ", ".join(sorted(risk_ids)),
                          ", ".join(risk_prefixes)),
                "the provision, credit cost, combined ratio, large loss or "
                "reserve development fact itself"))
    # The family matches the declared kind (architect ruling closing
    # P-FIa-2): a credit line cites a credit fact, an underwriting line
    # an underwriting fact. The gate already fits the kind to the sub-type.
    by_kind = families.get("risk_cost_kinds") or {}
    declared_kind = risk_cost.get("kind")
    for fid in risk_cost.get("facts") or ():
        if not isinstance(fid, str):
            continue
        kinds = sorted(
            kind for kind, family in by_kind.items()
            if isinstance(family, dict)
            and (fid in (family.get("ids") or ())
                 or fid.startswith(tuple(family.get("prefixes") or ()))))
        if kinds and declared_kind in by_kind and declared_kind not in kinds:
            failures.append((
                "a cost of risk of the kind the frame declares",
                "fi_risk_cost declares a %s cost of risk and cites '%s', "
                "which is %s fact - a %s reads its cost of risk as the "
                "line where its own cycle enters its earnings, and this "
                "one is another business's cycle"
                % (declared_kind, fid,
                   " or ".join("an %s" % kind if kind[0] in "aeiou"
                               else "a %s" % kind for kind in kinds),
                   subtype.replace("_", " ")),
                "the %s fact itself - %s" % (
                    declared_kind,
                    "a provision or credit cost" if declared_kind == "credit"
                    else "a combined ratio, large loss or reserve "
                         "development")))

    exited = ((floors.get("archetype_measures") or {})
              .get("fi_exited_business") or {})
    # Each denominator is a fact its role allows (architect ruling closing
    # P-FIa-1): the sub-type row names, per role, the ids the brief's row
    # prescribes - on the subject's side and on the peers' alike. The
    # continuing business's figure is the same id with its suffix.
    suffix = exited.get("continuing_suffix") or ""
    for side, named in (
            ("the subject's side",
             (rating or {}).get("subject_denominator_facts") or []),
            ("the peers' side",
             (rating or {}).get("peer_denominator_metrics") or [])):
        for fid, role, allowed in zip(named, row.get("denominator_roles")
                                      or (), row.get("denominator_ids")
                                      or ()):
            if not isinstance(fid, str):
                continue
            bare = (fid[:-len(suffix)] if suffix and fid.endswith(suffix)
                    else fid)
            if bare not in allowed:
                who = subtype.replace("_", " ")
                what = "%s %s's %s denominator" % (
                    "an" if who[0] in "aeiou" else "a", who,
                    role.replace("_", " "))
                failures.append((
                    what,
                    "architect ruling closing P-FIa-1: the rating divides "
                    "by '%s' on %s, and %s must be one of %s - the measure "
                    "is struck on those, and any other fact is another "
                    "measure" % (fid, side, what,
                                 ", ".join("'%s'" % item
                                           for item in allowed)),
                    "the rating_vs_history_or_peers row: %s named as that "
                    "denominator, in the role order the sub-type lists"
                    % " or ".join("'%s'" % item for item in allowed)))

    # Owner ruling AC30(4) (G4): on a model transition the exited
    # business's earnings and client money are banned as its revenue is.
    if changing == "model_transition" and exited:
        suffix = exited.get("continuing_suffix") or ""
        banned_roles = set(exited.get("roles") or ())
        denominators = (rating or {}).get("subject_denominator_facts") or []
        for fid, role in zip(denominators, row.get("denominator_roles") or ()):
            if (role in banned_roles and isinstance(fid, str)
                    and not fid.endswith(suffix)):
                failures.append((
                    "the continuing business's %s as the rating's "
                    "denominator" % role.replace("_", " "),
                    "owner ruling AC30(4): this business is changing its "
                    "model, and the rating divides by '%s', the %s of the "
                    "whole business - including the part being sold or "
                    "run off. The %s the rating rests on is the continuing "
                    "business's, its id ending '%s'"
                    % (fid, role.replace("_", " "), role.replace("_", " "),
                       suffix),
                    "the continuing business's figure - a derived fact may "
                    "strike it from the whole less the part being exited, "
                    "arithmetic shown"))
    return failures


def _dedupe(items):
    seen = set()
    kept = []
    for item in items:
        if item not in seen:
            seen.add(item)
            kept.append(item)
    return kept


def check(pack, floors):
    """Verify the pack can answer the question before a seat is paid.

    Returns {"result", "floors", "requirements_checked", "missing",
    "message"}; "missing" items each carry what / why_needed /
    where_it_likely_lives, and the message is written for an investor
    to act on.
    """
    capture = pack["capture"]
    subject = capture["subject"]
    if subject["kind"] == "single_stock" and not subject.get("ticker"):
        label = _subject_label(subject)
        return {
            "result": "refuse",
            "floors": {"satisfied": [], "lifted_by_declared_gap": [],
                       "advisory_missing": []},
            "requirements_checked": 0,
            "missing": [{
                "what": "the subject's ticker",
                "why_needed": ("the owner's per-name evidence minimums "
                               "are keyed by ticker; a single name "
                               "without one cannot be checked against "
                               "them, so nothing here may be trusted "
                               "as complete"),
                "where_it_likely_lives": ("the exchange listing or the "
                                          "broker's own quote page")}],
            "message": ("Not enough evidence to convene the council on "
                        "%s.\nThe capture names no ticker for this "
                        "single name. The owner's per-name minimums "
                        "are keyed by ticker; without it they cannot "
                        "be checked, so no seat is paid.\nAdd the "
                        "ticker from the exchange listing or the "
                        "broker's own quote page and capture again."
                        % label)}

    # Audit finding THEMES-A r5-3: a null etf ticker was schema-valid
    # and passed, silently shedding the per-name minimums exactly as a
    # null single-name ticker once did (r2-2) - and an ETF is ONE
    # listed instrument, so a fund without its ticker cannot be
    # honestly judged either.
    if subject["kind"] == "etf" and not subject.get("ticker"):
        label = _subject_label(subject)
        return {
            "result": "refuse",
            "floors": {"satisfied": [], "lifted_by_declared_gap": [],
                       "advisory_missing": []},
            "requirements_checked": 0,
            "missing": [{
                "what": "the fund's ticker",
                "why_needed": ("an ETF is one listed instrument, and "
                               "the owner's per-name evidence minimums "
                               "are keyed by ticker; a fund without "
                               "one cannot be checked against them, "
                               "so nothing here may be trusted as "
                               "complete"),
                "where_it_likely_lives": ("the exchange listing or the "
                                          "fund's own quote page")}],
            "message": ("Not enough evidence to convene the council on "
                        "%s.\nThe capture names no ticker for this "
                        "fund. An ETF is one listed instrument, and "
                        "the owner's per-name minimums are keyed by "
                        "ticker; without it they cannot be checked, "
                        "so no seat is paid.\nAdd the ticker from the "
                        "exchange listing or the fund's own quote "
                        "page and capture again." % label)}

    class_config = floors["classes"][subject["kind"]]
    entries = _merged_floors(floors, subject, capture)
    declared = _subtyped_archetype(floors, capture)
    # Owner ruling AC30(1) (G1): for a bank, insurer, reinsurer or
    # financial holding the free-cash test is answered by distributable
    # capital, and its refusal words come from the lifts data block. The
    # guide itself is never changed: every other subject reads it as is.
    lifts = _archetype_lifts(floors, declared)
    guide = dict(_CANONICAL_GUIDE)
    if lifts:
        guide["free_cash_flow"] = tuple(lifts["free_cash_flow_test_words"])

    tier1_rules = {}
    tier1_order = []
    for fact in capture["tier1"]:
        if fact["id"] not in tier1_rules:
            tier1_order.append(fact["id"])
            tier1_rules[fact["id"]] = fact["freshness_rule_days"]
    tier2_ids = {passage["id"] for passage in capture["tier2"]}
    # A declared gap lifts a conditional floor only when the capture
    # says the fact class is absent BY DESIGN - any other reason is a
    # gathering failure, not an unavailability (audit finding r1-6).
    #
    # EVERY row for a class is kept, not just the last one. Nothing
    # stops a capture naming one class twice, and reading only the last
    # row let an appended row silently reverse the first: it could lift
    # a floor whose real reason was a gathering failure, and it could
    # switch the AB19 substitute check off altogether (audit finding
    # AB19 r1-5). Each reader below takes the safer direction over the
    # whole list.
    gap_kinds = {}
    for gap in capture["gaps"]:
        gap_kinds.setdefault(gap["fact_class"], []).append(
            gap.get("reason_kind"))
    freshness = pack.get("freshness", {})
    facts_by_id = {fact["id"]: fact for fact in capture["tier1"]}

    def stale_dependency(fact_id, seen=None):
        """The first fact this one actually rests on - itself, an
        operand, or an operand's operand - that is not within_rule;
        None when the whole chain is fresh. A fresh derived fact must
        not launder a stale operand (audit finding r6-5); operands
        without a fact reference are inline constants and carry no
        freshness."""
        if seen is None:
            seen = set()
        if fact_id in seen:
            return None
        seen.add(fact_id)
        record = freshness.get(fact_id, {})
        if record.get("status") != "within_rule":
            return fact_id
        derived = (facts_by_id.get(fact_id) or {}).get("derived")
        if derived:
            for operand in derived["operands"]:
                reference = operand.get("fact_id")
                if reference is not None and reference in facts_by_id:
                    offender = stale_dependency(reference, seen)
                    if offender is not None:
                        return offender
        return None

    def fresh(fact_id):
        return stale_dependency(fact_id) is None

    def stale_words(fact_id):
        offender = stale_dependency(fact_id) or fact_id
        record = freshness.get(offender, {})
        words = ("'%s' is present but stale at capture - %s days old "
                 "against its %s-day rule - and a stale must-have "
                 "cannot convene the council"
                 % (offender, record.get("age_days"),
                    record.get("rule_days")))
        if offender != fact_id:
            words = ("'%s' rests on %s" % (fact_id, words))
        return words

    satisfied = []
    lifted_by_declared_gap = []
    advisory_missing = []
    missing = []

    def refuse(what, why_needed, where):
        missing.append({"what": what, "why_needed": why_needed,
                        "where_it_likely_lives": where})

    def enforce_stale(entry, what, words):
        """A floor's fact is PRESENT but stale: the level governs.
        Advisory is recorded and never refuses (the floors legend's own
        rule); required and conditional refuse - a declared gap asserts
        absence and can never lift a fact that is sitting in the pack."""
        if entry["level"] == "advisory":
            advisory_missing.append(what + " (present but stale at "
                                    "capture)")
            return
        refuse(what, words + " (%s)" % entry["why"],
               entry["likely_source"])

    def enforce_absence(entry, what, lift_key):
        """A floor's item is absent: refuse, lift, or note it,
        according to the floor's level."""
        level = entry["level"]
        if level == "advisory":
            advisory_missing.append(what + " (not captured)")
            return
        # A floor is lifted only where EVERY row declared for the class
        # says absent-by-design: one row calling it a gathering failure
        # is enough to keep the floor standing.
        declared = gap_kinds.get(lift_key) or ()
        if (level == "conditional" and declared
                and all(reason == "absent_by_design"
                        for reason in declared)):
            lifted_by_declared_gap.append(lift_key)
            return
        why = entry["why"]
        if level == "conditional":
            if lift_key in gap_kinds:
                why += (" - a gap is declared but not as absent-by-"
                        "design, so it reads as a gathering failure, "
                        "not an unavailability")
            else:
                why += (" - the fact is absent and the capture does "
                        "not declare why it is unavailable")
        refuse(what, why, entry["likely_source"])

    def evaluate(entry):
        floor_kind = entry["kind"]
        if floor_kind == "id":
            fact_id = entry["id"]
            if fact_id in tier1_rules:
                # Some anchors are not readings at all: they ARE the
                # difference of two other facts in the same pack. The
                # owner ruled the PBoC divergence must be VISIBLE, and a
                # figure that merely claims to be a difference is
                # asserted, not visible - so it declares its arithmetic
                # and the gate recomputes it exactly (audit finding
                # ANCHORLESS-A2 r2-1).
                if entry.get("requires_arithmetic"):
                    reason = _arithmetic_mismatch(
                        entry, facts_by_id.get(fact_id) or {})
                    if reason:
                        refuse(fact_id, reason + " (%s)" % entry["why"],
                               entry["likely_source"])
                # Owner ruling AB19: where the capture DECLARES that the
                # filer publishes no line of its own for this fact, the
                # figure standing in its place carries the ruling's own
                # terms. Undeclared, this is a no-op and an ordinary
                # sitting sees no change at all.
                for what, why, where in _substitute_failures(
                        entry, facts_by_id, gap_kinds):
                    refuse(what, why, where)
                if not fresh(fact_id):
                    enforce_stale(entry, fact_id, stale_words(fact_id))
                else:
                    satisfied.append(fact_id)
                ceiling = entry.get("max_freshness_days")
                if ceiling is not None and tier1_rules[fact_id] > ceiling:
                    refuse(fact_id,
                           "the ruled freshness for this fact is at "
                           "most %d day(s), but the capture declares a "
                           "%d-day rule - too loose to trust at a "
                           "sitting (%s)"
                           % (ceiling, tier1_rules[fact_id],
                              entry["why"]),
                           entry["likely_source"])
            else:
                enforce_absence(entry, fact_id, fact_id)
        elif floor_kind == "one_of":
            present = [i for i in entry["ids"] if i in tier1_rules]
            usable = [i for i in present if fresh(i)]
            if usable:
                satisfied.append(usable[0])
            elif present:
                enforce_stale(entry, "one of: " + ", ".join(entry["ids"]),
                              "; ".join(stale_words(i) for i in present))
            else:
                enforce_absence(entry,
                                "one of: " + ", ".join(entry["ids"]),
                                None)
        elif floor_kind == "prefix":
            prefix = entry["prefix"]
            matches = [i for i in tier1_order if i.startswith(prefix)]
            usable = [i for i in matches if fresh(i)]
            if usable:
                satisfied.append(usable[0])
            elif matches:
                enforce_stale(entry,
                              "a fact whose id starts with '%s'" % prefix,
                              "; ".join(stale_words(i) for i in matches))
            else:
                enforce_absence(entry,
                                "a fact whose id starts with '%s'"
                                % prefix,
                                prefix)
        elif floor_kind == "pairs":
            for first, second in entry["pairs"]:
                if first not in tier1_rules:
                    continue
                if second not in tier1_rules:
                    enforce_absence(entry,
                                    "%s (the companion figure beside "
                                    "%s)" % (second, first),
                                    second)
                elif not fresh(second):
                    enforce_stale(entry,
                                  "%s (the companion figure beside %s)"
                                  % (second, first),
                                  stale_words(second))
                else:
                    satisfied.append("%s with %s" % (first, second))
        elif floor_kind == "prefix_pairs":
            # A family that only means anything in pairs: what
            # management guided for a quarter, beside what it actually
            # delivered (owner ruling AC1). Either half alone says
            # nothing about whether management hits its own numbers, so
            # the family must be there - or declared absent - and every
            # member of it must carry its companion.
            prefix = entry["prefix"]
            companion = entry["companion_prefix"]
            matches = [i for i in tier1_order if i.startswith(prefix)]
            if not matches:
                enforce_absence(
                    entry,
                    "a fact whose id starts with '%s', with its '%s' "
                    "companion" % (prefix, companion),
                    prefix)
                return
            for fact_id in matches:
                partner = companion + fact_id[len(prefix):]
                if partner not in tier1_rules:
                    enforce_absence(entry,
                                    "%s (the companion figure beside %s)"
                                    % (partner, fact_id), partner)
                elif not fresh(partner):
                    enforce_stale(entry,
                                  "%s (the companion figure beside %s)"
                                  % (partner, fact_id),
                                  stale_words(partner))
                elif not fresh(fact_id):
                    enforce_stale(entry, fact_id, stale_words(fact_id))
                else:
                    satisfied.append("%s with %s" % (fact_id, partner))
        elif floor_kind == "parallel_prefixes":
            # A repeated structure - one row per cycle, one per venue -
            # is complete or it is not there. Each prefix must be
            # present AND the suffixes must be the same set across all
            # of them, so a capture cannot answer three peaks and one
            # recovery time and read as complete (ANCHORLESS-SPEC
            # 4.A.6: the durations were the cold read's central gap).
            prefixes = entry["prefixes"]
            suffixes = {}
            for prefix in prefixes:
                suffixes[prefix] = {fact_id[len(prefix):]
                                    for fact_id in tier1_order
                                    if fact_id.startswith(prefix)
                                    and len(fact_id) > len(prefix)}
            empty = [p for p in prefixes if not suffixes[p]]
            if len(empty) == len(prefixes):
                enforce_absence(
                    entry,
                    "the whole family: facts named %s"
                    % ", ".join("'%s...'" % p for p in prefixes),
                    prefixes[0])
                return
            # A repeated structure whose members all agree on ONE member
            # is complete and still not a history: the cold read's
            # complaint was about comparing ACROSS cycles, and one
            # cycle cannot be compared with anything (audit finding
            # ANCHORLESS-A2 r2-2).
            minimum = entry.get("min_members")
            members = set()
            for prefix in prefixes:
                members |= suffixes[prefix]
            if minimum is not None and len(members) < minimum:
                refuse("at least %d members of the family named %s"
                       % (minimum,
                          ", ".join("'%s...'" % p for p in prefixes)),
                       "the capture carries %d (%s), and %d is the "
                       "fewest that can be compared with each other - "
                       "one cycle is an anecdote, not a history (%s)"
                       % (len(members),
                          ", ".join(sorted(members)) or "none",
                          minimum, entry["why"]),
                       entry["likely_source"])
            for prefix in empty:
                refuse("facts named '%s...'" % prefix,
                       "the capture carries %s but nothing named '%s...' "
                       "- the family is answered for one part and silent "
                       "for another (%s)"
                       % (", ".join("'%s...'" % p for p in prefixes
                                    if suffixes[p]),
                          prefix, entry["why"]),
                       entry["likely_source"])
            covered = set()
            for prefix in prefixes:
                covered |= suffixes[prefix]
            for prefix in prefixes:
                if not suffixes[prefix]:
                    continue
                for suffix in sorted(covered - suffixes[prefix]):
                    refuse("'%s%s'" % (prefix, suffix),
                           "the capture answers '%s' for other members "
                           "of this family but not for '%s' - every "
                           "member of a repeated structure carries every "
                           "part of it, or the gap is invisible on the "
                           "page (%s)"
                           % (prefix, suffix, entry["why"]),
                           entry["likely_source"])
            for prefix in prefixes:
                for suffix in sorted(suffixes[prefix]):
                    fact_id = prefix + suffix
                    if not fresh(fact_id):
                        enforce_stale(entry, fact_id, stale_words(fact_id))
                    else:
                        satisfied.append(fact_id)
        else:
            # Audit finding THEMES-A r3-1: an entry this gate cannot
            # evaluate must never be skipped in silence - the ruled
            # minimum it encodes would quietly stop existing. A broken
            # floors file is a broken instrument, not an insufficient
            # capture, so it stops on the crash channel (exit 1), never
            # as a refusal telling the owner to capture again.
            raise ValueError(
                "the floors file carries an entry of kind %r, which "
                "this gate cannot evaluate (it knows id, one_of, "
                "prefix, pairs, prefix_pairs, parallel_prefixes) - the "
                "ruled minimum "
                "that entry encodes would be silently skipped, so the "
                "floors file must be fixed before any pack is judged "
                "against it" % floor_kind)

    for entry in entries:
        evaluate(entry)

    # ---- the ASSET CLASS's own anchors (ANCHORLESS-SPEC section 4) ----
    # The shape's floors say what a subject of this SHAPE always carries;
    # the class's anchors say what an asset of this SUBSTANCE must answer
    # before it can be rated at all. An equity's anchors are the four
    # canonical tests below and its list is empty.
    class_entry = subjects.class_registry(floors, subject)
    if class_entry is None:
        raise ValueError(
            "the floors file carries no asset_classes entry for %r, so "
            "the anchors this subject's class obliges cannot be checked "
            "- the ruled minimums would be silently skipped, and the "
            "floors file must be fixed before any pack is judged "
            "against it" % subjects.asset_class(subject))
    # ANCHORLESS-SPEC section 12 (architect ruling C2): a product the
    # owner has never ruled on does not sit. Section 8 sends each
    # product's conditional items back to him when the product is
    # charged, and a refusal is what forces that return - sitting on the
    # template alone is what skips it. The note is the product: what
    # would make this question sittable, at capture cost.
    named_product = subjects.product(subject)
    if named_product and named_product not in (
            class_entry.get("products") or {}):
        refuse("the owner's ruling on what %s needs beyond the template"
               % named_product,
               "no evidence items have been ruled for this product. The "
               "template covers what every commodity needs, but the two "
               "product-conditional items are decided per product and "
               "nobody has decided them for this one: whether an "
               "exchange stocks series exists for it and at which "
               "venues (or whether the reasoned gap is declared "
               "instead), and whether an undistorted positioning report "
               "exists for it. Until those are ruled and the product is "
               "in the registry, a sitting would judge it against a "
               "lower standard than any the owner has approved",
               "the owner's determination of those two items, and the "
               "product's entry in council/floors/floors.json under "
               "asset_classes.commodity.products - copper is the worked "
               "example to follow")
    for entry in subjects.class_anchors(floors, subject):
        evaluate(entry)

    requirements = capture["sufficiency"]["requirements"]
    requirements_by_id = {}
    for requirement in requirements:
        requirements_by_id.setdefault(requirement["id"], requirement)

    # An asset with no earnings cannot answer the four earnings tests,
    # whatever shape wraps it: a fund holding coins is judged as crypto
    # THROUGH the fund (ANCHORLESS-SPEC section 2). Its own class
    # anchors, checked above, are what it is judged on instead.
    absence_allowed = (class_config.get("canonical_tests")
                       == "absent_by_design_allowed"
                       or subjects.is_anchorless(subject))
    for test_id in CANONICAL_TEST_IDS:
        guide_why, guide_where = guide[test_id]
        requirement = requirements_by_id.get(test_id)
        if requirement is None or requirement["kind"] != "canonical_test":
            refuse(test_id,
                   "this canonical test is not on the pack's checklist "
                   "at all - " + guide_why,
                   guide_where)
        elif (requirement["status"] == "declared_gap"
              and not absence_allowed):
            refuse(test_id,
                   "for this class of subject the test must be "
                   "answered from the pack, never declared a gap - "
                   + guide_why,
                   guide_where)

    for requirement in requirements:
        requirement_id = requirement["id"]
        description = requirement["description"]
        if requirement_id in guide:
            hint = guide[requirement_id][1]
        else:
            hint = ("start from what the requirement itself describes: "
                    + description)
        if requirement["status"] == "answered":
            answered_by = requirement["answered_by"]
            if not answered_by:
                refuse(requirement_id,
                       "it is marked answered but names no supporting "
                       "facts (%s)" % description,
                       hint)
            prefix = lifts.get("free_cash_flow_test_answered_by_prefix")
            if (requirement_id == "free_cash_flow" and prefix
                    and requirement["kind"] == "canonical_test"
                    and not any(fact_id.startswith(prefix)
                                and fact_id in tier1_rules
                                for fact_id in answered_by)):
                refuse(requirement_id,
                       "owner ruling AC30(1): %s - so this test is "
                       "answered by a '%s' fact, and it names none (%s)"
                       % (guide[requirement_id][0], prefix, description),
                       hint)
            for fact_id in answered_by:
                if fact_id in tier1_rules:
                    offender = stale_dependency(fact_id)
                    if offender is not None:
                        record = freshness.get(offender, {})
                        rests = ("" if offender == fact_id
                                 else "'%s' rests on it and " % fact_id)
                        refuse(requirement_id,
                               "'%s' is present but stale - %s days "
                               "old against its %s-day rule - %sso "
                               "this requirement (%s) cannot rest on "
                               "it"
                               % (offender, record.get("age_days"),
                                  record.get("rule_days"), rests,
                                  description),
                               "a fresher reading of '%s' from the "
                               "source that produced it" % offender)
                elif fact_id not in tier2_ids:
                    refuse(requirement_id,
                           "it claims support from '%s', which is "
                           "nowhere in the pack (%s)"
                           % (fact_id, description),
                           hint)
        else:  # declared_gap
            if (not requirement.get("gap_reason")
                    or not requirement.get("weakened_test")):
                refuse(requirement_id,
                       "a declared gap must say why the fact family is "
                       "unavailable and which test it weakens (%s)"
                       % description,
                       hint)
            elif requirement.get("reason_kind") != "absent_by_design":
                refuse(requirement_id,
                       "a checklist item may be declared a gap only "
                       "for a fact class that is absent by design - "
                       "this one is not declared so, which reads as a "
                       "gathering failure (%s)" % description,
                       hint)

    # ---------- the business frame (owner ruling AC1) ----------
    # The cold read of 2026-09-08 found the hole this closes: the pack's
    # own checklist is written by the capturing session, so the one
    # number that decides a case can be left off it and nothing notices
    # (findings E3, E6). A priced business must now SAY what it is, how
    # it earns, what is changing, and the three to five numbers the
    # question turns on - and each of those numbers resolves here, to a
    # present, in-rule fact or to an honest gap, before a seat is paid.
    frames = capture.get("business_frame") or {}
    required_frames = gate.frame_tickers(subject)[0]

    def frame_words(ticker):
        return ("the business frame for %s" % ticker
                if len(required_frames) > 1 or ticker != subject.get("ticker")
                else "the business frame")

    for ticker in required_frames:
        if frames.get(ticker):
            continue
        refuse(frame_words(ticker),
               "%s. The parts a frame carries, and this capture carries "
               "none of them: %s"
               % (FRAME_REFUSAL,
                  "; ".join(words for _, words in gate.FRAME_PARTS)),
               _FRAME_LIKELY_SOURCE)

    for ticker in sorted(frames):
        frame = frames[ticker]
        metrics = frame["decisive_metrics"]
        if (ticker in required_frames
                and len(metrics) < _DECISIVE_METRIC_MINIMUM):
            refuse("at least %d decisive metrics in %s"
                   % (_DECISIVE_METRIC_MINIMUM, frame_words(ticker)),
                   "the frame names %d of the three to five numbers that "
                   "decide this question; below three there is no set to "
                   "argue over - one number is a thesis and two are a "
                   "preference" % len(metrics),
                   _FRAME_LIKELY_SOURCE)
        for row in metrics:
            if row["gap"]:
                continue
            for fact_id in row["answered_by"]:
                if fact_id in tier1_rules:
                    offender = stale_dependency(fact_id)
                    if offender is None:
                        satisfied.append(fact_id)
                        continue
                    record = freshness.get(offender, {})
                    rests = ("" if offender == fact_id
                             else "'%s' rests on it and " % fact_id)
                    refuse("the decisive metric '%s' in %s"
                           % (row["name"], frame_words(ticker)),
                           "'%s' is present but stale - %s days old "
                           "against its %s-day rule - %sso the number "
                           "this question turns on cannot be read from "
                           "the pack"
                           % (offender, record.get("age_days"),
                              record.get("rule_days"), rests),
                           "a fresher reading of '%s' from the source "
                           "that produced it" % offender)
                elif fact_id not in tier2_ids:
                    refuse("the decisive metric '%s' in %s"
                           % (row["name"], frame_words(ticker)),
                           "it claims to be answered by '%s', which is "
                           "nowhere in the pack" % fact_id,
                           _FRAME_LIKELY_SOURCE)

    def measure_component_fault(fact_id):
        """Why a rating-measure component - a numerator or a denominator,
        on the subject or a peer - is not a reading the ratio can be
        struck from, or None when it can. The same bar for every part of
        the ratio on both sides (owner ruling AC15 P2; architect ruling
        2026-09-20): a tier-1 fact - a tier-2 passage alone is a mention,
        not a reading a ratio can rest on - fresh against its own rule,
        and a finite number."""
        if fact_id not in tier1_rules:
            return "absent"
        if stale_dependency(fact_id) is not None:
            return "stale"
        if gate._decimal_or_none(facts_by_id[fact_id]["value"]) is None:
            return "nan"
        return None

    def denominator_fault(fact_id):
        """Why a DENOMINATOR cannot be divided into: the numerator's own
        bar (measure_component_fault) AND a value that is not zero. A ratio
        with a zero denominator is undefined, so a rating divided by it is
        not computable (owner ruling AC15 P2; finding r2-3). A numerator
        may be zero; a denominator may not, so this bar is the
        denominators' alone."""
        fault = measure_component_fault(fact_id)
        if fault:
            return fault
        if gate._decimal_or_none(facts_by_id[fact_id]["value"]) == 0:
            return "zero"
        return None

    # ---- the rating measure follows the archetype, and the cycle a
    #      single name depends on (owner ruling AC15, P2 and P4, U3e) ----
    # These two meaning changes bind a SINGLE NAME only - a basket, a
    # theme, a fund and an asset with no earnings carry none. The third
    # canonical test declares the subject's archetype and the rating
    # measure that archetype calls for; the measure must MATCH the
    # archetype (the table is data in floors.json), rest on the measure's
    # own numerator for the subject, be computable for every peer on the
    # shared numerator AND on each denominator the row names (or the peer
    # half a declared gap - a ratio is not computable from its numerator
    # alone), and never rate a business changing its model on the
    # trailing revenue of
    # the business it is exiting. A single name whose thesis rests on an
    # identifiable cycle carries dated series for it or declares the gap,
    # and a series is judged fresh against the class's own price rule.
    # This never asks whether the archetype is TRUE - no machine reads a
    # filing - only that the capture is self-consistent against the rule.
    archetype_data = floors.get("archetype_measures") or {}
    single_frame = frames.get(subject.get("ticker"))
    if (subject["kind"] == "single_stock" and single_frame
            and archetype_data):
        frame = single_frame
        table = archetype_data.get("table") or {}
        archetype = frame.get("archetype")
        entry = table.get(archetype) if archetype else None
        # Owner rulings AC28 and AC30 (architect ruling 1): an archetype
        # row that carries sub-types - the financial institution - is
        # resolved to the sub-type the frame names BEFORE anything reads
        # the row's measure, and everything below runs unchanged on the
        # resolved row. A missing or unknown sub-type is refused here.
        if entry is not None and entry.get("subtypes"):
            field = entry.get("subtype_field")
            subtype = frame.get(field)
            resolved = (entry["subtypes"].get(subtype)
                        if isinstance(subtype, str) else None)
            if resolved is None:
                refuse("the sub-type of the declared archetype",
                       "owner rulings AC28 and AC30: a '%s' is rated on the "
                       "measure of its own sub-type - one of %s - and the "
                       "frame %s, so neither the rating measure nor the "
                       "evidence minimums of the sub-type can be chosen"
                       % (archetype, ", ".join(sorted(entry["subtypes"])),
                          "names none" if subtype is None else
                          "names '%s', which is not one of them" % subtype),
                       "the '%s' field in the business frame" % field)
            entry = resolved
        rating = requirements_by_id.get("rating_vs_history_or_peers")
        measure = (rating or {}).get("measure")
        if not measure:
            refuse("the rating measure the third canonical test uses",
                   "owner ruling AC15 (P2): a single name's third "
                   "canonical test declares the rating measure its "
                   "archetype calls for, and this one names none - so "
                   "nothing binds the rating to the kind of business it is",
                   "the 'measure' field on the rating_vs_history_or_peers "
                   "row: one of the four the contract names")
        if entry is not None:
            if measure and measure != entry["measure"]:
                refuse("a rating measure that fits the declared archetype",
                       "owner ruling AC15 (P2): the frame calls this a "
                       "'%s', which is rated on '%s', but the third "
                       "canonical test declares '%s' - the rating basis "
                       "follows the kind of business, not a free choice"
                       % (archetype, entry["measure"], measure),
                       "either the archetype in the business frame or the "
                       "measure on the rating_vs_history_or_peers row, so "
                       "the two agree")
            if (entry.get("anchorless_only")
                    and not subjects.is_anchorless(subject)):
                refuse("an archetype legal for a priced single name",
                       "owner ruling AC15 (P2): '%s' keeps the anchorless "
                       "ladder and is legal only for an asset with no "
                       "earnings; this subject is a priced equity, rated "
                       "on one of the three earning archetypes" % archetype,
                       "the archetype in the business frame")
            numerator = entry.get("subject_numerator")
            if numerator and not entry.get("anchorless_only"):
                fault = measure_component_fault(numerator)
                if fault == "absent":
                    refuse("the rating measure's own numerator '%s'"
                           % numerator,
                           "owner ruling AC15 (P2): the '%s' measure rests "
                           "on '%s' for the subject, and the pack carries "
                           "no such fact - the measure cannot be struck at "
                           "all" % (entry["measure"], numerator),
                           "the subject's own market-data or filing facts")
                elif fault == "stale":
                    offender = stale_dependency(numerator)
                    record = freshness.get(offender, {})
                    refuse("the rating measure's own numerator '%s'"
                           % numerator,
                           "'%s' is present but stale - %s days old against "
                           "its %s-day rule - so the '%s' measure cannot be "
                           "struck from a reading the pack can trust"
                           % (offender, record.get("age_days"),
                              record.get("rule_days"), entry["measure"]),
                           "a fresher reading of '%s'" % offender)
                elif fault == "nan":
                    refuse("the rating measure's own numerator '%s'"
                           % numerator,
                           "owner ruling AC15 (P2): '%s' is present and "
                           "fresh but its value is not a number, so the "
                           "'%s' measure has no numerator to strike a ratio "
                           "from" % (numerator, entry["measure"]),
                           "a numeric reading of '%s' for the subject"
                           % numerator)
            # A ratio is computable only if BOTH halves are, on BOTH sides
            # (owner ruling AC15 P2; architect ruling 2026-09-20, closing
            # r1-1/r1-3). The measure's own denominators_required count is
            # data; the row names that many subject_denominator_facts, each
            # brought to the numerator's bar, and that many peer_denominator_
            # metrics (the peer half below). The subject side is never
            # lifted - only the peer half is, by a declared 'peer_' gap.
            required = entry.get("denominators_required")
            if required is not None and not entry.get("anchorless_only"):
                subject_denoms = ((rating or {}).get(
                    "subject_denominator_facts") or [])
                if len(subject_denoms) != required:
                    refuse("the subject-side denominators the rating measure "
                           "divides by",
                           "owner ruling AC15 (P2), architect ruling "
                           "2026-09-20: '%s' divides its numerator by %d "
                           "denominator(s) on the subject's own side, and the "
                           "row names %d - a ratio is not computable from its "
                           "numerator alone"
                           % (entry["measure"], required,
                              len(subject_denoms)),
                           "the 'subject_denominator_facts' list on the "
                           "rating_vs_history_or_peers row: exactly %d tier-1 "
                           "fact id(s)" % required)
                if len(set(subject_denoms)) != len(subject_denoms):
                    refuse("distinct subject-side denominators for the "
                           "rating measure",
                           "owner ruling AC15 (P2): the '%s' measure divides "
                           "its numerator by %d different denominator(s), and "
                           "the row names the same one more than once - one "
                           "denominator repeated is not the ratio the measure "
                           "needs" % (entry["measure"], required),
                           "%d distinct 'subject_denominator_facts' the "
                           "measure divides the numerator by" % required)
                for den in subject_denoms:
                    den_fault = denominator_fault(den)
                    if den_fault:
                        refuse("the rating measure's subject denominator '%s'"
                               % den,
                               "owner ruling AC15 (P2): the '%s' measure "
                               "divides the numerator by '%s' for the subject, "
                               "and '%s' %s - so the measure cannot be struck "
                               "for the subject, its numerator read alone"
                               % (entry["measure"], den, den,
                                  _FAULT_WORDS[den_fault]),
                               "a dated numeric reading of '%s' for the "
                               "subject" % den)
                # P-U3e-2 (architect ruling 2026-09-20): the data table's
                # own note fixes it - the subject's own denominators ARE
                # the frame's decisive metrics. A denominator no decisive
                # metric rests on can pass the count, the distinctness and
                # the numeric bar yet not be a number the rating turns on
                # (a cash rate standing in for contracted capacity), so it
                # is refused here, naming the fact and the measure. This
                # never reads whether a fact is TRULY contracted capacity;
                # it holds the capturer to his own decisive metrics, which
                # the evidence auditor and the owner see on the first page.
                decisive_ids = set()
                for metric_row in frame["decisive_metrics"]:
                    decisive_ids.update(metric_row.get("answered_by") or [])
                for den in subject_denoms:
                    if den not in decisive_ids:
                        refuse("a subject denominator that is one of the "
                               "frame's decisive metrics",
                               "owner ruling AC15 (P2), architect ruling "
                               "2026-09-20: the '%s' measure divides by '%s' "
                               "on the subject's side, but no decisive metric "
                               "in the business frame rests on '%s' - the "
                               "subject's own denominators ARE the frame's "
                               "decisive metrics, so a denominator no "
                               "decisive metric answers is not a number the "
                               "rating turns on" % (entry["measure"], den, den),
                               "either name '%s' in the 'answered_by' of a "
                               "decisive metric, or make the decisive metric "
                               "the '%s' measure divides by the subject "
                               "denominator" % (den, entry["measure"]))
            peer_metric = entry.get("peer_numerator_metric")
            if (peer_metric and not entry.get("anchorless_only")
                    and _PEER_GAP_CLASS not in gap_kinds):
                peers = frame.get("peers") or []
                # A ratio is not computable from its numerator alone
                # (owner ruling AC15 P2; architect ruling 2026-09-20).
                # With a real peer set and no declared peer gap, the
                # rating row names the peer-side denominator metric(s) the
                # measure divides by, and every peer carries the numerator
                # AND each named denominator under the peer_<metric>__
                # <ticker> convention - or the 'peer_' gap is declared,
                # which lifts the whole peer half exactly as it does for
                # the numerator today.
                denom_metrics = ((rating or {}).get(
                    "peer_denominator_metrics") or [])
                if peers and len(denom_metrics) != (required or 0):
                    refuse("the peer-side denominator the rating measure "
                           "divides by",
                           "owner ruling AC15 (P2), architect ruling "
                           "2026-09-20: '%s' divides its numerator by %d "
                           "denominator(s), and a ratio is not computable "
                           "from its numerator alone - the row names %d "
                           "peer-side denominator metric(s), so a peer "
                           "cannot be set beside the subject on the measure"
                           % (entry["measure"], (required or 0),
                              len(denom_metrics)),
                           "the 'peer_denominator_metrics' list on the "
                           "rating_vs_history_or_peers row: exactly %d "
                           "metric(s) the measure divides the numerator by"
                           % (required or 0))
                if peers and len(set(denom_metrics)) != len(denom_metrics):
                    refuse("distinct peer-side denominators for the rating "
                           "measure",
                           "owner ruling AC15 (P2): the '%s' measure divides "
                           "its numerator by %d different denominator(s), and "
                           "the row names the same peer metric more than once "
                           "- one denominator repeated is not the ratio the "
                           "measure needs" % (entry["measure"], (required or 0)),
                           "%d distinct 'peer_denominator_metrics'"
                           % (required or 0))
                for peer in peers:
                    slug = subjects.slug(peer["ticker"])
                    peer_id = "peer_%s__%s" % (peer_metric, slug)
                    fault = measure_component_fault(peer_id)
                    if fault:
                        refuse("the rating measure's numerator for peer %s"
                               % peer["ticker"],
                               "owner ruling AC15 (P2): the '%s' measure is "
                               "computable for the subject AND every peer, or "
                               "the peer half is a declared gap - and '%s' %s, "
                               "so this peer cannot be set beside the subject "
                               "on the measure at all"
                               % (entry["measure"], peer_id,
                                  _FAULT_WORDS[fault]),
                               "a dated numeric reading of '%s' for %s, or a "
                               "declared gap for the fact class '%s'"
                               % (peer_id, peer["ticker"], _PEER_GAP_CLASS))
                    for metric in denom_metrics:
                        den_id = "peer_%s__%s" % (metric, slug)
                        den_fault = denominator_fault(den_id)
                        if not den_fault:
                            continue
                        refuse("the rating measure's denominator '%s' for "
                               "peer %s" % (metric, peer["ticker"]),
                               "owner ruling AC15 (P2): the '%s' measure "
                               "divides the numerator by '%s', and '%s' %s - "
                               "so the measure cannot be struck for this peer, "
                               "its numerator read alone"
                               % (entry["measure"], metric, den_id,
                                  _FAULT_WORDS[den_fault]),
                               "a dated numeric reading of '%s' for %s, or a "
                               "declared gap for the fact class '%s'"
                               % (den_id, peer["ticker"], _PEER_GAP_CLASS))
        changing = (frame.get("what_is_changing") or {}).get("kind")
        if declared and declared[1] and entry is not None:
            decisive_ids = set()
            for metric_row in frame["decisive_metrics"]:
                decisive_ids.update(metric_row.get("answered_by") or [])
            for what, why, where in _fi_failures(
                    floors, declared, entry, frame, rating, changing,
                    gap_kinds, decisive_ids, facts_by_id):
                refuse(what, why, where)
            # Every figure the frame shows as the firm's capital, its cost
            # of risk or its second engine's share is read as the case
            # stands, so each fact those blocks cite is fresh - one fresh
            # member of a floor's family never vouches for another. A
            # holding's bridge needs no loop here: every part of it and the
            # holding company's net debt sit inside the net asset value's
            # chain (_nav_bridge_failures), and that value is the rating's
            # subject denominator, whose whole chain denominator_fault
            # already walks for staleness.
            capital = frame.get("fi_capital")
            capital = capital if isinstance(capital, dict) else {}
            risk_cost = frame.get("fi_risk_cost")
            risk_cost = risk_cost if isinstance(risk_cost, dict) else {}
            for block_words, cited in (
                    ("capital block",
                     list(capital.get("ratio_facts") or ())
                     + list(capital.get("requirement_facts") or ())
                     + [capital.get("target_fact")]),
                    ("cost of risk", list(risk_cost.get("facts") or ())),
                    ("secondary engine's share",
                     list(frame.get("fi_secondary_share_facts") or ()))):
                for fact_id in _dedupe(cited):
                    if (isinstance(fact_id, str) and fact_id in tier1_rules
                            and not fresh(fact_id)):
                        refuse("a fresh reading of '%s', which the frame's "
                               "%s cites" % (fact_id, block_words),
                               stale_words(fact_id),
                               "a fresher reading of '%s' from the source "
                               "that produced it"
                               % (stale_dependency(fact_id) or fact_id))
        forbidden = ((archetype_data.get("forbidden_on_model_transition")
                      or {}).get("trailing_revenue_fact_ids") or [])

        def rests_on_forbidden(fact_id):
            """The first forbidden trailing-revenue fact this rating fact
            rests on - itself or an operand, transitively - or None. A
            derived fact struck from the exited business's revenue is that
            revenue, however many operands deep (owner ruling AC15 P2; the
            same operand walk stale_dependency does)."""
            return _rests_on(fact_id, forbidden, facts_by_id)

        if changing == "model_transition" and rating:
            # The ban walks every fact the rating rests on, not only
            # answered_by: the measure's own numerator and each subject
            # denominator are rating components too (the round-1 fix added
            # subject_denominator_facts), and a forbidden trailing-revenue
            # fact placed in either escaped the answered_by-only walk
            # (finding r2-5).
            components = list(rating.get("answered_by") or [])
            components.extend(rating.get("subject_denominator_facts") or [])
            if entry:
                num = entry.get("subject_numerator")
                if num:
                    components.append(num)
            offenders = []
            for fid in components:
                hit = rests_on_forbidden(fid)
                if hit is not None and hit not in offenders:
                    offenders.append(hit)
            if offenders:
                refuse("a rating measure that is not the exited business's "
                       "trailing revenue",
                       "owner ruling AC15 (P2): this business is changing "
                       "its model, and the third canonical test rests on "
                       "%s - trailing revenue drawn from the business it is "
                       "exiting, which the ruling forbids because the "
                       "headline revenue is mostly the segment being closed"
                       % ", ".join("'%s'" % o for o in offenders),
                       "rate a model transition on what the NEW business "
                       "sells - contracted capacity and revenue per unit - "
                       "never the revenue of the business being exited")
        cycle_dep = frame.get("cycle_dependence")
        cycle = capture.get("cycle")
        if cycle_dep == "identified" and not cycle:
            refuse("the cycle series a single name depending on one carries",
                   "owner ruling AC15 (P4): the frame says this name's "
                   "thesis rests on an identifiable cycle, and the pack "
                   "carries no cycle block - three to five dated series for "
                   "it, or a declared gap with the reason",
                   "the top-level 'cycle' block: name the cycle, then carry "
                   "its dated series or declare why none is in hand")
        elif cycle_dep == "none" and cycle:
            refuse("agreement between the cycle declaration and the pack",
                   "owner ruling AC15 (P4): the frame says this name "
                   "depends on no identifiable cycle, yet the pack carries "
                   "a cycle block - one of the two is wrong",
                   "either declare cycle_dependence 'identified', or drop "
                   "the cycle block")
        if cycle and cycle.get("series"):
            multiple = ((archetype_data.get("cycle") or {})
                        .get("series_freshness_price_multiple"))
            price_days = None
            for floor_entry in class_config.get("floors") or []:
                if (floor_entry.get("id") == "price_last"
                        and floor_entry.get("max_freshness_days")):
                    price_days = floor_entry["max_freshness_days"]
                    break
            if multiple and price_days:
                ceiling = price_days * multiple
                sat = _as_of_moment(capture["captured_at"])
                for series in cycle["series"]:
                    series_moment = _as_of_moment(series["as_of"])
                    # Strict, and no clock-skew tolerance: as_of and the
                    # capture time are both written by the same capturer at
                    # capture, so a series after the capture is from the
                    # future exactly as the ordinary fact-date check reads
                    # it (gate._check_dates). A skew window let a series
                    # minutes after the capture through, its negative age
                    # read as fresh (finding r2-6).
                    if series_moment > sat:
                        refuse("a cycle series dated no later than the "
                               "capture '%s'" % series["id"],
                               "owner ruling AC15 (P4): '%s' is as-of %s, "
                               "later than the capture taken %s - a series "
                               "from the future is not a fresh reading, and "
                               "its negative age would otherwise pass the "
                               "freshness rule unseen"
                               % (series["id"], series["as_of"],
                                  capture["captured_at"]),
                               "a cycle series as-of at or before the capture "
                               "time")
                        continue
                    age = (sat - series_moment).days
                    if age > ceiling:
                        refuse("a fresh reading of the cycle series '%s'"
                               % series["id"],
                               "owner ruling AC15 (P4): a cycle series is "
                               "judged against the class's price-freshness "
                               "rule times %d - %d days - and '%s' is %d "
                               "days old, so the cycle the thesis rests on "
                               "is read from a series gone stale"
                               % (multiple, ceiling, series["id"], age),
                               "a fresher reading of '%s' from %s"
                               % (series["id"],
                                  series.get("refetch_url_or_source_line")))

    # ---- the outside auditor's findings (owner ruling AC2) ----
    # A second model read this evidence before any seat was paid, and
    # said what it thought was missing, wrong or misread. Every point it
    # raised is answered here - captured, declared a gap, or overruled
    # in the capture session's own words - before the council may sit.
    # An unanswered finding is the whole ruling undone: the call was
    # paid for, the answer was read, and nothing came of it. A call that
    # was never made undoes it more quietly still, which is why the
    # absence of the block refuses here as well.
    challenge = capture.get("evidence_challenge") or {}
    status = challenge.get("status")
    if status not in ("success", "failed"):
        refuse("the outside auditor's reading of the evidence",
               "the outside auditor has not checked the evidence and no "
               "failure is recorded - a call nobody made is neither a "
               "success nor a recorded failure, and no seat is paid "
               "until one of the two stands on the record",
               _UNCHECKED_LIKELY_SOURCE)
    else:
        # ---- the record points at an actual attempt (owner ruling
        # AC13.3, register item P-U2-5) ----
        # A block written by hand read exactly like one the bridge
        # wrote, and it reaches nine seat prompts and the owner's page
        # as the word of a model outside this family. Nothing can PROVE
        # a paid call happened - the capture session writes every file
        # in that folder - so this raises the cost of inventing one: the
        # block must carry the one-time token the bridge issued for the
        # call and the hash of the evidence it sent. Recorded as a
        # cost-raiser, in the owner's own words, and not as a proof.
        for field, words in (
                ("nonce", "the one-time token this council's own bridge "
                          "issues for each call"),
                ("evidence_sha256", "the hash of the evidence the "
                                    "auditor was sent")):
            if str(challenge.get(field) or "").strip():
                continue
            refuse("the outside auditor's reading of the evidence",
                   "the record of the audit carries no %s, so nothing "
                   "ties it to a call this council made - and the seats "
                   "and the owner's page are told an outside model read "
                   "these figures. The bridge writes both into its own "
                   "result and 'evidence-record' copies them across; a "
                   "block that carries neither was written by hand"
                   % words,
                   _UNCHECKED_LIKELY_SOURCE)
        # ---- what moved after the auditor read it (owner ruling
        # AC13.2, register item P-U2-4) ----
        # The capture MAY change what the auditor never asked about; the
        # rule is that every such change is LISTED, so the seats and the
        # owner see which figures the outside model did not read. This
        # is where an unlisted change stops the sitting: the recorded
        # hash is of the evidence as sent, and the pack's own hash is of
        # the evidence the council would sit on.
        sent = str(challenge.get("evidence_sha256") or "").strip()
        listed = str(challenge.get("post_audit_sha256") or "").strip()
        changes = challenge.get("post_audit_changes")
        body = gate.evidence_body_sha256(capture)
        if sent and body != sent and not changes:
            refuse("a list of what changed after the outside auditor read "
                   "the evidence",
                   "the evidence moved between the audit and this pack, "
                   "and nothing on the record says what moved: the "
                   "auditor was sent %s and the council would sit on %s. "
                   "A figure no outside model read would reach every seat "
                   "and the owner's page under a record saying one did"
                   % (sent, body),
                   _CHANGES_LIKELY_SOURCE)
        elif sent and body != sent and listed != body:
            # The list is written FOR one reading of the evidence, and
            # says nothing about any other. A capture edited after the
            # recording leaves the list standing and non-empty, so the
            # test above passes it - and the figure changed since is on
            # no record at all (audit round 1, r1-3).
            refuse("a list written for the evidence the council would "
                   "sit on",
                   "the record lists %d change(s) after the audit and it "
                   "was written for other evidence than this: the list "
                   "was made for %s and the council would sit on %s, so "
                   "whatever moved since it was written is on no record "
                   "at all. Nothing needs putting back - record the audit "
                   "again over the pack you mean to sit on, and the list "
                   "is written afresh for it"
                   % (len(changes), listed or "nothing", body),
                   _CHANGES_LIKELY_SOURCE)
    if status == "success":
        resolutions = challenge.get("resolutions") or {}
        for finding in challenge.get("findings") or []:
            finding_id = finding.get("id")
            resolution = resolutions.get(finding_id)
            if not resolution or not resolution.get("disposition"):
                refuse("an answer to the outside auditor's finding '%s'"
                       % finding_id,
                       "the outside auditor raised it before any seat was "
                       "paid (%s, %s) and the record answers it nowhere: "
                       "%s"
                       % (finding.get("kind"), finding.get("severity"),
                          finding.get("detail")),
                       _RESOLUTION_LIKELY_SOURCE)
                continue
            if resolution.get("disposition") == "gap_declared":
                # The same sentence of section U2.3 that fixes an
                # overrule at twenty-five words defines this answer as
                # `gap_declared (reason, weakened test)`. A disposition
                # word with neither of its two parts is the shape of an
                # answer and not an answer (audit round 1, r1-4).
                for field, words in (("reason", "a reason"),
                                     ("weakened_test",
                                      "the test it weakens")):
                    if str(resolution.get(field) or "").strip():
                        continue
                    refuse("the gap the record declares against the "
                           "outside auditor's %s finding '%s'"
                           % (finding.get("severity"), finding_id),
                           "a declared gap names %s and this one names no "
                           "%s: an absence nobody explains is not an "
                           "answer to the point that was raised - %s"
                           % (words, field.replace("_", " "),
                              finding.get("detail")),
                           _RESOLUTION_LIKELY_SOURCE)
                continue
            if resolution.get("disposition") != "overruled":
                continue
            words = len(str(resolution.get("reason") or "").split())
            if words < _OVERRULE_WORDS:
                refuse("a reason for overruling the outside auditor's "
                       "%s finding '%s'"
                       % (finding.get("severity"), finding_id),
                       "the council may set the auditor's point aside, "
                       "but only in its own words - and the record does "
                       "it in %d word(s) where at least %d are required: "
                       "%s"
                       % (words, _OVERRULE_WORDS, finding.get("detail")),
                       _RESOLUTION_LIKELY_SOURCE)

    # ---- a rebuilding correction must be re-audited (owner ruling AC15,
    # P8) ----
    # A user correction that only narrows a claim goes to no auditor; one
    # that rebuilds what the seats reason from - a fact the frame's
    # reading rests on, a headline pair - goes back as a delta before the
    # council sits, because the act of fixing can create a fresh error the
    # seats would otherwise never see (the debrief's $409m case). The
    # correction command records which it is; the delta re-audit clears
    # it. An un-re-audited rebuilding correction stops here.
    for correction in capture.get("corrections") or []:
        if (correction.get("classification") == "rebuilding"
                and not correction.get("reaudited")):
            refuse("a delta re-audit of the correction to '%s'"
                   % correction.get("fact_id"),
                   "'%s' was corrected after the outside auditor read the "
                   "evidence, and it is a figure the seats reason from, so "
                   "the correction rebuilds the case rather than narrowing "
                   "it - and no outside model has seen the change. A fix "
                   "can create a fresh error the seats would never catch"
                   % correction.get("fact_id"),
                   _REBUILDING_LIKELY_SOURCE)

    # ------- per-kind enforcement (THEMES-BASKETS-SPEC section 4) -------

    def member_core(ticker, member_words):
        """The essential core every named expression member carries: its
        own last price (on the ruled 3-day ceiling) and market value,
        id-suffixed with the member's slug. A declared gap never lifts
        these - the core is essential."""
        likely = ("a dated market-data page or the broker's quote page "
                  "for %s" % ticker)
        for concept in subjects.PER_EXPRESSION_CORE:
            fact_id = "%s__%s" % (concept, subjects.slug(ticker))
            if fact_id not in tier1_rules:
                refuse(fact_id,
                       "the essential core for %s: every named member of "
                       "the expression carries its own last price and "
                       "market value, and this one is not in the pack"
                       % member_words,
                       likely)
                continue
            if not fresh(fact_id):
                refuse(fact_id, stale_words(fact_id),
                       "a fresher reading of '%s' from the source that "
                       "produced it" % fact_id)
            else:
                satisfied.append(fact_id)
            if (concept == "price_last"
                    and tier1_rules[fact_id] > _MEMBER_PRICE_CEILING_DAYS):
                refuse(fact_id,
                       "the ruled freshness for this fact is at most %d "
                       "day(s), but the capture declares a %d-day rule - "
                       "too loose to trust at a sitting (what %s costs "
                       "at the sitting)"
                       % (_MEMBER_PRICE_CEILING_DAYS,
                          tier1_rules[fact_id], member_words),
                       likely)

    def essential_metrics(ticker):
        """Exactly one ANSWERED constituent_essential checklist row per
        named constituent - the one or two metrics the thesis load-bears
        on for that name. A declared gap does not lift it."""
        rows = [r for r in requirements
                if r["kind"] == "constituent_essential"
                and r.get("constituent") == ticker]
        answered = [r for r in rows if r["status"] == "answered"]
        if len(answered) == 1:
            # Audit finding THEMES-A r5-1: the row's facts must be the
            # constituent's OWN. A fact carrying another member's
            # suffix (or none) satisfied the row while the named
            # constituent's load-bearing metric went unmeasured, so
            # every fact the row rests on must be a tier1 fact
            # carrying this constituent's id suffix - the same
            # <concept>__<slug> form its price and market value carry.
            suffix = "__%s" % subjects.slug(ticker)
            for fact_id in answered[0]["answered_by"]:
                if fact_id in tier1_rules and fact_id.endswith(suffix):
                    continue
                refuse("the load-bearing metric bound to constituent "
                       "%s" % ticker,
                       "the constituent_essential row '%s' rests on "
                       "'%s', which is not a tier1 fact carrying %s's "
                       "own id suffix '%s' - the metrics the thesis "
                       "load-bears on for a constituent must be that "
                       "constituent's own frozen figures"
                       % (answered[0]["id"], fact_id, ticker, suffix),
                       "a tier1 fact for %s whose id ends in '%s', "
                       "the same suffix its price and market value "
                       "carry" % (ticker, suffix))
            return
        what = "a constituent_essential requirement for %s" % ticker
        if not rows:
            why = ("the pack's checklist carries no constituent_"
                   "essential row for constituent %s - the one or two "
                   "metrics the thesis load-bears on for that name are "
                   "essential" % ticker)
        elif not answered:
            why = ("the constituent_essential row for constituent %s is "
                   "declared a gap - the core is essential, and a "
                   "declared gap does not lift it" % ticker)
        else:
            why = ("the pack's checklist carries %d answered "
                   "constituent_essential rows for constituent %s - "
                   "exactly one per constituent is the contract"
                   % (len(answered), ticker))
        refuse(what, why,
               "the capture's own checklist: one constituent_essential "
               "row for %s, answered by the facts the thesis load-bears "
               "on for that name" % ticker)

    def falsifier_shapes(theme, via_vehicle):
        """The shape of meaning per declared falsifier: a level is
        scored against a frozen tier1 fact WITH its prior period
        visible (W8.2); an event or date is grounded in the pack. Stale
        referenced facts refuse in the standard freshness words."""
        via = ("; this vehicle wraps a theme, and the seats judge the "
               "theme through the vehicle" if via_vehicle else "")
        for falsifier in theme["falsifiers"]:
            falsifier_id = falsifier["id"]
            fact_id = falsifier["fact_id"]
            prior_id = falsifier["prior_fact_id"]
            if falsifier["kind"] == "level":
                if fact_id is None or fact_id not in tier1_rules:
                    refuse("a fact that could prove the theme wrong",
                           "falsifier '%s' is a level but is not scored "
                           "against a frozen tier1 fact - a falsifier "
                           "that cannot fire is not a falsifier%s"
                           % (falsifier_id, via),
                           "a dated tier1 fact carrying the level, "
                           "named by the falsifier's fact_id")
                elif not fresh(fact_id):
                    refuse(fact_id, stale_words(fact_id),
                           "a fresher reading of '%s' from the source "
                           "that produced it" % fact_id)
                if prior_id is None or prior_id not in tier1_rules:
                    refuse("the prior period beside the level",
                           "falsifier '%s' is a level and its prior "
                           "period is not visible in the pack - without "
                           "the earlier reading, a deterioration cannot "
                           "be seen (W8.2)%s" % (falsifier_id, via),
                           "the prior-period reading of the same "
                           "figure, frozen as its own tier1 fact and "
                           "named by prior_fact_id")
                elif not fresh(prior_id):
                    refuse(prior_id, stale_words(prior_id),
                           "a fresher reading of '%s' from the source "
                           "that produced it" % prior_id)
                if (fact_id is not None and fact_id in tier1_rules
                        and prior_id is not None
                        and prior_id in tier1_rules):
                    # Audit finding THEMES-A r1-3: a prior period that
                    # is not dated earlier than its level is the same
                    # observation wearing two ids.
                    level_dated = facts_by_id[fact_id]["as_of"]
                    prior_dated = facts_by_id[prior_id]["as_of"]
                    if (_as_of_moment(prior_dated)
                            >= _as_of_moment(level_dated)):
                        refuse("the prior period beside the level",
                               "falsifier '%s' names '%s' (dated %s) "
                               "as the prior period beside '%s' (dated "
                               "%s) - a reading not dated strictly "
                               "earlier than its level is not a prior "
                               "period (W8.2)%s"
                               % (falsifier_id, prior_id, prior_dated,
                                  fact_id, level_dated, via),
                               "the genuinely earlier reading of the "
                               "same figure, frozen as its own tier1 "
                               "fact with its own date")
                    # Audit finding THEMES-A r5-2, mechanical half:
                    # the W8.6 baseline reads the prior period in the
                    # SAME UNIT as its level. Whether the two facts
                    # measure the same METRIC beyond that is the
                    # owner's DEFERRED question (OWNER-RULINGS W8.6,
                    # register entry REG-18) and is deliberately NOT
                    # decided here - the first real theme sitting
                    # surfaces the concrete case to the owner.
                    level_unit = facts_by_id[fact_id]["unit"]
                    prior_unit = facts_by_id[prior_id]["unit"]
                    if prior_unit != level_unit:
                        refuse("the prior period beside the level",
                               "falsifier '%s' names '%s' (measured "
                               "in %s) as the prior period beside "
                               "'%s' (measured in %s) - a prior "
                               "period is the same figure read "
                               "earlier, and a reading in a different "
                               "unit cannot be one (W8.2)%s"
                               % (falsifier_id, prior_id, prior_unit,
                                  fact_id, level_unit, via),
                               "the genuinely earlier reading of the "
                               "same figure, in the same unit, frozen "
                               "as its own tier1 fact")
            else:
                if fact_id is None or (fact_id not in tier1_rules
                                       and fact_id not in tier2_ids):
                    refuse("a fact that could prove the theme wrong",
                           "falsifier '%s' names no fact in the pack to "
                           "score it against - a measurable falsifier "
                           "is grounded in the pack%s"
                           % (falsifier_id, via),
                           "a dated tier1 fact or tier2 passage the "
                           "falsifier is scored against, named by its "
                           "fact_id")
                elif fact_id in tier1_rules and not fresh(fact_id):
                    refuse(fact_id, stale_words(fact_id),
                           "a fresher reading of '%s' from the source "
                           "that produced it" % fact_id)

    kind = subject["kind"]
    if kind == "basket":
        for ticker in subjects.constituent_tickers(subject):
            member_core(ticker, "constituent %s" % ticker)
            essential_metrics(ticker)
    elif kind == "theme":
        # The ruled shopping-list refusal comes FIRST: the note is the
        # product - it states what would make the question sittable, at
        # capture cost, before any seat is paid.
        theme = subjects.theme_block(subject)
        vehicle = subject.get("vehicle")
        if not subjects.has_constituents(subject) and not vehicle:
            refuse("an investable expression - names or a vehicle",
                   "the theme names no investable expression: neither a "
                   "provisional universe of 2 to 8 named instruments "
                   "nor one implementation vehicle - and a theme with "
                   "no names attached must never earn conviction on "
                   "zero verifiable facts (W2.9)",
                   "the owner's or the evidence session's own naming: 2 "
                   "to 8 named instruments, or the one vehicle that "
                   "implements the theme - the council judges named "
                   "candidates and never invents them")
        if theme is None:
            refuse("a fact that could prove the theme wrong",
                   "the capture declares no theme block, so no "
                   "measurable falsifier exists - a thesis nothing "
                   "could contradict cannot be sat honestly",
                   "the subject's theme block: the thesis in one line "
                   "and at least one measurable falsifier, with the "
                   "prior period beside it where the falsifier is a "
                   "level")
        else:
            falsifier_shapes(theme, False)
        if subjects.has_constituents(subject):
            for ticker in subjects.constituent_tickers(subject):
                member_core(ticker, "constituent %s" % ticker)
                essential_metrics(ticker)
        elif vehicle:
            member_core(vehicle["ticker"],
                        "the named vehicle %s" % vehicle["ticker"])
    elif kind == "etf":
        theme = subjects.theme_block(subject)
        if theme is not None:
            falsifier_shapes(theme, True)

    result = "refuse" if missing else "pass"
    floors_out = {"satisfied": _dedupe(satisfied),
                  "lifted_by_declared_gap": _dedupe(lifted_by_declared_gap),
                  "advisory_missing": _dedupe(advisory_missing)}
    message = _compose_message(result, _subject_label(subject),
                               floors_out, len(requirements), missing,
                               _class_note(floors, subject))
    return {"result": result,
            "asset_class": subjects.asset_class(subject),
            "floors": floors_out,
            "requirements_checked": len(requirements),
            "missing": missing,
            "message": message}


def _class_note(floors, subject):
    """One plain sentence naming the anchor set this subject was judged
    against - and, for a commodity whose product has no registry entry
    of its own, saying so rather than letting the template pass for a
    complete answer (ANCHORLESS-SPEC section 8: further products return
    to the owner when charged)."""
    name = subjects.asset_class(subject)
    if not subjects.is_anchorless(subject):
        return None
    note = ("Judged as %s: an asset with no earnings, so its own anchor "
            "set stands in for the four earnings tests." % name)
    named = subjects.product(subject)
    if name != "commodity" or not named:
        return note
    entry = subjects.class_registry(floors, subject) or {}
    if named in (entry.get("products") or {}):
        return note + (" Product: %s, with its own ruled items." % named)
    # Ruled C2: this case refuses, and the refusal says what would make
    # it sittable - so the note names the product and leaves the reason
    # to the missing item beside it.
    return note + (" Product: %s - the owner has ruled no evidence items "
                   "for it." % named)


def _compose_message(result, label, floors_out, requirement_count,
                     missing, class_note=None):
    lines = []
    if result == "pass":
        lines.append("The evidence is sufficient to convene the "
                     "council on %s." % label)
        if class_note:
            lines.append(class_note)
        lines.append("%d must-have item(s) present; %d requirement(s) "
                     "on the pack's checklist, every one answered or "
                     "covered by a declared reason."
                     % (len(floors_out["satisfied"]), requirement_count))
        if floors_out["lifted_by_declared_gap"]:
            lines.append("Absences declared with a reason (accepted): "
                         "%s." % ", ".join(
                             floors_out["lifted_by_declared_gap"]))
        if floors_out["advisory_missing"]:
            lines.append("Advisory items missing or stale (noted, never "
                         "blocking; each says which it is): %s."
                         % ", ".join(floors_out["advisory_missing"]))
        return "\n".join(lines)
    lines.append("Not enough evidence to convene the council on %s."
                 % label)
    if class_note:
        lines.append(class_note)
    lines.append("%d item(s) stand in the way; no seat is paid until "
                 "they are in the pack:" % len(missing))
    for item in missing:
        lines.append("- Missing: %s" % item["what"])
        lines.append("  Why it matters: %s" % item["why_needed"])
        lines.append("  Where it likely lives: %s"
                     % item["where_it_likely_lives"])
    lines.append("Gather the items above and capture again - the "
                 "question cannot be answered honestly without them.")
    return "\n".join(lines)


_USAGE = ("usage: python -m council.evidence.sufficiency <pack.json> "
          "[--floors <floors.json>] [--out <sufficiency-result.json>]")


def _take_option(args, name):
    if name not in args:
        return None
    index = args.index(name)
    if index + 1 >= len(args):
        raise ValueError("%s needs a value" % name)
    value = args[index + 1]
    del args[index:index + 2]
    return value


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        floors_path = _take_option(args, "--floors")
        out_path = _take_option(args, "--out")
        if len(args) != 1:
            print(_USAGE)
            return 1
        pack = canonical.read_json(args[0])
        floors = canonical.read_json(floors_path or _DEFAULT_FLOORS_PATH)
        outcome = check(pack, floors)
        if out_path:
            canonical.write_canonical_json(out_path, outcome)
        print(outcome["message"])
        return 0 if outcome["result"] == "pass" else 3
    except Exception as exc:
        print("sufficiency check crashed: %r" % (exc,))
        return 1


if __name__ == "__main__":
    sys.exit(main())
