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

CLI:
    python -m council.evidence.sufficiency <pack.json>
        [--floors <floors.json>] [--out <sufficiency-result.json>]
Exit codes: 0 pass, 3 refuse, 1 crash.
"""

import os
import sys
from datetime import datetime

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


def _merged_floors(floors, subject):
    entries = list(floors["classes"][subject["kind"]]["floors"])
    ticker = subject.get("ticker")
    named = floors.get("names", {})
    if ticker and ticker in named:
        entries += list(named[ticker]["floors"])
    return entries


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
    entries = _merged_floors(floors, subject)

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
                "prefix, pairs, parallel_prefixes) - the ruled minimum "
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
        guide_why, guide_where = _CANONICAL_GUIDE[test_id]
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
        if requirement_id in _CANONICAL_GUIDE:
            hint = _CANONICAL_GUIDE[requirement_id][1]
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
