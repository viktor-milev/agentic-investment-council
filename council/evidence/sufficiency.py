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

import decimal
import os
import sys
import math
import re
from datetime import date, datetime

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
# The financial institution's own rules (capital, cost of risk, families,
# the bridge, its exited-business ban) are its alone: they run only where
# the declared archetype is this one, whatever other archetype the table
# splits into sub-types (unit GROWTH-ARCHETYPE, D1; the gate's spelling).
_FI_ARCHETYPE = "financial_institution"
# The growth company (owner rulings AC49(1) and AC50; the gate's spelling):
# its months of cash left, its standard tests and its rule are its alone.
_GROWER_ARCHETYPE = "reinvesting_grower"
# Architect ruling A10 under owner ruling AC50(5): the latest quarter's
# revenue and the same quarter a year earlier - the growth the yardstick is
# read beside - always decide a growth company's case.
_GROWER_GROWTH_PAIR = ("revenue_q", "revenue_prior_year_q")

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


def _shape_fault(part, fact, captured_at, window_days, zero_ok=False):
    """Why a floor's part does not have the shape and unit the floors
    data names for it, or None (unit U4(d): round 2 Step 0, P-U4d-3 and
    P-U4d-4, the parts of an examination must be real parts; round 3
    Step 0, P-U4d-5, the unit is part of the shape). Truth is not
    checked here - only that the part could be what it claims to be.
    zero_ok admits a positive_number of exactly zero. The value is read
    exactly as stored, nothing stripped (round 5 Step 0, P-U4d-8).

    Unit INSIDER-DEPTH adds the insider summary's two shapes - a whole
    number above zero, and buy, sell or even - each dated not after the
    capture like a positive number, and the financial-year end's shape,
    a month and day written MM-DD (owner ruling AC46(2))."""
    name, shape = part["part"], part["shape"]
    value = str(fact.get("value"))
    captured = _as_of_moment(captured_at)
    if shape in ("positive_whole_number", "buy_sell_or_even"):
        if shape == "positive_whole_number" and not re.fullmatch(
                r"[1-9][0-9]*", value):
            return "%s must be a whole number above zero, not '%s'" % (
                name, value)
        if shape == "buy_sell_or_even" and value not in ("buy", "sell",
                                                         "even"):
            return "%s must be buy, sell or even, not '%s'" % (name, value)
        if _as_of_moment(str(fact.get("as_of"))) > captured:
            return "%s is dated %s, after the capture" % (name,
                                                         fact.get("as_of"))
    elif shape == "month_day":
        try:
            if not re.fullmatch(r"[0-9]{2}-[0-9]{2}", value):
                raise ValueError(value)
            # A leap year, so the last day of February is a month and day.
            date.fromisoformat("2000-" + value)
        except ValueError:
            return "%s must be a month and day written MM-DD, not '%s'" % (
                name, value)
    elif shape == "buy_or_sell":
        if value not in ("buy", "sell"):
            return "%s must be buy or sell, not '%s'" % (name, value)
    elif shape == "trade_date":
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                raise ValueError(value)
            day = date.fromisoformat(value)
        except ValueError:
            return "%s must be an ISO date, not '%s'" % (name, value)
        if day > captured.date():
            return "dated %s, after the capture" % value
        if (captured.date() - day).days > window_days:
            return "dated %s, more than a year before the capture" % value
    elif shape == "positive_number":
        try:
            if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", value):
                raise ValueError(value)
            number = float(value)
        except ValueError:
            number = float("nan")
        if not (math.isfinite(number)
                and (number > 0 or (zero_ok and number == 0))):
            return "%s must be a positive number, not '%s'" % (name, value)
        if _as_of_moment(str(fact.get("as_of"))) > captured:
            return "%s is dated %s, after the capture" % (name,
                                                         fact.get("as_of"))
    else:
        raise ValueError(
            "the floors file names a part shape %r this gate cannot "
            "check, so the floors file must be fixed before any pack "
            "is judged against it" % shape)
    if fact.get("unit") not in part["units"]:
        return "%s in %s, must be %s" % (name, fact.get("unit"),
                                         part["units_mean"])
    return None


# Owner ruling AC47(3), in the architect's words: where what officers and
# directors own cannot be established from the record, the council rules
# without the insider evidence and the owner's pages and the seats' case
# file say so, once each, in this sentence.
INSIDER_NOT_CONSIDERED = ("Insider information was not available and was "
                          "not considered in the council's ruling: what the "
                          "company's officers and directors own could not "
                          "be established from the record.")

_EXACT_NUMBER = re.compile(r"[0-9]+(\.[0-9]+)?")


def holder_structure(pack, depth):
    """The holder-structure test (owner ruling AC41(1), as amended of
    record; AC47; the architect's round-3 reading, which replaced the
    patched one whole): ("light" | "full" | "not_considered", the holding
    in words or None), read from the pack against the floors' `depth`
    block, with exact decimals and no division.

    Every fresh deciding figure is read as a range: an exact figure is a
    point, a ceiling-bound one ("less than") runs from zero up to but not
    including the figure, a floor-bound one ("at least") from the figure,
    included, upward (the architect's round-4 reading of the edges). The
    holding's range is the ownership percentage's, where a percentage is
    recorded in a percent unit; where not, the group's shares over the
    shares in issue: its low is the group's low over the largest
    shares-in-issue high, its high the group's high over the smallest
    shares-in-issue low, every fresh shares-in-issue figure in the
    group's unit taking part. The depth is light only when the whole
    range lies under the threshold - so a ceiling at the threshold reads
    light, and an exact figure or a floor at it reads full - and full when
    any part of it reaches or exceeds the threshold. The holding in words
    names each figure with its own bound word - "less than" for a
    ceiling, "at least" for a floor, the bare figure where exact - and
    every distinct shares-in-issue figure taking part (the architect's
    round-5 ruling). Where no figure decides and the percentage
    is declared absent by design, the ownership cannot be established and
    the insider evidence is not considered (AC47(3)); otherwise the safe
    side, every dealing."""
    capture = pack["capture"]
    freshness = pack.get("freshness") or {}
    facts = {fact["id"]: fact for fact in capture["tier1"]}
    threshold = decimal.Decimal(depth["threshold_pct"])
    stale = {fact_id for fact_id in facts if (freshness.get(fact_id) or {})
             .get("status") != "within_rule"}

    def span(fact_id):
        """(low, high, the fact) for a fresh exact figure, the high None
        where the figure has no upper end; (None, None, None) where the
        figure is missing, not a number, or stale itself or through any
        fact it is derived from (audit round 5, r5-1)."""
        fact = facts.get(fact_id)
        if (fact is None or _rests_on(fact_id, stale, facts) is not None
                or not _EXACT_NUMBER.fullmatch(str(fact.get("value")))):
            return None, None, None
        value = decimal.Decimal(str(fact["value"]))
        kind = (fact.get("bound") or {}).get("kind")
        if kind == "ceiling":
            return decimal.Decimal(0), value, fact
        if kind == "floor":
            return value, None, fact
        return value, value, fact

    def under(high, fact, limit):
        """True where a range whose top is `high` lies wholly under
        `limit`: a ceiling's top is strictly under its figure, so it may
        sit at the limit; an exact or floor figure's top is the figure."""
        if high is None:
            return False
        if (fact.get("bound") or {}).get("kind") == "ceiling":
            return high <= limit
        return high < limit

    low, high, fact = span(depth["ownership_id"])
    if fact is not None and fact.get("unit") in depth["ownership_units"]:
        kind = (fact.get("bound") or {}).get("kind")
        said = {"ceiling": "less than ", "floor": "at least "}.get(
            kind, "") + "%s%% of the company" % fact["value"]
        light = under(high, fact, threshold)
        return ("light" if light else "full"), said
    group_low, group_high, group_fact = span(depth["group_shares_id"])
    issued = []
    if group_fact is not None:
        for issue_id in depth["shares_in_issue_ids"]:
            issue_low, issue_high, issued_fact = span(issue_id)
            if (issued_fact is not None and issued_fact.get("unit")
                    == group_fact.get("unit")):
                issued.append((issue_low, issue_high, issued_fact))
    if issued:
        fewest = min(issue_low for issue_low, _, _ in issued)
        unit = str(group_fact.get("unit")).replace("_", " ")

        def worded(fact, bare=""):
            """The figure with its own bound word, never another's."""
            return {"ceiling": "less than ", "floor": "at least "}.get(
                (fact.get("bound") or {}).get("kind"), bare) + format(
                decimal.Decimal(str(fact["value"])), ",")

        counts = []
        for _, _, issued_fact in issued:
            count = worded(issued_fact, "the ")
            if count not in counts:
                counts.append(count)
        said = "%s of %s %s in issue" % (worded(group_fact),
                                         " or ".join(counts), unit)
        top = group_high is not None and fewest > 0
        light = top and under(group_high * 100, group_fact,
                              threshold * fewest)
        return ("light" if light else "full"), said
    declared = [gap.get("reason_kind") for gap in capture["gaps"]
                if gap.get("fact_class") == depth["ownership_id"]]
    if (depth["ownership_id"] not in facts and declared
            and all(kind == "absent_by_design" for kind in declared)):
        return "not_considered", None
    return "full", None


def insider_depth(pack, floors):
    """What the insider floor reads for this pack, for the pages that
    print it: None where no floor of the subject carries a `depth` block,
    else {"depth", "holding", "threshold", "summary", "officer_roles",
    "not_considered"} - the last True only where the evidence is not
    considered AND the pack carries no insider fact, so the sentence
    above is never printed beside insider figures."""
    capture = pack["capture"]
    entry = next((entry for entry in _merged_floors(
        floors, capture["subject"], capture) if entry.get("depth")), None)
    if entry is None:
        return None
    depth = entry["depth"]
    state, holding = holder_structure(pack, depth)
    return {"depth": state, "holding": holding,
            "threshold": depth["threshold_pct"],
            "summary": list(depth["summary"]),
            "officer_roles": list(depth["officer_roles"]),
            "not_considered": state == "not_considered" and not any(
                str(fact.get("id")).startswith(depth["family"])
                for fact in capture["tier1"])}


def _subject_label(subject):
    if subject.get("ticker"):
        return "%s (%s)" % (subject["name"], subject["ticker"])
    return subject["name"]


def _declared_archetype(floors, capture):
    """(the archetype, the sub-type) where a single name's frame declares
    any row of the floors' archetype table, or None. The sub-type is None
    for a flat row, and for a row in sub-types (the financial institution,
    owner rulings AC28 and AC30; the grower, AC49) where the frame names
    none or one the row does not know - the archetype block of check()
    refuses that in plain words. The one reading of the declaration: the
    merged floors, the lifts and the brief's floors block all start here
    (unit GROWTH-ARCHETYPE, D1)."""
    subject = capture["subject"]
    if subject["kind"] != "single_stock":
        return None
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    archetype = frame.get("archetype") if isinstance(frame, dict) else None
    row = (((floors.get("archetype_measures") or {}).get("table") or {})
           .get(archetype) if isinstance(archetype, str) else None)
    if not isinstance(row, dict):
        return None
    subtype = None
    if row.get("subtypes"):
        subtype = frame.get(row.get("subtype_field"))
        if not isinstance(subtype, str) or subtype not in row["subtypes"]:
            subtype = None
    return archetype, subtype


def _archetype_floor_entries(floors, declared):
    """The floors the declared archetype carries on top of its class:
    what every sub-type carries, then what its own sub-type carries. A
    flat row's block is read by the same key, all_subtypes, so one
    reading serves both (owner rulings AC28, AC30 and AC49)."""
    if not declared:
        return []
    block = (floors.get("archetype_floors") or {}).get(declared[0]) or {}
    entries = list(block.get("all_subtypes") or [])
    if declared[1]:
        entries += list(block.get(declared[1]) or [])
    return entries


def _archetype_lifts(floors, declared):
    """The lifts block (owner ruling AC30(1), G1) where it applies to
    the declared sub-type, else an empty dict."""
    if not declared:
        return {}
    lifts = (((floors.get("archetype_floors") or {}).get(declared[0]) or {})
             .get("lifts") or {})
    return lifts if ("subtypes" not in lifts or declared[1] in lifts["subtypes"]) else {}


def _merged_floors(floors, subject, capture=None):
    entries = list(floors["classes"][subject["kind"]]["floors"])
    declared = _declared_archetype(floors, capture) if capture else None
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
    # Owner rulings AC28, AC30 and AC49: the third source, merged on top
    # of the class and the name - what every business of the declared
    # archetype carries, then what its own sub-type carries.
    entries += _archetype_floor_entries(floors, declared)
    return entries


def _rests_on(fact_id, targets, facts_by_id, seen=None, stop_suffix=""):
    """The first fact of `targets` this one rests on - itself or an
    operand, transitively - or None. Operands without a fact reference
    are inline constants and rest on nothing. Where `stop_suffix` is
    given, a fact whose id ends in it rests on nothing: the walk stops
    there, and neither it nor its operands are read."""
    if seen is None:
        seen = set()
    if fact_id in seen:
        return None
    seen.add(fact_id)
    if stop_suffix and fact_id.endswith(stop_suffix):
        return None
    if fact_id in targets:
        return fact_id
    derived = (facts_by_id.get(fact_id) or {}).get("derived")
    if derived:
        for operand in derived.get("operands") or ():
            reference = operand.get("fact_id")
            if reference is not None and reference in facts_by_id:
                hit = _rests_on(reference, targets, facts_by_id, seen,
                                stop_suffix)
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


def _nav_bridge_failures(frame, rating, facts_by_id,
                         ruling="owner rulings AC28 and AC30 (G3)",
                         who="a financial holding", floors=None, tagged=None, pairs=None,
                         holding_context=None):
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
        failures = [(
            "the bridge %s's net asset value is struck through" % who,
            (ruling + ": %s is rated " % who
             + "on its discount to what it owns at today's prices, and this "
            "frame names no nav_bridge, so nothing shows what that value "
            "is made of"),
            "the business frame's nav_bridge: each holding with its value "
            "fact, the holding company's net debt and the total")]
        return failures
    failures = []
    total = bridge.get("nav_total_fact")
    denominators = (rating or {}).get("subject_denominator_facts") or []
    if denominators != [total]:
        failures.append((
            "the net asset value the rating divides by, struck through the "
            "bridge",
            ruling + ": %s is rated "
            "on its discount to what it owns at today's prices, so the one "
            "figure the rating divides by is the total its bridge strikes - "
            "the rating names %s and the bridge's total is '%s'"
            % (who, ", ".join("'%s'" % fid for fid in denominators) or "nothing",
               total),
            "the rating_vs_history_or_peers row: 'subject_denominator_facts' "
            "naming the nav_bridge's nav_total_fact alone"))
    if not (facts_by_id.get(total) or {}).get("derived"):
        failures.append((
            "a net asset value struck from its parts",
            ruling + ": '%s' carries no arithmetic - "
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
                ruling + ": the bridge names %s, and "
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
                ruling + ": the net asset value is "
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
                ruling + ": followed down, '%s' "
                "rests on %r - a number written into the capture, resting "
                "on no captured reading at all. The arithmetic would "
                "recompute exactly and still show nothing" % (holder, label),
                "capture the figure itself as a fact, dated and sourced, "
                "and strike the total from it"))
    if tagged is None:
        floors = floors or canonical.read_json(_DEFAULT_FLOORS_PATH)
        tagged, pairs, _ = _holding_roles(floors, frame, rating or {}, facts_by_id)
    failures.extend(_holding_fact_failures(tagged, pairs, facts_by_id, ruling, holding_context))
    return failures


def _holding_id(tagged, role):
    return next((fid for fid, roles in tagged.items() if role in roles), None)


