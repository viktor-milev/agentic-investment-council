"""The one-page evidence brief (owner ruling AC3, spec section U3.1).

Deterministic text, generated from the frozen pack: no model call, no
network, nothing on this page that is not already in the pack. Every
figure is the exact string the capture recorded (PRECISION-REG-1) - a
page that rounded a value would show the reader a different number from
the one the seats will argue over.

It is the page a person reads before saying go: the question, what the
business is, the numbers that decide it, what the outside auditor asked
for and what happened, what the record admits it does not carry, the
price and the calendar, and what the capture stage cost. One page is the
ruling, so every section is bounded and says plainly when it left
something in the pack.

CLI:
    python -m council.evidence.brief <pack.json> --out <dir>/brief.md
                                     [--usage <dir>/capture-usage.json]
The capture's own cost sidecar defaults to capture-usage.json beside the
brief. Exit codes: 0 written, 1 usage error or crash.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.evidence import gate, tape, trace  # noqa: E402
from council.lib import canonical  # noqa: E402

# One page is the ruling (AC3), and a schema-valid capture can write at
# any length, so this page BOUNDS what it shows and says where the rest
# is - the same discipline the report's two-page front lives under. The
# whole of everything below is in the pack the council reads.
MAX_ROWS = 5
MAX_FRAMES = 3
FRAME_MAX_LINES = 12
TRIM_CHARS = 200
SHORT_TRIM = 120
PAGE_LINES = 72
IN_THE_PACK = "the whole of it is in the pack"

# A pack with no daily price series has no tape and no chart; the page
# says so rather than leaving a reader to wonder what they would have
# said (architect ruling 3 of unit U4(c): the tape and the chart are built
# now, so the line names what the pack lacks, not a later unit). The
# verdict's report page prints this same line where its chart would be.
# The line states what the pack carries, chosen by one predicate with three
# outcomes (architect ruling, Step 0 of U4(c) audit round 2, replacing the
# round-1 rule): a price and a matched 52-week range, a price alone, or no
# price at all. `tape_notice_case` decides and `tape_placeholder` words it,
# for the brief and the report page alike.
TAPE_PLACEHOLDER_RANGE = ("This pack carries no daily price series, so "
                          "there is no price chart and no tape table: the "
                          "price and its 52-week range are the whole of "
                          "what it says about the tape.")
TAPE_PLACEHOLDER_PRICE = ("This pack carries no daily price series, so "
                          "there is no price chart and no tape table: the "
                          "price alone is what it says about the tape.")
TAPE_PLACEHOLDER_NONE = ("This pack carries no daily price series and no "
                         "price, so there is no price chart and no tape "
                         "table: it says nothing about the tape.")

# Once the freeze has drawn the tape from a price series, the placeholder
# above would be false (audit round 4 of U4a2, r4-1): the page points to
# where the tape's figures are printed instead - by name in the full
# evidence document, and on one page with the price chart in the
# verdict's report (unit U4(c)).
TAPE_POINTER = ("The pack carries the tape's %d figures, drawn from its "
                "price series; the full evidence document prints each by "
                "name. Their one-page summary, with the price chart, is on "
                "the verdict's report page.")
# A series too short for any tape row (a recent listing) gives a tape of
# declared gaps only; the page must not call that tape unbuilt (audit
# round 5 of U4a2, r5-1). The line is chosen by whether the pack carries
# a price series, never by counting figures (round 6 ruling).
TAPE_ALL_GAPS = ("The pack carries a price series, but its history is too "
                 "short for any tape figure; the full evidence document "
                 "lists each missing figure by name.")

# A dated event is a tier-1 fact whose id begins with this. The report's
# own calendar uses the same rule (render_report.CALENDAR_PREFIX) and the
# two are pinned equal by the evidence suite: one calendar read two ways
# is one calendar nobody can trust.
CALENDAR_PREFIX = "calendar_"

PRICE_ID = "price_last"
RANGE_LOW_ID = "range_52w_low"
RANGE_HIGH_ID = "range_52w_high"

# The head line of every rendered brief and full document names the pack
# it was built from, with this exact prefix in front of the sha256 in
# back-ticks. `host init` reads the pack off THIS line to confirm the
# document a person approved describes the pack the council was handed,
# and refuses when it does not (register item P-U3d-5). The renderer and
# the parser share the one literal - the way CALENDAR_PREFIX is shared
# with the report - so a reword cannot silently unmatch them.
PACK_HEAD_PREFIX = "**The frozen pack:** sha256 "


def _one_line(text):
    return " ".join(str(text if text is not None else "").split())


def _safe(text):
    """The ONE neutralization both the one-page brief and the full document
    put every untrusted, model-written string through before rendering it:
    capture prose, the plain-English fact labels, source sentences, and the
    outside auditor's own ids, details, overall reading and resolutions
    (owner rulings AC15/AC3; register item P-U3d-6).

    The document a person approves is Markdown, and a reviewer may read it
    in a viewer that renders inline HTML. So a model string is made unable
    to forge structure in the document he approves: it is collapsed to one
    line, so it cannot inject a break and begin a block of its own; its `&`,
    `<` and `>` are escaped, so it cannot open an HTML tag; its back-ticks
    are escaped, so it cannot open a code fence or an inline span; and a
    leading heading or fence marker is escaped, so a value placed at the
    start of a line - a passage's text, the question - cannot open a
    heading. The value still reads as itself in any Markdown viewer.

    The numeric figures and the machine ids the renderer wraps in
    back-ticks are unaffected: a number and a snake_case id carry none of
    the characters escaped below, so they pass through as themselves. Only
    the schema's fixed enums are passed to the renderer raw (they cannot
    hold these characters either). Every OTHER value a model wrote - a
    fact's value or unit, which the schema lets be free text and not a
    number (round 3, r3-2), a passage's stated figures, and all prose - now
    passes through here.

    What it neutralizes (round 3, r3-3 - the round-2 helper stopped only at
    tags, back-ticks and a leading heading, and a model image then fetched
    an attacker's remote resource into the document a person approves):
    - `&`, `<`, `>` -> HTML entities, so no tag opens even where the viewer
      renders raw HTML (a backslash escape would not stop it there);
    - a back-slash first, so a model cannot use one to undo the escapes
      below;
    - a back-tick, a `[`, a `]`, a `*` and a `|`, anywhere on the line, so
      no code span or fence, no link, no remote image (`![alt](url)`), no
      `*`-emphasis or `***` rule, and no extra table cell (finding r2-7 - a
      value in a points table cell forged one) can form;
    - a leading `#`, so a value rendered at the start of its own line
      (a passage's text, the question) cannot open a heading.
    Left active, as a deliberate trade for keeping every figure the exact
    string the capture recorded (owner ruling AC3): a leading `-`, `+`, `=`
    or `~`, which can begin a negative or approximate figure, and `_`, which
    is not emphasis inside a word - so a `---` rule, a `- ` list or a `~~~`
    fence a model writes at the very start of a passage renders as itself
    rather than as the mark. These forge nothing a reader reads as evidence;
    the material vectors above are closed. Each escaped character still
    reads as itself in a Markdown viewer."""
    return _escape(_one_line(text))


def _escape(text):
    """The character escaping of _safe, without the collapse to one line.
    Split out for owner ruling AC19 (unit U3f): the untraced-figure marker
    is placed BETWEEN stretches of model prose, and each stretch is escaped
    here while the marker itself is emitted raw - exactly as _safe escapes
    prose while _freshness_mark's bracketed STALE mark is not. `_safe` is
    still `_escape(_one_line(...))`, byte for byte what it was."""
    s = str(text if text is not None else "")
    s = s.replace("\\", "\\\\")
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for character in "`[]*|":
        s = s.replace(character, "\\" + character)
    if s[:1] == "#":
        s = "\\" + s
    return s


_MARKS_CONFIG = None


def _marks_config():
    """The render-time figure-marking data (tolerances and exemptions),
    read once from the ruled floors file (owner ruling AC19(4))."""
    global _MARKS_CONFIG
    if _MARKS_CONFIG is None:
        _MARKS_CONFIG = trace.config(canonical.read_json(gate._FLOORS_PATH))
    return _MARKS_CONFIG


def _frame_bases(capture, ticker):
    """The recorded fact values this frame's prose numbers are traced
    against (owner ruling AC19)."""
    return trace._fact_bases(capture, ticker, _marks_config())


def _marked(text, bases):
    """`text` for the document a person approves, with the untraced-figure
    marker after every number that traces to no recorded fact (owner ruling
    AC19). Collapsed to one line and escaped exactly as _safe would, the
    marker aside. Where nothing is untraced this is _safe(text).

    separate_after=True: this is a Markdown document, so a '(' immediately
    after the marker is escaped, keeping the mark from becoming link text
    (audit UPGRADE2-U3f r5-1)."""
    return trace.mark(_one_line(text), bases, _marks_config(), _escape,
                      separate_after=True)


def _marked_trim(text, bases, budget=TRIM_CHARS, figures=()):
    """As _marked, on the one-page brief's trimmed value: the trim runs
    first, so the marker only ever falls on a number the page actually
    shows (owner ruling AC19). Markdown document, so separate_after=True
    (audit UPGRADE2-U3f r5-1)."""
    return trace.mark(_trim(text, budget, figures), bases, _marks_config(),
                      _escape, separate_after=True)


def _cut_point(text, budget, figures):
    """Where this value may be cut: at a space, never inside a figure the
    capture DECLARED, and never straight after a word carrying a digit.

    A declared figure can itself carry a space - `$12.5 billion` - so a
    whole-word cut still halves one, and `$12.5` is a different number
    by a factor of a billion (audit round 2, r2-2). Where a figure
    straddles the cut, the cut moves back to before it, so the page
    shows the figure whole or not at all.

    Two of this page's trimmed values have no declared figures to move
    back for, and no way of ever getting any: a fact's or passage's own
    SOURCE sentence, and a dated event's own description (register item
    P-U3-6). Both routinely carry numbers and dates, and the capture
    contract has no field that declares them. So the last word this page
    shows may never carry a digit - `$12.5 billion` cut after `$12.5`, a
    quarter cut after `Q3`, a date cut after `March 15,` all end on one -
    and the cut moves back to the whitespace before that word. The page
    shows a little less than it might have; it never shows part of a
    number, which is the trade the owner's one-page ruling makes.

    A figure the collapsed text does not contain is passed over in
    silence: the gate matched it against the raw value, and a figure
    written across a line break is legal there and unfindable here."""
    point = len(text[:budget + 1].rsplit(" ", 1)[0].rstrip())
    spans = []
    for figure in figures or ():
        figure = _one_line(figure)
        if not figure:
            continue
        at = text.find(figure)
        while at != -1:
            spans.append((at, at + len(figure)))
            at = text.find(figure, at + 1)
    while point > 0:
        straddling = [start for start, end in spans if start < point < end]
        if straddling:
            point = len(text[:min(straddling)].rstrip())
            continue
        last = text[:point].rsplit(" ", 1)[-1]
        if any(character.isdigit() for character in last):
            point = len(text[:point - len(last)].rstrip())
            continue
        break
    return point


def _trim(text, budget=TRIM_CHARS, figures=()):
    """One value, cut to the page's budget with a pointer to where the
    whole of it lives.

    The cut lands BETWEEN words, never inside one, and never inside a
    declared figure. A raw character slice turned `12.5%` into `1` - a
    different number, on the page a person approves (audit round 1,
    r1-7). Where what is left would still overrun the budget - a first
    word longer than the whole of it, or a figure that starts too early
    - the page shows no part of it: nothing is better than a wrong
    figure, and the pointer still says where the whole of it is."""
    text = _one_line(text)
    if len(text) <= budget:
        return text
    head = text[:_cut_point(text, budget, figures)]
    if len(head) > budget:
        head = ""
    return "%s... (%s)" % (head, IN_THE_PACK)


def _rows(items, what):
    """The first few of a list, plus one plain sentence when the rest
    were left in the pack. Returns (shown, note_or_None)."""
    items = list(items)
    if len(items) <= MAX_ROWS:
        return items, None
    return (items[:MAX_ROWS],
            "Showing %d of %d %s; %s."
            % (MAX_ROWS, len(items), what, IN_THE_PACK))


def _facts_by_id(capture):
    return {fact.get("id"): fact for fact in capture.get("tier1") or []}


def _passages_by_id(capture):
    return {item.get("id"): item for item in capture.get("tier2") or []}


def _freshness_mark(pack, fact_id):
    """STALE, in the reader's face, where the pack's own freshness record
    says the figure is older than its rule allows (owner ruling AC11)."""
    entry = (pack.get("freshness") or {}).get(fact_id) or {}
    if entry.get("status") != "stale":
        return ""
    return (" [STALE at capture: %s days old against a %s-day rule]"
            % (entry.get("age_days"), entry.get("rule_days")))


def _figure(pack, facts, fact_id, passages=None):
    """One frozen answer, as the capture wrote it: value, unit, date,
    staleness. Never reformatted, never recomputed.

    A decisive metric may be answered by a tier-2 PASSAGE that states its
    figures - a backlog written in prose is still a frozen answer - so
    the passage is rendered by the figures it declares, which are already
    checked to stand literally in its own words."""
    fact = facts.get(fact_id)
    if fact is None:
        passage = (passages or {}).get(fact_id)
        if passage is None:
            return "`%s` is named but is not in the pack" % _one_line(fact_id)
        figures = ", ".join(_safe(item)
                            for item in passage.get("figures") or [])
        return "`%s` (passage, as of %s) states %s: %s" % (
            _one_line(fact_id), _one_line(passage.get("as_of")),
            figures or "no figure",
            _safe(_trim(passage.get("text"), SHORT_TRIM,
                        passage.get("figures"))))
    unit = _safe(fact.get("unit"))
    return "`%s` = %s%s (as of %s)%s" % (
        _one_line(fact_id), _safe(fact.get("value")),
        (" " + unit) if unit else "", _one_line(fact.get("as_of")),
        _freshness_mark(pack, fact_id))


def _source(facts, fact_id, passages=None):
    entry = facts.get(fact_id) or (passages or {}).get(fact_id)
    if entry is None:
        return "no source: the id is not in the pack"
    return _safe(_trim(entry.get("source"), SHORT_TRIM))


# ------------------------------------------------------------- sections


def _head_lines(pack, pack_sha256):
    capture = pack["capture"]
    subject = capture.get("subject") or {}
    name = _safe(subject.get("name"))
    ticker = _safe(subject.get("ticker"))
    lines = ["# The evidence, in one page - what the council will be "
             "allowed to know", ""]
    lines.append("**Subject:** %s%s - %s. **Captured:** %s."
                 % (name or "not named",
                    (" (%s)" % ticker) if ticker else "",
                    _one_line(subject.get("kind")) or "kind not stated",
                    _one_line(capture.get("captured_at"))))
    # What this line may claim, and what it may not (closing pass, r7-1;
    # closing incremental, r8-1). The page is ASSEMBLED by rule and
    # nothing on it was written for it - but it quotes the capture
    # session's prose and the outside auditor's own words, and this
    # project treats both as untrusted model output. The page exists so
    # a person can CHECK model output; a head telling him there is none
    # to check was the worst sentence it could carry. Nor may the head
    # bind the WHOLE page to the pack's hash: the last section is the
    # capture stage's cost sidecar, which the freeze does not include,
    # so the same pack and the same hash render two different pages.
    lines.append("%s`%s`. Every line below is "
                 "assembled by rule and nothing was written for this page: "
                 "the evidence comes from the pack that hash names, and "
                 "what the stage cost comes from its own sidecar, which "
                 "the hash does not cover. The words quoted are the "
                 "capture session's and the outside auditor's own, to be "
                 "read as such." % (PACK_HEAD_PREFIX, pack_sha256))
    lines.append("")
    return lines


def pack_sha256_at_head(text):
    """The pack sha256 a rendered brief or full document names on its head
    line, or None when that line is absent. `host init` reads it to confirm
    the document a person approved describes the pack the council was handed
    (register item P-U3d-5): it parses the one line the renderer prints and
    never re-renders. Lower-cased, so the comparison the host makes is the
    case-insensitive one it already makes on the recorded hashes."""
    for line in text.splitlines():
        if line.startswith(PACK_HEAD_PREFIX):
            rest = line[len(PACK_HEAD_PREFIX):]
            if rest.startswith("`"):
                end = rest.find("`", 1)
                if end > 1:
                    return rest[1:end].strip().lower()
    return None


# Owner ruling AC32 with the architect ruling closing P-FIb-1: the page the
# owner approves (owner ruling AC3) carries the capture's one-line question
# at its top, so the report's masthead may print that line on his approval.
QUESTION_LINE_LABEL = "The question, in one line:"


def question_line(capture):
    """The capture's one-line question, spaces collapsed, or None for a
    capture written before 1.8.0 (the first contract that carries it) or
    one that carries no line."""
    line = capture.get("question_line")
    try:
        version = tuple(int(part) for part in
                        str(capture.get("capture_version")).split("."))
    except ValueError:
        return None
    if version < (1, 8, 0) or not isinstance(line, str) or not line.strip():
        return None
    return " ".join(line.split())


def question_line_row(capture):
    """The row the brief prints for the capture's one-line question, or None."""
    line = question_line(capture)
    return "%s %s" % (QUESTION_LINE_LABEL, _safe(line)) if line else None


def _question_lines(capture):
    lines = ["## The question", ""]
    row = question_line_row(capture)
    if row:
        lines += [row, ""]
    return lines + [_safe(capture.get("question_verbatim"))
                    or "The pack carries no question.", ""]


def _how_it_earns_words(frame, bases):
    shown, note = _rows(frame.get("how_it_earns") or [], "revenue lines")
    parts = ["%s (%s of the latest reported period)"
             % (_marked_trim(row.get("line"), bases, SHORT_TRIM,
                             row.get("figures")),
                _one_line(row.get("share_of_period")))
             for row in shown]
    words = "; ".join(parts) if parts else "no revenue lines are stated"
    return words + ("" if note is None else " - " + note)


def _management_words(pack, facts, frame):
    management = frame.get("management") or {}
    bits = []
    for label, key in (("CEO tenure", "ceo_tenure_years"),
                       ("CFO tenure", "cfo_tenure_years"),
                       ("insider ownership", "insider_ownership_pct")):
        fact_id = management.get(key)
        if fact_id:
            bits.append("%s %s" % (label, _figure(pack, facts, fact_id)))
    rows, note = _rows(management.get("guidance_vs_delivery") or [],
                       "guided quarters")
    for row in rows:
        guided = ", ".join(_figure(pack, facts, fact_id)
                           for fact_id in row.get("guided") or [])
        revisions = row.get("revisions")
        if isinstance(revisions, list):
            # Owner ruling AC30(6): the FIRST guidance, then each revision
            # with its date, then what was delivered - delivery is judged
            # against the first; an empty list says it was never revised.
            revised = "; ".join(
                "revised on %s to %s"
                % (_safe((item or {}).get("date")),
                   ", ".join(_figure(pack, facts, fact_id)
                             for fact_id in (item or {}).get("guided")
                             or []) or "nothing named")
                for item in revisions) or FI_NEVER_REVISED
            bits.append("%s first guided %s; %s; delivered %s"
                        % (_safe(row.get("period")),
                           guided or "nothing named", revised,
                           _figure(pack, facts, row.get("delivered"))))
            continue
        bits.append("%s guided %s, delivered %s"
                    % (_safe(row.get("period")),
                       guided or "nothing named",
                       _figure(pack, facts, row.get("delivered"))))
    if note is not None:
        bits.append(note)
    if not bits:
        return "the pack states nothing about management"
    return "; ".join(bits)


def _peers_words(frame):
    shown, note = _rows(frame.get("peers") or [], "peers")
    if not shown:
        return ("no peer set: the pack declares the gap rather than "
                "naming doubtful comparisons")
    words = ", ".join("%s (%s)" % (_safe(_trim(peer.get("name"), SHORT_TRIM)),
                                   _safe(peer.get("ticker")))
                      for peer in shown)
    return words + ("" if note is None else " - " + note)


_DECLINE_WORDS = {
    "by_design": "the fall in the headline figures is BY DESIGN",
    "deterioration": "the fall in the headline figures is DETERIORATION",
    "mixed": "the fall in the headline figures is MIXED",
    "unknown": "the fall in the headline figures is NOT READ - the pack "
               "declares that as a gap",
}

# Owner ruling AC15 (P2, unit U3e): the archetype and the rating measure
# it calls for, in plain words for the owner's page and the seats.
_ARCHETYPE_WORDS = {
    "profitable_operator": "profitable operator",
    "ramping_infrastructure_builder": "ramping infrastructure builder",
    "stabilised_lessor": "stabilised lessor",
    "no_earnings_asset": "asset with no earnings",
    "financial_institution": "financial institution",
}
_MEASURE_WORDS = {
    "earnings_vs_history_and_peers":
        "earnings against its own history and peers",
    "ev_per_contracted_capacity_and_contracted_revenue_per_unit":
        "enterprise value per unit of contracted capacity and contracted "
        "revenue per unit",
    "ev_to_operating_income": "enterprise value to operating income",
    "anchorless_ladder": "the anchorless scenario ladder",
    # Owner rulings AC28 and AC30 (FI-ARCHETYPE (b)): the financial
    # institution and its six measures, one wording on every page.
    "price_to_tangible_book_against_return_on_tangible_equity":
        "price against tangible book, read against the return on tangible "
        "equity",
    "price_to_book_against_operating_return_on_equity":
        "price against book, read against the operating return on equity",
    "price_to_book_against_return_on_equity":
        "price against book, read against the return on equity",
    "price_to_earnings_against_return_on_client_assets":
        "price against earnings, read against the return on client assets",
    "price_to_fee_earnings_against_fee_earning_assets":
        "price against fee earnings, read against the fee-earning assets",
    "price_to_net_asset_value": "price against net asset value",
}
# The same table under a public name, so the seats' case file (unit
# FI-ARCHETYPE (c)) reads this one wording rather than a second copy.
MEASURE_WORDS = _MEASURE_WORDS

# Owner rulings AC28 and AC30 (FI-ARCHETYPE (b), the page): the plain words
# for what a financial institution's frame declares. The report carries the
# same wording in its own tables (a test holds the two equal).
FI_ARCHETYPE = "financial_institution"
FI_HOLDING = "financial_holding"
FI_SUBTYPE_WORDS = {
    "bank": "a bank",
    "insurer": "an insurer",
    "reinsurer": "a reinsurer",
    "traditional_asset_manager": "a traditional asset manager",
    "alternative_asset_manager": "an alternative asset manager",
    "financial_holding": "a financial holding company",
}
FI_RISK_KIND_WORDS = {
    "credit": "credit losses",
    "underwriting": "underwriting losses",
    "none_by_design": "none by design",
}
FI_NATURE_WORDS = {
    "spread": "spread income",
    "fee": "fee income",
    "underwriting": "underwriting income",
    "investment": "investment income",
    "trading": "trading income",
    "performance": "performance fees",
    "other": "other income",
}
FI_METHOD_WORDS = {
    "listed_at_market": "a listed stake at its market price",
    "company_reported_value": "the value the company itself reports",
    "carrying_value": "the value it is carried at in its own books",
}
FI_NOT_RATED_SENTENCE = ("The companies this holding owns were not rated in "
                         "this sitting.")
FI_FREE_CASH_WORDS = ("capital the firm can pay out and still stay above its "
                      "regulator's minimum")
FI_STRESS_HEADING = "The regulator's own bad year for this firm"
FI_STRESS_PREFIX = "stress_"
FI_NEVER_REVISED = "never revised"

_FLOORS = None


def _floors():
    """The ruled floors file, read once (the FI families and the lift)."""
    global _FLOORS
    if _FLOORS is None:
        _FLOORS = canonical.read_json(gate._FLOORS_PATH)
    return _FLOORS


def fi_lifted_subtypes():
    """The sub-types whose free-cash test is answered by distributable
    capital (owner ruling AC30(1)), as the floors rule them."""
    lifts = (((_floors().get("archetype_floors") or {})
              .get(FI_ARCHETYPE) or {}).get("lifts") or {})
    return tuple(lifts.get("subtypes") or ())


def fi_capital_pairs(capital):
    """Each capital ratio beside the requirement FOR THAT RATIO (the suffix
    rule the floors' fi_families read: 'cet1_ratio_<x>' beside
    'cet1_requirement_<x>'), in the order the frame names the ratios; a
    ratio with no partner named stands with None, and a requirement no
    ratio claimed follows with None as its ratio. Pairing only - the
    sufficiency gate is where a missing partner refuses."""
    families = _floors().get("fi_families") or {}
    prefix_pairs = list(zip(families.get("capital_ratio_prefixes") or (),
                            families.get("capital_requirement_prefixes")
                            or ()))
    ratios = [fid for fid in capital.get("ratio_facts") or ()
              if isinstance(fid, str)]
    requirements = [fid for fid in capital.get("requirement_facts") or ()
                    if isinstance(fid, str)]
    pairs, claimed = [], set()
    for ratio in ratios:
        partner = None
        for ratio_prefix, requirement_prefix in prefix_pairs:
            if ratio.startswith(ratio_prefix):
                wanted = requirement_prefix + ratio[len(ratio_prefix):]
                if wanted in requirements:
                    partner = wanted
                break
        if partner is not None:
            claimed.add(partner)
        pairs.append((ratio, partner))
    pairs.extend((None, fid) for fid in requirements if fid not in claimed)
    return pairs


def fi_stress_evidence(capture, ticker):
    """The stress facts (sorted ids) and stress gaps that are THIS
    frame's own (owner ruling AC30(5)), stated whole here once: a single
    name (gate.frame_suffix empty) keeps every stress fact and gap, a
    double-underscore tail on its id included (audit round 6, r6-1); a
    basket member keeps only those wearing its own member suffix or none
    (gate._id_suffix), so it never shows another member's supervisory
    result as its own (round 5, r5-1). The full document and the report
    read this one selection."""
    suffix = gate.frame_suffix(capture.get("subject") or {}, ticker)

    def own(identifier):
        return (identifier.startswith(FI_STRESS_PREFIX)
                and (not suffix
                     or gate._id_suffix(identifier) in ("", suffix)))

    stress = sorted(str(fact.get("id")) for fact in capture.get("tier1") or []
                    if isinstance(fact.get("id"), str) and own(fact["id"]))
    gaps = [gap for gap in capture.get("gaps") or []
            if own(str(gap.get("fact_class") or ""))]
    return stress, gaps


def fi_subject_frame(capture):
    """The single name's own frame where it declares the financial
    institution, or None."""
    subject = capture.get("subject") or {}
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    if isinstance(frame, dict) and frame.get("archetype") == FI_ARCHETYPE:
        return frame
    return None


def _rating_measure(capture):
    """The measure the third canonical test declares, or None."""
    for row in (capture.get("sufficiency") or {}).get("requirements") or []:
        if row.get("id") == "rating_vs_history_or_peers":
            return row.get("measure")
    return None


def _rating_subject_denominators(capture):
    """The subject-side denominator fact ids the rating measure divides by
    (owner ruling AC15 P2, unit U3e; finding r2-4). They are decisive - the
    rating's computability rests on them - and can be facts the rating row
    does not also list in answered_by, so the full document a person
    approves names them so none is invisible to him."""
    for row in (capture.get("sufficiency") or {}).get("requirements") or []:
        if row.get("id") == "rating_vs_history_or_peers":
            return row.get("subject_denominator_facts") or []
    return []


def _fi_value(pack, facts, fact_id):
    """One fact a financial institution's frame names, as the page shows
    it: its plain label where one exists, then the frozen value. The id is
    named in the file's own voice ONLY when it is a tier-1 id of this pack;
    anything else is sent through _safe, as data (P-U3e-3)."""
    if not isinstance(fact_id, str) or fact_id not in facts:
        return "%s (not in the pack)" % _safe(fact_id)
    label = str(facts[fact_id].get("label") or "").strip()
    figure = _figure(pack, facts, fact_id)
    return ("%s: %s" % (_safe(label), figure)) if label else figure


def _fi_values(pack, facts, fact_ids):
    return ", ".join(_fi_value(pack, facts, fid) for fid in fact_ids or ())


def fi_kind_words(frame, escape):
    """What kind of financial firm this is, in the page's words: the
    archetype, the sub-type and, for a hybrid, its other engine. `escape`
    is the renderer's own neutralisation, applied only to a value outside
    the ruled words."""
    subtype = frame.get("fi_subtype")
    words = "financial institution - %s" % (
        FI_SUBTYPE_WORDS.get(subtype) or escape(subtype)
        or "its kind not stated")
    secondary = frame.get("fi_secondary_subtype")
    if secondary:
        words += ", with %s as its other engine" % (
            FI_SUBTYPE_WORDS.get(secondary) or escape(secondary))
    return words


def _fi_capital_words(pack, facts, capital, bases):
    """Capital beside its requirement, on one line: each ratio on the SAME
    line as the requirement for that ratio, or the declared gap's reason."""
    gap = capital.get("gap")
    if gap:
        return "a declared gap - %s" % _marked(gap.get("reason"), bases)
    return "; ".join(_fi_pair_words(pack, facts, ratio, requirement)
                     for ratio, requirement in fi_capital_pairs(capital)
                     ) or "nothing is named"


def _fi_pair_words(pack, facts, ratio, requirement):
    if ratio is None:
        return ("a requirement with no ratio named beside it: %s"
                % _fi_value(pack, facts, requirement))
    if requirement is None:
        return ("%s, with no requirement named beside it"
                % _fi_value(pack, facts, ratio))
    return ("%s beside its requirement %s"
            % (_fi_value(pack, facts, ratio),
               _fi_value(pack, facts, requirement)))


def _fi_archetype_line(capture, frame):
    """The one-page brief's archetype line for a financial institution:
    the kind of firm and the measure, and for a holding the one sentence
    (owner rulings AC28, AC30(3))."""
    measure = _rating_measure(capture)
    line = "- Archetype: %s" % fi_kind_words(frame, _safe)
    if measure:
        line += " - rated on %s" % _MEASURE_WORDS.get(measure, _safe(measure))
    if frame.get("fi_subtype") == FI_HOLDING:
        line += ". " + FI_NOT_RATED_SENTENCE
    return line


def _one_frame_lines(pack, facts, passages, ticker, frame):
    """One business, in a handful of lines (spec section U3.1)."""
    capture = pack["capture"]
    bases = _frame_bases(capture, ticker)
    lines = ["**%s**" % _safe(ticker)]
    # Owner ruling AC19: the one summary line per frame, before the prose,
    # so a reader sees at once how much of this description traces to the
    # record. The numbers below are marked where they are shown.
    lines.append("- %s" % trace.summary_sentence(
        trace.frame_counts(capture, ticker, frame, _marks_config())))
    archetype = frame.get("archetype")
    if archetype == FI_ARCHETYPE:
        # Owner rulings AC28 and AC30: the kind of firm and its capital
        # beside its requirement stand on the one page; the rest of the
        # financial institution is in the full document.
        lines.append(_fi_archetype_line(capture, frame))
        lines.append("- Capital beside its requirement: %s"
                     % _fi_capital_words(pack, facts,
                                         frame.get("fi_capital") or {},
                                         bases))
    elif archetype:
        measure = _rating_measure(capture)
        rated = ((" - rated on %s"
                  % _MEASURE_WORDS.get(measure, _safe(measure)))
                 if measure else "")
        lines.append("- Archetype: %s%s"
                     % (_ARCHETYPE_WORDS.get(archetype, _safe(archetype)),
                        rated))
    lines.append("- What it does: %s"
                 % _marked_trim(frame.get("what_it_does"), bases,
                                figures=frame.get("what_it_does_figures")))
    lines.append("- How it earns: %s" % _how_it_earns_words(frame, bases))
    changing = frame.get("what_is_changing") or {}
    lines.append("- What is changing (%s): %s"
                 % (_one_line(changing.get("kind")) or "not stated",
                    _marked_trim(changing.get("statement"), bases,
                                 figures=changing.get("figures"))))
    decline = frame.get("headline_decline_read")
    if decline:
        lines.append("- The headline read: %s."
                     % _DECLINE_WORDS.get(decline.get("reading"),
                                          _safe(decline.get("reading"))))
    else:
        lines.append("- The headline read: no headline figure has fallen "
                     "against its prior-year pair.")
    lines.append("- Peers: %s" % _peers_words(frame))
    lines.append("- Management: %s" % _management_words(pack, facts, frame))
    standing = frame.get("competitive_position")
    passage = passages.get(standing) or {}
    lines.append("- Competitive standing (passage `%s`): %s"
                 % (_one_line(standing),
                    _safe(_trim(passage.get("text"),
                                figures=passage.get("figures")))
                    or "the passage is not in the pack"))
    cycle_dep = frame.get("cycle_dependence")
    # The reason a single name depends on a cycle (or on none) is required
    # by the gate; carry it on the cycle line, which adds no line to the
    # page's budget (finding r1-8).
    because = frame.get("cycle_dependence_because")
    because_suffix = (" - %s" % _marked(because, bases)) if because else ""
    if cycle_dep == "identified":
        cyc = capture.get("cycle") or {}
        count = len(cyc.get("series") or [])
        detail = ("%d dated series" % count if count
                  else "the series are a declared gap")
        lines.append("- Cycle: identified - %s (%s)%s"
                     % (_safe(cyc.get("name")), detail, because_suffix))
    elif cycle_dep == "none":
        lines.append("- Cycle: none - no identifiable capital or commodity "
                     "cycle this name depends on%s" % because_suffix)
    return lines[:FRAME_MAX_LINES]


def _business_lines(pack, facts, passages, capture):
    frames = capture.get("business_frame") or {}
    lines = ["## The business, before the numbers", ""]
    if not frames:
        lines.append("This pack carries no business frame. It is an asset "
                     "with no earnings to frame, or a fund judged on its "
                     "own anchor set.")
        lines.append("")
        return lines
    tickers, note = _rows(sorted(frames), "businesses")
    tickers = tickers[:MAX_FRAMES]
    if len(frames) > MAX_FRAMES:
        note = ("Showing %d of %d businesses in this pack; %s."
                % (MAX_FRAMES, len(frames), IN_THE_PACK))
    for index, ticker in enumerate(tickers):
        if index:
            lines.append("")
        lines.extend(_one_frame_lines(pack, facts, passages, ticker,
                                      frames[ticker]))
    if note is not None:
        lines.append("- %s" % note)
    lines.append("")
    return lines


def _decisive_lines(pack, facts, passages, capture):
    """The numbers that decide THIS question, with their values and the
    source each came from."""
    lines = ["## The numbers that decide this question", ""]
    stale_ids = gate.stale_reading_ids(capture)
    frames = capture.get("business_frame") or {}
    metrics = []
    for ticker in sorted(frames):
        for metric in (frames[ticker] or {}).get("decisive_metrics") or []:
            metrics.append((ticker, metric))
    if not metrics:
        lines.append("The pack names no decisive metrics: no business "
                     "frame stands in it.")
        lines.append("")
        return lines
    shown, note = _rows(metrics, "decisive metrics")
    for ticker, metric in shown:
        bases = _frame_bases(capture, ticker)
        lines.append("- **%s** (%s, %s): %s"
                     % (_marked_trim(metric.get("name"), bases, SHORT_TRIM),
                        _safe(ticker),
                        _one_line(metric.get("kind")),
                        _marked_trim(metric.get("why_it_decides"), bases,
                                     figures=metric.get("figures"))))
        gap = metric.get("gap")
        if gap:
            lines.append("  - NOT ANSWERED. %s. The test it weakens: %s."
                         % (_marked_trim(gap.get("reason"), bases, SHORT_TRIM),
                            _marked_trim(gap.get("weakened_test"), bases,
                                         SHORT_TRIM)))
            continue
        # Through _rows, like every other bounded list on this page: a
        # bare slice dropped the sixth frozen answer - a decisive figure
        # and its source - with nothing said (audit round 1, r1-6).
        answers, answers_note = _rows(metric.get("answered_by") or [],
                                      "answers")
        for fact_id in answers:
            lines.append("  - %s, source: %s"
                         % (_figure(pack, facts, fact_id, passages),
                            _source(facts, fact_id, passages)))
            if fact_id in stale_ids:
                lines.append("    - READING STALE: corrected without a new "
                             "source - re-gather before relying on it.")
        if answers_note is not None:
            lines.append("  - %s" % answers_note)
    if note is not None:
        lines.append("- %s" % note)
    lines.append("")
    return lines


_DISPOSITION_WORDS = {
    "captured": "gathered, and it is in the pack",
    "gap_declared": "could not be gathered; the gap is declared",
    "overruled": "set aside by the session that gathered the evidence",
}


def _resolution_words(resolution):
    resolution = resolution or {}
    disposition = resolution.get("disposition")
    words = _DISPOSITION_WORDS.get(disposition)
    if words is None:
        return "NOT ANSWERED"
    if disposition == "captured":
        named = ", ".join(_one_line(item)
                          for item in resolution.get("fact_ids") or [])
        return "%s (%s)" % (words, named or "no id named")
    if disposition == "gap_declared":
        return ("%s; it weakens %s - %s"
                % (words,
                   _safe(_trim(resolution.get("weakened_test"), SHORT_TRIM))
                   or "no named test",
                   _safe(_trim(resolution.get("reason"), SHORT_TRIM))
                   or "no reason given"))
    return "%s: %s" % (words,
                       _safe(_trim(resolution.get("reason"), SHORT_TRIM)))


def _conceded_gaps(block):
    """Which of the auditor's points were answered by conceding a gap,
    as (point id, answer) pairs in id order. The gaps section names them
    so this page can never say the record declares nothing while a
    conceded gap stands (the case file's own rule, audit round 5 r5-3)."""
    if block.get("status") != "success":
        return []
    return [(_one_line(point_id), entry)
            for point_id, entry
            in sorted((block.get("resolutions") or {}).items())
            if (entry or {}).get("disposition") == "gap_declared"]


def _auditor_lines(capture):
    block = capture.get("evidence_challenge") or {}
    lines = ["## What the outside auditor asked for, and what happened", ""]
    if block.get("status") != "success":
        lines.append("**NOTHING HERE WAS CHECKED BY A SECOND MODEL.** The "
                     "outside audit of this evidence failed: %s - %s. Every "
                     "figure on this page is one session's work."
                     % (_one_line(block.get("failure_status"))
                        or "no status recorded",
                        _safe(_trim(block.get("failure_reason"), SHORT_TRIM))
                        or "no reason recorded"))
        lines.append("")
        return lines
    findings = block.get("findings") or []
    resolutions = block.get("resolutions") or {}
    lines.append("A model outside this council's own family (%s) read this "
                 "evidence before any seat was paid."
                 % (_safe(block.get("model")) or "not recorded"))
    if not findings:
        lines.append("- It found nothing to raise against this evidence.")
    shown, note = _rows(findings, "points")
    for finding in shown:
        lines.append("- **%s** (%s, %s): %s"
                     % (_safe(finding.get("id")),
                        _one_line(finding.get("kind")),
                        _one_line(finding.get("severity")),
                        _safe(_trim(finding.get("detail")))))
        lines.append("  - the record's answer: %s"
                     % _resolution_words(resolutions.get(finding.get("id"))))
    if note is not None:
        lines.append("- %s" % note)
    overall = _safe(_trim(block.get("overall")))
    if overall:
        lines.append("- Its overall reading: %s" % overall)
    lines.append("")
    return lines


def _unanswered_metrics(capture):
    """The decisive metrics that carry a gap instead of an answer, named
    by business and metric. A capture declares gaps in THREE places, not
    two, and this is the third: the metric rows are capped at five like
    every list here, so an unanswered metric past the cap was a declared
    gap the page never mentioned (audit round 6, r6-1)."""
    frames = capture.get("business_frame") or {}
    named = []
    for ticker in sorted(frames):
        # Architect ruling closing P-U3f-4: this gap list shows the metric
        # NAME, a scanned field, so it is marked here too. The bases are the
        # SAME frame index the per-frame summary count is built from (the
        # canonical _frame_bases), so count and shown marks agree (AC19).
        bases = _frame_bases(capture, ticker)
        for metric in (frames[ticker] or {}).get("decisive_metrics") or []:
            if metric.get("gap"):
                named.append("%s / %s" % (_safe(ticker),
                                          _marked(metric.get("name"), bases)))
    return named


def _gaps_lines(capture):
    lines = ["## What this record admits it does not carry", ""]
    gaps = capture.get("gaps") or []
    block = capture.get("evidence_challenge") or {}
    conceded = _conceded_gaps(block)
    unanswered = _unanswered_metrics(capture)
    if not gaps and not conceded and not unanswered:
        lines.append("Nothing is declared missing.")
        lines.append("")
        return lines
    # NAMING COMES FIRST, on one line, and is never trimmed or cut.
    #
    # This section is the one place on the page whose whole purpose is to
    # say what the record does NOT carry, so nothing missing may go
    # unnamed here (audit round 4, r4-1) - a flagged omission is honest
    # everywhere else on the page, but an unnamed missing gap is the one
    # thing a reader cannot even ask about. Two later rounds showed that
    # the naming has to be a line of its OWN to hold: r5-1, the names
    # were inside a trimmed note and twenty fact classes are longer than
    # the trim, so the names it existed to carry were themselves cut;
    # r5-2, the names sat after the rows they summarise and the page's
    # bound cuts from the end, so on a full page the names went first.
    # A name list is not prose and a line has no width to overrun - only
    # the page has a length - so this line is as long as it must be, it
    # leads the section, and no section is ever cut below its first row.
    named = []
    if gaps:
        named.append("declared missing: %s"
                     % ", ".join(_safe(gap.get("fact_class"))
                                 for gap in gaps))
    if unanswered:
        named.append("decisive metrics with no answer: %s"
                     % ", ".join(unanswered))
    if conceded:
        named.append("conceded to the outside auditor: %s"
                     % ", ".join(_safe(point_id) for point_id, _ in conceded))
    lines.append("- Every gap on this record, named - %s." % "; ".join(named))
    shown, note = _rows(gaps, "declared gaps")
    for gap in shown:
        lines.append("- %s: %s (the test it weakens: %s)"
                     % (_safe(gap.get("fact_class")),
                        _safe(_trim(gap.get("reason"), SHORT_TRIM)),
                        _safe(_trim(gap.get("weakened_test"), SHORT_TRIM))))
    if note is not None:
        lines.append("- %s" % note)
    if conceded:
        # ONE self-contained line per conceded gap, and nothing above or
        # below them that depends on their surviving. Two audit rounds
        # are written into that sentence. r2-3: this block used to point
        # at the auditor section for a gap's words, and the page's own
        # bound then cut that section afterwards, so the page named a
        # gap it never explained. r3-1: the block then led with a line
        # naming every id, and the bound cut the rows beneath it and
        # kept the naming line, which was the same defect one level
        # down. A cross-reference between two parts of one page is a
        # claim that can go stale inside a single render.
        shown_conceded, conceded_note = _rows(conceded, "conceded gaps")
        for point_id, entry in shown_conceded:
            lines.append("- Conceded to the outside auditor - %s: %s (the "
                         "test it weakens: %s)"
                         % (_safe(point_id),
                            _safe(_trim(entry.get("reason"), SHORT_TRIM))
                            or "no reason given",
                            _safe(_trim(entry.get("weakened_test"), SHORT_TRIM))
                            or "no named test"))
        if conceded_note is not None:
            lines.append("- %s" % conceded_note)
    lines.append("")
    return lines


def _calendar_rows(capture):
    """Every dated event in the pack, soonest first. The event's own date
    is the fact's value where the value is a date; where it is words, the
    fact's as-of date orders it."""
    rows = []
    for fact in capture.get("tier1") or []:
        fact_id = str(fact.get("id") or "")
        if not fact_id.startswith(CALENDAR_PREFIX):
            continue
        text = _one_line(fact.get("value"))
        leading_date = (len(text) >= 10 and text[4] == "-" and text[7] == "-"
                        and text[:4].isdigit() and text[5:7].isdigit()
                        and text[8:10].isdigit())
        when = text if leading_date else _one_line(fact.get("as_of"))
        detail = "" if leading_date else text
        rows.append((when, fact_id, detail))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def tape_notice_case(capture):
    """What a pack with no price series carries about the tape: "range"
    when one entity - the subject, or one member's '__' suffix for a basket
    or a theme - carries its price and both ends of its 52-week range,
    "price" for a price without that, "none" for no price at all. The one
    test behind the no-series line on the brief and on the report page
    (architect ruling, Step 0 of U4(c) audit round 4: the range is one
    entity's, never a range on a member whose price the pack lacks)."""
    ids = set(str(fact.get("id") or "") for fact in capture.get("tier1") or [])
    priced = [fact_id[len(PRICE_ID):] for fact_id in ids
              if fact_id == PRICE_ID or fact_id.startswith(PRICE_ID + "__")]
    if not priced:
        return "none"
    if any(RANGE_LOW_ID + suffix in ids and RANGE_HIGH_ID + suffix in ids
           for suffix in priced):
        return "range"
    return "price"


def tape_placeholder(capture):
    """The line a pack with no price series prints where its chart and
    tape would be, stating what the pack carries."""
    return {"range": TAPE_PLACEHOLDER_RANGE, "price": TAPE_PLACEHOLDER_PRICE,
            "none": TAPE_PLACEHOLDER_NONE}[tape_notice_case(capture)]


def _price_and_calendar_lines(pack, facts, capture):
    lines = ["## The price, and what is dated ahead", ""]
    # A source-less correction to the price, a range endpoint or a calendar
    # fact must be flagged here too, or this section shows the new value as
    # ordinary evidence (audit round 2, r2-4).
    stale_ids = gate.stale_reading_ids(capture)
    if PRICE_ID in facts:
        low, high = facts.get(RANGE_LOW_ID), facts.get(RANGE_HIGH_ID)
        where = ""
        if low is not None and high is not None:
            where = (", against a 52-week range of %s to %s"
                     % (_safe(low.get("value")),
                        _safe(high.get("value"))))
        lines.append("- Price: %s%s." % (_figure(pack, facts, PRICE_ID),
                                         where))
        priced_stale = [fact_id for fact_id
                        in (PRICE_ID, RANGE_LOW_ID, RANGE_HIGH_ID)
                        if fact_id in stale_ids]
        if priced_stale:
            lines.append("  - READING STALE: %s corrected without a new "
                         "source - re-gather before relying on it."
                         % ", ".join("`%s`" % f for f in priced_stale))
    else:
        lines.append("- The pack carries no last price.")
    carried = sum(1 for fact_id in tape.ROW_IDS if fact_id in facts)
    if "price_series" not in capture:
        lines.append("- %s" % tape_placeholder(capture))
    elif carried:
        lines.append("- %s" % (TAPE_POINTER % carried))
    else:
        lines.append("- %s" % TAPE_ALL_GAPS)
    rows, note = _rows(_calendar_rows(capture), "dated events")
    if not rows:
        lines.append("- The pack carries no dated events for this subject.")
    for when, fact_id, detail in rows:
        lines.append("- %s: %s`%s`"
                     % (_safe(when), (_safe(_trim(detail, SHORT_TRIM)) + " ")
                        if detail else "", fact_id))
        if fact_id in stale_ids:
            lines.append("  - READING STALE: corrected without a new source.")
    if note is not None:
        lines.append("- %s" % note)
    lines.append("")
    return lines


# The capture stage's sidecar is read TWICE in one sitting - here, for
# the page a person approves, and again by `host init`, which is run
# afterwards. Two readings of one file is how the archived page came to
# say "-1 tokens" where the published verdict said "not recorded" (audit
# round 2, r2-1), so both readers go through these two functions and
# there is no second rule anywhere. They live in this module, and the
# host imports them, because `council/evidence` is the layer beneath
# `council/engine` and never the other way round; a module of their own
# would be tidier still, and is outside this unit's file list.


def challenge_tokens(usage):
    """What the outside auditor's call cost, or None where the sidecar
    does not say. The field is nullable by design - a failed evidence
    challenge honestly has no count - so anything that cannot BE a count
    reads as not recorded rather than stopping the sitting."""
    value = (usage or {}).get("evidence_challenge_tokens")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def capture_model(usage):
    """Which model gathered the evidence, or None where the sidecar does
    not say it in words. A name of nothing but spaces is not a name, and
    the collapsing happens HERE rather than where the page prints it:
    doing it at the page alone left the record keeping '   ' while the
    page said "not recorded", which is the split r2-1 closed one value
    over (closing pass, r7-5)."""
    value = (usage or {}).get("model")
    if not isinstance(value, str):
        return None
    return _one_line(value) or None


def _cost_lines(usage):
    """What the capture stage itself cost (owner ruling AC3). The council
    has always measured its seats; the stage that gathers the evidence
    was the one nobody charged for."""
    lines = ["## What the evidence stage cost", ""]
    if usage is None:
        lines.append("**No cost sidecar stands beside this brief.** The "
                     "capture stage's own minutes and tokens were not "
                     "recorded, and the host will refuse to open a run "
                     "without them.")
        lines.append("")
        return lines
    challenge = challenge_tokens(usage)
    # Owner ruling AC15 (P5(b)): an estimate never reads as a counted
    # figure - so the marker rides beside the figures HERE too, not only in
    # the final report. This one-page brief, and the full document it heads
    # (render_full), is what a person approves in reviewed mode; the WULF
    # sitting's ~700,000-token estimate reached the report labelled but the
    # approved document unlabelled - one figure with two readings (audit
    # UPGRADE2-U3d-c r1).
    # r9: the flag is REQUIRED (AC15 P5(b)) and the host refuses a sidecar
    # whose 'estimated' is not a boolean (host._read_capture_usage). This page
    # renders from the RAW sidecar BEFORE the host runs, and in reviewed mode
    # it is the document a person approves; where the flag does not say true
    # or false, the figure carries that uncertainty in words and is never
    # shown as a bare counted figure. The host refuses the run for the bad
    # flag a moment later, exactly as it does a missing sidecar.
    flag = usage.get("estimated")
    if flag is True:
        estimated = " (estimated)"
    elif flag is False:
        estimated = ""
    else:
        estimated = " (estimate status not recorded)"
    lines.append("- The capture: %s minutes, %s tokens%s, on %s."
                 % (_one_line(usage.get("minutes")) or "not recorded",
                    _one_line(usage.get("tokens")) or "not recorded",
                    estimated,
                    _safe(capture_model(usage) or "a model not recorded")))
    lines.append("- The outside auditor's call: %s."
                 % ("%s tokens" % _one_line(challenge)
                    if challenge is not None else "not recorded"))
    lines.append("")
    return lines


def _closing_lines():
    return ["## What happens now", "",
            "In reviewed mode nothing is paid until a person writes "
            "`approval.json` beside this page, naming what was checked or "
            "changed. In auto-mode the council sits without that step, and "
            "the report's front page says so.", ""]


# Every section above is bounded on its own, and until audit round 1
# nothing bounded their SUM: a basket the capture schema fully permits -
# five decisive metrics per business, five frozen answers behind each -
# measured 104 lines against a 72-line page, so "one page" was an
# assertion in a test rather than a rule in the code (r1-5). The page is
# now cut to its bound at the end, and every cut says so in the section
# it came from. The sections NOT named here are never cut: the question
# the page answers, what the evidence stage cost and what happens next
# are the page's spine, and a bound that ate them would defeat the page
# rather than fit it.
CUTTABLE = ("business", "decisive", "auditor", "gaps", "calendar")
CUT_NOTE = ("- The one-page bound cut %d further line(s) from this "
            "section; %s.")
# And what the bound took from the page as a whole, on the page's own
# last line (register item P-U3-6). The per-section notes say where each
# cut fell; a reader looking at one page has no way to add them up, and
# how much of the record is NOT in front of him is the first thing he
# should be able to see.
CUT_TOTAL_NOTE = "The one-page bound left %d line(s) of this brief out; %s."
# What marks a line as the detail of the row above it, rather than a row
# of its own. The page writes every such line as an indented bullet.
INDENT = "  "
# The lines that say what SHAPE of subject this is - the business's name,
# its trace summary, its archetype, its capital and its cycle - which the
# bound cuts only after every descriptive line (register item P-FIb-5).
SHAPE_PREFIXES = ("**", "- Figures traced to the record:", "- Archetype: ",
                  "- Capital beside its requirement: ", "- Cycle: ")


def _rows_to_cut(body, lines_wanted):
    """Which rows of the business section the bound removes, as a set of
    row indexes, and the rows themselves. A row is a line and the
    indented detail beneath it, cut whole. The first row always stands.
    The rest go longest first, and a subject-shape row only once no
    descriptive row is left (architect ruling on P-FIb-5); ties go to
    the later row."""
    rows = []
    for line in body:
        if rows and line.startswith(INDENT):
            rows[-1].append(line)
        else:
            rows.append([line])
    order = sorted(range(1, len(rows)), key=lambda index: (
        rows[index][0].startswith(SHAPE_PREFIXES),
        -max(len(line) for line in rows[index]), -index))
    dropped, removed = set(), 0
    for index in order:
        if removed >= lines_wanted:
            break
        dropped.add(index)
        removed += len(rows[index])
    return dropped, rows


def _fit_to_one_page(blocks):
    """The assembled page, cut to PAGE_LINES. Each block is
    (name, lines), where lines[0] is the section's heading, lines[1] the
    blank beneath it and lines[-1] the blank that separates it from the
    next; only the body between those is ever cut, so no heading is left
    standing over nothing and no two sections run together.

    The LONGEST section gives up each line, one at a time, so a page
    that overruns loses its bulk and not one whole ruled section: every
    section spec U3.1 names still stands, shorter. Ties go to the first
    name in CUTTABLE, so one pack always renders one page. Within the
    business section the longest rows go first, never a subject-shape
    row while a descriptive one remains (_rows_to_cut); every other
    section is ordered by importance - the auditor's blocking points
    first - and gives up its tail, as before.

    A page that was cut ends by saying how many lines it left out, and
    the bound pays for that line itself."""
    keep = {name: len(lines[2:-1])
            for name, lines in blocks if name in CUTTABLE}
    over = sum(len(lines) for _, lines in blocks) - PAGE_LINES
    if over > 0:
        over += 1              # the closing line this page is about to gain
    cut = dict.fromkeys(keep, 0)
    while over > 0:
        # No section is ever cut below its FIRST row. A section reduced
        # to nothing but a cut note tells a reader less than nothing,
        # and the gaps section's first row is the line naming every gap
        # this record admits to (audit round 5, r5-2). The floor cannot
        # stall the bound: the page's fixed parts and five sections at
        # one row each come to well under PAGE_LINES.
        givers = [name for name in keep if keep[name] > 1]
        if not givers:
            break
        name = max(givers, key=lambda key: (keep[key],
                                            -CUTTABLE.index(key)))
        if cut[name] == 0:
            over += 1          # the note this section is about to gain
        keep[name] -= 1
        cut[name] += 1
        over -= 1
    out = []
    omitted = 0
    for name, lines in blocks:
        if name not in CUTTABLE or not cut[name]:
            out.extend(lines)
            continue
        body = lines[2:-1]
        # Never keep half a row. A row on this page is one line, or a
        # line and its detail indented beneath it, and a cut landing
        # between the two kept a point named with its answer gone (audit
        # round 3, r3-1). Whole rows are cut, so what goes, goes whole.
        # The page only gets shorter, never longer, so the bound holds.
        if name == "business":
            dropped, rows = _rows_to_cut(body, cut[name])
            kept = [line for index, row in enumerate(rows)
                    if index not in dropped for line in row]
        else:
            count = keep[name]
            while 0 < count < len(body) and body[count].startswith(INDENT):
                count -= 1
            kept = body[:count]
        omitted += len(body) - len(kept)
        out.extend(lines[:2] + kept
                   + [CUT_NOTE % (len(body) - len(kept), IN_THE_PACK)]
                   + lines[-1:])
    if omitted:
        out.append(CUT_TOTAL_NOTE % (omitted, IN_THE_PACK))
    return out


def render(pack, pack_sha256, usage=None):
    """The whole brief, as one string. `usage` is the capture stage's own
    cost sidecar, or None where none stands."""
    if "capture" not in pack:
        raise ValueError("not a frozen pack: the capture wrapper is "
                         "missing - render from the freeze's pack.json, "
                         "never from a raw capture")
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    passages = _passages_by_id(capture)
    blocks = [
        ("head", _head_lines(pack, pack_sha256)),
        ("question", _question_lines(capture)),
        ("business", _business_lines(pack, facts, passages, capture)),
        ("decisive", _decisive_lines(pack, facts, passages, capture)),
        ("auditor", _auditor_lines(capture)),
        ("gaps", _gaps_lines(capture)),
        ("calendar", _price_and_calendar_lines(pack, facts, capture)),
        ("cost", _cost_lines(usage)),
        ("closing", _closing_lines()),
    ]
    return "\n".join(_fit_to_one_page(blocks)).rstrip("\n") + "\n"


# ---------------------------------------------------------------------------
# Owner ruling AC15 (P6): the full evidence document. In reviewed mode the
# document a person approves is the WHOLE evidence rendered for a reader -
# every fact, passage, gap, auditor finding and resolution, and the
# checklist, frame first - not the one-page cut, which becomes its summary
# at the top. It prints the plain-English fact label where one exists and
# the machine key where none does (owner ruling AC15, P5). Nothing here is
# trimmed: completeness is the whole point.
# ---------------------------------------------------------------------------

def _fact_heading(fact):
    """The owner-facing name of a fact: its label where one exists, the
    machine key where none does (owner ruling AC15, P5)."""
    label = str(fact.get("label") or "").strip()
    return _safe(label) if label else "`%s`" % _one_line(fact.get("id"))


def _fact_ref(facts, fact_id):
    """A reference to a fact for the reader: its plain-English label with
    the machine key beside it where a label exists, the key alone where
    none does (owner ruling AC15, P5 - the full document uses the label
    wherever one exists, not only in the fact's own heading; audit round 1
    of sub-charge b, b-r1-8). The key always survives, so a reference stays
    unambiguous - labels are optional and not checked for uniqueness."""
    fact = (facts or {}).get(fact_id) or {}
    label = str(fact.get("label") or "").strip()
    key = "`%s`" % _one_line(fact_id)
    return "%s (%s)" % (_safe(label), key) if label else key


def _full_frame_lines(pack, capture):
    facts = _facts_by_id(capture)
    passages = _passages_by_id(capture)
    frames = capture.get("business_frame") or {}
    if not frames:
        return []
    lines = ["## The business - read this before the numbers", ""]
    for ticker in sorted(frames):
        frame = frames[ticker]
        bases = _frame_bases(capture, ticker)
        lines.append("### %s" % _safe(ticker))
        lines.append("")
        # Owner ruling AC19: the one summary line per frame, and every
        # number below marked where the reader who approves this sees it.
        lines.append(trace.summary_sentence(
            trace.frame_counts(capture, ticker, frame, _marks_config())))
        lines.append("")
        archetype = frame.get("archetype")
        if archetype:
            measure = _rating_measure(capture)
            rated = ((" It is rated on %s."
                      % _MEASURE_WORDS.get(measure, _safe(measure)))
                     if measure else "")
            kind = (fi_kind_words(frame, _safe) if archetype == FI_ARCHETYPE
                    else _ARCHETYPE_WORDS.get(archetype, _safe(archetype)))
            lines.append("**Archetype.** %s.%s %s"
                         % (kind, rated,
                            _marked(frame.get("archetype_because"), bases)))
            denoms = _rating_subject_denominators(capture)
            if denoms:
                lines.append("")
                # P-U3e-3 (finding r6-1): the subject denominators are
                # validated at sufficiency for a single_stock alone, so a
                # basket/theme value the schema never checked reaches here
                # unvouched. Name it in the file's own voice (its label and
                # back-ticked key) ONLY when it is one of the pack's own
                # tier-1 fact ids; send anything else through _safe, as data.
                lines.append("**The rating divides by** %s."
                             % ", ".join(_fact_ref(facts, fid)
                                         if fid in facts else _safe(fid)
                                         for fid in denoms))
            lines.append("")
        lines.append("**What it does.** %s"
                     % _marked(frame.get("what_it_does"), bases))
        lines.append("")
        lines.append("**How it earns.**")
        for row in frame.get("how_it_earns") or []:
            # Owner rulings AC28 and AC30: the kind of earnings a line is
            # stands beside its share of the period, where the line says.
            nature = row.get("nature")
            nature_words = (("%s, " % (FI_NATURE_WORDS.get(nature)
                                       or _safe(nature)))
                            if nature else "")
            lines.append("- %s - %s%s of the latest reported period (%s)"
                         % (_marked(row.get("line"), bases), nature_words,
                            _one_line(row.get("share_of_period")),
                            ", ".join(_fact_ref(facts, fid)
                                      for fid in row.get("facts") or [])))
        if archetype == FI_ARCHETYPE:
            lines.extend(_full_fi_lines(pack, capture, ticker, frame,
                                        facts, bases))
        changing = frame.get("what_is_changing") or {}
        lines.append("")
        lines.append("**What is changing (%s).** %s"
                     % (_one_line(changing.get("kind")),
                        _marked(changing.get("statement"), bases)))
        reading = frame.get("headline_decline_read")
        if reading:
            lines.append("")
            lines.append("**A fallen headline figure, read as:** %s (%s)"
                         % (_safe(reading.get("reading")),
                            ", ".join(_fact_ref(facts, fid)
                                      for fid in reading.get("facts") or [])
                            or "no facts named"))
        lines.append("")
        lines.append("**The numbers that decide it.**")
        for row in frame.get("decisive_metrics") or []:
            gap = row.get("gap")
            if gap:
                answer = ("declared gap: %s (weakens %s)"
                          % (_marked(gap.get("reason"), bases),
                             _marked(gap.get("weakened_test"), bases)))
            else:
                answer = "answered by " + ", ".join(
                    _fact_ref(facts, fid)
                    for fid in row.get("answered_by") or [])
            lines.append("- %s: %s - %s"
                         % (_marked(row.get("name"), bases),
                            _marked(row.get("why_it_decides"), bases), answer))
        lines.extend(_full_peer_lines(frame, facts, bases))
        lines.append("")
        lines.append("**Management.** %s"
                     % _management_words(pack, facts, frame))
        lines.append("")
        lines.append("**Competitive standing:** passage `%s`."
                     % _one_line(frame.get("competitive_position")))
        lines.append("")
        # cycle_dependence and its reason are required of a single name by
        # the gate; the full document a person approves prints them, for an
        # identified cycle and for a name that depends on none (finding
        # r1-8). The dated series, where identified, follow in their own
        # section below.
        cycle_dep = frame.get("cycle_dependence")
        if cycle_dep:
            because = frame.get("cycle_dependence_because")
            lines.append("**Cycle dependence:** %s.%s"
                         % (_one_line(cycle_dep),
                            (" %s" % _marked(because, bases)) if because
                            else ""))
            lines.append("")
    return lines


def _full_fi_lines(pack, capture, ticker, frame, facts, bases):
    """What the full document shows of a financial institution (owner
    rulings AC28 and AC30): the kind of firm, capital beside its
    requirement, the regulator's own bad year, the risk-cost line and, for
    a holding, its net asset value part by part. Evidence only: nothing
    here reads the figures."""
    kind = fi_kind_words(frame, _safe)
    lines = ["", "**The kind of firm.** %s%s." % (kind[:1].upper(), kind[1:])]
    if frame.get("fi_secondary_subtype"):
        lines.append("Its other engine's share is carried by %s."
                     % (_fi_values(pack, facts,
                                   frame.get("fi_secondary_share_facts"))
                        or "no fact named"))
    capital = frame.get("fi_capital") or {}
    lines.append("")
    if capital.get("gap"):
        lines.append("**Capital beside its requirement.** %s."
                     % _fi_capital_words(pack, facts, capital, bases))
    else:
        lines.append("**Capital beside its requirement.**")
        for ratio, requirement in fi_capital_pairs(capital):
            lines.append("- %s" % _fi_pair_words(pack, facts, ratio,
                                                  requirement))
        for label, key in (("The regime", "regime"),
                           ("The binding constraint", "binding_constraint")):
            if capital.get(key):
                lines.append("- %s: %s" % (label, _marked(capital[key],
                                                           bases)))
        if capital.get("target_fact"):
            lines.append("- Management's own target: %s"
                         % _fi_value(pack, facts, capital["target_fact"]))
    stress, stress_gaps = fi_stress_evidence(capture, ticker)
    if stress or stress_gaps:
        # Owner ruling AC30(5): the supervisor's own stress figures, as
        # dated evidence - never a reading of them.
        lines.append("")
        lines.append("**%s.** Evidence only: the pack carries these and "
                     "nothing here reads them." % FI_STRESS_HEADING)
        for fid in stress:
            lines.append("- %s" % _fi_value(pack, facts, fid))
        for gap in stress_gaps:
            lines.append("- declared gap (%s): %s"
                         % (_safe(gap.get("fact_class")),
                            _safe(gap.get("reason"))))
    risk = frame.get("fi_risk_cost") or {}
    if risk:
        kind = risk.get("kind")
        lines.append("")
        lines.append("**The risk-cost line: %s.** %s. Why this line: %s"
                     % (FI_RISK_KIND_WORDS.get(kind) or _safe(kind),
                        _fi_values(pack, facts, risk.get("facts"))
                        or "no fact, by design",
                        _marked(risk.get("because"), bases)))
    bridge = frame.get("nav_bridge")
    if isinstance(bridge, dict):
        lines.append("")
        lines.append("**The net asset value, part by part.**")
        lines.append("")
        lines.append("| Component | How it is valued | Value |")
        lines.append("| --- | --- | --- |")
        for part in bridge.get("components") or []:
            lines.append("| %s | %s | %s |"
                         % (_marked(part.get("name"), bases),
                            FI_METHOD_WORDS.get(part.get("method"))
                            or _safe(part.get("method")),
                            _fi_value(pack, facts, part.get("value_fact"))))
        lines.append("")
        for label, key in (
                ("Holding-company net debt", "holdco_net_debt_fact"),
                ("The net asset value", "nav_total_fact"),
                ("The company's own published net asset value",
                 "published_nav_fact"),
                ("The discount", "discount_fact")):
            if bridge.get(key):
                lines.append("- %s: %s"
                             % (label, _fi_value(pack, facts, bridge[key])))
        lines.append("")
        lines.append(FI_NOT_RATED_SENTENCE)
    return lines


def _full_cycle_lines(capture):
    """The cycle a single name depends on (owner ruling AC15, P4): the
    dated series carried as EVIDENCE, or the declared gap. Nothing here is
    computed from them - the seats read them as evidence, never a reading."""
    cycle = capture.get("cycle")
    if not cycle:
        return []
    lines = ["## The cycle this name depends on", "",
             "**%s.** %s" % (_safe(cycle.get("name")),
                             _safe(cycle.get("why_it_matters"))), ""]
    gap = cycle.get("gap")
    if gap:
        lines.append("The dated series are a declared gap: %s"
                     % _safe(gap.get("reason")))
        lines.append("")
        return lines
    for series in cycle.get("series") or []:
        points = series.get("points") or []
        span = ("%s to %s" % (points[0]["date"], points[-1]["date"])
                if points else "no points")
        # Render-only (FI-ARCHETYPE (b)): the date the series was read
        # beside the date of its LAST point, so a reader sees how old the
        # latest reading is.
        lines.append("- **`%s`** (%s, read %s; latest point %s): %d dated "
                     "points, %s. Source: %s. Re-fetch: %s"
                     % (_one_line(series.get("id")),
                        _safe(series.get("unit")),
                        _safe(series.get("as_of")),
                        _safe(points[-1].get("date")) if points
                        else "none", len(points), span,
                        _safe(series.get("source")),
                        _safe(series.get("refetch_url_or_source_line"))))
        # The full document is what a person approves, so it must show
        # what the seats see: every dated point, not only the count and
        # the span (owner ruling AC15 P4, U3d P6; finding r1-7).
        lines.append("")
        lines.append("| Date | Value |")
        lines.append("| --- | --- |")
        for point in points:
            lines.append("| %s | %s |" % (_safe(point.get("date")),
                                          _safe(point.get("value"))))
        lines.append("")
    lines.append("")
    return lines


def _full_peer_lines(frame, facts, bases):
    """The peer set. Owner ruling AC15 (P1): where a peer carries a
    recorded comparability statement, it is shown; where it does not
    (a pack written before that rule), only the name and metrics are.
    Metric fact ids are shown by their label where one exists (P5). Owner
    ruling AC19: a number in either comparability statement is marked where
    it is shown when it traces to no recorded fact."""
    peers = frame.get("peers") or []
    if not peers:
        return ["", "**Peers.** None; the record declares why in its gaps."]
    lines = ["", "**Peers.**"]
    for peer in peers:
        lines.append("- %s (%s): %s"
                     % (_safe(peer.get("name")),
                        _safe(peer.get("ticker")),
                        ", ".join(_fact_ref(facts, m)
                                  for m in peer.get("metrics") or [])))
        if peer.get("comparable_because"):
            lines.append("  - comparable because: %s"
                         % _marked(peer.get("comparable_because"), bases))
        if peer.get("not_comparable_on"):
            lines.append("  - not comparable on: %s"
                         % _marked(peer.get("not_comparable_on"), bases))
    return lines


def _full_fact_lines(pack, capture):
    lines = ["## Every fact, in full", ""]
    notes = pack.get("generated_notes") or {}
    for fact in capture.get("tier1") or []:
        fact_id = fact.get("id")
        lines.append("### %s" % _fact_heading(fact))
        unit = _safe(fact.get("unit"))
        lines.append("- Value: %s%s (as of %s)%s"
                     % (_safe(fact.get("value")),
                        (" " + unit) if unit else "",
                        _one_line(fact.get("as_of")),
                        _freshness_mark(pack, fact_id)))
        # A bound is not a measurement: a ceiling can only be too high, a
        # floor too low, and a ceiling names the published line it was
        # struck from. Printing the value alone turns a bound into an
        # apparent measurement (audit round 1 of sub-charge b, b-r1-4).
        bound = fact.get("bound")
        if bound:
            kind = _one_line(bound.get("kind"))
            meaning = {"ceiling": "a ceiling - it can only be too high",
                       "floor": "a floor - it can only be too low"}.get(
                           kind, kind)
            lines.append("- Bound: %s" % meaning)
            if bound.get("published_line"):
                lines.append("  - struck from the published line: %s"
                             % _safe(bound.get("published_line")))
        lines.append("- Source: %s" % _safe(fact.get("source")))
        note = notes.get(fact_id)
        if note:
            lines.append("- Arithmetic: %s" % _one_line(note))
        period_basis = fact.get("period_basis")
        if period_basis:
            lines.append("- Period basis: %s" % _safe(period_basis))
        lines.append("")
    return lines


def _full_passage_lines(capture):
    lines = ["## Every passage, in full", ""]
    passages = capture.get("tier2") or []
    if not passages:
        lines.append("None in this pack.")
        lines.append("")
        return lines
    for passage in passages:
        lines.append("### `%s` (as of %s)"
                     % (_one_line(passage.get("id")),
                        _one_line(passage.get("as_of"))))
        lines.append("- Source: %s" % _safe(passage.get("source")))
        figures = passage.get("figures") or []
        if figures:
            lines.append("- Figures stated: %s"
                         % ", ".join(_safe(f) for f in figures))
        lines.append("")
        lines.append(_safe(passage.get("text")))
        lines.append("")
    return lines


def _full_gap_lines(capture):
    lines = ["## Every declared gap", ""]
    gaps = capture.get("gaps") or []
    if not gaps:
        lines.append("None declared.")
        lines.append("")
        return lines
    for gap in gaps:
        lines.append("- %s: %s (weakens %s)"
                     % (_safe(gap.get("fact_class")),
                        _safe(gap.get("reason")),
                        _safe(gap.get("weakened_test"))))
    lines.append("")
    return lines


def _audit_pass_lines(block, facts, current):
    """One audit pass, rendered whole (audit round 1 of sub-charge b,
    b-r1-5/b-r1-6): its scope (a full audit or a delta re-audit of a
    correction), its overall reading, and every finding with all the
    fields it carries and the record's full answer. Nothing summarized to
    a count - a delta hiding a prior pass's material finding behind a
    count is exactly what a reviewer must not miss."""
    scope = _one_line(block.get("scope")) or "full"
    pass_no = _one_line(block.get("current_pass") if current
                        else block.get("pass")) or "1"
    lines = ["**A %s audit (pass %s).**" % (scope, pass_no), ""]
    if block.get("status") != "success":
        lines.append("This pass did not complete: %s (%s). No outside model "
                     "checked this evidence."
                     % (_one_line(block.get("failure_status")),
                        _safe(block.get("failure_reason"))))
        lines.append("")
        return lines
    if block.get("overall"):
        lines.append("**Its overall reading:** %s"
                     % _safe(block.get("overall")))
        lines.append("")
    resolutions = block.get("resolutions") or {}
    findings = block.get("findings") or []
    if not findings:
        lines.append("It raised nothing.")
        lines.append("")
    for finding in findings:
        finding_id = finding.get("id")
        lines.append("#### %s - %s (%s)"
                     % (_safe(finding_id), _one_line(finding.get("kind")),
                        _one_line(finding.get("severity"))))
        lines.append("- It said: %s" % _safe(finding.get("detail")))
        if finding.get("fact_ids"):
            lines.append("- The figures it is about: %s"
                         % ", ".join(_fact_ref(facts, f)
                                     for f in finding["fact_ids"]))
        if finding.get("where_it_likely_lives"):
            lines.append("- Where it would be found: %s"
                         % _safe(finding.get("where_it_likely_lives")))
        # source_url and figure_at_source are independently nullable in the
        # capture schema, so each is rendered on its own: the full document
        # renders every auditor finding in full (owner ruling AC15, P6), and
        # an observed figure the auditor read without a url must not be
        # dropped with the missing url (round 2, r2-2).
        source_url = finding.get("source_url")
        figure = finding.get("figure_at_source")
        if source_url and figure:
            lines.append("- Read at %s, which prints %s"
                         % (_safe(source_url), _safe(figure)))
        elif source_url:
            lines.append("- Read at %s" % _safe(source_url))
        elif figure:
            lines.append("- The figure it read at the source: %s"
                         % _safe(figure))
        resolution = resolutions.get(finding_id) or {}
        disposition = _one_line(resolution.get("disposition")) or "unanswered"
        answer = "- The record answered: %s" % disposition
        if resolution.get("fact_ids"):
            answer += " (%s)" % ", ".join(_fact_ref(facts, f)
                                          for f in resolution["fact_ids"])
        if resolution.get("reason"):
            answer += " - %s" % _safe(resolution.get("reason"))
        lines.append(answer)
        if resolution.get("weakened_test"):
            lines.append("  - it weakens: %s"
                         % _safe(resolution.get("weakened_test")))
        lines.append("")
    return lines


def _full_auditor_lines(capture):
    lines = ["## What the outside auditor said, and what was done about it",
             ""]
    block = capture.get("evidence_challenge")
    if not block:
        lines.append("No outside audit is on this record.")
        lines.append("")
        return lines
    facts = _facts_by_id(capture)
    lines.extend(_audit_pass_lines(block, facts, current=True))
    for prior in block.get("prior_passes") or []:
        lines.append("### An earlier audit pass, kept whole")
        lines.append("")
        lines.extend(_audit_pass_lines(prior, facts, current=False))
    return lines


FREE_CASH_ROW = "free_cash_flow"


def checklist_description(capture, req, escape):
    """A checklist row's description as the page prints it. For a bank,
    insurer, reinsurer or holding the free-cash test is named for what
    answers it - capital the firm can pay out and still stay above its
    regulator's minimum (owner ruling AC30(1)) - with the capture's own
    words after it; every other row, and every other subject, prints the
    capture's words alone, through the renderer's own `escape`."""
    words = escape(req.get("description"))
    frame = fi_subject_frame(capture)
    if (req.get("id") == FREE_CASH_ROW and frame is not None
            and frame.get("fi_subtype") in fi_lifted_subtypes()):
        return "%s%s%s" % (escape("%s (the capture's words: "
                                  % FI_FREE_CASH_WORDS), words, escape(")"))
    return words


def _full_checklist_lines(capture):
    lines = ["## The sufficiency checklist", ""]
    facts = _facts_by_id(capture)
    for req in (capture.get("sufficiency") or {}).get("requirements") or []:
        if req.get("status") == "answered":
            lines.append("- [answered] `%s` (%s): %s - by %s"
                         % (_one_line(req.get("id")),
                            _one_line(req.get("kind")),
                            checklist_description(capture, req, _safe),
                            ", ".join(_fact_ref(facts, f)
                                      for f in req.get("answered_by") or [])
                            or "none"))
        else:
            # The weakened test is what a declared gap COSTS; the approved
            # document must state it, not only the reason (audit round 1 of
            # sub-charge b, b-r1-7).
            lines.append("- [declared gap] `%s` (%s): %s - %s (weakens %s)"
                         % (_one_line(req.get("id")),
                            _one_line(req.get("kind")),
                            checklist_description(capture, req, _safe),
                            _safe(req.get("gap_reason") or "no reason"),
                            _safe(req.get("weakened_test") or "not stated")))
    lines.append("")
    return lines


def render_full(pack, pack_sha256, usage=None):
    """The full evidence document (owner ruling AC15, P6): the one-page
    brief as its summary at the top, then the WHOLE evidence rendered for
    a reader - the business frame first, then every fact (by its plain
    label where one exists), every passage, every gap, every auditor
    finding and resolution, and the checklist. Deterministic, no model
    call, nothing trimmed."""
    if "capture" not in pack:
        raise ValueError("not a frozen pack: the capture wrapper is "
                         "missing - render from the freeze's pack.json, "
                         "never from a raw capture")
    capture = pack["capture"]
    summary = render(pack, pack_sha256, usage).rstrip("\n")
    lines = [summary, "",
             "---", "",
             "# The full evidence - the document approved in reviewed mode",
             "",
             "Everything above is the one-page summary; everything below is "
             "the whole of the evidence the council will sit on, in full and "
             "nothing trimmed. This is the document a reviewer approves "
             "(owner ruling AC15).", ""]
    lines.extend(_full_frame_lines(pack, capture))
    lines.extend(_full_cycle_lines(capture))
    lines.extend(_full_fact_lines(pack, capture))
    lines.extend(_full_passage_lines(capture))
    lines.extend(_full_gap_lines(capture))
    lines.extend(_full_auditor_lines(capture))
    lines.extend(_full_checklist_lines(capture))
    return "\n".join(lines).rstrip("\n") + "\n"


_USAGE = ("usage: python -m council.evidence.brief <pack.json> "
          "--out <brief.md> [--usage <capture-usage.json>] [--full]")

USAGE_NAME = "capture-usage.json"


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
        full = "--full" in args
        args = [a for a in args if a != "--full"]
        out_path = _take_option(args, "--out")
        usage_path = _take_option(args, "--usage")
        if len(args) != 1 or not out_path:
            print(_USAGE)
            return 1
        pack_path = args[0]
        pack = canonical.read_json(pack_path)
        if usage_path is None:
            usage_path = os.path.join(os.path.dirname(os.path.abspath(
                out_path)), USAGE_NAME)
        usage = None
        if os.path.exists(usage_path):
            usage = canonical.read_json(usage_path)
        renderer = render_full if full else render
        text = renderer(pack, canonical.sha256_file(pack_path), usage)
        canonical.write_bytes_atomic(out_path, text.encode("utf-8"))
        print("brief: %s written to %s (%d lines)"
              % ("full document" if full else "one page", out_path,
                 len(text.splitlines())))
        if usage is None:
            print("  the capture's cost sidecar is not at %s - the page "
                  "says so, and the host refuses a run without it"
                  % usage_path)
        return 0
    except Exception as exc:
        print("brief crashed: %r" % (exc,))
        return 1


if __name__ == "__main__":
    sys.exit(main())
