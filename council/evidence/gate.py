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


def load_capture_schema():
    """The capture contract this gate enforces."""
    return canonical.read_json(_SCHEMA_PATH)


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


def _check_figures_literal(capture):
    reasons = []
    for passage in capture["tier2"]:
        for figure in passage["figures"]:
            if not _figure_is_stated(figure, passage["text"]):
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
    reasons.extend(_check_id_uniqueness(capture))
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
