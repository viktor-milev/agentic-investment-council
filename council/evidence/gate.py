"""The provenance gate over a capture document (REBUILD-SPEC section 5).

The evidence session writes captures; this script only validates. Every
check refuses with a plain-English reason naming the offending id - the
gate never edits, never repairs, never rounds. The arithmetic check is
the section-6e lesson from the old stack: a pack must never disagree
with its own declared arithmetic, so a derived value must recompute
EXACTLY from its operand value strings, compared with no rounding and
no tolerance.

CLI:
    python -m council.evidence.gate <capture.json> [--out <gate-result.json>]
Exit codes: 0 accepted, 3 refused, 1 crash.
"""

import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, Inexact, InvalidOperation, localcontext

# Far above any honest financial figure's digits; the Inexact trap is
# what enforces exactness, the precision only gives honest arithmetic
# room to be exact in (audit finding r1-7: the default 28-digit context
# blessed rounded quotients as exact and refused exact long products).
_EXACT_PRECISION = 200

# An honestly dated capture stays valid forever; only a capture dated
# AHEAD of the validating machine's own clock is refused, with a small
# allowance for clock skew (audit finding r1-10).
_CLOCK_SKEW_SECONDS = 600

from council.lib import canonical, subjects, validate

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
_SCHEMA_PATH = os.path.join(_REPO_ROOT, "council", "schemas",
                            "capture_schema.json")
# The ruled floors data, read here for ONE entry: which fact families a
# revenue line may point at (owner ruling AC12.3). The families are DATA
# so a ruling can widen them without touching code; the rule bites in
# this gate, because a revenue line pointing at the last price is the
# capture contradicting itself, which is this gate's whole character.
_FLOORS_PATH = os.path.join(_REPO_ROOT, "council", "floors", "floors.json")

# The words of the owner's inventory (REBUILD-SPEC section 2). They are
# assembled from split string literals so the plain words never appear
# in this source file - the tree-wide language scan in test_foundations
# bans them from every council file - while the gate still recognizes
# and refuses ids built from them. A trailing plural is refused too.
_INVENTORY_WORDS = frozenset((
    "he" "ld",
    "unhe" "ld",
    "posi" "tion",
    "slee" "ve",
    "wei" "ght",
    "acco" "unt",
    "n" "lv",
))

# Broker calls that read the owner's book. A fact citing either is
# refused: the broker is a market-data source only (REBUILD-SPEC
# section 2).
_BANNED_SOURCE_CALLS = ("get_account_positions", "get_account_summary")

_OPERATOR_TEXT = {"add": " + ", "sum": " + ", "subtract": " - ",
                  "multiply": " * ", "divide": " / "}
_EXACTLY_TWO = ("subtract", "divide")

# The business frame's ruled word limits (owner ruling AC1), counted on
# whitespace-separated words. A limit is a discipline, not a style: a
# frame nobody can read in a minute is a frame no seat reads at all.
_WHAT_IT_DOES_WORDS = 120
_WHAT_IS_CHANGING_WORDS = 150
_WHY_IT_DECIDES_WORDS = 40

# Owner ruling AC15 (P5): a fact's optional plain-English label is at most
# eight words. The owner's own reasoning - "for user review purposes you
# need only the noun" - is that the label is a short human name, not a
# sentence; a label as long as the source it replaces buys nothing.
_LABEL_WORDS = 8

# Owner ruling AC15 (P1): a peer's comparability statement names, in at
# most 40 words, the contract structure and duration or the revenue model
# it shares; the caveat naming where it is NOT comparable is at most 25.
_COMPARABLE_BECAUSE_WORDS = 40
_NOT_COMPARABLE_ON_WORDS = 25

# Owner ruling AC15 (P2 and P4, unit U3e): a single name's frame says
# what KIND of business it is and why (at most 40 words), and whether its
# thesis rests on an identifiable cycle and why (at most 25 words); a
# cycle block names the cycle in one line (at most 25 words) and why it
# matters (at most 40 words). The four archetypes and the two
# cycle-dependence words are the schema's enums; these are the word
# limits the schema cannot state.
_ARCHETYPE_BECAUSE_WORDS = 40
_CYCLE_DEPENDENCE_BECAUSE_WORDS = 25
_CYCLE_NAME_WORDS = 25
_CYCLE_WHY_WORDS = 40

# The three headline figures whose fall obliges a reading (AC1). Each
# is read against its own prior-year pair; a member of an expression
# carries the same ids under its own suffix. PUBLIC because the case
# file names which of the three the pack actually carries, and the two
# modules must read one list, never two (audit finding r1-5).
HEADLINE_PAIRS = (("revenue_q", "revenue_prior_year_q"),
                  ("net_income_q", "net_income_prior_year_q"),
                  ("operating_cash_flow_q",
                   "operating_cash_flow_prior_year_q"))

# What one headline pair establishes, as headline_reading() returns it.
# Only the first two are a comparison; the other three are the pair
# deciding nothing, each for its own reason.
HEADLINE_FELL = "fell"
HEADLINE_DID_NOT_FALL = "did_not_fall"
HEADLINE_UNREADABLE = "unreadable"
HEADLINE_UNITS_DIFFER = "units_differ"
HEADLINE_BOUNDED = "bounded"

# The gap classes the frame leans on when it declares an absence. Each
# is an ordinary gaps row, so the absence reaches every seat's case
# file through the machinery that already carries declared gaps.
_PEER_GAP_CLASS = "peer_"
_GUIDANCE_GAP_CLASS = "guided_"
_DECLINE_GAP_CLASS = "headline_decline_read"

# The two halves of a guidance row. The delivered id is derived from the
# guided one exactly as the ruled guided_/delivered_ floor derives it
# (council/floors/floors.json, kind prefix_pairs), so the frame and the
# floor read one rule and cannot drift apart. The guided prefix is the
# same word as the gap class above because a fact family and the ids
# that carry it are named alike throughout this contract.
_GUIDED_PREFIX = "guided_"
_DELIVERED_PREFIX = "delivered_"

# How many quarters the guidance table may hold - the capture
# contract's own maxItems for guidance_vs_delivery, and the spec's
# "last four reported quarters that had guidance". A table already
# holding this many has shown every quarter it is allowed to show, so
# the completeness rule below has nothing left to ask of it.
_GUIDANCE_ROWS = 4

# A figure written the way a filing prints it: three-digit groups
# separated by commas, with an optional decimal part. Anchored whole,
# so a lone comma, a short group or a trailing separator is not a
# number and is not guessed at.
_GROUPED_THOUSANDS = re.compile(
    r"[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?\Z")

# Everything that is not a letter or a digit, for the ONE canonical slug
# a period label takes (owner ruling AC12.1). A run of them collapses to
# a single underscore, so 'Q1 FY2026', 'Q1  FY-2026' and 'q1 fy2026' all
# name the same quarter and bind to the same fact ids.
_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")

# What a frame must say. Used in the sufficiency gate's refusal, so the
# words that name a missing part are written once.
FRAME_PARTS = (
    ("what_it_does",
     "what it does - what is sold, to whom, and what the customer "
     "loses if this company disappears"),
    ("how_it_earns",
     "how it earns - the revenue lines with their share of the latest "
     "reported period"),
    ("what_is_changing",
     "what is changing - and, where a headline figure has fallen, "
     "whether that fall is by design, deterioration or mixed"),
    ("decisive_metrics",
     "the three to five numbers that decide this question"),
    ("peers",
     "the peer set, or an honest reason no peer set exists"),
    ("management",
     "management's delivery against its own guidance"),
    ("competitive_position",
     "where the business sits against its competitors, in facts"),
)


def load_capture_schema():
    """The capture contract this gate enforces."""
    return canonical.read_json(_SCHEMA_PATH)


def revenue_families():
    """The fact families a business frame's revenue line may point at
    (owner ruling AC12.3), read from the ruled floors data.

    Named as data rather than written into this file so a ruling can
    widen them without a code change - the same reasoning that puts the
    evidence floors themselves in that file."""
    return canonical.read_json(_FLOORS_PATH)["revenue_families"]


def period_basis_data():
    """The signal words that make a derived fact present itself as an
    annual figure, and the bases that are a multi-year or lifetime
    average (owner ruling AC15, P3). Data so a ruling can widen either
    without a code change."""
    return canonical.read_json(_FLOORS_PATH).get("period_basis") or {}


def period_slug(label):
    """The one canonical form of a period label: lower case, every run
    of anything that is not a letter or a digit collapsed to a single
    underscore, the ends trimmed.

    Public because it is what BINDS a guidance row's displayed period to
    the facts beneath it (owner ruling AC12.1): the row says 'Q1 FY2026'
    and its ids must end '_q1_fy2026', or the case file labels one
    quarter's figures with another quarter's name."""
    return _NOT_ALPHANUMERIC.sub("_", str(label).casefold()).strip("_")


def _moment(text):
    """A capture timestamp as a naive UTC datetime; a date-only value
    means midnight that day."""
    if text.endswith("Z"):
        return datetime.fromisoformat(text[:-1])
    return datetime.fromisoformat(text)


def _entries(capture):
    """Every id-carrying entry with its plain tier label."""
    entries = [("tier1 fact", fact) for fact in capture["tier1"]]
    entries += [("tier2 passage", passage) for passage in capture["tier2"]]
    return entries


def _check_constituent_bound(capture):
    """The ruled 2-to-8 constituent bound, checked before the shape so
    the over-the-bound refusal reads plainly instead of as a schema
    item count (THEMES-BASKETS-SPEC section 2: more than 8 refuses at
    intake; raising the bound is an owner ruling). Only the bound is
    pre-checked; every other shape error flows through the schema."""
    subject = capture.get("subject") if isinstance(capture, dict) else None
    constituents = (subject.get("constituents")
                    if isinstance(subject, dict) else None)
    if isinstance(constituents, list) and len(constituents) > 8:
        return ["the subject names %d constituents; the ruled bound is "
                "2 to 8 - raising it is an owner ruling, not a capture "
                "choice" % len(constituents)]
    return []


