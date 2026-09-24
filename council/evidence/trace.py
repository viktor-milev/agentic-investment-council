"""Owner ruling AC19 - a number in the business-frame PROSE that is not
traced to a recorded fact is MARKED where it is shown, and never refuses
the pack (unit UPGRADE-2 U3f; mechanism recorded in docs/BUILD-LOG.md).

The council reads every number in the business-frame prose. A number that
matches a recorded fact - allowing for rounding and for a change of scale
or unit wording - is left alone. A number that matches nothing stays in the
text and is marked. Years, dates, ordinals, period labels and plain counts
are exempt; the exemption list and the matching tolerances are DATA, kept in
council/floors/floors.json under `prose_figure_marks`, never code constants
here (AC19(4)).

Everything here is computed at RENDER TIME from the frozen pack. No schema
field, no change to the freeze, no change to the pack hash: the same pack
produces the same marks, byte for byte (mechanism ruling 7). A token this
scanner cannot read is left in the text unmarked and counted under "could
not be read"; the scan never raises on prose (mechanism ruling 6).

There is NO arithmetic-between-facts recognition. The owner's own case - a
correct quarterly figure that is one fourth of a recorded annual one - is
the case that earns a mark and costs nothing, by design of the ruling.
"""

import re
from decimal import (Decimal, DecimalException, InvalidOperation,
                     ROUND_HALF_UP)

from council.evidence import gate

# The ONE marker, the renderer's own voice, placed directly after an
# untraced number wherever the prose is shown. The same wording everywhere
# (mechanism ruling 5). It is not model text and is emitted as itself, the
# way the STALE mark of owner ruling AC11 is (brief._freshness_mark).
MARKER = "[not traced to a recorded fact]"

# A model may, by its own unreliability, write the marker's own text into
# prose. Only the RENDERER may speak the marker, so any occurrence in model
# prose is turned into a look-alike that is not the marker, before the renderer
# adds its own (audit UPGRADE2-U3f r1-1). The look-alike is the same length, so
# token offsets are unchanged.
_FORGED_MARKER = MARKER.replace("[", "(").replace("]", ")")


# One tokenizer, stdlib `re`, written once (mechanism ruling 2). A numeric
# token is an optional currency sign, an optional sign, digits with optional
# grouping commas and an optional decimal, and an optional percent sign. The
# left edge forbids a start in the middle of a number (a digit, a comma or a
# decimal point just before), so "1,234.5" is one token and "20-25" is two.
# A scale word or letter after the token (thousand, M, bn) is read from the
# text in _classify, where the ruled scale list decides whether it is one; a
# percent WORD, a unit word, an ordinal suffix and a letter just before the
# token are read from context there too.
_TOKEN = re.compile(r"""
    (?<![0-9.,])                       # not mid-number
    (?P<sign_pre>[+-])?                 # a sign BEFORE the currency (-$500)
    (?P<currency>[$€£])?     # $  euro  pound
    (?P<sign>[+-])?                     # or after it ($-500), or none
    (?P<digits>
        [0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?   # grouped thousands
        | [0-9]+(?:\.[0-9]+)?                    # plain or decimal
        | \.[0-9]+                               # bare decimal
    )
    (?P<percent>\s*%)?
""", re.VERBOSE)

# The scale word, if any, sitting right after a token (optionally one space).
_SCALE_AFTER = re.compile(r"\s*(?P<scale>[A-Za-z]+)")
# An ISO date is exempt whole (mechanism ruling 3): its day-of-month would
# otherwise read as a bare number above the plain-count floor.
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_WORD_AFTER = re.compile(r"\s*([A-Za-z]+)")


class Token:
    """One numeric token found in prose, with where it sits and what the
    scan decided. `status` is traced / untraced / unreadable / exempt; only
    the first three are counted in a summary, and only `untraced` earns the
    marker. `end` is where the marker would go - after the figure and its
    percent sign and scale word."""

    __slots__ = ("start", "end", "text", "status")

    def __init__(self, start, end, text, status):
        self.start = start
        self.end = end
        self.text = text
        self.status = status


