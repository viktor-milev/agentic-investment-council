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

import decimal
import os
import re
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.evidence import gate, sufficiency, tape, trace  # noqa: E402
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
# The tape's own figures the one page shows beside the price (unit
# READ-B2): the 200-day average and the price against it, then the
# 52-week closing range.
AVERAGE_IDS = ("tape_sma200_level", "tape_close_vs_sma200")
CLOSING_RANGE_IDS = ("tape_low_close_252", "tape_high_close_252")

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
    return holding_display_facts(capture)


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
    """One frozen answer, as the reader reads it (unit READ-B2): its plain
    label, then its figure in the market form (owner ruling AC16(4)), then
    staleness. The exact recorded value is printed beside the formatted one
    in the fact's own entry of the full document; the figure is never
    recomputed.

    A decisive metric may be answered by a tier-2 PASSAGE that states its
    figures - a backlog written in prose is still a frozen answer - so
    the passage is rendered by the figures it declares, which are already
    checked to stand literally in its own words."""
    fact_id = holding_display_id(pack.get("capture") or {}, fact_id)
    fact = facts.get(fact_id)
    if fact is None:
        passage = (passages or {}).get(fact_id)
        if passage is None:
            return "%s is named but is not in the pack" % _safe(fact_id)
        figures = ", ".join(_safe(item)
                            for item in passage.get("figures") or [])
        return "the passage %s states %s: %s" % (
            _passage_title(fact_id), figures or "no figure",
            _safe(_trim(passage.get("text"), SHORT_TRIM,
                        passage.get("figures"))))
    shown = _shown(fact)
    return "%s: %s%s" % (_fact_name(fact), shown,
                         _freshness_mark(pack, fact_id))


# Owner ruling AC45(9): a row the gate let wait for its outcome - a period
# the pack has not yet reported - leaves what was delivered open. The
# words are NOT_REPORTED, defined once with the guidance tables below.


def _delivered(pack, facts, row):
    """What a guidance row says was delivered: the figure, or - on a row
    that leaves it open - that the period is not reported yet."""
    if row.get("delivered") is None:
        return NOT_REPORTED
    return _figure(pack, facts, row.get("delivered"))


# ------------------------------------------------ the reader's figures
# Unit READ-B2 (owner rulings AC16(4) and AC40(2c)): the document a person
# approves shows every figure in the market form the report uses, and the
# full document prints the exact recorded value beside it. The frozen
# evidence itself stays exact (the ruling closing PRECISION-REG-1): only
# the reading is formatted. The report's formatter is loaded when first
# used, never at the top: the report imports this module at its own top.

RECORD_KEY_LINE = "- Record key: "


def _format_number(value, unit):
    from council.report import render_report
    return render_report.format_number(value, unit)


def _format_date(value):
    from council.report import render_report
    return render_report.format_date(value)


def _unit_words(unit):
    """A recorded unit as words: its underscores read as spaces."""
    return _one_line(unit).replace("_", " ")


def _shown(fact):
    """A fact's value in the market form, neutralized for the document."""
    return _safe(_format_number(fact.get("value"), fact.get("unit")))


def _exact(fact):
    """A fact's value exactly as recorded, with its unit in words."""
    unit = _unit_words(fact.get("unit"))
    return _safe(fact.get("value")) + ((" " + _safe(unit)) if unit else "")


def _value_words(fact):
    """The formatted value with the exact recorded value beside it, or the
    exact value alone where formatting changes nothing a reader sees."""
    shown = _format_number(fact.get("value"), fact.get("unit"))
    raw = _one_line(fact.get("value"))
    unit = _unit_words(fact.get("unit"))
    if _one_line(shown) in (raw, ("%s %s" % (raw, unit)).strip()):
        return _exact(fact)
    return "%s — recorded %s" % (_safe(shown), _exact(fact))


def _fact_name(fact):
    """A fact's plain name: its label, or its key read as words where it
    carries none (unit READ-B2: the key itself stands only in the fact's
    own entry, in small print)."""
    label = str(fact.get("label") or "").strip()
    return _safe(label) if label else _words_of_id(fact.get("id"))


def _words_of_id(identifier):
    """A machine name read as words: a passage's tier prefix dropped, its
    underscores read as spaces, the first letter capitalised."""
    return _safe(_id_words(identifier))


def _id_words(identifier):
    """_words_of_id before the escaping, for a printer that escapes."""
    text = _one_line(identifier)
    if text.startswith("t2_"):
        text = text[len("t2_"):]
    text = " ".join(text.replace("_", " ").split())
    return text[:1].upper() + text[1:]


def _point_words(text):
    """An outside point on the one page: its first sentence, then the pack
    pointer when more follows - never a cut inside a sentence (architect
    ruling, round 2 of UPGRADE2-READ-B2; the seed's item 14). A first
    sentence longer than the page budget gives its place to the pointer
    alone (architect ruling closing r2-1, Step 0 of round 3)."""
    text = _one_line(text)
    first = _first_sentence(text)
    if len(first) > TRIM_CHARS:
        return "(%s)" % IN_THE_PACK
    if first == text:
        return text
    return "%s (%s)" % (first, IN_THE_PACK)


def _passage_title(passage_id):
    return "\"%s\"" % _words_of_id(passage_id)


def _first_sentence(text):
    """The first sentence of a stretch of prose: up to the first full stop
    that ends a lower-case word, a figure or a bracket and is followed by
    a space; the whole text where there is none."""
    text = _one_line(text)
    at = 0
    while True:
        at = text.find(". ", at)
        if at == -1:
            return text
        before = text[at - 1:at]
        if before and (before.islower() or before.isdigit() or before == ")"):
            return text[:at + 1]
        at += 2


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
    kind = subject.get("kind")
    # Unit READ-B2: the subject in words and the gathering time as a date,
    # never the schema's kind or a machine timestamp.
    lines.append("**%s%s, %s.** Evidence gathered %s."
                 % (name or "Not named",
                    (" (%s)" % ticker) if ticker else "",
                    SUBJECT_KIND_WORDS.get(kind) or _safe(kind)
                    or "its kind not stated",
                    _safe(_moment_words(capture.get("captured_at")))
                    or "at a time not recorded"))
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


_MOMENT = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::\d{2})?Z$")


def _moment_words(stamp):
    """A capture's UTC time stamp as a reader writes it: "24 Sep 2026,
    16:05 UTC". Any other text passes to the report's date rule."""
    match = _MOMENT.match(_one_line(stamp))
    if match:
        return "%s, %s:%s UTC" % (_format_date(match.group(1)),
                                  match.group(2), match.group(3))
    return _format_date(_one_line(stamp))


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
QUESTION_IN_FULL_LABEL = "The question in full:"
QUESTION_REPEAT_POINTER = "(his words, as in the line above)"

SUBJECT_KIND_WORDS = {
    "single_stock": "one stock",
    "etf": "an exchange-traded fund",
    "bitcoin": "bitcoin",
    "gold": "gold",
    "commodity": "a commodity",
    "theme": "a theme",
    "basket": "a basket",
}


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
    """The one-line row, then the question in full, once (unit READ-B2):
    where the full question repeats the one line word for word, the repeat
    is replaced by a pointer to the row above, so no text prints twice."""
    lines = ["## The question", ""]
    row = question_line_row(capture)
    line = question_line(capture)
    verbatim = _one_line(capture.get("question_verbatim"))
    if row:
        lines += [row, ""]
    if not verbatim:
        return lines + ["The pack carries no question.", ""]
    if line and verbatim == line:
        return lines
    if line and line in verbatim:
        verbatim = verbatim.replace(line, QUESTION_REPEAT_POINTER)
    return lines + ["%s %s" % (QUESTION_IN_FULL_LABEL, _safe(verbatim)), ""]


def _how_it_earns_words(pack, frame, bases):
    """Each revenue line by its short name, its revenue and its share of
    the firm, read from the one table both pages print (unit READ-B1); a
    share the frame records as a share reads as the table reads it."""
    table = earnings_rows(pack, frame)
    lines = frame.get("how_it_earns") or []
    shown, note = _rows(list(zip(lines, table["rows"])), "revenue lines")
    at = table["head"].index(EARNINGS_HEAD[2])
    parts = []
    for line, row in shown:
        revenue, share = row[at], row[at + 1]
        words = _md_cell(row[0], bases)
        if revenue["kind"] == "fact":
            words += ": %s" % _md_cell(revenue, bases)
        if share["kind"] == "calc":
            words += ", %s of the firm (calculated)" % _md_cell(share, bases)
        elif share["kind"] == "fact":
            words += ", %s of the latest reported period" % _md_cell(
                share, bases)
        parts.append(words)
    words = "; ".join(parts) if parts else "no revenue lines are stated"
    return words + ("" if note is None else " - " + note)


def _management_words(pack, facts, frame, guidance=True):
    """Management on one line: tenure and ownership, then - on the one
    page - its guidance as a sentence. The full document passes
    guidance=False and prints the guidance as tables (unit READ-B1)."""
    management = frame.get("management") or {}
    bits = []
    for label, key in (("CEO tenure", "ceo_tenure_years"),
                       ("CFO tenure", "cfo_tenure_years"),
                       ("insider ownership", "insider_ownership_pct")):
        fact_id = management.get(key)
        if fact_id:
            named = str((facts.get(fact_id) or {}).get("label") or "").strip()
            figure = _figure(pack, facts, fact_id)
            bits.append(figure if named else "%s %s" % (label, figure))
    rows, note = _rows((management.get("guidance_vs_delivery") or [])
                       if guidance else [], "guided quarters")
    for row in rows:
        guided = " / ".join(_figure(pack, facts, fact_id)
                           for fact_id in row.get("guided") or [])
        revisions = row.get("revisions")
        if isinstance(revisions, list):
            # Owner ruling AC30(6): the FIRST guidance, then each revision
            # with its date, then what was delivered - delivery is judged
            # against the first; an empty list says it was never revised.
            revised = "; ".join(
                "revised on %s to %s"
                % (_safe(_format_date((item or {}).get("date"))),
                   " / ".join(_figure(pack, facts, fact_id)
                             for fact_id in (item or {}).get("guided")
                             or []) or "nothing named")
                for item in revisions) or FI_NEVER_REVISED
            bits.append("%s first guided %s; %s; delivered %s"
                        % (_safe(row.get("period")),
                           guided or "nothing named", revised,
                           _delivered(pack, facts, row)))
            continue
        bits.append("%s guided %s, delivered %s"
                    % (_safe(row.get("period")),
                       guided or "nothing named",
                       _delivered(pack, facts, row)))
    if note is not None:
        bits.append(note)
    if not bits:
        return MANAGEMENT_NOTHING
    return "; ".join(bits)


MANAGEMENT_NOTHING = "the pack states nothing about management"
MANAGEMENT_GUIDANCE_ONLY = "What it guided, and what it delivered, follows."


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
    # Owner rulings AC49(1) and AC50 (GROWTH-ARCHETYPE (c)): the growth
    # company and its one measure, one wording on every page.
    "reinvesting_grower": "a growth company that does not yet make a profit",
    # Owner rulings AC51-AC54 (RESOURCE-ARCHETYPE (c)): the producer.
    "resource_producer": "an oil, gas or mining producer",
    "investment_holding": "a holding company that owns other businesses",
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
    "ev_to_gross_profit_against_revenue_growth":
        "enterprise value against gross profit, read beside sales growth",
    "ev_to_reserves_against_cash_flow_at_the_recorded_price":
        "enterprise value against its reserves and against the cash they "
        "earn, each beside the price it rests on",
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
# Owner rulings AC59-AC62: one wording for every holding reader.
HOLDING_ARCHETYPE = "investment_holding"
HOLDING_KIND_WORDS = _ARCHETYPE_WORDS[HOLDING_ARCHETYPE]
VALUATION_BASIS_WORDS = {
    "listed_peer_multiples": "against listed companies like it",
    "latest_funding_round": "at its latest funding round",
    "discounted_cash_flow": "on its forecast cash",
    "fund_manager_statement": "on the fund manager's statement",
    "cost": "at cost",
    "other": "another way the company states",
}
HOLDING_POSITION_WORDS = {
    "wider": "Today's discount on the company's latest published value is wider than {comparison}.",
    "inside": "Today's discount on the company's latest published value is inside the range of {years}.",
    "narrower": "Today's discount on the company's latest published value is narrower than {comparison}.",
}
HOLDING_COUNT_WORDS = ("zero", "one", "two", "three", "four", "five")
HOLDING_CURRENCY_WORDS = {
    "USD": "US dollars", "EUR": "euros", "SEK": "Swedish kronor",
    "GBP": "pounds sterling", "CAD": "Canadian dollars", "AUD": "Australian dollars",
    "CHF": "Swiss francs", "HKD": "Hong Kong dollars", "AED": "UAE dirhams",
}
ONE_HOLDING_SENTENCE = "Most of this company's value is one holding, %s, which this sitting did not rate."
MOSTLY_PRIVATE_SENTENCE = "Most of what this company owns is private; private values move slowly and usually lag the market in a fall."
HOLDING_LEAD = "Discount to net asset value"


def holding_currency_words(unit):
    """AC62(H16): the pack's currency, named once in plain words."""
    unit = (_floors()["prose_figure_marks"].get("currency_aliases") or {}).get(unit, unit) or ""
    return HOLDING_CURRENCY_WORDS.get(unit.split("_")[0], "")


def holding_currency_line(capture):
    frame = holding_subject_frame(capture)
    facts = holding_display_facts(capture, recorded=True)
    row = _floors()["archetype_measures"]["table"][frame["archetype"]]
    unit = (facts.get(row["subject_numerator"]) or {}).get("unit")
    return "All money figures are in %s." % holding_currency_words(unit)


def holding_position_words(readings):
    """Architect W1: name the compared discount and the complete pairs."""
    count, word = len(readings["history"]), readings.get("range_word")
    if not count or word not in HOLDING_POSITION_WORDS:
        reason = readings.get("history_reason") or "; ".join(readings.get("errors") or [])
        return reason[:1].upper() + reason[1:]
    years = ("the last five year-ends" if count == 5 else
             "the %s year-end%s recorded" % (HOLDING_COUNT_WORDS[count], "" if count == 1 else "s"))
    comparison = ("at " if count == 1 else "at either of " if count == 2 else "at any of ") + years
    return HOLDING_POSITION_WORDS[word].format(comparison=comparison, years=years)


def holding_history_lead(readings):
    count = len(readings["history"])
    if not count:
        return ""
    return ("The discount at each of the last five financial year-ends" if count == 5 else
            "The discount at each of the %s financial year-end%s recorded" % (
                HOLDING_COUNT_WORDS[count], "" if count == 1 else "s"))

def holding_subject_frame(capture):
    frame = (capture.get("business_frame") or {}).get(
        (capture.get("subject") or {}).get("ticker"))
    return frame if frame and frame.get("archetype") == HOLDING_ARCHETYPE else None


def holding_readings(pack):
    return sufficiency.holding_readings(pack, _floors())


def holding_percent(readings, key):
    figure = readings.get(key)
    if figure is None:
        return "; ".join(readings.get("errors") or ["no published value"])
    return "%s%% (calculated)" % figure["percent"]


def holding_sentences(readings):
    sentences = []
    if readings.get("largest_above_half"):
        sentences.append(ONE_HOLDING_SENTENCE % readings["largest"]["name"])
    if readings.get("private_above_half"):
        sentences.append(MOSTLY_PRIVATE_SENTENCE)
    return sentences


def holding_summary(readings):
    return ("%s at today's prices (the one rated): %s; on the company's latest "
            "published value (comparable with the history): %s. %s. Private holding "
            "share: %s." % (HOLDING_LEAD, holding_percent(readings, "discount_today"),
            holding_percent(readings, "discount_published"), holding_position_words(readings).rstrip("."),
            holding_percent(readings, "private_share")))