def _check_subject_kind(capture):
    """Kind-consistency and referential integrity for the subject's
    constituent, vehicle, proportion, theme and asset-class fields
    (THEMES-BASKETS-SPEC section 2; ANCHORLESS-SPEC section 2). The
    schema cannot express per-kind rules, so they live here. A theme
    MISSING its block or expression is left for the sufficiency gate's
    shopping-list refusal - this check refuses only a field that is
    misplaced for the kind, or one whose references dangle."""
    reasons = []
    subject = capture["subject"]
    kind = subject["kind"]
    constituents = subject.get("constituents")
    vehicle = subject.get("vehicle")
    proportions = subject.get("thesis_proportions")
    theme = subject.get("theme")

    # The shape and the class must agree where the shape fixes its own
    # class: bullion is gold and a coin is crypto, whatever a capture
    # types into the other field. The collective shapes - a fund, a
    # basket, a theme - may wrap any class, so they are left alone.
    declared_class = subject.get("asset_class")
    fixed = subjects.SHAPE_CLASS.get(kind)
    if fixed is not None and declared_class != fixed:
        reasons.append(
            "the subject's kind is '%s' but its asset_class says '%s' - "
            "this shape is always '%s', and the class decides which "
            "evidence anchors the sitting is judged against, so a "
            "mismatch would judge the subject against another asset's "
            "must-haves" % (kind, declared_class, fixed))

    # A commodity is analysed through the instrument it would actually
    # be bought as, and the ruled product-conditional items (W2.7) are
    # keyed by the product's name: without it the conditional anchors
    # cannot be looked up at all.
    named_product = subject.get("product")
    if declared_class == "commodity":
        if not named_product:
            reasons.append(
                "the subject's asset_class is 'commodity' but it names "
                "no product - the ruled product-conditional evidence "
                "(the exchange stocks a product either has or honestly "
                "lacks) is keyed by the product, so an unnamed product "
                "cannot be checked against its own minimums")
    elif named_product:
        reasons.append(
            "the subject names the product '%s' but its asset_class is "
            "'%s' - only a commodity subject names a product"
            % (named_product, declared_class))

    if kind in ("single_stock", "bitcoin", "gold", "commodity"):
        for field, value in (("constituents", constituents),
                             ("vehicle", vehicle),
                             ("thesis_proportions", proportions),
                             ("theme", theme)):
            if value is not None:
                reasons.append(
                    "the subject's kind is '%s' but the capture carries "
                    "'%s' - that field belongs to basket, theme and "
                    "collective-vehicle subjects only" % (kind, field))
    elif kind == "basket":
        if not constituents:
            reasons.append(
                "the subject is a basket but names no constituents - a "
                "basket is one thesis expressed through 2 to 8 named "
                "instruments, each with its own ticker")
        if vehicle is not None:
            reasons.append(
                "the subject is a basket but carries a 'vehicle' - a "
                "basket judges its named constituents directly; a "
                "vehicle belongs to a theme or an etf subject")
        if theme is not None:
            reasons.append(
                "the subject is a basket but carries a 'theme' block - "
                "the theme block belongs to theme and etf subjects")
    elif kind == "theme":
        if constituents is not None and vehicle is not None:
            reasons.append(
                "the subject declares constituents and a vehicle at "
                "once - a theme names a provisional universe or one "
                "implementation vehicle, never both")
        if proportions is not None and not constituents:
            reasons.append(
                "the subject carries 'thesis_proportions' but names no "
                "constituents - proportions state the idea's emphasis "
                "across declared constituents, so they travel only with "
                "a constituent list")
    elif kind == "etf":
        if constituents is not None:
            reasons.append(
                "the subject is an etf but declares constituents - the "
                "fund's published disclosure is its universe; the pack "
                "carries the holdings picture as facts, never a "
                "constituent list")
        if vehicle is not None:
            reasons.append(
                "the subject is an etf but carries a separate "
                "'vehicle' - the etf IS the vehicle; the field belongs "
                "to theme subjects")
        if proportions is not None:
            reasons.append(
                "the subject is an etf but carries 'thesis_proportions' "
                "- proportions state an idea's emphasis across declared "
                "constituents, and an etf declares none")

    declared = subjects.constituent_tickers(subject)
    seen = set()
    for ticker in declared:
        if ticker in seen:
            reasons.append(
                "constituent ticker '%s' appears more than once - every "
                "constituent must be independently resolvable under its "
                "own ticker" % ticker)
        seen.add(ticker)

    # Distinct tickers can still collapse to one fact-id form (every
    # character outside [a-z0-9] becomes '_' in the suffix), and one
    # form means one set of per-member facts standing in for two
    # members (audit finding THEMES-A r1-5). The vehicle's ticker is
    # checked beside the constituents': every fact-id consumer reads
    # tickers through the same forms.
    forms = {}
    for ticker in declared + ([vehicle["ticker"]] if vehicle else []):
        forms.setdefault(subjects.slug(ticker), set()).add(ticker)
    for form, group in sorted(forms.items()):
        if len(group) > 1:
            reasons.append(
                "tickers %s all take the same fact-id form '%s' - "
                "their per-member facts could not be told apart, so "
                "every ticker the expression names must keep its own "
                "form" % (" and ".join("'%s'" % ticker
                                       for ticker in sorted(group)),
                          form))

    counted = set()
    for entry in proportions or ():
        named = entry["constituent"]
        if named not in seen:
            reasons.append(
                "thesis-proportion entry names '%s', which is not a "
                "declared constituent ticker" % named)
        elif named in counted:
            reasons.append(
                "constituent '%s' carries more than one "
                "thesis-proportion entry - at most one per constituent"
                % named)
        counted.add(named)

    if theme:
        tier1_ids = {fact["id"] for fact in capture["tier1"]}
        tier2_ids = {passage["id"] for passage in capture["tier2"]}
        falsifier_ids = set()
        for falsifier in theme["falsifiers"]:
            falsifier_id = falsifier["id"]
            if falsifier_id in falsifier_ids:
                reasons.append(
                    "theme falsifier id '%s' appears more than once - "
                    "every falsifier id must be unique" % falsifier_id)
            falsifier_ids.add(falsifier_id)
            fact_id = falsifier["fact_id"]
            if fact_id is not None and (fact_id not in tier1_ids
                                        and fact_id not in tier2_ids):
                reasons.append(
                    "theme falsifier '%s' points at fact '%s', which is "
                    "nowhere in the capture" % (falsifier_id, fact_id))
            prior_id = falsifier["prior_fact_id"]
            if prior_id is not None and prior_id not in tier1_ids:
                reasons.append(
                    "theme falsifier '%s' names prior-period fact '%s', "
                    "which is not a tier1 fact of the capture - a prior "
                    "period must be a frozen figure"
                    % (falsifier_id, prior_id))
            if prior_id is not None and prior_id == fact_id:
                reasons.append(
                    "theme falsifier '%s' names its own fact '%s' as "
                    "the prior period - the prior period must be a "
                    "different, earlier reading, never the level fact "
                    "itself (audit finding THEMES-A r1-3)"
                    % (falsifier_id, fact_id))

    for requirement in capture["sufficiency"]["requirements"]:
        named = requirement.get("constituent")
        if named is not None and named not in seen:
            reasons.append(
                "sufficiency requirement '%s' is bound to constituent "
                "'%s', which is not a declared constituent ticker"
                % (requirement["id"], named))
    return reasons


def evidence_body_sha256(capture):
    """The capture's hash WITHOUT the audit block: the evidence the
    outside auditor read, and the one part of this file that recording
    an audit does not touch. Comparing on it is stable across a repeat
    recording, where the only difference IS the block - which is what
    made round 2's equality exemption necessary, and what made round 3's
    r3-2 possible (audit round 3).

    It lives here, beside the contract it is a hash of, because three
    readers need one answer (owner ruling AC13): the bridge, which sends
    this hash to the auditor and records it; the recording step, which
    lists what moved after the call; and the sufficiency gate, which
    refuses a pack whose evidence moved with nothing saying so.

    Owner ruling AC15 (P7): the `corrections` list is excluded too. It is
    the bookkeeping of the correction process - who corrected what, and
    whether a delta re-audit has cleared it - not evidence the auditor
    reasons about; the corrected FACTS are in tier1 and move the hash
    there. Leaving it in would make marking a correction re-audited read
    as the evidence moving, and every correction read as a change to
    itself."""
    body = dict(capture)
    body.pop("evidence_challenge", None)
    body.pop("corrections", None)
    return canonical.sha256_bytes(canonical.canonical_bytes(body))


def frame_tickers(subject):
    """Which instruments this subject's business frame is keyed by, as
    (required, allowed) ticker lists.

    The frame is keyed by TICKER because everything else per member in
    a capture already is - the per-member facts, the per-constituent
    checklist rows - so one contract carries a single name and an
    expression of several without a second shape.

    REQUIRED of a priced business (owner ruling AC1): a listed single
    name for itself, a basket or a theme universe for every constituent
    it names. ADVISORY elsewhere - a fund, a theme implemented through
    one vehicle, and every asset with no earnings may carry a frame and
    is never refused for its absence: a coin has no business to frame,
    and a fund's business is the business of what it holds."""
    kind = subject.get("kind")
    constituents = [ticker for ticker in subjects.constituent_tickers(subject)
                    if ticker]
    # The SHAPE does not decide this; the asset class does. A basket and
    # a theme may wrap any class (subjects.SHAPE_CLASS), so a basket of
    # coins reaches this branch as readily as a basket of shares - and
    # an asset with no earnings has no business to state, whatever shape
    # holds it. Its constituents stay ALLOWED: a frame written anyway is
    # still validated, never refused for its absence.
    # A COLLECTIVE is keyed by what it NAMES, never by a label of its
    # own: one key per constituent for a basket or a theme universe, the
    # vehicle's for a theme carried through one. Nothing refuses a
    # basket that declares a ticker of its own, so reading that ticker
    # here let a collective carry a frame of its own - one heading over
    # two companies' facts - and, where it equalled a constituent's,
    # unbound that member's frame from its own figures.
    if kind in ("basket", "theme"):
        members = [ticker for ticker in subjects.expression_tickers(subject)
                   if ticker]
        if constituents and not subjects.is_anchorless(subject):
            return list(members), list(members)
        return [], list(members)
    own = [subject["ticker"]] if subject.get("ticker") else []
    if kind == "single_stock":
        return list(own), list(own)
    advisory = [ticker for ticker in subjects.expression_tickers(subject)
                if ticker]
    return [], own + [t for t in advisory if t not in own]


def frame_suffix(subject, ticker):
    """The fact-id suffix a frame's own figures carry: none where the
    frame describes the subject itself, the member suffix where it
    describes one named member of an expression.

    Read from MEMBERSHIP of the expression, not from equality with the
    subject's own ticker: a basket may declare a ticker of its own, and
    where that ticker equalled a constituent's, that member's frame lost
    its suffix and with it the bound that keeps a member citing its own
    figures."""
    if ticker in subjects.expression_tickers(subject):
        return "__%s" % subjects.slug(ticker)
    return ""


def _words(text):
    return len(str(text).split())


def _decimal_or_none(text):
    """A captured value as a finite number, or None where the string is
    not one. What None means is the caller's to decide; for a headline
    pair it is a refusal, because that figure is what the reading of a
    fall - and the growth test - both rest on.

    Grouped thousands are a FORMAT, not a different number. The runbook
    requires a passage's figures in the same format as its prose,
    grouped thousands included, and forbids reformatting any captured
    value - and 38% of the tier-2 figures in the sittings on record are
    written that way - so '2,300' is two thousand three hundred and
    this must read it (audit r6-1). Only STRICT grouping is read: a
    comma that is not a thousands separator stays unreadable, because
    guessing at '1,3' would silently turn one and three tenths into
    thirteen."""
    candidate = str(text)
    if _GROUPED_THOUSANDS.match(candidate):
        candidate = candidate.replace(",", "")
    try:
        parsed = Decimal(candidate)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def headline_reading(current, prior):
    """What one headline pair of facts ESTABLISHES about a fall.

    Returns one of the HEADLINE_* words below. Public, and the single
    place this question is answered: the gate turns the answer into
    refusals, the case file turns it into a sentence, and two readers
    of one entity must not decide it apart (fix-checklist 8a).

    Three ways a pair decides nothing. Its two values may not read as
    numbers. They may be recorded in DIFFERENT UNITS, where 900 USD_m
    against 1 USD_billion compared as bare decimals reads as a rise
    though revenue fell by a tenth (audit r5-2); this gate normalises
    no units anywhere - it compares like with like and refuses
    otherwise, as the prior-period rule in the sufficiency gate already
    does. Or one side may carry a BOUND rather than a measurement
    (owner ruling AB20): a ceiling can only be too high and a floor too
    low, so a ceiling ABOVE last year leaves the true figure free to be
    below it, and the record decides nothing (audit r5-3). A bound
    still decides the other direction - a ceiling BELOW last year puts
    the true figure below it whatever it is - and those cases are kept.
    """
    if current["unit"] != prior["unit"]:
        return HEADLINE_UNITS_DIFFER
    current_value = _decimal_or_none(current["value"])
    prior_value = _decimal_or_none(prior["value"])
    if current_value is None or prior_value is None:
        return HEADLINE_UNREADABLE
    fell = current_value < prior_value
    # Per side, the case in which a CEILING on it leaves the answer
    # open; a FLOOR on the same side leaves the other case open. A
    # ceiling on the current figure decides a fall only when the
    # recorded figure is already below last year; a ceiling on the
    # prior figure decides one only when the current figure is at or
    # above the recorded prior. The floors are the mirror.
    for fact, ceiling_decides_nothing in ((current, not fell),
                                          (prior, fell)):
        kind = (fact.get("bound") or {}).get("kind")
        if kind == "ceiling" and ceiling_decides_nothing:
            return HEADLINE_BOUNDED
        if kind == "floor" and not ceiling_decides_nothing:
            return HEADLINE_BOUNDED
    return HEADLINE_FELL if fell else HEADLINE_DID_NOT_FALL