def _holding_roles(floors, frame, rating, facts_by_id, captured_day=None, requirements=()):
    """AC62(H16), a2: ONE reading of currencies and each conversion use."""
    measures = floors["archetype_measures"]
    kind = (measures.get("holding_rule") or {}).get("holding_archetype")
    entries = floors["archetype_floors"].get(kind, {}).get("all_subtypes") or []
    history = next((e["prefixes"] for e in entries if e["kind"] == "parallel_prefixes"), None)
    if history is None:
        history = next(e["prefixes"] for e in floors["archetype_floors"][
            "financial_institution"]["financial_holding"] if e["kind"] == "parallel_prefixes")
    codes = {u.removesuffix("_per_share") for u in floors["allowed_units"] if u.endswith("_per_share")}
    rates = {a + " per " + b for a in codes for b in codes}
    aliases = floors["prose_figure_marks"].get("currency_aliases") or {}
    units = {u: c for u in floors["allowed_units"] for c in codes
             if (v := aliases.get(u, u)) not in rates and (v == c or v.startswith((c + "_", c + " per ")))}
    bridge, tagged, pairs = frame.get("nav_bridge") or {}, {}, {}

    def tag(fid, role):
        if isinstance(fid, str):
            tagged.setdefault(fid, set()).add(role)

    for field, role in (("nav_total_fact", "nav"), ("holdco_net_debt_fact", "debt"),
                        ("discount_fact", "discount"), ("published_nav_fact", "published")):
        tag(bridge.get(field), role)
    row = measures["table"].get(frame.get("archetype"), {})
    row = row.get("subtypes", {}).get(frame.get(row.get("subtype_field")), row)
    tag(row.get("subject_numerator"), "market")
    tag(next(e["id"] for e in floors["classes"]["single_stock"]["floors"] if e.get("id") == "price_last"), "price")
    tag("holdco_costs_ttm", "costs")
    for part in bridge.get("components") or ():
        tag(part.get("value_fact"), "component")
        if part.get("method") in ("company_reported_value", "carrying_value"):
            tag(part.get("value_fact"), "private")
    prefix = floors["archetype_floors"].get(kind, {}).get("canonical_tests", {}).get("free_cash_flow", {}).get("answered_by_prefix")
    for fid in rating.get("cash_answered_by") or ():
        if prefix and fid.startswith(prefix):
            tag(fid, "cash_cover")
    for fid, fact in facts_by_id.items():
        if fact.get("unit") in units:
            tag(fid, "currency:" + units[fact["unit"]])
        for index, prefix in enumerate(history):
            if fid.startswith(prefix) and len(fid) > len(prefix):
                suffix = fid[len(prefix):]
                tag(fid, "history:" + str(index))
                pairs.setdefault(suffix, [None, None])[index] = fid
    # Architect rulings A/B and AC62(H16): resolve aliases before comparing
    # currencies or suffixes. Exemptions name the parent AND its operand.
    if captured_day is not None:
        rule = measures["holding_rule"]
        fx = rule["fx_rate_prefix"]
        def references(tree):
            if isinstance(tree, dict):
                for key, value in tree.items():
                    references(key)
                    references(value)
            elif isinstance(tree, (list, tuple)):
                for value in tree:
                    references(value)
            elif isinstance(tree, str) and tree in facts_by_id:
                tag(tree, "referenced")

        references(frame)
        references(requirements)
        # AC62(H16), fix round two: the rating also reads peers by name.
        for peer in frame.get("peers") or ():
            for metric in ([row.get("peer_numerator_metric")]
                           + list(rating.get("peer_denominator_metrics") or ())):
                if metric:
                    tag("peer_%s__%s" % (metric, subjects.slug(peer["ticker"])), "referenced")
        market = _holding_id(tagged, "market")
        pack_currency = units.get((facts_by_id.get(market) or {}).get("unit"))
        uses, exemptions = {}, set()
        for fid, fact in facts_by_id.items():
            derived = fact.get("derived") or {}
            refs = [o.get("fact_id") for o in derived.get("operands") or ()]
            for ref in refs:
                if ref:
                    uses.setdefault(ref, set()).add(fid)
            rate_refs = [r for r in refs if r and (r.startswith(fx)
                         or (facts_by_id.get(r) or {}).get("unit") in rates)]
            money_refs = [r for r in refs if r not in rate_refs
                          and (facts_by_id.get(r) or {}).get("unit") in units]
            target = units.get(fact.get("unit"))
            natives = [r for r in money_refs if units[facts_by_id[r]["unit"]] != target]
            # AC65(1): judge the class, including unnamed rates and plain
            # multipliers changing a money operand's currency.
            if not rate_refs and not (target and natives):
                continue
            rate_refs = rate_refs or [r for r in refs if r and r not in money_refs]
            # AC65(1): every conversion ends in the pack's rated currency.
            # An outward leg also invalidates a round trip through two rates.
            if target != pack_currency:
                for rate in rate_refs or natives:
                    tag(rate, "rate_fault:AC65(1): '%s' converts into %s, "
                        "required the pack currency %s"
                        % (rate, target or fact.get("unit"), pack_currency))
                continue
            if not target or not natives:
                # Ruling C: every rate use is judged, even without native money.
                currency = target or pack_currency or "no rated currency"
                pair = currency + " per " + currency
                for rate in rate_refs:
                    tag(rate, "rate_fault:'%s' is in %s, required %s"
                        % (rate, (facts_by_id.get(rate) or {}).get("unit"), pair))
                continue
            shape = (derived.get("operation") == "multiply" and len(rate_refs) == 1
                     and len(money_refs) == 1 and len(refs) == 2)
            if len(rate_refs) != 1 or len(money_refs) != 1:
                for native in natives:
                    tag(native, "currency_fault:AC65(1): one currency throughout: '%s' is in %s, "
                        "result '%s' is in %s; needs one native figure and one dated %s fact"
                        % (native, facts_by_id[native]["unit"], fid, fact.get("unit"), fx))
                continue
            rate, native = rate_refs[0], money_refs[0]
            native_unit = aliases.get(facts_by_id[native]["unit"], facts_by_id[native]["unit"])
            result_unit = aliases.get(fact["unit"], fact["unit"])
            source = units[facts_by_id[native]["unit"]]
            same_scale = native_unit[len(source):] == result_unit[len(target):]
            if not same_scale:
                tag(native, "currency_fault:one currency throughout: '%s' is in %s, "
                    "the conversion '%s' is in %s with a different scale suffix"
                    % (native, native_unit, fid, result_unit))
            elif not shape:
                tag(native, "currency_fault:one currency throughout: '%s' is in %s, "
                    "the pack also uses %s" % (native, native_unit, result_unit))
            pair, rate_fact, faults = target + " per " + source, facts_by_id.get(rate) or {}, []
            if not rate.startswith(fx):
                faults.append("AC65(1): '%s' is not a dated %s fact" % (rate, fx))
            try:
                age = (captured_day - _as_of_moment(rate_fact["as_of"]).date()).days
            except (KeyError, ValueError, TypeError, AttributeError):
                age = None
                faults.append("'%s' is absent or undated" % rate)
            if age is not None and age < 0:
                faults.append("'%s' is dated after the capture" % rate)
            elif age is not None and age > rule["max_price_freshness_days"]:
                faults.append("'%s' is %s days old against %s days" % (rate, age, rule["max_price_freshness_days"]))
            if rate_fact.get("unit") != pair:
                faults.append("'%s' is in %s, required %s" % (rate, rate_fact.get("unit"), pair))
            for fault in faults:
                tag(rate, "rate_fault:" + fault)
            if shape and same_scale and not faults and target == pack_currency:
                exemptions.add((fid, native))
                tag(native, "native:" + fid)
        for fid, roles in list(tagged.items()):
            currency = units.get((facts_by_id.get(fid) or {}).get("unit"))
            if currency and currency != pack_currency:
                direct = roles - {r for r in roles if r.startswith(("currency:", "native:", "currency_fault:"))}
                if (direct or not uses.get(fid)
                        or any((parent, fid) not in exemptions for parent in uses[fid])):
                    tag(fid, "unconverted")
    return tagged, pairs, history


def _holding_history(pairs, gaps, history):
    """HA7: the ONE annual reading for checks, figures and floor gaps."""
    years = sorted((s for s in pairs if re.fullmatch(r"fy\d{4}", s)
                    and gate.period_order(s) is not None), key=gate.period_order, reverse=True)
    gap = [g.get("reason_kind") for g in gaps if g["fact_class"] == history[0]]
    return {"complete": [(s, *pairs[s]) for s in years if None not in pairs[s]],
            "incomplete": [s for s in years if None in pairs[s]],
            "gap": bool(gap and all(k == "absent_by_design" for k in gap))}


def _holding_fact_failures(tagged, pairs, facts_by_id, ruling, holding_context=None):
    """Every property keeps its own ground and shopping-list source."""
    failures = []
    market, nav, price = (_holding_id(tagged, r) for r in ("market", "nav", "price"))
    currency = next((r for r in tagged.get(market, ()) if r.startswith("currency:")), None)
    if holding_context:
        rule, captured_day, decisive_ids = holding_context

    def broken(fid, why, ground, where):
        failures.append(("a holding reading: '%s'" % fid, ground + ": " + why, where))

    if holding_context and _holding_id(tagged, "published") is None:
        broken("published_nav_fact", "the bridge must name published_nav_fact", "owner ruling AC60(H5)", "the company's own latest NAV")
    for fid, roles in tagged.items():
        fact = facts_by_id.get(fid) or {}
        if holding_context:
            for role in sorted(roles):
                if role.startswith("rate_fault:"):
                    broken(fid, role[len("rate_fault:"):], "owner ruling AC62(H16)", "the dated exchange-rate source")
                elif role.startswith("currency_fault:"):
                    broken(fid, role[len("currency_fault:"):], "owner ruling AC62(H16)", "the money figure and its dated conversion arithmetic")
        if not fact:
            continue
        counterparts = [market] if roles & {"component", "debt", "nav"} else []
        if "costs" in roles:
            counterparts.append(nav)
        if "published" in roles and holding_context:
            counterparts.append(price if fact.get("unit") == (facts_by_id.get(price) or {}).get("unit") else market)
        if "history:1" in roles:
            counterparts += [left for left, right in pairs.values() if right == fid]
        for other in counterparts:
            expected = (facts_by_id.get(other) or {}).get("unit")
            if expected is not None and fact.get("unit") != expected:
                failures.append(("one unit for '%s' and '%s'" % (fid, other),
                    ruling + ": '%s' is in %s and '%s' is in %s; the council normalises no units" % (fid, fact.get("unit"), other, expected),
                    "both readings in one unit, any conversion shown in arithmetic"))
        if not holding_context:
            continue
        value = gate._decimal_or_none(fact["value"])
        if roles & {"component", "debt", "nav", "published", "costs", "cash_cover", "history:0", "history:1"} and value is None:
            broken(fid, "a numeric reading, recorded as '%s'" % fact["value"], "architect ruling HA8", "the numeric source reading")
        if "nav" in roles and value is not None and value <= 0:
            broken(fid, "net asset value above zero, recorded as %s" % value, "architect ruling HA8/F5", "the bridge's positive NAV total")
        if "published" in roles and roles & {"history:0", "history:1"}:
            broken(fid, "the latest published NAV is not a history member", "owner ruling AC60(H5)", "the company's own latest NAV")
        if "private" in roles:
            age = (captured_day - _as_of_moment(fact["as_of"]).date()).days
            if age > rule["private_valuation_max_age_days"]:
                broken(fid, "a private value dated %s, %s days old against %s days" % (fact["as_of"], age, rule["private_valuation_max_age_days"]),
                       "owner ruling AC60(H6)", "the company's latest dated private valuation")
        if roles & {"nav", "discount", "cash_cover"} and fid not in decisive_ids:
            failures.append(("a decisive holding fact: '%s'" % fid,
                "owner ruling AC62(H13), HA10: '%s' must be named in a decisive metric's answered_by" % fid,
                "the business frame's decisive metrics"))
        if "unconverted" in roles:
            broken(fid, "one currency throughout: '%s' is in %s, the pack also uses %s" % (fid, fact["unit"], currency[9:] if currency else "no rated currency"),
                   "owner ruling AC62(H16)", "the money figure and its dated conversion arithmetic")
    return failures


def _holding_failures(floors, frame, rating, capture, facts_by_id, captured_day,
                      decisive_ids, gap_kinds, tagged, pairs, history):
    """HA7/HA8: relationships over the shared reading, freshness unchanged."""
    rule = floors["archetype_measures"]["holding_rule"]
    if captured_day < date.fromisoformat(rule["applies_from"]):
        return []
    failures = []
    for target in (_holding_id(tagged, "market"), _holding_id(tagged, "nav")):
        if target and not _rests_on(_holding_id(tagged, "discount"), {target}, facts_by_id):
            failures.append(("a discount resting on '%s'" % target,
                "architect ruling HA8: the discount must rest on both the market value and the bridge total",
                "the discount fact's declared arithmetic"))
    annual = _holding_history(pairs, capture["gaps"], history)
    for suffix in annual["incomplete"]:
        failures.append(("a year-end pair: '%s'" % suffix,
            "owner ruling AC61(H9): NAV per share and the share price that day must both be recorded",
            "the published financial year-end NAV and closing price"))
    if len(annual["complete"]) < rule["history_year_ends"] and not annual["gap"]:
        failures.append(("the holding's financial year-end history",
            "owner ruling AC61(H9): %s year-end pairs are required; the pack carries %s, with no absent-by-design gap" % (rule["history_year_ends"], len(annual["complete"])),
            "the last published financial year-end NAV and share prices"))
    return failures


def holding_readings(pack, floors):
    """HA8: exact ratio halves plus percent displays cut toward zero.
    Returns None for other subjects. Unreadable holding figures are None
    with reasons in errors. No value is written into the frozen pack.
    Comparisons use Decimal cross products, never displayed percentages."""
    capture = (pack or {}).get("capture") or {}
    if not capture.get("subject") or _declared_archetype(floors, capture) != (
            floors["archetype_measures"]["holding_rule"]["holding_archetype"], None):
        return None
    frame = capture["business_frame"][capture["subject"]["ticker"]]
    facts = {f["id"]: f for f in capture["tier1"]}
    rating = next((r for r in capture["sufficiency"]["requirements"]
                   if r["id"] == "rating_vs_history_or_peers"), {})
    captured_day = _as_of_moment(capture["captured_at"]).date()
    tagged, pairs, history = _holding_roles(floors, frame, rating, facts, captured_day,
        capture["sufficiency"]["requirements"])
    decisive = {fid for m in frame["decisive_metrics"] for fid in m.get("answered_by") or []}
    context = (floors["archetype_measures"]["holding_rule"], _as_of_moment(capture["captured_at"]).date(), decisive)
    errors = [why for _, why, _ in _holding_fact_failures(tagged, pairs, facts, "HA6", context)]
    bridge = frame.get("nav_bridge") or {}
    result = {"errors": errors}

    def amount(fid):
        value = gate._decimal_or_none((facts.get(fid) or {}).get("value"))
        if value is None:
            errors.append("missing or unreadable '%s'" % fid)
        return value

    def ratio(numerator, denominator):
        if numerator is None or denominator is None or denominator <= 0:
            errors.append("ratio needs both halves and a denominator above zero")
            return None
        with decimal.localcontext() as exact:
            exact.prec = max(100, len(numerator.as_tuple().digits)
                             + len(denominator.as_tuple().digits) + 20)
            display = (numerator * 1000 // denominator / 10).quantize(
                decimal.Decimal("0.1"))
        return {"numerator": numerator, "denominator": denominator,
                "percent": display}

    # All arithmetic shares one precision chosen from the recorded class.
    with decimal.localcontext() as exact:
        exact.prec = 100 + sum(len(str(facts[fid]["value"]))
                               for fid in tagged if fid in facts)
        holdings = []
        for part in bridge.get("components") or ():
            holdings.append(dict(part, value=amount(part.get("value_fact")),
                                 as_of=(facts.get(part.get("value_fact")) or {}).get("as_of")))
        values = [p["value"] for p in holdings]
        gross = sum(values) if values and None not in values else None
        private = sum(p["value"] for p in holdings
                      if "private" in tagged[p["value_fact"]]) if gross is not None else None
        for part in holdings:
            part["share"] = ratio(part["value"], gross)
        holdings.sort(key=lambda p: p["value"] if p["value"] is not None
                      else decimal.Decimal("-Infinity"), reverse=True)
        nav, market = amount(_holding_id(tagged, "nav")), amount(_holding_id(tagged, "market"))
        published_id = _holding_id(tagged, "published")
        published = amount(published_id)
        pub_unit = (facts.get(published_id) or {}).get("unit")
        comparable = market if pub_unit == (facts.get(_holding_id(tagged, "market")) or {}).get("unit") else amount(_holding_id(tagged, "price"))
        today = ratio(nav - market if None not in (nav, market) else None, nav)
        company = ratio(published - comparable if None not in (published, comparable)
                        else None, published)
        rows = []
        annual = _holding_history(pairs, capture["gaps"], history)
        if annual["incomplete"]:
            errors.append("missing year-end members: " + ", ".join(annual["incomplete"]))
        for suffix, left, right in annual["complete"][:floors["archetype_measures"]["holding_rule"]["history_year_ends"]]:
            a, b = amount(left), amount(right)
            rows.append({"year": suffix, "nav_fact": left, "price_fact": right,
                         "discount": ratio(a - b if None not in (a, b) else None, a)})
        average = word = None
        if rows and company and all(r["discount"] for r in rows) and not errors:
            numerator, denominator = decimal.Decimal(0), decimal.Decimal(1)
            for row in rows:
                r = row["discount"]
                numerator = numerator * r["denominator"] + r["numerator"] * denominator
                denominator *= r["denominator"]
            average = ratio(numerator, denominator * len(rows))
            comparisons = [company["numerator"] * r["discount"]["denominator"]
                           - r["discount"]["numerator"] * company["denominator"]
                           for r in rows]
            word = "wider" if all(c > 0 for c in comparisons) else "narrower" if all(
                c < 0 for c in comparisons) else "inside"
        result.update(gross_value=gross, private_share=ratio(private, gross),
                      holdings=holdings, largest=holdings[0] if holdings else None,
                      largest_above_half=(holdings[0]["value"] * 2 > gross
                                          if holdings and gross is not None else None),
                      private_above_half=(private * 2 > gross if gross is not None else None),
                      loan_to_value=ratio(amount(_holding_id(tagged, "debt")), gross),
                      costs_to_nav=ratio(amount(_holding_id(tagged, "costs")), nav),
                      discount_today=today, discount_published=company,
                      history=rows, history_average=average, range_word=word,
                      history_reason=None if rows else "no financial year-end pairs are recorded")
        if errors:
            # A unit breach must never leave a printable bogus ratio behind.
            for key in ("private_share", "loan_to_value", "costs_to_nav",
                        "discount_today", "discount_published", "history_average"):
                result[key] = None
            for part in holdings:
                part["share"] = None
            for row in rows:
                row["discount"] = None
            result["range_word"] = None
            result["gross_value"] = result["largest"] = None
            result["largest_above_half"] = result["private_above_half"] = None
        return result


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
        failures.extend(_nav_bridge_failures(frame, rating, facts_by_id, floors=floors))

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
    failures.extend(_denominator_id_failures(
        row, rating, subtype.replace("_", " "),
        exited.get("continuing_suffix") or ""))

    # Owner ruling AC30(4) (G4): on a model transition the exited
    # business's earnings and client money are banned as its revenue is.
    if changing == "model_transition" and exited:
        failures.extend(_exited_business_failures(
            row, rating, exited.get("roles"),
            exited.get("continuing_suffix") or "", "owner ruling AC30(4)",
            "the continuing business's figure - a derived fact may "
            "strike it from the whole less the part being exited, "
            "arithmetic shown"))
    return failures