def holding_facts_read(capture, frame):
    facts = holding_display_facts(capture, recorded=True)
    rating = next((r for r in capture["sufficiency"]["requirements"]
                   if r["id"] == "rating_vs_history_or_peers"), {})
    tagged, _, _ = sufficiency._holding_roles(_floors(), frame, rating, facts)
    return set(tagged)


def holding_display_facts(capture, recorded=False):
    """AC62(H16): ONE accessor for every by-id page reading.
    Recorded provenance and rule operands retain their source values;
    displayed money reads select the conversion vouched for by the rule."""
    facts = {fact.get("id"): fact for fact in capture.get("tier1") or []}
    frame = holding_subject_frame(capture)
    if frame is None or recorded:
        return facts
    tagged, _, _ = sufficiency._holding_roles(_floors(), frame, {}, facts,
        sufficiency._as_of_moment(capture["captured_at"]).date())
    displayed = dict(facts)
    for fid, roles in tagged.items():
        converted = sorted(r[len("native:"):] for r in roles if r.startswith("native:"))
        if converted:
            displayed[fid] = facts[converted[0]]
    return displayed


def holding_display_id(capture, fact_id):
    fact = holding_display_facts(capture).get(fact_id)
    return fact["id"] if fact is not None else fact_id

def holding_tables(pack, frame, readings):
    """AC60-AC62: build every holding table once from the ONE readings.
    Fact cells keep their ids for the seats; authored words stay prose."""
    capture, bridge = pack["capture"], frame.get("nav_bridge") or {}
    facts = _facts_by_id(capture)

    def value(fid):
        return _id_cell(pack, facts, holding_display_id(capture, fid))

    def percent(key, row=None):
        return (_words if (row or readings).get(key) is not None else _prose)(holding_percent(row or readings, key))

    rows = []
    for part in readings["holdings"]:
        method = part.get("method")
        private = method in ("company_reported_value", "carrying_value")
        rows.append([_prose(part.get("name")),
            _words(FI_METHOD_WORDS[method]) if method in FI_METHOD_WORDS else _prose(method),
            (_words(VALUATION_BASIS_WORDS[part["valuation_basis"]])
             if part.get("valuation_basis") in VALUATION_BASIS_WORDS
             else _prose(part.get("valuation_basis") or "not stated")) if private else _words("listed"),
            _words(_format_date(part.get("as_of"))), value(part.get("value_fact")), percent("share", part)])
    bridge_table = {"head": ["Holding", "How it is valued", "Private holding basis", "As of",
                              "Value", "Share of gross value (calculated)"], "rows": rows, "below": []}
    totals = [[_words(label), value(bridge.get(key))] for label, key in (
        ("Holding-company net debt", "holdco_net_debt_fact"), ("Net asset value", "nav_total_fact"),
        ("Published net asset value", "published_nav_fact"))]
    totals += [[_words(label), percent(key)] for label, key in (
        ("Discount to net asset value at today's prices (the one rated)", "discount_today"),
        ("Discount to net asset value on the company's latest published value (comparable with the history)", "discount_published"),
        ("Private holding share", "private_share"), ("Loan-to-value", "loan_to_value"),
        ("Yearly costs against net asset value", "costs_to_nav"))]
    block = _floors()["archetype_floors"][HOLDING_ARCHETYPE]
    entries = block["all_subtypes"]
    cash_prefix = block["canonical_tests"]["free_cash_flow"]["answered_by_prefix"]
    cost_ids = {e["id"] for e in entries if e["kind"] == "id"
                and e["why"].startswith("AC60(H8): yearly own costs")}
    return_prefixes = tuple(e["prefix"] for e in entries if e["kind"] == "prefix"
                            and e["why"].startswith("AC62(H16)"))
    totals += [[_prose(_plain_name(facts, fid)), value(fid)] for fid in sorted(facts)
               if fid in cost_ids or fid.startswith((cash_prefix,) + return_prefixes)]
    history = [[_words(row["year"].removeprefix("fy")), value(row["nav_fact"]),
                value(row["price_fact"]), percent("discount", row)]
               for row in reversed(readings["history"])]
    below = ([[_words("Average:"), percent("history_average")]] if history else [])
    below += [[(_words if readings.get("range_word") else _prose)(holding_position_words(readings))]]
    _, _, prefixes = sufficiency._holding_roles(_floors(), frame, {}, holding_display_facts(capture, recorded=True))
    below += [[_prose(gap.get("reason"))] for gap in capture.get("gaps") or []
              if any((gap.get("fact_class") or "").startswith(p) for p in prefixes)]
    tables = [("The net asset value, part by part", bridge_table),
              ("The holding company and its dividend cover", {"head": ["Figure", "Value"], "rows": totals, "below": []})]
    if history:
        tables.append((holding_history_lead(readings), {
            "head": ["Year-end", "Published net asset value", "Price", "Discount (calculated)"],
            "rows": history, "below": below}))
    return tables


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

# Owner rulings AC49(1) and AC50 (GROWTH-ARCHETYPE (c), the pages): the plain
# words for what a growth company's frame declares, read by every renderer -
# the seats' case file imports them and the report holds its own archetype and
# measure tables equal to this module's by a test. Evidence and the ruled
# sentence only: no word here reads the yardstick.
GROWER_ARCHETYPE = "reinvesting_grower"
GROWER_SUBTYPE_WORDS = {
    "recurring_revenue": "a subscription business",
    "transaction_platform": "a platform that earns a cut of what passes "
                            "through it",
}
GROWER_NATURE_WORDS = {
    "subscription": "subscription income",
    "usage": "usage income",
    "transaction": "transaction income",
    "product": "product sales",
}
# Owner ruling AC50(8): below the line the council rates the company at most
# hold, sell still allowed, and the front says so in this one sentence. The
# line is the floors' own figure, filled in where the sentence is printed.
GROWER_CAP_SENTENCE = ("The company's cash covers fewer than %s months at its "
                       "recent burn, so the council may not rate it above "
                       "hold.")
GROWER_MONTHS_LEAD = "Months of cash left: "
GROWER_NOT_BURNING = "not burning cash"
GROWER_NOT_COUNTED = "shown, not counted"
GROWER_UNDRAWN_LEAD = "Undrawn credit lines, shown and not counted: "
GROWER_GUIDED = "guided by the company - shown beside, never rated on"
CALCULATED = "calculated"
RECORDED = "recorded"
# The facts the yardstick and what stands beside it are read from (owner
# rulings AC50(5), (6) and (9)), by the ids the grower's floors require.
GROWER_REVENUE_PAIR = ("revenue_q", "revenue_prior_year_q")
GROWER_STOCK_PAY = "stock_based_compensation_q"
GROWER_SHARES_PAIR = ("diluted_shares_q", "diluted_shares_prior_year_q")
GROWER_ARR_PREFIX = "arr_"
GROWER_GUIDED_PREFIX = "guidance_breakeven_"
GROWER_QUARTER_PREFIXES = ("revenue_quarter_", "gross_profit_quarter_",
                           "operating_income_quarter_")
QUARTERS_HEAD = ("Quarter", "Sales", "Gross profit", "Operating profit")
YARDSTICK_HEAD = ("Figure", "Value", "How it is struck")
RUNWAY_HEAD = ("Figure", "Value", "How it counts")

# Owner rulings AC51-AC56 (RESOURCE-ARCHETYPE (c), the pages): the plain words
# for what a producer's frame declares, read by every renderer as the grower's
# are. Evidence and the ruled sentence only: no word here reads the yardstick
# or judges the reserves.
PRODUCER_ARCHETYPE = gate._PRODUCER_ARCHETYPE
PRODUCER_SUBTYPE_WORDS = {
    "oil_and_gas_producer": "an oil and gas producer",
    "miner": "a miner",
    "royalty_and_streaming": "a royalty and streaming company",
}
PRODUCT_WORDS = {
    "crude_oil": "crude oil",
    "natural_gas": "natural gas",
    "gold": "gold",
    "silver": "silver",
    "copper": "copper",
}
PRODUCER_NATURE_WORDS = {
    "commodity_sales": "commodity sales",
    "royalty": "royalty income",
    "stream": "stream income",
}
RESERVES_STANDARD_WORDS = {
    "sec_oil_and_gas": "the US SEC's oil and gas rules",
    "sec_s_k_1300": "the US SEC's mining rules (S-K 1300)",
    "ni_43_101": "Canada's NI 43-101",
    "jorc": "Australia's JORC code",
    "prms": "the SPE petroleum resources management system",
}
# Owner ruling AC53(R9), the words the architect confirmed: where today's price
# is below the price some reserves were counted at, every page says so.
RESERVE_PRICE_SENTENCE = ("Today's price is below the price some of these "
                          "reserves were counted at, so they rest on a price "
                          "the market is not paying today.")
# A quantity unit read after "per" (register item P-RESOURCEb-5); a unit the
# table does not name reads as its own words.
PER_UNIT_WORDS = {
    "boe": "barrel of oil equivalent",
    "bbl": "barrel",
    "mcf": "thousand cubic feet",
    "oz": "ounce",
    "lb": "pound",
    "tonnes": "tonne",
}
PRODUCER_LIFE_LEAD = "Reserve life: "
BY_PRODUCT_WORDS = " - a by-product, shown apart and not rated on"
NOT_COMPARABLE = "not comparable in one unit"
NEGATIVE_CASH = "negative, not a multiple"
PRODUCER_NO_HEDGE = "none - the company does not hedge"
PRODUCER_NOT_NETTED = "shown, never netted"
PRODUCER_BESIDE = "shown beside, never the denominator"
INTEGRATED_BESIDE_LEAD = "Its reserves and today's price, shown beside: "
PRODUCER_STANDARDIZED = sufficiency._PRODUCER_STANDARDIZED
PRODUCER_BALANCE_IDS = sufficiency._PRODUCER_BALANCE
PRODUCER_QUARTER_PREFIXES = ("production_quarter_", "realized_price_quarter_")
PRODUCER_LATEST_PAIRS = tuple(zip(sufficiency._PRODUCER_HEADLINES,
                                 sufficiency._PRODUCER_YEAR_AGO))
RESERVES_HEAD = ("Reserves", "Amount", "Standard", "As of",
                 "Counted at", "Today's price")
PRODUCER_QUARTERS_HEAD = ("Quarter", "Output", "Price received")
# The rating row is the producer's third standard test (owner ruling
# AC54(R14)(iii)): the yardstick, named in the measure's own words.
PRODUCER_THIRD_TEST = ("rating_vs_history_or_peers",
                       "a producer's third standard test - the producer's "
                       "yardstick: %s")

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
    it: its plain label, then the figure in the market form (unit READ-B2).
    Anything that is not a tier-1 id of this pack is sent through _safe,
    as data (P-U3e-3)."""
    if not isinstance(fact_id, str) or fact_id not in facts:
        return "%s (not in the pack)" % _safe(fact_id)
    return _figure(pack, facts, fact_id)


def _fi_values(pack, facts, fact_ids):
    return "; ".join(_fi_value(pack, facts, fid) for fid in fact_ids or ())


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
    cushion = _cushion_words(facts.get(ratio), facts.get(requirement))
    return ("%s, against %s%s"
            % (_fi_value(pack, facts, ratio),
               _fi_value(pack, facts, requirement), cushion))


_PERCENT_UNITS = ("percent", "%", "pct")


def _cushion_words(ratio, requirement):
    """The gap between a capital ratio and its requirement, in points to
    one decimal, struck at display from the two recorded percentages
    (unit READ-B2: reading precision belongs to the page, the ruling
    closing PRECISION-REG-1). Nothing where either is not a percentage."""
    if not ratio or not requirement:
        return ""
    if (ratio.get("unit") not in _PERCENT_UNITS
            or requirement.get("unit") not in _PERCENT_UNITS):
        return ""
    try:
        gap = (decimal.Decimal(str(ratio.get("value")))
               - decimal.Decimal(str(requirement.get("value"))))
    except (decimal.InvalidOperation, ValueError):
        return ""
    if not gap.is_finite():
        return ""
    points = gap.quantize(decimal.Decimal("0.1"),
                          rounding=decimal.ROUND_HALF_UP)
    if points < 0:
        return " - short of it by %s points (calculated)" % abs(points)
    return " - a cushion of %s points (calculated)" % points


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


def grower_subject_frame(capture):
    """The single name's own frame where it declares the growth
    archetype, or None."""
    subject = capture.get("subject") or {}
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    if isinstance(frame, dict) and frame.get("archetype") == GROWER_ARCHETYPE:
        return frame
    return None


def grower_kind_words(frame, escape):
    """What kind of growth company this is, in the page's words: the
    archetype and the sub-type. `escape` is the renderer's own
    neutralisation, applied only to a value outside the ruled words."""
    subtype = frame.get("grower_subtype")
    return "%s - %s" % (_ARCHETYPE_WORDS[GROWER_ARCHETYPE],
                        GROWER_SUBTYPE_WORDS.get(subtype) or escape(subtype)
                        or "its kind not stated")


def grower_runway(pack):
    """The months of cash left as sufficiency.growth_runway reads them
    under the ruled floors (owner rulings AC50(7) and AC50(8); architect
    ruling A6) - the one reading every page prints; nothing here works
    the months out again. None for any other subject."""
    return sufficiency.growth_runway(pack, _floors())


def grower_cap_sentence(runway):
    """The ruled sentence (owner ruling AC50(8)) where the company's cash
    covers fewer months than the line, its figure the floors' own; None
    at or above the line and for any other subject."""
    if not runway or not runway.get("below"):
        return None
    return GROWER_CAP_SENTENCE % runway["threshold_months"]


def grower_months_words(runway):
    """The months of cash left as every page prints them: the helper's
    figure, cut toward zero to one place and marked calculated, against
    the ruled line; a company generating cash is not burning it."""
    if runway is None:
        return NOT_CALCULABLE
    if runway.get("burn") is None:
        return GROWER_NOT_BURNING
    return ("%s months (%s), at the last four quarters' cash burn, against "
            "the owner's line of %s months"
            % (runway["months"], CALCULATED, runway["threshold_months"]))


def grower_months_line(runway, with_cap=True):
    """The one line the one-page brief, the full document and the case
    file print alike: the months of cash left, then - below the line -
    the ruled sentence (the report's front sets that sentence in a card
    of its own, `with_cap` False)."""
    cap = grower_cap_sentence(runway) if with_cap else None
    return "%s%s.%s" % (GROWER_MONTHS_LEAD, grower_months_words(runway),
                        (" " + cap) if cap else "")


def grower_undrawn_words(pack, frame):
    """Each undrawn credit line the runway block names - its plain name and
    its figure - before either printer escapes them, for the summaries that
    print the months of cash left (owner ruling AC50(7): shown, not
    counted; audit finding r1-4). Empty where the block names none."""
    block = frame.get("growth_runway")
    block = block if isinstance(block, dict) else {}
    facts = _facts_by_id(pack["capture"])
    return ["%s %s" % (_plain_name(facts, fid),
                       cell_text(_fact_cell(pack, facts, fid)))
            if isinstance(fid, str) and fid in facts
            else _plain_name(facts, fid)
            for fid in block.get("undrawn_facility_facts") or []]


def _grower_archetype_line(capture, frame, kind_words=None):
    """The one-page brief's archetype line for a growth company (or, with
    `kind_words`, a producer): the kind of business, its sub-type and the
    measure."""
    measure = _rating_measure(capture)
    line = "- Archetype: %s" % (kind_words or grower_kind_words)(frame, _safe)
    if measure:
        line += " - rated on %s" % _MEASURE_WORDS.get(measure, _safe(measure))
    return line


def producer_subject_frame(capture):
    """The single name's own frame where it declares the producer
    archetype, or None."""
    subject = capture.get("subject") or {}
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    if (isinstance(frame, dict)
            and frame.get("archetype") == PRODUCER_ARCHETYPE):
        return frame
    return None


def _resource_block(frame):
    block = frame.get("resource_base")
    return block if isinstance(block, dict) else {}


def producer_kind_words(frame, escape):
    """What kind of producer this is, in the page's words: the archetype,
    the sub-type and the main commodity. `escape` is the renderer's own
    neutralisation, applied only to a value outside the ruled words."""
    subtype = frame.get("producer_subtype")
    product = _resource_block(frame).get("product")
    return "%s - %s whose main commodity is %s" % (
        _ARCHETYPE_WORDS[PRODUCER_ARCHETYPE],
        PRODUCER_SUBTYPE_WORDS.get(subtype) or escape(subtype)
        or "its kind not stated",
        PRODUCT_WORDS.get(product) or escape(product) or "not stated")


def producer_readings(pack):
    """The producer's worked-out figures as sufficiency.resource_readings
    reads them under the ruled floors (owner rulings AC52(R5), AC53(R9),
    AC54(R13)) - the one reading every page prints; nothing here works a
    figure out again. None for any other subject."""
    return sufficiency.resource_readings(pack, _floors())


def reserve_price_sentence(readings):
    """The ruled sentence (owner ruling AC53(R9)) where today's price is
    below the price some reserves were counted at; None otherwise."""
    if not readings or readings.get("today_below_reserve_price") is not True:
        return None
    return RESERVE_PRICE_SENTENCE


def producer_life_words(readings):
    """The reserve life as every page prints it: the helper's figure, cut
    toward zero to one place and marked calculated; where the reserves and
    the output are read but not in one unit, not comparable - the council
    converts nothing."""
    life = (readings or {}).get("reserve_life_years")
    if life is not None:
        return ("%s years (%s), the reserves against the last four quarters' "
                "output" % (life, CALCULATED))
    output = (readings or {}).get("production_ttm")
    if (readings or {}).get("reserves") is not None and output is not None \
            and output > 0:
        return NOT_COMPARABLE
    return NOT_CALCULABLE


def producer_life_line(readings, with_sentence=True):
    """The one line the one-page brief, the full document and the case
    file print alike: the reserve life, then - where today's price is below
    the reserves' - the ruled sentence (the report's front sets that
    sentence in a card of its own, `with_sentence` False)."""
    sentence = reserve_price_sentence(readings) if with_sentence else None
    return "%s%s.%s" % (PRODUCER_LIFE_LEAD, producer_life_words(readings),
                        (" " + sentence) if sentence else "")


def _tier1_ids(capture):
    return [fact["id"] for fact in capture.get("tier1") or []
            if isinstance(fact.get("id"), str)]


def _resource_rule():
    return (_floors().get("archetype_measures") or {}).get(
        "resource_rule") or {}


def _family(field, subtype=None):
    """The id prefixes the producer rule reads a resource-block field by
    (architect ruling B12), the sub-type's own where the floors give one."""
    rule = _resource_rule()
    prefixes = dict(rule.get("block_families") or {})
    prefixes.update((rule.get("block_families_by_subtype") or {}).get(
        subtype) or {})
    return tuple(prefixes.get(field) or ())