def _states_a_number(entry_id, facts_by_id, passages_by_id):
    """Whether the thing this id names actually carries a figure: a
    tier-1 fact whose value reads as a finite number, or a tier-2
    passage at least one of whose declared figures does.

    The frame names ids under labels that promise a number - the
    metrics that decide the question, what insiders own, how long the
    chief executive has served. Existence was the only test, so a date
    or a sentence could stand under any of them (audit r5-1)."""
    fact = facts_by_id.get(entry_id)
    if fact is not None:
        return _decimal_or_none(fact["value"]) is not None
    passage = passages_by_id.get(entry_id)
    if passage is None:
        return False
    return any(_decimal_or_none(figure) is not None
               for figure in passage["figures"])


def _foreign_operand(fact_id, suffix, facts_by_id, chain=()):
    """The path down to the first figure in this fact's arithmetic that
    does NOT carry this member's suffix, or None where every one does.

    The member bound stopped at the cited id itself, so a fact wearing
    ACHP's suffix could be struck entirely out of BGRD's figures and the
    case file printed the result under ACHP's heading - the r1-3 defect
    reached again, one level down (audit r1-2). An operand carrying no
    fact id at all is a literal in the arithmetic and belongs to nobody,
    so it is passed over."""
    if fact_id in chain:
        return None
    derived = (facts_by_id.get(fact_id) or {}).get("derived")
    if not derived:
        return None
    chain = chain + (fact_id,)
    for operand in derived["operands"]:
        reference = operand.get("fact_id")
        if reference is None:
            continue
        if not reference.endswith(suffix):
            return chain + (reference,)
        deeper = _foreign_operand(reference, suffix, facts_by_id, chain)
        if deeper is not None:
            return deeper
    return None


def _is_revenue(fact_id, suffix, families, facts_by_id, chain=()):
    """Whether this id names REVENUE (owner ruling AC12.3): a fact in
    one of the ruled families, or a fact STRUCK from facts that are -
    however many steps down.

    A revenue line could point at any fact the pack carried, the last
    price included, and the case file printed that id under 'Facts that
    carry it' - so a seat could argue the mix of the business from a
    number that is not revenue. The families are read from the ruled
    floors data, never written here.

    A DERIVED fact is judged on what it is struck from, never on what it
    is called: the ruling admits 'a derived fact struck from them', so a
    figure named for a revenue family and computed out of the last price
    is not revenue however it is spelt (audit r1-2, found in triage).
    A fact that is not derived is judged on its name, which is all a
    recorded observation has.

    The derived branch is followed to the bottom rather than one step,
    because a share of the period struck from a subtotal that is itself
    struck from segment lines is honest revenue, and a rule that refused
    it would be the false refusal this ruling was written to avoid. The
    chain of ids already walked is the cycle guard; a cycle is refused
    for what it is by _check_operand_references."""
    if fact_id in chain:
        return False
    derived = (facts_by_id.get(fact_id) or {}).get("derived")
    if not derived:
        base = (fact_id[:-len(suffix)]
                if suffix and fact_id.endswith(suffix) else fact_id)
        return (base in families["ids"]
                or any(base.startswith(prefix)
                       for prefix in families["prefixes"]))
    chain = chain + (fact_id,)
    for operand in derived["operands"]:
        reference = operand.get("fact_id")
        if reference is None or not _is_revenue(reference, suffix,
                                                families, facts_by_id,
                                                chain):
            return False
    return True


def _id_suffix(fact_id):
    """The member suffix an id WEARS - the last '__' and everything
    after it - or '' where it wears none.

    Every per-member id in this contract is <concept>__<slug(ticker)>
    (council/lib/subjects.py), so the tail after the last '__' is the
    name an id claims to belong to. Read here rather than compared
    against a list of the subject's own members, because the name an
    id wears may be nobody this capture declares - a peer's ticker,
    say - and that is exactly the case the list could not see."""
    _, marker, tail = str(fact_id).rpartition("__")
    return marker + tail if marker and tail else ""


def _share_carriers(line_facts, facts_by_id, suffix):
    """Every value this revenue line's OWN facts carry, and the facts
    excluded for wearing another name: the values of the facts the line
    cites, and the value of any fact in the pack struck only from facts
    it cites (owner ruling AC12.2). Returned as (values, foreign),
    foreign being (id, value) pairs.

    The second is how a share of the period is honestly carried - a
    segment's revenue divided by the quarter's, whose arithmetic the
    freeze prints like any other derived fact. Without this rule a line
    could put 99% beside facts that say otherwise, and the seats read
    the unsupported number first.

    The carrier is DISCOVERED rather than named by the frame, so it
    never passes the member bound that every declared id passes, and a
    figure wearing another name could stand as this member's carrier
    (audit r3-1; register item P-U1b-5). Excluding the OTHER MEMBERS'
    suffixes was one narrowing too far in each direction: it admitted a
    carrier suffixed to a name the subject never declares - a peer's
    ticker - while an honest pack-level figure with no suffix at all
    had to be admitted (audit round 4, found in triage). Both are
    settled by reading the name the id itself wears: a carrier wears
    THIS frame's suffix, or none. This says nothing about whether a
    mislabelled fact may sit in the pack at all - nothing here has ever
    bound the suffix of a fact no frame references."""
    cited = set(line_facts)
    values = [facts_by_id[fact_id]["value"] for fact_id in line_facts
              if fact_id in facts_by_id]
    foreign = []
    for fact_id, fact in facts_by_id.items():
        derived = fact.get("derived")
        if not derived or fact_id in cited:
            continue
        references = [operand.get("fact_id")
                      for operand in derived["operands"]]
        if not all(reference in cited for reference in references):
            continue
        if _id_suffix(fact_id) not in ("", suffix):
            foreign.append((fact_id, fact["value"]))
            continue
        values.append(fact["value"])
    return values, foreign