def config(floors):
    """The `prose_figure_marks` block of the ruled floors data, as the
    scanner reads it. Kept as data so a tolerance or an exemption is
    changed in floors.json, never here (AC19(4))."""
    block = (floors or {}).get("prose_figure_marks") or {}
    return {
        "tolerance": _decimal(block.get("relative_tolerance", "0.005"))
        or Decimal("0.005"),
        "year_min": int(block.get("year_min", 1900)),
        "year_max": int(block.get("year_max", 2100)),
        "day_min": int(block.get("day_min", 1)),
        "day_max": int(block.get("day_max", 31)),
        "plain_count_max": int(block.get("plain_count_max", 12)),
        "ordinal_suffixes": tuple(s.lower() for s in
                                  (block.get("ordinal_suffixes")
                                   or ("st", "nd", "rd", "th"))),
        "date_day_closers": frozenset(block.get("date_day_closers")
                                      or (",", ".", ";", ":", ")")),
        "scale_words": {k: int(v)
                        for k, v in (block.get("scale_words") or {}).items()
                        if len(str(k)) == 1},
        "scale_words_ci": {str(k).lower(): int(v)
                           for k, v in (block.get("scale_words") or {}).items()
                           if len(str(k)) > 1},
        "percent_words": tuple(w.lower() for w in
                               (block.get("percent_words") or ())),
        "month_words": tuple(w.lower() for w in
                             (block.get("month_words") or ())),
        "percent_units": frozenset(block.get("percent_units") or ()),
        "fraction_units": frozenset(block.get("fraction_units") or ()),
        "currency_scale_units": {k: int(v) for k, v in
                                 (block.get("currency_scale_units")
                                  or {}).items()},
    }


def _decimal(text):
    """A string as a finite Decimal, or None, read EXACTLY as the gate reads a
    captured value (gate._decimal_or_none): only STRICT thousands grouping is
    stripped, so a comma that is not a thousands separator leaves the value
    unreadable rather than silently becoming a different number - '1,3' is not
    thirteen (audit UPGRADE2-U3f r1-4; the gate's own rule, audit r6-1). The
    prose tokenizer only ever emits strict grouping, so prose reads unchanged;
    a fact value the gate rejects is skipped here too, never mis-read."""
    return gate._decimal_or_none(text)


def _sig_figs(digits):
    """How many significant figures the prose WROTE - the precision a match
    is judged to (mechanism ruling 4). Leading zeros never count; other
    digits, including trailing zeros, do."""
    clean = digits.replace(",", "")
    if "." in clean:
        whole = "".join(clean.split(".")).lstrip("0")
    else:
        whole = clean.lstrip("0")
    return max(len(whole), 1)


def _round_sig(value, sig):
    """`value` rounded to `sig` significant figures, half up."""
    if value == 0:
        return Decimal(0)
    quantum = Decimal(1).scaleb(value.adjusted() - sig + 1)
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _fact_bases(capture, ticker, cfg):
    """Every recorded fact value this frame may be traced against, each as
    (scaled, face, is_percent) (mechanism ruling 4). `scaled` reads the
    fact's unit where it states a currency scale (USD_thousand -> base
    units); `face` is the value as the record writes it, so a prose number
    that omits the scale word but writes the fact's own digits still traces
    (owner ruling AC19(1): a number that matches a recorded fact allowing a
    change of scale OR unit wording is left alone - the change of scale is
    ALLOWED, never required). For a member frame that is the member's own
    facts plus the unsuffixed shared ones - the same reach gate binds a
    declared figure to (gate `block_values`); on a single name every fact,
    a double-underscore tail on its id included (P-FIb-4). Derived facts
    are facts."""
    subject = capture.get("subject") or {}
    suffix = gate.frame_suffix(subject, ticker)
    bases = []
    for fact in capture.get("tier1") or []:
        fact_id = fact.get("id")
        if suffix and gate._id_suffix(fact_id) not in ("", suffix):
            continue
        value = _decimal(fact.get("value"))
        if value is None:
            continue
        unit = str(fact.get("unit") or "")
        if unit in cfg["percent_units"]:
            bases.append((value, value, True))
        elif unit in cfg["fraction_units"]:
            bases.append((value * 100, value * 100, True))
        else:
            exponent = cfg["currency_scale_units"].get(unit)
            scaled = value.scaleb(exponent) if exponent is not None else value
            bases.append((scaled, value, False))
    return bases


def _close(a, b, sig, tolerance):
    """Whether two values agree to the prose's own precision, or within the
    ruled relative tolerance (mechanism ruling 4)."""
    if _round_sig(a, sig) == _round_sig(b, sig):
        return True
    if b == 0:
        return a == 0
    return abs(a - b) <= tolerance * abs(b)


def _traced(scaled, face, is_percent, sig, bases, tolerance, face_ok):
    """Whether this prose number matches any recorded fact value: either the
    prose read at its scale against the fact read at its unit's scale, or -
    only where the prose carries NO explicit scale word (`face_ok`) - the
    prose's own digits against the fact's own digits. The face branch lets a
    bare number that omits the scale word still trace; forbidding it where the
    prose DOES state a scale stops '$950M' matching a fact worth 950 in base
    units, a million-fold mismatch (audit UPGRADE2-U3f r1-3). A percentage
    matches a percent-unit or fraction-unit fact; a plain number matches a
    plain fact."""
    for fact_scaled, fact_face, fact_is_percent in bases:
        if fact_is_percent != is_percent:
            continue
        if _close(scaled, fact_scaled, sig, tolerance):
            return True
        if face_ok and _close(face, fact_face, sig, tolerance):
            return True
    return False