def _exited_business_failures(row, rating, roles, suffix, ruling, where):
    """On a model transition, each subject denominator whose role is
    named in `roles` is the continuing business's figure, its id ending
    in `suffix` (owner ruling AC30(4) for the financial institution;
    architect ruling A9 for any row carrying exited_business_roles). One
    (what, why, where) per whole-business denominator."""
    failures = []
    banned_roles = set(roles or ())
    denominators = (rating or {}).get("subject_denominator_facts") or []
    for fid, role in zip(denominators, row.get("denominator_roles") or ()):
        if (role in banned_roles and isinstance(fid, str)
                and not fid.endswith(suffix)):
            failures.append((
                "the continuing business's %s as the rating's "
                "denominator" % role.replace("_", " "),
                "%s: this business is changing its "
                "model, and the rating divides by '%s', the %s of the "
                "whole business - including the part being sold or "
                "run off. The %s the rating rests on is the continuing "
                "business's, its id ending '%s'"
                % (ruling, fid, role.replace("_", " "),
                   role.replace("_", " "), suffix),
                where))
    return failures


def _denominator_id_failures(row, rating, who, suffix):
    """Each denominator is a fact its role allows (architect ruling
    closing P-FIa-1): a resolved archetype row that names, per role, the
    ids its measure is struck on holds the rating to them - on the
    subject's side and on the peers' alike - whatever the archetype (unit
    GROWTH-ARCHETYPE, D1). `who` names the business in the refusal; the
    continuing business's figure is the same id ending in `suffix`, the
    row's own exited-business data. One (what, why, where) per breach."""
    failures = []
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
    return failures


def _grower_frame(floors, capture):
    """The business frame of a single name that declares the growth
    archetype, or None."""
    declared = _declared_archetype(floors, capture)
    if not declared or declared[0] != _GROWER_ARCHETYPE:
        return None
    frame = (capture.get("business_frame") or {}).get(
        capture["subject"].get("ticker"))
    return frame if isinstance(frame, dict) else None


def _runway_units(fact_ids, facts_by_id):
    """Each recorded runway fact's unit, in order (audit finding r1-1 of
    sub-charge b): the months of cash left are worked out only where they
    are all one unit - the council normalises no units anywhere, it
    compares like with like and refuses otherwise."""
    return [(fid, facts_by_id[fid].get("unit")) for fid in fact_ids
            if fid in facts_by_id]