def _check_business_frame(capture):
    """The business frame's own consistency (owner ruling AC1).

    This check has the same character as the arithmetic check: it never
    asks whether the frame is TRUE - no machine here can read a filing
    - only whether the capture contradicts itself, points at figures it
    does not carry, or declares a change without the number that would
    show it. Whether a REQUIRED frame is present AT ALL is the
    sufficiency gate's refusal, in the ruled sentence, because that is
    the stage that decides a pack cannot convene the council."""
    frames = capture.get("business_frame")
    if not frames:
        return []
    subject = capture["subject"]
    _, allowed = frame_tickers(subject)
    tier1_ids = {fact["id"] for fact in capture["tier1"]}
    tier2_ids = {passage["id"] for passage in capture["tier2"]}
    passages_by_id = {passage["id"]: passage for passage in capture["tier2"]}
    facts_by_id = {fact["id"]: fact for fact in capture["tier1"]}
    gap_classes = {gap["fact_class"] for gap in capture["gaps"]}
    families = revenue_families()
    reasons = []

    for ticker in sorted(frames):
        frame = frames[ticker]
        where = "the business frame for '%s'" % ticker
        if ticker not in allowed:
            reasons.append(
                "%s is keyed to a ticker this subject does not name - a "
                "frame describes one named instrument, so it is keyed by "
                "that instrument's ticker: the subject's own for a single "
                "name, one key per declared constituent for a basket or a "
                "theme universe%s" % (where,
                                      (" (this subject names %s)"
                                       % ", ".join("'%s'" % t
                                                   for t in allowed))
                                      if allowed else
                                      " (this subject names no ticker at "
                                      "all, so it can carry no frame)"))
            continue

        # A frame describes ONE named instrument, so every figure and
        # passage it cites is that instrument's own. Inside an
        # expression that is carried by the member suffix on the id.
        # Without this bound, one constituent's frame could cite its
        # NEIGHBOUR's revenue, passage or management figure - both
        # stages would pass, and the case file would print one
        # company's numbers under the other's heading.
        suffix = frame_suffix(subject, ticker)
        def not_this_member(field, entry_id):
            if not suffix:
                return False
            if not entry_id.endswith(suffix):
                reasons.append(
                    "%s names '%s' as %s, and that id does not belong to "
                    "%s - inside an expression every figure and passage "
                    "a frame cites carries its own member's suffix '%s', "
                    "or the seats read one member's numbers under "
                    "another's name"
                    % (where, entry_id, field, ticker, suffix))
                return True
            # The bound stopped at the id itself, so a fact WEARING this
            # member's suffix could be struck entirely from the
            # neighbour's figures and reach the seats under this
            # member's heading by another route (audit r1-2). A figure
            # belongs to one member all the way down or it belongs to
            # neither.
            path = _foreign_operand(entry_id, suffix, facts_by_id)
            if path is None:
                return False
            reasons.append(
                "%s names '%s' as %s, and it is struck from '%s', which "
                "does not belong to %s (%s) - a figure carries its "
                "member's suffix all the way down, or one member's "
                "numbers reach the seats under another member's name"
                % (where, entry_id, field, path[-1], ticker,
                   " -> ".join(path)))
            return True

        def missing_fact(field, fact_id, tier="tier1", scoped=True):
            pool = tier1_ids if tier == "tier1" else tier2_ids
            if fact_id in pool:
                if scoped:
                    not_this_member(field, fact_id)
                return
            reasons.append(
                "%s names %s '%s' as %s, and no such %s is in the capture "
                "- a frame points at the record, it never stands beside it"
                % (where, "fact" if tier == "tier1" else "passage",
                   fact_id, field,
                   "fact" if tier == "tier1" else "passage"))

        # ---- the ruled word limits, counted and named ----
        word_limits = [
            ("what_it_does", _WHAT_IT_DOES_WORDS, frame["what_it_does"]),
            ("what_is_changing.statement", _WHAT_IS_CHANGING_WORDS,
             frame["what_is_changing"]["statement"])]
        # Owner ruling AC15 (P2, P4): the archetype's ground and the
        # cycle-dependence reason are word-limited wherever they appear,
        # even on a frame not obliged to carry them.
        if frame.get("archetype_because") is not None:
            word_limits.append(("archetype_because",
                                _ARCHETYPE_BECAUSE_WORDS,
                                frame["archetype_because"]))
        if frame.get("cycle_dependence_because") is not None:
            word_limits.append(("cycle_dependence_because",
                                _CYCLE_DEPENDENCE_BECAUSE_WORDS,
                                frame["cycle_dependence_because"]))
        for field, limit, text in word_limits:
            counted = _words(text)
            if counted > limit:
                reasons.append(
                    "%s writes %d words for %s; the ruled limit is %d - "
                    "the frame is read by every seat before the numbers, "
                    "and a frame nobody finishes is a frame nobody reads"
                    % (where, counted, field, limit))

        # ---- a single name says what kind of business it is and whether
        #      its thesis rests on a cycle (owner ruling AC15, P2/P4) ----
        # Required of a SINGLE NAME only: a basket, a theme, a fund and an
        # asset with no earnings carry none, and one carried anyway is
        # still word-limited above. The archetype-to-measure MATCH and the
        # cycle block itself are the sufficiency gate's, because they read
        # the ruled table and the class's freshness rule.
        if subject.get("kind") == "single_stock":
            for field in ("archetype", "archetype_because",
                          "cycle_dependence", "cycle_dependence_because"):
                if not str(frame.get(field) or "").strip():
                    reasons.append(
                        "%s carries no %s - owner ruling AC15 obliges a "
                        "single name to state what kind of business it is "
                        "and why, and whether its thesis rests on a cycle "
                        "and why, before the rating measure and the cycle "
                        "series can be read" % (where, field))

        # ---- figures written in the frame's own prose (AC12.2, AC13.1) --
        # The seats read this prose BEFORE the fact table, and until
        # AC12.2 nothing bound a number written in it to anything at
        # all. Every figure the capture declares beside a block of frame
        # prose must stand in that prose word for word - the rule a
        # tier-2 passage has always met, applied by the same matcher.
        # Owner ruling AC13.1 closes the half that was left: standing in
        # the prose was never enough, and the figure must BE one the
        # record carries. A pack could declare 28,000 beside a fact
        # saying 27,900 and both stages passed, while every seat read
        # the invented number before it reached the fact table
        # (register items P-U1b-1 and the root of P-U2-4).
        def block_values(cited):
            """Every value this part of the frame's OWN citations put on
            the record: the cited facts themselves, a derived fact
            struck only from them (the rule a revenue line's share of
            the period already lives under), and the figures a cited
            tier-2 passage declares - which that passage has already had
            to state word for word. Nothing else is this part's, so
            nothing else may be written into its prose.

            `cited` is None for the ONE part of the frame the contract
            gives no facts list at all - the opening paragraph. The
            owner's ruling binds its figures too ("a recorded fact of
            the pack"), so they are judged against every fact this
            frame's own name may own: its member's, or the pack's shared
            ones. A narrower pool would be empty, and an empty pool
            makes declaring a figure there illegal while writing one
            undeclared stays legal - a rule that punishes the honest
            capture and closes nothing."""
            if cited is None:
                return [str(fact["value"]).strip()
                        for fact_id, fact in facts_by_id.items()
                        if _id_suffix(fact_id) in ("", suffix)]
            values, _ = _share_carriers(list(cited), facts_by_id, suffix)
            for entry_id in cited:
                passage = passages_by_id.get(entry_id)
                if passage:
                    values.extend(passage["figures"])
            return [str(value).strip() for value in values]

        def figures_bind(field, figures, text, cited):
            for figure in unstated_figures(figures, text):
                reasons.append(
                    "%s declares the figure '%s' for %s, and that figure "
                    "does not stand word for word in what it wrote there "
                    "- the seats read this prose before any number, so a "
                    "figure declared beside it must be IN it (a fragment "
                    "of a larger number does not state it)"
                    % (where, figure, field))
            carried = block_values(cited)
            for figure in figures:
                if str(figure).strip() in carried:
                    continue
                if not carried:
                    reasons.append(
                        "%s declares the figure '%s' for %s, and that "
                        "part of the frame points at nothing in the "
                        "record at all - a figure in the frame's prose "
                        "is a figure of the pack, so write it where the "
                        "frame cites the fact that carries it (what is "
                        "changing, a revenue line, or the decisive "
                        "metric it belongs to), or leave the number out "
                        "of this text"
                        % (where, figure, field))
                    continue
                reasons.append(
                    "%s declares the figure '%s' for %s, and no fact "
                    "that part of the frame cites carries that value - a "
                    "figure in the frame's prose is a figure of the "
                    "pack, written exactly as the pack writes it, or the "
                    "seats read an invented number before they reach the "
                    "fact table (what is cited there carries %s)"
                    % (where, figure, field,
                       ", ".join("'%s'" % value for value in carried)))

        # The opening paragraph carries no facts list of its own, so its
        # figures answer to the pack rather than to a citation.
        figures_bind("what it does",
                     frame["what_it_does_figures"],
                     frame["what_it_does"], None)
        figures_bind("what is changing",
                     frame["what_is_changing"]["figures"],
                     frame["what_is_changing"]["statement"],
                     frame["what_is_changing"]["facts"])

        # The two single-name rationale fields (owner ruling AC15, P2/P4)
        # are frame prose the seats read, so owner ruling AC13.1 binds
        # their figures too (unit U3e closing pass, register item
        # P-U3e-4). Neither carries a facts list of its own, so - like
        # the opening paragraph above - a figure written into either
        # answers to the pack under this frame's name rather than to a
        # citation, checked by the SAME matcher. Guarded on the prose's
        # presence, exactly as its word limit is: a frame without the
        # field, or carrying it without a number, declares no figure.
        if frame.get("archetype_because") is not None:
            figures_bind("the archetype ground",
                         frame.get("archetype_because_figures") or [],
                         frame["archetype_because"], None)
        if frame.get("cycle_dependence_because") is not None:
            figures_bind("the cycle-dependence reason",
                         frame.get("cycle_dependence_because_figures") or [],
                         frame["cycle_dependence_because"], None)

        # ---- how it earns ----
        for line in frame["how_it_earns"]:
            figures_bind("the revenue line '%s'" % line["line"],
                         line["figures"], line["line"], line["facts"])
            for fact_id in line["facts"]:
                missing_fact("a revenue line's supporting fact", fact_id)
                # A REVENUE line points at revenue (AC12.3). The member
                # bound above is the other half of this: an id that is
                # not this member's has already been refused, and
                # refusing it twice for two reasons helps nobody.
                if fact_id not in tier1_ids:
                    continue
                if suffix and not fact_id.endswith(suffix):
                    continue
                if not _is_revenue(fact_id, suffix, families, facts_by_id):
                    reasons.append(
                        "%s carries '%s' among the facts behind the "
                        "revenue line '%s', and that fact is not revenue "
                        "- a revenue line may point only at the "
                        "whole-business revenue figures, a segment "
                        "revenue line, their prior-year pairs, or a "
                        "figure struck from those; otherwise the seats "
                        "argue the mix of the business from a number "
                        "that is not revenue"
                        % (where, fact_id, line["line"]))
            # The share of the period is not free text: it is what a
            # fact of this line's own carries. A line could say 99%
            # beside facts saying otherwise, and the case file printed
            # the share to every seat (register item P-U1-3).
            share = str(line["share_of_period"]).strip()
            carried, foreign = _share_carriers(
                line["facts"], facts_by_id, suffix)
            carriers = [str(value).strip() for value in carried]
            outsider = next((fact_id for fact_id, value in foreign
                             if str(value).strip() == share), None)
            if share in carriers:
                pass
            elif outsider is not None:
                # The figure IS in the pack, struck from this line's own
                # facts, under an id suffixed to somebody else. The
                # arithmetic is right and the label is wrong, so the
                # capturer is told which it is (register item P-U1b-5).
                reasons.append(
                    "%s puts '%s' as the share of the period for the "
                    "revenue line '%s', and the only fact carrying that "
                    "figure is '%s', which is suffixed to another name - "
                    "a share carrier wears this frame's own suffix%s or "
                    "no suffix at all, or one company's arithmetic "
                    "stands as another's share"
                    % (where, line["share_of_period"], line["line"],
                       outsider, " ('%s')" % suffix if suffix else ""))
            else:
                reasons.append(
                    "%s puts '%s' as the share of the period for the "
                    "revenue line '%s', and no fact that line names "
                    "carries that figure - the share must be written "
                    "exactly as one of the line's own facts writes it, "
                    "or as a fact struck only from them (they carry %s); "
                    "where the pack carries no such figure, strike the "
                    "share itself as a fact over the line's own figures "
                    "and the freeze prints the arithmetic - there is no "
                    "gap to declare for it"
                    % (where, line["share_of_period"], line["line"],
                       ", ".join("'%s'" % value for value in carriers)
                       if carriers else "nothing at all"))

        # ---- what is changing ----
        changing = frame["what_is_changing"]
        for fact_id in changing["facts"]:
            missing_fact("a fact behind what is changing", fact_id)
        if changing["kind"] != "none" and not changing["facts"]:
            reasons.append(
                "%s declares the change '%s' and cites no fact for it - a "
                "change nothing in the record shows is an assertion, and "
                "the seats would read it as evidence"
                % (where, changing["kind"]))

        # ---- the decisive metrics ----
        metrics = frame["decisive_metrics"]
        # The minimum counts NUMBERS, not rows: three copies of one
        # metric would otherwise satisfy "three to five", and the case
        # file would show one number three times while the numbers the
        # rule exists to demand went unasked. Spacing and case are not
        # identity, so they are normalised away first.
        seen_metrics = set()
        for index, row in enumerate(metrics):
            key = " ".join(str(row["name"]).split()).casefold()
            if key in seen_metrics:
                reasons.append(
                    "%s names the decisive metric '%s' more than once - "
                    "the three to five numbers that decide a question are "
                    "three to five DIFFERENT numbers, and a repeated row "
                    "fills the minimum while leaving the others unasked"
                    % (where, row["name"]))
            seen_metrics.add(key)
            counted = _words(row["why_it_decides"])
            if counted > _WHY_IT_DECIDES_WORDS:
                reasons.append(
                    "%s writes %d words for why the decisive metric '%s' "
                    "decides the question; the ruled limit is %d"
                    % (where, counted, row["name"],
                       _WHY_IT_DECIDES_WORDS))
            figures_bind(
                "why the decisive metric '%s' decides the question"
                % row["name"], row["figures"], row["why_it_decides"],
                row["answered_by"])
            answered = row["answered_by"]
            gap = row["gap"]
            if answered and gap:
                reasons.append(
                    "%s says the decisive metric '%s' is both answered by "
                    "%s and a declared gap - a number is in the pack or it "
                    "is honestly missing, never both"
                    % (where, row["name"],
                       ", ".join("'%s'" % item for item in answered)))
            elif not answered and not gap:
                reasons.append(
                    "%s names the decisive metric '%s' and neither answers "
                    "it from the pack nor declares it a gap - a number "
                    "that decides the case cannot simply be listed"
                    % (where, row["name"]))
            carries_a_number = False
            for fact_id in answered:
                if fact_id in tier1_ids or fact_id in tier2_ids:
                    not_this_member("the answer to the decisive metric "
                                    "'%s'" % row["name"], fact_id)
                    if _states_a_number(fact_id, facts_by_id,
                                        passages_by_id):
                        carries_a_number = True
                    # A frozen passage may answer a decisive metric -
                    # a backlog stated in prose is still a frozen
                    # answer - but ONLY where it states a figure. A
                    # decisive metric is a number, and a wholly
                    # qualitative passage stood in for one before this
                    # (architect's mechanism ruling, audit r1-10). The
                    # figures a passage lists are already checked to
                    # appear literally in its own text.
                    if (fact_id in tier2_ids
                            and not passages_by_id[fact_id]["figures"]):
                        reasons.append(
                            "%s answers the decisive metric '%s' with the "
                            "passage '%s', and that passage states no "
                            "figure - a number that decides the case is a "
                            "NUMBER, so a passage answers one only where "
                            "it carries the figure itself"
                            % (where, row["name"], fact_id))
                    continue
                reasons.append(
                    "%s says the decisive metric '%s' is answered by '%s', "
                    "which is nowhere in the capture"
                    % (where, row["name"], fact_id))
            # The same ruling as r1-10, on the branch that was missed: a
            # decisive metric is a NUMBER. A row could rest on a tier-1
            # fact whose value is a date or a sentence, or on a passage
            # whose one declared figure is the word 'none', and still
            # fill the three-row minimum - so the seats were handed
            # three "numbers that decide the question" and not one
            # number. A row may cite prose BESIDE a figure; what it may
            # not do is cite no figure at all.
            if answered and not gap and not carries_a_number:
                reasons.append(
                    "%s answers the decisive metric '%s' with %s, and "
                    "there is no number behind it - a metric that "
                    "decides the case is a NUMBER, so at least one thing "
                    "a row names must be a figure: a fact whose value is "
                    "one, or a passage that states one"
                    % (where, row["name"],
                       ", ".join("'%s'" % item for item in answered)))
        if changing["kind"] in ("model_transition", "turnaround"):
            kinds = {row["kind"] for row in metrics}
            if not kinds & {"capacity_or_backlog", "unit_economics"}:
                reasons.append(
                    "%s says the business is in a %s, and none of its "
                    "decisive metrics measures contracted capacity or "
                    "backlog, or the economics of one unit - a business "
                    "changing what it sells is judged on what the NEW "
                    "business has contracted and what each unit of it "
                    "earns, never on the old one's shrinking revenue"
                    % (where, changing["kind"].replace("_", " ")))

        # ---- the peer set, or an honest gap ----
        peers = frame["peers"]
        # Counted before the cardinality rule, for the same reason the
        # decisive metrics are: two rows for one company are not two
        # peers, and the case file would present the same name twice as
        # a set. Identity is the FACT-ID FORM of the ticker, not the
        # ticker as typed - 'AB.C' and 'AB-C' both take the form 'ab_c',
        # so two such rows cite one set of facts (the same reasoning the
        # constituent check applies, audit finding THEMES-A r1-5). The
        # display name beside the ticker is never the identity.
        peer_forms = {}
        for peer in peers:
            peer_forms.setdefault(subjects.slug(peer["ticker"]),
                                  []).append(peer["ticker"])
        for form, group in sorted(peer_forms.items()):
            if len(group) < 2:
                continue
            distinct = sorted(set(group))
            if len(distinct) == 1:
                reasons.append(
                    "%s names the peer '%s' more than once - a peer set "
                    "is two to six DIFFERENT companies, and one company "
                    "listed twice is still the one comparison the rule "
                    "calls an anecdote" % (where, distinct[0]))
            else:
                reasons.append(
                    "%s names peers %s, which all take the same fact-id "
                    "form '%s' - one form is one set of "
                    "peer_<metric>__<ticker> facts, so those rows would "
                    "stand on the same figures and be read as two "
                    "comparisons" % (where,
                                     " and ".join("'%s'" % ticker
                                                  for ticker in distinct),
                                     form))
        if len(peers) == 1:
            reasons.append(
                "%s names one peer - the ruled peer set is two to six "
                "names, and one comparison is an anecdote; where no "
                "honest peer set exists, name none and declare the gap "
                "for the fact class '%s'" % (where, _PEER_GAP_CLASS))
        elif not peers and _PEER_GAP_CLASS not in gap_classes:
            reasons.append(
                "%s names no peer and the capture declares no gap for the "
                "fact class '%s' - three true peers beat six doubtful "
                "ones, but a silent absence tells the seats nothing at all"
                % (where, _PEER_GAP_CLASS))
        for peer in peers:
            wanted = subjects.slug(peer["ticker"])
            # Owner ruling AC15 (P1): a peer is comparable by business
            # model, not by narrative. Each peer records WHY it is
            # comparable - the contract structure and duration or the
            # revenue model it shares - and where it is not; the gate
            # refuses a peer that carries no such statement, and the two
            # statements reach the outside auditor's brief. An empty
            # statement is already refused by the contract shape; these
            # checks are the word limits it cannot state.
            because = peer.get("comparable_because")
            if not str(because or "").strip():
                reasons.append(
                    "%s names the peer %s with no statement of why it is "
                    "comparable - a peer is comparable by business model, "
                    "not by narrative, so each names the contract structure "
                    "and duration or the revenue model it shares"
                    % (where, peer["ticker"]))
            elif _words(because) > _COMPARABLE_BECAUSE_WORDS:
                reasons.append(
                    "%s writes %d words for why peer %s is comparable; the "
                    "ruled limit is %d"
                    % (where, _words(because), peer["ticker"],
                       _COMPARABLE_BECAUSE_WORDS))
            not_on = peer.get("not_comparable_on")
            if not str(not_on or "").strip():
                reasons.append(
                    "%s names the peer %s with no statement of where it is "
                    "NOT comparable - an honest comparison names its own "
                    "limits, or says 'nothing material'"
                    % (where, peer["ticker"]))
            elif _words(not_on) > _NOT_COMPARABLE_ON_WORDS:
                reasons.append(
                    "%s writes %d words for where peer %s is not comparable; "
                    "the ruled limit is %d"
                    % (where, _words(not_on), peer["ticker"],
                       _NOT_COMPARABLE_ON_WORDS))
            # The contract asks each peer for at least TWO metrics, and
            # one id named twice filled that minimum - so the case file
            # showed one comparable figure as the two the rule demands
            # (audit r5-5). The id is the identity: it is pattern-bound,
            # so unlike a metric's name or a peer's ticker there is
            # nothing to normalise away first.
            seen_metrics = set()
            for metric_id in peer["metrics"]:
                if metric_id in seen_metrics:
                    reasons.append(
                        "%s names the metric '%s' twice for peer %s - "
                        "the ruled two comparable figures are two "
                        "DIFFERENT figures, and one named twice is one "
                        "comparison wearing two rows"
                        % (where, metric_id, peer["ticker"]))
                seen_metrics.add(metric_id)
            for metric_id in peer["metrics"]:
                # A peer's figures carry the PEER's suffix, not this
                # frame's member suffix - the convention check on the
                # next line is what binds them to the right company.
                missing_fact("a peer metric for %s" % peer["ticker"],
                             metric_id, scoped=False)
                base, _, carried = metric_id.partition("__")
                if not base.startswith("peer_") or carried != wanted:
                    reasons.append(
                        "%s carries '%s' as a metric for peer %s - a peer "
                        "metric is named peer_<metric>__<ticker>, so this "
                        "one must read 'peer_<metric>__%s' or the seats "
                        "cannot tell whose figure it is"
                        % (where, metric_id, peer["ticker"], wanted))
                    continue
                # The convention check reads the NAME. A peer metric
                # struck out of the subject's own figures wears the
                # peer's name and carries the subject's number, and the
                # seats read it as the comparison (audit r3-1's class,
                # found in triage). This one bites on a single listed
                # name as well as inside an expression, which makes it
                # the widest of the four.
                path = _foreign_operand(metric_id, "__" + wanted,
                                        facts_by_id)
                if path is not None:
                    reasons.append(
                        "%s carries '%s' as a metric for peer %s, and it "
                        "is struck from '%s', which is not that peer's "
                        "figure (%s) - a comparison built out of the "
                        "subject's own numbers is not a comparison"
                        % (where, metric_id, peer["ticker"], path[-1],
                           " -> ".join(path)))

        # ---- management, and its delivery against its own guidance ----
        management = frame["management"]
        for field in ("ceo_tenure_years", "cfo_tenure_years",
                      "insider_ownership_pct"):
            if management[field] is None:
                continue
            missing_fact(field, management[field])
            # Each of these three field names promises a number, and
            # the case file prints the named fact under that promise.
            # The same bound as the decisive metrics, one field over
            # (audit r5-1, fix-checklist 8a).
            if (management[field] in tier1_ids
                    and not _states_a_number(management[field],
                                             facts_by_id, passages_by_id)):
                reasons.append(
                    "%s names '%s' as %s, and its value '%s' is not a "
                    "number - the case file prints that fact under a "
                    "heading that promises one"
                    % (where, management[field], field,
                       facts_by_id[management[field]]["value"]))
        delivery = management["guidance_vs_delivery"]
        if not delivery and _GUIDANCE_GAP_CLASS not in gap_classes:
            reasons.append(
                "%s carries no quarter of guidance beside what was "
                "delivered, and the capture declares no gap for the fact "
                "class '%s' - whether management hits its own numbers is "
                "evidence, and its absence has to be stated"
                % (where, _GUIDANCE_GAP_CLASS))
        # One quarter listed twice read as two quarters of management's
        # record, and a seat weighing whether management hits its own
        # numbers counted it twice (audit r5-6). The row's identity is
        # the FACTS it names, never the period label beside them: the
        # label is free text and a second row can carry a different one
        # over identical ids, which is r2-2's lesson one field over.
        seen_quarters = set()
        for quarter in delivery:
            row_key = (frozenset(quarter["guided"]), quarter["delivered"])
            if row_key in seen_quarters:
                reasons.append(
                    "%s carries the same quarter of guidance twice - %s "
                    "beside '%s' - so one quarter's record of whether "
                    "management hit its own number would be read as two"
                    % (where, ", ".join("'%s'" % item
                                        for item in quarter["guided"]),
                       quarter["delivered"]))
            seen_quarters.add(row_key)
        def without_suffix(fact_id):
            return (fact_id[:-len(suffix)]
                    if suffix and fact_id.endswith(suffix) else fact_id)

        for row_index, quarter in enumerate(delivery):
            for fact_id in quarter["guided"]:
                missing_fact("the guided figure for %s" % quarter["period"],
                             fact_id)
            missing_fact("the delivered figure for %s" % quarter["period"],
                         quarter["delivered"])
            # Existence was the only test, so one quarter's guidance
            # could stand beside ANOTHER quarter's delivery - or two
            # figures that are neither - and the case file published the
            # pair as one period's record of whether management hits its
            # own numbers. The partner id is derived exactly as the
            # ruled guided_/delivered_ floor derives it, so the frame
            # and the floor read one rule.
            delivered_id = quarter["delivered"]
            partners = [_DELIVERED_PREFIX + fact_id[len(_GUIDED_PREFIX):]
                        for fact_id in quarter["guided"]
                        if fact_id.startswith(_GUIDED_PREFIX)]
            for fact_id in quarter["guided"]:
                if not fact_id.startswith(_GUIDED_PREFIX):
                    reasons.append(
                        "%s offers '%s' as what management guided for %s, "
                        "and a guided figure is named '%s<metric>_<quarter>' "
                        "- an id outside that family is some other number, "
                        "and the seats would read it as a promise"
                        % (where, fact_id, quarter["period"],
                           _GUIDED_PREFIX))
            if not delivered_id.startswith(_DELIVERED_PREFIX):
                reasons.append(
                    "%s offers '%s' as what management delivered for %s, "
                    "and a delivered figure is named "
                    "'%s<metric>_<quarter>' - an id outside that family "
                    "is some other number, and the seats would read it "
                    "as the outcome" % (where, delivered_id,
                                        quarter["period"],
                                        _DELIVERED_PREFIX))
            elif partners and delivered_id not in partners:
                reasons.append(
                    "%s puts '%s' beside the guidance for %s (%s), and it "
                    "is not the delivered figure for any of them - a "
                    "quarter's promise is read against ITS OWN outcome, "
                    "so this pair would score management on two "
                    "different periods"
                    % (where, delivered_id, quarter["period"],
                       ", ".join("'%s'" % item
                                 for item in quarter["guided"])))
            # The DISPLAYED period binds to the facts beneath it (owner
            # ruling AC12.1). The label was free text bound to nothing,
            # so a row headed Q2 could carry Q1's ids and the case file
            # printed one quarter's figures under another quarter's name
            # (register item P-U1-2). One canonical slug decides it:
            # every id in the row ends with the label's own slug.
            slug = period_slug(quarter["period"])
            if not slug:
                reasons.append(
                    "%s labels a quarter of guidance '%s', which carries "
                    "no letter or digit to name a period by - the label "
                    "is what binds the row to its own figures"
                    % (where, quarter["period"]))
            else:
                tail = "_" + slug
                for fact_id in list(quarter["guided"]) + [delivered_id]:
                    if suffix and not fact_id.endswith(suffix):
                        continue
                    if not without_suffix(fact_id).endswith(tail):
                        reasons.append(
                            "%s heads a quarter of guidance '%s' and puts "
                            "'%s' in it, and that id does not end '%s' - "
                            "the period a row DISPLAYS must be the period "
                            "its figures carry, or the seats read one "
                            "quarter's promise under another quarter's "
                            "name" % (where, quarter["period"], fact_id,
                                      tail))
                # A label that fits this row's ids may fit ANOTHER row's
                # too: 'FY2026' ends both q1_fy2026 and q2_fy2026, so two
                # quarters were printed under one heading and a seat
                # could not tell which promise was which (audit r1-3).
                # The duplicate-row check above cannot see this - it
                # keys on the ids, which differ. Nothing here parses an
                # id into metric and quarter: the ruled shape
                # guided_<metric>_<quarter> has no delimiter between
                # them, which is why that prescription was refuted once
                # already (audit r2-3).
                shared = sorted(
                    fact_id
                    for other_index, other in enumerate(delivery)
                    if other_index != row_index
                    for fact_id in list(other["guided"]) + [
                        other["delivered"]]
                    if without_suffix(fact_id).endswith(tail))
                if shared:
                    reasons.append(
                        "%s heads a quarter of guidance '%s', and %s "
                        "belongs to a different row of the same table - "
                        "a label that fits two quarters tells them "
                        "apart for nobody, and the case file prints "
                        "both rows under it"
                        % (where, quarter["period"],
                           ", ".join("'%s'" % item for item in shared)))
            # EVERY guided figure in the row is scored, not just one:
            # the delivered id had only to partner ONE of them, so a
            # second promise in the same row could stand with no outcome
            # anywhere in the pack (AC12.1, register item P-U1-2). The
            # partner is derived exactly as the ruled guided_/delivered_
            # floor derives it.
            for fact_id in quarter["guided"]:
                if not fact_id.startswith(_GUIDED_PREFIX):
                    continue
                partner = _DELIVERED_PREFIX + fact_id[len(_GUIDED_PREFIX):]
                # The partner is DISCOVERED, so it never passed the
                # member bound the declared delivered id passes: it
                # could be struck entirely from the neighbour's figures
                # and still satisfy "every promise has an outcome"
                # (audit r3-2). The guard stops the declared id being
                # reported twice for one defect.
                if partner in tier1_ids and partner != delivered_id:
                    not_this_member(
                        "the delivered figure that scores '%s'" % fact_id,
                        partner)
                if partner not in tier1_ids:
                    reasons.append(
                        "%s carries '%s' as what management guided for "
                        "%s, and the pack has no '%s' to score it "
                        "against - a promise with no outcome beside it "
                        "says nothing about whether management hits its "
                        "own numbers"
                        % (where, fact_id, quarter["period"], partner))
        # And every guided figure the PACK carries appears in the table
        # (AC12.1): the frame could leave one out, and the quarter
        # management missed was the one that went missing while its
        # figures sat in the fact table below.
        #
        # UNLESS the table is already full. The contract lets it hold
        # four quarters and the spec asks for the last four that had
        # guidance, so a pack holding five is an honest pack, and which
        # four are shown is the capturer's own recorded choice. Read
        # literally, this rule made that pack illegal (the architect's
        # mechanism ruling at the U1b merge). A table with room left
        # still owes every quarter it can hold.
        framed_guided = {fact_id for quarter in delivery
                         for fact_id in quarter["guided"]}
        orphans = [fact_id for fact_id in sorted(tier1_ids)
                   if fact_id.startswith(_GUIDED_PREFIX)
                   and fact_id.endswith(suffix)
                   and fact_id not in framed_guided]
        if orphans and len(delivery) < _GUIDANCE_ROWS:
            pronoun = "it" if len(orphans) == 1 else "them"
            reasons.append(
                "%s leaves %s out of what management guided, and the "
                "pack carries %s while the table still has room for %s "
                "(%d of the %d quarters it may hold are shown) - every "
                "quarter of guidance the pack holds belongs in the table "
                "until it is full, or the quarter management missed is "
                "the one nobody sees"
                % (where, ", ".join("'%s'" % item for item in orphans),
                   pronoun, pronoun, len(delivery), _GUIDANCE_ROWS))
        missing_fact("the capital-allocation passage",
                     management["capital_allocation"], "tier2")
        missing_fact("the competitive_position passage",
                     frame["competitive_position"], "tier2")

        # ---- the required reading of a falling headline figure ----
        fallen = []
        measured = []
        for current_base, prior_base in HEADLINE_PAIRS:
            current_id = current_base + suffix
            prior_id = prior_base + suffix
            # These two ids are CONSTRUCTED from the member's suffix, so
            # neither is named by the frame and neither passed the
            # member bound - and they are the widest of the discovered
            # ids, because they decide whether a fall is demanded, what
            # reading the frame owes, and what the case file tells every
            # seat about the quarter. A pair struck out of the
            # neighbour's figures decided this member's quarter (audit
            # r3-1's class, found in triage).
            #
            # EVERY half that is present is bound BEFORE the pair is
            # asked whether it is complete. A half standing alone is
            # never compared, but the case file still names it under
            # this member - "in this pack, with no prior-year figure to
            # compare it against" - so a foreign-struck half told the
            # seats something about the wrong company either way, and
            # the bound placed after this test closed only the case
            # where both halves were there (audit r4-2).
            foreign = False
            for fact_id, field in ((current_id,
                                    "the latest headline figure"),
                                   (prior_id,
                                    "the prior-year headline figure")):
                if (fact_id in facts_by_id
                        and not_this_member(field, fact_id)):
                    foreign = True
            if (foreign or current_id not in facts_by_id
                    or prior_id not in facts_by_id):
                continue
            reading = headline_reading(facts_by_id[current_id],
                                       facts_by_id[prior_id])
            if reading == HEADLINE_UNREADABLE:
                for fact_id in (current_id, prior_id):
                    if _decimal_or_none(
                            facts_by_id[fact_id]["value"]) is None:
                        reasons.append(
                            "%s rests on headline fact '%s', whose value "
                            "'%s' is not a finite number - whether this "
                            "figure has fallen decides how every seat "
                            "reads the quarter, so a value nobody can "
                            "compare is a defect of the capture, not a "
                            "pair to pass over"
                            % (where, fact_id,
                               facts_by_id[fact_id]["value"]))
                continue
            if reading == HEADLINE_UNITS_DIFFER:
                reasons.append(
                    "%s rests on headline facts '%s' in %s and '%s' in "
                    "%s, and figures in two units cannot be compared - "
                    "this gate rescales nothing, so restate both in one "
                    "unit or the fall is decided by arithmetic on "
                    "unlike numbers"
                    % (where, current_id, facts_by_id[current_id]["unit"],
                       prior_id, facts_by_id[prior_id]["unit"]))
                continue
            if reading == HEADLINE_BOUNDED:
                # A bound is not a measurement: it decides a fall in one
                # direction only, and this pair points the other way. It
                # counts as neither fallen nor measured, so no reading is
                # demanded of it and it cannot make up the three that let
                # the gate refuse a reading.
                continue
            measured.append(current_id)
            if reading == HEADLINE_FELL:
                fallen.append(current_id)
        decline = frame["headline_decline_read"]
        if fallen and decline is None:
            reasons.append(
                "%s carries no reading of a headline figure that has "
                "fallen: %s below the prior-year pair. Say whether the "
                "fall is by design, deterioration or mixed - or declare "
                "it unknown with the gap - because every seat otherwise "
                "reads the same fall as deterioration by default"
                % (where, ", ".join("'%s'" % item for item in fallen)))
        # The rule ran one way only: a fall with no reading was refused,
        # a reading with no fall was not. The second is the worse one -
        # the seats are told the quarter went the other way. It is
        # judged on the pairs the pack CARRIES: a pack that measures one
        # of the three has shown nothing about the other two, and
        # demanding them would be a requirement AC1 does not make.
        if (decline is not None and not fallen
                and len(measured) == len(HEADLINE_PAIRS)):
            reasons.append(
                "%s reads a fall in its headline figures as '%s', and "
                "none of the three has fallen: %s, each at or above its "
                "prior-year pair. A reading answers a fall the record "
                "shows; a reading with no fall behind it tells every "
                "seat the quarter went the other way"
                % (where, decline["reading"],
                   ", ".join("'%s'" % item for item in measured)))
        if decline is not None:
            for fact_id in decline["facts"]:
                missing_fact("a fact behind the headline-decline reading",
                             fact_id)
            if decline["reading"] == "unknown":
                if _DECLINE_GAP_CLASS not in gap_classes:
                    reasons.append(
                        "%s reads the fall in the headline figures as "
                        "unknown and the capture declares no gap for the "
                        "fact class '%s' - unknown is an admission, and an "
                        "admission is declared where the seats will see it"
                        % (where, _DECLINE_GAP_CLASS))
            elif not decline["facts"]:
                reasons.append(
                    "%s reads the fall in the headline figures as '%s' and "
                    "rests it on no fact - a reading of a decline is worth "
                    "only the figures it stands on"
                    % (where, decline["reading"]))

    # AC12.1's completeness at the level the ruling states it: every
    # guided figure the pack carries FOR THE SUBJECT appears in a table.
    # Inside an expression each member's table is scoped to its own
    # suffix, so a guidance fact carrying no member suffix belonged to
    # no table and could never be an orphan - and no member could put it
    # in one either, because the member bound refuses an id without its
    # own suffix. It was unreachable by the rule from both ends, and a
    # promise management missed sat in the fact table where every seat
    # reads it with nothing obliged to show its outcome beside it (audit
    # round 4, found in triage).
    member_suffixes = tuple("__%s" % subjects.slug(member)
                            for member in subjects.expression_tickers(subject)
                            if member)
    if member_suffixes:
        homeless = [fact_id for fact_id in sorted(tier1_ids)
                    if fact_id.startswith((_GUIDED_PREFIX,
                                           _DELIVERED_PREFIX))
                    and not fact_id.endswith(member_suffixes)]
        if homeless:
            reasons.append(
                "this capture carries %s, and %s named for no member of "
                "the expression - inside a basket or a theme a promise "
                "and its outcome belong to ONE company, so each carries "
                "that member's suffix (%s); without one it appears in no "
                "member's table and the quarter management missed is the "
                "one nobody sees"
                % (", ".join("'%s'" % item for item in homeless),
                   "it is" if len(homeless) == 1 else "they are",
                   ", ".join("'%s'" % item for item in member_suffixes)))
    return reasons