def _exempt_zones(text):
    """Character ranges that are dates, exempt whole (mechanism ruling 3).
    Only ISO dates need a zone; a written date's day and year are caught by
    the month-word and year rules in _classify."""
    return [(m.start(), m.end()) for m in _ISO_DATE.finditer(text)]


def _word_before(text, start):
    """The alphabetic run ending just before `start`, skipping any spaces
    between it and `start`, lower-cased, or ''. Skipping the space lets a month
    word be read across the gap of a written date - the day in 'September 30'
    (audit UPGRADE2-U3f r1-6)."""
    end = start
    while end > 0 and text[end - 1] in " \t ":
        end -= 1
    i = end
    while i > 0 and text[i - 1].isalpha():
        i -= 1
    return text[i:end].lower()


def _following_words(text, pos):
    """Up to the next two alphabetic words from `pos`, lower-cased. Enough
    to read 'per cent' and to see the word that sits after a number."""
    words = []
    for _ in range(2):
        m = _WORD_AFTER.match(text, pos)
        if not m:
            break
        words.append(m.group(1).lower())
        pos = m.end()
    return words


def _classify(text, bases, cfg):
    """Every numeric token in `text`, in order, each decided. Never raises:
    a token whose digits do not read as a number is `unreadable` (mechanism
    ruling 6)."""
    if not text:
        return []
    zones = _exempt_zones(text)
    tokens = []
    for match in _TOKEN.finditer(text):
        start = match.start()
        digits = match.group("digits")
        after_number = (match.end("percent") if match.group("percent")
                        else match.end("digits"))
        # A scale word or letter right after the figure, if the ruled data
        # says it is one. Anything else (a unit word, a preposition) is not
        # part of the token and the marker lands after the figure.
        exponent = None
        end = after_number
        scale_match = _SCALE_AFTER.match(text, after_number)
        if scale_match:
            candidate = scale_match.group("scale")
            if len(candidate) == 1 and candidate in cfg["scale_words"]:
                exponent = cfg["scale_words"][candidate]
                end = scale_match.end()
            elif candidate.lower() in cfg["scale_words_ci"]:
                exponent = cfg["scale_words_ci"][candidate.lower()]
                end = scale_match.end()
        token_text = text[start:end]

        is_percent = bool(match.group("percent"))
        following = _following_words(text, after_number)
        if not is_percent and following:
            if following[0] in cfg["percent_words"]:
                is_percent = True
            elif (len(following) >= 2 and following[0] == "per"
                  and following[1] == "cent"):
                is_percent = True

        if _is_exempt(match, digits, exponent, is_percent, start,
                      after_number, following, zones, cfg, text):
            tokens.append(Token(start, end, token_text, "exempt"))
            continue

        # Never raise on prose (mechanism ruling 6): a token whose digits do
        # not read as a number, or a pathological one the decimal library
        # cannot round, is left unmarked and counted "could not be read".
        try:
            face = _decimal(digits)
            if face is None:
                raise InvalidOperation
            if (match.group("sign_pre") or match.group("sign")) == "-":
                face = -face
            scaled = face.scaleb(exponent) if exponent is not None else face
            status = ("traced"
                      if _traced(scaled, face, is_percent, _sig_figs(digits),
                                 bases, cfg["tolerance"], exponent is None)
                      else "untraced")
        except (DecimalException, ValueError, OverflowError):
            status = "unreadable"
        tokens.append(Token(start, end, token_text, status))
    return tokens


def _is_day_number(match, digits, exponent, is_percent, cfg):
    """A plausible day of the month: an unsigned integer in the ruled day
    range, with no currency, percent, scale or sign. Only such a number sitting
    beside a month word is a written date's day; a percent, currency or scaled
    figure that merely follows a month name (e.g. 'September 30.5%') is a figure
    of the prose and must still be marked (audit UPGRADE2-U3f r2-2)."""
    if (is_percent or match.group("currency") or exponent is not None
            or match.group("sign_pre") or match.group("sign")
            or "." in digits):
        return False
    value = _decimal(digits)
    if value is None:
        return False
    return cfg["day_min"] <= int(value) <= cfg["day_max"]