def integrated_major_frame(capture):
    """The single name's own frame where it carries the integrated_major
    block (owner ruling AC52(1)), or None."""
    subject = capture.get("subject") or {}
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    if isinstance(frame, dict) and isinstance(frame.get("integrated_major"),
                                              dict):
        return frame
    return None


def integrated_major_ids(capture):
    """Owner ruling AC52(1), register item P-RESOURCEa-4: a passing
    integrated major is shown with its reserves and today's commodity price
    beside - every reported reserve, and every today's price of crude oil or
    natural gas the three-arm test reads (the architect's ruling on
    P-RESOURCEc-3: the one set, sufficiency.integrated_major_prices). None
    for any subject whose own frame carries no integrated_major block."""
    if integrated_major_frame(capture) is None:
        return None
    order = _tier1_ids(capture)
    products = (_floors().get("archetype_measures") or {}).get(
        "resource_products") or {}
    return (sufficiency._reserve_ids(_resource_rule(), order),
            [fid for fid, _ in sufficiency.integrated_major_prices(
                _resource_rule(), products, order, _floors())])


def integrated_major_words(pack):
    """The integrated major's reserves and today's price in one line of
    evidence, before either printer escapes it; None for any other
    subject."""
    found = integrated_major_ids(pack["capture"])
    if found is None:
        return None
    facts = _facts_by_id(pack["capture"])
    parts = ["%s %s" % (_plain_name(facts, fid),
                        cell_text(_fact_cell(pack, facts, fid)))
             for fid in found[0] + found[1]]
    if not found[1]:
        parts.append("today's price is not in the pack")
    return "; ".join(parts)


UNTRACED_LEAD = "Not traced: "
UNTRACED_SENTENCE = ("%d figure(s) in this business description match no "
                     "recorded fact and are marked in the text")
UNREADABLE_SENTENCE = "%d figure(s) in it could not be read"
NOT_CHANGING_WORDS = "The business is not changing its model."
CHANGING_KIND_WORDS = {
    "mix_shift": "its mix is shifting",
    "model_transition": "its model is changing",
    "turnaround": "a turnaround",
    "cyclical_trough": "at the bottom of its cycle",
    "cyclical_peak": "at the top of its cycle",
    "rollup": "a roll-up of acquisitions",
}


def _untraced_sentence(capture, ticker, frame):
    """The AC19 summary, only where a figure is not traced or not read."""
    _traced, untraced, unreadable = trace.frame_counts(
        capture, ticker, frame, _marks_config())
    parts = []
    if untraced:
        parts.append(UNTRACED_SENTENCE % untraced)
    if unreadable:
        parts.append(UNREADABLE_SENTENCE % unreadable)
    return (UNTRACED_LEAD + "; ".join(parts) + ".") if parts else None


def _changing_opening(changing):
    """What is changing, opened in words: the kind of change, or, where
    the capture says none, that the business is not changing its model."""
    kind = changing.get("kind")
    if kind == "none":
        return NOT_CHANGING_WORDS + " "
    words = CHANGING_KIND_WORDS.get(kind) or _safe(kind)
    return ("%s%s. " % (words[:1].upper(), words[1:])) if words else ""