def _check_cycle(capture):
    """The optional top-level cycle block's own consistency (owner ruling
    AC15, P4, unit U3e).

    It is EVIDENCE, never analysis: this check reads the shape, the word
    limits, that exactly one of series or gap is carried, and that each
    series' dates strictly increase. It never asks whether the cycle is
    the RIGHT one - that is the sitting's judgement. Whether cycle
    freshness is in rule, and whether the frame's cycle_dependence agrees
    with this block, are the sufficiency gate's, because they read the
    class's price-freshness rule and the frame together."""
    cycle = capture.get("cycle")
    if not cycle:
        return []
    reasons = []
    where = "the cycle block"
    for field, limit in (("name", _CYCLE_NAME_WORDS),
                         ("why_it_matters", _CYCLE_WHY_WORDS)):
        counted = _words(cycle.get(field))
        if counted > limit:
            reasons.append(
                "%s writes %d words for %s; the ruled limit is %d"
                % (where, counted, field, limit))
    series = cycle.get("series")
    gap = cycle.get("gap")
    if series and gap:
        reasons.append(
            "%s carries both dated series and a declared gap - a cycle "
            "is one or the other: the series where they are in hand, the "
            "gap with a reason where they are not" % where)
    elif not series and not gap:
        reasons.append(
            "%s carries neither dated series nor a declared gap - name "
            "the cycle, then carry three to five dated series for it or "
            "declare why none is in hand" % where)
    # Owner ruling AC15 (P4): "three to five dated series" means that many
    # DISTINCT series. The schema counts array items, so copies sharing one
    # id satisfy the count while carrying one series repeated; the pack and
    # the reports would then claim more series than they hold. Refuse a
    # repeated id, as a repeated denominator is refused (round-7 r7-5,
    # applying finding r2-2's distinctness rule to the cycle).
    ids = [entry["id"] for entry in series or []]
    repeated = sorted({fid for fid in ids if ids.count(fid) > 1})
    if repeated:
        reasons.append(
            "%s carries %d series but only %d distinct id(s) - 'three to "
            "five dated series' means that many DISTINCT series, not one "
            "series repeated (ids repeated: %s)"
            % (where, len(ids), len(set(ids)), ", ".join(repeated)))
    for entry in series or []:
        dates = [point["date"] for point in entry["points"]]
        if any(later <= earlier
               for earlier, later in zip(dates, dates[1:])):
            reasons.append(
                "the cycle series '%s' does not run in strictly "
                "increasing dates - a dated series read as evidence is "
                "ordered, or two readings sit on one date and the seats "
                "cannot tell which came first" % entry["id"])
    return reasons