def growth_runway(pack, floors):
    """The months of cash a growth company has left (owner rulings AC50(7)
    and AC50(8); architect ruling A6), or None for any other subject or a
    runway block that cannot be read.

    Returns {"cash", "burn", "threshold_months", "below", "months"}: the
    cash is the sum of the block's cash facts (cash plus short-term
    investments; an undrawn credit line is shown, never counted); the burn
    is the last four quarters' capital spending less operating cash flow,
    or None where the company generates cash; below is True where the cash
    covers fewer months of that burn than the floors' line. The test is
    exact multiplication, never division: below where cash times twelve is
    less than the line times the annual burn. The months are worked out to
    one place for printing only, cut toward zero so a company under the
    line never prints at it - never written to the pack, never compared. The pages and the publisher read this helper; nothing
    computes the months twice."""
    capture = (pack or {}).get("capture") or {}
    if not capture.get("subject"):
        return None
    frame = _grower_frame(floors, capture)
    data = (floors.get("archetype_measures") or {}).get("growth_runway")
    block = (frame or {}).get("growth_runway")
    if not isinstance(block, dict) or not isinstance(data, dict):
        return None
    facts_by_id = {fact["id"]: fact for fact in capture.get("tier1") or []}

    def amount(fact_id):
        fact = facts_by_id.get(fact_id) if isinstance(fact_id, str) else None
        return gate._decimal_or_none(fact["value"]) if fact else None

    cash_ids = _dedupe(block.get("cash_facts") or [])
    amounts = [amount(fact_id) for fact_id in cash_ids]
    operating = amount(block.get("operating_cash_flow_fact"))
    spending = amount(block.get("capital_expenditure_fact"))
    if (not cash_ids or None in amounts or operating is None
            or spending is None):
        return None
    if len({unit for _, unit in _runway_units(
            cash_ids + [block.get("operating_cash_flow_fact"),
                        block.get("capital_expenditure_fact")],
            facts_by_id)}) != 1:
        return None
    cash = sum(amounts, decimal.Decimal(0))
    burn = spending - operating
    threshold = data.get("threshold_months")
    if burn <= 0:
        return {"cash": cash, "burn": None, "threshold_months": threshold,
                "below": False, "months": None}
    # Tenths of a month, cut toward zero by exact integer division, so the
    # printed months never cross the line the multiplication decided
    # (audit finding r3-1 of sub-charge (b)).
    months = (cash * 12 * 10 // burn / 10).quantize(decimal.Decimal("0.1"))
    return {"cash": cash, "burn": burn, "threshold_months": threshold,
            "below": cash * 12 < decimal.Decimal(threshold) * burn,
            "months": months}


def _grower_failures(floors, row, frame, rating, decisive_ids,
                     facts_by_id):
    """Why a growth company's frame breaks the rule the floors set for it
    (owner rulings AC50 (4), (5) and (7); architect ruling A10) - one
    (what, why, where) per breach - or nothing where it holds. The runway
    block's SHAPE is the provenance gate's; this is the rule against the
    floors data. Its freshness is read in check(), as the financial
    institution's blocks are."""
    failures = []
    data = (floors.get("archetype_measures") or {}).get("growth_runway") or {}
    block = frame.get("growth_runway")
    block = block if isinstance(block, dict) else {}
    cash_ids = list(data.get("cash_ids") or ())
    burn_ids = data.get("burn_ids") or {}
    cash_facts = [fid for fid in block.get("cash_facts") or ()
                  if isinstance(fid, str)]
    for fid in cash_facts:
        if fid not in cash_ids:
            failures.append((
                "a cash fact the floors name for the months of cash left",
                "owner ruling AC50(7): the months of cash left count cash "
                "and short-term investments only - %s - and the frame's "
                "growth_runway counts '%s' as cash; a credit line or any "
                "other figure is shown, never counted"
                % (", ".join("'%s'" % item for item in cash_ids), fid),
                "growth_runway.cash_facts: %s"
                % " or ".join("'%s'" % item for item in cash_ids)))
    burn_facts = []
    for key, role, words in (
            ("operating_cash_flow_fact", "operating_cash_flow",
             "operating cash flow"),
            ("capital_expenditure_fact", "capital_spending",
             "capital spending")):
        named, wanted = block.get(key), burn_ids.get(role)
        if isinstance(named, str):
            burn_facts.append(named)
        if wanted and named != wanted:
            failures.append((
                "the cash burn fact the floors name for %s" % words,
                "owner ruling AC50(7): the cash burn is the last four "
                "quarters' operating cash flow less capital spending, and "
                "the %s it is counted from is '%s' - the frame's "
                "growth_runway names '%s'" % (words, wanted, named),
                "growth_runway.%s: '%s'" % (key, wanted)))
    for fid in _dedupe(cash_facts + burn_facts):
        fact = facts_by_id.get(fid)
        if fact is None:
            continue
        value = gate._decimal_or_none(fact["value"])
        if value is None:
            failures.append((
                "a number for '%s', which the months of cash left are "
                "counted from" % fid,
                "owner ruling AC50(7): the months of cash left are worked "
                "out from '%s', and its value is not a number" % fid,
                "a numeric reading of '%s'" % fid))
        elif fid == block.get("capital_expenditure_fact") and value < 0:
            failures.append((
                "capital spending recorded as the amount spent",
                "owner ruling AC50(7): the cash burn is operating cash flow "
                "less capital spending, and '%s' is below zero - recorded "
                "with its cash-flow sign it would shrink the burn instead "
                "of adding to it" % fid,
                "the capital spending as the amount spent, without the "
                "sign the cash-flow statement prints it with"))
    units = _runway_units(_dedupe(cash_facts + burn_facts), facts_by_id)
    if len({unit for _, unit in units}) > 1:
        failures.append((
            "one unit for the figures the months of cash left are counted "
            "from",
            "owner ruling AC50(7): the months of cash left are worked out "
            "from the cash and the cash burn together, and they are "
            "recorded in different units - %s - so no months can be struck "
            "from them" % ", ".join("'%s' in %s" % (fid, unit)
                                    for fid, unit in units),
            "the growth_runway block's cash and burn facts recorded in one "
            "unit"))
    # Architect ruling A10: the cash and its burn, and the growth the
    # yardstick is read beside, always decide a growth company's case.
    runway_ids = _dedupe(cash_facts + burn_facts)
    missing = [fid for fid in runway_ids if fid not in decisive_ids]
    if runway_ids and missing:
        failures.append((
            "a decisive metric resting on the months of cash left",
            "architect ruling A10 under owner ruling AC50(7): a growth "
            "company's cash and its cash burn always decide the case, and "
            "no decisive metric in the business frame rests on %s"
            % ", ".join("'%s'" % fid for fid in missing),
            "name the growth_runway block's cash and burn facts in the "
            "'answered_by' of a decisive metric"))
    missing = [fid for fid in _GROWER_GROWTH_PAIR if fid not in decisive_ids]
    if missing:
        failures.append((
            "a decisive metric resting on revenue growth",
            "architect ruling A10 under owner ruling AC50(5): the growth "
            "yardstick is read beside the latest quarter's revenue growth "
            "against the same quarter a year ago, so that growth always "
            "decides the case, and no decisive metric in the business "
            "frame rests on %s" % ", ".join("'%s'" % fid for fid in missing),
            "name %s in the 'answered_by' of a decisive metric"
            % " and ".join("'%s'" % fid for fid in _GROWER_GROWTH_PAIR)))
    # Owner ruling AC50(4): no sales, or a loss on every sale, is not a
    # growth company the yardstick can be struck for. A zero is already
    # the denominators' own refusal; this is the half below zero.
    denominators = (rating or {}).get("subject_denominator_facts") or []
    for fid, role in zip(denominators, row.get("denominator_roles") or ()):
        fact = facts_by_id.get(fid) if isinstance(fid, str) else None
        value = gate._decimal_or_none(fact["value"]) if fact else None
        if value is not None and value < 0:
            words = role.replace("_", " ")
            failures.append((
                "%s above zero" % words,
                "owner ruling AC50(4): the growth yardstick divides "
                "enterprise value by %s, and '%s' is below zero - %s; the "
                "council refuses such a company openly until the owner "
                "rules on companies without sales or with a loss on every "
                "sale" % (words, fid,
                          "a loss on every sale" if role == "gross_profit"
                          else "no sales to speak of"),
                "the owner's ruling on such companies comes first; no "
                "figure in this pack can stand in for it"))
    # The architect's ruling on P-GROWTHc-4 under owner ruling AC50(7): the
    # yardstick's two halves - the floors row's numerator and the gross
    # profit the rating row divides it by - are recorded in one unit, as
    # the months of cash left are; the council normalises no units.
    halves = [row.get("subject_numerator")] + [
        fid for fid, role in zip(denominators,
                                 row.get("denominator_roles") or ())
        if role == "gross_profit"]
    units = _runway_units(_dedupe([fid for fid in halves
                                   if isinstance(fid, str)]), facts_by_id)
    if len(units) == 2 and len({unit for _, unit in units}) > 1:
        failures.append((
            "one unit for the two halves of the growth yardstick",
            "owner ruling AC50(7): the growth yardstick divides the "
            "enterprise value by the last four quarters' gross profit, and "
            "they are recorded in different units - %s - so no multiple can "
            "be struck from them" % ", ".join("'%s' in %s" % (fid, unit)
                                              for fid, unit in units),
            "the yardstick's enterprise value and gross profit recorded in "
            "one unit"))
    return failures


def _canonical_test_terms(floors, declared):
    """The canonical tests the declared archetype re-points or adds, each
    {"words": [why, where], "authority", and "answered_by_ids",
    "answered_by_prefix" or "answered_by_prefix_where_carried"} - the
    archetype's own block, then its sub-type's lifts (owner rulings
    AC30(1) and AC50(9)). Empty for every other subject, whose tests read
    the guide unchanged."""
    if not declared:
        return {}
    block = (floors.get("archetype_floors") or {}).get(declared[0]) or {}
    terms = dict(block.get("canonical_tests") or {})
    terms.update(_archetype_lifts(floors, declared).get("canonical_tests")
                 or {})
    return terms


def _test_term_failures(term, answered_by, tier1_ids):
    """What a canonical test's answer lacks against its term: (the facts
    that answer it, what it names instead) per breach, in the words the
    refusal completes."""
    failures = []
    ids = list(term.get("answered_by_ids") or ())
    missing = [fid for fid in ids if fid not in answered_by]
    if missing:
        failures.append((", ".join("'%s'" % fid for fid in ids),
                         "does not name %s"
                         % ", ".join("'%s'" % fid for fid in missing)))
    prefix = term.get("answered_by_prefix")
    if prefix and not any(fid.startswith(prefix) and fid in tier1_ids
                          for fid in answered_by):
        failures.append(("a '%s' fact" % prefix, "names none"))
    carried = term.get("answered_by_prefix_where_carried")
    present = [fid for fid in tier1_ids
               if carried and fid.startswith(carried)]
    if present and not any(fid in present for fid in answered_by):
        failures.append((
            "a '%s' fact wherever the pack carries one, as it carries %s"
            % (carried, ", ".join("'%s'" % fid for fid in present)),
            "names none"))
    return failures


# The period a quarterly member's id ends in (owner rulings AC49(1) and
# AC50(1)): a quarter of a year, or - for a company reporting every six
# months - one half of it.
_PERIOD_QUARTER = re.compile(r"q[1-4]\Z")
_PERIOD_HALF = re.compile(r"h([12])\Z")


def _period_place(slug):
    """Where a quarterly member's period falls: ("quarter", n) or
    ("half", n), n counting quarters or halves from year nought so the
    one before is n - 1; None where the slug names no single quarter or
    half of one year. A quarter is read by the gate's own period_order; a
    bare year is not a quarter, though period_order reads it as its last."""
    tokens = slug.split("_")
    halves = [token for token in tokens if _PERIOD_HALF.match(token)]
    if halves:
        rest = [token for token in tokens if token not in halves]
        order = gate.period_order("_".join(rest))
        if (len(halves) != 1 or order is None
                or any(_PERIOD_QUARTER.match(token) for token in rest)):
            return None
        return "half", order[0] * 2 + int(_PERIOD_HALF.match(
            halves[0]).group(1)) - 1
    order = gate.period_order(slug)
    if order is None or not any(_PERIOD_QUARTER.match(token)
                                for token in tokens):
        return None
    return "quarter", order[0] * 4 + order[1] - 1


def _continuing_profit_suffix(floors, declared, capture):
    """The id ending of the continuing business's operating income where
    the frame declares a model transition, or "" (the architect's ruling
    on audit finding r1-3's residual, under owner ruling AC50(1): standard
    accounting's continuing-operations line, the AC30(4) precedent). Read
    from the declared row where it names the roles its exited business
    touches, else from the growth archetype's rows, which do: the rule
    weighs every company it governs against the growth path, so both
    directions read the same figures."""
    subject = capture["subject"]
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    if ((frame or {}).get("what_is_changing") or {}).get(
            "kind") != "model_transition":
        return ""
    measures = floors.get("archetype_measures") or {}
    table = measures.get("table") or {}

    def rows(archetype, subtype=None):
        row = table.get(archetype) or {}
        if not row.get("subtypes"):
            return [row]
        if subtype:
            return [row["subtypes"].get(subtype) or {}]
        return list(row["subtypes"].values())

    for candidates in (rows(*declared), rows(
            (measures.get("profitability_rule") or {}).get(
                "growth_archetype"))):
        suffixes = {row.get("continuing_suffix") for row in candidates
                    if row.get("exited_business_roles")
                    and row.get("continuing_suffix")}
        if len(suffixes) == 1:
            return suffixes.pop()
    return ""


def _placed_members(members, prefix, suffix):
    """({place: [member ids]}, [ids no period can be read from]) for the
    members of a quarterly family, each placed by _period_place from the
    id between `prefix` and `suffix` - the one reading of which quarter a
    member is (owner rulings AC49(1) and AC50(1); the producer's quarters,
    the architect's ruling on P-RESOURCEa-10, read the same way)."""
    places, unplaced = {}, []
    for fact_id in members:
        place = _period_place(fact_id[len(prefix):len(fact_id)
                                      - len(suffix)])
        if place is None:
            unplaced.append(fact_id)
        else:
            places.setdefault(place, []).append(fact_id)
    return places, unplaced


def _latest_wanted(capture, places, rule):
    """(kind, need, wanted): the periods the latest quarters (or halves)
    are, newest first, counted back from the newer of the newest member and
    the latest period the pack reports - `need` of them, the rule's
    quarters or half-years; wanted is empty where neither is known."""
    kinds = sorted({kind for kind, _ in places})
    kind = kinds[0] if kinds else "quarter"
    need = int(rule["half_years"] if kind == "half" else rule["quarters"])
    newest = max((number for _, number in places), default=None)
    reported = _latest_reported_place(capture, kind)
    if reported is not None:
        newest = reported if newest is None else max(newest, reported)
    return kind, need, ([] if newest is None
                        else [newest - step for step in range(need)])


def _profitability_failures(floors, declared, capture, facts_by_id,
                            captured_day):
    """The rule that chooses between earnings and the growth path (owner
    rulings AC49(1) and AC50 (1)-(3)), read from the floors'
    profitability_rule: for a single name declaring an archetype the rule
    governs, or the growth archetype, and captured on or after the day its
    quarterly floor is ruled from, the operating income of the latest four
    quarters (or two halves) decides. A governed archetype short of that
    refuses and points at the growth archetype; the growth archetype with
    it refuses as graduated. Where the frame declares a model transition
    and the pack carries the continuing business's quarters, those decide
    and the whole business's are set aside; without them the whole
    business decides, as where no exit is declared. One (what, why,
    where) per breach."""
    rule = ((floors.get("archetype_measures") or {})
            .get("profitability_rule") or {})
    if not rule or not declared:
        return []
    archetype = declared[0]
    governs = list(rule.get("governs") or ())
    growth = rule.get("growth_archetype")
    if archetype not in governs and archetype != growth:
        return []
    prefix = rule["profit_prefix"]
    source = "the operating income of each quarter, from its own filing"
    for entry in _archetype_floor_entries(floors, declared):
        if (entry.get("kind") == "parallel_prefixes"
                and prefix in (entry.get("prefixes") or ())):
            source = entry.get("likely_source") or source
            if (entry.get("applies_from") and captured_day
                    < date.fromisoformat(entry["applies_from"])):
                return []
    failures = []
    suffix = _continuing_profit_suffix(floors, declared, capture)
    members = [fact["id"] for fact in capture["tier1"]
               if fact["id"].startswith(prefix)
               and len(fact["id"]) > len(prefix)]
    continuing = [fact_id for fact_id in members if suffix
                  and fact_id.endswith(suffix)
                  and len(fact_id) > len(prefix) + len(suffix)]
    if continuing:
        members = continuing
    else:
        suffix = ""
    places, unplaced = _placed_members(members, prefix, suffix)
    for fact_id in unplaced:
        failures.append((
            "a quarter the rule can place: '%s'" % fact_id,
            "owner ruling AC49(1): the latest quarters are read newest "
            "first by their period, and '%s' ends in no single quarter "
            "or half of one year, so it cannot be placed among them"
            % fact_id,
            "the id ending in the quarter's period, as the floor names "
            "it: %s" % source))
    if failures:
        return failures
    kinds = sorted({kind for kind, _ in places})
    if len(kinds) > 1:
        return [(
            "operating income by one kind of period",
            "owner ruling AC50(1): a company reports by the quarter or by "
            "the half-year, and the operating-income members here mix the "
            "two (%s) - the rule reads the latest quarters or the latest "
            "halves, never a blend" % ", ".join(
                "'%s'" % fact_id for place in sorted(places)
                if place[0] == "half" for fact_id in places[place]),
            source)]
    for place in sorted(places):
        if len(places[place]) > 1:
            failures.append((
                "one operating-income member per period",
                "owner ruling AC49(1): %s name the same period, so the "
                "latest quarters cannot be counted"
                % " and ".join("'%s'" % item for item in places[place]),
                source))
    if failures:
        return failures
    kind, need, wanted = _latest_wanted(capture, places, rule)
    newest = wanted[0] if wanted else None
    words = "quarters" if kind == "quarter" else "half-years"
    missing = [number for number in wanted if (kind, number) not in places]
    if newest is None or missing:
        return [(
            "the operating income of each of the %d latest %s" % (need,
                                                                words),
            "owner ruling AC49(1): whether this company is rated on its "
            "earnings or on the growth path is chosen by its %d latest %s, "
            "and the pack carries %s - so the rule cannot choose"
            % (need, words,
               "no '%s' member at all" % prefix if newest is None else
               "no '%s' member for %s" % (
                   prefix + ("..." + suffix if suffix else ""), ", ".join(
                   _period_words(kind, number) for number in missing))),
            source)]
    chosen = [places[(kind, number)][0] for number in wanted]
    unread = [fact_id for fact_id in chosen
              if gate._decimal_or_none(facts_by_id[fact_id]["value"])
              is None]
    if unread:
        return [(
            "a number for the operating income of '%s'" % fact_id,
            "owner ruling AC49(1): the rule reads whether each of the "
            "latest %s shows an operating profit, and '%s' is not a number"
            % (words, fact_id), source) for fact_id in unread]
    losses = [fact_id for fact_id in chosen
              if gate._decimal_or_none(facts_by_id[fact_id]["value"]) <= 0]
    if archetype in governs and losses:
        return [(
            "four profitable quarters behind a %s"
            % archetype.replace("_", " "),
            "owner ruling AC49(1): a company without four profitable "
            "quarters behind it is rated on the growth path, never on "
            "earnings it does not yet have - the frame declares a '%s', "
            "and the operating income of %s is at or below zero"
            % (archetype, ", ".join("'%s'" % item for item in losses)),
            "the archetype in the business frame: '%s', the growth path, "
            "rated on enterprise value over gross profit beside how fast "
            "sales grow" % growth)]
    if archetype == growth and not losses:
        return [(
            "a growth company without four profitable quarters behind it",
            "owner rulings AC49(1) and AC50(2): the rule works both ways - "
            "the operating income of each of the latest %s (%s) is above "
            "zero, so this company has graduated and is rated on its "
            "earnings, not on the growth path"
            % (words, ", ".join("'%s'" % item for item in chosen)),
            "the archetype in the business frame: one of %s, the "
            "archetypes rated on earnings" % ", ".join(
                "'%s'" % item for item in governs))]
    return []


def _archetype_rule_failures(floors, declared, frame, capture, facts_by_id,
                             captured_day, stale_words_of, freshness):
    """Owner rulings AC51(R4), AC59(H4), HA5: one reader of both rules.
    Marker membership is a class over tier one; the resource exception
    keeps its own three-arm checks and its original words."""
    if not declared:
        return []
    measures = floors.get("archetype_measures") or {}
    failures = []
    for key in ("resource_rule", "holding_rule"):
        rule = measures.get(key) or {}
        if (not rule or declared[0] not in (rule.get("refuses") or ())
                or (rule.get("applies_from") and captured_day
                    < date.fromisoformat(rule["applies_from"]))):
            continue
        markers = (_reserve_ids(rule, facts_by_id) if key == "resource_rule"
                   else [fid for fid in facts_by_id
                         if fid.startswith(tuple(rule.get("marker_prefixes")
                                                 or ()))])
        if key == "resource_rule":
            failures.extend(_producer_fit_failures(
                rule, markers, floors, declared, frame, capture, facts_by_id,
                stale_words_of, freshness))
        elif markers:
            failures.append((
                "the holding archetype for a company whose value is stakes",
                "owner ruling AC59(H4): a company whose value is the stakes "
                "it owns is rated on its discount to what it owns - never "
                "on earnings, never as a growth company - and the frame "
                "declares '%s' while the pack carries %s"
                % (declared[0], ", ".join("'%s'" % fid for fid in markers)),
                "the archetype '%s' in the business frame, with nav_bridge"
                % rule["holding_archetype"]))
    return failures


def _producer_fit_failures(rule, reserves, floors, declared, frame, capture,
                           facts_by_id, stale_words_of, freshness):
    """AC51(R4): the resource rule's exception and original refusal."""
    archetype = declared[0]
    block = frame.get("integrated_major")
    if (archetype == gate._INTEGRATED_MAJOR_ARCHETYPE
            and isinstance(block, dict)):
        products = (floors.get("archetype_measures") or {}).get(
            "resource_products") or {}
        return _integrated_major_failures(
            rule, block, facts_by_id, stale_words_of, products,
            integrated_major_prices(rule, products, [
                fact["id"] for fact in capture["tier1"]], floors), floors, freshness)
    if not reserves:
        return []
    why = ("owner ruling AC51(R4): a company that reports reserves and earns "
           "from what it extracts is rated as a producer - never on earnings "
           "at the top of the cycle, never as a growth company - and the "
           "frame declares '%s' while the pack carries the reserves %s"
           % (archetype, ", ".join("'%s'" % fid for fid in reserves)))
    where = ("the archetype '%s' in the business frame, with its "
             "producer_subtype and resource_base" % rule["producer_archetype"])
    if archetype == gate._INTEGRATED_MAJOR_ARCHETYPE:
        why += ("; an integrated oil major is rated as a profit-maker only "
                "with the integrated_major block, which this frame does not "
                "carry (owner ruling AC52(1))")
        where += (" - or, for an integrated oil major, the frame's "
                  "integrated_major block")
    return [("the producer archetype for a company that reports reserves",
             why, where)]


# The architect's ruling on P-RESOURCEc-3 (owner ruling AC52(1): an
# integrated major is rated as a profit-maker "with its reserves and today's
# commodity price shown beside"): today's price of an integrated oil major is
# a price of one of these products, named in its id as a whole word (the name
# rule of sub-charge (b)), in the product's price unit from the floors.
def integrated_major_kind(floors):
    """Architect fix round 2 item 8: the subtype with oil-equivalent units,
    and its product list, read from the producer's existing measure data."""
    measures = floors.get("archetype_measures") or {}
    rule = measures.get("resource_rule") or {}
    row = (measures.get("table") or {}).get(rule.get("producer_archetype")) or {}
    return next((name, data) for name, data in (row.get("subtypes") or {}).items()
                if data.get("boe_unit"))


def integrated_major_prices(rule, products, tier1_order, floors):
    """[(fact id, product)] in the pack's order: every today's-price fact
    (the resource rule's reference_price_fact family) naming crude oil or
    natural gas as a whole word - the one set the three-arm test reads and
    the integrated major's pages print."""
    prefixes = tuple((rule.get("block_families") or {}).get(
        "reference_price_fact") or ())
    found = []
    for fid in tier1_order:
        named = [product for product in integrated_major_kind(floors)[1]["products"]
                 if product in products and "_%s_" % product in "_%s_" % fid]
        if prefixes and fid.startswith(prefixes) and named:
            found.append((fid, named[0]))
    return found


def _integrated_major_failures(rule, block, facts_by_id, stale_words_of,
                               products, prices, floors, freshness):
    """The integrated oil major's three-arm test (owner ruling AC52(1) as
    amended; the architect's session-2 ruling on the arms): each arm's share
    fact is known by its id's prefix, as data; upstream production and
    downstream refining and marketing are each at or above the floors'
    share of group capital employed, in percent; midstream is measured only
    where the block names its share fact. Its evidence facts, required
    always, are the contract's and the gate's. A failed arm refuses naming
    the arm and its figure or its id, and points at the producer.
    Every fact the block names is checked here as one class, in one loop
    (audit round 1, r1-8; the architect's ruling on P-RESOURCEa-14): it is
    read only fresh at capture, and each arm share is also a number in
    percent from 0 to 100 - a stale or impossible share is refused by name
    and never set against the threshold. The arms' sum is deliberately not
    bounded: a segment note's corporate and eliminations lines can be
    negative, so honest arm shares may total over 100, and the evidence
    auditor checks the figures against the segment note.
    Today's price (the architect's ruling on P-RESOURCEc-3) is read in the
    same loop: every fact `prices` names (integrated_major_prices) is fresh
    at capture under a rule no looser than its product's, and a number in
    its product's price unit; at least one is carried."""
    failures = []
    prefixes = rule.get("integrated_major_arm_prefixes") or {}
    least = decimal.Decimal(str(rule["integrated_major_min_share"]))
    downstream = rule["integrated_major_downstream_words"]
    words = {"upstream": "upstream production",
             "downstream": "downstream " + downstream,
             "midstream": "midstream"}
    producer = "the archetype '%s' in the business frame" % (
        rule["producer_archetype"])
    test = ("owner ruling AC52(1) as amended: an integrated oil major's "
            "upstream production and downstream %s arms are each at or above "
            "%s percent of the group's capital employed over the last three "
            "financial years combined, midstream too where the company "
            "reports it as its own segment" % (downstream, least))
    beside = ("owner ruling AC52(1): an integrated oil major is rated as a "
              "profit-maker with its reserves and today's commodity price "
              "shown beside")
    named = [(arm, block.get(arm + "_share_fact"))
             for arm in ("upstream", "downstream", "midstream")]
    named += [(None, fid) for fid in
              block.get("midstream_evidence_facts") or ()]
    named += [(("price", product), fid) for fid, product in prices]
    # P-RESOURCEc-6..9: the same role-tagged class includes every printed
    # reserve, in its own product's physical unit, with its own date.
    reserves = _reserve_ids(rule, facts_by_id)
    named += [("reserve", fid) for fid in reserves]
    tagged = {}
    for arm, fid in named:
        if isinstance(fid, str) and fid in facts_by_id:
            tagged.setdefault(fid, set()).add(
                "reported_reserve" if arm == "reserve" else
                "reference_price_fact" if isinstance(arm, tuple) else
                "integrated_" + (arm or "evidence"))
    if _ROLE_SINK is not None:
        _ROLE_SINK.update(tagged)
    subtype, subtype_row = integrated_major_kind(floors)
    units = _producer_units(floors, (rule["producer_archetype"], subtype),
                            {"resource_base": {"product": subtype_row["products"][0]}})
    for arm, fid in named:
        if not isinstance(fid, str):
            continue
        if arm == "reserve":
            fact = facts_by_id[fid]
            own = [product for product in products
                   if "_%s_" % product in "_%s_" % fid]
            allowed = ({products[own[0]]["unit"]} if len(own) == 1
                       else units["quantities"])
            failures.extend(_resource_reserve_failures(
                fid, fact, rule, freshness, allowed))
            stale = stale_words_of(fid)
            if stale is not None:
                failures.append(("a fresh reading of '%s'" % fid, stale,
                                 "a fresher reading of '%s' from the reserve report" % fid))
            continue
        price = arm[1] if isinstance(arm, tuple) else None
        today = ("today's price of %s beside an integrated oil major"
                 % price.replace("_", " ") if price else None)
        prefix = (prefixes.get(arm) or "") if arm and not price else ""
        if arm and not price and not fid.startswith(prefix):
            failures.append((
                "a share fact for the %s arm of an integrated oil major"
                % words[arm],
                "%s - each arm's share is known by its fact id's prefix, "
                "'%s' for the %s arm, and the block names '%s'%s"
                % (test, prefix, arm, fid,
                   "; the downstream arm is %s, a chemicals arm is not "
                   "downstream" % downstream if arm == "downstream" else ""),
                "integrated_major.%s_share_fact: a fact whose id starts "
                "'%s', or %s" % (arm, prefix, producer)))
            continue
        fact = facts_by_id.get(fid)
        if fact is None:
            continue
        stale = stale_words_of(fid)
        if stale is not None:
            failures.append((
                "a fresh reading of %s" % (
                    today if price else
                    "the %s arm's share of capital employed" % words[arm]
                    if arm else
                    "the midstream evidence of an integrated oil major"),
                "%s - %s%s" % (
                    beside if price else test, "" if arm else "its midstream "
                    "is shown by the company's own reported pipeline, "
                    "processing or LNG assets, ", "and " + stale),
                "a fresher reading of '%s' from the source that produced it"
                % fid))
            continue
        if price:
            data = products[price]
            ceiling = data.get("max_price_freshness_days")
            if (gate._decimal_or_none(fact["value"]) is None
                    or fact.get("unit") != data["price_unit"]):
                failures.append((
                    "%s, a number in %s" % (today, data["price_unit"]),
                    "%s - and '%s' is recorded as '%s' in %s; the council "
                    "converts no units" % (beside, fid, fact["value"],
                                           fact.get("unit")),
                    "'%s' as a number in %s" % (fid, data["price_unit"])))
            elif (ceiling is not None
                  and fact["freshness_rule_days"] > ceiling):
                failures.append((
                    "%s, read under a rule no looser than %s days"
                    % (today, ceiling),
                    "%s - and '%s' declares a %s-day rule, so a price that "
                    "old would still read as today's" % (
                        beside, fid, fact["freshness_rule_days"]),
                    "'%s' dated at the sitting from %s, its freshness rule "
                    "at most %s days" % (fid, data.get("benchmark_words"),
                                         ceiling)))
            continue
        if arm is None:
            continue
        value = gate._decimal_or_none(fact["value"])
        if value is None or fact.get("unit") != "percent":
            failures.append((
                "the %s arm's share of capital employed in percent"
                % words[arm],
                "%s - and '%s' is recorded as '%s' in %s, so the arm "
                "cannot be set against the share"
                % (test, fid, fact["value"], fact.get("unit")),
                "'%s' as a number in percent" % fid))
        elif not 0 <= value <= 100:
            failures.append((
                "the %s arm's share of capital employed as a percent from 0 "
                "to 100" % words[arm],
                "%s - and '%s' is %s percent, which no share of the group's "
                "capital employed can be, so the arm cannot be set against "
                "the share" % (test, fid, fact["value"]),
                "'%s' as the arm's share from the segment note, from 0 to "
                "100 percent" % fid))
        elif value < least:
            failures.append((
                "the %s arm at or above %s percent of capital employed"
                % (words[arm], least),
                "%s - and the %s arm's share '%s' is %s percent, so the "
                "company is not an integrated major and is rated as a "
                "producer" % (test, arm, fid, fact["value"]),
                "%s, or an arm share at or above %s percent"
                % (producer, least)))
    if not prices:
        failures.append((
            "today's price of crude oil or natural gas beside an integrated "
            "oil major",
            "%s - and the pack carries no '%s' fact naming crude oil or "
            "natural gas" % (beside, "' or '".join(
                (rule.get("block_families") or {}).get(
                    "reference_price_fact") or ())),
            "a today's-price fact such as 'reference_price_crude_oil' or "
            "'reference_price_natural_gas', dated at the sitting, in %s"
            % " or ".join(products[product]["price_unit"] for product in
                          subtype_row["products"] if product in products)))
    return failures


def _resource_reserve_failures(fid, fact, rule, freshness, allowed=None):
    """AC53(R12), P-RESOURCEc-6..9: the per-reserve properties of the ONE
    printed-fact class, shared by producers and integrated majors. Units
    for producers are checked with their other role units in the caller."""
    failures = []
    value = gate._decimal_or_none(fact["value"])
    if value is None:
        failures.append((
            "a number the council can read as '%s'" % fid,
            "owner rulings AC52(R5) and AC53(R9): reserves are printed as "
            "numbers, and '%s' reads '%s'" % (fid, fact["value"]),
            "'%s' as the figure its source states, a plain number" % fid))
    elif value < 0:
        failures.append((
            "reserves at or above zero: '%s'" % fid,
            "owner ruling AC52(R5): '%s' is %s - below zero, which no "
            "reserve report can show" % (fid, value),
            "'%s' as the reserves the report states, in its own unit" % fid))
    if allowed is not None and fact.get("unit") not in allowed:
        failures.append((
            "'%s' in its product's physical unit" % fid,
            "owner ruling AC52(R6): reserves are a physical amount, and "
            "'%s' is recorded in %s; the council converts no units"
            % (fid, fact.get("unit")),
            "'%s' recorded in %s" % (fid, " or ".join(sorted(allowed)))))
    most = rule.get("reserve_max_age_days")
    age = (freshness.get(fid) or {}).get("age_days")
    if most is not None and age is not None and age > most:
        failures.append((
            "a reserve figure no older than %s days: '%s'" % (most, fid),
            "owner ruling AC53(R12): reserve figures are at most %s days "
            "old at the sitting, and '%s' is dated %d days before the "
            "capture" % (most, fid, age),
            "the latest annual reserve report, dated within %s days of "
            "the sitting" % most))
    return failures


def _producer_unit_failures(row, rating, counted, facts_by_id):
    """The yardstick's halves (the dispatch update's item 3, the architect's
    ruling on P-GROWTHc-4 applied to the producer; owner rulings AC52(R5)
    and (R6)): the enterprise value and the cash flow it is divided by are
    recorded in one unit, and the reserves in the unit the floors count the
    product in - the sub-type's boe_unit for oil and gas, else the
    product's own - or the council refuses by name; it converts no units.
    A product off the floors' list (`counted` None) is refused by name in
    _producer_failures, which calls this."""
    failures = []
    roles = dict(zip(row.get("denominator_roles") or (),
                     (rating or {}).get("subject_denominator_facts") or ()))
    halves = [fid for fid in (row.get("subject_numerator"),
                              roles.get("cash_flow")) if isinstance(fid, str)]
    units = _runway_units(_dedupe(halves), facts_by_id)
    if len(units) == 2 and units[0][1] != units[1][1]:
        failures.append((
            "one unit for the enterprise value and the cash flow of the "
            "producer's yardstick",
            "owner ruling AC52(R5): the producer's yardstick divides the "
            "enterprise value by the last four quarters' operating cash "
            "flow, and they are recorded in different units - %s - so no "
            "multiple can be struck from them"
            % ", ".join("'%s' in %s" % (fid, unit) for fid, unit in units),
            "the yardstick's enterprise value and operating cash flow "
            "recorded in one unit"))
    wanted = (counted or {}).get("unit")
    reserves = roles.get("reserves")
    fact = facts_by_id.get(reserves) if isinstance(reserves, str) else None
    if wanted and fact is not None and fact.get("unit") != wanted:
        failures.append((
            "the reserves in the unit the floors count them in",
            "owner ruling AC52(R6): a producer's reserves are counted in "
            "the commodity's own unit - %s here - and '%s' is recorded in "
            "%s; the council converts no units"
            % (wanted, reserves, fact.get("unit")),
            "'%s' recorded in %s" % (reserves, wanted)))
    return failures


# The producer's own output and quarterly families (owner rulings AC54(R14)
# and (R16)): the last four quarters' output the reserve life is read
# against, the prefix a by-product's own output starts with, and the two
# quarterly families of the evidence list's first floor, each with its words.
_PRODUCER_OUTPUT_TTM = "production_ttm"
_PRODUCER_OUTPUT_PREFIX = "production_"
_PRODUCER_QUARTERS = (("production_quarter_", "output"),
                      ("realized_price_quarter_", "price received"))
# The headline quarterly figure of each family above, in the same order.
_PRODUCER_HEADLINES = ("production_q", "realized_price_q")
# What the producer pages print beside the rule's own figures (the
# architect's ruling on P-RESOURCEc-4 and -5): each read as a number, fresh.
_PRODUCER_YEAR_AGO = ("production_prior_year_q", "realized_price_prior_year_q")
_PRODUCER_STANDARDIZED = "standardized_measure"
_PRODUCER_BALANCE = ("total_debt_mrq_end", "cash_and_investments_mrq_end",
                     "asset_retirement_obligation")


def _reserve_ids(rule, fact_ids):
    """The ids among `fact_ids` that are reported reserves: starting with
    the rule's reserve_prefix and never with its reserve_history_prefix, a
    past year-end's figure (the architect's ruling on P-RESOURCEa-2) - the
    one place the reserve prefix is read."""
    prefix = rule.get("reserve_prefix") or ""
    history = rule.get("reserve_history_prefix")
    return [fid for fid in fact_ids if isinstance(fid, str) and prefix
            and fid.startswith(prefix) and len(fid) > len(prefix)
            and not (history and fid.startswith(history))]


def _producer_units(floors, declared, frame):
    """The units a producer's figures are counted in (owner ruling AC52(R6);
    lesson 2: one function reads every unit against the floors' product
    list, for the subject and every peer): {"product", "unit" - the rated
    reserves' unit, the sub-type's boe_unit for oil and gas, else the
    product's own - "price_unit", "quantities" - the units a reserve or
    output figure may be counted in - "costs" - the units a unit cost may
    be stated in - and "product_data"}, or None where the frame's product
    is off the floors' list. The council converts no units."""
    measures = floors.get("archetype_measures") or {}
    row = (((((measures.get("table") or {}).get(declared[0]) or {})
             .get("subtypes") or {}).get(declared[1])) or {})
    product = ((frame or {}).get("resource_base") or {}).get("product")
    data = ((measures.get("resource_products") or {}).get(product)
            if isinstance(product, str) else None)
    if not isinstance(data, dict):
        return None
    boe = row.get("boe_unit")
    return {"product": product, "unit": boe or data["unit"],
            "price_unit": data["price_unit"],
            "quantities": {unit for unit in (data["unit"], boe) if unit},
            "costs": {unit for unit in (data["price_unit"],
                                        row.get("boe_price_unit")) if unit},
            "product_data": data}


def resource_product_names(fid, commodities):
    """Round 4: consume each whole compound occurrence, longest first,
    retaining a shorter commodity when it also occurs separately."""
    alternatives = "|".join(re.escape(name) for name in sorted(
        commodities, key=lambda name: (-len(name), name)))
    return sorted(set(re.findall(r"(?<![^_])(%s)(?=_|$)" % alternatives, fid))) if alternatives else []


def _resource_reserve_naming_failure(fid, named, product, main):
    """AC52(R6), round 4: ONE naming class for every subject reserve role."""
    if len(named) == 1 and (not main or named == [product]):
        return None
    return (("a fact of the main product, '%s', naming no other commodity: '%s'"
             % (product, fid) if main else "a reserve naming exactly one commodity: '%s'" % fid),
            "owner rulings AC52(R6) and AC53(R9): '%s' names %s; every reserve "
            "names exactly one listed or declared commodity, shown apart"
            % (fid, ", ".join("'%s'" % name.replace("_", " ") for name in named)
               or "no listed or declared commodity"),
            "'%s' for one listed or declared commodity alone, from its reserve report" % fid)


def _by_product_units_seen(rule, product, tier1_order, facts_by_id):
    """AC56(1), fix round 3: the ONE reading of a by-product's quantity units."""
    named = [fid for fid in tier1_order if "_%s_" % product in "_%s_" % fid]
    counted = _reserve_ids(rule, named) + [fid for fid in named
                                         if fid.startswith(_PRODUCER_OUTPUT_PREFIX)]
    return sorted({str(facts_by_id[fid].get("unit")) for fid in counted})


def resource_price_terms(floors, frame, facts_by_id, product):
    """AC56(1), AC37, architect fix round 2: the ONE decision whether a
    product's prices are checkable, with their unit and freshness data."""
    measures = floors.get("archetype_measures") or {}
    products = measures.get("resource_products") or {}
    if product in products:
        return products[product]
    rule = measures.get("resource_rule") or {}
    block = frame.get("resource_base") or {}
    if product not in (block.get("by_products") or ()):
        return None
    units = _by_product_units_seen(rule, product, facts_by_id, facts_by_id)
    if len(units) != 1 or units[0] not in (rule.get("by_product_units") or ()):
        return None
    return {"unit": units[0],
            "price_unit": rule["by_product_price_unit_prefix"] + units[0],
            "max_price_freshness_days": rule["by_product_price_freshness_days"]}


def resource_reserve_prices(floors, frame, facts_by_id, reserve_id, field):
    """AC53(R9), architect fix round 2: the price ids beside this reserve,
    shared by the rule's missing-price check and the row builder."""
    block = frame.get("resource_base") or {}
    measures = floors.get("archetype_measures") or {}
    rule = measures.get("resource_rule") or {}
    commodities = set(measures.get("resource_products") or {}) | set(
        block.get("by_products") or ())
    named = resource_product_names(reserve_id, commodities)
    if not named or named == [block.get("product")]:
        cited = block.get(field)
        return [fid for fid in ([cited] if isinstance(cited, str) else cited or ())
                if isinstance(fid, str)]
    if len(named) != 1 or not resource_price_terms(floors, frame, facts_by_id, named[0]):
        return []
    prefixes = tuple((rule.get("block_families") or {}).get(field) or ())
    return [fid for fid in facts_by_id if prefixes and fid.startswith(prefixes)
            and resource_product_names(fid, commodities) == named]


def _producer_frame(floors, capture):
    """(declared, frame) for a single name whose frame declares the producer
    archetype with a sub-type the table knows, else None."""
    declared = _declared_archetype(floors, capture)
    if (not declared or declared[0] != gate._PRODUCER_ARCHETYPE
            or declared[1] is None):
        return None
    frame = (capture.get("business_frame") or {}).get(
        capture["subject"].get("ticker"))
    return (declared, frame) if isinstance(frame, dict) else None


def resource_readings(pack, floors):
    """The producer's worked-out figures (owner rulings AC52(R5), AC53(R9)
    and AC54(R13); architect ruling B7), or None for any other subject, a
    product off the floors' list or a resource block that cannot be read.

    Returns {"product", "unit", "price_unit", "reserves" (the rated
    denominator's value), "production_ttm", "reserve_life_years",
    "value_per_unit", "reserve_price", "today_price",
    "today_below_reserve_price", "cash_flow_negative"}. Units are read
    through _producer_units only: a reserve or output figure outside the
    product's unit (or the barrel of oil equivalent for oil and gas) reads
    None, the reserve life needs the reserves and the output in ONE unit,
    and a price outside the product's price unit reads None - the council
    never converts. The reserve price is the LOWEST price any cited reserve
    figure was counted at, and today is below it only by exact comparison
    against that lowest price, every cited reserve price read (None where
    any is unreadable). The reserve life (reserves over the last four
    quarters' output) and the value per unit (enterprise value over the
    reserves) are cut toward zero - the life to one place, the value per
    unit to three significant figures in the enterprise value's unit
    (P-RESOURCEc-1) - for printing only - never compared, never written to the pack. The pages and the
    chairman's sentence read this helper; nothing works a figure out
    twice."""
    capture = (pack or {}).get("capture") or {}
    if not capture.get("subject"):
        return None
    found = _producer_frame(floors, capture)
    block = (found[1].get("resource_base") if found else None)
    if not isinstance(block, dict):
        return None
    declared, frame = found
    units = _producer_units(floors, declared, frame)
    if units is None:
        return None
    row = (floors["archetype_measures"]["table"][declared[0]]["subtypes"]
           [declared[1]])
    rating = next((item for item in (capture.get("sufficiency") or {}).get(
        "requirements") or () if item.get("id")
        == "rating_vs_history_or_peers"), {})
    roles = dict(zip(row.get("denominator_roles") or (),
                     rating.get("subject_denominator_facts") or ()))
    facts_by_id = {fact["id"]: fact for fact in capture.get("tier1") or []}

    def amount(fact_id, allowed=None):
        fact = facts_by_id.get(fact_id) if isinstance(fact_id, str) else None
        if fact is None or (allowed is not None
                            and fact.get("unit") not in allowed):
            return None
        return gate._decimal_or_none(fact["value"])

    reserves_id = roles.get("reserves")
    reserves = amount(reserves_id, units["quantities"])
    output = amount(_PRODUCER_OUTPUT_TTM, units["quantities"])
    life = None
    if (reserves is not None and output is not None and reserves >= 0
            and output > 0 and facts_by_id[reserves_id]["unit"]
            == facts_by_id[_PRODUCER_OUTPUT_TTM]["unit"]):
        life = (reserves * 10 // output / 10).quantize(decimal.Decimal("0.1"))
    value = amount(row.get("subject_numerator"))
    per_unit = None
    if value is not None and reserves is not None and reserves > 0:
        # The architect's ruling on P-RESOURCEc-1 (owner ruling AC16): three
        # significant figures, cut toward zero by the exact division, so a
        # positive value in a scaled unit (USD_m over single barrels) never
        # reads 0; written out in plain digits, never an exponent.
        with decimal.localcontext() as exact:
            exact.prec, exact.rounding = 3, decimal.ROUND_DOWN
            per_unit = value / reserves
        if per_unit.as_tuple().exponent > 0:
            per_unit = per_unit.quantize(decimal.Decimal(1))
    price = {units["price_unit"]}
    cited = [amount(fid, price)
             for fid in block.get("reserve_price_facts") or ()]
    lowest = min(cited) if cited and None not in cited else None
    today = amount(block.get("reference_price_fact"), price)
    cash = amount(roles.get("cash_flow"))
    return {"product": units["product"], "unit": units["unit"],
            "price_unit": units["price_unit"], "reserves": reserves,
            "production_ttm": output, "reserve_life_years": life,
            "value_per_unit": per_unit, "reserve_price": lowest,
            "today_price": today,
            "today_below_reserve_price": (None if lowest is None
                                          or today is None
                                          else today < lowest),
            "cash_flow_negative": None if cash is None else cash < 0}


def _line_share(line, facts_by_id):
    """The fact carrying a revenue line's share of the period, read as the
    provenance gate binds it (owner ruling AC12.2): one of the line's own
    facts, or a fact struck only from them, whose value is the share as
    written; None where none is."""
    share = str(line.get("share_of_period")).strip()
    cited = set(line.get("facts") or ())
    for fact_id in line.get("facts") or ():
        fact = facts_by_id.get(fact_id)
        if fact is not None and str(fact["value"]).strip() == share:
            return fact
    for fact_id, fact in facts_by_id.items():
        derived = fact.get("derived")
        if (derived and fact_id not in cited
                and str(fact["value"]).strip() == share
                and all(operand.get("fact_id") in cited
                        for operand in derived.get("operands") or ())):
            return fact
    return None


def _producer_failures(floors, declared, row, frame, rating, capture,
                       facts_by_id, freshness, captured_day, decisive_ids,
                       gap_kinds, stale_words_of, stale_source):
    """Why a producer's frame breaks the rule the floors set for it (owner
    rulings AC51-AC54; the architect's dispatch update of sub-charge b) -
    one (what, why, where) per breach - or nothing where it holds. Each
    rule is stated as a class over every fact the resource_base block
    cites, every peer and every by-product, never a list of ids. The
    block's SHAPE is the provenance gate's. `stale_words_of(fact_id)` and
    `stale_source(fact_id)` (the first stale fact it rests on) are the
    check's own. The
    trailing output is not re-derived here: its arithmetic is declared and
    recomputed where every derived figure is, at the provenance gate."""
    failures = []
    measures = floors.get("archetype_measures") or {}
    rule = measures.get("resource_rule") or {}
    block = frame.get("resource_base")
    block = block if isinstance(block, dict) else {}
    units = _producer_units(floors, declared, frame)
    product = block.get("product")
    roles = dict(zip(row.get("denominator_roles") or (),
                     (rating or {}).get("subject_denominator_facts") or ()))
    peer_roles = dict(zip(row.get("denominator_roles") or (),
                          (rating or {}).get("peer_denominator_metrics")
                          or ()))
    reserves_id = roles.get("reserves")
    tier1_order = [fact["id"] for fact in capture["tier1"]]

    def ids(field):
        named = block.get(field)
        named = [named] if isinstance(named, str) else list(named or ())
        return [fid for fid in named if isinstance(fid, str)]

    def value_of(fact_id):
        fact = facts_by_id.get(fact_id)
        return gate._decimal_or_none(fact["value"]) if fact else None

    def listing(items):
        return " or ".join("'%s'" % item for item in sorted(items))

    # Owner ruling AC51(R3), the P-RESOURCEa-5 refusal: a product off the
    # floors' list is refused with what would make it sittable.
    if units is None:
        failures.append((
            "a main product the owner has ruled on",
            "owner ruling AC51(R3): the council rates producers of %s at "
            "first, anything else refused openly until added - and the "
            "frame's resource_base names '%s'" % (", ".join(
                name.replace("_", " ") for name in sorted(
                    measures.get("resource_products") or {})), product),
            "the owner's ruling adding '%s' to the floors' product list, "
            "with the unit its reserves and output are counted in, the unit "
            "its price is quoted in and its benchmark price - no figure in "
            "this pack can stand in for it" % product))
    # Architect rulings B4 and B12, lesson 1: every fact the block names
    # under a field starts with that field's family.
    families = dict(rule.get("block_families") or {})
    families.update((rule.get("block_families_by_subtype") or {}).get(
        declared[1]) or {})
    words = {"reserve_facts": "the reserves",
             "reserve_price_facts": "the price the reserves were counted at",
             "reference_price_fact": "today's price of the main commodity",
             "unit_cost_facts": "the cost of each unit",
             "hedge_facts": "the hedges",
             "production_facts": "the output",
             "realized_price_facts": "the price received"}
    for field in words:
        if field == "reserve_facts":
            wanted = (rule.get("reserve_prefix") or "",)
            strays = [fid for fid in ids(field)
                      if fid not in _reserve_ids(rule, [fid])]
        else:
            wanted = tuple(families.get(field) or ())
            strays = [fid for fid in ids(field)
                      if wanted and not fid.startswith(wanted)]
        for fid in strays:
            failures.append((
                "a fact of its own family as %s: '%s'" % (words[field], fid),
                "architect ruling B12 under owner rulings AC51-AC54: every "
                "fact the resource_base block names as %s starts with %s%s, "
                "and '%s' does not - so the council would print as %s a "
                "figure that is not one" % (
                    words[field], listing(wanted),
                    ", never '%s', a past year-end's figure"
                    % rule["reserve_history_prefix"]
                    if field == "reserve_facts"
                    and rule.get("reserve_history_prefix") else "",
                    fid, words[field]),
                "resource_base.%s: a fact whose id starts with %s"
                % (field, listing(wanted))))
    if isinstance(reserves_id, str) and reserves_id not in ids(
            "reserve_facts"):
        failures.append((
            "the rated reserves among the resource block's reserve facts",
            "owner ruling AC52(R5): the yardstick divides enterprise value "
            "by the reserves '%s', and the resource_base block's "
            "reserve_facts do not name it - so the reserves rated are not "
            "the reserves the block dates, prices and ages" % reserves_id,
            "resource_base.reserve_facts naming '%s'" % reserves_id))
    # The architect's ruling on P-RESOURCEa-10: the quarterly members read
    # are the latest, counted back from the pack's latest reported period
    # as the four-quarters rule counts them, each fresh.
    quarter_rule = measures.get("profitability_rule") or {}
    quarter_where = ("one '%s' member for each of the latest quarters, the "
                     "id ending in the quarter's period (for example "
                     "_q2_fy2026), from that quarter's report or production "
                     "release")
    chosen = {}
    for prefix, said in _PRODUCER_QUARTERS:
        members = [fid for fid in tier1_order
                   if fid.startswith(prefix) and len(fid) > len(prefix)]
        places, unplaced = _placed_members(members, prefix, "")
        doubled = [fid for place in sorted(places)
                   if len(places[place]) > 1 for fid in places[place]]
        if unplaced or doubled or len({kind for kind, _ in places}) > 1:
            failures.append((
                "the %s of each of the latest quarters, one member per "
                "period" % said,
                "owner ruling AC54(R16): output and the price received are "
                "read quarter by quarter, newest first by their period, and "
                "%s cannot be placed as one member per period of one kind"
                % ", ".join("'%s'" % fid for fid in unplaced + doubled
                            or members),
                quarter_where % prefix))
            continue
        kind, need, wanted = _latest_wanted(capture, places, quarter_rule)
        missing = [number for number in wanted
                   if (kind, number) not in places]
        periods = "quarters" if kind == "quarter" else "half-years"
        if not wanted or missing:
            failures.append((
                "the %s of each of the %d latest %s" % (said, need, periods),
                "owner ruling AC54(R14): whether output is growing and what "
                "each unit earns are read from the %d latest %s, counted "
                "back from the latest period the pack reports, and the pack "
                "carries %s" % (need, periods, (
                    "no '%s' member at all" % prefix if not wanted else
                    "no '%s' member for %s" % (prefix, ", ".join(
                        _period_words(kind, number) for number in missing)))),
                quarter_where % prefix))
            continue
        chosen[prefix] = [places[(kind, number)][0] for number in wanted]
    # The architect's ruling at audit round 5 (replacing the separate
    # readings of audit r1-1, r1-2, r4-2 and r4-5, P-RESOURCEb-6 and -8, the
    # units reads, the freshness loop and the reserves' age): ONE set, built
    # once, of every fact the rule or its standard tests read, each tagged
    # with its role - the block's cited fields, the headlines, the trailing
    # output, the latest quarters chosen above, the yardstick's operands,
    # every fact answering a standard test, every declared by-product's
    # facts and every peer's reserves. Every per-fact property is applied
    # over it by role in one place, below. A figure absent from the pack is
    # refused where it is required (the floors' required ids, the rated
    # denominators), never here.
    products = measures.get("resource_products") or {}
    extras = [extra for extra in block.get("by_products") or ()
              if isinstance(extra, str)]
    tagged = {}

    def tag(role, fids):
        for fid in fids:
            if isinstance(fid, str) and fid in facts_by_id:
                tagged.setdefault(fid, set()).add(role)

    def names(fid, others):
        return resource_product_names(fid, others)

    for field in sorted(set(block) - {"product", "by_products",
                                      "reserves_standard",
                                      "hedge_none_by_design"}):
        tag(field, ids(field))
    tag("headline", _PRODUCER_HEADLINES)
    tag("trailing_output", [_PRODUCER_OUTPUT_TTM])
    for prefix, members in chosen.items():
        tag(prefix, members)
    tag("operand", [row.get("subject_numerator")] + list(roles.values()))
    # A prefix member naming a declared by-product is the by-product's,
    # unless the test's own answer names it (audit r5-1).
    answers = {item.get("id"): item.get("answered_by") or () for item in (
        capture.get("sufficiency") or {}).get("requirements") or ()}
    for test_id, term in _canonical_test_terms(floors, declared).items():
        heads = tuple(head for head in (
            term.get("answered_by_prefix"),
            term.get("answered_by_prefix_where_carried")) if head)
        tag("test", list(term.get("answered_by_ids") or ()) + [
            fid for fid in tier1_order if heads and fid.startswith(heads)
            and (not names(fid, extras) or fid in answers.get(test_id, ()))])
    # Owner ruling AC56(2), P-RESOURCEb-11: a royalty or streaming company's
    # first test reads "the fixed price it pays under each stream", so a
    # lifted test's prefix answer is EVERY fact of that prefix the block
    # cites - each already in the set above under its block role, read
    # there for its number, its unit and its freshness.
    answered = {item.get("id") for item in (capture.get(
        "sufficiency") or {}).get("requirements") or ()
        if item.get("status") == "answered"}
    for test_id, term in sorted((_archetype_lifts(floors, declared).get(
            "canonical_tests") or {}).items()):
        prefix = term.get("answered_by_prefix")
        unanswered = sorted(
            fid for fid, role in tagged.items() if prefix and test_id
            in answered and fid.startswith(prefix) and role & set(block)
            and fid not in answers.get(test_id, ()))
        if unanswered:
            failures.append((
                "every stream payment the resource block cites answering "
                "'%s'" % test_id,
                "owner ruling AC56(2): %s - so each stream payment the "
                "resource block cites answers it, and its answer does not "
                "name %s" % (term["words"][0], ", ".join(
                    "'%s'" % fid for fid in unanswered)),
                "%s's answered_by naming %s" % (test_id, ", ".join(
                    "'%s'" % fid for fid in unanswered))))
    tag("peer_reserve", ["peer_%s__%s" % (peer_roles["reserves"],
                                          subjects.slug(peer["ticker"]))
                         for peer in frame.get("peers") or ()
                         if peer_roles.get("reserves")])
    # Owner ruling AC52(R6), P-RESOURCEa-8 and -9: every peer's figures in
    # the subject's unit - nothing converted.
    if units is not None:
        money = (facts_by_id.get(row.get("subject_numerator")) or {}).get(
            "unit")
        for peer in frame.get("peers") or ():
            slug = subjects.slug(peer["ticker"])
            for metric, unit in ((peer_roles.get("reserves"), units["unit"]),
                                 (row.get("peer_numerator_metric"), money),
                                 (peer_roles.get("cash_flow"), money)):
                pid = "peer_%s__%s" % (metric, slug)
                have = (facts_by_id.get(pid) or {}).get("unit")
                if metric and unit and pid in facts_by_id and have != unit:
                    failures.append((
                        "peer %s's '%s' in the subject's unit"
                        % (peer["ticker"], metric),
                        "owner rulings AC52(R6) and AC54(R15): each peer is "
                        "set beside the subject on the producer's yardstick, "
                        "so its figure is recorded in the unit the "
                        "subject's is - %s - and '%s' is recorded in %s; "
                        "the council converts no units" % (unit, pid, have),
                        "'%s' recorded in %s" % (pid, unit)))
    # The architect's ruling on P-RESOURCEa-12 (AC52(R6)): each by-product
    # is shown apart - a reserve and an output figure of its own, in its own
    # unit, its id naming it - and never summed into the rated figures.
    # Owner ruling AC56(1): only the main product must be on the list; a
    # by-product off it is shown in the one allowed unit its own reserve
    # and output figures are recorded in, never converted - a unit of
    # quantity on the rule's own list (audit r1-1), never money or a share.
    by_product_units = set(rule.get("by_product_units") or ())
    for extra in (extra for extra in block.get("by_products") or ()
                  if isinstance(extra, str)):
        token = "_%s_" % extra
        named = [fid for fid in tier1_order if token in "_%s_" % fid]
        data = products.get(extra)
        unit = data.get("unit") if isinstance(data, dict) else None
        counted = _reserve_ids(rule, named) + [
            fid for fid in named if fid.startswith(_PRODUCER_OUTPUT_PREFIX)]
        seen = _by_product_units_seen(rule, extra, tier1_order, facts_by_id)
        if unit is None and len(seen) == 1 and seen[0] in by_product_units:
            unit = seen[0]
        elif unit is None and len(seen) > 1:
            failures.append((
                "the by-product '%s' in one unit of its own" % extra,
                "owner ruling AC56(1): a by-product off the floors' product "
                "list is shown apart in the unit the company reports it in, "
                "never converted - and its figures are recorded in %d "
                "units: %s" % (len(seen), ", ".join(
                    "'%s' in %s" % (fid, facts_by_id[fid].get("unit"))
                    for fid in counted)),
                "every reserve and output figure naming '%s' recorded in "
                "one unit, as the company reports it" % extra))
        elif unit is None and seen:
            failures.append((
                "the by-product '%s' in a unit of quantity on the floors' "
                "list" % extra,
                "owner ruling AC56(1): a by-product off the product list is "
                "shown in the unit the company reports its quantity in, a "
                "unit on the producer rule's by_product_units - and %s are "
                "recorded in %s, which is not on it" % (", ".join(
                    "'%s'" % fid for fid in counted), seen[0]),
                "the figures naming '%s' in a unit of quantity on the "
                "floors' by_product_units, as the company reports them"
                % extra))
        own = [fid for fid in named
               if unit is not None and facts_by_id[fid].get("unit") == unit]
        # Audit r5-2: its figures are numbers; its other facts (a report
        # date) are read for freshness alone.
        figures = tuple(head for heads in families.values() for head in heads)
        tag("by_product", [fid for fid in named if fid.startswith(figures)])
        tag("by_product_other", named)
        tag("by_product_reserve", _reserve_ids(rule, named))
        lacking = [said for said, have in (
            ("a reserve figure", _reserve_ids(rule, own)),
            ("an output figure", [fid for fid in own if fid.startswith(
                _PRODUCER_OUTPUT_PREFIX)])) if not have]
        if lacking and (unit is not None or not seen):
            failures.append((
                "the by-product '%s' shown apart, with figures of its own"
                % extra,
                "owner ruling AC52(R6): by-products are shown apart and "
                "never converted, so '%s' carries a reserve and an output "
                "figure of its own in %s, each id naming '%s' - and the "
                "pack carries no %s" % (extra, unit or (
                    "the one unit its own figures are recorded in"), extra,
                    " and no ".join(lacking)),
                "a '%s' fact and a '%s' fact naming '%s', each in %s, from "
                "the reserve report and the production release"
                % (rule.get("reserve_prefix"), _PRODUCER_OUTPUT_PREFIX,
                   extra, unit or "one unit of quantity on the floors' "
                   "by_product_units")))
        for rated in (reserves_id, _PRODUCER_OUTPUT_TTM):
            hit = (_rests_on(rated, set(named), facts_by_id)
                   if isinstance(rated, str) else None)
            if hit is not None:
                failures.append((
                    "'%s' without the by-product '%s' summed into it"
                    % (rated, extra),
                    "owner ruling AC52(R6): by-products are shown apart, "
                    "never summed into the rated figure, and '%s' rests on "
                    "'%s'" % (rated, hit),
                    "'%s' struck from the main product alone, the "
                    "by-product shown beside it" % rated))
    # Owner ruling AC53(R12), P-RESOURCEa-6: the reserves no older than the
    # ruled age at the sitting, counted from the report's own date - and
    # every reserve figure and reserve price the block cites no older.
    most = rule.get("reserve_max_age_days")
    report_id = block.get("reserve_report_date_fact")
    report = facts_by_id.get(report_id) if isinstance(report_id, str) else None
    renew = ("the latest annual reserve report (the annual filing's reserves "
             "section or the company's own reserves statement), dated within "
             "%s days of the sitting" % most)
    if most is not None and report is not None:
        try:
            dated = date.fromisoformat(str(report["value"]).strip())
        except ValueError:
            dated = None
        if dated is None or dated > captured_day:
            failures.append((
                "a reserve report date the council can count from",
                "owner ruling AC53(R12): reserve figures are at most %s "
                "days old at the sitting, counted from the latest annual "
                "reserve report's own date, and '%s' reads '%s', which is "
                "no date on or before the capture" % (most, report_id,
                                                      report["value"]),
                "'%s' as the report's effective date, YYYY-MM-DD" % report_id))
        elif (captured_day - dated).days > most:
            failures.append((
                "reserve figures no older than %s days" % most,
                "owner ruling AC53(R12): reserve figures are at most %s days "
                "old at the sitting, counted from the latest annual reserve "
                "report's own date, and '%s' dates the report %s, %d days "
                "before the capture" % (most, report_id, dated,
                                        (captured_day - dated).days),
                renew))
    # The one place every per-fact property is applied, by role: (i) a
    # number (audit r1-2), (ii) the unit its role requires (AC52(R6)),
    # (iii) fresh, one fresh member never vouching for another, (iv) a
    # reserve no older than the ruled age (AC53(R12)) and never below zero
    # (P-RESOURCEa-15; a zero is the denominators' own refusal), (v) a fact
    # read for the main product names it where it is a price (audit r1-1)
    # and never names another listed commodity (P-RESOURCEb-10) - a
    # by-product's own facts are read for the by-product.
    quantities = ("reserve_facts", "production_facts", "trailing_output",
                  _PRODUCER_QUARTERS[0][0], "reported_reserve")
    prices = ("reserve_price_facts", "realized_price_facts",
              "reference_price_fact", _PRODUCER_QUARTERS[1][0])
    unit_rules = [] if units is None else [
        (quantities, units["quantities"], "reserves and output"),
        (prices, {units["price_unit"]}, "prices"),
        (("unit_cost_facts",), units["costs"], "unit costs")]
    # The architect's ruling on P-RESOURCEc-4 and -5 (AC52(R6)): the pages
    # print only facts in this set - every reported reserve, and a reserve
    # naming another listed commodity that is no by-product (oil and gas
    # apart beside the barrel-of-oil-equivalent total) read with that
    # commodity's own prices, in its own units - and the figures beside.
    tag("shown", _PRODUCER_YEAR_AGO + _PRODUCER_BALANCE
        + (_PRODUCER_STANDARDIZED,))
    commodities = sorted(set(products) | set(extras))
    parts = {}
    for fid in _reserve_ids(rule, tier1_order):
        named = names(fid, commodities)
        if set(named) & set(extras):
            continue
        # Audit r2-2: a reserve naming two commodities is the main
        # product's, refused below as naming another.
        if len(named) == 1 and named[0] != product:
            parts[fid] = named[0]
            tag("component_reserve", [fid])
        else:
            tag("reported_reserve", [fid])
    components = set(parts.values())
    for field in ("reserve_price_facts", "reference_price_fact"):
        for fid in tier1_order:
            named = names(fid, commodities)
            if (fid.startswith(tuple(families.get(field) or ()))
                    and len(named) == 1 and named[0] in components | set(extras)
                    and resource_price_terms(floors, frame, facts_by_id, named[0])):
                parts[fid] = named[0]
                tag(("by_product_" if named[0] in extras else "component_")
                    + field, [fid])
    if _ROLE_SINK is not None:
        _ROLE_SINK.update(tagged)
    reserve_roles = {"reserve_facts", "by_product_reserve", "peer_reserve",
                     "reported_reserve", "component_reserve"}
    others = [name for name in products if name != (units or {}).get(
        "product")]
    for fid, role in tagged.items():
        fact, value = facts_by_id[fid], value_of(fid)
        if role & (reserve_roles - {"peer_reserve"}):
            main_reserve = not role & {"by_product_reserve", "component_reserve"}
            named = names(fid, commodities) or ([product] if main_reserve else [])
            naming = _resource_reserve_naming_failure(fid, named, product, main_reserve)
            if naming:
                failures.append(naming)
            for field in ("reserve_price_facts", "reference_price_fact"):
                if naming:
                    continue
                own_product = named[0] if len(named) == 1 else product
                terms = resource_price_terms(floors, frame, facts_by_id, own_product)
                if terms and not any(fid in facts_by_id for fid in resource_reserve_prices(
                        floors, frame, facts_by_id, fid, field)):
                    missing = "%s%s" % ((families.get(field) or [""])[0], own_product)
                    said = ("the price the reserves were counted at" if field ==
                            "reserve_price_facts" else "today's price")
                    lacking = ("the price its %s reserves were counted at" if field ==
                               "reserve_price_facts" else "today's %s price") % own_product.replace("_", " ")
                    source = ("the reserve report" if field == "reserve_price_facts" else
                              terms.get("benchmark_words") or "the source recording today's price")
                    failures.append((
                        "'%s', %s beside '%s'" % (missing, said, fid),
                        "owner ruling AC53(R9), P-RESOURCEc-6: every reserve "
                        "figure prints beside its own reserve price and today's "
                        "price, and '%s' lacks %s" % (fid, lacking),
                        "'%s' from %s" % (missing, source)))
            failures.extend(_resource_reserve_failures(fid, fact, rule, freshness))
        elif "peer_reserve" in role and value is not None and value < 0:
            failures.append((
                "reserves at or above zero: '%s'" % fid,
                "owner ruling AC52(R5): '%s' is %s - below zero, which no reserve report can show"
                % (fid, value), "'%s' as the reserves the report states, in its own unit" % fid))
        if role == {"peer_reserve"}:
            role = set()
        elif value is None and role - (set(block) - set(words)) - {
                "by_product_other"} and not role & reserve_roles:
            failures.append((
                "a number the council can read as '%s'" % fid,
                "owner rulings AC52(R5) and AC53(R9)-(R11): the producer's "
                "figures are read, compared and printed as numbers, and '%s' "
                "reads '%s'" % (fid, fact["value"]),
                "'%s' as the figure its source states, a plain number" % fid))
        for said_roles, allowed, said in unit_rules:
            if role & set(said_roles) and fact.get("unit") not in allowed:
                failures.append((
                    "'%s' in the unit the floors count %s in" % (fid, said),
                    "owner ruling AC52(R6): a producer of %s counts its %s in "
                    "%s - and '%s' is recorded in %s; the council compares "
                    "like with like and converts no units" % (
                        units["product"].replace("_", " "), said,
                        listing(allowed), fid, fact.get("unit")),
                    "'%s' recorded in %s" % (fid, listing(allowed))))
                break
        part = resource_price_terms(floors, frame, facts_by_id, parts.get(fid)) or {}
        allowed = part.get("unit" if "component_reserve" in role
                           else "price_unit")
        if part and fact.get("unit") != allowed:
            said = "reserves" if "component_reserve" in role else "prices"
            failures.append((
                "'%s' in the unit the floors count %s's %s in" % (
                    fid, parts[fid].replace("_", " "), said),
                "owner ruling AC52(R6): the pages print '%s' apart as %s's "
                "own, and %s's %s are counted in %s - it is recorded in %s; "
                "the council converts no units" % (
                    fid, parts[fid].replace("_", " "), parts[fid].replace(
                        "_", " "), said, allowed, fact.get("unit")),
                "'%s' recorded in %s" % (fid, allowed)))
        data = (part if role & {"component_reference_price_fact",
                               "by_product_reference_price_fact"}
                else (units or {}).get("product_data", {})
                if "reference_price_fact" in role else {})
        ceiling = data.get("max_price_freshness_days")
        if ceiling is not None and fact["freshness_rule_days"] > ceiling:
            failures.append((
                "today's price read under a rule no looser than %s days" % ceiling,
                "architect ruling B4 under owner ruling AC53(R9): every reserve "
                "figure is read beside today's price, current within %s days as "
                "the product list rules it, and '%s' declares a %s-day rule - "
                "so a price that old would still read as today's"
                % (ceiling, fid, fact["freshness_rule_days"]),
                "'%s' dated at the sitting from %s, its freshness rule at most "
                "%s days" % (fid, data.get("benchmark_words") or "the source recording today's price", ceiling)))
        if role and stale_words_of(fid) is not None:
            said = dict(_PRODUCER_QUARTERS)
            failures.append((
                "a fresh reading of '%s', %s" % (fid, (
                    "which the frame's resource block cites" if role
                    & set(block) else "one of the latest quarters' %s"
                    % said[min(role & set(said))] if role & set(said)
                    else "which the producer rule or its standard tests "
                    "read")),
                stale_words_of(fid),
                "a fresher reading of '%s' from the source that produced it"
                % (stale_source(fid) or fid)))
        age = (freshness.get(fid) or {}).get("age_days")
        if (role & {"reserve_price_facts", "component_reserve_price_facts",
                    "by_product_reserve_price_facts"}
                and not role & reserve_roles
                and most is not None
                and age is not None and age > most):
            failures.append((
                "a reserve figure no older than %s days: '%s'" % (most, fid),
                "owner ruling AC53(R12): reserve figures are at most %s days "
                "old at the sitting, and '%s' is dated %d days before the "
                "capture" % (most, fid, age), renew))
        main = role - {"by_product", "by_product_reserve",
                       "by_product_other", "component_reserve",
                       "component_reserve_price_facts",
                       "component_reference_price_fact",
                       "by_product_reserve_price_facts",
                       "by_product_reference_price_fact"}
        field = min(main & {"reserve_price_facts", "reference_price_fact"},
                    default=None)
        if units is None or not main:
            continue
        if field and names(fid, [units["product"]]) == []:
            failures.append((
                "the main product's own price as %s: '%s'"
                % (words[field], fid),
                "owner ruling AC53(R9): every reserve figure is read "
                "beside the price it was counted at and today's price "
                "of the main commodity, '%s' - and '%s' does not name "
                "it, so another commodity's price could be read as "
                "its own" % (units["product"], fid),
                "resource_base.%s: a fact whose id names '%s'"
                % (field, units["product"])))
        elif not role & reserve_roles and names(fid, others):
            failures.append((
                "a fact of the main product, '%s', naming no other "
                "commodity: '%s'" % (units["product"], fid),
                "owner rulings AC52(R6) and AC53(R9): the producer's figures "
                "are its main product's, and '%s' names '%s', another "
                "commodity on the product list - a by-product is shown "
                "apart, never read as the main product's"
                % (fid, names(fid, others)[0]),
                "'%s' for '%s' alone, or the other commodity declared in "
                "resource_base.by_products and shown apart"
                % (fid, units["product"])))
    # The architect's ruling on P-RESOURCEb-6 (AC54(R14)): each headline
    # quarterly figure is its family's latest member - the same number in
    # the same unit - or two readings of one quarter differ. An unreadable
    # side is the number check's refusal, just above.
    for (prefix, said), headline in zip(_PRODUCER_QUARTERS,
                                        _PRODUCER_HEADLINES):
        latest = (chosen.get(prefix) or [None])[0]
        if latest is None or headline not in facts_by_id:
            continue
        pair = [(value_of(fid), facts_by_id[fid].get("unit"))
                for fid in (headline, latest)]
        if None in (pair[0][0], pair[1][0]) or pair[0] == pair[1]:
            continue
        failures.append((
            "'%s' equal to its own quarter's '%s'" % (headline, latest),
            "the architect's ruling on P-RESOURCEb-6 under owner ruling "
            "AC54(R14): the latest quarter's %s is one figure, and '%s' "
            "reads %s %s while '%s' reads %s %s" % (
                said, headline, facts_by_id[headline]["value"], pair[0][1],
                latest, facts_by_id[latest]["value"], pair[1][1]),
            "'%s' and '%s' as the same quarter's figure from the same report"
            % (headline, latest)))
    # Architect ruling B4, P-RESOURCEa-7: today's price is read under a rule
    # no looser than the product's own; its staleness is the freshness loop's.
    reference_id = block.get("reference_price_fact")
    # Owner ruling AC53(R11), P-RESOURCEa-13: hedges shown, never netted -
    # 'none' only where no hedge figure is carried and the gap is declared.
    hedge = tuple(families.get("hedge_facts") or ())
    if block.get("hedge_none_by_design") is True and hedge:
        carried = [fid for fid in tier1_order if fid.startswith(hedge)]
        if carried:
            failures.append((
                "no hedge figure beside a company said not to hedge",
                "owner ruling AC53(R11): hedges are shown, never netted, and "
                "'none' is written only where the company does not hedge - "
                "the frame says it does not (hedge_none_by_design), and the "
                "pack carries %s" % ", ".join("'%s'" % fid
                                              for fid in carried),
                "the hedge facts named in resource_base.hedge_facts, or no "
                "fact starting with %s" % listing(hedge)))
        kinds = gap_kinds.get(hedge[0]) or []
        if not kinds or not all(kind == "absent_by_design" for kind in kinds):
            failures.append((
                "the hedges declared absent by design",
                "owner ruling AC53(R11): a company that does not hedge says "
                "so twice - the frame's hedge_none_by_design, and the '%s' "
                "gap declared absent by design - and the pack %s"
                % (hedge[0], "declares no such gap" if not kinds else
                   "declares it for another reason"),
                "a gap for the fact class '%s' with the reason_kind "
                "'absent_by_design'" % hedge[0]))
    carried = [fid for fid in tier1_order if hedge and fid.startswith(hedge)]
    for fid in (fid for fid in list(roles.values())
                + [row.get("subject_numerator")] if isinstance(fid, str)):
        hit = _rests_on(fid, set(carried), facts_by_id) if carried else None
        if hit is not None:
            failures.append((
                "'%s' without a hedge netted into it" % fid,
                "owner ruling AC53(R11): hedges are shown beside the "
                "yardstick, never netted into it, and '%s' rests on '%s'"
                % (fid, hit),
                "'%s' as the company reports it, the hedges shown apart"
                % fid))
    # Architect ruling B11: today's price always decides (the subject's two
    # denominators already must, by the rating measure's own check).
    if isinstance(reference_id, str) and reference_id not in decisive_ids:
        failures.append((
            "a decisive metric resting on today's price",
            "architect ruling B11 under owner ruling AC53(R9): every "
            "reserve figure is read beside today's price of the main "
            "commodity, so that price always decides a producer's case, and "
            "no decisive metric in the business frame rests on '%s'"
            % reference_id,
            "name '%s' in the 'answered_by' of a decisive metric"
            % reference_id))
    # The architect's ruling on P-RESOURCEa-11 (AC51(R1)): the revenue lines
    # of the producer's natures carry more than half of revenue.
    natures = set(rule.get("sales_natures") or ())
    marks = floors.get("prose_figure_marks") or {}
    shares, unread = [], []
    for line in frame.get("how_it_earns") or ():
        carrier = _line_share(line, facts_by_id)
        value = gate._decimal_or_none(carrier["value"]) if carrier else None
        unit = (carrier or {}).get("unit")
        whole = (100 if unit in (marks.get("percent_units") or ()) else
                 1 if unit in (marks.get("fraction_units") or ()) else None)
        if value is None or whole is None:
            unread.append(line["line"])
        else:
            shares.append((line.get("nature"), carrier["id"], value, unit,
                           whole))
    said = ", ".join(sorted(natures))
    if natures and (unread or len({unit for *_, unit, _ in shares}) > 1):
        failures.append((
            "each revenue line's share of revenue, in one unit the council "
            "can read",
            "owner ruling AC51(R1): a producer's sales come mostly from what "
            "it extracts or from royalties and streams, read from each "
            "revenue line's own share fact - and %s" % (
                "no share fact of %s is a number in a percent or fraction "
                "unit" % ", ".join("'%s'" % item for item in unread)
                if unread else "the lines' shares are recorded in %s"
                % ", ".join(sorted({unit for *_, unit, _ in shares}))),
            "each revenue line's share struck as a fact over its own "
            "figures, all in one percent or fraction unit"))
    elif natures and shares:
        own = sum((value for nature, _, value, _, _ in shares
                   if nature in natures), decimal.Decimal(0))
        whole = shares[0][4]
        if not own * 2 > whole:
            failures.append((
                "more than half of revenue from what the producer extracts, "
                "or from royalties and streams",
                "owner ruling AC51(R1): a producer's sales come mostly from "
                "what it extracts under a reserve standard, or from royalties "
                "and streams on others' output - the revenue lines of nature "
                "%s carry more than half of revenue, and here they carry %s "
                "of %s (%s)" % (said, own, whole, ", ".join(
                    "'%s' %s" % (fid, value) for nature, fid, value, _, _
                    in shares if nature in natures) or "no such line"),
                "the archetype in the business frame that fits a company "
                "earning most of its revenue elsewhere, or the revenue "
                "lines' natures and shares as the latest report states them"))
    # The yardstick's halves in one unit (sub-charge a's check, its units
    # read through the same function).
    failures += _producer_unit_failures(row, rating, units, facts_by_id)
    return failures


def _latest_reported_place(capture, kind):
    """The latest period the pack reports, numbered as _period_place
    numbers a `kind` ("quarter" or "half"): a quarter as the gate's
    latest_reported_period reads it; a half as the report names it, or
    the half its quarter or year ends in (owner ruling AC50(1); audit
    finding r1-4). None where the report names no period."""
    latest = gate.latest_reported_period(capture)
    if kind == "quarter":
        return None if latest is None else latest[0] * 4 + latest[1] - 1
    for fact in capture.get("tier1") or []:
        if (isinstance(fact, dict)
                and fact.get("id") == gate._LATEST_REPORT_ID):
            place = _period_place(gate.period_slug(
                str(fact.get("value")).split(",", 1)[0]))
            if place is not None and place[0] == "half":
                return place[1]
            break
    return None if latest is None else (latest[0] * 4 + latest[1] - 1) // 2


def _period_words(kind, number):
    """A placed period in plain words, as the ids spell it."""
    if kind == "half":
        return "h%d fy%d" % (number % 2 + 1, number // 2)
    return "q%d fy%d" % (number % 4 + 1, number // 4)


def _dedupe(items):
    seen = set()
    kept = []
    for item in items:
        if item not in seen:
            seen.add(item)
            kept.append(item)
    return kept


# Where producer_role_set collects the producer rule's role-tagged set.
_ROLE_SINK = None


def producer_role_set(pack, floors):
    """{fact id: roles}: the one role-tagged set the producer rule reads for
    this pack, as check() builds it - empty for any other subject. The
    architect's ruling on P-RESOURCEc-4 and -5: the producer pages print
    only facts in it."""
    global _ROLE_SINK
    _ROLE_SINK = {}
    try:
        check(pack, floors)
        return _ROLE_SINK
    finally:
        _ROLE_SINK = None


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
    declared = _declared_archetype(floors, capture)
    # Owner ruling AC30(1) (G1): for a bank, insurer, reinsurer or
    # financial holding the free-cash test is answered by distributable
    # capital, and its refusal words come from the lifts data block. The
    # guide itself is never changed: every other subject reads it as is.
    # Owner ruling AC50(9): a growth company's three standard tests - the
    # revenue test added to its checklist, the profit and cash tests
    # answered by gross profit and the months of cash - read the same way.
    terms = _canonical_test_terms(floors, declared)
    guide = dict(_CANONICAL_GUIDE)
    for test_id, term in terms.items():
        guide[test_id] = tuple(term["words"])
    test_ids = CANONICAL_TEST_IDS + tuple(
        test_id for test_id in terms if test_id not in CANONICAL_TEST_IDS)

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
    holding_kind = (floors["archetype_measures"].get("holding_rule") or {}).get("holding_archetype")
    holding_data = None
    if declared == (holding_kind, None):
        holding_frame = capture["business_frame"][subject["ticker"]]
        holding_rows = {r["id"]: r for r in capture["sufficiency"]["requirements"]}
        holding_rating = dict(holding_rows.get("rating_vs_history_or_peers") or {})
        holding_rating["cash_answered_by"] = (holding_rows.get("free_cash_flow") or {}).get("answered_by") or []
        holding_day = _as_of_moment(capture["captured_at"]).date()
        holding_data = _holding_roles(floors, holding_frame, holding_rating, facts_by_id,
            holding_day if holding_day >= date.fromisoformat(floors["archetype_measures"]["holding_rule"]["applies_from"]) else None,
            capture["sufficiency"]["requirements"])

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

    def stale_or_none(fact_id):
        """None for a fact fresh through every operand, else the words
        saying it is stale - the rule helpers' reading of freshness."""
        return (stale_words(fact_id) if stale_dependency(fact_id) is not None
                else None)

    satisfied = []
    lifted_by_declared_gap = []
    advisory_missing = []
    missing = []
    notes = []
    open_guided = gate.open_guidance_ids(capture)

    def refuse(what, why_needed, where):
        missing.append({"what": what, "why_needed": why_needed,
                        "where_it_likely_lives": where})

    def refuse_stale_cited(fact_ids, block_words):
        """Every fact a frame block cites is read as the case stands: each
        one fresh, one fresh member never vouching for another (the
        financial institution's and the grower's loop; the producer's reads
        its one set of every fact it reads)."""
        for fact_id in _dedupe(fact_ids):
            if (isinstance(fact_id, str) and fact_id in tier1_rules
                    and not fresh(fact_id)):
                refuse("a fresh reading of '%s', which the frame's %s cites"
                       % (fact_id, block_words),
                       stale_words(fact_id),
                       "a fresher reading of '%s' from the source that "
                       "produced it" % (stale_dependency(fact_id) or fact_id))

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

    def shape_fault(entry, part, fact_id, zero_ok=False):
        return _shape_fault(part, facts_by_id[fact_id],
                            capture["captured_at"],
                            entry.get("window_days"), zero_ok)

    def evaluate_depth(entry):
        """The insider floor's depth (owner ruling AC41(1), as amended of
        record; AC47): True where this settles the entry, False where the
        dealings are judged as before. Under the threshold the three
        summary facts meet the floor, whole and well shaped, beside
        whatever dealings the pack carries; at or over it a summary alone
        refuses and every dealing is judged as before. The summary is
        checked whole only where it is what meets the floor; beside the
        dealings a part is checked for shape, unit, date and freshness
        through the facts it rests on - more is never less at either
        depth. Where the ownership cannot be established
        the floor does not apply, and an insider fact in the pack refuses,
        because the pages then say the insider evidence was not
        considered. No summary, no dealing: the declared gap as before."""
        depth = entry["depth"]
        state, holding = holder_structure(pack, depth)
        family = [i for i in tier1_order if i.startswith(depth["family"])]
        if state == "not_considered":
            if family:
                refuse("no insider fact while the ownership is unknown",
                       "what officers and directors own could not be "
                       "established from the record - the percentage is "
                       "declared absent and no share counts decide it - so "
                       "the insider evidence is not considered, yet the "
                       "pack carries %s; record the ownership (the "
                       "percentage, or %s beside the shares in issue) or "
                       "drop those facts (%s)"
                       % (", ".join(family), depth["group_shares_id"],
                          entry["why"]),
                       entry["likely_source"])
            else:
                notes.append(INSIDER_NOT_CONSIDERED)
            return True
        summary = [i for i in depth["summary"] if i in tier1_rules]
        dealt = any(i.startswith(prefix) for prefix in entry["prefixes"]
                    for i in tier1_order)
        if not summary:
            return False
        captured_day = _as_of_moment(capture["captured_at"]).date()

        def summary_faults(fact_ids):
            """Each named summary part missing, malformed, or not dated on
            the capture's own day - its twelve months end where the
            capture's do (audit round 1, r1-3)."""
            faults = []
            for fact_id in fact_ids:
                if fact_id not in tier1_rules:
                    faults.append("%s: missing" % fact_id)
                    continue
                fault = shape_fault(entry, depth["summary"][fact_id],
                                    fact_id)
                as_of = str(facts_by_id[fact_id].get("as_of"))
                if not fault and _as_of_moment(as_of).date() != captured_day:
                    fault = "dated %s, not on the capture's own day" % as_of
                if fault:
                    faults.append("%s: %s" % (fact_id, fault))
            return faults

        what = "the twelve-month insider summary"
        if dealt and (state == "full"
                      or len(summary) < len(depth["summary"])):
            # The dealings meet the floor here - every dealing at the full
            # depth, the officers' own at the light - so the summary is
            # checked for completeness only where it is what meets it; a
            # part carried beside the dealings is printed as a fact, so it
            # is checked for shape, unit and date and a malformed one
            # refuses by name (audit round 1, r1-4); a part of one rides,
            # more is never less (audit round 5, r5-2). It is read for
            # freshness through the facts it rests on exactly as a whole
            # summary is, so a stale-resting part refuses by name
            # (P-INSIDERDEPTH-5).
            faults = summary_faults(summary)
            if faults:
                refuse(what, "; ".join(faults) + " (%s)" % entry["why"],
                       entry["likely_source"])
            elif not all(fresh(i) for i in summary):
                enforce_stale(entry, what, "; ".join(
                    stale_words(i) for i in summary if not fresh(i)))
            return False
        if state == "full":
            refuse("every insider dealing",
                   "officers and directors together own %s, against a "
                   "threshold of %s%% - at this ownership every dealing is "
                   "carried, and the twelve-month summary does not answer "
                   "the insider floor (%s)"
                   % (holding or "an amount this record does not "
                      "establish", depth["threshold_pct"], entry["why"]),
                   entry["likely_source"])
            return True
        faults = summary_faults(depth["summary"])
        if faults:
            refuse(what, "; ".join(faults) + " (%s)" % entry["why"],
                   entry["likely_source"])
        elif not all(fresh(i) for i in summary):
            enforce_stale(entry, what, "; ".join(
                stale_words(i) for i in summary if not fresh(i)))
        else:
            satisfied.extend(summary)
            notes.append("Insider dealings: officers and directors "
                         "together own %s, under the threshold of %s%%, so "
                         "the twelve-month summary and the chief "
                         "executive's, finance chief's and chair's own "
                         "dealings answer the insider floor."
                         % (holding, depth["threshold_pct"]))
        return not dealt

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
                fault = entry.get("shape") and shape_fault(
                    entry, entry["shape"], fact_id)
                if fault:
                    refuse(fact_id, "%s (%s)" % (fault, entry["why"]),
                           entry["likely_source"])
                elif not fresh(fact_id):
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
            part = (entry.get("shapes") or {}).get(prefix)
            if part and matches:
                # Every match is checked and a malformed one refuses;
                # the one exception is a zero beside one that counts,
                # which neither refuses nor counts (round 3 Step 0 of
                # unit U4(d), P-U4d-6). A bare prefix names no period
                # and never counts (round 5 Step 0, P-U4d-7).
                counting = [i for i in matches if i != prefix
                            and not shape_fault(entry, part, i)]
                faults = [(i, "a fact id must name its period after "
                           + prefix if i == prefix else
                           shape_fault(entry, part, i,
                                       zero_ok=bool(counting)))
                          for i in matches if i not in counting]
                faults = [pair for pair in faults if pair[1]]
                if faults:
                    refuse("a fact whose id starts with '%s'" % prefix,
                           "; ".join("%s: %s" % pair for pair in faults)
                           + " (%s)" % entry["why"],
                           entry["likely_source"])
                    return
                matches = counting
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
            # A promise for a period not yet reported has no outcome to
            # pair with (owner ruling AC45(9)): the floor asks its pair
            # only of a period that has since been reported, so a pack
            # whose only guidance is this year's still owes a reported
            # pair or the declared gap.
            matches = [i for i in tier1_order if i.startswith(prefix)
                       and i not in open_guided]
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
            if entry.get("depth") and evaluate_depth(entry):
                return
            prefixes = entry["prefixes"]
            suffixes = {}
            for prefix in prefixes:
                suffixes[prefix] = {fact_id[len(prefix):]
                                    for fact_id in tier1_order
                                    if fact_id.startswith(prefix)
                                    and len(fact_id) > len(prefix)}
                # A bare prefix names no member (round 5 Step 0,
                # P-U4d-7): where the part is shaped, it refuses.
                if (entry.get("shapes") or {}).get(prefix) and any(
                        fact_id == prefix for fact_id in tier1_order):
                    refuse(prefix, "a dealing's fact id must carry its "
                           "number after %s (%s)" % (prefix, entry["why"]),
                           entry["likely_source"])
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
            holding_gap = (holding_data is not None and prefixes == holding_data[2]
                           and _holding_history(holding_data[1], capture["gaps"], holding_data[2])["gap"])
            if minimum is not None and len(members) < minimum and not holding_gap:
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
            # A member is counted whole or not at all: a fault in any
            # of its parts keeps every part of it out of the count.
            faulty = set()
            for prefix in prefixes:
                part = (entry.get("shapes") or {}).get(prefix)
                for suffix in sorted(suffixes[prefix]):
                    fault = part and shape_fault(entry, part,
                                                 prefix + suffix)
                    if fault:
                        faulty.add(suffix)
                        refuse(prefix + suffix, "%s %s: %s (%s)"
                               % (entry["member_name"], suffix, fault,
                                  entry["why"]),
                               entry["likely_source"])
            for prefix in prefixes:
                for suffix in sorted(suffixes[prefix] - faulty):
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

    # A floor ruled after a capture was made (its `applies_from` date) is
    # not read against it: the capture's own recorded date tells the two
    # apart, so no capture on record is judged by it (owner ruling AC46(2)).
    captured_day = _as_of_moment(capture["captured_at"]).date()
    for entry in entries:
        if (entry.get("applies_from") and captured_day
                < date.fromisoformat(entry["applies_from"])):
            continue
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
    for test_id in test_ids:
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
            term = terms.get(requirement_id)
            if term and requirement["kind"] == "canonical_test":
                for facts, lacks in _test_term_failures(
                        term, answered_by, tier1_order):
                    refuse(requirement_id,
                           "%s: %s - so this test is answered by %s, and "
                           "it %s (%s)"
                           % (term["authority"], guide[requirement_id][0],
                              facts, lacks, description),
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
                   "row: the measure the floors' archetype table gives the "
                   "declared archetype")
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
                # Unit GROWTH-ARCHETYPE, D3: the earning archetypes are
                # read from the table, so the words never go stale.
                earning = [key.replace("_", " ")
                           for key, row in table.items()
                           if isinstance(row, dict)
                           and not row.get("anchorless_only")]
                refuse("an archetype legal for a priced single name",
                       "owner ruling AC15 (P2): '%s' keeps the anchorless "
                       "ladder and is legal only for an asset with no "
                       "earnings; this subject is a priced equity, rated "
                       "on one of the earning archetypes the floors' table "
                       "names - %s" % (archetype, ", ".join(earning)),
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
        # HA5: false-fit rules run once; where one refuses, a pointer to
        # the growth archetype would send this company to a second false fit.
        fit_failures = _archetype_rule_failures(
            floors, declared, frame, capture, facts_by_id, captured_day,
            stale_or_none, freshness)
        if not fit_failures:
            for what, why, where in _profitability_failures(
                    floors, declared, capture, facts_by_id, captured_day):
                refuse(what, why, where)
        for what, why, where in fit_failures:
            refuse(what, why, where)
        changing = (frame.get("what_is_changing") or {}).get("kind")
        # Unit GROWTH-ARCHETYPE, D1: the per-role denominator check is the
        # resolved row's, whatever the archetype; the financial
        # institution's own rules run for the financial institution alone,
        # the denominator check in its old place among them.
        is_fi = (declared is not None and declared[0] == _FI_ARCHETYPE
                 and declared[1] is not None and entry is not None)
        if declared and entry is not None and not is_fi:
            for what, why, where in _denominator_id_failures(
                    entry, rating, archetype.replace("_", " "),
                    entry.get("continuing_suffix") or ""):
                refuse(what, why, where)
            # HA3: any resolved non-FI row requiring the bridge uses the
            # same check; the FI call remains inside its own rules.
            if entry.get("requires_nav_bridge"):
                context = None
                if declared[0] == holding_kind:
                    decisive = {fid for m in frame["decisive_metrics"] for fid in m.get("answered_by") or []}
                    rule = floors["archetype_measures"]["holding_rule"]
                    if captured_day >= date.fromisoformat(rule["applies_from"]):
                        context = (rule, captured_day, decisive)
                tagged, pairs, history = holding_data or _holding_roles(floors, frame, rating or {}, facts_by_id)
                for what, why, where in _nav_bridge_failures(
                        frame, rating, facts_by_id,
                        "owner rulings AC59-AC62, extending AC30(3)",
                        "an investment holding", floors, tagged, pairs, context):
                    refuse(what, why, where)
                if declared[0] == holding_kind:
                    for what, why, where in _holding_failures(
                            floors, frame, rating, capture, facts_by_id,
                            captured_day, decisive, gap_kinds, tagged, pairs, history):
                        refuse(what, why, where)
            # Architect ruling A9 (audit finding r1-2): a row naming the
            # roles its exited business touches rates a changing company
            # on the continuing business's figures only.
            if (changing == "model_transition"
                    and entry.get("exited_business_roles")):
                for what, why, where in _exited_business_failures(
                        entry, rating, entry["exited_business_roles"],
                        entry.get("continuing_suffix") or "",
                        "architect ruling A9",
                        "the continuing business's figure, its id ending "
                        "'%s', as the filing reports it or struck from "
                        "the continuing business's own figures, "
                        "arithmetic shown"
                        % (entry.get("continuing_suffix") or "")):
                    refuse(what, why, where)
        # Owner rulings AC50 (4), (5) and (7), architect ruling A10: the
        # growth company's own rules, for the growth company alone - its
        # months-of-cash block against the floors, its cash, burn and growth
        # always decisive, and no loss on every sale. Below the line the
        # rating is capped at publication, never refused (AC50(8)).
        if (declared is not None and declared[0] == _GROWER_ARCHETYPE
                and entry is not None and declared[1] is not None):
            decisive_ids = set()
            for metric_row in frame["decisive_metrics"]:
                decisive_ids.update(metric_row.get("answered_by") or [])
            for what, why, where in _grower_failures(
                    floors, entry, frame, rating, decisive_ids, facts_by_id):
                refuse(what, why, where)
            # Every figure the months of cash left are counted from, or the
            # block shows beside them, is read as the case stands: one
            # fresh member never vouches for another.
            block = frame.get("growth_runway")
            block = block if isinstance(block, dict) else {}
            refuse_stale_cited(
                list(block.get("cash_facts") or ())
                + [block.get("operating_cash_flow_fact"),
                   block.get("capital_expenditure_fact")]
                + list(block.get("undrawn_facility_facts") or ()),
                "months-of-cash block")
        # Owner rulings AC51-AC54 (sub-charge b): the producer's own rules,
        # for the producer alone - the product listed, one unit throughout,
        # the families, the reserves' age, today's price, the hedges, the
        # latest quarters, the by-products, what it mostly sells, today's
        # price always decisive, no reserve below zero, the yardstick's
        # halves in one unit - and every fact its resource block cites read
        # as the case stands: one fresh member never vouches for another.
        if (declared is not None and entry is not None
                and declared[1] is not None
                and declared[0] == gate._PRODUCER_ARCHETYPE):
            decisive_ids = set()
            for metric_row in frame["decisive_metrics"]:
                decisive_ids.update(metric_row.get("answered_by") or [])
            for what, why, where in _producer_failures(
                    floors, declared, entry, frame, rating, capture,
                    facts_by_id, freshness, captured_day, decisive_ids,
                    gap_kinds, stale_or_none, stale_dependency):
                refuse(what, why, where)
        if is_fi:
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
                refuse_stale_cited(cited, block_words)
        banned = archetype_data.get("forbidden_on_model_transition") or {}
        # A family named by prefix (the quarterly revenue members, owner
        # ruling AC49(1), architect ruling A9) is banned member by member.
        banned_prefixes = tuple(banned.get("trailing_revenue_prefixes")
                                or ())
        forbidden = list(banned.get("trailing_revenue_fact_ids") or [])
        forbidden += [fact_id for fact_id in tier1_order
                      if banned_prefixes
                      and fact_id.startswith(banned_prefixes)]
        # A CONTINUING fact - its id ending in the resolved row's
        # continuing suffix (the financial institution's in its
        # exited-business block), its derivation accepted by the gate - is
        # the continuing business's figure: its operands are the arithmetic
        # that removes the exited part, not a reliance on it, so the walk
        # stops there (the architect's ruling on audit findings r1-3 and
        # r2-1, replacing the r1-3 exemption of the member alone).
        if is_fi:
            kept_suffix = (archetype_data.get("fi_exited_business")
                           or {}).get("continuing_suffix") or ""
        else:
            kept_suffix = (entry or {}).get("continuing_suffix") or ""

        def rests_on_forbidden(fact_id):
            """The first forbidden trailing-revenue fact this rating fact
            rests on - itself or an operand, transitively, never through a
            continuing fact - or None. A derived fact struck from the
            exited business's revenue is that revenue, however many
            operands deep (owner ruling AC15 P2; the same operand walk
            stale_dependency does)."""
            return _rests_on(fact_id, forbidden, facts_by_id,
                             stop_suffix=kept_suffix)

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
                               _class_note(floors, subject), notes)
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
                     missing, class_note=None, notes=()):
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
        lines.extend(notes)
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