def _one_frame_lines(pack, facts, passages, ticker, frame):
    """One business, in a handful of lines (spec section U3.1)."""
    capture = pack["capture"]
    bases = _frame_bases(capture, ticker)
    lines = ["**%s**" % _safe(ticker)]
    # Owner ruling AC19: the numbers below are marked where they are shown.
    # The summary count stands before the prose only when a figure is NOT
    # traced (unit READ-B2): a checking statistic that finds nothing is
    # not in the reader's path.
    untraced = _untraced_sentence(capture, ticker, frame)
    if untraced:
        lines.append("- %s" % untraced)
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
    elif (archetype == GROWER_ARCHETYPE
          and grower_subject_frame(capture) is frame):
        # Owner rulings AC49(1) and AC50: the kind of growth company, the
        # measure and the months of cash left stand on the one page, with
        # the ruled sentence below the line; the rest is in the full
        # document.
        lines.append(_grower_archetype_line(capture, frame))
        lines.append("- " + grower_months_line(grower_runway(pack)))
        undrawn = grower_undrawn_words(pack, frame)
        if undrawn:
            lines.append("- %s%s" % (GROWER_UNDRAWN_LEAD, "; ".join(
                _safe(words) for words in undrawn)))
    elif producer_subject_frame(capture) is frame:
        # Owner rulings AC51-AC54: the kind of producer, the measure and the
        # reserve life stand on the one page, with the ruled sentence where
        # today's price is below the reserves'; the rest is in the full
        # document.
        lines.append(_grower_archetype_line(capture, frame,
                                            producer_kind_words))
        lines.append("- " + _safe(producer_life_line(producer_readings(
            pack))))
    elif holding_subject_frame(capture) is frame:
        readings = holding_readings(pack)
        lines.append("- Archetype: %s - rated on %s" % (
            _ARCHETYPE_WORDS[HOLDING_ARCHETYPE], _MEASURE_WORDS[_rating_measure(capture)]))
        lines.append("- Holding: " + _safe(holding_currency_line(capture)))
        lines.append("- Holding: " + _safe(holding_summary(readings)))
        lines.append("- Holding: " + FI_NOT_RATED_SENTENCE)
        lines += ["- Holding: " + _marked(s, bases) for s in holding_sentences(readings)]
    elif archetype:
        measure = _rating_measure(capture)
        rated = ((" - rated on %s"
                  % _MEASURE_WORDS.get(measure, _safe(measure)))
                 if measure else "")
        lines.append("- Archetype: %s%s"
                     % (_ARCHETYPE_WORDS.get(archetype, _safe(archetype)),
                        rated))
        if integrated_major_frame(capture) is frame:
            lines.append("- %s%s" % (INTEGRATED_BESIDE_LEAD,
                                     _safe(integrated_major_words(pack))))
    lines.append("- What it does: %s"
                 % _marked_trim(frame.get("what_it_does"), bases,
                                figures=frame.get("what_it_does_figures")))
    lines.append("- How it earns: %s" % _how_it_earns_words(pack, frame,
                                                            bases))
    changing = frame.get("what_is_changing") or {}
    lines.append("- What is changing: %s%s"
                 % (_changing_opening(changing),
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
    lines.append("- Competitive standing: %s"
                 % (_safe(_trim(_first_sentence(passage.get("text")),
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


DECISIVE_TABLE_HEAD = ("| The number that decides | What answers it |",
                       "| --- | --- |")


def _decisive_lines(pack, facts, passages, capture):
    """The numbers that decide THIS question, as one small table (unit
    READ-B2): each metric beside its answering figures, by label, in the
    market form. The bound keeps the table whole or drops it whole."""
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
    lines.extend(DECISIVE_TABLE_HEAD)
    for ticker, metric in shown:
        bases = _frame_bases(capture, ticker)
        name = _marked_trim(metric.get("name"), bases, SHORT_TRIM)
        if len(frames) > 1:
            name += " (%s)" % _safe(ticker)
        gap = metric.get("gap")
        if gap:
            answer = ("NOT ANSWERED. %s. The test it weakens: %s."
                      % (_marked_trim(gap.get("reason"), bases, SHORT_TRIM),
                         _marked_trim(gap.get("weakened_test"), bases,
                                      SHORT_TRIM)))
        else:
            # Through _rows, like every other bounded list on this page: a
            # bare slice dropped the sixth frozen answer with nothing said
            # (audit round 1, r1-6).
            answers, answers_note = _rows(metric.get("answered_by") or [],
                                          "answers")
            parts = []
            for fact_id in answers:
                part = _figure(pack, facts, fact_id, passages)
                if fact_id in stale_ids:
                    part += (" (READING STALE: corrected without a new "
                             "source - re-gather before relying on it)")
                parts.append(part)
            if answers_note is not None:
                parts.append(answers_note)
            answer = "; ".join(parts) or "nothing is named"
        lines.append("| %s | %s |" % (name, answer))
    if note is not None:
        lines.append("")
        lines.append("- %s" % note)
    lines.append("")
    return lines


# Owner ruling AC41(4): the outside model's job before the sitting is the
# "evidence check", and a point the record rejected is "set aside". The
# words for a point's kind and severity are data, as the report's are.
EVIDENCE_CHECK = "evidence check"
FINDING_KIND_WORDS = {
    "missing_decisive_fact": "a deciding figure is missing",
    "suspect_figure": "a figure looks wrong",
    "framing_error": "the business is read wrongly",
    "missing_checklist_row": "a question is missing from the checklist",
    "source_doubt": "the source prints a different figure",
}
SEVERITY_WORDS = {
    "blocking": "Blocking",
    "material": "Material",
    "minor": "Minor",
}
_DISPOSITION_WORDS = {
    "captured": "gathered, and it is in the pack",
    "gap_declared": "conceded as a gap",
    "overruled": "set aside",
}


def _finding_title(finding):
    """A point's name, severity and kind in words: "Point E1, blocking - a
    deciding figure is missing"."""
    severity = finding.get("severity")
    kind = finding.get("kind")
    severity_words = SEVERITY_WORDS.get(severity) or _safe(severity)
    return "Point %s, %s - %s" % (_safe(finding.get("id")),
                                  severity_words.lower(),
                                  FINDING_KIND_WORDS.get(kind) or _safe(kind))


def _resolution_words(resolution, facts):
    """The record's answer to one point, in words: what was gathered, by
    label, or the reason's first sentence; the whole of the reason is in
    the full evidence."""
    resolution = resolution or {}
    disposition = resolution.get("disposition")
    words = _DISPOSITION_WORDS.get(disposition)
    if words is None:
        return None
    if disposition == "captured":
        named = "; ".join(_fact_ref(facts, item)
                          for item in resolution.get("fact_ids") or [])
        return "%s (%s)" % (words, named or "no figure named")
    # Bounded by characters as well as by sentence: one Markdown line that
    # wraps across the page defeats the one-page bound (audit round 1 of
    # UPGRADE2-READ-B2).
    reason = _safe(_trim(_first_sentence(resolution.get("reason")),
                         SHORT_TRIM)) or "no reason given"
    if disposition == "gap_declared":
        return ("%s: %s The test it weakens: %s"
                % (words, reason,
                   _safe(_trim(resolution.get("weakened_test"), SHORT_TRIM))
                   or "not named"))
    return "%s: %s" % (words, reason)


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
    """The evidence check, every point shown (unit READ-B2): the point's
    severity and kind in words, the point's first sentence with the pack
    pointer, then the record's answer. This section is cut last
    by the page's line bound; the whole of each point is in the full
    evidence."""
    block = capture.get("evidence_challenge") or {}
    lines = ["## The %s: what the outside model asked for, and what "
             "happened" % EVIDENCE_CHECK, ""]
    if block.get("status") != "success":
        lines.append("**NOTHING HERE WAS CHECKED BY A SECOND MODEL.** The "
                     "evidence check failed: %s - %s. Every figure on this "
                     "page is one session's work."
                     % (_one_line(block.get("failure_status"))
                        or "no status recorded",
                        _safe(_trim(block.get("failure_reason"), SHORT_TRIM))
                        or "no reason recorded"))
        lines.append("")
        return lines
    facts = holding_display_facts(capture, recorded=True)
    findings = block.get("findings") or []
    resolutions = block.get("resolutions") or {}
    lines.append("A model outside this council's own family (%s) read this "
                 "evidence before any seat was paid."
                 % (_safe(block.get("model")) or "not recorded"))
    if not findings:
        lines.append("- It found nothing to raise against this evidence.")
    for finding in findings:
        # One line per point, the answer beside it (the review's row).
        answer = _resolution_words(resolutions.get(finding.get("id")),
                                   facts)
        lines.append("- **%s.** %s %s"
                     % (_finding_title(finding),
                        _safe(_point_words(finding.get("detail"))),
                        ("**Answered:** %s" % answer) if answer is not None
                        else "**NOT ANSWERED by the record.**"))
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
        named.append("conceded in the %s: %s"
                     % (EVIDENCE_CHECK,
                        ", ".join("point %s" % _safe(point_id)
                                  for point_id, _ in conceded)))
    lines.append("- Every gap on this record, named - %s." % "; ".join(named))
    shown, note = _rows(gaps, "declared gaps")
    for gap in shown:
        # Unit READ-B2: each gap by its reason first, its class after.
        lines.append("- %s (%s; the test it weakens: %s)"
                     % (_safe(_trim(gap.get("reason"), SHORT_TRIM)),
                        _safe(gap.get("fact_class")),
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
            lines.append("- Conceded in the %s - point %s: %s (the "
                         "test it weakens: %s)"
                         % (EVIDENCE_CHECK, _safe(point_id),
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
        # Unit READ-B2: the price, the 200-day average and the gap between
        # them, and both 52-week ranges, in the market form - the tape's
        # own figures, with the close they are read at.
        low, high = facts.get(RANGE_LOW_ID), facts.get(RANGE_HIGH_ID)
        price = facts[PRICE_ID]
        lines.append("- Price: %s, on %s%s."
                     % (_shown(price), _safe(_format_date(price.get("as_of"))),
                        _freshness_mark(pack, PRICE_ID)))
        closing = [facts[fact_id] for fact_id in CLOSING_RANGE_IDS
                   if fact_id in facts]
        if low is not None and high is not None:
            lines.append("- The 52-week trading range: %s to %s%s."
                         % (_shown(low), _shown(high),
                            ("; the closing range: %s to %s"
                             % (_shown(closing[0]), _shown(closing[1])))
                            if len(closing) == len(CLOSING_RANGE_IDS)
                            else ""))
        carried = [fact_id for fact_id in AVERAGE_IDS if fact_id in facts]
        if carried:
            lines.append("- %s (at the close of %s)."
                         % ("; ".join(_figure(pack, facts, fact_id)
                                      for fact_id in carried),
                            _safe(_format_date(
                                facts[carried[0]].get("as_of")))))
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
        lines.append("- %s — %s%s"
                     % (_safe(_format_date(when)),
                        _fact_name(facts.get(fact_id) or {"id": fact_id}),
                        (": " + _safe(_trim(detail, SHORT_TRIM)))
                        if detail else ""))
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
    status = ("" if isinstance(flag, bool)
              else " (estimate status not recorded)")
    # Unit READ-B2 (owner ruling AC41(4)): the money follows the report's
    # own rule and price list - the capture's figure in the estimated bin
    # unless its flag says counted, the evidence check's counted - read
    # through the report's one function, never summed across bins.
    tokens = usage.get("tokens")
    if _is_count(tokens):
        shown, words = _priced("council", "the evidence gathering", tokens,
                               flag is not False)
        gathering = "%s (tokens: %s%s)" % (shown, words, status)
    else:
        gathering = ("tokens as recorded: %s%s, not a count, so not priced"
                     % (_count_words(tokens), status))
    lines.append("- Gathering the evidence (%s): %s minutes; %s."
                 % (_safe(capture_model(usage) or "a model not recorded"),
                    _count_words(usage.get("minutes")), gathering))
    if challenge is None:
        checked = "not recorded"
    else:
        checked = "%s (tokens: %s)" % _priced(
            "outside", "the evidence check", challenge, False)
    lines.append("- The %s by the outside model: %s." % (EVIDENCE_CHECK,
                                                        checked))
    lines.append("- %s" % _safe(_list_prices()["comment"]))
    lines.append("")
    return lines


def _is_count(value):
    return (isinstance(value, int) and not isinstance(value, bool)
            and value >= 0)


def _priced(key, name, tokens, is_estimate):
    """One cost row's money and token words, from the report's own function
    and price list (loaded when first used, as the formatter is)."""
    from council.report import render_report
    return render_report.priced_tokens(key, [(name, [tokens], is_estimate)])


def _list_prices():
    from council.report import render_report
    return render_report.LIST_PRICES


def _count_words(value):
    """A recorded count with thousands separators; anything that is not a
    whole number prints as recorded, and nothing as 'not recorded'."""
    if isinstance(value, int) and not isinstance(value, bool):
        return "{:,}".format(value)
    return _safe(value) or "not recorded"


WHAT_HAPPENS_NOW = ("Nothing runs until you approve this evidence. Tell the "
                    "host 'approved', with any changes.")


def _closing_lines():
    return ["## What happens now", "",
            WHAT_HAPPENS_NOW + " In auto-mode the council sits without that "
            "step, and the report's front page says so.", ""]


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
# Architect ruling 11 of unit READ-B (READ-B2): the evidence check and the
# numbers that decide are cut last, only once no other section can give.
CUT_LAST = ("decisive", "auditor")
CUT_NOTE = ("- The one-page bound cut %d further line(s) from this "
            "section; %s.")
# Inside the full document the one page is a summary with the whole of
# the evidence below it, so its cut notes point there (ruling 10 of READ-B).
CUT_NOTE_IN_FULL = ("- %d further line(s) of this section follow in the "
                    "full evidence below.")
CUT_TOTAL_NOTE_IN_FULL = ("%d line(s) of this summary follow in the full "
                          "evidence below.")
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
SHAPE_PREFIXES = ("**", "- " + UNTRACED_LEAD, "- Archetype: ",
                  "- Capital beside its requirement: ", "- Cycle: ",
                  "- " + GROWER_MONTHS_LEAD, "- " + GROWER_UNDRAWN_LEAD,
                  "- " + PRODUCER_LIFE_LEAD, "- " + INTEGRATED_BESIDE_LEAD, "- Holding: ")


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


def _fit_to_one_page(blocks, in_full=False):
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
        givers = [name for name in givers if name not in CUT_LAST] or givers
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
            # A table is one block: kept whole or dropped whole (ruling 11
            # of READ-B), never cut between its rows.
            if 0 < count < len(body) and body[count].startswith("|"):
                while count > 0 and body[count - 1].startswith("|"):
                    count -= 1
            kept = body[:count]
        omitted += len(body) - len(kept)
        note = (CUT_NOTE_IN_FULL % (len(body) - len(kept)) if in_full
                else CUT_NOTE % (len(body) - len(kept), IN_THE_PACK))
        out.extend(lines[:2] + kept + [note] + lines[-1:])
    if omitted:
        out.append(CUT_TOTAL_NOTE_IN_FULL % omitted if in_full
                   else CUT_TOTAL_NOTE % (omitted, IN_THE_PACK))
    return out


def render(pack, pack_sha256, usage=None, in_full=False):
    """The whole brief, as one string. `usage` is the capture stage's own
    cost sidecar, or None where none stands. `in_full` is set by
    render_full, where this page is the summary at the top of the whole
    evidence and its cut notes point below."""
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
    return "\n".join(_fit_to_one_page(blocks, in_full)).rstrip("\n") + "\n"


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
    """The owner-facing name of a fact (owner ruling AC15, P5): its plain
    name, as every reference to it reads."""
    return _fact_name(fact)


def _fact_ref(facts, fact_id, passages=None):
    """A reference to a fact for the reader (unit READ-B2): its plain
    label, never its key; the key stands only in the fact's own entry
    below, in small print. A fact without a label is named by its key, its
    only name; a passage by its title in words; an id the pack does not
    carry is sent through _safe as data and said to be missing."""
    fact = (facts or {}).get(fact_id)
    if fact is not None:
        return _fact_name(fact)
    if fact_id in (passages or {}):
        return "the passage %s" % _passage_title(fact_id)
    return "%s (not in the pack)" % _safe(fact_id)


# ------------------------------------------------ the business tables
# Unit READ-B1 (owner rulings AC40(2c), AC16(4); the seed's design item 1):
# the business sections are small tables of figures, built ONCE here as
# data and printed twice - as HTML by the report, as Markdown by the full
# document - through the one market formatter. A table is a dict: "head"
# (the column names), "rows" (lists of cells) and "below" (lines under the
# table, each a list of cells read with a space between them). A cell is a
# dict whose "kind" says how it reads: "fact" (a recorded fact, in the
# market form), "calc" (a figure struck here at display from recorded
# ones, exact until it is shown to one decimal - reading precision belongs
# to the page, the ruling closing PRECISION-REG-1), "reading" (one dated
# point of a cycle series), "words" (the page's own words or a label) and
# "prose" (the capture's own words, which each printer marks by owner
# ruling AC19). Nothing here reads a
# figure: the tables are evidence, never analysis (AC15 P4).

NOT_CALCULABLE = "not calculable"
NOT_REPORTED = "not reported yet"
NO_FIGURE = "—"
FIRM_TOTAL_NOT_OWN = "the firm total, not the line's own"
PRIOR_YEAR_TAIL = "_prior_year_q"
QUARTER_TAIL = "_q"
HEADLINE_REVENUE = "revenue_q"
EARNINGS_HEAD = ("Business", "Kind of earnings", "Revenue, latest quarter",
                 "Share of the firm (calculated)",
                 "Change on a year ago (calculated)")
EARNINGS_SHARE_RECORDED = "Share of the firm (recorded, else calculated)"
GUIDANCE_HEAD = ("Metric", "First guide")
GUIDANCE_REVISED = "Revised %s"
GUIDANCE_TAIL = ("Delivered", "Delivered minus first guide (calculated)")
GUIDANCE_LEAD = ("Guidance for %s: the first guide, each revision, then "
                 "what was delivered")
GUIDANCE_OTHER = "Other: %s"
CAPITAL_HEAD = ("Capital ratio", "Level", "Its requirement", "Required",
                "Cushion (calculated)")
STRESS_HEAD = ("Figure", "Value", "As of")
RISK_HEAD = ("Figure", "Latest", "A year ago", "As of")
CYCLE_HEAD = ("Series", "First reading", "Latest reading", "Change")


def _words(text):
    return {"kind": "words", "text": _one_line(text)}


def _prose(text):
    return {"kind": "prose", "text": _one_line(text)}


def _fact_cell(pack, facts, fact_id):
    """A fact the table shows, or where the pack does not carry it the id
    said to be missing (as data, P-U3e-3)."""
    fact = facts.get(fact_id) if isinstance(fact_id, str) else None
    if fact is None:
        return _words("%s (not in the pack)" % _one_line(fact_id))
    return {"kind": "fact", "fact": fact,
            "stale": _freshness_mark(pack, fact_id)}


def _number(fact):
    """A fact's recorded value as an exact decimal, or None."""
    try:
        value = decimal.Decimal(str((fact or {}).get("value")))
    except (decimal.InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _calc(value, unit, how, signed=False):
    """A figure struck at display, or "not calculable" where it cannot be."""
    if value is None:
        return _words(NOT_CALCULABLE)
    return {"kind": "calc", "value": value, "unit": unit, "how": how,
            "signed": signed}


def _difference_unit(unit):
    """The unit a difference of two figures reads in: points for two
    percentages, else the figures' own unit."""
    return "percentage_points" if unit in _PERCENT_UNITS else unit


def _difference(later, earlier, signed=True):
    """later minus earlier, where both are numbers in one unit."""
    high, low = _number(later), _number(earlier)
    if high is None or low is None or later.get("unit") != earlier.get(
            "unit"):
        return _words(NOT_CALCULABLE)
    return _calc(high - low, _difference_unit(later.get("unit")),
                 "%s - %s" % (later.get("value"), earlier.get("value")),
                 signed)


def _ratio(top, bottom, less_one=False):
    """top over bottom as a percentage (less one hundred for a change),
    where both are numbers in one unit and the bottom is not zero."""
    high, low = _number(top), _number(bottom)
    if (high is None or low is None or low == 0
            or top.get("unit") != bottom.get("unit")):
        return _words(NOT_CALCULABLE)
    with decimal.localcontext() as context:
        context.prec = 28
        value = high / low * 100 - (100 if less_one else 0)
    return _calc(value, "percent", "%s / %s" % (top.get("value"),
                                                bottom.get("value")),
                 signed=less_one)


def _share_text(value):
    """A share on the owner's pages (AC16(4)): a percentage to one
    decimal; a share that is not zero but too small to show at one
    decimal reads as less than a tenth of a percent."""
    shown = value.quantize(decimal.Decimal("0.1"),
                           rounding=decimal.ROUND_HALF_UP)
    if value and not shown:
        return "<0.1%" if value > 0 else ">-0.1%"
    return _format_number(str(abs(shown) if shown == 0 else shown),
                          "percent")


def _fact_text(cell):
    """A recorded fact in the market form; a recorded share as a share
    reads (its value as a percentage, carried on the cell)."""
    if "share" in cell:
        return _share_text(cell["share"])
    fact = cell["fact"]
    return _format_number(fact.get("value"), fact.get("unit"))


def cell_text(cell):
    """The words a cell shows, before either printer escapes them - the
    one reading both pages share."""
    kind = cell["kind"]
    if kind == "fact":
        return _fact_text(cell) + cell["stale"]
    if kind == "calc":
        value = cell["value"]
        if cell.get("share"):
            return _share_text(value)
        if cell["unit"] in _PERCENT_UNITS + ("percentage_points",):
            value = value.quantize(decimal.Decimal("0.1"),
                                   rounding=decimal.ROUND_HALF_UP)
            value = abs(value) if value == 0 else value
        text = _format_number(str(value), cell["unit"])
        return "+" + text if cell["signed"] and value > 0 else text
    if kind == "reading":
        return "%s (%s)" % (_format_number(cell["value"], cell["unit"]),
                            _format_date(cell["date"]))
    return cell["text"]


def _base_and_suffix(fact_id):
    """An id without the member suffix it wears, and that suffix."""
    suffix = gate._id_suffix(fact_id)
    return (fact_id[:len(fact_id) - len(suffix)] if suffix else fact_id,
            suffix)


def _prior_year_partner(own, prior):
    """True where `prior` is `own`'s prior-year pair: '<x>_q' beside
    '<x>_prior_year_q', one member suffix on both."""
    own_base, own_suffix = _base_and_suffix(own)
    prior_base, prior_suffix = _base_and_suffix(prior)
    return (own_base.endswith(QUARTER_TAIL) and own_suffix == prior_suffix
            and prior_base == own_base[:-len(QUARTER_TAIL)]
            + PRIOR_YEAR_TAIL)


def _is_prior_year(fact_id):
    return _base_and_suffix(fact_id)[0].endswith(PRIOR_YEAR_TAIL)


def _headline_revenue(fact_id):
    """True where an id is the headline revenue figure, the firm total a
    line may cite when no one figure is shared by every line."""
    return _base_and_suffix(fact_id)[0] == HEADLINE_REVENUE


def earnings_facts(frame, line, facts):
    """(own, prior year, firm total, firm named) for one revenue line,
    told by the facts' names - the architect's design of the READ-B1
    audit (round 3, rule 1 ruled again at rounds 4 and 6), stated whole:
    - a fact `facts` records in a share's unit (a percent or a fraction,
      the share carrier's own test) is never a revenue candidate, for
      the firm total or the line's own;
    - the firm total is the one current fact every line of the frame
      cites (two lines or more), the shared denominator; failing that,
      the headline revenue id where the line cites it;
    - the line's own current revenue is the one current fact it cites
      that is not the firm total (where it cites several, the one whose
      year-ago partner it also cites); the firm total is the line's own
      only where the frame has one revenue line, and in a frame of
      several a line naming no current figure but the firm total says
      so (firm named);
    - the year-ago figure is the own id's '_prior_year_q' partner among
      the facts the line cites - never another pair's."""
    lines = frame.get("how_it_earns") or []
    cited = [fid for fid in line.get("facts") or [] if isinstance(fid, str)]
    current = [fid for fid in cited if not _is_prior_year(fid)
               and not _share_unit(facts.get(fid))]
    total = None
    if len(lines) >= 2:
        shared = [fid for fid in current
                  if all(fid in (other.get("facts") or []) for other in lines)]
        total = shared[0] if len(shared) == 1 else None
    if total is None:
        headline = [fid for fid in current if _headline_revenue(fid)]
        total = headline[0] if len(headline) == 1 else None
    own = [fid for fid in current if fid != total]
    if len(own) > 1:
        own = [fid for fid in own
               if any(_prior_year_partner(fid, other) for other in cited)]
    if not own and len(lines) == 1 and total is not None:
        own = [total]
    if len(own) != 1:
        firm = len(lines) >= 2 and not own and total in current
        return None, None, total, firm
    prior = [fid for fid in cited if _prior_year_partner(own[0], fid)]
    return own[0], (prior[0] if len(prior) == 1 else None), total, False


def _fraction_units():
    """The units the floors rule a plain fraction (owner ruling AC19's
    prose_figure_marks: 'share of the segment total' among them)."""
    return tuple((_floors().get("prose_figure_marks") or {}).get(
        "fraction_units") or ())


def _share_unit(fact):
    """True where a fact is recorded in a share's unit: a percent, or a
    unit the floors rule a plain fraction."""
    return (isinstance(fact, dict)
            and fact.get("unit") in _PERCENT_UNITS + _fraction_units())


def share_carrier(facts, line):
    """The fact carrying a line's share, found by id and unit: a fact the
    line cites, or one struck only from facts it cites, recorded in a
    percent or a fraction unit, whose recorded figure is the one the
    line writes as its share. None where no such fact exists - a figure
    in any other unit is never taken for a share, whatever its value."""
    cited = set(line.get("facts") or [])
    share = _one_line(line.get("share_of_period"))
    for fact_id, fact in facts.items():
        operands = [item.get("fact_id") for item in
                    (fact.get("derived") or {}).get("operands") or []]
        if ((fact_id in cited or (operands and set(operands) <= cited))
                and _share_unit(fact)
                and _number(fact) is not None
                and _one_line(fact.get("value")) == share):
            return fact
    return None


def _share_cell(pack, facts, carrier):
    """A recorded share as a cell, its value read as a percentage."""
    cell = _fact_cell(pack, facts, carrier.get("id"))
    value = _number(carrier)
    cell["share"] = (value if carrier.get("unit") in _PERCENT_UNITS
                     else value * 100)
    return cell


def earnings_rows(pack, frame):
    """How it earns, line by line (the seed's design item 2): the line's
    short name (its words up to the first colon or semicolon, ruling 4),
    its kind of earnings where the frame says, its revenue in the market
    form, its share of the firm - read from its carrier where one exists,
    else struck here as its own revenue over the firm total - and its
    change on a year ago, struck here. The capture's whole sentence, and
    the facts it names, stand under the table."""
    facts = _facts_by_id(pack["capture"])
    lines = frame.get("how_it_earns") or []
    natured = any(line.get("nature") for line in lines)
    head = [name for name in EARNINGS_HEAD
            if natured or name != EARNINGS_HEAD[1]]
    rows, below, recorded = [], [], False
    for line in lines:
        own, prior, total, firm = earnings_facts(frame, line, facts)
        own_fact, prior_fact, total_fact = (facts.get(own), facts.get(prior),
                                            facts.get(total))
        carrier = None if firm else share_carrier(facts, line)
        if firm:
            revenue = _words(FIRM_TOTAL_NOT_OWN)
        elif own_fact is not None:
            revenue = _fact_cell(pack, facts, own)
        else:
            revenue = _words(NOT_CALCULABLE)
        if carrier is not None:
            share_cell = _share_cell(pack, facts, carrier)
            recorded = True
        elif own_fact is not None and total_fact is not None:
            share_cell = _ratio(own_fact, total_fact)
            if share_cell["kind"] == "calc":
                share_cell["share"] = True
        else:
            share_cell = _words(NOT_CALCULABLE)
        change = (_ratio(own_fact, prior_fact, less_one=True)
                  if own_fact is not None and prior_fact is not None
                  else _words(NOT_CALCULABLE))
        name = re.split(r"[:;]", _one_line(line.get("line")), maxsplit=1)[0]
        row = [_prose(name.strip())]
        if natured:
            nature = line.get("nature")
            row.append(_words(FI_NATURE_WORDS.get(nature)
                              or GROWER_NATURE_WORDS.get(nature)
                              or PRODUCER_NATURE_WORDS.get(nature)
                              or nature or "not stated"))
        rows.append(row + [revenue, share_cell, change])
        below.append([_prose(line.get("line")), _words(
            "(from: %s)" % "; ".join(_plain_name(facts, fid)
                                      for fid in line.get("facts") or []))])
    if recorded:
        head[head.index(EARNINGS_HEAD[3])] = EARNINGS_SHARE_RECORDED
    return {"head": head, "rows": rows, "below": below}


def _plain_name(facts, fact_id):
    """A fact's name before any escaping: its label, else its id read as
    words, as every reference in the document reads it (unit READ-B2)."""
    fact = facts.get(fact_id) if isinstance(fact_id, str) else None
    if fact is None:
        return "%s (not in the pack)" % _one_line(fact_id)
    return _one_line(fact.get("label")) or _id_words(fact_id)


def _metric_name(facts, fact_id, metric):
    """A guided metric's name: its first guide's label after the label's
    first colon (a label "First guide for the year: adjusted expense"
    reads "Adjusted expense"), else the metric in the id read as words."""
    label = _one_line((facts.get(fact_id) or {}).get("label"))
    name = (label.split(":", 1)[1].strip() if ":" in label
            else metric.replace("_", " "))
    return name[:1].upper() + name[1:]


def guidance_rows(pack, frame):
    """Guidance, one table per period row the frame carries (the seed's
    design item 3; owner ruling AC30(6)): a row per guided metric in the
    ruled 'guided_<metric>_<period>' shape; its first guide; each dated
    revision in its column, placed by the ruled
    'guidance_revised_<metric>_<period>[_rN]' shape; what was delivered,
    found by the gate's own prefix swap wherever the pack carries it;
    then delivered minus the first guide, signed, in the metric's unit
    (ruling 5: no word says beat or miss). An id that fits no family is
    printed in a trailing "Other" row, never dropped."""
    facts = _facts_by_id(pack["capture"])
    tables = []
    for row in (frame.get("management") or {}).get(
            "guidance_vs_delivery") or []:
        period = _one_line(row.get("period"))
        tail = "_" + gate.period_slug(period)
        revisions = row.get("revisions")
        dated = [item for item in revisions or [] if isinstance(item, dict)]
        width = 1 + len(dated) + 1   # first guide, revisions, delivered
        metrics, others, partners = [], [], []
        for fid in row.get("guided") or []:
            base, _suffix = _base_and_suffix(str(fid))
            body = base[len(gate._GUIDED_PREFIX):]
            if (base.startswith(gate._GUIDED_PREFIX) and tail != "_"
                    and body.endswith(tail) and len(body) > len(tail)):
                metrics.append([fid, body[:-len(tail)],
                                [None] * width])
                metrics[-1][2][0] = fid
            else:
                others.append((0, fid))
        for column, revision in enumerate(dated, start=1):
            for fid in revision.get("guided") or []:
                bare, _ordinal = gate._revision_ordinal(
                    _base_and_suffix(str(fid))[0])
                body = bare[len(gate._REVISED_PREFIX):]
                home = [entry for entry in metrics
                        if bare.startswith(gate._REVISED_PREFIX)
                        and body == entry[1] + tail
                        and entry[2][column] is None]
                if home:
                    home[0][2][column] = fid
                else:
                    others.append((column, fid))
        for entry in metrics:
            partner = (gate._DELIVERED_PREFIX
                       + str(entry[0])[len(gate._GUIDED_PREFIX):])
            partners.append(partner)
            entry[2][-1] = partner
        declared = row.get("delivered")
        if declared and declared not in partners:
            others.append((width - 1, declared))
        head = list(GUIDANCE_HEAD) + [
            GUIDANCE_REVISED % _format_date(item.get("date"))
            for item in dated] + list(GUIDANCE_TAIL)
        rows = []
        for fid, metric, cells in metrics:
            first, delivered = facts.get(fid), facts.get(cells[-1])
            shown = [_fact_cell(pack, facts, item) if item else
                     _words(NO_FIGURE) for item in cells[:-1]]
            if delivered is None:
                shown += [_words(NOT_REPORTED), _words(NO_FIGURE)]
            else:
                shown += [_fact_cell(pack, facts, cells[-1]),
                          _difference(delivered, first) if first
                          else _words(NOT_CALCULABLE)]
            rows.append([_words(_metric_name(facts, fid, metric))] + shown)
        for column, fid in others:
            cells = [_words(NO_FIGURE)] * (width + 1)
            cells[column] = _fact_cell(pack, facts, fid)
            rows.append([_words(GUIDANCE_OTHER % _plain_name(facts, fid))]
                        + cells)
        below = []
        if isinstance(revisions, list) and not dated:
            below.append([_words("The guidance for %s was %s."
                                 % (period, FI_NEVER_REVISED))])
        tables.append({"period": period, "head": head, "rows": rows,
                       "below": below})
    return tables


def capital_rows(pack, frame):
    """Capital beside its requirement (the seed's design item 4): one row
    per ratio and the requirement for that ratio, the cushion between them
    in points, struck here; two pairs with the same figures are two facts
    and both stay (ruling 6). The capture's regime, binding constraint
    and management's own target stand under the table. None where the
    frame declares the gap instead."""
    capital = frame.get("fi_capital") or {}
    if capital.get("gap"):
        return None
    facts = _facts_by_id(pack["capture"])
    rows = []
    for ratio, requirement in fi_capital_pairs(capital):
        cushion = (_difference(facts.get(ratio), facts.get(requirement),
                               signed=False)
                   if ratio in facts and requirement in facts
                   and facts[ratio].get("unit") in _PERCENT_UNITS
                   else _words(NOT_CALCULABLE))
        rows.append([
            _words(_plain_name(facts, ratio)) if ratio
            else _words("no ratio named"),
            _fact_cell(pack, facts, ratio) if ratio else _words(NO_FIGURE),
            _words(_plain_name(facts, requirement)) if requirement
            else _words("no requirement named"),
            _fact_cell(pack, facts, requirement) if requirement
            else _words(NO_FIGURE),
            cushion if ratio and requirement else _words(NO_FIGURE)])
    below = [[_words("%s:" % label), _prose(capital[key])]
             for label, key in (("The regime", "regime"),
                                ("The binding constraint",
                                 "binding_constraint"))
             if capital.get(key)]
    if capital.get("target_fact"):
        below.append([_words("Management's own target: %s:"
                             % _plain_name(facts, capital["target_fact"])),
                      _fact_cell(pack, facts, capital["target_fact"])])
    return {"head": list(CAPITAL_HEAD), "rows": rows, "below": below}


def _dated_row(pack, facts, fact_id):
    return [_words(_plain_name(facts, fact_id)),
            _fact_cell(pack, facts, fact_id),
            _words(_format_date((facts.get(fact_id) or {}).get("as_of"))
                   or NO_FIGURE)]


def stress_rows(pack, ticker):
    """The regulator's own bad year (the seed's design item 5; owner ruling
    AC30(5)): this frame's own stress facts in capture order, each by its
    label, value and date, and each declared stress gap by its reason.
    None where there is neither."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    stress, gaps = fi_stress_evidence(capture, ticker)
    if not stress and not gaps:
        return None
    order = [fact.get("id") for fact in capture.get("tier1") or []
             if fact.get("id") in stress]
    rows = [_dated_row(pack, facts, fid) for fid in order]
    rows += [[_words("Declared gap (%s)" % _one_line(gap.get("fact_class"))),
              _words(gap.get("reason")), _words(NO_FIGURE)] for gap in gaps]
    return {"head": list(STRESS_HEAD), "rows": rows, "below": []}


def risk_rows(pack, frame):
    """The risk-cost line (the seed's design item 5): each fact the line
    names by its label, value and date, a '_prior_year_q' fact beside its
    partner in one row, and one whose partner the line does not name in
    the year-ago column with no latest figure. The capture's reason is
    printed with the line's heading. None where the line names no
    fact."""
    facts = _facts_by_id(pack["capture"])
    named = [fid for fid in (frame.get("fi_risk_cost") or {}).get("facts")
             or [] if isinstance(fid, str)]
    if not named:
        return None
    paired = {prior: own for own in named for prior in named
              if _prior_year_partner(own, prior)}
    rows = []
    for fid in named:
        if fid in paired:
            continue
        row = _dated_row(pack, facts, fid)
        if _is_prior_year(fid):
            row.insert(1, _words(NO_FIGURE))
        else:
            prior = [item for item, own in paired.items() if own == fid]
            row.insert(2, _fact_cell(pack, facts, prior[0]) if prior
                       else _words(NO_FIGURE))
        rows.append(row)
    return {"head": list(RISK_HEAD), "rows": rows, "below": []}


def _grower_numerator(frame):
    """The id the growth yardstick's numerator carries, as the floors'
    row for the frame's sub-type names it."""
    row = ((((_floors().get("archetype_measures") or {}).get("table") or {})
            .get(GROWER_ARCHETYPE) or {}).get("subtypes") or {}).get(
                frame.get("grower_subtype")) or {}
    return row.get("subject_numerator") or "enterprise_value"


def _grower_gross_profit(capture):
    """The gross-profit denominator the rating row divides by (the
    continuing business's on a model transition), else the floors' id."""
    for fact_id in _rating_subject_denominators(capture):
        if isinstance(fact_id, str) and fact_id.startswith("gross_profit_"):
            return fact_id
    return "gross_profit_ttm"


def _multiple(top, bottom):
    """top over bottom as a multiple, where both are numbers in one unit
    and the bottom is not zero."""
    high, low = _number(top), _number(bottom)
    if (high is None or low is None or low == 0
            or top.get("unit") != bottom.get("unit")):
        return _words(NOT_CALCULABLE)
    with decimal.localcontext() as context:
        context.prec = 28
        value = high / low
    return _calc(value, "x", "%s / %s" % (top.get("value"),
                                          bottom.get("value")))


def _labelled(label, cell, how):
    return [_words(label), cell, _words(how)]


def _id_cell(pack, facts, fact_id):
    """A fact the grower's tables show, carrying the id it was asked for,
    so the seats' case file can name it only where it is a tier-1 id of
    this pack (P-U3e-3); the pages ignore the id."""
    cell = _fact_cell(pack, facts, fact_id)
    cell["id"] = (cell.get("fact") or {}).get("id", fact_id)
    return cell


GROWER_MONTHS_ROW = "Months of cash left"


def grower_yardstick_rows(pack, frame):
    """The growth yardstick and what stands beside it (owner rulings
    AC50 (5), (6) and (9)): enterprise value over the last four quarters'
    gross profit beside the latest quarter's sales growth, stock-based pay
    as a share of sales and the growth in the diluted share count - each
    struck here from the recorded figures and marked calculated - then
    annual recurring revenue where the pack carries it, and whatever the
    company guides, shown beside and never rated on. Evidence only."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    numerator, gross = _grower_numerator(frame), _grower_gross_profit(capture)
    revenue, prior = (facts.get(fid) for fid in GROWER_REVENUE_PAIR)
    shares, shares_prior = (facts.get(fid) for fid in GROWER_SHARES_PAIR)
    stock_pay = facts.get(GROWER_STOCK_PAY)
    growth = (_ratio(revenue, prior, less_one=True)
              if revenue is not None and prior is not None
              else _words(NOT_CALCULABLE))
    pay = (_ratio(stock_pay, revenue)
           if stock_pay is not None and revenue is not None
           else _words(NOT_CALCULABLE))
    if pay["kind"] == "calc":
        pay["share"] = True
    dilution = (_ratio(shares, shares_prior, less_one=True)
                if shares is not None and shares_prior is not None
                else _words(NOT_CALCULABLE))
    rows = [
        _labelled(_plain_name(facts, numerator),
                  _id_cell(pack, facts, numerator), RECORDED),
        _labelled(_plain_name(facts, gross), _id_cell(pack, facts, gross),
                  RECORDED),
        _labelled("Enterprise value against gross profit, the last four "
                  "quarters", _multiple(facts.get(numerator), facts.get(gross))
                  if numerator in facts and gross in facts
                  else _words(NOT_CALCULABLE), CALCULATED),
        _labelled("Sales growth, the latest quarter against the same "
                  "quarter a year ago", growth, CALCULATED),
        _labelled("Stock-based pay as a share of sales, the latest quarter",
                  pay, CALCULATED),
        _labelled("Growth in the diluted share count against a year ago",
                  dilution, CALCULATED)]
    order = [fact.get("id") for fact in capture.get("tier1") or []
             if isinstance(fact.get("id"), str)]
    for fact_id in order:
        if fact_id.startswith(GROWER_ARR_PREFIX) and not _is_prior_year(
                fact_id):
            rows.append(_labelled(_plain_name(facts, fact_id),
                                  _id_cell(pack, facts, fact_id), RECORDED))
            partner = [other for other in order
                       if _prior_year_partner(fact_id, other)]
            if partner:
                rows.append(_labelled(
                    "Annual recurring revenue growth against a year ago",
                    _ratio(facts[fact_id], facts[partner[0]], less_one=True),
                    CALCULATED))
    for fact_id in order:
        if fact_id.startswith(GROWER_GUIDED_PREFIX):
            rows.append(_labelled(_plain_name(facts, fact_id),
                                  _id_cell(pack, facts, fact_id),
                                  GROWER_GUIDED))
    return {"head": list(YARDSTICK_HEAD), "rows": rows, "below": []}


def grower_quarters(capture, prefixes=GROWER_QUARTER_PREFIXES, suffix=None):
    """The period endings of the latest quarters the pack carries under
    the grower's quarterly prefixes (or `prefixes`), oldest first, as many
    as the floors' rule reads (owner ruling AC50(1)); a half-year
    reporter's halves stand in their place. Placed by the sufficiency
    gate's own reading of a period; an ending it cannot place is not
    shown. On a model transition the continuing business's quarters (the
    id ending in the rule's own continuing suffix, unless `suffix` names
    one) stand as rows of their own, each after the whole business's row
    for the same period (audit finding r1-2)."""
    floors = _floors()
    count = ((floors.get("archetype_measures") or {}).get(
        "profitability_rule") or {}).get("quarters")
    if suffix is None:
        suffix = sufficiency._continuing_profit_suffix(
            floors, sufficiency._declared_archetype(floors, capture), capture)
    places = {}
    for fact in capture.get("tier1") or []:
        fact_id = fact.get("id")
        for prefix in prefixes:
            if isinstance(fact_id, str) and fact_id.startswith(prefix):
                slug = fact_id[len(prefix):]
                period = (slug[:-len(suffix)] if suffix
                          and slug.endswith(suffix) else slug)
                place = sufficiency._period_place(period)
                if place is not None:
                    places[slug] = (place, period != slug)
    latest = sorted({place for place, _ in places.values()})
    latest = set(latest[-count:] if count else latest)
    return sorted((slug for slug in places if places[slug][0] in latest),
                  key=lambda slug: places[slug])


def grower_quarter_rows(pack, frame):
    """Sales, gross profit and operating profit for each of the latest
    quarters, one row each, oldest to newest - the recorded figures, as
    the pack carries them."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    rows = [[_words(" ".join(slug.split("_")).upper())]
            + [_id_cell(pack, facts, prefix + slug)
               for prefix in GROWER_QUARTER_PREFIXES]
            for slug in grower_quarters(capture)]
    return {"head": list(QUARTERS_HEAD), "rows": rows, "below": []}


def grower_runway_rows(pack, frame, runway):
    """What the months of cash left are counted from (owner ruling
    AC50(7)): each cash fact, the last four quarters' operating cash flow
    and capital spending, the burn and the months as the one helper works
    them out, the ruled line, and each undrawn credit line, shown and not
    counted; the capture's own funding reason under the table."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    block = frame.get("growth_runway")
    block = block if isinstance(block, dict) else {}
    rows = [_labelled(_plain_name(facts, fid), _id_cell(pack, facts, fid),
                      "counted")
            for fid in block.get("cash_facts") or []]
    flows = [block.get(key) for key in ("operating_cash_flow_fact",
                                        "capital_expenditure_fact")]
    rows += [_labelled(_plain_name(facts, fid), _id_cell(pack, facts, fid),
                       "counted in the burn") for fid in flows]
    if runway is None:
        burn = _words(NOT_CALCULABLE)
    elif runway.get("burn") is None:
        burn = _words(GROWER_NOT_BURNING)
    else:
        burn = _calc(runway["burn"], (facts.get(flows[0]) or {}).get("unit"),
                     "capital spending less operating cash flow")
    months = (_words(NOT_CALCULABLE) if runway is None
              else _words(GROWER_NOT_BURNING) if runway.get("burn") is None
              else _words("%s months" % runway["months"]))
    rows.append(_labelled("The cash burn, the last four quarters", burn,
                          CALCULATED))
    rows.append(_labelled(GROWER_MONTHS_ROW, months, CALCULATED))
    threshold = ((_floors().get("archetype_measures") or {}).get(
        "growth_runway") or {}).get("threshold_months")
    rows.append(_labelled("The line the owner ruled",
                          _words("%s months" % threshold),
                          "owner ruling AC50(7)"))
    rows += [_labelled(_plain_name(facts, fid), _id_cell(pack, facts, fid),
                       GROWER_NOT_COUNTED)
             for fid in block.get("undrawn_facility_facts") or []]
    below = ([[_words("How it funds itself, in the capture's words:"),
               _prose(block["funding_because"])]]
             if block.get("funding_because") else [])
    return {"head": list(RUNWAY_HEAD), "rows": rows, "below": below}


def grower_facts_read(capture, frame):
    """Every fact id a growth company's lines read: the ids its three
    tables show and the recorded figures its calculated rows are struck
    from - so a corrected one brings the frame into a delta re-audit
    (audit finding r1-3)."""
    pack = {"capture": capture}
    ids = set(GROWER_REVENUE_PAIR + GROWER_SHARES_PAIR + (GROWER_STOCK_PAY,))
    ids.update(fact.get("id") for fact in capture.get("tier1") or []
               if isinstance(fact.get("id"), str)
               and fact["id"].startswith(GROWER_ARR_PREFIX))
    for table in (grower_yardstick_rows(pack, frame),
                  grower_quarter_rows(pack, frame),
                  grower_runway_rows(pack, frame, grower_runway(pack))):
        for row in table["rows"]:
            ids.update(cell["id"] for cell in row
                       if isinstance(cell, dict) and "id" in cell)
    return ids


# ------------------------------------------------ the producer's tables
# Owner rulings AC51-AC56 (RESOURCE-ARCHETYPE (c)); the architect's lesson of
# sub-charge (b): every table below is a CLASS over the facts the producer
# rule reads - the families the floors name for each resource-block field,
# every reported reserve by the rule's own reading of the reserve prefix - and
# the one helper's worked-out figures (resource_readings). No list of ids.

# The reserve categories a reserve id names, read after the reserve prefix.
RESERVE_CATEGORY_WORDS = {
    "proved": "Proved reserves",
    "probable": "Probable reserves",
    "pp": "Proven and probable reserves",
}


def _name_cell(facts, fact_id, name=None):
    """A row's first cell naming a fact: its plain name (or `name`), carrying
    the id so the seats' case file prints the fact rather than the words."""
    cell = _words(name or _plain_name(facts, fact_id))
    cell["name_of"] = fact_id
    return cell


def _named(pack, facts, fact_id, how):
    return [_name_cell(facts, fact_id), _id_cell(pack, facts, fact_id),
            _words(how)]


def _ids_cell(pack, facts, fact_ids):
    """One cell showing every fact in `fact_ids`, carrying their ids."""
    if len(fact_ids) == 1:
        return _id_cell(pack, facts, fact_ids[0])
    if not fact_ids:
        return _words("not in the pack")
    cell = _words("; ".join(cell_text(_fact_cell(pack, facts, fid))
                            for fid in fact_ids))
    cell["ids"] = list(fact_ids)
    return cell


def _commodities(frame):
    """Every commodity a fact id may name: the floors' product list and the
    frame's own by-products."""
    products = set((_floors().get("archetype_measures") or {}).get(
        "resource_products") or {})
    return sorted(products | {extra for extra in _resource_block(frame).get(
        "by_products") or () if isinstance(extra, str)})


def _naming(fact_id, names):
    return sufficiency.resource_product_names(fact_id, names)


def _reserve_name(facts, fact_id, names, extras):
    """A reserve row's name: the fact's own label, else the category and
    the commodity its id names, else its id in words - and, for a
    by-product, that it is shown apart and not rated on (owner rulings
    AC52(R6) and AC56(1))."""
    tokens = fact_id[len(_resource_rule().get("reserve_prefix") or ""):]
    category = next((words for token, words in RESERVE_CATEGORY_WORDS.items()
                     if "_%s_" % token in "_%s_" % tokens), None)
    named = _naming(fact_id, names)
    if _one_line((facts.get(fact_id) or {}).get("label")) or not category:
        name = _plain_name(facts, fact_id)
    else:
        name = "%s%s" % (category, (", %s" % (
            PRODUCT_WORDS.get(named[0]) or named[0].replace("_", " ")))
            if named else "")
    return name + (BY_PRODUCT_WORDS if set(named) & set(extras) else "")


def producer_reserve_rows(pack, frame):
    """The reserves (owner rulings AC52(R6)-(R7), AC53(R9), AC56(1)): one row
    per reported reserve the pack carries - every tier-1 fact the producer
    rule reads as a reserve, the rated figure, each other category, oil and
    gas apart and every by-product - never summed; each with the standard,
    its own fact's date, the price it was counted at and today's price beside.
    A row naming another commodity reads that commodity's own prices; a row
    naming none, or the main product, reads the prices the resource block
    cites - the ones the producer rule reads (audit round 1, r1-1: an
    uncited price is never shown as the main product's). Where today's
    price is in another unit than the price the reserves were counted at,
    the two are not compared."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    block = _resource_block(frame)
    order = _tier1_ids(capture)
    names = _commodities(frame)
    standard = block.get("reserves_standard")
    standard = (_words(RESERVES_STANDARD_WORDS[standard])
                if standard in RESERVES_STANDARD_WORDS
                else _prose(standard or "not stated"))

    def own(field, fact_id):
        return sufficiency.resource_reserve_prices(_floors(), frame, facts, fact_id, field)

    rows = []
    for fact_id in sufficiency._reserve_ids(_resource_rule(), order):
        counted = own("reserve_price_facts", fact_id)
        today = own("reference_price_fact", fact_id)
        counted_cell = _ids_cell(pack, facts, counted)
        units = {(facts.get(fid) or {}).get("unit") for fid in counted}
        if today and counted and units != {(facts.get(fid) or {}).get(
                "unit") for fid in today}:
            today_cell = _words(NOT_COMPARABLE)
        else:
            today_cell = _ids_cell(pack, facts, today)
        rows.append([_name_cell(facts, fact_id, _reserve_name(
            facts, fact_id, names, block.get("by_products") or ())),
                     _id_cell(pack, facts, fact_id), standard,
                     dict(_words(_format_date(facts[fact_id].get("as_of"))),
                          date_of=fact_id),
                     counted_cell, today_cell])
    # The architect's ruling on P-RESOURCEc-4 (AC56(1)): each by-product's
    # output on a row of its own beside its reserves, in its own unit; every
    # by-product row carries its marking for the seats' case file too.
    extras = {extra for extra in block.get("by_products") or ()
              if isinstance(extra, str)}
    rows += [[_name_cell(facts, fid, _plain_name(facts, fid)
                         + BY_PRODUCT_WORDS), _id_cell(pack, facts, fid)]
             + [_words("")] * (len(RESERVES_HEAD) - 2) for fid in order
             if fid.startswith(sufficiency._PRODUCER_OUTPUT_PREFIX)
             and set(_naming(fid, names)) & extras]
    for row in rows:
        if set(_naming(row[0]["name_of"], names)) & extras:
            row[0]["note"] = BY_PRODUCT_WORDS[3:]
    return {"head": list(RESERVES_HEAD), "rows": rows, "below": []}


def _producer_roles(capture, frame):
    """The yardstick's numerator id and its denominators by role, as the
    floors' row for the frame's sub-type and the rating row name them."""
    row = ((((_floors().get("archetype_measures") or {}).get("table") or {})
            .get(PRODUCER_ARCHETYPE) or {}).get("subtypes") or {}).get(
                frame.get("producer_subtype")) or {}
    return (row.get("subject_numerator") or "enterprise_value",
            dict(zip(row.get("denominator_roles") or (),
                     _rating_subject_denominators(capture))))


def _per_unit_money(per_unit, unit):
    """The value per unit of reserves through the AC16 money formatter, in
    whole currency where the enterprise value's unit is a scaled currency
    (the architect's ruling on P-RESOURCEc-1): $14.1M over a million
    barrels and $14,100 over a thousand print the same money as the one
    figure recorded in plain dollars."""
    from council.report import render_report
    money = render_report._money_parse(unit) if isinstance(unit, str) else None
    if money and not money[2]:
        whole = (per_unit * money[1]).normalize()
        return _format_number(format(whole, "f"), unit.split("_")[0])
    return _format_number(format(per_unit, "f"), unit)


def producer_yardstick_rows(pack, frame, readings):
    """The producer's yardstick (owner rulings AC52(R5), AC53(R10), AC54(R13)):
    enterprise value, the reserves it is divided by and the value per unit
    of reserves as the one helper works it out, in the enterprise value's
    unit per unit of the commodity; the last four quarters' operating cash
    flow and what the market pays for it - "negative, not a multiple" where
    the cash is negative; today's price; and, where carried, the SEC's
    standardized measure, shown beside and never the denominator. Evidence
    only."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    numerator, roles = _producer_roles(capture, frame)
    cash = roles.get("cash_flow")
    per_unit = (readings or {}).get("value_per_unit")
    unit = (readings or {}).get("unit")
    unit_words = PER_UNIT_WORDS.get(unit) or _unit_words(unit or "unit")
    value = (_words(_per_unit_money(per_unit, (facts.get(numerator) or {})
                                    .get("unit")))
             if per_unit is not None else _words(NOT_CALCULABLE))
    negative = (readings or {}).get("cash_flow_negative")
    if negative is None and cash in facts:
        negative = (_number(facts[cash]) or 0) < 0
    multiple = (_words(NEGATIVE_CASH) if negative
                else _multiple(facts.get(numerator), facts.get(cash))
                if numerator in facts and cash in facts
                else _words(NOT_CALCULABLE))
    rows = [_named(pack, facts, numerator, RECORDED)]
    if roles.get("reserves"):
        rows.append(_named(pack, facts, roles["reserves"], RECORDED))
    rows.append(_labelled("Enterprise value per %s of reserves" % unit_words,
                          value, CALCULATED))
    if cash:
        rows.append(_named(pack, facts, cash, RECORDED))
    rows.append(_labelled("Enterprise value against the last four quarters' "
                          "operating cash flow", multiple, CALCULATED))
    rows += [_named(pack, facts, fid, RECORDED)
             for fid in _family_ids(pack, frame, "reference_price_fact")]
    if PRODUCER_STANDARDIZED in facts:
        rows.append(_named(pack, facts, PRODUCER_STANDARDIZED,
                           PRODUCER_BESIDE))
    return {"head": list(YARDSTICK_HEAD), "rows": rows, "below": []}


def _family_ids(pack, frame, field):
    """Every tier-1 fact of the family the producer rule reads `field` by,
    in the pack's order - the block's own cited facts among them - or, for
    today's price, the block's one fact."""
    block = _resource_block(frame)
    if field == "reference_price_fact":
        cited = block.get(field)
        return [cited] if isinstance(cited, str) else []
    prefixes = _family(field, frame.get("producer_subtype"))
    return [fid for fid in _tier1_ids(pack["capture"])
            if prefixes and fid.startswith(prefixes)]


def producer_quarter_rows(pack, frame):
    """Output and the price received for each of the latest quarters,
    oldest to newest, then the latest quarter beside the same quarter a
    year ago and the change between them (owner rulings AC53(R10) and
    AC54(R16)). The members are the whole business's, as the producer rule
    reads them."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    rows = [[_words(" ".join(slug.split("_")).upper())]
            + [_id_cell(pack, facts, prefix + slug)
               for prefix in PRODUCER_QUARTER_PREFIXES]
            for slug in grower_quarters(capture, PRODUCER_QUARTER_PREFIXES,
                                        "")]
    pairs = PRODUCER_LATEST_PAIRS
    rows.append([_words("The latest quarter")]
                + [_id_cell(pack, facts, now) for now, _ in pairs])
    rows.append([_words("The same quarter a year ago")]
                + [_id_cell(pack, facts, then) for _, then in pairs])
    rows.append([_words("Change on a year ago (%s)" % CALCULATED)] + [
        _ratio(facts[now], facts[then], less_one=True)
        if now in facts and then in facts else _words(NOT_CALCULABLE)
        for now, then in pairs])
    return {"head": list(PRODUCER_QUARTERS_HEAD), "rows": rows, "below": []}


def producer_cost_rows(pack, frame):
    """What each unit costs, in the words each fact carries - for a royalty
    or streaming company every stream payment it cites (owner rulings
    AC54(R14), AC56(2)); each hedge, shown and never netted, beside today's
    price, or none where the company does not hedge (AC53(R11)); and the
    debt, the cash and the clean-up obligations (AC54(R16))."""
    capture = pack["capture"]
    facts = _facts_by_id(capture)
    rows = [_named(pack, facts, fid, RECORDED)
            for fid in _family_ids(pack, frame, "unit_cost_facts")]
    if _resource_block(frame).get("hedge_none_by_design"):
        rows.append(_labelled("Hedges", _words(PRODUCER_NO_HEDGE), RECORDED))
    rows += [_named(pack, facts, fid, PRODUCER_NOT_NETTED)
             for fid in _family_ids(pack, frame, "hedge_facts")]
    rows += [_named(pack, facts, fid, RECORDED)
             for fid in _family_ids(pack, frame, "reference_price_fact")]
    rows += [_named(pack, facts, fid, RECORDED)
             for fid in PRODUCER_BALANCE_IDS if fid in facts]
    return {"head": list(RUNWAY_HEAD), "rows": rows, "below": []}


PRODUCER_LEADS = (
    "The reserves, each beside the price the reserves were counted at and "
    "today's price",
    "The yardstick, and what stands beside it",
    "Output and the price received, the latest quarters oldest first",
    "What each unit costs, the hedges, the debt and the clean-up "
    "obligations")


def producer_tables(pack, frame, readings):
    """The producer's four tables with their leads, in page order - built
    once here, printed by the full document, the report and the case
    file."""
    return list(zip(PRODUCER_LEADS, (
        producer_reserve_rows(pack, frame),
        producer_yardstick_rows(pack, frame, readings),
        producer_quarter_rows(pack, frame),
        producer_cost_rows(pack, frame))))


def producer_facts_read(capture, frame):
    """Every fact id a producer's lines read: every fact the resource block
    cites, every fact its tables show and every figure a calculated row is
    struck from - so a corrected price or hedge brings the frame into a
    delta re-audit."""
    pack = {"capture": capture}
    ids = {fid for pair in PRODUCER_LATEST_PAIRS for fid in pair}
    for field, named in _resource_block(frame).items():
        named = [named] if isinstance(named, str) else named
        if field.endswith(("_fact", "_facts")) and isinstance(named, list):
            ids.update(fid for fid in named if isinstance(fid, str))
    for _, table in producer_tables(pack, frame, producer_readings(pack)):
        for row in table["rows"]:
            for cell in row:
                ids.update(cell.get("ids") or ())
                ids.update(cell[key] for key in ("id", "name_of")
                           if key in cell)
    ids.update(_producer_roles(capture, frame)[1].values())
    return ids


def _series_names():
    """The plain names of the cycle series on record, as data (ruling 7:
    the report's glossary map, loaded when first used)."""
    from council.report import render_report
    return render_report.GLOSSARY.get("series") or {}


def cycle_rows(capture):
    """The cycle (the seed's design item 6; owner ruling AC15 P4): each
    series by its plain name (its id where the map has none), its first
    and latest point with their dates, and the change between them, in
    points for a percentage. None where the series are a declared gap or
    absent. No reading of the series."""
    cycle = capture.get("cycle") or {}
    series = cycle.get("series") or []
    if cycle.get("gap") or not series:
        return None
    names = _series_names()
    rows = []
    for item in series:
        points = item.get("points") or []
        name = _words(names.get(item.get("id")) or _one_line(item.get("id")))
        if not points:
            rows.append([name, _words("no points"), _words(NO_FIGURE),
                         _words(NO_FIGURE)])
            continue
        unit = item.get("unit")
        first, last = ({"value": point.get("value"), "unit": unit}
                       for point in (points[0], points[-1]))
        rows.append([name] + [
            {"kind": "reading", "value": point.get("value"), "unit": unit,
             "date": point.get("date")} for point in (points[0], points[-1])
        ] + [_difference(last, first)])
    return {"head": list(CYCLE_HEAD), "rows": rows, "below": []}


def _md_cell(cell, bases):
    """One cell for the Markdown document: the capture's words marked
    (AC19), everything else neutralised as data; a STALE mark raw, as the
    document prints it everywhere."""
    if cell["kind"] == "prose":
        return _marked(cell["text"], bases)
    if cell["kind"] == "fact":
        return _safe(_fact_text(cell)) + cell["stale"]
    return _safe(cell_text(cell))


def table_lines(table, bases):
    """A business table as Markdown: the pipe table, then each line under
    it as a list item."""
    lines = ["| %s |" % " | ".join(_safe(name) for name in table["head"]),
             "| %s |" % " | ".join("---" for _ in table["head"])]
    lines += ["| %s |" % " | ".join(_md_cell(cell, bases) for cell in row)
              for row in table["rows"]]
    if table["below"]:
        lines.append("")
        lines += ["- %s" % " ".join(_md_cell(cell, bases) for cell in line)
                  for line in table["below"]]
    return lines


CYCLE_DEPENDENCE_WORDS = {
    "identified": "a cycle is identified",
    "none": "no cycle this name depends on",
}


def _full_frame_lines(pack, capture):
    facts = _facts_by_id(capture)
    recorded = holding_display_facts(capture, recorded=True)
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
        # Owner ruling AC19: every number below is marked where the reader
        # who approves this sees it; the count stands only where a figure is
        # not traced (unit READ-B2).
        untraced = _untraced_sentence(capture, ticker, frame)
        if untraced:
            lines.append(untraced)
            lines.append("")
        archetype = frame.get("archetype")
        if archetype:
            measure = _rating_measure(capture)
            rated = ((" It is rated on %s."
                      % _MEASURE_WORDS.get(measure, _safe(measure)))
                     if measure else "")
            kind = (fi_kind_words(frame, _safe) if archetype == FI_ARCHETYPE
                    else grower_kind_words(frame, _safe)
                    if grower_subject_frame(capture) is frame
                    else producer_kind_words(frame, _safe)
                    if producer_subject_frame(capture) is frame
                    else _ARCHETYPE_WORDS.get(archetype, _safe(archetype)))
            lines.append("**Archetype.** %s.%s %s"
                         % (kind, rated,
                            _marked(frame.get("archetype_because"), bases)))
            if integrated_major_frame(capture) is frame:
                lines += ["", "%s%s" % (INTEGRATED_BESIDE_LEAD, _safe(
                    integrated_major_words(pack)))]
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
                             % "; ".join(_fact_ref(recorded, fid)
                                         for fid in denoms))
            lines.append("")
        lines.append("**What it does.** %s"
                     % _marked(frame.get("what_it_does"), bases))
        lines.append("")
        lines.append("**How it earns.**")
        if frame.get("how_it_earns"):
            # Unit READ-B1: one row per revenue line - its revenue, the
            # share of the firm and the change on a year ago struck here
            # from the recorded figures - and the capture's own sentence
            # under the table, with the facts it names.
            lines.append("")
            lines.extend(table_lines(earnings_rows(pack, frame), bases))
        if archetype == FI_ARCHETYPE:
            lines.extend(_full_fi_lines(pack, capture, ticker, frame,
                                        facts, bases))
        elif holding_subject_frame(capture) is frame:
            lines.extend(_full_nav_bridge_lines(pack, frame, facts, bases))
        elif grower_subject_frame(capture) is frame:
            lines.extend(_full_grower_lines(pack, frame, bases))
        elif producer_subject_frame(capture) is frame:
            lines.extend(_full_producer_lines(pack, frame, bases))
        changing = frame.get("what_is_changing") or {}
        lines.append("")
        lines.append("**What is changing.** %s%s"
                     % (_changing_opening(changing),
                        _marked(changing.get("statement"), bases)))
        reading = frame.get("headline_decline_read")
        if reading:
            lines.append("")
            lines.append("**A fallen headline figure:** %s (%s)"
                         % (_DECLINE_WORDS.get(reading.get("reading"))
                            or _safe(reading.get("reading")),
                            "; ".join(_fact_ref(recorded, fid)
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
                answer = "answered by " + "; ".join(
                    _figure(pack, facts, fid, passages)
                    for fid in row.get("answered_by") or [])
            lines.append("- %s: %s - %s"
                         % (_marked(row.get("name"), bases),
                            _marked(row.get("why_it_decides"), bases), answer))
        lines.extend(_full_peer_lines(frame, recorded, bases))
        lines.append("")
        guidance = guidance_rows(pack, frame)
        said = _management_words(pack, facts, frame, guidance=False)
        if guidance and said == MANAGEMENT_NOTHING:
            said = MANAGEMENT_GUIDANCE_ONLY
        lines.append("**Management.** %s" % said)
        lines.append("")
        for table in guidance:
            lines.append("**%s.**" % _safe(GUIDANCE_LEAD % table["period"]))
            lines.append("")
            lines.extend(table_lines(table, bases))
            lines.append("")
        standing = frame.get("competitive_position")
        passage = passages.get(standing)
        if passage is not None:
            lines.append("**Competitive standing.** %s From the passage "
                         "%s, in full below."
                         % (_safe(_first_sentence(passage.get("text"))),
                            _passage_title(standing)))
        else:
            lines.append("**Competitive standing.** %s is named, but the "
                         "passage is not in the pack." % _safe(standing))
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
                         % (CYCLE_DEPENDENCE_WORDS.get(cycle_dep)
                            or _safe(cycle_dep),
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
        # Unit READ-B1: one row per ratio and its requirement, the cushion
        # in points; the capture's regime and constraint under the table.
        lines.append("**Capital beside its requirement.**")
        lines.append("")
        lines.extend(table_lines(capital_rows(pack, frame), bases))
    stress = stress_rows(pack, ticker)
    if stress:
        # Owner ruling AC30(5): the supervisor's own stress figures, as
        # dated evidence - never a reading of them.
        lines.append("")
        lines.append("**%s.** Evidence only: the pack carries these and "
                     "nothing here reads them." % FI_STRESS_HEADING)
        lines.append("")
        lines.extend(table_lines(stress, bases))
    risk = frame.get("fi_risk_cost") or {}
    if risk:
        kind = risk.get("kind")
        table = risk_rows(pack, frame)
        lines.append("")
        lines.append("**The risk-cost line: %s.** %sWhy this line: %s"
                     % (FI_RISK_KIND_WORDS.get(kind) or _safe(kind),
                        "" if table else "no fact, by design. ",
                        _marked(risk.get("because"), bases)))
        if table:
            lines.append("")
            lines.extend(table_lines(table, bases))
    lines.extend(_full_nav_bridge_lines(pack, frame, facts, bases))
    return lines


def _full_nav_bridge_lines(pack, frame, facts, bases):
    """AC30(3), AC60: the bridge shared by both kinds of holding."""
    lines = []
    if holding_subject_frame(pack["capture"]) is frame:
        readings = holding_readings(pack)
        for lead, table in holding_tables(pack, frame, readings):
            lines += ["", "**%s.**" % lead, ""] + table_lines(table, bases)
        return lines + ["", FI_NOT_RATED_SENTENCE] + [
            _marked(sentence, bases) for sentence in holding_sentences(readings)]
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


def _full_grower_lines(pack, frame, bases):
    """What the full document shows of a growth company (owner rulings
    AC49(1) and AC50): the yardstick and what stands beside it, the
    latest quarters, and the months of cash left with, below the line,
    the ruled sentence. Evidence only: nothing here reads the figures."""
    runway = grower_runway(pack)
    lines = ["", "**The yardstick, and what stands beside it.** Evidence: "
             "the figures the pack carries, and those worked out from them "
             "marked calculated; nothing here reads them.", ""]
    lines.extend(table_lines(grower_yardstick_rows(pack, frame), bases))
    lines += ["", "**The latest quarters, oldest first.**", ""]
    lines.extend(table_lines(grower_quarter_rows(pack, frame), bases))
    lines += ["", "**The cash, and how long it lasts.** %s" % _safe(
        grower_months_line(runway)), ""]
    lines.extend(table_lines(grower_runway_rows(pack, frame, runway), bases))
    return lines


def _full_producer_lines(pack, frame, bases):
    """What the full document shows of a producer (owner rulings
    AC51-AC56): the reserves, the yardstick, output and the price received
    by quarter, and what each unit costs with the hedges, the debt and the
    clean-up obligations; the reserve life with, where today's price is
    below the reserves', the ruled sentence. Evidence only."""
    readings = producer_readings(pack)
    lines = ["", "**The producer's figures.** Evidence: the figures the pack "
             "carries, and those worked out from them marked calculated; "
             "nothing here reads them.", "",
             "**%s**" % _safe(producer_life_line(readings))]
    for lead, table in producer_tables(pack, frame, readings):
        lines += ["", "**%s.**" % _safe(lead), ""]
        lines.extend(table_lines(table, bases))
    return lines


def _full_cycle_lines(capture):
    """The cycle a single name depends on (owner ruling AC15, P4): the
    dated series carried as EVIDENCE, or the declared gap. Nothing here is
    computed from them - the seats read them as evidence, never a reading."""
    cycle = capture.get("cycle")
    if not cycle:
        return []
    lines = ["## The cycle this name depends on", "",
             "**%s.** %s" % (_safe(cycle.get("name")).rstrip("."),
                             _safe(cycle.get("why_it_matters"))), ""]
    gap = cycle.get("gap")
    if gap:
        lines.append("The dated series are a declared gap: %s"
                     % _safe(gap.get("reason")))
        lines.append("")
        return lines
    # Unit READ-B1: the series first and latest, in plain names, as one
    # table; every dated point of each follows under it.
    table = cycle_rows(capture)
    if table:
        lines.extend(table_lines(table, {}))
        lines.append("")
    names = _series_names()
    for series in cycle.get("series") or []:
        points = series.get("points") or []
        span = ("%s to %s" % (points[0]["date"], points[-1]["date"])
                if points else "no points")
        # Render-only (FI-ARCHETYPE (b)): the date the series was read
        # beside the date of its LAST point, so a reader sees how old the
        # latest reading is.
        lines.append("- **%s** (`%s`, %s, read %s; latest point %s): %d "
                     "dated points, %s. Source: %s. Re-fetch: %s"
                     % (_safe(names[series.get("id")])
                        if series.get("id") in names
                        else _words_of_id(series.get("id")),
                        _one_line(series.get("id")),
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
                        "; ".join(_fact_ref(facts, m)
                                  for m in peer.get("metrics") or [])))
        if peer.get("comparable_because"):
            lines.append("  - comparable because: %s"
                         % _marked(peer.get("comparable_because"), bases))
        if peer.get("not_comparable_on"):
            lines.append("  - not comparable on: %s"
                         % _marked(peer.get("not_comparable_on"), bases))
    return lines


# Unit READ-B2: a dealing an insider made is carried as three facts - its
# direction, its date and its size, sharing one suffix (owner ruling
# AC35(2)) - and the full document prints them as ONE table row, with the
# shares sold and bought summed beneath. A dealing whose three facts carry
# anything a row would not show (a bound, a period basis, a note of
# arithmetic, or an as-of date other than the dealing's own) keeps its
# three entries instead: a table never drops what an entry carried.
INSIDER_HEADING = "Insider dealings"
INSIDER_PARTS = (("direction", "insider_flow_direction_"),
                 ("date", "insider_flow_date_"),
                 ("size", "insider_flow_size_"))
INSIDER_TABLE_HEAD = ("| Entry | Date | The dealing | Direction | Shares "
                      "| Source |",
                      "| --- | --- | --- | --- | --- | --- |")
DIRECTION_WORDS = {"sell": "sale", "buy": "purchase"}
# The share-count units the insider floor permits (floors.json,
# insider_flow_size_), each as shares (audit round 1 of UPGRADE2-READ-B2).
SHARES_PER_UNIT = {"shares": 1, "thousand_shares": 1000,
                   "thousands_of_shares": 1000, "million_shares": 1000000}
INSIDER_KEY_NOTE = ("%s`insider_flow_direction_<n>`, `insider_flow_date_<n>`, "
                    "`insider_flow_size_<n>` - <n> as in the first column")


def _insider_dealings(capture, notes):
    """{suffix: {"direction": fact, "date": fact, "size": fact}} for every
    whole dealing the table can print without dropping anything."""
    parts = {}
    for fact in capture.get("tier1") or []:
        fact_id = str(fact.get("id") or "")
        for role, prefix in INSIDER_PARTS:
            if fact_id.startswith(prefix) and len(fact_id) > len(prefix):
                parts.setdefault(fact_id[len(prefix):], {})[role] = fact
    dealings = {}
    for suffix, trio in parts.items():
        if len(trio) != len(INSIDER_PARTS):
            continue
        day = _one_line(trio["date"].get("value"))
        if any(fact.get("bound") or fact.get("period_basis")
               or notes.get(fact.get("id"))
               or _one_line(fact.get("as_of")) != day
               for fact in trio.values()):
            continue
        dealings[suffix] = trio
    return dealings


def _distinct(values):
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


# Unit INSIDER-DEPTH (owner ruling AC41(1), as amended of record): where
# officers and directors together own under the floors' threshold, the
# section opens with the twelve-month summary in one plain line, and the
# table below lists only the dealings the pack carries.
SUMMARY_NET_WORDS = {"sell": "net sellers", "buy": "net buyers",
                     "even": "neither net buyers nor net sellers"}
OFFICERS_ONLY = ("Below, only the chief executive's, the finance chief's "
                 "and the chair's own dealings, because officers and "
                 "directors together own under %s%% of the company: %s.")
NO_OFFICER_DEALT = "None of the three dealt in the window."


def _insider_lead(pack, capture, insider, order):
    """The light depth's opening lines where the pack carries the whole
    twelve-month summary, else None - and None at every other depth, so
    the section is exactly as before."""
    if (insider or {}).get("depth") != "light":
        return None
    facts = _facts_by_id(capture)
    count, direction, value = (facts.get(fact_id)
                               for fact_id in insider["summary"])
    if count is None or direction is None or value is None:
        return None
    net = _one_line(direction.get("value"))
    lead = ["Over the twelve months to %s, officers and directors made %s "
            "dealings; by shares they were %s; the dealings' total value, "
            "bought plus sold, was %s (the summary's own figures, from the "
            "filings its sources name)."
            % (_safe(_format_date(count.get("as_of"))),
               _safe(count.get("value")),
               SUMMARY_NET_WORDS.get(net) or _safe(net),
               _value_words(value))]
    roles = tuple(role + "_" for role in insider["officer_roles"])
    if order and all(str(suffix).startswith(roles) for suffix in order):
        lead.append(OFFICERS_ONLY % (_safe(insider["threshold"]),
                                     _safe(insider["holding"])))
    elif not any(str(fact_id).startswith(prefix) for fact_id in facts
                 for _role, prefix in INSIDER_PARTS):
        lead.append(NO_OFFICER_DEALT)
    return lead


def _insider_lines(pack, dealings, order, lead=None):
    """The insider dealings as one table, then the shares sold and bought
    across them, summed at display. At the light depth the summary's lead
    line comes first, and the closing sum speaks of the dealings listed,
    so the officers' sums are never read as the whole."""
    lines = ["### %s" % INSIDER_HEADING, ""]
    if lead:
        for sentence in lead:
            lines.extend([sentence, ""])
        if not order:
            return lines
    lines.extend(INSIDER_TABLE_HEAD)
    totals = {"sell": decimal.Decimal(0), "buy": decimal.Decimal(0)}
    summable = True
    for suffix in order:
        trio = dealings[suffix]
        facts = [trio[role] for role, _prefix in INSIDER_PARTS]
        names = " / ".join(_distinct(_fact_name(fact) for fact in facts))
        stale = "".join(_freshness_mark(pack, fact.get("id"))
                        for fact in facts)
        direction = _one_line(trio["direction"].get("value"))
        sources = " / ".join(_distinct(_safe(fact.get("source"))
                                       for fact in facts))
        # The recorded direction and date stand beside their words, and
        # the entry's own key ending in the first column: the table keeps
        # what the three entries carried (audit round 1 of UPGRADE2-READ-B2).
        said = DIRECTION_WORDS.get(direction)
        lines.append("| %s | %s | %s%s | %s | %s | %s |"
                     % (_safe(suffix), _value_words(trio["date"]),
                        names, stale,
                        ("%s — recorded %s" % (said, _safe(direction)))
                        if said else _safe(direction),
                        _value_words(trio["size"]), sources))
        if direction in totals:
            try:
                size = decimal.Decimal(str(trio["size"].get("value")))
            except (decimal.InvalidOperation, ValueError):
                size = None
            per = SHARES_PER_UNIT.get(trio["size"].get("unit"))
            if size is None or not size.is_finite() or per is None:
                summable = False
            else:
                totals[direction] += size * per
    lines.append("")
    lines.append(INSIDER_KEY_NOTE % RECORD_KEY_LINE)
    lines.append("")
    # Number agreement for one dealing and for many (architect ruling,
    # round 2 of UPGRADE2-READ-B2).
    across = "Across %s%d %s%s" % ("the " if lead else "", len(order),
                                   "dealing" if len(order) == 1
                                   else "dealings",
                                   " listed" if lead else "")
    if summable:
        lines.append("%s, insiders sold %s and bought %s (calculated)."
                     % (across,
                        _safe(_format_number(str(totals["sell"]), "shares")),
                        _safe(_format_number(str(totals["buy"]), "shares"))))
    else:
        lines.append("%s, the shares sold and bought are not calculable: a "
                     "size is not a number of shares." % across)
    lines.append("")
    return lines


def _full_fact_lines(pack, capture):
    lines = ["## Every fact, in full", ""]
    # Owner ruling AC47(3): where the ownership cannot be established the
    # insider evidence is not considered, and the document says so once.
    insider = sufficiency.insider_depth(pack, _floors())
    if (insider or {}).get("not_considered"):
        lines.extend(["### %s" % INSIDER_HEADING, "",
                      sufficiency.INSIDER_NOT_CONSIDERED, ""])
    notes = pack.get("generated_notes") or {}
    dealings = _insider_dealings(capture, notes)
    in_table = {}
    for suffix, trio in dealings.items():
        for fact in trio.values():
            in_table[fact.get("id")] = suffix
    order = []
    for fact in capture.get("tier1") or []:
        suffix = in_table.get(fact.get("id"))
        if suffix is not None and suffix not in order:
            order.append(suffix)
    lead = _insider_lead(pack, capture, insider, order)
    opens = set(insider["summary"]) if lead else set()
    printed_table = False
    for fact in capture.get("tier1") or []:
        fact_id = fact.get("id")
        if fact_id in in_table or fact_id in opens:
            if not printed_table:
                lines.extend(_insider_lines(pack, dealings, order, lead))
                printed_table = True
            if fact_id in in_table:
                continue
        lines.append("### %s" % _fact_heading(fact))
        lines.append("- Value: %s (as of %s)%s"
                     % (_value_words(fact),
                        _safe(_format_date(fact.get("as_of"))),
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
        lines.append("%s`%s`" % (RECORD_KEY_LINE, _one_line(fact_id)))
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
        lines.append("### %s (as of %s)"
                     % (_words_of_id(passage.get("id")),
                        _safe(_format_date(passage.get("as_of")))))
        lines.append("- Source: %s" % _safe(passage.get("source")))
        figures = passage.get("figures") or []
        if figures:
            lines.append("- Figures stated: %s"
                         % ", ".join(_safe(f) for f in figures))
        lines.append("")
        lines.append(_safe(passage.get("text")))
        lines.append("")
        lines.append("%s`%s`" % (RECORD_KEY_LINE,
                                 _one_line(passage.get("id"))))
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
        lines.append("- %s (%s; weakens %s)"
                     % (_safe(gap.get("reason")),
                        _safe(gap.get("fact_class")),
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
    lines = ["**Pass %s: %s.**" % (pass_no, AUDIT_SCOPE_WORDS.get(scope)
                                   or "a %s check" % _safe(scope)), ""]
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
        lines.append("#### %s" % _finding_title(finding))
        lines.append("- It said: %s" % _safe(finding.get("detail")))
        if finding.get("fact_ids"):
            lines.append("- The figures it is about: %s"
                         % "; ".join(_fact_ref(facts, f)
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
        disposition = resolution.get("disposition")
        answer = "- The answer: %s" % (
            _DISPOSITION_WORDS.get(disposition) or _safe(disposition)
            or "not answered")
        if resolution.get("fact_ids"):
            answer += " (%s)" % "; ".join(_fact_ref(facts, f)
                                          for f in resolution["fact_ids"])
        if resolution.get("reason"):
            answer += " - %s" % _safe(resolution.get("reason"))
        lines.append(answer)
        if resolution.get("weakened_test"):
            lines.append("  - it weakens: %s"
                         % _safe(resolution.get("weakened_test")))
        lines.append("")
    return lines


AUDIT_SCOPE_WORDS = {
    "full": "the whole evidence read",
    "delta": "a re-check of a correction",
}


def _full_auditor_lines(capture):
    lines = ["## The %s in full: what the outside model said, and what was "
             "done about it" % EVIDENCE_CHECK, ""]
    block = capture.get("evidence_challenge")
    if not block:
        lines.append("No %s is on this record." % EVIDENCE_CHECK)
        lines.append("")
        return lines
    facts = holding_display_facts(capture, recorded=True)
    lines.extend(_audit_pass_lines(block, facts, current=True))
    for prior in block.get("prior_passes") or []:
        lines.append("### An earlier pass of the %s, kept whole"
                     % EVIDENCE_CHECK)
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
    producer = producer_subject_frame(capture) is not None
    if (grower_subject_frame(capture) is not None or producer
            or holding_subject_frame(capture) is not None):
        # Owner ruling AC50(9) as amended: a growth company's three
        # standard tests, each named in the floors' own words; a producer's
        # two in the floors' words and its third, the yardstick, in the
        # measure's (owner ruling AC54(R14)).
        term = sufficiency._canonical_test_terms(
            _floors(), sufficiency._declared_archetype(_floors(), capture)
        ).get(req.get("id")) or {}
        ruled = (term.get("words") or [None])[0]
        if (holding_subject_frame(capture) is not None
                and req.get("id") == "rating_vs_history_or_peers"):
            # AC62(H13): the third holding test, beside the first two in data.
            ruled = "the discount against its own history and its peers"
        if (producer and not ruled and req.get("id") == PRODUCER_THIRD_TEST[0]
                and _rating_measure(capture) in _MEASURE_WORDS):
            ruled = PRODUCER_THIRD_TEST[1] % _MEASURE_WORDS[
                _rating_measure(capture)]
        if ruled:
            return "%s %s%s" % (escape("%s (the capture's words:" % ruled),
                                words, escape(")"))
        return words
    frame = fi_subject_frame(capture)
    if (req.get("id") == FREE_CASH_ROW and frame is not None
            and frame.get("fi_subtype") in fi_lifted_subtypes()):
        # The space after the colon is added outside `escape`: the page's
        # neutralization collapses a trailing space away (unit READ-B2).
        return "%s %s%s" % (escape("%s (the capture's words:"
                                   % FI_FREE_CASH_WORDS), words, escape(")"))
    return words


REQUIREMENT_KIND_WORDS = {
    "canonical_test": "standard test",
    "thesis_specific": "your thesis test",
    "floor": "a floor the rules require",
    "constituent_essential": "essential for a member",
}


def _full_checklist_lines(capture):
    """The checklist in words (unit READ-B2): each question, whether it is
    answered, what kind of test it is, and the facts that answer it by
    name - no keys (audit round 1 of UPGRADE2-READ-B2: which fact answers
    which test is a record the approved document keeps)."""
    lines = ["## The sufficiency checklist", ""]
    facts = holding_display_facts(capture, recorded=True)
    passages = _passages_by_id(capture)
    for req in (capture.get("sufficiency") or {}).get("requirements") or []:
        kind = req.get("kind")
        kind_words = REQUIREMENT_KIND_WORDS.get(kind) or _safe(kind)
        if req.get("status") == "answered":
            by = "; ".join(_fact_ref(facts, fact_id, passages)
                           for fact_id in req.get("answered_by") or [])
            lines.append("- Answered - %s: %s%s"
                         % (kind_words,
                            checklist_description(capture, req, _safe),
                            (" - answered by: %s" % by) if by else ""))
        else:
            # The weakened test is what a declared gap COSTS; the approved
            # document must state it, not only the reason (audit round 1 of
            # sub-charge b, b-r1-7).
            lines.append("- Declared gap - %s: %s - %s (weakens %s)"
                         % (kind_words,
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
    summary = render(pack, pack_sha256, usage, in_full=True).rstrip("\n")
    lines = [summary, "",
             "---", "",
             "# The full evidence - the document approved in reviewed mode",
             "",
             "Everything above is the one-page summary; everything below is "
             "the whole of the evidence the council will sit on, in full and "
             "nothing trimmed. This is the document a reviewer approves.",
             ""]
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
    """The brief command. With `--full` it writes the full evidence document
    AND, beside it, the page the owner reads it on (owner ruling AC40(2b)):
    `<name>.md` gets `<name>.html`, rendered by
    council.report.evidence_page from the exact Markdown bytes written here,
    so the page is provably that document. An existing file at the page's
    path is replaced only when it is a page that renderer wrote; anything
    else is refused and NEITHER file is written. Without `--full` no page is
    written. Exit 0 written, 1 usage error, refusal or crash."""
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
        data = text.encode("utf-8")
        page_path = page = None
        if full:
            # Imported here, never at the top: the report renderer the page
            # module reads its shell from imports this module at its own top.
            from council.report import evidence_page
            page_path = evidence_page.page_path(out_path)
            if (os.path.exists(page_path)
                    and not evidence_page.is_own_page(page_path)):
                print("brief: REFUSED - %s already exists and is not a page "
                      "the brief command wrote. Writing the page would "
                      "overwrite it; nothing was written." % page_path)
                return 1
            page = evidence_page.render_page(data.decode("utf-8"))
        canonical.write_bytes_atomic(out_path, data)
        print("brief: %s written to %s (%d lines)"
              % ("full document" if full else "one page", out_path,
                 len(text.splitlines())))
        if full:
            canonical.write_bytes_atomic(page_path, page.encode("utf-8"))
            print("  the page to read it on: %s - open it in a browser"
                  % page_path)
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