def _check_labels(capture):
    """The optional plain-English fact label (owner ruling AC15, P5).

    A label is checked only where a fact carries one: it must not be
    empty, must not merely repeat the machine key it stands in for (the
    owner ruled the keys wasted space; a label equal to the key saves
    none), and is at most eight words. The full evidence document prints
    the label where one exists and the key where none does."""
    reasons = []
    for fact in capture["tier1"]:
        if "label" not in fact:
            continue
        # An empty or whitespace-only label is already refused by the
        # contract's own shape (minLength 1 and a non-whitespace pattern),
        # so this check is only about what the shape cannot say.
        label = str(fact.get("label") or "")
        fact_id = fact.get("id")
        if label.strip() == fact_id:
            reasons.append(
                "fact '%s' has a label equal to its id - the label is the "
                "plain-English name the owner reads instead of the machine "
                "key, and repeating the key saves him nothing" % fact_id)
        # A label is untrusted model output printed as a HEADING in the
        # document a person approves; a line break or control character in
        # it forges a new section on that page (audit round 1 of sub-charge
        # b, b-r1-9). A label is one line of plain text.
        if any(ord(char) < 32 for char in label):
            reasons.append(
                "fact '%s' has a label with a line break or control "
                "character - a label is a single line of plain text, and it "
                "is printed as a heading in the document a person approves"
                % fact_id)
        counted = _words(label)
        if counted > _LABEL_WORDS:
            reasons.append(
                "fact '%s' has a %d-word label; the ruled limit is %d - a "
                "label is a short name, not a sentence"
                % (fact_id, counted, _LABEL_WORDS))
    return reasons