def _day_ends_date(text, after_number, cfg):
    """Whether a plausible day-of-month written AFTER its month word
    ("September 30") ends a written date rather than opening a measured
    figure. It ends a date only when nothing that could be its unit follows
    it: after an optional ordinal suffix (30th) and any spaces, the next
    character is the end of the text, one of the ruled date closers (a comma,
    a sentence end, a semicolon, colon or closing bracket), or the first
    digit of a four-digit year in the ruled range (a comma-less "September 30
    2026"). A letter-word after the number ("September 30 MW", "August 25
    basis points") makes the number a figure of the prose, traced and marked
    like any other (architect ruling closing register item P-U3f-2, audit
    UPGRADE2-U3f r3-1). By this rule "September 30 and October 1" over-marks
    the 30 - an over-marked date costs the reader one glance; a missed figure
    is the failure AC19 exists to prevent (the ruling accepts the cost)."""
    pos = after_number
    tail = text[pos:]
    for suffix in cfg["ordinal_suffixes"]:
        if tail[:len(suffix)].lower() == suffix:
            pos += len(suffix)
            break
    while pos < len(text) and text[pos] in " \t\xa0":
        pos += 1
    if pos >= len(text):
        return True
    if text[pos] in cfg["date_day_closers"]:
        return True
    year = text[pos:pos + 4]
    return (len(year) == 4 and year.isdigit()
            and not (pos + 4 < len(text) and text[pos + 4].isdigit())
            and cfg["year_min"] <= int(year) <= cfg["year_max"])


def _is_exempt(match, digits, exponent, is_percent, start, after_number,
               following, zones, cfg, text):
    """Whether this token is exempt from marking (mechanism ruling 3), every
    parameter read from the ruled data."""
    # A number inside a fact id, a ticker or a period label (Q3, FY2026, H1)
    # has its DIGITS sitting straight after a letter; it is not a figure of the
    # prose. A currency sign between a letter and the digits (US$500) is not
    # such an identifier, so the character read is the one before the digits,
    # never before an optional leading currency sign (audit UPGRADE2-U3f r1-5).
    digits_start = match.start("digits")
    if digits_start > 0 and text[digits_start - 1].isalpha():
        return True
    # A date: an ISO date whole, and a written date's day sitting beside a
    # month word (a month-year's year is caught by the year rule below).
    for lo, hi in zones:
        if start < hi and match.end("digits") > lo:
            return True
    if cfg["month_words"] and _is_day_number(match, digits, exponent,
                                             is_percent, cfg):
        # "30 September": the month word itself follows the number - a written
        # date's day, unchanged.
        if following and following[0] in cfg["month_words"]:
            return True
        # "September 30": a day written AFTER a month word is a date's day
        # ONLY when nothing that could be its unit follows it - see
        # _day_ends_date (architect ruling closing register item P-U3f-2,
        # audit UPGRADE2-U3f r3-1).
        if (_word_before(text, digits_start) in cfg["month_words"]
                and _day_ends_date(text, after_number, cfg)):
            return True
    plain = (not match.group("currency") and not is_percent
             and exponent is None)
    if not plain:
        return False
    # An ordinal (21st, 40th) is exempt - but only a suffix DIRECTLY attached
    # to the digits and ending at a non-letter boundary. A unit word that
    # merely begins with an ordinal bigram ("40 stores" -> "st", "40thstore")
    # is not an ordinal and does not lift the mark (audit UPGRADE2-U3f r4-1).
    tail = text[after_number:]
    for suffix in cfg["ordinal_suffixes"]:
        if (tail[:len(suffix)].lower() == suffix
                and not tail[len(suffix):len(suffix) + 1].isalpha()):
            return True
    if "." in digits:
        return False
    value = _decimal(digits)
    if value is None:
        return False
    integer = int(value)
    # A four-digit year in the ruled range.
    if len(digits) == 4 and cfg["year_min"] <= integer <= cfg["year_max"]:
        return True
    # A plain count up to the ruled maximum. A count carries no scale, no
    # currency and no percent; a following ordinary word (a preposition, a
    # noun) does not turn a count into a measured figure, so it does not
    # lift the exemption.
    if 0 <= integer <= cfg["plain_count_max"]:
        return True
    return False