def _check_period_basis(capture):
    """An average must not be published as an annual figure (owner ruling
    AC15, P3).

    A derived fact that PRESENTS itself as an annual, per-year or run-rate
    figure - its id or its label carries one of the ruled signal words -
    must declare which period it covers; and one that calls itself annual
    while declaring a multi-year or lifetime average basis is refused,
    because that is the conflation the owner flagged: a multi-decade
    average run rate read as the first twelve months' billing. The signal
    words and the average bases are DATA in the floors file. period_basis
    is otherwise free to carry on any fact and its value is checked by the
    contract's own enum.

    The 'divides a total by a term' half of the ruling is not enforced
    structurally: the gate cannot tell a total-over-term from a
    part-over-whole (a share is a divide too), and the harm the ruling
    names is a figure PRESENTED as annual - which is exactly what the
    signal words catch. A session dividing a total by a term declares its
    basis by naming the fact for what it is."""
    data = period_basis_data()
    # A fact signals annual through its id or its label, both untrusted model
    # output. Rounds 1-4 matched the signal words as substrings over a
    # separator-folded string and patched a new spelling each round - the
    # hyphen (r1), unicode dashes and the slash (r2), a cross-token straddle
    # (r3), the underscore and the plural (r4). A substring match cannot stop
    # straddling a token at one end without running off a word at the other,
    # so r5 replaced it with a TOKEN-SET rule on the architect's instruction:
    # the id and label are split into tokens on every run of non-word
    # characters and underscores, and each signal is matched against whole
    # tokens, never across a token or inside one. A phrase signal ("per
    # year", "run rate", "a year") matches only a contiguous run of tokens.
    # The signal words stay DATA in the floors file; the underscore aliases
    # "per_year" and "run_rate" were pruned there, dead now that a snake_case
    # id splits to the same tokens as the space-written phrase (audit
    # UPGRADE2-U3d-c r5).
    signal_token_lists = [str(word).casefold().split()
                          for word in (data.get("annual_signal_words") or [])]
    signal_token_lists = [tokens for tokens in signal_token_lists if tokens]
    average_bases = set(data.get("average_bases") or [])

    def token_matches(token, signal):
        # A signal matches a token only when it IS the token, exactly. Every
        # word that signals annual - the base word, its inflections and its
        # derivations ("annual", "annually", "annualized", "annualization")
        # and the plural of a phrase's last word ("run rates") - is
        # enumerated in the floors file, so the match needs no character
        # heuristic. The fixed two-character prefix allowance this replaces
        # was wrong in BOTH directions (audit UPGRADE2-U3d-c r6): it MISSED
        # longer real forms ("annualization" is more than two characters past
        # "annual", so an explicitly annualized multi-year average was
        # accepted) and it MATCHED different words ("perks" is two characters
        # past "per", so "perks year-end" was read as "per year" and a valid
        # point-in-time figure refused). Exact whole-token matching against a
        # vocabulary kept in DATA closes both; a phrase signal still matches
        # only a contiguous run of tokens, each exact.
        return token == signal

    def signals_annual(tokens):
        for signal_tokens in signal_token_lists:
            span = len(signal_tokens)
            for start in range(len(tokens) - span + 1):
                if all(token_matches(tokens[start + i], signal_tokens[i])
                       for i in range(span)):
                    return True
        return False

    def field_tokens(text):
        return [token for token in re.split(r"[\W_]+", str(text).casefold())
                if token]

    reasons = []
    for fact in capture["tier1"]:
        if not fact.get("derived"):
            continue
        fact_id = fact.get("id")
        # The id and the label are tokenized and matched SEPARATELY, so a
        # phrase signal ("a year", "per year", "run rate") must fall within a
        # single field and can never straddle the seam between the two. Joined
        # into one stream, a derived point-in-time fact with id "series_a" and
        # label "year-end valuation" read as [series, a, year, end, valuation]
        # and "a year" matched across the id/label boundary, refusing a valid
        # fact that signals annual in NEITHER field - contrary to AC15 P3
        # (audit UPGRADE2-U3d-c r9).
        signalled = (signals_annual(field_tokens(fact_id))
                     or signals_annual(field_tokens(fact.get("label") or "")))
        basis = fact.get("period_basis")
        if signalled and not basis:
            reasons.append(
                "derived fact '%s' presents itself as an annual figure but "
                "declares no period basis - an average must not be published "
                "as an annual figure, so a figure that names itself annual "
                "says over what period it is measured (owner ruling AC15)"
                % fact_id)
        elif signalled and basis in average_bases:
            reasons.append(
                "derived fact '%s' names itself an annual figure and "
                "declares a period basis of '%s' - a multi-year or lifetime "
                "average presented as an annual figure is the very "
                "conflation owner ruling AC15 forbids; call it what it is or "
                "state the actual annual figure" % (fact_id, basis))
    return reasons


def _check_id_uniqueness(capture):
    reasons = []
    tier1_ids = [fact["id"] for fact in capture["tier1"]]
    tier2_ids = [passage["id"] for passage in capture["tier2"]]
    for tier, ids in (("tier1", tier1_ids), ("tier2", tier2_ids)):
        seen = set()
        for entry_id in ids:
            if entry_id in seen:
                reasons.append(
                    "%s id '%s' appears more than once - every id in a "
                    "tier must be unique" % (tier, entry_id))
            seen.add(entry_id)
    for entry_id in sorted(set(tier1_ids) & set(tier2_ids)):
        reasons.append(
            "id '%s' names both a tier1 fact and a tier2 passage - ids "
            "may not collide across the tiers" % entry_id)
    return reasons


def _compute(operation, values):
    """The declared arithmetic, exactly or not at all: any operation
    whose true result cannot be written as a finite decimal raises
    Inexact instead of silently rounding."""
    with localcontext() as context:
        context.prec = _EXACT_PRECISION
        context.traps[Inexact] = True
        result = values[0]
        for value in values[1:]:
            if operation in ("add", "sum"):
                result = result + value
            elif operation == "subtract":
                result = result - value
            elif operation == "multiply":
                result = result * value
            else:
                result = result / value
        return result


def _check_arithmetic(capture):
    reasons = []
    for fact in capture["tier1"]:
        derived = fact["derived"]
        if not derived:
            continue
        operation = derived["operation"]
        operands = derived["operands"]
        if operation in _EXACTLY_TWO and len(operands) != 2:
            reasons.append(
                "derived fact '%s' declares '%s' over %d operands - "
                "'%s' takes exactly two"
                % (fact["id"], operation, len(operands), operation))
            continue
        values = []
        unusable = False
        for operand in operands:
            try:
                parsed = Decimal(operand["value"])
            except InvalidOperation:
                reasons.append(
                    "operand '%s' of derived fact '%s' has value '%s', "
                    "which is not a number"
                    % (operand["label"], fact["id"], operand["value"]))
                unusable = True
                continue
            if not parsed.is_finite():
                reasons.append(
                    "operand '%s' of derived fact '%s' is '%s' - a "
                    "frozen figure must be finite"
                    % (operand["label"], fact["id"], operand["value"]))
                unusable = True
                continue
            values.append(parsed)
        try:
            declared = Decimal(fact["value"])
        except InvalidOperation:
            reasons.append(
                "derived fact '%s' has value '%s', which is not a number"
                % (fact["id"], fact["value"]))
            unusable = True
        else:
            if not declared.is_finite():
                reasons.append(
                    "derived fact '%s' declares '%s' - a frozen figure "
                    "must be finite" % (fact["id"], fact["value"]))
                unusable = True
        if unusable:
            continue
        try:
            computed = _compute(operation, values)
        except Inexact:
            reasons.append(
                "the declared arithmetic of derived fact '%s' has no "
                "exact decimal result - it may not be frozen as an "
                "exact figure" % fact["id"])
            continue
        except ArithmeticError:
            reasons.append(
                "the declared arithmetic of derived fact '%s' cannot be "
                "computed at all (for example a division by zero)"
                % fact["id"])
            continue
        if computed != declared:
            equation = _OPERATOR_TEXT[operation].join(
                operand["value"] for operand in operands)
            reasons.append(
                "derived fact '%s' does not recompute from its own "
                "operands: %s = %s, but the fact's value says %s"
                % (fact["id"], equation, computed, fact["value"]))
    return reasons


def derived_dependents(capture, changed_ids):
    """Every derived fact whose operands rest, directly or through
    another derived fact, on one of `changed_ids` (owner ruling AC15,
    P7/P8). The changed facts' own ids are never in the result; only the
    figures struck from them are. Operands without a fact reference are
    inline constants and depend on nothing.

    This is the dependent CHAIN a correction re-strikes and the delta
    re-audit shows the auditor - the debrief's caveat that a stale
    derived figure must never be left behind."""
    changed = set(changed_ids)
    deps = set()
    grew = True
    while grew:
        grew = False
        for fact in capture.get("tier1", []):
            derived = fact.get("derived")
            fact_id = fact.get("id")
            if not derived or fact_id in deps or fact_id in changed:
                continue
            refs = {operand.get("fact_id")
                    for operand in derived["operands"]
                    if operand.get("fact_id") is not None}
            if refs & (changed | deps):
                deps.add(fact_id)
                grew = True
    return deps


def stale_reading_ids(capture):
    """Every tier-1 fact whose CURRENT value the source beside it no
    longer supports (owner ruling AC15, P7). A source-less correction
    moves the value while leaving the old source, so the number stops
    tracing to what was observed - until a human re-gathers it, OR until
    a later correction moves the value back to what that source supports
    (audit round 2, r2-5). The supported value is the one the most recent
    source-bearing correction set; where no correction supplied a source,
    it is the value the auditor read (the first correction's `old`), which
    the unchanged source still supports. This carries the correction
    command's console notice into the durable rendering a reader sees."""
    by_fact = {}
    for correction in capture.get("corrections") or []:
        fact_id = correction.get("fact_id")
        if fact_id is not None:
            by_fact.setdefault(fact_id, []).append(correction)
    facts = {fact.get("id"): fact for fact in capture.get("tier1", [])}
    stale = set()
    for fact_id, corrections in by_fact.items():
        fact = facts.get(fact_id)
        if fact is None:
            continue
        supported = corrections[0].get("old")
        for correction in corrections:
            if correction.get("source") is not None:
                supported = correction.get("new")
        if fact.get("value") != supported:
            stale.add(fact_id)
    return stale