def scannable_texts(frame):
    """Every prose field of a business frame the council reads (mechanism
    ruling 1), in a stable order. Tier-2 passages are NOT here: they meet
    their own declared-figures rule. The one source of truth for what is
    scanned, used by both the marker and the summary count so the two can
    never disagree."""
    if not frame:
        return []
    texts = [frame.get("what_it_does")]
    changing = frame.get("what_is_changing") or {}
    texts.append(changing.get("statement"))
    decline = frame.get("headline_decline_read") or {}
    texts.append(decline.get("statement"))
    for line in frame.get("how_it_earns") or []:
        texts.append(line.get("line"))
    for metric in frame.get("decisive_metrics") or []:
        # Architect ruling closing P-U3f-4 (round 5): a decisive metric's
        # NAME is model-written business-frame prose a person sees in every
        # artifact, so under AC19(1) it is scanned - and marked at every
        # render site - like the rest.
        texts.append(metric.get("name"))
        texts.append(metric.get("why_it_decides"))
        gap = metric.get("gap") or {}
        texts.append(gap.get("reason"))
        texts.append(gap.get("weakened_test"))
    for peer in frame.get("peers") or []:
        texts.append(peer.get("comparable_because"))
        texts.append(peer.get("not_comparable_on"))
    texts.append(frame.get("archetype_because"))
    texts.append(frame.get("cycle_dependence_because"))
    return [text for text in texts if text]


def counts(frame, bases, cfg):
    """(traced, untraced, unreadable) over every scannable field of one
    frame, against an already-built fact index. The number behind the
    summary line."""
    traced = untraced = unreadable = 0
    for text in scannable_texts(frame):
        for token in _classify(text, bases, cfg):
            if token.status == "traced":
                traced += 1
            elif token.status == "untraced":
                untraced += 1
            elif token.status == "unreadable":
                unreadable += 1
    return (traced, untraced, unreadable)


def frame_counts(capture, ticker, frame, cfg):
    """(traced, untraced, unreadable) for a frame, building the frame's fact
    index from the capture first."""
    return counts(frame, _fact_bases(capture, ticker, cfg), cfg)


def summary_sentence(counts):
    """The one summary line per frame (mechanism ruling 5), the same wording
    everywhere it is shown."""
    traced, untraced, unreadable = counts
    total = traced + untraced + unreadable
    sentence = ("Figures traced to the record: %d of %d number(s) in this "
                "business description match a recorded fact; %d marked in "
                "the text as not traced to one" % (traced, total, untraced))
    if unreadable:
        sentence += "; %d could not be read" % unreadable
    return sentence + "."


AUDITOR_LOOK_FIRST = (
    "Numbers in the business description below that are not traced to a "
    "recorded fact of this pack are marked %s; look at those first." % MARKER)


def mark(text, bases, cfg, transform=None, separate_after=False):
    """`text` with the marker placed directly after every untraced number,
    each stretch of model prose passed through `transform` and each marker
    emitted as itself (mechanism ruling 5).

    `transform` is the caller's own neutralization - brief._escape for the
    document a person approves, or the identity for the case file, where the
    quoted-data fence carries the trust. `bases` is _fact_bases for the
    frame. The text is walked once; where there is nothing to mark the
    result is exactly `transform(text)`, so a frame with no untraced number
    renders as it did before this unit.

    `separate_after` is set only by a Markdown-emitting caller (brief._marked
    / _marked_trim). Where the model prose immediately after the marker begins
    with '(', that one character is escaped ('\\('), so the renderer's own
    '[not traced to a recorded fact]' can never pair with a model-supplied
    '(url)' into a Markdown link in the document a person approves (audit
    UPGRADE2-U3f r5-1). The raw-text case file and auditor brief leave it off:
    they are read by the seats, not rendered as Markdown."""
    transform = transform or (lambda segment: segment)
    # Only the renderer speaks the marker: neutralise any occurrence the model
    # wrote into the prose before scanning, so a forged one can never pass for
    # a renderer-added mark (audit UPGRADE2-U3f r1-1).
    text = text.replace(MARKER, _FORGED_MARKER)
    marks = [token for token in _classify(text, bases, cfg)
             if token.status == "untraced"]
    if not marks:
        return transform(text)

    def _follows_marker(segment):
        # A prose stretch that FOLLOWS the marker must not begin with '(' in a
        # Markdown artifact: '[MARKER](url)' would read as a link made from the
        # renderer's own mark (audit UPGRADE2-U3f r5-1). Escape that one char.
        segment = transform(segment)
        if separate_after and segment[:1] == "(":
            segment = "\\" + segment
        return segment

    # The first stretch is BEFORE any marker, so it is never escaped this way;
    # every later stretch and the tail follow a marker.
    out = [transform(text[:marks[0].end])]
    cursor = marks[0].end
    for token in marks[1:]:
        out.append(" " + MARKER)
        out.append(_follows_marker(text[cursor:token.end]))
        cursor = token.end
    out.append(" " + MARKER)
    out.append(_follows_marker(text[cursor:]))
    return "".join(out)