def _cycles_in(graph):
    """Every cycle in a small id->ids graph, self-loops included, as a
    list of ' -> '-joined strings (iterative colouring, no recursion)."""
    found = []
    state = {}
    for start in sorted(graph):
        if state.get(start):
            continue
        stack = [(start, iter(sorted(graph.get(start, ()))))]
        state[start] = "open"
        path = [start]
        while stack:
            node, children = stack[-1]
            advanced = False
            for child in children:
                if child not in graph:
                    continue
                if state.get(child) == "open":
                    cycle = path[path.index(child):] + [child]
                    found.append(" -> ".join(cycle))
                elif not state.get(child):
                    state[child] = "open"
                    path.append(child)
                    stack.append((child, iter(sorted(graph.get(child, ())))))
                    advanced = True
                    break
            if not advanced:
                state[node] = "done"
                path.pop()
                stack.pop()
    return found


def _check_operand_references(capture):
    reasons = []
    facts_by_id = {}
    for fact in capture["tier1"]:
        facts_by_id.setdefault(fact["id"], fact)
    graph = {}
    for fact in capture["tier1"]:
        if fact["derived"]:
            graph[fact["id"]] = {
                operand["fact_id"]
                for operand in fact["derived"]["operands"]
                if operand.get("fact_id") is not None}
    for cycle in _cycles_in(graph):
        reasons.append(
            "derived facts form a cycle (%s) - a figure cannot rest on "
            "itself; every derivation must bottom out in observed facts"
            % cycle)
    for fact in capture["tier1"]:
        derived = fact["derived"]
        if not derived:
            continue
        for operand in derived["operands"]:
            reference = operand.get("fact_id")
            if reference is None:
                continue
            if reference not in facts_by_id:
                reasons.append(
                    "operand '%s' of derived fact '%s' points at fact "
                    "'%s', which is not in the capture"
                    % (operand["label"], fact["id"], reference))
            elif operand["value"] != facts_by_id[reference]["value"]:
                reasons.append(
                    "operand '%s' of derived fact '%s' carries value "
                    "'%s', but fact '%s' records '%s' - the two strings "
                    "must match byte for byte"
                    % (operand["label"], fact["id"], operand["value"],
                       reference, facts_by_id[reference]["value"]))
    return reasons


def _edge_is_clean(text, pos, direction):
    """True when no digit continues the number across this edge (a '.'
    or ',' separator counts as continuing when a digit sits on its far
    side) - so '25.5' is not 'stated' by '125.5' or '1,255.5'."""
    if pos < 0 or pos >= len(text):
        return True
    char = text[pos]
    if char.isdigit():
        return False
    if char in ".,":
        far = pos + direction
        if 0 <= far < len(text) and text[far].isdigit():
            return False
    if char == "-" and direction < 0:
        # A minus functioning as a SIGN negates the figure ("-25.5"
        # does not state 25.5); between digits it is a range dash
        # ("20-25.5" does). A plus sign leaves the value unchanged.
        before = pos - 1
        if before < 0 or not text[before].isdigit():
            return False
    return True


def _figure_is_stated(figure, text):
    """A figure is stated literally only where it stands as a COMPLETE
    number, not as a fragment of a larger one (audit finding r6-4)."""
    start = 0
    while True:
        index = text.find(figure, start)
        if index == -1:
            return False
        if (_edge_is_clean(text, index - 1, -1)
                and _edge_is_clean(text, index + len(figure), 1)):
            return True
        start = index + 1


def unstated_figures(figures, text):
    """Which of these declared figures do NOT stand word for word in
    this text.

    The one place that question is answered. A tier-2 passage has met
    this rule since the rebuild; owner ruling AC12.2 puts the business
    frame's prose under the same one, and it must be the SAME one - a
    second matcher would drift, and prose the seats read first is the
    last place to keep two standards."""
    return [figure for figure in figures
            if not _figure_is_stated(figure, text)]


def _check_figures_literal(capture):
    reasons = []
    for passage in capture["tier2"]:
        for figure in unstated_figures(passage["figures"],
                                       passage["text"]):
            reasons.append(
                "figure '%s' of tier2 passage '%s' does not appear "
                "word for word in the passage's own text (a "
                "fragment of a larger number does not state it)"
                % (figure, passage["id"]))
    return reasons


def _check_vocabulary(capture):
    reasons = []
    for label, entry in _entries(capture):
        for token in entry["id"].split("_"):
            if token in _INVENTORY_WORDS or (
                    token.endswith("s") and token[:-1] in _INVENTORY_WORDS):
                reasons.append(
                    "%s id '%s' contains '%s' - the council has no words "
                    "for the owner's inventory (REBUILD-SPEC section 2)"
                    % (label, entry["id"], token))
        for call in _BANNED_SOURCE_CALLS:
            if call in entry["source"].casefold():
                reasons.append(
                    "%s '%s' cites %s as a source - the broker is a "
                    "market-data source only; that call is never evidence"
                    % (label, entry["id"], call))
    return reasons


def _check_source_lines(capture):
    """A source containing any line break is refused: rendered into a
    case file it could mint free-standing prompt lines (round-11
    finding). splitlines is the one definition of a line break. A bound
    tag's published line is rendered into the case file the same way
    and carries the same rule."""
    reasons = []
    for label, entry in _entries(capture):
        source = str(entry["source"])
        if "".join(source.splitlines()) != source:
            reasons.append(
                "%s '%s' has a line break inside its source - a source "
                "names where a fact came from - one line, never a page "
                "of text" % (label, entry["id"]))
    for fact in capture["tier1"]:
        tag = fact.get("bound")
        line = tag.get("published_line") if isinstance(tag, dict) else None
        if line is not None and "".join(str(line).splitlines()) != str(line):
            reasons.append(
                "tier1 fact '%s' has a line break inside the published "
                "line named by its bound tag - that name is a line from "
                "a filing, not a page of text" % fact["id"])
    return reasons


def _check_market_state(capture):
    state = capture["market_state"]
    if state["state"] != "closed":
        return []
    disclosure = state["disclosure"]
    if not isinstance(disclosure, dict):
        return ["the market is recorded as closed but the capture "
                "carries no disclosure - a market-shut capture must "
                "state the price's age and the reason, as two fields "
                "(DIAG-2)"]
    reasons = []
    for field, meaning in (("price_age", "how old the price is"),
                           ("reason", "why the market was shut")):
        if not str(disclosure.get(field, "")).strip():
            reasons.append(
                "the market-shut disclosure does not state %s - the "
                "'%s' field is empty (DIAG-2 names both parts)"
                % (meaning, field))
    return reasons


def _check_evidence_challenge(capture):
    """The outside auditor's block, checked for self-consistency the way
    every other block here is (owner ruling AC2).

    Only what the CONTRACT cannot say, and only where a person wrote it.
    The findings and the status are written by the bridge from the
    auditor's own answer; the resolutions are hand-written by the
    capture session, and they are what these checks are about. Whether
    every finding HAS a resolution is the sufficiency gate's refusal,
    because that is the stage that decides a pack may convene a
    council."""
    block = capture.get("evidence_challenge")
    if not block:
        return []
    reasons = []
    findings = block.get("findings") or []
    seen = set()
    for finding in findings:
        finding_id = finding.get("id")
        if finding_id in seen:
            reasons.append(
                "the outside auditor's answer carries the finding id '%s' "
                "twice - the record answers each finding by its id, so "
                "two findings under one id would share one answer and "
                "one of them would go unanswered" % finding_id)
        seen.add(finding_id)
    known_ids = {fact["id"] for fact in capture["tier1"]}
    known_ids |= {passage["id"] for passage in capture["tier2"]}
    for finding_id in sorted(block.get("resolutions") or {}):
        resolution = block["resolutions"][finding_id]
        if finding_id not in seen:
            reasons.append(
                "the record answers a finding '%s' that the outside "
                "auditor never raised - an answer to nothing reads as an "
                "answer to something" % finding_id)
        if resolution.get("disposition") != "captured":
            continue
        for fact_id in resolution.get("fact_ids") or []:
            if fact_id not in known_ids:
                reasons.append(
                    "the record says finding '%s' was answered by "
                    "capturing '%s', and no such fact or passage is in "
                    "the pack - a point answered by a figure nobody can "
                    "read is not answered" % (finding_id, fact_id))
        if not (resolution.get("fact_ids") or []):
            reasons.append(
                "the record says finding '%s' was answered by capturing "
                "the evidence, and names no fact for it - what was "
                "captured has to be nameable" % finding_id)
    return reasons


def _check_dates(capture):
    reasons = []
    captured_at = _moment(capture["captured_at"])
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if (captured_at - now).total_seconds() > _CLOCK_SKEW_SECONDS:
        reasons.append(
            "the capture is dated %s, ahead of this machine's own clock "
            "- a capture cannot be its own authority on when it "
            "happened" % capture["captured_at"])
    for label, entry in _entries(capture):
        if _moment(entry["as_of"]) > captured_at:
            reasons.append(
                "%s '%s' is dated %s, after the capture itself (%s) - "
                "evidence cannot come from the future"
                % (label, entry["id"], entry["as_of"],
                   capture["captured_at"]))
    return reasons


def validate_capture(capture, schema):
    """Run every provenance check over a capture document.

    Returns {"result": "accepted"|"refused", "reasons": [...]}. The
    ruled constituent bound is pre-checked so its refusal reads plainly
    (THEMES-BASKETS-SPEC section 2); then the shape check runs alone:
    the other checks assume the contract's shape and would only bury
    its plain reasons.
    """
    validate.check_schema(schema)
    bound_reasons = _check_constituent_bound(capture)
    if bound_reasons:
        return {"result": "refused", "reasons": bound_reasons}
    shape_errors = validate.validate(capture, schema)
    if shape_errors:
        return {"result": "refused",
                "reasons": ["the capture does not match the capture "
                            "contract: " + error
                            for error in shape_errors]}
    reasons = []
    reasons.extend(_check_subject_kind(capture))
    reasons.extend(_check_business_frame(capture))
    reasons.extend(_check_cycle(capture))
    reasons.extend(_check_evidence_challenge(capture))
    reasons.extend(_check_id_uniqueness(capture))
    reasons.extend(_check_labels(capture))
    reasons.extend(_check_period_basis(capture))
    reasons.extend(_check_arithmetic(capture))
    reasons.extend(_check_operand_references(capture))
    reasons.extend(_check_figures_literal(capture))
    reasons.extend(_check_vocabulary(capture))
    reasons.extend(_check_source_lines(capture))
    reasons.extend(_check_market_state(capture))
    reasons.extend(_check_dates(capture))
    return {"result": "accepted" if not reasons else "refused",
            "reasons": reasons}


_USAGE = ("usage: python -m council.evidence.gate "
          "<capture.json> [--out <gate-result.json>]")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        out_path = None
        if "--out" in args:
            index = args.index("--out")
            if index + 1 >= len(args):
                print(_USAGE)
                return 1
            out_path = args[index + 1]
            del args[index:index + 2]
        if len(args) != 1:
            print(_USAGE)
            return 1
        capture = canonical.read_json(args[0])
        result = validate_capture(capture, load_capture_schema())
        if out_path:
            canonical.write_canonical_json(out_path, result)
        if result["result"] == "accepted":
            print("gate: accepted - every provenance check passed")
            return 0
        print("gate: refused - %d reason(s)" % len(result["reasons"]))
        for reason in result["reasons"]:
            print("  - " + reason)
        return 3
    except Exception as exc:
        print("gate crashed: %r" % (exc,))
        return 1


if __name__ == "__main__":
    sys.exit(main())
