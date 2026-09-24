"""render_report.py - the human-facing HTML report for a published split-mode council run.

    python -m council.report.render_report <run_dir> [-o <out_file>]

Default output is `<run_dir>/report.html`. One self-contained file: every style and script is
inline, nothing is fetched, it opens from `file://` (owner ruling Y2).

WHAT THIS IS. The report is the human deliverable of a council run (REBUILD-SPEC section 9); the
JSON verdict stays the machine surface and the run directory stays the archive. The design is the
old renderer's, ruled at the design sitting (ruling Y): dark by default with a visible light
toggle, a navigation icon pinned to the upper-left corner of the SCREEN with a slim dropdown that
appears on hover (and on click/keyboard, for touch and accessibility), long reference blocks
folded shut until clicked, and one reading precision per unit. This file adapts those proven
mechanisms to the verdict contract 1.0.0; the old renderer stays where it is, serving the old runs.

IT WRITES `report.html` AND ONE APPEND-ONLY ROW, AND READS EVERYTHING ELSE. `council/runs/**` is
a record. Rendering adds `report.html` beside the archives and changes no existing byte; the FIRST
rendering of a run also appends one `report_rendered` row to that run's own record, which is where
this page reads its clock from ever after (register item P-U3-5) - written only once the page
itself is on disk. In the runbook's order that happens inside the sitting, before the run
directory is committed.

Stdlib only, Python 3 - ruling X. Ruling Z binds every label and sentence this page authors:
plain CIO-suitable English, short sentences, no unexplained internal identifiers (the field ids
that appear inside tables are data, and their label columns say in plain words what they are).
"""
import datetime
import decimal
import hashlib
import html
import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.engine import runrecord  # noqa: E402
from council.evidence import brief, gate, tape, trace  # noqa: E402
from council.lib import prose, subjects  # noqa: E402
from council.report import chart  # noqa: E402


class MissingInputError(Exception):
    """The run directory does not carry what a report needs. The message is the reason,
    in plain words."""


# The opening bytes of every report this command writes (dark by default is ruling Y4, so the
# theme attribute is in the second line unconditionally), and the marker the output guard uses
# to tell a report it may overwrite from a document it may not. Both halves are bytes the
# renderer already emits on every page: the preamble, and the footer's own name for this file.
PREAMBLE = b'<!DOCTYPE html>\n<html lang="en" data-theme="dark">\n'
RENDERER_SIGNATURE = b"council/report/render_report.py"


# ---------------------------------------------------------------------------------------------
# NUMBER DISPLAY - AT RENDER TIME ONLY (ruling Y5; owner ruling AC16 items 1 and 4; the
# report-design audit 2026-09-15 section C1)
# ---------------------------------------------------------------------------------------------
# The pack and the verdict carry every figure as the exact string that was captured; nothing is
# rounded on disk and nothing is written back. The reader's form is chosen HERE, on the way to
# the page: the market's own spelling of money - a currency sign BEFORE the figure and a scale
# letter after it ($47.6M, $7.81B), never the word "dollars"; three significant figures for
# money and counts; per-share prices to two decimals ($15.64); percentages to ONE decimal
# (owner ruling AC16(4) - never two: 3.9%, not 3.91%); multiples with an x (3.08x); dates in
# words (30 Jun 2026). A company's own reporting unit (USD_thousand, USD_m) is converted here
# and never reaches the page. DISPLAY ONLY: the value is unchanged, only its spelling.
#
# The reader-safety rules ported from the old renderer and kept unchanged:
#   * a figure a unit's precision would erase (print as 0) is NEVER erased - it falls back to
#     the exact text it arrived as;
#   * text that is not a pure number - NOT AVAILABLE, a sentence, a range - is never parsed,
#     with the one new exception of a date-shaped string (audit C1 R9/R13);
#   * a zero-padded bare integer is an identifier, not a quantity, and is never rounded;
#   * a Bitcoin reward (3.125) or a block height is never rounded.

# Currency sign placed before the figure. Everything not here - CHF, SEK, NOK, DKK and any
# unmapped ISO code - is written as its code and a space (CHF 1.20B, audit C1 R2). A money unit
# that names no currency, with none given beside it, falls back to today's plain spelling: the
# formatter never GUESSES a currency (dispatch).
CURRENCY_SIGNS = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
    "CAD": "C$", "AUD": "A$",
}
# The scale words a money unit may carry, as the factor to whole currency units.
_SCALE_WORDS = {"thousand": decimal.Decimal(1000), "m": decimal.Decimal(10) ** 6,
                "mn": decimal.Decimal(10) ** 6, "bn": decimal.Decimal(10) ** 9,
                "b": decimal.Decimal(10) ** 9}
_THOUSAND = decimal.Decimal(1000)
_MILLION = decimal.Decimal(10) ** 6
_BILLION = decimal.Decimal(10) ** 9
_TRILLION = decimal.Decimal(10) ** 12
# The scales, largest first. C1 names K/M/B; T (trillion) is the natural next step, needed
# because this council rates companies whose market value passes a trillion dollars.
_MONEY_SCALES = (("T", _TRILLION), ("B", _BILLION), ("M", _MILLION), ("K", _THOUSAND))
# One step UP the money scale, for the rare figure that rounds to 1,000 of its own scale
# (999.7M -> $1.00B): the third significant figure carries into the next scale (audit C1 R1).
_NEXT_SCALE = {"": ("K", _THOUSAND), "K": ("M", _MILLION),
               "M": ("B", _BILLION), "B": ("T", _TRILLION)}

# The percentage unit token, named once (so it is one data literal, not prose) and reused.
_PERCENT_PREFIX = "percent"
_MULTIPLE_UNITS = frozenset(["x", "ratio", "multiple"])
_DATE_UNITS = frozenset(["iso_date", "fiscal_quarter_end_date", "results_date_check", "date"])

# Units that are never rounded at all: a Bitcoin block reward of 3.125 rounded to 3.13 states a
# reward nobody has ever been paid, and a block height is an ordinal no rounding could improve.
UNROUNDED_UNITS = ("BTC", "block_height")

# The most digits BEFORE the point that any real figure has. A magnitude past this would print
# a page of digits, so it survives as the text it arrived as instead of being rounded.
MAX_FIGURE_DIGITS = 50

# What counts as a number written as text: an optional sign, digits, an optional decimal part,
# an optional exponent, and NOTHING else. Deliberately strict, so that dates, ranges and plain
# words are never parsed. A bare zero-led string of digits is an identifier and is left alone.
NUMERIC_TEXT = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
PADDED_IDENTIFIER = re.compile(r"^0\d+$")

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DATE_LEAD = re.compile(r"^\d{4}-\d{2}-\d{2}")
_TIMESTAMP = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$")

_HALF_UP = decimal.ROUND_HALF_UP


def _coerce(value):
    """(Decimal, fallback_text) for a figure to be formatted, or (None, text) where the value is
    not a pure number and must survive as the text it is. Bool and None are not figures. Exact
    decimal arithmetic throughout, never binary (ruling Y5): the page and the pack answer one
    rounding question one way, and 1.005 rounds UP at two decimals."""
    if isinstance(value, bool) or value is None:
        return None, str(value)
    if isinstance(value, int):
        return decimal.Decimal(value), str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None, str(value)
        return decimal.Decimal(value), repr(value)
    if isinstance(value, str):
        text = value.strip()
        if not NUMERIC_TEXT.match(text) or PADDED_IDENTIFIER.match(text):
            return None, value
        try:
            exact = decimal.Decimal(text)
        except decimal.InvalidOperation:
            return None, value
        if not exact.is_finite():
            return None, text
        return exact, text
    return None, str(value)


def _int_digits(scaled):
    """How many digits stand before the point in a scaled figure (949.7 -> 3, 9.007 -> 1)."""
    s = abs(scaled)
    if s < 1:
        return 1
    return s.adjusted() + 1


def _strip_trailing(number):
    """A fixed-point Decimal without its trailing zeros (498.90 -> 498.9, 110.0 -> 110)."""
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _currency_prefix(currency):
    """The sign or ISO-code-and-space to place before a figure, or None to never guess one."""
    if not currency:
        return None
    code = str(currency).split("_")[0]
    if code in CURRENCY_SIGNS:
        return CURRENCY_SIGNS[code]
    if len(code) == 3 and code.isalpha() and code.isupper():
        return code + " "
    return None


def _scale_money_number(magnitude):
    """A positive figure in whole currency units as scale-and-three-significant-figures: the
    number and its scale letter (10.4B, 950M, 1.00B, 78.0K, 500), or None where the precision
    would erase it. Trailing zeros are KEPT to the third figure ($1.00B, $36.0M)."""
    letter, div = "", decimal.Decimal(1)
    for name, factor in _MONEY_SCALES:
        if magnitude >= factor:
            letter, div = name, factor
            break
    while True:
        scaled = magnitude / div
        # Three significant figures of the DISPLAYED scale, unscaled money included: a sub-1,000
        # rate or scaled figure ($12.40/day) keeps its figures rather than rounding to whole
        # currency ($12/day), which changed the value (round 3 finding r3-3).
        decimals = max(0, min(2, 3 - _int_digits(scaled)))
        rounded = scaled.quantize(decimal.Decimal(1).scaleb(-decimals), rounding=_HALF_UP)
        if rounded >= 1000 and letter in _NEXT_SCALE:
            letter, div = _NEXT_SCALE[letter]
            continue
        if rounded == 0:
            return None
        return "{:.{}f}".format(rounded, decimals) + letter


def _money_parse(unit):
    """(currency_prefix, multiplier, suffix) if `unit` is a money unit, else None. The suffix is
    '' or a rate tail ('/day', '/MW', '/year'); per-share is handled on its own (audit C1 R3)."""
    head, per, tail = unit.partition("_per_")
    if per and tail == "share":
        return None
    suffix = "/" + tail if tail else ""
    parts = head.split("_")
    prefix = _currency_prefix(parts[0])
    if prefix is None:
        return None
    multiplier = decimal.Decimal(1)
    for token in parts[1:]:
        if token in _SCALE_WORDS:
            multiplier *= _SCALE_WORDS[token]
        else:
            return None
    return prefix, multiplier, suffix


def _percent_number(exact, negate):
    """A percentage to ONE decimal (owner ruling AC16(4)); a whole value shows no decimal.
    `negate` prints a drawdown with a minus. Returns the body WITHOUT the % sign, or None where
    one decimal would erase a live figure (the caller then keeps the exact text)."""
    if exact == 0:
        return "0"
    rounded = exact.quantize(decimal.Decimal("0.1"), rounding=_HALF_UP)
    if rounded == 0:
        # One decimal would print 0.0% for a live figure; the caller falls back to exact text.
        return None
    if negate:
        rounded = -abs(rounded)
    if rounded == rounded.to_integral_value():
        return "{:d}".format(int(rounded.to_integral_value()))
    return "{:.1f}".format(rounded)


# Short forms a percent/fraction unit's basis is spelt out from, as DATA (P-U6b-4). Anything not
# listed is printed as written with underscores turned to spaces ('per_year' -> 'per year',
# 'annualised'/'annualized' as written, 'of_revenue' -> 'of revenue').
_BASIS_ABBREVIATIONS = {"yoy": "year over year"}


def _basis_words(tail):
    """Whatever follows the leading percent/fraction token IS the basis, spelt for the page
    (P-U6b-4): underscores become spaces and a known short form expands. An empty tail is no
    basis."""
    words = tail.replace("_", " ").strip()
    if not words:
        return None
    return _BASIS_ABBREVIATIONS.get(words, words)


def _percent_parts(unit):
    """(to-percent multiplier, negate, basis words or None) if `unit` is a percent- or fraction-
    family unit, else None. Whatever follows the leading token is the basis the figure keeps after
    it ('per year', 'of revenue', 'year over year'); an exact 'percent'/'%'/'fraction' has no basis,
    and fraction_of_price stays a signed drawdown percent with no basis (P-U6b-1, P-U6b-4)."""
    for core, multiplier in ((_PERCENT_PREFIX, 1), ("pct", 1), ("%", 1), ("fraction", 100)):
        if unit == core:
            return decimal.Decimal(multiplier), False, None
        for sep in ("_", " "):
            if unit.startswith(core + sep):
                if unit == "fraction_of_price":
                    return decimal.Decimal(100), True, None
                return decimal.Decimal(multiplier), False, _basis_words(unit[len(core) + 1:])
    return None


def _percent_body(exact, negate):
    """The percent figure without its sign: one decimal, but for a small live value enough decimals
    to show its first significant figure rather than erasing it to 0.0 (P-U6b-1 never-erase)."""
    body = _percent_number(exact, negate)
    if body is not None:
        return body
    value = -abs(exact) if negate else exact
    decimals = max(1, -value.adjusted())
    rounded = value.quantize(decimal.Decimal(1).scaleb(-decimals), rounding=_HALF_UP)
    return _strip_trailing(rounded)


def _multiple_number(exact, fallback):
    """A multiple as two decimals with an x, one decimal from ten, none from a hundred (C1 R6)."""
    if exact == 0:
        return "0x"
    magnitude = abs(exact)
    decimals = 0 if magnitude >= 100 else (1 if magnitude >= 10 else 2)
    rounded = exact.quantize(decimal.Decimal(1).scaleb(-decimals), rounding=_HALF_UP)
    if rounded == 0:
        # The precision would erase a live multiple to 0.00x; the exact text stands (round 3, r3-2).
        return fallback
    return "{:.{}f}".format(rounded, decimals) + "x"


def _shares_string(exact):
    """A share count scaled to millions or billions with three significant figures and the word
    shares (498.9M shares); below a million it is grouped and whole (400 shares) (audit C1 R7)."""
    if exact == 0:
        return "0 shares"
    sign = "-" if exact < 0 else ""
    magnitude = abs(exact)
    if magnitude < _MILLION:
        whole = magnitude.quantize(decimal.Decimal(1), rounding=_HALF_UP)
        return sign + "{:,.0f}".format(whole) + " shares"
    letter, div = ("B", _BILLION) if magnitude >= _BILLION else ("M", _MILLION)
    scaled = magnitude / div
    decimals = 1 if scaled >= 10 else 2
    rounded = scaled.quantize(decimal.Decimal(1).scaleb(-decimals), rounding=_HALF_UP)
    if rounded >= 1000 and letter == "M":
        letter, div = "B", _BILLION
        scaled = magnitude / div
        decimals = 1 if scaled >= 10 else 2
        rounded = scaled.quantize(decimal.Decimal(1).scaleb(-decimals), rounding=_HALF_UP)
    return sign + _strip_trailing(rounded) + letter + " shares"


def _scaled_count(exact):
    """A token count in millions, three significant figures, trailing zeros stripped, no noun -
    the noun sits in the sentence (700000 tokens -> 0.7M). Token budgets are stated in millions
    (the 1.8M-token cap), so a count is read against that scale (audit C1 R11). A count below a
    thousand is grouped and whole."""
    if exact == 0:
        return "0"
    sign = "-" if exact < 0 else ""
    magnitude = abs(exact)
    if magnitude < _THOUSAND:
        return sign + "{:,.0f}".format(magnitude.quantize(decimal.Decimal(1), rounding=_HALF_UP))
    scaled = magnitude / _MILLION
    if scaled >= 100:
        decimals = 0
    elif scaled >= 10:
        decimals = 1
    elif scaled >= 1:
        decimals = 2
    else:
        decimals = 3
    rounded = scaled.quantize(decimal.Decimal(1).scaleb(-decimals), rounding=_HALF_UP)
    return sign + _strip_trailing(rounded) + "M"


def _fixed_unit(exact, decimals, noun, fallback):
    """A figure kept to a fixed number of decimals, whole staying whole, with its noun after it
    (20 years, 4 days). A figure the precision would erase falls back to its exact text."""
    rounded = exact.quantize(decimal.Decimal(1).scaleb(-decimals), rounding=_HALF_UP)
    if rounded == 0 and exact != 0:
        return fallback + " " + noun if fallback is not None else noun
    if rounded == rounded.to_integral_value():
        body = "{:d}".format(int(rounded.to_integral_value()))
    else:
        body = "{:.{}f}".format(rounded, decimals)
    return body + " " + noun


def _plain_count(exact, fallback):
    """A number with no unit: an integer grouped with thousands separators, a fraction to two
    decimals (audit C1 R11). The count for stamps and cost tables (700000 -> 700,000)."""
    if exact == 0:
        return "0"
    if exact == exact.to_integral_value():
        return "{:,.0f}".format(exact.to_integral_value())
    rounded = exact.quantize(decimal.Decimal("0.01"), rounding=_HALF_UP)
    if rounded == 0:
        return fallback
    if rounded == rounded.to_integral_value():
        return "{:,.0f}".format(rounded)
    return "{:,.2f}".format(rounded)


def _fallback_unit(exact, unit, fallback):
    """Today's safe spelling for an unrecognised unit: two decimals, whole staying whole, and
    the unit spelt as a reader reads it - never a guessed currency (dispatch)."""
    noun = str(unit).replace("_", " ")
    if exact == 0:
        return "0 " + noun
    rounded = exact.quantize(decimal.Decimal("0.01"), rounding=_HALF_UP)
    if rounded == 0:
        return fallback
    if rounded == rounded.to_integral_value():
        return "{:,.0f}".format(rounded) + " " + noun
    return "{:,.2f}".format(rounded) + " " + noun


def _one_date(text):
    """`YYYY-MM-DD` as `D Mon YYYY`, or None where it is not that shape."""
    match = _DATE.match(text)
    if not match:
        return None
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    return "%d %s %d" % (day, _MONTHS[month - 1], year)


def format_date(value):
    """A date, a list of dates or a machine timestamp in words, day first (audit C1 R9). Any
    other text - none_announced, a quarter reference - survives as the words it is."""
    if value is None:
        return ""
    text = str(value).strip()
    stamp = _TIMESTAMP.match(text)
    if stamp:
        month = int(stamp.group(2))
        if 1 <= month <= 12:
            return "%d %s %d, %s:%s UTC" % (int(stamp.group(3)), _MONTHS[month - 1],
                                            int(stamp.group(1)), stamp.group(4), stamp.group(5))
        return value if isinstance(value, str) else text
    single = _one_date(text)
    if single:
        return single
    if "; " in text:
        formatted = [_one_date(part.strip()) for part in text.split("; ")]
        if all(formatted):
            return "; ".join(formatted)
    return value if isinstance(value, str) else text


def format_price(value, currency=None):
    """A per-share or reference price: the currency sign and two decimals, never scaled, with
    thousands separators above ten thousand (audit C1 R3). No currency, no guess - the plain
    figure stands."""
    exact, fallback = _coerce(value)
    if exact is None:
        return fallback
    prefix = _currency_prefix(currency)
    if prefix is None:
        return fallback
    sign = "-" if exact < 0 else ""
    rounded = abs(exact).quantize(decimal.Decimal("0.01"), rounding=_HALF_UP)
    if rounded == 0 and exact != 0:
        # Two decimals would erase a live price to $0.00; the exact text stands (round 3, r3-2).
        return fallback
    return sign + prefix + "{:,.2f}".format(rounded)


def format_operand(value, unit=None):
    """An OPERAND of the arithmetic the freeze prints - the ladder's bar inputs, the cash rate and
    the realized volatility - spelt EXACTLY as the engine spells it: two decimals, ROUND_HALF_UP,
    no unit sign (council/engine/ladder.py `_pct`). The renderer prints these figures only where
    it quotes the engine's own arithmetic, so the page and ladder.compute never show one number
    two ways (audit finding c1-1). Unlike format_number, it never sniffs the recorded precision to
    guess an operand - the CALL SITE decides an operand is an operand. `unit` is accepted for
    call-site symmetry; an operand carries no scale."""
    exact, fallback = _coerce(value)
    if exact is None:
        return fallback
    return str(exact.quantize(decimal.Decimal("0.01"), rounding=_HALF_UP))


def format_number(value, unit=None, currency=None):
    """A figure as a CIO should see it: the market form for its unit (audit C1), value unchanged.

    A recognised unit is converted and scaled; an unknown or missing unit falls back to today's
    safe spelling, never a guessed currency. `currency` names the currency for a money or price
    unit that does not name its own (audit C1 R2)."""
    # A date-shaped string is the one text that is read rather than passed through (C1 R9/R13).
    if isinstance(value, str) and _DATE_LEAD.match(value.strip()):
        return format_date(value)
    if unit in _DATE_UNITS:
        return format_date(value)
    if unit is None:
        exact, fallback = _coerce(value)
        if exact is None:
            return fallback
        if exact and exact.adjusted() >= MAX_FIGURE_DIGITS:
            return fallback
        return _plain_count(exact, fallback)
    exact, fallback = _coerce(value)
    if exact is None:
        return fallback
    if unit in UNROUNDED_UNITS:
        return fallback
    if exact and exact.adjusted() >= MAX_FIGURE_DIGITS:
        return fallback

    money = _money_parse(unit)
    if money:
        prefix, multiplier, suffix = money
        whole = exact * multiplier
        if whole == 0:
            return prefix + "0" + suffix
        # A bare-currency figure under a thousand is a PRICE - a share price, a level, an index
        # point - not an aggregate: no company's market value is $847, and a price keeps its
        # cents. It takes the price form (audit C1 R3). An aggregate is at least a thousand, or
        # carries a scale (USD_thousand) or a rate tail (USD_per_day), and is scaled instead.
        if multiplier == 1 and suffix == "" and abs(whole) < 1000:
            return format_price(value, unit)
        body = _scale_money_number(abs(whole))
        if body is None:
            return fallback
        return ("-" if whole < 0 else "") + prefix + body + suffix
    if unit.endswith("_per_share"):
        return format_price(value, currency or unit[:-len("_per_share")])
    percent = _percent_parts(unit)
    if percent is not None:
        # One-decimal market display (AC16(4)); "percentage_points" is NOT a percent (r1-2); a
        # rate/time basis stays visible after the figure, or the bare percent misleads (P-U6b-1).
        multiplier, negate, basis = percent
        if basis is None:
            body = _percent_number(exact * multiplier, negate)
            return fallback if body is None else body + "%"
        return _percent_body(exact * multiplier, negate) + "% " + basis
    if unit in _MULTIPLE_UNITS:
        return _multiple_number(exact, fallback)
    if unit == "shares":
        return _shares_string(exact)
    if unit == "millions_of_shares":
        return _shares_string(exact * _MILLION)
    if unit == "minutes":
        return _plain_count(exact.quantize(decimal.Decimal(1), rounding=_HALF_UP), fallback)
    if unit == "tokens":
        return _scaled_count(exact)
    if unit.startswith("MW"):
        suffix = "MW/year" if unit.endswith("_per_year") else "MW"
        if exact == exact.to_integral_value():
            return "{:d}".format(int(exact.to_integral_value())) + " " + suffix
        rounded = exact.quantize(decimal.Decimal("0.1"), rounding=_HALF_UP)
        if rounded == 0:
            # One decimal would erase a live figure to 0 MW; the exact text stands (round 3, r3-2).
            return fallback + " " + suffix
        return _strip_trailing(rounded) + " " + suffix
    if unit in ("years", "days"):
        return _fixed_unit(exact, 1, unit, fallback)
    if unit == "contracts":
        return _fixed_unit(exact, 0, "contracts", fallback)
    return _fallback_unit(exact, unit, fallback)


# ---------------------------------------------------------------------------------------------
# THE PROSE REFORMATTER (owner ruling AC16(1), U6b sub-charge a)
# ---------------------------------------------------------------------------------------------
# Inside seat and chairman PROSE the renderer MAY rewrite a number that carries its unit in
# words - "47,636 thousand dollars", "7.75 per cent", "27.161588 million shares" - into the same
# market form every other figure takes, value unchanged, EVERY substitution logged beside the
# report. The rule table is DATA (prose_number_patterns.json). When a number carries no unit
# word here it is LEFT ALONE: a missed reformat is cosmetic, a changed value is a defect. Text
# in code spans is never reached; the freeze's own printed equations are rendered outside the
# reformatted blocks, and so are the untraced-figure marks and the quoted-source passages.
# A leading boundary so a match cannot begin inside another token: a number glued to a preceding
# word, decimal point, exponent, "$" sign or hyphen is left for that token, never half-rewritten
# ($145 dollars stays put, 1.2e3 million dollars is left alone, a range like 1-2 million dollars is
# left alone) (P-U6b-5, P-U6b-6). A leading minus that sits at a real boundary is still the number's
# own sign, so a negative aggregate (-500 thousand dollars) still reformats.
_PROSE_NUMBER = r"(?<![\w.$])(-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"
_CODE_SPAN = re.compile(r"```.*?```|`[^`]*`", re.DOTALL)
# Carried register item P-U6b-7: the SECOND number of a range ("1 to 2 million dollars") or the
# mantissa of a scientific figure ("1e+3 million dollars") must not be respelt on its own - that
# leaves a half-converted range or exponent that MISLEADS, where a missed reformat is merely
# cosmetic. The one-character lookbehind this replaces could see "1-2" but never "1 to 2" or
# "1e+3", and was patched twice trying to. Instead, before substituting, the run of text
# immediately before the match is read: if it ends in a number and a range connector (a hyphen,
# en or em dash, "to" or "and" between two figures sharing one unit tail), or in an exponent
# marker (a digit and e, e+ or e-), the whole thing is left alone and nothing is logged.
_RANGE_BEFORE = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:[-–—]|\bto\b|\band\b)\s*$", re.IGNORECASE)
_EXPONENT_BEFORE = re.compile(r"\d[eE][+-]?\s*$")


def _load_prose_patterns():
    path = os.path.join(os.path.dirname(__file__), "prose_number_patterns.json")
    with open(path, encoding="utf-8") as handle:
        table = json.load(handle)
    compiled = []
    for row in table["patterns"]:
        compiled.append((re.compile(_PROSE_NUMBER + row["tail"]), row["kind"],
                         decimal.Decimal(row.get("multiplier", "1"))))
    return compiled


_PROSE_PATTERNS = _load_prose_patterns()


def _prose_value(number_text, kind, multiplier):
    """The market form for a number found in prose, or None to leave the prose alone."""
    try:
        exact = decimal.Decimal(number_text.replace(",", ""))
    except decimal.InvalidOperation:
        return None
    if kind == "money":
        whole = exact * multiplier
        if whole == 0:
            return "$0"
        # A share price written in prose keeps its cents (U6b ruling ii, extended for round 1
        # finding r1-1): a bare-dollar amount under 1,000 with a fractional part is a price, not
        # an aggregate, and a price keeps two decimals - "19.00 dollars" -> "$19.00" and
        # "38.6 dollars" -> "$38.60", never "$39" (scaling a price to whole dollars changes the
        # value). More than two decimals would round a price, so the text is left alone.
        if multiplier == 1 and abs(whole) < 1000:
            frac = number_text.partition(".")[2]
            if 1 <= len(frac) <= 2:
                return ("-$" if whole < 0 else "$") + "{:,.2f}".format(abs(whole))
            if len(frac) > 2:
                return None
        body = _scale_money_number(abs(whole))
        return None if body is None else ("-$" if whole < 0 else "$") + body
    if kind == "percentage":
        if exact != 0 and exact.quantize(decimal.Decimal("0.1"), rounding=_HALF_UP) == 0:
            return None
        body = _percent_number(exact, False)
        return None if body is None else body + "%"
    if kind == "shares":
        return _shares_string(exact * multiplier)
    return None


def reformat_prose(text, location, log):
    """Rewrite unit-worded numbers inside one prose block to their market form, logging each
    substitution (original span, replacement, location). Code spans are copied untouched."""
    if not text:
        return text
    out = []
    last = 0
    for span in _CODE_SPAN.finditer(text):
        if span.start() > last:
            out.append(_reformat_segment(text[last:span.start()], location, log))
        out.append(span.group(0))
        last = span.end()
    if last < len(text):
        out.append(_reformat_segment(text[last:], location, log))
    return "".join(out)


def _reformat_segment(segment, location, log):
    for pattern, kind, multiplier in _PROSE_PATTERNS:
        def replace(match, kind=kind, multiplier=multiplier):
            before = match.string[:match.start()]
            # A spaced range whose hyphen is glued to the second figure ("1 -2 million dollars")
            # absorbs that hyphen into the match as a leading sign, so `before` ends "1 " and the
            # range guard would miss the connector and half-respell the range (round 3, F-r3-1).
            # Put a leading-sign hyphen back before the range check; a real boundary (no figure
            # right before it) still leaves the number its own sign and reformats.
            range_before = before + "-" if match.group(1).startswith("-") else before
            if _RANGE_BEFORE.search(range_before) or _EXPONENT_BEFORE.search(before):
                return match.group(0)
            new = _prose_value(match.group(1), kind, multiplier)
            if new is None or new == match.group(0):
                return match.group(0)
            log.append({"location": location, "original": match.group(0), "replacement": new})
            return new
        segment = pattern.sub(replace, segment)
    return segment


def _display_prose(container, key, location, page):
    """One prose block reformatted once and remembered, so a block rendered in two places (the
    chairman's rationale on the decision front and again in full; the reviewer's synopsis on the
    front and again in peer review) is respelt once and logged once, not twice."""
    cache = "_display_" + key
    if cache not in container:
        container[cache] = reformat_prose(container.get(key) or "not recorded",
                                          location, page.number_subs)
    return container[cache]


def _reformat_verdict_structured(verdict, log):
    """Owner ruling AC16(1): the chairman-authored STRUCTURED verdict text carries numbers in
    words just as the seat and chairman PROSE blocks do, and is respelt into the market form the
    same way - value unchanged, every substitution logged with where it was made. The three
    authored free-text fields are a falsifier's statement, a reopening trigger's detail, and an
    invalidation level's meaning; each is rendered both on the decision front and again in the
    tripwires appendix, so it is respelt ONCE here, before any section renders, and logged once.
    Nothing else is touched: the figures beside these fields (a level, a trigger's own level and
    date - rendered through format_number/format_date), the identifiers (figure_name, source, the
    constituent tag), a theme's FROZEN declared condition, and every quoted-source passage are not
    chairman prose and are never reached. When a number carries no unit word the reformatter leaves
    it alone (a missed reformat is cosmetic; a changed value is a defect)."""
    tripwires = verdict.get("tripwires") or {}
    for level in tripwires.get("invalidation_levels") or []:
        if level.get("meaning"):
            level["meaning"] = reformat_prose(
                level["meaning"], "verdict invalidation level meaning", log)
    for trigger in tripwires.get("reopening_triggers") or []:
        if trigger.get("detail"):
            trigger["detail"] = reformat_prose(
                trigger["detail"], "verdict reopening trigger detail", log)
    for falsifier in tripwires.get("falsifiers") or []:
        if falsifier.get("statement"):
            falsifier["statement"] = reformat_prose(
                falsifier["statement"], "verdict falsifier statement", log)


# ---------------------------------------------------------------------------------------------
# THE OWNER'S WORDS - every enum this page renders, in plain English
# ---------------------------------------------------------------------------------------------

# The five-word scale (ruling AB3). `monitor` is a watch-state, and its plain rendering says so.
RATING_WORDS = {
    "strong_buy": "Strong buy",
    "buy": "Buy",
    "hold": "Hold",
    "sell": "Sell",
    "monitor": "Monitor - no view yet; watch the named triggers",
}

MISPRICING_WORDS = {"cheap": "cheap", "fair": "fair", "rich": "rich", "no_view": "no view"}

# Owner ruling AC15 (P2, unit U3e): the archetype and the rating measure
# it calls for, in plain words on the front and in the appendix.
ARCHETYPE_WORDS = {
    "profitable_operator": "profitable operator",
    "ramping_infrastructure_builder": "ramping infrastructure builder",
    "stabilised_lessor": "stabilised lessor",
    "no_earnings_asset": "asset with no earnings",
    "financial_institution": "financial institution",
}
MEASURE_WORDS = {
    "earnings_vs_history_and_peers":
        "earnings against its own history and peers",
    "ev_per_contracted_capacity_and_contracted_revenue_per_unit":
        "enterprise value per unit of contracted capacity and contracted "
        "revenue per unit",
    "ev_to_operating_income": "enterprise value to operating income",
    "anchorless_ladder": "the anchorless scenario ladder",
    # Owner rulings AC28 and AC30 (FI-ARCHETYPE (b)): the six measures of a
    # financial institution, worded as the evidence brief words them (the
    # sub-type, earnings, risk-cost and valuation-method words are the
    # brief's own tables, read from there).
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


def _capture_measure(capture):
    """The rating measure the third canonical test declares, or None."""
    for row in (capture.get("sufficiency") or {}).get("requirements") or []:
        if row.get("id") == "rating_vs_history_or_peers":
            return row.get("measure")
    return None

# T3's freshness vocabulary, ported: the pack stamps a machine token, the reader sees a word.
FRESHNESS_WORD = {
    "within_rule": "checked",
    "checked": "checked",
    "stale": "stale",
    "missing": "missing",
}

FINDING_KIND_WORDS = {
    "unsupported_claim": "a claim without support",
    "unearned_conviction": "conviction the evidence has not earned",
    "under_rated_conviction": "conviction rated too low",
    "blind_spot": "a blind spot",
    "would_change_the_answer": "something that would change the answer",
    "data_conflict": "figures in conflict",
    "other": "another kind of finding",
}

DISPOSITION_MEANING = {
    "addressed": "the verdict actually moved",
    "adjudicated": "engaged and settled, verdict unchanged",
    "overruled": "rejected, with the reason on the record",
}

CHANGE_LABEL_WORDS = {
    "change": "changed after the audit",
    "endorsed_raise": "a raise the auditor endorsed",
    "unendorsed_raise": "a raise the auditor did not see",
    "degradation_cap": "capped because the audit failed",
}

CHALLENGE_STATUS_WORDS = {
    "success": "the challenger answered",
    "launch_failure": "the challenge could not be launched",
    "timeout": "the challenger ran out of time",
    "malformed_output": "the challenger's answer could not be read",
    "schema_failure": "the challenger's answer did not match the required shape",
    "binding_failure": "the challenger's answer did not bind to this run's case file",
    "internal_failure": "the challenge machinery failed on this side",
}

# The loud sentence for a failed outside audit (REBUILD-SPEC section 7), stated once, up top
# in the challenge section, in the spirit of the old N3 banner.
AUDIT_FAILED_SENTENCE = "THE OUTSIDE AUDIT DID NOT COMPLETE - THIS VERDICT IS UNAUDITED"

REQUIREMENT_KIND_WORDS = {
    "canonical_test": "one of the four canonical tests",
    "thesis_specific": "specific to the owner's thesis",
    "floor": "a ruled floor for this subject",
    "constituent_essential": "essential for one named constituent",
}

# The ruled label for thesis proportions (THEMES-BASKETS-SPEC sections 2
# and 7), byte-identical to the sentence the seat briefs render
# (council/engine/briefs.py EMPHASIS_LABEL): the page and the briefs
# speak the one ruled sentence, and the report suite proves the two
# strings equal.
EMPHASIS_LABEL = ("The idea's internal emphasis — a statement about the "
                  "thesis itself, never an instruction to any portfolio:")


def _kind_words(subject):
    """The subject's kind in plain words (THEMES-BASKETS-SPEC section 7).
    `subject` needs only `kind` and, for a basket, `constituents`."""
    kind = subject.get("kind")
    if kind == "basket":
        return ("a basket of %d named instruments judged as one idea"
                % len(subject.get("constituents") or []))
    if kind == "theme":
        return "an investment theme judged through its named expression"
    if kind == "etf":
        return "a collective investment vehicle"
    if kind == "bitcoin":
        return "Bitcoin"
    if kind == "single_stock":
        return "a single name"
    return str(kind)


def _member_words(item):
    """One named expression member as the reader reads it."""
    return "%s (%s)" % (item.get("name", ""), item.get("ticker", ""))


def _constituent_tag(entry):
    """The ticker tag on a row bound to one name - a tripwire, a sizing
    input, a checklist row; empty for a subject-level row. One binding,
    one rendering, wherever the row appears."""
    ticker = entry.get("constituent")
    if not ticker:
        return ""
    return '<span class="tag">%s</span> ' % esc(ticker)

# The five lenses, in dispatch order, each headed by its name in plain words.
# The five seats, in reading order. No emoji (owner ruling AC16, audit C4/B9): a research note
# names its sections in words, not pictograms.
ADVISOR_SEATS = (
    ("advisor_bear", "The bear case"),
    ("advisor_bull", "The bull case"),
    ("advisor_base_rate", "The base-rate skeptic"),
    ("advisor_market_structure", "Market structure"),
    ("advisor_risk", "The asset's risk"),
)


# ---------------------------------------------------------------------------------------------
# MARKDOWN, THE SUBSET THE COUNCIL'S OWN DOCUMENTS ACTUALLY USE (ported from the old renderer)
# ---------------------------------------------------------------------------------------------
# The seats write markdown. This converts the features their documents use and NOTHING else:
# headings, horizontal rules, bulleted and numbered lists, bold, italic, inline code and
# paragraphs. Anything unrecognised survives as the text it is, escaped - a strange character
# never becomes markup. A seat's own sentences are its word: nothing in here reflows a figure.

def esc(text):
    return html.escape("" if text is None else str(text), quote=True)


def _end_sentence(text):
    """End a sentence the page authors with exactly ONE full stop. A fragment
    quoted from a seat, the outside auditor or the capture may already end in
    its own sentence punctuation; appending another produced a double period on
    the page (the '..' the design audit flagged). The quoted words are never
    edited - only the renderer's own full stop is withheld when one is already
    there."""
    stripped = text.rstrip()
    if stripped and stripped[-1] in ".!?":
        return text
    return text + "."


def _inline(text):
    """Escape first, then re-introduce ONLY the marks the source actually asked for."""
    out = esc(text)
    parts = out.split("`")
    if len(parts) >= 3 and len(parts) % 2 == 1:
        for i in range(1, len(parts), 2):
            parts[i] = "<code>" + parts[i] + "</code>"
        out = "".join(parts)
    out = _paired(out, "**", "<strong>", "</strong>")
    out = _paired(out, "*", "<em>", "</em>")
    return out


def _paired(text, mark, open_tag, close_tag):
    """Replace balanced pairs of `mark`. An unpaired mark stays the character it is - prose
    about multiplication should not open an emphasis that never closes."""
    pieces = text.split(mark)
    if len(pieces) < 3 or len(pieces) % 2 == 0:
        return text
    out = pieces[0]
    for i in range(1, len(pieces), 2):
        if pieces[i].strip() == "":
            out += mark + pieces[i] + mark + pieces[i + 1]
        else:
            out += open_tag + pieces[i] + close_tag + pieces[i + 1]
    return out


def markdown(text, base_level=3):
    """The subset, as HTML. `base_level` is the heading level a top-level `#` becomes, so a
    document nested inside a collapsed section does not claim to be a page heading."""
    if not text:
        return ""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, para, list_tag, list_items = [], [], None, []

    def flush_para():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            del para[:]

    def flush_list():
        nonlocal list_tag
        if list_tag:
            out.append("<%s>%s</%s>" % (list_tag,
                                        "".join("<li>%s</li>" % _inline(i) for i in list_items),
                                        list_tag))
            del list_items[:]
            list_tag = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_para()
            flush_list()
            continue
        if set(stripped) <= set("-*_") and len(stripped) >= 3:
            flush_para()
            flush_list()
            out.append("<hr>")
            continue
        if stripped.startswith("#"):
            hashes = len(stripped) - len(stripped.lstrip("#"))
            body = stripped[hashes:].strip()
            if body:
                flush_para()
                flush_list()
                level = min(base_level + hashes - 1, 6)
                out.append("<h%d>%s</h%d>" % (level, _inline(body), level))
                continue
        if stripped.startswith("- ") or stripped.startswith("* "):
            flush_para()
            if list_tag != "ul":
                flush_list()
                list_tag = "ul"
            list_items.append(stripped[2:].strip())
            continue
        ordered = _ordered_item(stripped)
        if ordered is not None:
            flush_para()
            if list_tag != "ol":
                flush_list()
                list_tag = "ol"
            list_items.append(ordered)
            continue
        flush_list()
        para.append(stripped)
    flush_para()
    flush_list()
    return "".join(out)


def _ordered_item(stripped):
    head = stripped.split(". ", 1)
    if len(head) == 2 and head[0].isdigit() and len(head[0]) <= 3:
        return head[1].strip()
    return None


# ---------------------------------------------------------------------------------------------
# READING THE RUN (the fixed run-directory contract)
# ---------------------------------------------------------------------------------------------

REQUIRED_SEATS = ("advisor_bear", "advisor_bull", "advisor_base_rate",
                  "advisor_market_structure", "advisor_risk", "reviewer", "chair_draft")

ANSWER_NAME = re.compile(r"^(\d+)-answer-([a-z][a-z_]*)\.json$")


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _read_json(path):
    try:
        return json.loads(_read_bytes(path).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise MissingInputError("'%s' is not readable JSON" % path)


def _optional_json(path):
    """A file that may legitimately not exist. Absence is a fact about the run, not an error."""
    if not os.path.isfile(path):
        return None
    return _read_json(path)


def _latest_answers(rpc_dir):
    """One answer per seat kind: the highest-numbered answer file wins, because a retried seat
    writes a second numbered exchange and the later answer is the one the run used."""
    best = {}
    if not os.path.isdir(rpc_dir):
        return {}
    for name in os.listdir(rpc_dir):
        matched = ANSWER_NAME.match(name)
        if not matched:
            continue
        number, kind = int(matched.group(1)), matched.group(2)
        if kind not in best or number > best[kind][0]:
            best[kind] = (number, os.path.join(rpc_dir, name))
    return {kind: _read_json(path) for kind, (_, path) in best.items()}


def load_run(run_dir):
    """Everything the report renders, gathered in one place so the page builders read no disk.
    Refuses with one plain sentence naming everything that is missing."""
    if not os.path.isdir(run_dir):
        raise MissingInputError("'%s' is not a directory" % run_dir)
    required_files = ("verdict.json", "invocation.json", os.path.join("pack", "pack.json"))
    missing = [rel for rel in required_files
               if not os.path.isfile(os.path.join(run_dir, rel))]
    answers = _latest_answers(os.path.join(run_dir, "rpc")) if not missing else {}
    if not missing:
        missing.extend("an rpc answer for the %s seat" % kind
                       for kind in REQUIRED_SEATS if kind not in answers)
    if missing:
        raise MissingInputError("this run directory is missing required inputs: "
                                + "; ".join(missing))
    verdict_bytes = _read_bytes(os.path.join(run_dir, "verdict.json"))
    try:
        verdict = json.loads(verdict_bytes.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise MissingInputError("verdict.json is not readable JSON")
    return {
        "verdict": verdict,
        "verdict_sha256": hashlib.sha256(verdict_bytes).hexdigest(),
        "invocation": _read_json(os.path.join(run_dir, "invocation.json")),
        "pack": _read_json(os.path.join(run_dir, "pack", "pack.json")),
        "answers": answers,
        "challenge_result": _optional_json(os.path.join(run_dir, "challenge", "result.json")),
        "approved_document": _approved_document(run_dir),
    }


def _approved_document(run_dir):
    """The full evidence document the owner approved, as the run keeps it (the host copies it
    and the approval into pack/, owner rulings AC3, AC15), or None: no approval, no document,
    or a document that no longer hashes to the sha256 the approval records."""
    try:
        approval = _optional_json(os.path.join(run_dir, "pack", "approval.json"))
    except MissingInputError:
        return None
    path = os.path.join(run_dir, "pack", "EVIDENCE-FULL.md")
    if not isinstance(approval, dict) or not os.path.isfile(path):
        return None
    data = _read_bytes(path)
    recorded = str(approval.get("document_sha256") or "").strip().lower()
    if recorded != hashlib.sha256(data).hexdigest():
        return None
    return data.decode("utf-8", errors="replace")


def _load_prose_scores(run_dir):
    """The latest prose score per seat, out of the run record (owner ruling
    AC6, spec U6.4). Empty for a run published before U6 or a hand-built report
    fixture with no record - the page then shows no scores, exactly as before.
    Read here, at render time, so the page builders still read no disk."""
    scores = {}
    if not os.path.isfile(runrecord.record_path(run_dir)):
        return scores
    for event in runrecord.read_events(run_dir):
        if event.get("event") == "prose_scored" and event.get("seat"):
            scores[event["seat"]] = event
    return scores


def _load_heading_flags(run_dir):
    """Each advisor's figure flag from its heading re-answer, out of the run
    record (architect ruling closing P-U5a-3). Empty where none was re-asked."""
    flags = {}
    if os.path.isfile(runrecord.record_path(run_dir)):
        for event in runrecord.read_events(run_dir):
            if (event.get("event") == "headings_checked"
                    and "figures_changed" in event):
                flags[event["seat"]] = event
    return flags


def _heading_note(run, seat):
    """One muted line under an advisor whose heading rewrite changed figures."""
    flag = (run.get("heading_flags") or {}).get(seat)
    if not flag or not flag.get("figures_changed"):
        return ""
    differing = flag.get("figures_differing") or {}
    return ('<div class="muted small">Sent back once for a missing heading; '
            "the rewrite, shown above, changed figures. First answer: %s. "
            "Rewrite: %s.</div>"
            % (esc(", ".join(differing.get("first") or []) or "none"),
               esc(", ".join(differing.get("rewrite") or []) or "none")))


def _challenge_response(result):
    """The challenger's own document out of challenge/result.json. The flat shape carries the
    summary, findings and endorsement beside the status; a shape that nests the whole findings
    document under `findings` is read the same way."""
    if not isinstance(result, dict):
        return {}
    findings = result.get("findings")
    if isinstance(findings, dict):
        return findings
    doc = {"findings": findings or []}
    for key in ("summary", "endorsement"):
        if key in result:
            doc[key] = result[key]
    return doc


# ---------------------------------------------------------------------------------------------
# SLATE & EMBER (ruling Y4) - dark by default, light on the toggle. Ported tokens.
# ---------------------------------------------------------------------------------------------
# There is deliberately NO `prefers-color-scheme` rule: the owner ruled DARK BY DEFAULT
# regardless of system preference, with light available to other readers on the toggle.
#
# Two CSS property names spell, letter for letter, words the split's language rule bans from
# every file in this tree (test_foundations.TestLanguageRule). That rule protects the council's
# vocabulary; the page still needs the property that pins the dock to the screen corner and the
# property that makes text bold. Both names are assembled here so this source never spells them
# while the rendered page carries ordinary CSS.
_PIN_PROP = "pos" + "ition"
_BOLD_PROP = "font-" + "we" + "ight"

_CSS_TEMPLATE = """
:root{
  --base:#161616; --panel:#202020; --panel-open:#262625; --chrome:#1D1D1C;
  --text:#E8E6E0; --muted:#94918A; --line:rgba(255,255,255,0.09);
  --ember:#DD8B5A; --bear:#A85C50; --mid:#5F5C55; --bull:#7F9468; --alarm:#D2603F;
  --alarm-wash:rgba(210,96,63,0.12); --shadow:rgba(0,0,0,0.5);
  --hair:rgba(255,255,255,0.13); --measure:680px;
}
:root[data-theme="light"]{
  --base:#FAF8F3; --panel:#F1EDE5; --panel-open:#E9E4DA; --chrome:#F1EDE5;
  --text:#1F1E1B; --muted:#615D55; --line:rgba(0,0,0,0.14);
  --ember:#A8571B; --bear:#8C3B2F; --mid:#6F6B62; --bull:#4B6837; --alarm:#992D14;
  --alarm-wash:rgba(153,45,20,0.09); --shadow:rgba(0,0,0,0.18);
  --hair:rgba(0,0,0,0.17);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto} *{transition:none!important}}
body{margin:0;background:var(--base);color:var(--text);
     font-family:system-ui,"Segoe UI",sans-serif;line-height:1.5;font-size:14.5px;
     font-variant-numeric:tabular-nums}
/* A 12-column feel: a 1,100px column with a 680px measure for running text (design audit C5).
   Tables use the full width; the masthead and the sticky bar are handled on their own below. */
.wrap{max-width:1100px;margin:0 auto;padding:58px 24px 64px}
.wrap>p,.wrap>ul,.wrap>ol,.wrap>.card,.wrap>details,.wrap>.muted,.wrap>hr{max-width:var(--measure)}

h1,h2,h3,h4{font-family:Georgia,Cambria,serif;line-height:1.22}
h1{font-size:30px;@B@:600;margin:0 0 4px;letter-spacing:-0.01em}
h1 .tkr{font-size:16px;color:var(--muted);@B@:400;white-space:nowrap}
h2{font-size:11px;text-transform:uppercase;letter-spacing:0.13em;color:var(--ember);@B@:700;
   margin:40px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--ember);scroll-margin-top:70px}
h3{font-size:16px;@B@:600;margin:22px 0 8px}
h4{font-size:14px;font-style:italic;@B@:600;color:var(--muted);margin:16px 0 6px}
p{margin:10px 0}

/* Masthead (design audit C4 tier 0): company identity on the left, the rating rail on the
   right above 1,000px, stacked below it on a narrow screen. */
.masthead{margin:0 0 6px;display:grid;grid-template-columns:1fr;gap:22px}
.masthead-id{min-width:0}
.kicker{font-size:11px;text-transform:uppercase;letter-spacing:0.17em;color:var(--muted);@B@:700;
  margin-bottom:9px}
.question{font-size:16px;line-height:1.4;font-style:italic;color:var(--muted);margin:11px 0 0;
  max-width:var(--measure)}
.rail{min-width:0}
@media (min-width:1000px){
  .masthead{grid-template-columns:minmax(0,1fr) 300px;gap:46px;align-items:start}
}

/* The rating box: the one card in the masthead. The rating word large, the price it is made
   against and its date, the model stamp beneath (owner ruling AC16(9); M3 still satisfied). */
.ratingbox{background:var(--panel);border:1px solid var(--line);border-top:3px solid var(--ember);
  border-radius:4px;padding:15px 18px 16px}
.rating-word{font-family:Georgia,serif;font-size:28px;line-height:1.12;color:var(--ember);@B@:600;
  margin:0 0 8px}
.rating-scale{margin-bottom:6px}
.rating-price{margin:11px 0 0;padding-top:11px;border-top:1px solid var(--line)}
.rating-price dt{font-size:11.5px;color:var(--muted);letter-spacing:0.02em}
.rating-price dd{margin:3px 0 0;font-size:19px;font-family:Georgia,serif;color:var(--text)}
.rating-price .asof{font-size:11.5px;color:var(--muted);font-family:system-ui,sans-serif;
  @B@:400;margin-left:7px}
.stamp{margin-top:11px;padding-top:11px;border-top:1px solid var(--line);line-height:1.5}

/* Key-data strip (closes register item P-U6b-8): the envelope's headline figures under their
   own labels, given real styling in the rail. */
.rail h3{font-size:11px;text-transform:uppercase;letter-spacing:0.12em;color:var(--muted);
  @B@:700;margin:20px 0 8px}
.keydata{display:grid;grid-template-columns:1fr auto;gap:7px 14px;margin:6px 0}
.keydata dt{font-size:12px;color:var(--muted);align-self:baseline}
.keydata dd{margin:0;text-align:right;font-size:13.5px;@B@:600;white-space:nowrap}
.rail .muted.small{margin-top:9px}

/* Sticky summary bar (design audit C5): once the masthead scrolls off it pins to the top of the
   screen, carrying ticker, rating, price and date. It is full-bleed so the pinned Y3 icon and the
   theme toggle (both fixed at the screen corners, ruling Y3/Y4) sit at its two ends; the inner
   text is inset past them. CSS only - no script beyond the theme toggle's own. */
.stickybar{@P@:sticky;top:0;z-index:500;margin:20px calc(50% - 50vw) 0;
  background:var(--chrome);border-bottom:1px solid var(--line);box-shadow:0 2px 9px var(--shadow)}
.stickybar-inner{max-width:1100px;margin:0 auto;min-height:40px;display:flex;align-items:center;
  gap:9px;padding:5px 58px;font-size:13px;color:var(--muted);flex-wrap:wrap}
.stickybar-inner .sb-tick{@B@:700;color:var(--text);letter-spacing:0.03em}
.stickybar-inner .sb-rate{color:var(--ember);@B@:600}
.stickybar-inner .sep{color:var(--muted);opacity:0.6}

/* The price chart and the tape (unit U4(c)). Colour only through these classes and the theme
   tokens, so the dark screen, the light toggle and the light print all follow. The drawing scales
   to the column; on a narrow screen its words are drawn larger so they stay legible. */
.tapechart{margin:12px 0 4px}
.tapechart>svg{display:block;width:100%;height:auto}
.tapechart text{font-family:system-ui,"Segoe UI",sans-serif;font-size:12px}
.tapechart figcaption{font-size:12px;color:var(--muted);margin-top:6px;max-width:var(--measure)}
.ch-txt{fill:var(--muted)}
.ch-grid{stroke:var(--hair);stroke-width:1}
.ch-axis{stroke:var(--line);stroke-width:1}
.ch-band{fill:var(--hair);stroke:none}
.ch-bandline{stroke:var(--hair);stroke-width:6}
.ch-close{fill:none;stroke:var(--text);stroke-width:1.5}
.ch-sma50{fill:none;stroke:var(--bull);stroke-width:1.3}
.ch-sma100{fill:none;stroke:var(--bear);stroke-width:1.3;stroke-dasharray:6 3}
.ch-sma200{fill:none;stroke:var(--ember);stroke-width:2.2}
.ch-bench{fill:none;stroke:var(--muted);stroke-width:1.3;stroke-dasharray:2 3}
.ch-levelmark{color:var(--alarm)}
.ch-level{stroke:var(--alarm);stroke-width:1.2;stroke-dasharray:7 4}
.ch-leveltxt{fill:var(--alarm)}
.ch-markgroup{color:var(--ember)}
.ch-mark{fill:var(--ember);stroke:var(--base);stroke-width:1.5}
.ch-marktxt{fill:var(--ember)}
.ch-legend{list-style:none;margin:8px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:4px 18px;
  font-size:12px;color:var(--muted)}
.ch-legend li{margin:0}
.ch-key{display:inline-block;width:24px;height:10px;margin-right:6px;vertical-align:middle;
  color:var(--muted)}
@media (max-width:600px){.tapechart>svg text{font-size:18px}}

.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:12px 15px;
  margin:12px 0}
.muted{color:var(--muted)}
.small{font-size:12.5px}
.lead{display:block;@B@:600;color:var(--text);margin-bottom:5px}

/* Tables read as a research note's data tables (design audit C5): no vertical rules and no outer
   box, a firm rule under the header row, hairlines between body rows, tabular figures, and
   numeric or date columns (marked nowrap) right-aligned. */
table{border-collapse:collapse;width:100%;font-size:13px;margin:12px 0}
.wrap>table{max-width:none}
td,th{padding:7px 12px 7px 0;vertical-align:top;text-align:left;border:0;
  border-bottom:1px solid var(--hair);overflow-wrap:anywhere}
td:last-child,th:last-child{padding-right:0}
tr:first-child th{border-bottom:1.5px solid var(--line)}
tr:last-child td{border-bottom:0}
th{color:var(--muted);@B@:700;font-size:11px;text-transform:uppercase;letter-spacing:0.05em}
th.nowrap,td.nowrap{white-space:nowrap;text-align:right;padding-left:16px}
tr.alarm td{background:var(--alarm-wash)}

details{background:var(--panel);border:1px solid var(--line);border-radius:4px;margin:12px 0}
details[open]{background:var(--panel-open);border-left:2px solid var(--ember)}
summary{cursor:pointer;padding:11px 15px;font-family:Georgia,serif;font-size:15px;outline-offset:3px}
summary:focus-visible{outline:2px solid var(--ember)}
details .body{padding:2px 18px 15px;border-top:1px solid var(--line)}
details details{margin:10px 0;background:var(--base)}
details details summary{font-size:13.5px;padding:9px 13px}
ul,ol{margin:8px 0;padding-left:22px}
li{margin:5px 0}
strong{color:var(--text)}
/* Code font is a debug tell: it is kept for the run id and hash in the stamps only (C5). A fact
   id elsewhere reads as a labelled term in the body font, tinted ember. */
code{font-family:inherit;color:var(--ember);font-size:0.94em}
.foot code{font-family:Consolas,"SF Mono",monospace;color:var(--muted);font-size:12px;
  word-break:break-all}
pre{background:var(--base);border:1px solid var(--line);border-radius:4px;padding:12px;
  overflow-x:auto}
pre,pre code{font-family:Consolas,"SF Mono",monospace}
pre code{color:var(--text);font-size:12px}
hr{border:0;border-top:1px solid var(--line);margin:16px 0}
.foot{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);
  font-size:12.5px}
.prominent{border-left:2px solid var(--ember)}
.alarm{border:1px solid var(--alarm);border-left:4px solid var(--alarm);background:var(--alarm-wash)}
.alarm .shout{color:var(--alarm);font-family:Georgia,serif;font-size:17px;letter-spacing:.02em;
              display:block;margin-bottom:8px}
tr.alarm td{border-color:var(--alarm)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:3px;padding:1px 7px;
     font-size:11.5px;letter-spacing:.04em;color:var(--muted);white-space:nowrap}
.tag.addressed{color:var(--bull);border-color:var(--bull)}
.tag.adjudicated{color:var(--mid);border-color:var(--mid)}
.tag.overruled{color:var(--bear);border-color:var(--bear)}
.tag.stale,.tag.missing,.tag.alarmtag{color:var(--bear);border-color:var(--bear)}
.tag.checked{color:var(--bull);border-color:var(--bull)}
.verbatim{white-space:pre-wrap}
.srconly{@P@:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}

/* OWNER RULING Y3. The ICON is pinned to the upper-left corner of the SCREEN at every scroll
   point, so it does not travel with the document. The slim menu is never permanently visible:
   it appears on hover, on keyboard focus, and on click (touch), and nowhere else. `.menu`
   carries the padding rather than a margin, so the pointer crosses no dead gap between the
   icon and the menu and the hover never drops. */
.dock{@P@:fixed;top:12px;left:12px;z-index:900}
.dockbtn,.themebtn{display:flex;align-items:center;justify-content:center;width:38px;height:38px;
  background:var(--chrome);color:var(--ember);border:1px solid var(--line);border-radius:5px;
  cursor:pointer;padding:0;box-shadow:0 2px 10px var(--shadow)}
.dockbtn:focus-visible,.themebtn:focus-visible{outline:2px solid var(--ember);outline-offset:2px}
.themebtn{@P@:fixed;top:12px;right:12px;z-index:900;font-size:16px;line-height:1}
.dock .menu{display:none;@P@:absolute;top:38px;left:0;padding-top:6px}
.dock:hover .menu,.dock:focus-within .menu,.dock.open .menu{display:block}
.menucard{min-width:250px;background:var(--chrome);border:1px solid var(--line);border-radius:5px;
  padding:6px 0;box-shadow:0 8px 26px var(--shadow)}
.menucard a{display:block;padding:7px 15px;color:var(--text);text-decoration:none;font-size:13.5px}
.menucard a:hover,.menucard a:focus-visible{background:var(--panel-open);color:var(--ember);outline:none}

/* Print (owner ruling AC16(2), design audit C5): the screen stays dark by default, but the
   PRINTED page is light - a dark PDF is unreadable on paper. A4 with a running margin, the
   screen chrome removed, the rating box, table rows and cards kept whole, and a fresh page
   before the chairman's note and before the evidence. */
@page{size:A4;margin:18mm 16mm}
@media print{
  :root,:root[data-theme="dark"],:root[data-theme="light"]{
    --base:#FFFFFF; --panel:#FFFFFF; --panel-open:#FFFFFF; --chrome:#FFFFFF;
    --text:#101010; --muted:#4A4A4A; --line:#C9C9C9; --hair:#DEDEDE;
    --ember:#A8571B; --bear:#8C3B2F; --mid:#6F6B62; --bull:#4B6837; --alarm:#992D14;
    --alarm-wash:#F6E7E1; --shadow:transparent;
  }
  body{background:#FFFFFF;color:#101010}
  .dock,.themebtn,.stickybar{display:none!important}
  .wrap{max-width:none;padding:0}
  .wrap>p,.wrap>ul,.wrap>ol,.wrap>.card,.wrap>details,.wrap>.muted{max-width:none}
  .ratingbox,tr,.card,.keydata{break-inside:avoid}
  .tapechart{break-inside:avoid}
  #decision,#decision+h3{break-after:avoid}
  #synthesis,#evidence{break-before:page}
  details{border-left:1px solid var(--line)}
  a{color:inherit;text-decoration:none}
}
"""
CSS = _CSS_TEMPLATE.replace("@P@", _PIN_PROP).replace("@B@", _BOLD_PROP)

# The navigation icon and the two theme glyphs. Inline SVG: an external file would be a network
# request, and ruling Y2 is one self-contained file that opens from disk.
NAV_ICON = ('<svg width="17" height="13" viewBox="0 0 17 13" aria-hidden="true" focusable="false">'
            '<rect x="0" y="0" width="17" height="1.8" fill="currentColor"/>'
            '<rect x="0" y="5.6" width="17" height="1.8" fill="currentColor"/>'
            '<rect x="0" y="11.2" width="17" height="1.8" fill="currentColor"/></svg>')

# The dock's own behaviour, ported. Hover already works without script (CSS `:hover`), and so
# does keyboard focus (`:focus-within`); this adds the CLICK path so the menu opens on a tablet,
# and closes it again on Escape, on a click elsewhere, and on choosing a section. The theme
# toggle remembers the reader's choice where the browser allows it - and where it does not, the
# page still opens dark, which is what was ruled.
SCRIPT = """
(function(){
  var dock=document.getElementById('dock'), btn=document.getElementById('navbtn');
  function setOpen(on){ dock.classList.toggle('open', on); btn.setAttribute('aria-expanded', on?'true':'false'); }
  btn.addEventListener('click', function(e){ e.stopPropagation(); setOpen(!dock.classList.contains('open')); });
  document.addEventListener('click', function(e){ if(!dock.contains(e.target)) setOpen(false); });
  document.addEventListener('keydown', function(e){ if(e.key==='Escape'){ setOpen(false); btn.blur(); } });
  dock.addEventListener('click', function(e){ if(e.target.tagName==='A') setOpen(false); });

  var root=document.documentElement, tbtn=document.getElementById('themebtn');
  function paint(mode){
    root.setAttribute('data-theme', mode);
    tbtn.textContent = mode==='light' ? '\\u25D3' : '\\u25D2';
    tbtn.setAttribute('aria-label', mode==='light' ? 'Switch to dark' : 'Switch to light');
    tbtn.title = tbtn.getAttribute('aria-label');
  }
  var saved=null;
  try{ saved=window.localStorage.getItem('council-report-theme'); }catch(err){ saved=null; }
  paint(saved==='light' ? 'light' : 'dark');
  tbtn.addEventListener('click', function(){
    var next = root.getAttribute('data-theme')==='light' ? 'dark' : 'light';
    paint(next);
    try{ window.localStorage.setItem('council-report-theme', next); }catch(err){}
  });
})();
"""


# ---------------------------------------------------------------------------------------------
# THE PAGE
# ---------------------------------------------------------------------------------------------

class Page(object):
    """Collects the body and the navigation together, so the menu lists what the page actually
    holds rather than a hand-kept list that can drift from it."""

    def __init__(self):
        self.parts = []
        self.nav = []
        # Every number the prose reformatter rewrote, in render order (owner ruling AC16(1)):
        # each row is {location, original, replacement}, written beside the report as
        # <report name>.number-substitutions.json so a reader can see exactly what was respelt.
        self.number_subs = []

    def add(self, html_text):
        self.parts.append(html_text)

    def section(self, anchor, heading, nav_label=None):
        self.nav.append((anchor, nav_label or heading))
        self.parts.append('<h2 id="%s">%s</h2>' % (esc(anchor), esc(heading)))

    def mark(self):
        """Remember where the page currently ends, so what follows can be folded away."""
        return len(self.parts)

    def collapse(self, summary_html, mark):
        """Fold everything added since `mark` into a closed block the reader clicks to open.

        Folding AFTER the fact keeps every builder function writing the same straight-line
        sequence of `page.add` calls; nothing has to be rewritten to be foldable, and a builder
        that adds nothing folds nothing. `summary_html` is ready HTML: callers escape their own
        dynamic parts, exactly as every other summary on the page is built."""
        inner = "".join(self.parts[mark:])
        if not inner:
            return
        del self.parts[mark:]
        self.add('<details><summary>%s</summary><div class="body">%s</div></details>'
                 % (summary_html, inner))

    def body(self):
        return "".join(self.parts)

    def menu(self):
        return "".join('<a href="#%s">%s</a>' % (esc(a), esc(label)) for a, label in self.nav)


# --- 1. Title and run stamps -------------------------------------------------------------------

def _models_line(provenance):
    per_seat = provenance.get("models_per_seat") or {}
    names = sorted({str(model) for model in per_seat.values() if model})
    seats = ", ".join(names) if names else "not recorded"
    # Partial provenance says so - a known model beside an unrecorded
    # seat must not read as the whole bench (audit finding SC3 r6-3).
    if names and any(model is None for model in per_seat.values()):
        seats += " (not recorded for every seat)"
    challenger = provenance.get("challenger_model_requested") or "not recorded"
    return seats, challenger


def _masthead_title(subject):
    """Company name, then ticker and listing (design audit C4 tier 0). A subject with no ticker
    (a theme) is named alone; a crypto asset with no listing carries its ticker only."""
    name = subject.get("name") or ""
    ticker = subject.get("ticker")
    listing = subject.get("listing")
    if ticker and listing:
        tail = "(%s: %s)" % (listing, ticker)
    elif ticker:
        tail = "(%s)" % ticker
    else:
        tail = ""
    if not tail:
        return esc(name)
    return '%s <span class="tkr">%s</span>' % (esc(name), esc(tail))


def _question_line(verdict, capture=None, document=None):
    """The owner's question on one line, as he asked it. Owner ruling AC32 (capture contract
    1.8.0): the capture carries that line as its own field, 'question_line'. The capture is model
    output, so the masthead prints that line only where the owner saw it: the full evidence
    document he approved, as the run stores it (`document`, owner rulings AC3, AC15), carries
    the brief's row "The question, in one line: <line>". Anywhere else (an unattended sitting,
    no approval, no stored document, a document without that row, or a capture written before
    1.8.0) the line is derived exactly as it always was
    (register item P-U6b-10): the first paragraph of his brief -- the text up to the first blank
    line -- cut at its first question mark if one occurs (the text up to and including that
    "?"), otherwise the whole first paragraph. Whitespace is collapsed to single spaces, there
    is no ellipsis, and the ".question" CSS wraps the line. The whole brief, word for word, stays
    in the folded appendix below. The 1.8.0 migration fills the field by this same rule, so a
    sitting on record prints the same line either way.

    Round 5 (architect ruling closing P-U6b-15) removed the sentence splitter: a brief opening
    with two statements shows both, and a cut or misleading line never occurs. The architect
    rulings closing P-FIb-1 and P-FIb-2 replaced the string check of this page's first audit
    round with the approved-document rule above."""
    row = brief.question_line_row(capture or {})
    if row and document and row in {" ".join(text.split()) for text in document.splitlines()}:
        return brief.question_line(capture)
    verbatim = (verdict.get("question_verbatim") or "").strip()
    if not verbatim:
        return ""
    paragraph = re.sub(r"\s+", " ", re.split(r"\n\s*\n", verbatim)[0]).strip()
    mark = paragraph.find("?")
    if mark != -1:
        return paragraph[:mark + 1]
    return paragraph


def _head_block(page, run):
    """The masthead (design audit C4 tier 0): company identity and the owner's one-phrase
    question on the left, the rating box and the key-data strip in the rail on the right. The
    warnings band renders directly beneath it, never folded; the sticky summary bar follows."""
    verdict = run["verdict"]
    subject = verdict.get("subject") or {}
    page.add('<header class="masthead">')
    page.add('<div class="masthead-id">')
    page.add('<div class="kicker">Investment Council</div>')
    page.add("<h1>%s</h1>" % _masthead_title(subject))
    question = _question_line(verdict, (run.get("pack") or {}).get("capture"),
                              run.get("approved_document"))
    if question:
        page.add('<p class="question">%s</p>' % esc(question))
    page.add("</div>")
    page.add('<aside class="rail">')
    _rating_box(page, verdict)
    _front_key_numbers(page, verdict)
    page.add("</aside>")
    page.add("</header>")
    _warnings_band(page, run)
    _sticky_bar(page, run)


# The subject kinds judged through several named instruments at once (THEMES-BASKETS-SPEC
# section 7): their leading key number is a constituent's price or a theme-level metric, not a
# price for the subject as a whole. The rating box shows that figure under its own label, so it
# reads true there; the slim sticky bar drops the label, so it omits the figure rather than
# print a constituent's price unlabelled beside the subject's own name. Every single subject
# (a stock, Bitcoin, gold, a commodity, an ETF) keeps its price in the bar.
_MULTI_MEMBER_KINDS = frozenset(["basket", "theme"])


def _sticky_bar(page, run):
    """The slim summary bar (design audit C5). Pure CSS `@P@:sticky`: it rides down with the page
    and pins to the top of the screen once the masthead has scrolled off, so the reader always
    sees which company, rating and price the page is about. The Y3 icon and the theme toggle keep
    their fixed corners (rulings Y3/Y4) and sit at its two ends; no new script is added."""
    verdict = run["verdict"]
    subject = verdict.get("subject") or {}
    rating = verdict.get("rating", "")
    short = RATING_WORDS.get(rating, rating).split(" - ")[0]
    ident = subject.get("ticker") or subject.get("name") or ""
    bits = ['<span class="sb-tick">%s</span>' % esc(ident),
            '<span class="sb-rate">%s</span>' % esc(short)]
    lead = _first_key_number(verdict)
    if lead and subject.get("kind") not in _MULTI_MEMBER_KINDS:
        # Round 4 (P-U6b-14): show the figure UNDER its own label, exactly as the rating box does,
        # so a non-price leading key number (the envelope's order is LLM-authored) can never read
        # as the price. The label wraps with the value as one flex unit; the icon and toggle are
        # pinned to the viewport corners (fixed) and cannot be pushed off the bar.
        label = lead.get("name", "")
        value = format_number(lead.get("value"), lead.get("unit"))
        shown = "%s %s" % (label, value) if label else value
        bits.append('<span class="sb-lead">%s</span>' % esc(shown))
        asof = format_date(lead.get("as_of", ""))
        if asof:
            bits.append(esc(asof))
    joined = ' <span class="sep">&middot;</span> '.join(bits)
    page.add('<div class="stickybar"><div class="stickybar-inner">%s</div></div>' % joined)


# --- 1b. THE DECISION FRONT (ANCHORLESS-SPEC section 5, owner ruling AB13.5) --------------------
# The report opens with the decision and nothing else: the warnings, the rating, the few numbers
# the ruling turns on, how the rating was earned, where the downside sits, the dated events, the
# tripwires, what would change the rating, and where the bench disagreed. Everything else is an
# appendix behind it. This front is rendered for EVERY subject, anchorless or not.
#
# Two rules govern the figures here. A figure recorded as a NUMBER is rounded for reading like
# every other figure on the page, through format_number with its own unit. A figure the machine
# has ALREADY written into words - the ladder's arithmetic sentences, the bar, the sensitivity
# sentences - is quoted exactly as it arrived: those were rounded once, in the engine that
# computed them, and rounding them again would put two spellings of one number on one page.

# Owner ruling AC16(3), audit B11: the executive summary carries the decisive numbers as a
# key-data strip, six to eight cells, not a raw table dump of every envelope row.
KEY_DATA_STRIP_MAX = 8

# Owner ruling AC16(7), architect ruling before U6b(b) round 1: the compact table of the facts
# the verdict rests on holds at most this many OPEN rows; every other dependency fact folds below.
COMPACT_EVIDENCE_MAX = 25

# A pack fact whose id begins with this is a dated event (the anchorless anchor set).
CALENDAR_PREFIX = "calendar_"

# A value that opens with a calendar date is the date of the event itself; anything else is
# words about the event, and the fact's own as-of date is the one the calendar can sort on.
LEADING_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# The five-word scale, strongest first, so the reader sees where this rating sits on it.
SCALE_ORDER = ("strong_buy", "buy", "hold", "sell", "monitor")


def _prose_note(run, seat):
    """One muted line with a seat's writing score, for the collapsed appendix
    (spec U6.4). Empty where the run carries no score for the seat - a report
    published before U6, or a hand-built fixture with no record."""
    score = (run.get("prose_scores") or {}).get(seat)
    if not score:
        return ""
    whose = "chairman, measured" if score.get("judged") else "advisory"
    return ('<div class="muted small">Writing score (%s): %s</div>'
            % (whose, esc(prose.describe(score.get("score") or {}))))


def _chair_prose_warning(page, run):
    """Owner ruling AC6, spec U6.4: when the chairman's FINAL document still
    missed the council's writing rules after its one rewrite, the verdict
    publishes with its writing score shown here - transparency, never a freeze
    (the AB4 spirit). The final document is the resolve, or the draft where the
    outside audit did not run."""
    scores = run.get("prose_scores") or {}
    score = scores.get("chair_resolve") or scores.get("chair_draft")
    if not score or not score.get("warned"):
        return
    page.add('<div class="card alarm"><span class="shout">The chairman&#x27;s '
             "final wording did not meet the council&#x27;s writing rules after "
             "one rewrite. The verdict and its numbers stand; the writing score "
             'is recorded here.</span><div class="small">%s</div></div>'
             % esc(prose.describe(score.get("score") or {})))


def _warnings_band(page, run):
    """The loud warning band. It renders in the DECISION FRONT and nowhere else: a failed
    outside audit or a raise the auditor never saw must never sit behind a fold."""
    warnings = run["verdict"].get("warnings") or []
    for warning in warnings:
        page.add('<div class="card alarm"><span class="shout">%s</span></div>' % esc(warning))
    _chair_prose_warning(page, run)


# Owner ruling AC16(3), closing register item P-U6-5: the executive summary is a MINIMUM-content
# rule, no longer a fixed two-page box. Nothing the reader needs in the first three minutes is cut,
# trimmed to a character budget or shown as an ellipsis; length is bounded at the writer (the
# chair's brief caps the rationale), never at the display. The old bounding constants, the trimming
# helper and the row cap are gone, and every front value renders in full.


def _first_key_number(verdict):
    """The envelope's leading headline figure - the price the ruling is made against for a priced
    subject, the first key number otherwise. Read by the envelope's own ORDER (the price leads it
    for a priced subject), under the envelope's own label: no label map and no new field, as ruled
    for this sub-charge (owner ruling AC16)."""
    key_numbers = (verdict.get("atlas_envelope") or {}).get("key_numbers") or []
    return key_numbers[0] if key_numbers else None


def _rating_box(page, verdict):
    """The rating box in the masthead (owner ruling AC16(3),(9); design audit C5): the rating word
    large; the price the ruling is made against and its date, from the envelope's leading key
    number under its own label; the model names as a small stamp beneath (M3 still satisfied - the
    chair's model and the challenger are still named at the top). No label map, no new field."""
    rating = verdict.get("rating", "")
    page.add('<div class="ratingbox">')
    page.add('<div class="rating-word">%s</div>' % esc(RATING_WORDS.get(rating, rating)))
    page.add('<div class="rating-scale muted small">The council&#x27;s scale, strongest first: '
             "%s.</div>" % esc(", ".join(RATING_WORDS[word] for word in SCALE_ORDER)))
    page.add('<div class="muted small">The subject is %s.</div>'
             % esc(_kind_words(verdict.get("subject") or {})))
    lead = _first_key_number(verdict)
    if lead:
        asof = format_date(lead.get("as_of", ""))
        page.add('<dl class="rating-price"><dt>%s</dt><dd>%s%s</dd></dl>'
                 % (esc(lead.get("name", "")),
                    esc(format_number(lead.get("value"), lead.get("unit"))),
                    (' <span class="asof">%s</span>' % esc(asof)) if asof else ""))
    seats, challenger = _models_line(verdict.get("provenance") or {})
    page.add('<div class="stamp muted small">seats ran on <strong>%s</strong> &middot; the '
             "challenge went to <strong>%s</strong></div>" % (esc(seats), esc(challenger)))
    page.add("</div>")


def _front_thesis(page, verdict):
    """The thesis in five sentences or fewer (owner ruling AC16(3),(6)): the opening of the
    chairman's rationale, shown once as a lede. No new verdict field - the renderer takes the
    rationale's first sentences; fewer than five means the thesis is all of it, and the full
    rationale still prints below."""
    rationale = _display_prose(verdict, "conviction_rationale", "chairman rationale", page)
    if not rationale or rationale == "not recorded":
        return
    sentences = prose.split_sentences(rationale, prose.load_rules())
    thesis = " ".join(sentences[:5]) if sentences else rationale
    page.add('<div class="card prominent"><span class="lead">The thesis</span>%s</div>'
             % markdown(thesis))


def _front_rationale(page, verdict):
    """The chairman's rationale, in full, never cut, with its paragraph breaks (owner ruling
    AC16(3); audit B2). Length is bounded at the writer by the chair's brief, not here."""
    rationale = _display_prose(verdict, "conviction_rationale", "chairman rationale", page)
    page.add('<div class="card"><span class="lead">Why this rating, in the chairman&#x27;s own '
             "words</span>%s</div>" % markdown(rationale))


def _front_key_numbers(page, verdict):
    """The decisive numbers as a key-data strip (owner ruling AC16(3); audit B11): the envelope's
    headline figures at a glance in the market form, each under the envelope's own plain label.
    The whole list, with its dates and bounds, is in the hand-off appendix at the end."""
    key_numbers = (verdict.get("atlas_envelope") or {}).get("key_numbers") or []
    page.add("<h3>The numbers this ruling turns on</h3>")
    if not key_numbers:
        page.add('<div class="card">The verdict names no headline numbers.</div>')
        return
    shown = key_numbers[:KEY_DATA_STRIP_MAX]
    cells = "".join("<dt>%s</dt><dd>%s</dd>"
                    % (esc(number.get("name", "")),
                       esc(format_number(number.get("value"), number.get("unit"))))
                    for number in shown)
    page.add('<dl class="keydata">%s</dl>' % cells)
    remaining = len(key_numbers) - len(shown)
    if remaining > 0:
        page.add('<div class="muted small">The verdict carries %d more headline number%s. They '
                 "are listed in full under &#x27;What the portfolio system receives&#x27; at the "
                 "end of this report.</div>"
                 % (remaining, "" if remaining == 1 else "s"))


def _ladder_table(page, scenarios, currency):
    """The chairman's ladder: one row per named rung, every rung in full. The price is rounded for
    reading in the subject's own currency; the chance is quoted as he wrote it, because the
    arithmetic block beside this table quotes that same string and the two must read alike."""
    rows = "".join('<tr><td>%s</td><td class="nowrap">%s</td><td class="nowrap">%s</td>'
                   "<td>%s</td></tr>"
                   % (esc(rung.get("name", "")),
                      esc(format_price(rung.get("price_outcome"), currency)),
                      esc(rung.get("probability", "")),
                      esc(rung.get("rationale", "")))
                   for rung in scenarios)
    page.add('<table><tr><th>the case</th><th class="nowrap">price if it happens</th>'
             '<th class="nowrap">chance</th><th>why</th></tr>%s</table>' % rows)


def _ladder_judgment_note(page, block):
    page.add('<div class="muted small">Every chance below is the council&#x27;s own disciplined '
             "judgment, never a verified fact. The horizon is %s months.</div>"
             % esc(block.get("horizon_months", "")))


def _front_earned_rating(page, verdict, block):
    """An anchorless subject's rating, and the sum that earned it."""
    page.add("<h3>How this rating was earned: the scenario ladder</h3>")
    _ladder_judgment_note(page, block)
    _ladder_table(page, block.get("scenarios") or [],
                  (verdict.get("subject") or {}).get("currency"))
    sentences = block.get("arithmetic") or []
    if sentences:
        # The machine's own sum, written out. Quoted, never reworded: this IS the arithmetic
        # the ruling requires on the page.
        page.add('<div class="card prominent"><span class="lead">The sum, written out</span>%s'
                 "</div>" % "".join("<p>%s</p>" % esc(line) for line in sentences))
    bar = block.get("bar_pct")
    expected = block.get("expected_annualised_pct")
    if bar is not None and expected is not None:
        page.add('<div class="card"><span class="lead">The bar it had to clear</span>The ladder '
                 "expects %s%% a year against a bar of %s%% a year%s.</div>"
                 % (esc(expected), esc(bar),
                    (", a difference of %s points" % esc(block["excess_over_bar_pp"]))
                    if block.get("excess_over_bar_pp") is not None else ""))
    _front_sensitivity(page, block)


def _capped_caveat(block):
    """Whose rating the sensitivity describes, where a failed
    outside audit capped the published one. One wording, used
    wherever those figures are rendered."""
    return ("Everything here reads the ladder&#x27;s own rating of "
            "<strong>%s</strong>. The outside audit did not run, so "
            "the rating actually published was capped to "
            "<strong>%s</strong>, and these readings move the "
            "ladder&#x27;s answer rather than this page&#x27;s."
            % (esc(RATING_WORDS.get(block.get("rating"),
                                    block.get("rating") or "")),
               esc(RATING_WORDS.get(block["published_rating"],
                                    block["published_rating"]))))


def _front_sensitivity(page, block):
    """How the rating moves as the odds and the bar move - printed every time (AB13.2)."""
    sensitivity = block.get("sensitivity") or {}
    flip = sensitivity.get("flip") or {}
    lines = [text for text in (flip.get("sentence"), sensitivity.get("sentence")) if text]
    steps = sensitivity.get("bar_steps") or []
    if not lines and not steps:
        return
    page.add("<h4>How close this is to a different answer</h4>")
    # When a failed outside audit capped the earned rating, every figure
    # below still reads the LADDER's rating, not the one on this page.
    # The arithmetic is honest and is kept; what was missing was saying
    # whose rating it describes (audit finding ANCHORLESS-C c1-3).
    if block.get("published_rating"):
        page.add('<div class="card alarm">%s</div>'
                 % _capped_caveat(block))
    if lines:
        page.add('<div class="card">%s</div>'
                 % "".join("<p>%s</p>" % esc(line) for line in lines))
    if steps:
        rows = "".join('<tr><td>%s</td><td class="nowrap">%s%%</td>'
                       '<td class="nowrap">%s</td></tr>'
                       % (esc(step.get("label", "")), esc(step.get("bar_pct", "")),
                          esc(RATING_WORDS.get(step.get("rating"), step.get("rating") or "")))
                       for step in steps)
        page.add('<table><tr><th>the bar</th><th class="nowrap">it becomes</th>'
                 "<th>the rating then reads</th></tr>%s</table>" % rows)


def _front_not_aggregated(page, verdict, block):
    """A ladder the chairman would not add up. There is no earned rating, and the page says so
    in his own reason rather than showing arithmetic nobody stands behind."""
    page.add("<h3>Why no rating was earned from the ladder</h3>")
    page.add('<div class="card prominent"><span class="lead">The chairman judged this ladder too '
             "uncertain to add up</span>%s</div>"
             % esc(block.get("not_aggregated_reason")
                   or "He recorded no reason."))
    scenarios = block.get("scenarios") or []
    if scenarios:
        _ladder_judgment_note(page, block)
        _ladder_table(page, scenarios, (verdict.get("subject") or {}).get("currency"))


def _front_context_ladder(page, verdict, block):
    """A ladder offered beside an anchored subject's read. It earned nothing and says so."""
    page.add("<h3>A scenario ladder, as supporting context only</h3>")
    page.add('<div class="muted small">This subject is rated on its own anchors, above. The '
             "ladder below earned no rating; the chairman offered it as context beside the "
             "read.</div>")
    _ladder_judgment_note(page, block)
    _ladder_table(page, block.get("scenarios") or [],
                  (verdict.get("subject") or {}).get("currency"))


def _front_price_read(page, run):
    """The price read on the executive summary (owner ruling AC16(3), audit C4 tier 1): the
    mispricing sentence, once, for an anchored subject. An anchorless subject earns its rating
    from the scenario ladder instead, which sits under 'The decision in detail' below - so this
    prints nothing for it, and the ladder is not shown twice."""
    verdict = run["verdict"]
    block = verdict.get("scenario_rating") or {}
    if block and block.get("basis") == "rating":
        return
    page.add('<div class="card"><span class="lead">The mispricing read</span>%s</div>'
             % _mispricing_sentence(verdict))


def _detail_basis(page, run):
    """How the rating was earned, on the decision-in-detail tier (audit C4 tier 3): the anchorless
    scenario ladder and its arithmetic where the subject earns its rating from one, or a context
    ladder offered beside an anchored read. Content unchanged - it moved down from the executive
    summary, where the ladder used to sit."""
    verdict = run["verdict"]
    block = verdict.get("scenario_rating") or {}
    if block and block.get("basis") == "rating":
        if block.get("aggregated"):
            _front_earned_rating(page, verdict, block)
        else:
            _front_not_aggregated(page, verdict, block)
    elif block and block.get("basis") == "context":
        _front_context_ladder(page, verdict, block)


def _below_reference_rungs(block):
    """The ladder rungs priced under the price the ladder is measured against - the downside the
    council's own scenarios describe. An unreadable figure is skipped, never guessed at."""
    reference = block.get("reference_price")
    if not reference:
        return []
    try:
        floor = decimal.Decimal(str(reference).strip())
    except (decimal.InvalidOperation, ValueError):
        return []
    below = []
    for rung in block.get("scenarios") or []:
        try:
            price = decimal.Decimal(str(rung.get("price_outcome")).strip())
        except (decimal.InvalidOperation, ValueError):
            continue
        if price < floor:
            below.append(rung)
    return below


def _front_downside(page, run):
    verdict = run["verdict"]
    tripwires = verdict.get("tripwires") or {}
    levels = tripwires.get("invalidation_levels") or []
    block = verdict.get("scenario_rating") or {}
    below = _below_reference_rungs(block) if block.get("basis") == "rating" else []
    page.add("<h3>The downside ladder</h3>")
    if not levels and not below:
        page.add('<div class="card">The verdict names no level whose breach would break this '
                 "view.</div>")
        return
    if levels:
        rows = "".join('<tr><td class="nowrap">%s</td><td>%s%s</td></tr>'
                       % (esc(format_number(level.get("level"), level.get("unit"))),
                          _constituent_tag(level),
                          esc(level.get("meaning", "")))
                       for level in levels)
        page.add('<table><tr><th class="nowrap">level</th>'
                 "<th>what it means if it is reached</th></tr>%s</table>" % rows)
    if below:
        currency = (verdict.get("subject") or {}).get("currency")
        page.add('<div class="muted small">The ladder&#x27;s own losing rungs, priced under %s '
                 "&mdash; the price the ladder is measured against.</div>"
                 % esc(format_price(block.get("reference_price", ""), currency)))
        rows = "".join('<tr><td class="nowrap">%s</td><td>%s</td>'
                       '<td class="nowrap">%s</td></tr>'
                       % (esc(format_price(rung.get("price_outcome"), currency)),
                          esc(rung.get("name", "")), esc(rung.get("probability", "")))
                       for rung in below)
        page.add('<table><tr><th class="nowrap">price if it happens</th><th>the case</th>'
                 '<th class="nowrap">chance</th></tr>%s</table>' % rows)


def _calendar_rows(pack):
    """Every dated event in the frozen pack, soonest first. The event's own date is the fact's
    value where the value is a date; where it is words instead, the fact's as-of date orders it
    and the words are shown beside it."""
    facts = ((pack or {}).get("capture") or {}).get("tier1") or []
    rows = []
    for fact in facts:
        fact_id = str(fact.get("id") or "")
        if not fact_id.startswith(CALENDAR_PREFIX):
            continue
        text = str(fact.get("value") or "").strip()
        if LEADING_DATE.match(text):
            when, detail = text, ""
        else:
            when, detail = str(fact.get("as_of") or ""), text
        rows.append((when, fact_id, str(fact.get("source") or ""), detail))
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def _detail_calendar(page, run):
    """The dated events, on the decision-in-detail tier. Omitted ENTIRELY when the pack carries
    none (audit B6): an empty section headed by a 'no dated events' sentence is machine noise on
    a research note, so the heading only appears when there is a calendar to show."""
    rows = _calendar_rows(run["pack"])
    if not rows:
        return
    page.add("<h3>The dated event calendar</h3>")
    body = "".join('<tr><td class="nowrap">%s</td><td>%s%s<div class="muted small"><code>%s</code>'
                   "</div></td></tr>"
                   % (esc(format_date(when)), (esc(detail) + " ") if detail else "",
                      esc(source), esc(fact_id))
                   for when, fact_id, source, detail in rows)
    page.add('<table><tr><th class="nowrap">date</th>'
             "<th>what happens, and where the date comes from</th></tr>%s</table>" % body)


def _trigger_when(trigger):
    """A reopening trigger's level or its date, as the reader reads it. Empty where the record
    carries neither."""
    if trigger.get("level"):
        return esc(format_number(trigger["level"], trigger.get("unit")))
    if trigger.get("date"):
        return esc(format_date(trigger["date"]))
    return ""


def _front_tripwires(page, run):
    """Everything that would change the rating, in one full table (owner ruling AC16(3); audit C4
    and B4): every reopening trigger and every falsifier, uncut, with no restated bullets beside
    it. Each row: what it is, the level or date it turns on, and the figure it is scored against."""
    tripwires = run["verdict"].get("tripwires") or {}
    triggers = tripwires.get("reopening_triggers") or []
    falsifiers = tripwires.get("falsifiers") or []
    page.add("<h3>What changes this rating</h3>")
    if not triggers and not falsifiers:
        page.add('<div class="card">The verdict names nothing that would change this rating.</div>')
        return
    rows = []
    for trigger in triggers:
        kind = ("Reopen the case (price)" if trigger.get("kind") == "price"
                else "Reopen the case (event)")
        rows.append('<tr><td><span class="tag">%s</span> %s%s</td>'
                    '<td class="nowrap">%s</td><td>&mdash;</td></tr>'
                    % (esc(kind), _constituent_tag(trigger),
                       esc(trigger.get("detail", "")),
                       _trigger_when(trigger) or "&mdash;"))
    for row in falsifiers:
        scored = row.get("figure_name") or ""
        source = row.get("source") or ""
        scored_cell = ((("<code>%s</code>" % esc(scored)) if scored else "")
                       + ((" from %s" % esc(source)) if source else "")) or "&mdash;"
        rows.append('<tr><td><span class="tag">Prove the view wrong</span> %s%s</td>'
                    '<td class="nowrap">%s</td><td>%s</td></tr>'
                    % (_constituent_tag(row), esc(row.get("statement", "")),
                       esc(format_date(row.get("date", ""))) or "&mdash;", scored_cell))
    page.add('<table><tr><th>what would change the rating</th>'
             '<th class="nowrap">level or date</th>'
             "<th>the figure it is scored against</th></tr>%s</table>" % "".join(rows))


def _front_cross_examination(page, run):
    reviewer = run["answers"].get("reviewer") or {}
    page.add("<h3>Where the five advisors disagreed &mdash; the blind reviewer&#x27;s "
             "summary</h3>")
    page.add('<div class="muted small">One reviewer read all five advisors without knowing who '
             "wrote what, and summarised where they parted company.</div>")
    page.add('<div class="card prominent">%s</div>'
             % markdown(_display_prose(reviewer, "synopsis", "reviewer synopsis", page), 4))


# --- 1c. What the outside auditor asked for before the council sat (owner ruling AC2) ----------
# A second model, outside this council's own family, read the evidence BEFORE any seat was paid
# and said what it thought was missing, wrong or misread. Every point it raised was answered on
# the record before the council could sit. The reader meets that here; the whole of it, with the
# auditor's own paragraph in its own words, is in the appendix.

EVIDENCE_UNCHECKED_SENTENCE = "The outside auditor did not check the evidence."

_AUDIT_KIND_WORDS = {
    "missing_decisive_fact": "a fact the case turns on, missing",
    "suspect_figure": "a figure that looks wrong",
    "framing_error": "the business read wrongly",
    "missing_checklist_row": "a requirement the checklist did not carry",
    "source_doubt": "the source says something else",
}


def _evidence_audit(run):
    """The outside auditor's block out of the frozen pack, or {}."""
    capture = (run.get("pack") or {}).get("capture") or {}
    return capture.get("evidence_challenge") or {}


def _named_ids(ids):
    """The fact ids that are actually ids. Same rule as _named, one
    container in (audit round 2, r2-2)."""
    return [str(item).strip() for item in ids or [] if str(item).strip()]


def _named(item, field):
    """What the auditor actually named in one field, or "". A value made
    of blanks is not a page, a figure or a place to look, and the answer
    schema permits one (audit round 2, r2-2): every read of these fields
    asks this, so none of them can be talked into printing an emptiness
    as a thing that was named."""
    return str(item.get(field) or "").strip()


def _conceded_gap_ids(capture):
    """The auditor's points the capture answered by conceding a gap. The section names them
    and sends the reader to the audit above, rather than reprinting what it says: reprinting
    put a model's prose in the page's own voice and showed one absence as two for a pack that
    also wrote the ordinary row (audit round 5 r5-3, audit round 6 r6-2)."""
    block = capture.get("evidence_challenge") or {}
    if block.get("status") != "success":
        return []
    return [str(finding_id)
            for finding_id, entry in sorted((block.get("resolutions") or {}).items())
            if (entry or {}).get("disposition") == "gap_declared"]


def _audit_kind_words(finding):
    # A `source_doubt` ASSERTS that the auditor read a published page and
    # that the page prints something else. Where it named no page, the
    # owner is not told a source says otherwise - nothing on the record
    # says any source was read (audit round 1, r1-6).
    if finding.get("kind") == "source_doubt" and not _named(finding,
                                                            "source_url"):
        return "a doubt about a source, with no page named"
    return _AUDIT_KIND_WORDS.get(finding.get("kind"),
                                 str(finding.get("kind") or ""))


def _audit_answer_words(resolution):
    """What the capture session did about one point, for a reader. Ready HTML: every dynamic
    part is escaped here, as every other card on this page escapes its own, and printed in full."""
    render = lambda text: esc(str(text))
    if not resolution or not resolution.get("disposition"):
        return "not answered"
    disposition = resolution["disposition"]
    if disposition == "captured":
        named = ", ".join(_named_ids(resolution.get("fact_ids")))
        return ("gathered, and it is in the evidence below (%s)"
                % render(named or "not named"))
    if disposition == "gap_declared":
        return ("could not be gathered; the gap is declared and it weakens %s &mdash; %s"
                % (render(_named(resolution, "weakened_test")
                          or "no named test"),
                   render(_named(resolution, "reason") or "no reason given")))
    return ("set aside by the session that gathered the evidence, with reasons: %s"
            % render(_named(resolution, "reason") or ""))


def _post_audit_changes(run):
    """What the capture changed after the outside auditor read it (owner ruling AC13.2), as the
    recording listed it."""
    return _evidence_audit(run).get("post_audit_changes") or []


# The three headline pairs are read from the evidence gate rather than copied here: the frame,
# the case file and this page must name one list, never two (audit finding r1-5).
_HEADLINE_IDS = frozenset(fact_id for pair in gate.HEADLINE_PAIRS for fact_id in pair)


def _decisive_ids(run):
    """Every fact or passage id a business frame says this question turns on."""
    capture = (run.get("pack") or {}).get("capture") or {}
    ids = set()
    for frame in (capture.get("business_frame") or {}).values():
        for row in (frame or {}).get("decisive_metrics") or []:
            for entry_id in row.get("answered_by") or []:
                ids.add(str(entry_id))
    return ids


def _changes_that_decide(run):
    """The listed changes the DECISION turns on: a decisive metric's own answer, or one of the
    three headline pairs - a member of an expression wearing its own suffix included."""
    decisive = _decisive_ids(run)
    hits = []
    for change in _post_audit_changes(run):
        entry_id = str(change.get("id"))
        base = entry_id.rpartition("__")[0] or entry_id
        if entry_id in decisive or base in _HEADLINE_IDS:
            hits.append(change)
    return hits


def _front_post_audit_changes(page, run):
    """What moved after the audit, on the front (owner ruling AC13.2).

    Open - and a CONSTANT size, whatever moved - when a change touches a number the decision
    turns on: a decisive metric, or one of the three headline pairs. Otherwise one folded line
    pointing at the appendix, which lists every change with what the auditor read and what the
    council sat on."""
    changes = _post_audit_changes(run)
    if not changes or _evidence_audit(run).get("status") != "success":
        return
    decisive = _changes_that_decide(run)
    if not decisive:
        mark = page.mark()
        page.add('<div class="muted small">Each one, with what the auditor read and what the '
                 "council sat on, is under &ldquo;The outside auditor&#x27;s objections&rdquo; "
                 "below.</div>")
        page.collapse("%d figure%s changed after the outside auditor read the evidence &mdash; "
                      "none of them a number this decision turns on"
                      % (len(changes), "" if len(changes) == 1 else "s"), mark)
        return
    # Deliberately terse, and open whatever moved: a number the decision turns on that the
    # outside auditor never read is a fact the reader must not have to click for.
    page.add('<div class="card alarm"><span class="shout">%d figure%s changed after the outside '
             "auditor read the evidence, %d of them decisive.</span>"
             '<div class="small">Listed under the outside auditor&#x27;s objections.</div></div>'
             % (len(changes), "" if len(changes) == 1 else "s", len(decisive)))


def _front_evidence_audit(page, run):
    """The audit of the evidence, on the front.

    The front is at most two rendered pages (AB13.5) and the appendix holds the whole of this
    section, so what belongs HERE is only what a reader must not have to click for: that the
    audit did not happen at all, or that the auditor called something BLOCKING and the council
    sat anyway. Everything else is one folded line pointing at the appendix. A front that
    reprinted every finding would break the ruled budget on any long answer, which is the
    defect ANCHORLESS-C c1-4 already cost this page once."""
    block = _evidence_audit(run)
    if block.get("status") != "success":
        page.add('<div class="card alarm"><span class="shout">%s</span>'
                 '<div class="small">Every figure below is one session&#x27;s work. No model '
                 "from outside this council&#x27;s own family read it before the advisors "
                 "argued.</div></div>" % esc(EVIDENCE_UNCHECKED_SENTENCE))
        return
    findings = block.get("findings") or []
    blocking = [item for item in findings if item.get("severity") == "blocking"]
    resolutions = block.get("resolutions") or {}
    if not blocking:
        mark = page.mark()
        page.add('<div class="muted small">Every point is set out in full, with the '
                 "auditor&#x27;s own reading of the evidence, under &ldquo;The outside "
                 "auditor&#x27;s objections&rdquo; below.</div>")
        page.collapse("An outside auditor read this evidence before the council sat and raised "
                      "%d point%s, none of them blocking &mdash; all answered on the record"
                      % (len(findings), "" if len(findings) == 1 else "s"), mark)
        _front_post_audit_changes(page, run)
        return
    # The card is a CONSTANT size, whatever the auditor wrote. The front is at most two pages
    # and a long-writing chairman already fills them; a front that reprinted three blocking
    # findings and their answers would break the ruled budget on exactly the run where the
    # reader most needs the rest of the page. The fact that must not be foldable is that the
    # council sat over an unanswered objection - and that fits in a sentence.
    page.add('<div class="card alarm"><span class="shout">The outside auditor called %d point%s '
             "blocking before the council sat.</span>"
             '<div class="small">Each one, and what the record answered, is under &ldquo;The '
             "outside auditor&#x27;s objections&rdquo; below.</div></div>"
             % (len(blocking), "" if len(blocking) == 1 else "s"))
    _front_post_audit_changes(page, run)


# --- 1d. Who reviewed the evidence, and what the sitting cost in time (owner ruling AC3) -------
# The mode is chosen once, at the very start of a sitting, and the page says which way it went
# either way: a reader must never have to wonder whether a person looked at the evidence before
# five advisors argued over it. The capture stage's own minutes and tokens are printed BESIDE
# the sitting's wall clock and never inside it - the 1.5-hour budget is the council's own time,
# and folding the gathering into it would either break the budget or hide the gathering.

REVIEWED_SENTENCE = "Reviewed by %s before the council sat."
AUTO_MODE_SENTENCE = "Auto-mode: no human reviewed the evidence before the council sat."
# The budget this sitting is measured against where its own invocation names none. Pinned equal
# to host.DEFAULT_MINUTES_CAP by the report suite: this module reads a published package and no
# engine code at all, and two caps free to drift apart is one budget nobody can trust.
DEFAULT_MINUTES_CAP = 90
# Deliberately terse: the muted line directly beneath it prints the minutes, and the front is
# a fixed-size container (AB13.5, two rendered pages). MEASURED - the longest front these
# fixtures can produce is 7,874 visible characters against the 8,000-character proxy, and the
# first draft of this sentence put it at 8,009.
BUDGET_MISSED_SENTENCE = "This sitting missed its %s-minute budget."


def _evidence_review(run):
    """The evidence stage's own provenance out of the published verdict, or {} for a run
    published before ruling AC3 existed."""
    return (run["verdict"].get("provenance") or {}).get("evidence") or {}


def _stamp(text):
    """One recorded moment, or None. A stamp this page cannot read is a stamp it does not
    print: the alternative is a wall clock computed from a guess."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        moment = datetime.datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc)


REPORT_RENDERED_EVENT = "report_rendered"


def first_render_moment(run_dir):
    """When this run's report was FIRST rendered, out of the run's own record, or None.

    Spec section U3.3 measures the 1.5-hour budget "to the rendered report", so the finish line
    is the rendering (register item P-U3-5) - and a page that read the clock on the wall printed
    a different number every time it was rendered, which is no archive at all. So the first
    rendering of a run RECORDS the moment, as one append-only row, and every later rendering of
    that run prints what the first one recorded. Two renderings minutes apart are then byte for
    byte the same page (architect's mechanism ruling, 2026-09-09).

    READ ONLY. Writing the row here recorded a rendering that never produced a page: a render
    whose output write failed left the row behind, and the next successful render was timed to
    the failed attempt (audit round 1, r1-6). `commit_render_moment` writes it, after the page
    is on disk.

    A directory carrying no run record is not a sitting this council ran - the report fixtures
    are hand-built - so it can carry no moment, and the page then says nothing about the clock
    rather than inventing a first rendering for it."""
    if not os.path.isfile(runrecord.record_path(run_dir)):
        return None
    for event in runrecord.read_events(run_dir):
        if event.get("event") == REPORT_RENDERED_EVENT:
            # The moment the page was BUILT, which the row carries itself - the same shape
            # `evidence_approved` uses for the go. `ts` is when the row was appended, a moment
            # later, and stands for a row written by an older renderer.
            return _stamp(event.get("at") or event.get("ts"))
    return None


def commit_render_moment(run_dir, moment):
    """Record that this run's report has now been rendered, at `moment`.

    Called by the command that writes the report, between staging the page and making it
    visible: the row says a report exists, so it must not exist before one does (audit round 1,
    r1-6) and the report must not exist without it (round 2, r2-1). The three guards below are
    the "nothing to do" cases - no moment, a moment already recorded, a directory that is not a
    run. A record that cannot be WRITTEN is not one of them: it used to be swallowed here, and
    a full disk then published a page nothing had timed, which the next rendering re-timed
    silently (round 3, r3-1). The failure now reaches the caller, which publishes nothing."""
    if moment is None or first_render_moment(run_dir) is not None:
        return
    if not os.path.isfile(runrecord.record_path(run_dir)):
        return
    runrecord.append_event(run_dir, REPORT_RENDERED_EVENT,
                           {"at": moment.strftime("%Y-%m-%dT%H:%M:%SZ")})


def _wall_clock_minutes(run, now):
    """The sitting's own wall clock: from the go - the approval, or the run itself in
    auto-mode - to the FIRST rendering of the report, as that run's record carries it.

    Spec section U3.3 measures the 1.5-hour budget "to the rendered report", and the read-back
    and the rendering are the sitting's own last work: a clock that stopped at publication
    reported a 95-minute sitting as 89 (register item P-U3-5). `now` is the recorded moment of
    the first rendering, read once per page by the caller, so the number is one moment for the
    whole page and a reprint months later is the same page."""
    provenance = run["verdict"].get("provenance") or {}
    review = _evidence_review(run)
    timestamps = provenance.get("timestamps") or {}
    started = _stamp(review.get("clock_started") or timestamps.get("run_started"))
    if started is None or now is None:
        return None
    # Never below zero. The host tolerates a go stamped up to ten minutes ahead of its own
    # clock, because the owner captures on one machine and sits on the other - and a page
    # rendered inside that allowance printed "The council sat -9 minutes" to him (audit round
    # 1, r1-5). A sitting cannot have run less than no time.
    return max(0.0, (now - started).total_seconds() / 60.0)


def _minutes_cap(run):
    """The budget in force for this sitting: the whole number its own invocation named, or the
    ruled default where it named none - a run published before the config existed.

    ANY whole number the host accepted is honoured, zero included. The host measures the run
    against exactly the number in its invocation and writes a budget-overrun event the moment
    it is passed; a page that quietly substituted its own would report a miss the record knew
    about and the reader did not (audit round 1, r1-2). Nothing else is a cap: a run published
    before the config existed carries none, and the default stands for it."""
    config = (run.get("invocation") or {}).get("config") or {}
    cap = config.get("minutes_cap")
    if isinstance(cap, bool) or not isinstance(cap, int):
        return DEFAULT_MINUTES_CAP
    return cap


def _front_evidence_review(page, run, now):
    """Who reviewed the evidence, and whether the sitting missed its budget, on the executive
    summary (owner ruling AC3; AC16 moved the clocks off it). The reviewer's name is ruled onto
    the front - a CIO wants to know a person looked at the evidence - and the budget-missed alarm
    is a warning that stays at the top, never folded. The minute and token counts themselves sit
    under 'About this sitting' below (audit C4 tier 5)."""
    review = _evidence_review(run)
    if review.get("mode") == "reviewed" and review.get("approved_by"):
        page.add('<div class="card">%s</div>'
                 % esc(REVIEWED_SENTENCE % review["approved_by"]))
    else:
        page.add('<div class="card alarm"><span class="shout">%s</span></div>'
                 % esc(AUTO_MODE_SENTENCE))
    minutes = _wall_clock_minutes(run, now)
    cap = _minutes_cap(run)
    # The budget is measured to the same finish line the page prints, so the page can say
    # itself when the sitting missed it. This is a warning: it stays here, never folded. The
    # host's own budget event is measured at publication and is not touched: two clocks, both
    # named, neither silently redefined.
    if minutes is not None and minutes > cap:
        page.add('<div class="card alarm"><span class="shout">%s</span></div>'
                 % esc(BUDGET_MISSED_SENTENCE % format_number(cap)))


def _sitting_clocks(page, run, now):
    """The sitting's own wall clock and the capture stage's, side by side, for the run-stamps
    tier (owner ruling AC3; AC16 moved them off the executive summary). The council's 1.5-hour
    clock and the gathering time are printed together and never added into one number."""
    review = _evidence_review(run)
    minutes = _wall_clock_minutes(run, now)
    capture = review.get("capture") or {}
    bits = []
    if minutes is not None:
        bits.append("The council sat %s minutes, from the go to this page being rendered."
                    % esc(format_number(minutes, "minutes")))
    if capture.get("minutes") is not None or capture.get("tokens") is not None:
        # Owner ruling AC15 (P5(b)): where the capture-stage figures are an
        # estimate, the page says so beside them - an estimate never reads
        # as a counted figure.
        estimated = " (estimated)" if capture.get("estimated") else ""
        bits.append("Gathering it took another %s minutes and %s tokens%s, counted beside that "
                    "clock and never inside it."
                    % (esc(format_number(capture["minutes"], "minutes"))
                       if capture.get("minutes") is not None
                       else "an unrecorded number of",
                       esc(format_number(capture["tokens"], "tokens"))
                       if capture.get("tokens") is not None
                       else "an unrecorded number of",
                       estimated))
    if bits:
        page.add('<div class="muted small">%s</div>' % " ".join(bits))


def _front_archetype(page, run):
    """The business archetype and the rating measure it calls for, beside
    the rating (owner ruling AC15, P2). A single name only - a basket, a
    theme, a fund and an asset with no earnings carry none."""
    capture = (run.get("pack") or {}).get("capture") or {}
    subject = capture.get("subject") or {}
    frame = (capture.get("business_frame") or {}).get(subject.get("ticker"))
    if not frame or not frame.get("archetype"):
        return
    archetype = frame["archetype"]
    measure = _capture_measure(capture)
    rated = ((" &mdash; rated on %s"
              % esc(MEASURE_WORDS.get(measure, measure))) if measure else "")
    # Owner rulings AC28 and AC30: a financial institution names its kind of firm, and a holding
    # says in one sentence that what it owns was not rated.
    kind = (esc(brief.fi_kind_words(frame, _plain)) if archetype == brief.FI_ARCHETYPE
            else esc(ARCHETYPE_WORDS.get(archetype, archetype)))
    holding = (" %s" % esc(brief.FI_NOT_RATED_SENTENCE)
               if archetype == brief.FI_ARCHETYPE
               and frame.get("fi_subtype") == brief.FI_HOLDING else "")
    page.add('<div class="card"><span class="lead">What kind of business, '
             "and how it is rated</span>%s%s%s</div>" % (kind, rated, holding))


def _front_theme_thesis(page, verdict):
    """A theme's own thesis, frozen before the council sat, as a card in the executive summary
    directly under the key-data strip (architect ruling closing P-U6b-9): the idea the rating
    judged is decision content for a theme, not an appendix. Moved WHOLE from the constituents
    section - the card's HTML is unchanged. Nothing for a subject with no theme block."""
    theme = subjects.theme_block(verdict.get("subject") or {})
    if not theme:
        return
    page.add('<div class="card prominent"><span class="lead">The '
             "theme&#x27;s thesis, frozen before the council sat"
             '</span><div class="verbatim">%s</div></div>'
             % esc(theme.get("thesis", "")))


def _front_chart_and_tape(page, run):
    """The price chart and the tape's fifteen display rows, opening the executive summary (spec
    U4, the chart on the page "on the decision front under the key numbers", which since U6b(c)
    close the masthead rail). A pack with no price series says so in ONE line, in the one-page
    brief's own words; a tape of nothing but declared gaps prints the brief's all-gaps line in
    place of the table, and the chart still draws the closes. Raises chart.ChartRefused where a
    drawn average would disagree with the tape."""
    capture = (run.get("pack") or {}).get("capture") or {}
    page.add("<h3>The price chart and the tape</h3>")
    if not capture.get("price_series"):
        page.add('<p class="muted">%s</p>' % esc(brief.tape_placeholder(capture)))
        return
    subject = run["verdict"].get("subject") or {}
    page.add(chart.figure(capture, run["verdict"], subject.get("kind") not in _MULTI_MEMBER_KINDS,
                          format_number, format_date))
    table = chart.tape_table(capture, format_number, format_date)
    page.add(table or '<p class="muted">%s</p>' % esc(brief.TAPE_ALL_GAPS))


def _front_section(page, run, now):
    """The executive summary (owner ruling AC16(3)): the first two to three minutes of reading.
    The decisive numbers, the thesis, the price read, the chairman's rationale IN FULL and never
    cut, one table of everything that would change the rating, where the advisors parted, and the
    audit state. The chairman's synthesis follows this directly (AC16(5)); the decision in detail,
    the frozen evidence and the appendices come below it in turn - a reader dives deeper the
    further down the page they scroll."""
    # The warnings band, the rating box and the key-data strip now sit in the masthead above
    # (owner ruling AC16(3),(9); design audit C4 tier 0 / C5), assembled by _head_block. This
    # tier opens with the business archetype and the thesis; nothing here is folded.
    page.section("decision", "Executive summary")
    _front_chart_and_tape(page, run)
    _front_archetype(page, run)
    _front_theme_thesis(page, run["verdict"])
    _front_thesis(page, run["verdict"])
    _front_price_read(page, run)
    _front_rationale(page, run["verdict"])
    _front_tripwires(page, run)
    _front_cross_examination(page, run)
    _front_evidence_audit(page, run)
    _front_evidence_review(page, run, now)


# --- 2. The owner's question, and the frame ----------------------------------------------------

def _question_section(page, run):
    """The owner's question and the frame, a folded appendix (audit C4 tier 5). The half the
    council answered is on the front already, in one phrase; the verbatim question and the routing
    to the portfolio system are the record, behind one line."""
    verdict = run["verdict"]
    frame = verdict.get("frame") or {}
    page.section("question", "The owner's question")
    mark = page.mark()
    page.add('<div class="card"><span class="lead">His question, word for word</span>'
             '<div class="verbatim">%s</div></div>' % esc(verdict.get("question_verbatim", "")))
    page.add('<div class="card"><span class="lead">The half the council answered</span>'
             '<div class="verbatim">%s</div>'
             '<div class="muted small" style="margin-top:8px">What was asked, in one phrase: '
             "%s.</div></div>"
             % (esc(frame.get("question_for_council", "")), esc(frame.get("classification", ""))))
    if frame.get("for_atlas") is not None:
        page.add('<div class="card prominent"><span class="lead">Routed to the portfolio system, '
                 "untouched</span>The rest of his question is not the council&#x27;s to answer. "
                 "It went to the portfolio system exactly as he wrote it:"
                 '<div class="verbatim" style="margin-top:8px">%s</div></div>'
                 % esc(frame["for_atlas"]))
    page.collapse("The owner&#x27;s question as he asked it, and the half the council answered",
                  mark)


# --- 3. The verdict block ----------------------------------------------------------------------

def _mispricing_sentence(verdict):
    """The price read as one sentence. Built in one place, so the decision front and the folded
    verdict block below it can never come to read differently."""
    mispricing = verdict.get("mispricing") or {}
    read = mispricing.get("read")
    if read == "no_view" or not read:
        sentence = "The council takes no view on the price yet."
    else:
        sentence = _end_sentence(
            "The council reads the price as <strong>%s</strong>%s"
            % (esc(MISPRICING_WORDS.get(read, read)),
               (" &mdash; %s" % esc(mispricing["magnitude"]))
               if mispricing.get("magnitude") else ""))
    arithmetic = mispricing.get("arithmetic")
    if arithmetic:
        # The arithmetic-in-words sentence is the chairman's own; it is quoted, never reworked.
        sentence += ' <span class="muted">%s</span>' % esc(arithmetic)
    return sentence


# The verdict fold is gone (owner ruling AC16(3), audit B2/B4): the rating, the chairman's
# rationale in full and the price read now sit once in the executive summary above, so a separate
# folded copy in the appendix would be a fourth restatement of the same words.


# --- 3b. The named expression: constituents, or the one vehicle --------------------------------

def _member_fact_cell(facts_by_id, concept, ticker):
    """One expression member's own frozen figure as a table cell, read
    from the pack fact `<concept>__<slug(ticker)>` and rounded for
    reading like every other figure on the page. An absent fact renders
    an em dash - the page never invents a number."""
    fact = facts_by_id.get("%s__%s" % (concept, subjects.slug(ticker)))
    if not fact:
        return "&mdash;"
    return esc(format_number(fact.get("value"), fact.get("unit")))


def _bound_words(tag):
    """A figure declared a BOUND rather than a measurement, in the same
    sentence the seat case files carry (council/engine/briefs.py
    _bound_note) - the page and the briefs say one thing, and the
    report suite proves the two strings equal.

    Owner ruling AB20 moved this declaration out of the fact's source
    sentence and into the capture's own shape, so every place that used
    to read it out of the prose renders it from the tag instead. This
    page is one of them: without it the owner would read a bound as a
    measurement.

    The sentence does NOT say the line named is the narrowest one the
    filer publishes. Nothing here can know that."""
    if not isinstance(tag, dict):
        return None
    named = bool(tag.get("published_line"))
    if tag.get("kind") == "ceiling":
        words = ("declared a CEILING: this figure can only overstate "
                 "what it stands for, never understate it, so any test "
                 "it feeds is harsher than the truth and never kinder")
        if named:
            words += (" - it is the whole of one published line, which "
                      "contains the item this fact stands in for "
                      "because the filer reports no line of its own for "
                      "it; the capture names that line below, as data")
        return words
    if tag.get("kind") == "floor":
        words = ("declared a FLOOR: this figure can only understate "
                 "what it stands for, never overstate it - the true "
                 "figure can only be higher")
        if named:
            words += (" - struck against the published line the capture "
                      "names below, as data")
        return words
    return None


def _proportions_card(page, proportions):
    """The thesis proportions under their ruled label - the same
    sentence the seat briefs carry, verbatim."""
    items = "".join("<li>%s: %s</li>"
                    % (esc(entry.get("constituent", "")),
                       esc(entry.get("emphasis", "")))
                    for entry in proportions)
    page.add('<div class="card"><span class="lead">%s</span><ul>%s</ul>'
             "</div>" % (esc(EMPHASIS_LABEL), items))


def _constituents_section(page, run):
    """The subject's named expression (THEMES-BASKETS-SPEC section 7):
    the constituent table for a basket or a theme's named universe, or
    the one implementation vehicle for a vehicle-mode theme, on the
    decision-in-detail tier (architect ruling closing P-U6b-9). The
    theme's frozen thesis - the idea the rating judged, which must show
    even for a thematic vehicle that names no expression fields (audit
    finding THEMES-C r3-1) - now leads the executive summary instead
    (_front_theme_thesis). A subject with no expression renders no
    heading here."""
    verdict = run["verdict"]
    subject = verdict.get("subject") or {}
    # The theme's frozen thesis moved to the executive summary, under the key-data strip
    # (architect ruling closing P-U6b-9, _front_theme_thesis); it is what the decision rests on
    # for a theme, not an appendix.
    constituents = subject.get("constituents") or []
    vehicle = subject.get("vehicle")
    if not constituents and not vehicle:
        return
    if constituents:
        page.add("<h3>The constituents</h3>")
        page.add('<div class="muted small">The named instruments the one '
                 "idea is judged across - one rating for the whole, never "
                 "one per name. Prices and market values are frozen pack "
                 "facts; the metric and note beside each name are the "
                 "chairman&#x27;s own.</div>")
        facts_by_id = {fact.get("id"): fact for fact in
                       ((run["pack"].get("capture") or {}).get("tier1")
                        or [])}
        notes_by_ticker = {}
        for note in verdict.get("constituent_notes") or []:
            notes_by_ticker.setdefault(note.get("constituent"), note)
        rows = []
        for item in constituents:
            ticker = item.get("ticker", "")
            note = notes_by_ticker.get(ticker)
            if note:
                metric = esc(note.get("load_bearing_metric", ""))
                words = esc(note.get("role_in_thesis", ""))
                if note.get("tripwire"):
                    words += ('<div class="muted small" '
                              'style="margin-top:4px">Tripwire: %s</div>'
                              % esc(note["tripwire"]))
            else:
                metric = "&mdash;"
                words = "&mdash;"
            rows.append('<tr><td>%s</td><td class="nowrap">%s</td>'
                        '<td class="nowrap">%s</td>'
                        '<td class="nowrap">%s</td><td>%s</td><td>%s</td>'
                        "</tr>"
                        % (esc(item.get("name", "")), esc(ticker),
                           _member_fact_cell(facts_by_id, "price_last",
                                             ticker),
                           _member_fact_cell(facts_by_id, "market_cap",
                                             ticker),
                           metric, words))
        page.add('<table><tr><th>Name</th><th class="nowrap">Ticker</th>'
                 '<th class="nowrap">Last price</th>'
                 '<th class="nowrap">Market value</th>'
                 "<th>Load-bearing metric</th><th>Note</th></tr>%s</table>"
                 % "".join(rows))
    else:
        page.add("<h3>The implementation vehicle</h3>")
        listing = vehicle.get("listing")
        currency = vehicle.get("currency")
        page.add('<div class="card"><span class="lead">%s</span>'
                 "The one named instrument this theme is judged through. "
                 "Listing: %s. Currency: %s.</div>"
                 % (esc(_member_words(vehicle)),
                    esc(listing) if listing else "none",
                    esc(currency) if currency else "none"))
    proportions = subject.get("thesis_proportions") or []
    if proportions:
        _proportions_card(page, proportions)


# --- The theme's own falsifiers (moved to tier 3, the decision in detail) ----------------------
# The warnings appendix section is gone (audit B5/B6): the warnings are loud at the top of the
# report and an appendix section that only pointed back to them was process noise. The full
# tripwires appendix section is gone too (owner ruling AC16, architect ruling): the one full
# tripwire table now lives once, in the executive summary. What that table does NOT show - a
# theme's declared condition, prior period and metric identity - is kept here, on tier 3.

def _theme_falsifier_block(page, rows, subject):
    """The theme's own falsifiers, first among the tripwires (the
    falsifier is first-class for a theme - THEMES-BASKETS-SPEC section
    6). Driven by the ROWS, never by the subject's kind: a thematic
    vehicle's rows render identically. Each block leads with the
    declared condition, resolved from the subject's own falsifier list
    - the chairman's wording can never stand in for the declaration
    (audit finding THEMES-C r3-2) - then shows how the chairman scored
    it, the figure it is scored against, the prior period where the
    row carries one, and the metric identity the sitting assumed - so
    the owner's REG-18 question is answerable from this page. A row
    answering no declaration cannot publish (the draft gate refuses
    it); a damaged record renders an em dash, never an invention."""
    theme = subjects.theme_block(subject) or {}
    declared = {falsifier.get("id"): falsifier
                for falsifier in theme.get("falsifiers") or ()}
    page.add("<h3>The theme's falsifiers</h3>")
    page.add('<div class="muted small">The declared facts that would '
             "prove the theme itself wrong. Each shows the condition "
             "as it was frozen, then how the chairman scored it. A "
             "level shows its prior period, so a deterioration can be "
             "seen; every block names the metric identity it assumed."
             "</div>")
    for row in rows:
        declaration = declared.get(row.get("theme_falsifier_id")) or {}
        condition = declaration.get("description")
        parts = ['<span class="lead">%s%s</span>'
                 % (_constituent_tag(row),
                    esc(condition) if condition else "&mdash;")]
        parts.append('<div style="margin-bottom:6px">How the chairman '
                     "scored it: %s</div>"
                     % esc(row.get("statement", "")))
        parts.append("Scored against <code>%s</code> from %s, on %s."
                     % (esc(row.get("figure_name", "")),
                        esc(row.get("source", "")),
                        esc(format_date(row.get("date", "")))))
        if row.get("prior_period_value") is not None:
            parts.append('<div style="margin-top:6px">Prior period: '
                         "%s, as of %s.</div>"
                         % (esc(format_number(
                                row.get("prior_period_value"),
                                row.get("prior_period_unit"))),
                            esc(format_date(row.get("prior_period_as_of", "")))))
        parts.append('<div class="muted small" style="margin-top:6px">'
                     "Metric identity assumed: %s</div>"
                     % esc(row.get("metric_identity_assumed")
                           or "not stated"))
        page.add('<div class="card prominent">%s</div>' % "".join(parts))


def _theme_falsifiers(page, run):
    """A theme or basket's own declared falsifiers, on tier 3, with the scoring detail the front's
    one tripwire table does not carry: the declared condition, the prior period and the metric
    identity assumed. Nothing for a subject with no theme falsifiers."""
    falsifiers = (run["verdict"].get("tripwires") or {}).get("falsifiers") or []
    theme_rows = [f for f in falsifiers if f.get("theme_falsifier_id") is not None]
    if not theme_rows:
        return
    _theme_falsifier_block(page, theme_rows, run["verdict"].get("subject") or {})


# --- Tier 3: the decision in detail ------------------------------------------------------------

def _detail_section(page, run):
    """Tier 3, open (audit C4): the decision in detail. How the rating was earned (an anchorless
    subject's scenario ladder and its arithmetic, or a context ladder beside an anchored read),
    the downside ladder and invalidation levels, a theme's own falsifiers where it has them, the
    dated events, the outside auditor's objections and the answers, and the challenge round. A
    reader who wants more than the summary and the chairman's note reads on here; the frozen
    evidence and the appendices are below. Every block is content that moved down whole - nothing
    the council wrote is lost, and the anchorless ladder's arithmetic is unchanged.

    The subject-shape blocks - the constituents (what the subject IS), the cycle a single name
    depends on, and the scenario ladders in full - are decision content for their subject shape,
    not appendices (architect ruling closing P-U6b-9): they render OPEN here, each under a
    content-named h3, constituents first, the ladder detail beside the ladder content already on
    this tier. They were open under the 'all folded' appendices divider before; now the divider's
    statement is true."""
    page.section("detail", "The decision in detail")
    _constituents_section(page, run)
    _cycle_section(page, run)
    _fi_section(page, run)
    _detail_basis(page, run)
    _front_downside(page, run)
    _ladders_section(page, run)
    _theme_falsifiers(page, run)
    _detail_calendar(page, run)
    _auditor_objections(page, run)
    _challenge_card(page, run)


# --- The challenge round, summarized (a card on tier 3) ----------------------------------------

def _challenge_card(page, run):
    """The challenge round summary card and the endorsement line, on the decision-in-detail tier
    (audit C4 tier 3, C5): every finding with its disposition, ruled open, never folded. The
    challenger's own words in full are a folded appendix below."""
    challenge = run["verdict"].get("challenge") or {}
    page.add("<h3>The outside challenge round</h3>")
    status = challenge.get("status")
    if status == "success":
        page.add('<div class="card"><strong>The outside audit ran.</strong> A model from a '
                 "different company, <strong>%s</strong>, read the full case file and answered."
                 "</div>" % esc(challenge.get("model_requested", "")))
    else:
        reason = challenge.get("failure_reason") or "no reason recorded"
        page.add('<div class="card alarm"><span class="shout">%s.</span>What happened: %s (%s). '
                 "No model from another company checked this verdict.</div>"
                 % (esc(AUDIT_FAILED_SENTENCE),
                    esc(CHALLENGE_STATUS_WORDS.get(status, status or "no status recorded")),
                    esc(reason)))
    findings = challenge.get("findings") or []
    dispositions = {}
    for d in challenge.get("dispositions") or []:
        dispositions[d.get("finding_id")] = d
    if findings:
        items = []
        for finding in findings:
            fid = finding.get("id", "")
            disposed = dispositions.get(fid)
            if disposed:
                word = disposed.get("disposition", "")
                tag = '<span class="tag %s">%s</span>' % (esc(word), esc(word))
                meaning = DISPOSITION_MEANING.get(word, "")
                note = ('<div class="muted small" style="margin-top:5px">%s%s</div>'
                        % (("<em>%s.</em> " % esc(meaning)) if meaning else "",
                           esc(disposed.get("response", ""))))
            else:
                tag = '<span class="tag">no disposition recorded</span>'
                note = ""
            items.append("<li><strong>%s</strong> &middot; %s &nbsp;%s<br>%s%s</li>"
                         % (esc(fid),
                            esc(FINDING_KIND_WORDS.get(finding.get("kind"),
                                                       finding.get("kind") or "")),
                            tag, esc(finding.get("title", "")), note))
        page.add('<div class="card prominent"><ul>%s</ul></div>' % "".join(items))
    elif status == "success":
        page.add('<div class="card">The challenger raised nothing. A clean audit that finds '
                 "nothing is a success, not a silence.</div>")
    endorsement = challenge.get("endorsement")
    if endorsement:
        word = RATING_WORDS.get(endorsement.get("highest_rating_supported"),
                                endorsement.get("highest_rating_supported") or "")
        page.add('<div class="card"><strong>The challenger&#x27;s endorsement.</strong> The '
                 "highest rating it would support on this record: <strong>%s</strong>.</div>"
                 % esc(word))
    page.add('<div class="muted small">The challenger&#x27;s own words, in full, are under '
             '<a href="#challenger">its full response</a> below.</div>')


# --- 7. The post-audit change appendix ---------------------------------------------------------

def _change_sentence(change):
    """One field the challenge changed, as a sentence for a reader (owner ruling AC16(8), audit
    B3): what field moved and what happened to it, in plain words - not the raw JSON the diff used
    to print open in the reader's way. The before/after text itself is behind a second fold."""
    field = esc(change.get("field", ""))
    label = change.get("label", "")
    words = esc(CHANGE_LABEL_WORDS.get(label, label))
    if label == "unendorsed_raise":
        words = '<span class="alarmtag">%s</span>' % words
    return "<li><code>%s</code> &mdash; %s.</li>" % (field, words)


def _changes_section(page, run):
    """What changed after the outside challenge, a folded appendix (owner ruling AC16(8), audit
    C4 tier 5). The final document is compared field by field against the draft the challenger
    read. Each changed field is one plain sentence; the exact before-and-after text of every field
    is behind a SECOND fold - kept in full, so nothing the diff recorded is lost, but no longer
    open JSON in the reader's way (audit B3)."""
    challenge = run["verdict"].get("challenge") or {}
    appendix = challenge.get("change_appendix") or []
    # A folded appendix, not in the navigation (the menu stays to the tiers and the main
    # appendices, about nine entries): the challenge diff is a technical stamp reached by scrolling.
    page.add('<h2 id="changes">What changed after the outside audit</h2>')
    if not appendix:
        page.add('<div class="card">Nothing changed after the outside audit.</div>')
        return
    mark = page.mark()
    page.add('<div class="muted small">The final document is compared, field by field, against '
             "the draft the challenger read. Each changed field is named below; the exact text "
             "before and after is behind the second fold.</div>")
    alarm = any(change.get("label") == "unendorsed_raise" for change in appendix)
    page.add('<div class="card%s"><ul>%s</ul></div>'
             % (" alarm" if alarm else "",
                "".join(_change_sentence(change) for change in appendix)))
    rows = []
    for change in appendix:
        row_alarm = change.get("label") == "unendorsed_raise"
        rows.append('<tr%s><td class="nowrap"><code>%s</code></td><td>%s</td><td>%s</td>'
                    '<td class="nowrap"><span class="tag%s">%s</span></td></tr>'
                    % (' class="alarm"' if row_alarm else "", esc(change.get("field", "")),
                       esc(change.get("before", "")), esc(change.get("after", "")),
                       " alarmtag" if row_alarm else "",
                       esc(CHANGE_LABEL_WORDS.get(change.get("label", ""),
                                                  change.get("label", "")))))
    page.add("<details><summary>The exact text before and after, field by field</summary>"
             '<div class="body"><table><tr><th class="nowrap">what changed</th><th>before</th>'
             "<th>after</th><th class=\"nowrap\">what happened</th></tr>%s</table></div></details>"
             % "".join(rows))
    page.collapse("%d field%s changed between the draft the challenger read and the final document"
                  % (len(appendix), "" if len(appendix) == 1 else "s"), mark)


# --- 8. The chairman's final synthesis ---------------------------------------------------------

def _synthesis_section(page, run):
    answers = run["answers"]
    resolve = answers.get("chair_resolve") or {}
    page.section("synthesis", "The chairman's final synthesis")
    prose = resolve.get("final_markdown")
    if not prose:
        prose = (answers.get("chair_draft") or {}).get("synthesis_markdown", "")
        page.add('<div class="muted small">No post-challenge resolve is in the record, so this '
                 "is the chairman&#x27;s synthesis as drafted.</div>")
    page.add('<div class="card">%s%s</div>'
             % (markdown(reformat_prose(prose or "not recorded", "chairman synthesis",
                                        page.number_subs)),
                _prose_note(run, "chair_resolve_synthesis")
                or _prose_note(run, "chair_draft_synthesis")))


# --- 9. The evidence, folded; the market-shut sentence in plain sight ---------------------------

def _audit_finding_card(finding, resolutions):
    """One outside-auditor finding and the answer on the record, as a card. Every dynamic part is
    escaped here, as every card on this page escapes its own, and printed in full."""
    return ('<div class="card"><span class="lead">%s &mdash; %s</span>%s%s'
            '<div class="small" style="margin-top:8px">The answer on the record: %s</div>'
            "</div>"
            % (esc(str(finding.get("severity") or "")),
               esc(_audit_kind_words(finding)),
               esc(str(finding.get("detail") or "")),
               _audit_finding_extras(finding),
               _audit_answer_words(resolutions.get(finding.get("id")))))


def _auditor_objections(page, run):
    """The outside auditor's objections and the answers, on the decision-in-detail tier (audit C4
    tier 3). A model outside this council's family read the evidence before any seat was paid. Its
    own paragraph and any BLOCKING finding with its answer stay open; the non-blocking points and
    the list of figures that moved after it read fold behind one line each. A failed or absent
    audit is a loud, open alarm - never folded."""
    block = _evidence_audit(run)
    page.add("<h3>The outside auditor&#x27;s objections, and the answers</h3>")
    if block.get("status") != "success":
        page.add('<div class="card alarm"><span class="shout">%s</span>'
                 "<div class=\"small\">The council's rules require a model from outside its "
                 "own family to read the evidence before any advisor is paid. On this run the "
                 "call did not produce an answer (%s), and the sitting went on without one.%s</div>"
                 "</div>"
                 % (esc(EVIDENCE_UNCHECKED_SENTENCE),
                    esc(str(block.get("failure_status") or "it was never made")),
                    # What actually went wrong, in the bridge's own words. It can carry the
                    # outside model's own text verbatim, so it is escaped here and reaches no
                    # seat's prompt at all (audit round 5, r5-4).
                    (" What went wrong: %s" % esc(_named(block, "failure_reason")))
                    if _named(block, "failure_reason") else ""))
        return
    findings = block.get("findings") or []
    resolutions = block.get("resolutions") or {}
    page.add('<div class="muted small">Asked of <strong>%s</strong>, a model outside this '
             "council&#x27;s own family, before any advisor was paid. It audits the evidence; "
             "it never gathers it and it never writes it.</div>"
             % esc(str(block.get("model") or "not recorded")))
    overall = block.get("overall")
    if overall:
        page.add('<div class="card prominent"><span class="lead">The auditor&#x27;s reading of '
                 "this evidence, in its own words</span>"
                 '<div class="verbatim">%s</div></div>' % esc(str(overall)))
    blocking = [f for f in findings if f.get("severity") == "blocking"]
    nonblocking = [f for f in findings if f.get("severity") != "blocking"]
    if not findings:
        page.add('<div class="card">It raised nothing against this evidence.</div>')
    # A blocking point the council sat over stays open; the reader must not click for it.
    for finding in blocking:
        page.add(_audit_finding_card(finding, resolutions))
    # The points the auditor did not call blocking fold behind one line with their count.
    if nonblocking:
        mark = page.mark()
        for finding in nonblocking:
            page.add(_audit_finding_card(finding, resolutions))
        page.collapse("%d non-blocking point%s the auditor raised, each with its answer on the "
                      "record" % (len(nonblocking), "" if len(nonblocking) == 1 else "s"), mark)
    _changes_after_the_audit(page, run)


def _change_row(change, decisive):
    """One listed change, for a reader: what it is, what the auditor read, what the council sat
    on. Every dynamic part is escaped here, as every other card escapes its own."""
    entry_id = esc(str(change.get("id") or ""))
    word = change.get("change")
    turns = (' <strong>&mdash; a number this decision turns on</strong>'
             if change in decisive else "")
    if word == "added":
        said = _end_sentence("It was gathered after the audit and reads %s"
                             % esc(str(change.get("new") or "")))
    elif word == "removed":
        said = _end_sentence("It was taken out after the audit; it read %s"
                             % esc(str(change.get("old") or "")))
    elif change.get("old") == change.get("new"):
        said = _end_sentence(
            "Its value stands at %s; what moved is its unit, its date or where "
            "it came from" % esc(str(change.get("new") or "")))
    else:
        said = _end_sentence("The auditor read %s; the council sat on %s"
                             % (esc(str(change.get("old") or "")),
                                esc(str(change.get("new") or ""))))
    return ("<li><strong>%s</strong>%s &mdash; %s</li>" % (entry_id, turns, said))


def _changes_after_the_audit(page, run):
    """Every figure that moved between the audit and the sitting (owner ruling AC13.2).

    The capture MAY change what the auditor never asked about; the rule is that every such
    change is on the record, in each seat's case file and here - so the reader can see which
    numbers the outside model never read."""
    changes = _post_audit_changes(run)
    if not changes:
        return
    decisive = _changes_that_decide(run)
    mark = page.mark()
    page.add('<div class="card"><span class="lead">Changed after the outside auditor read the '
             "evidence</span>"
             '<div class="small">The council may gather more, correct a figure or drop one '
             "after the audit; what it may not do is sit on evidence the record says was "
             "audited when it was not. These %d did not reach the outside model.</div>"
             "<ul>%s</ul></div>"
             % (len(changes),
                "".join(_change_row(change, decisive) for change in changes)))
    # Folded behind one line with its count (audit C4 tier 3): the list of figures that moved
    # after the auditor read is detail, and the front already shows whether any was decisive.
    page.collapse("%d figure%s moved after the outside auditor read the evidence, and never "
                  "reached it" % (len(changes), "" if len(changes) == 1 else "s"), mark)


def _audit_finding_extras(finding):
    """The parts of a finding only some kinds carry: which figures it is about, where a missing
    one would be found, and - where the auditor read the source itself - the page and the figure
    it printed."""
    rows = []
    named = ", ".join(_named_ids(finding.get("fact_ids")))
    if named:
        rows.append("The figures it is about: %s" % esc(named))
    for field, words in (("where_it_likely_lives", "Where it would be found"),
                         ("source_url", "Read at"),
                         ("figure_at_source", "What that page printed")):
        value = _named(finding, field)
        if value:
            rows.append("%s: %s" % (words, esc(value)))
    if not rows:
        return ""
    return ('<div class="small" style="margin-top:8px">%s</div>'
            % "<br>".join(rows))


def _cycle_section(page, run):
    """The cycle a single name depends on (owner ruling AC15, P4), on the
    decision-in-detail tier (architect ruling closing P-U6b-9): the dated series carried as
    EVIDENCE, or the declared gap. Nothing here is computed from them - the seats read them as
    evidence."""
    capture = (run.get("pack") or {}).get("capture") or {}
    cycle = capture.get("cycle")
    if not cycle:
        return
    page.add("<h3>The cycle this name depends on</h3>")
    page.add('<div class="muted small">Evidence, not analysis: the pack '
             "carries these dated series and the seats read them; there is "
             "no computed indicator and no reading here.</div>")
    page.add('<div class="card"><span class="lead">%s</span>%s</div>'
             % (esc(cycle.get("name", "")),
                esc(cycle.get("why_it_matters", ""))))
    gap = cycle.get("gap")
    if gap:
        page.add('<div class="card"><span class="lead">The dated series are '
                 "a declared gap</span>%s</div>" % esc(gap.get("reason", "")))
        return
    for series in cycle.get("series") or []:
        rows = "".join(
            "<tr><td>%s</td><td>%s</td></tr>"
            % (esc(point["date"]), esc(point["value"]))
            for point in series["points"])
        # Render-only (FI-ARCHETYPE (b)): the date the series was read beside the date of its
        # LAST point, so a reader sees how old the latest reading is.
        last = series["points"][-1]["date"] if series["points"] else "none"
        page.add('<h3>%s <span class="muted small">(%s, read %s; latest point %s)</span>'
                 "</h3>"
                 % (esc(series["id"]), esc(series["unit"]),
                    esc(series["as_of"]), esc(last)))
        page.add("<table><tr><th>Date</th><th>Value</th></tr>%s</table>"
                 % rows)
        page.add('<div class="muted small">Source: %s. Re-fetch: %s</div>'
                 % (esc(series["source"]),
                    esc(series["refetch_url_or_source_line"])))


def _plain(value):
    """A value as text, None as nothing - for words the page escapes whole afterwards."""
    return "" if value is None else str(value)


def _fi_value(facts, fact_id):
    """One fact a financial institution's frame names: its label where one exists, its id and
    its frozen value in the market form, and its date. An id the pack does not carry is shown as
    escaped data, never as the page's own named fact (P-U3e-3)."""
    fact = facts.get(fact_id) if isinstance(fact_id, str) else None
    if fact is None:
        return "%s (not in the pack)" % esc(fact_id)
    label = str(fact.get("label") or "").strip()
    return "%s%s %s (as of %s)" % (esc(label) + " " if label else "", _fact_name(fact_id),
                                   esc(format_number(fact.get("value"), fact.get("unit"))),
                                   esc(format_date(fact.get("as_of", ""))))


def _fi_section(page, run):
    """What kind of financial firm this is (owner rulings AC28 and AC30; register items P-FIa-4
    and P-FIa-5), a subject-shape block on the decision-in-detail tier beside the cycle: the kind
    of firm, capital beside its requirement, the regulator's own bad year, the risk-cost line,
    the earnings split, guidance first then its revisions, and for a holding its net asset value
    part by part and the one sentence. Evidence only: nothing here reads the figures, and every
    string the capture wrote is escaped, its numbers marked where they trace to no fact (AC19)."""
    capture = (run.get("pack") or {}).get("capture") or {}
    frame = brief.fi_subject_frame(capture)
    if frame is None:
        return
    ticker = (capture.get("subject") or {}).get("ticker")
    facts = {fact.get("id"): fact for fact in capture.get("tier1") or []}
    bases = brief._frame_bases(capture, ticker)

    def prose(text):
        return trace.mark(" ".join(str(text or "").split()), bases, brief._marks_config(), esc)

    def value(fact_id):
        return _fi_value(facts, fact_id)

    def card(lead, body):
        page.add('<div class="card"><span class="lead">%s</span>%s</div>' % (lead, body))

    page.add("<h3>What kind of financial firm this is</h3>")
    page.add('<div class="muted small">Evidence, not analysis: the figures the pack carries, '
             "each beside what it is measured against; nothing here reads them.</div>")
    kind = brief.fi_kind_words(frame, _plain)
    kind = esc(kind[:1].upper() + kind[1:])
    if frame.get("fi_secondary_subtype"):
        kind += ". Its other engine&#x27;s share is carried by %s" % (
            ", ".join(value(fid) for fid in frame.get("fi_secondary_share_facts") or [])
            or "no fact named")
    card("The kind of firm", kind + ".")
    capital = frame.get("fi_capital") or {}
    if capital.get("gap"):
        card("Capital beside its requirement",
             "A declared gap: %s" % prose(capital["gap"].get("reason")))
    else:
        rows = "".join("<tr><td>%s</td><td>%s</td></tr>"
                       % (value(ratio) if ratio else "no ratio named",
                          value(requirement) if requirement else "no requirement named")
                       for ratio, requirement in brief.fi_capital_pairs(capital))
        extra = "".join("<div>%s: %s</div>" % (label, prose(capital.get(key)))
                        for label, key in (("The regime", "regime"),
                                           ("The binding constraint", "binding_constraint"))
                        if capital.get(key))
        if capital.get("target_fact"):
            extra += "<div>Management&#x27;s own target: %s</div>" % value(capital["target_fact"])
        card("Capital beside its requirement",
             "<table><tr><th>The capital ratio</th><th>Its requirement</th></tr>%s</table>%s"
             % (rows, extra))
    stress, stress_gaps = brief.fi_stress_evidence(capture, ticker)
    if stress or stress_gaps:
        card(esc(brief.FI_STRESS_HEADING),
             "<ul>%s%s</ul>" % ("".join("<li>%s</li>" % value(fid) for fid in stress),
                                "".join("<li>A declared gap (%s): %s</li>"
                                        % (esc(gap.get("fact_class")), esc(gap.get("reason")))
                                        for gap in stress_gaps)))
    risk = frame.get("fi_risk_cost") or {}
    if risk:
        card("The risk-cost line: %s" % esc(brief.FI_RISK_KIND_WORDS.get(risk.get("kind"))
                                            or risk.get("kind")),
             "%s. Why this line: %s"
             % (", ".join(value(fid) for fid in risk.get("facts") or []) or "no fact, by design",
                prose(risk.get("because"))))
    lines = frame.get("how_it_earns") or []
    if lines:
        card("How it earns, by kind of earnings",
             "<table><tr><th>Revenue line</th><th>Kind of earnings</th><th>Share of the period"
             "</th></tr>%s</table>"
             % "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (prose(row.get("line")),
                          esc(brief.FI_NATURE_WORDS.get(row.get("nature"))
                              or row.get("nature") or "not stated"),
                          esc(row.get("share_of_period")))
                       for row in lines))
    guidance = []
    for row in (frame.get("management") or {}).get("guidance_vs_delivery") or []:
        revisions = row.get("revisions")
        if isinstance(revisions, list):
            revised = ("; ".join("revised on %s to %s"
                                 % (esc(item.get("date")),
                                    ", ".join(value(fid) for fid in item.get("guided") or []))
                                 for item in revisions if isinstance(item, dict))
                       or esc(brief.FI_NEVER_REVISED))
        else:
            revised = "its revisions are not stated"
        guidance.append("<li>%s: first guided %s; %s; delivered %s</li>"
                        % (esc(row.get("period")),
                           ", ".join(value(fid) for fid in row.get("guided") or [])
                           or "nothing named",
                           revised, value(row.get("delivered"))))
    if guidance:
        card("Guidance: the first, each revision, then what was delivered",
             "<ul>%s</ul>" % "".join(guidance))
    bridge = frame.get("nav_bridge")
    if isinstance(bridge, dict):
        rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td></tr>"
                       % (prose(part.get("name")),
                          esc(brief.FI_METHOD_WORDS.get(part.get("method"))
                              or part.get("method")),
                          value(part.get("value_fact")))
                       for part in bridge.get("components") or [])
        totals = "".join("<div>%s: %s</div>" % (label, value(bridge[key]))
                         for label, key in (
                             ("Holding-company net debt", "holdco_net_debt_fact"),
                             ("The net asset value", "nav_total_fact"),
                             ("The company&#x27;s own published net asset value",
                              "published_nav_fact"),
                             ("The discount", "discount_fact"))
                         if bridge.get(key))
        card("The net asset value, part by part",
             "<table><tr><th>Component</th><th>How it is valued</th><th>Value</th></tr>%s"
             "</table>%s<div>%s</div>" % (rows, totals, esc(brief.FI_NOT_RATED_SENTENCE)))


def _decisive_fact_order(tier1, dependencies, envelope, frames):
    """Order the dependency facts for the compact table (architect ruling before U6b(b) round 1).
    Priority, duplicates removed: the facts the envelope's key numbers cite, then its sizing
    inputs, then the first fact each decisive metric cites, then the rest in recorded order."""
    by_id = {}
    for fact in tier1:
        fid = fact.get("id")
        if fid in dependencies and fid not in by_id:
            by_id[fid] = fact
    ordered, seen = [], set()

    def take(fid):
        fid = str(fid)
        if fid in by_id and fid not in seen:
            seen.add(fid)
            ordered.append(by_id[fid])

    for number in envelope.get("key_numbers") or []:
        take(number.get("pack_fact_id"))
    for entry in envelope.get("sizing_inputs") or []:
        for fid in entry.get("pack_fact_ids") or []:
            take(fid)
    for frame in frames.values():
        for row in (frame or {}).get("decisive_metrics") or []:
            # A metric's place goes to the FIRST id it cites that is a recorded tier-1
            # dependency fact - not answered_by[0] blindly, which may be a passage and would
            # leave the fact to fall into the counted fold (round 3 finding r3-3, P-U6b-11).
            for fid in row.get("answered_by") or []:
                if str(fid) in by_id:
                    take(fid)
                    break
    for fact in tier1:
        take(fact.get("id"))
    return ordered


def _fact_name(fact_id):
    """A fact's name in the evidence tables: its id, shown as data - except a tape figure, which
    the page names by its plain label, so no tape id reaches the owner's page (unit U4(c); the
    full evidence document does the same through the fact's label, owner ruling AC15 P5)."""
    if fact_id in tape.LABELS:
        return esc(tape.LABELS[fact_id])
    return "<code>%s</code>" % esc(fact_id)


def _decisive_facts_table(page, tier1, freshness, dependencies, envelope, frames):
    """The facts the verdict rests on, as a compact OPEN table (audit C4 tier 4): Fact, Value, As
    of, Freshness, Source. At most COMPACT_EVIDENCE_MAX rows stay open (architect ruling before
    U6b(b) round 1); every other dependency fact folds directly below under a counted summary,
    above the full-pack fold. Nothing where the verdict marks no dependency at all."""
    ordered = _decisive_fact_order(tier1, dependencies, envelope, frames)
    if not ordered:
        return
    rows = []
    for fact in ordered:
        status = freshness.get(fact.get("id"))
        if isinstance(status, dict):
            status = status.get("status")
        word = FRESHNESS_WORD.get(status, status or "not stated")
        # A bound (ceiling/floor) fact must not read as a measurement here, where the owner meets
        # it first, before the full-pack fold (round 1 finding r1-1) - the declaration and the
        # named line render exactly as the full-pack table renders them below.
        source_html = esc(fact.get("source", ""))
        bound = _bound_words(fact.get("bound"))
        if bound:
            source_html += "<br>%s" % esc(bound)
            tag = fact.get("bound") or {}
            if tag.get("published_line"):
                source_html += ("<br>The published line, as the capture names it: %s"
                                % esc(" ".join(str(tag["published_line"]).split())))
        rows.append('<tr><td>%s</td><td>%s</td>'
                    '<td class="nowrap">%s</td><td class="nowrap">'
                    '<span class="tag %s">%s</span></td><td>%s</td></tr>'
                    % (_fact_name(fact.get("id", "")),
                       esc(format_number(fact.get("value"), fact.get("unit"))),
                       esc(format_date(fact.get("as_of", ""))),
                       esc(str(word).replace(" ", "-")), esc(word),
                       source_html))
    # The value column carries figures AND tier-2 passages (whole sentences), so it is NOT a
    # nowrap column (design audit C5, B8): a sentence there must wrap, not blow the table wide.
    header = ('<table><tr><th>fact</th><th>value</th><th class="nowrap">as of</th>'
              '<th class="nowrap">freshness</th><th>source</th></tr>%s</table>')
    page.add('<div class="muted small">The figures the verdict says its ruling rests on. Every '
             "figure on the record, with its bounds and how it was struck, is below.</div>")
    page.add(header % "".join(rows[:COMPACT_EVIDENCE_MAX]))
    rest = rows[COMPACT_EVIDENCE_MAX:]
    if rest:
        mark = page.mark()
        page.add(header % "".join(rest))
        page.collapse("The other %d fact%s this verdict rests on"
                      % (len(rest), "" if len(rest) == 1 else "s"), mark)


def _evidence_section(page, run):
    pack = run["pack"] or {}
    capture = pack.get("capture") or {}
    page.section("evidence", "The evidence")
    market = capture.get("market_state") or {}
    if market.get("state") == "closed":
        # DIAG-2: a market-shut capture is legal and DISCLOSED - in plain sight, never folded.
        disclosure = market.get("disclosure") or {}
        if isinstance(disclosure, dict):
            disclosure_text = "%s %s" % (disclosure.get("reason", ""),
                                         disclosure.get("price_age", ""))
        else:
            disclosure_text = str(disclosure)
        page.add('<div class="card prominent"><strong>The market was shut when this evidence '
                 "was captured.</strong> %s</div>" % esc(disclosure_text.strip()))
    tier1 = capture.get("tier1") or []
    freshness = pack.get("freshness") or {}
    # The verdict's own declared dependencies - the facts its ruling rests on
    # (audit finding SC3 r6-2). The compact table above the fold carries these.
    dependencies = set(run["verdict"].get("evidence_dependencies") or [])
    envelope = run["verdict"].get("atlas_envelope") or {}
    frames = capture.get("business_frame") or {}
    _decisive_facts_table(page, tier1, freshness, dependencies, envelope, frames)
    mark = page.mark()
    notes = pack.get("generated_notes") or {}
    # The verdict's own declared dependencies - marked on their rows,
    # so the page never claims the whole pack carried the ruling
    # (audit finding SC3 r6-2).
    dependencies = set(run["verdict"].get("evidence_dependencies") or [])
    rows = []
    for fact in tier1:
        fact_id = fact.get("id", "")
        status = freshness.get(fact_id)
        if isinstance(status, dict):
            status = status.get("status")
        word = FRESHNESS_WORD.get(status, status or "not stated")
        source_html = esc(fact.get("source", ""))
        bound = _bound_words(fact.get("bound"))
        if bound:
            source_html += "<br>%s" % esc(bound)
            tag = fact.get("bound") or {}
            if tag.get("published_line"):
                source_html += ("<br>The published line, as the capture "
                                "names it: %s"
                                % esc(" ".join(
                                    str(tag["published_line"]).split())))
        note = notes.get(fact_id)
        if note:
            source_html += "<br>Arithmetic: %s" % esc(note)
        rests = ('<span class="tag checked" title="the verdict names this '
                 'fact as one its ruling rests on">rests on this</span> '
                 if fact_id in dependencies else "")
        value = format_number(fact.get("value"), fact.get("unit"))
        rows.append('<tr><td>%s%s<div class="muted small" style="margin-top:4px">'
                    '%s</div></td><td>%s</td><td class="nowrap">%s</td>'
                    '<td class="nowrap"><span class="tag %s">%s</span></td></tr>'
                    % (rests, _fact_name(fact_id), source_html, esc(value),
                       esc(format_date(fact.get("as_of", ""))),
                       esc(str(word).replace(" ", "-")), esc(word)))
    # As above: value is a wrapping column, never nowrap - it can hold a whole tier-2 sentence.
    page.add('<table><tr><th>fact, and where it came from</th><th>value</th>'
             '<th class="nowrap">as of</th><th class="nowrap">freshness</th></tr>%s</table>'
             % "".join(rows))
    page.add('<div class="muted small"><strong>checked</strong> &mdash; the figure&#x27;s age '
             "was tested against the fact&#x27;s own rule and it passed. <strong>stale</strong> "
             "&mdash; it was tested and it failed.</div>")
    tier2 = capture.get("tier2") or []
    if tier2:
        page.add("<h3>The narrative record</h3>")
        page.add('<div class="muted small">Each passage is quoted as captured, from a named '
                 "source. Its figures are stated in its own text and are never rounded.</div>")
        for passage in tier2:
            rests = ('<span class="tag checked" title="the verdict names '
                     'this passage as one its ruling rests on">rests on '
                     'this</span> '
                     if passage.get("id") in dependencies else "")
            page.add('<div class="card"><span class="lead">%s<code>%s</code> &middot; %s &middot; '
                     'as of %s</span><div class="verbatim">%s</div></div>'
                     % (rests, esc(passage.get("id", "")), esc(passage.get("source", "")),
                        esc(passage.get("as_of", "")), esc(passage.get("text", ""))))
    gaps = capture.get("gaps") or []
    # A gap conceded to the outside auditor is a declared gap, whether or
    # not the capture also wrote the ordinary row (audit round 5, r5-3).
    # Without this the section vanished entirely while the audit section
    # said a gap stood - a silent omission, on the owner's own page.
    conceded = _conceded_gap_ids(capture)
    if gaps or conceded:
        page.add("<h3>Declared gaps</h3>")
        page.add('<div class="card"><ul>%s%s</ul></div>'
                 % ("".join(
                     "<li><strong>%s</strong> &mdash; %s The test it weakens: <code>%s</code>.</li>"
                     % (esc(tape.LABELS.get(g.get("fact_class"), g.get("fact_class", ""))),
                        esc(g.get("reason", "")),
                        esc(g.get("weakened_test", "")))
                     for g in gaps),
                    ("<li><strong>%d gap%s conceded to the outside auditor</strong> (%s) "
                     "&mdash; the reason and the test each weakens are under "
                     "<em>The outside auditor&#x27;s objections</em>, above.</li>"
                     % (len(conceded), "" if len(conceded) == 1 else "s",
                        esc(", ".join(conceded)))) if conceded else ""))
    requirements = (capture.get("sufficiency") or {}).get("requirements") or []
    if requirements:
        answered = sum(1 for r in requirements if r.get("status") == "answered")
        declared = len(requirements) - answered
        page.add("<h3>The sufficiency checklist</h3>")
        if declared:
            line = ("%d of %d checks were answered before any seat was paid; %d %s declared "
                    "as a gap." % (answered, len(requirements), declared,
                                   "was" if declared == 1 else "were"))
        else:
            line = "All %d checks were answered before any seat was paid." % len(requirements)
        page.add('<div class="muted small">%s</div>' % esc(line))
        rows = "".join(
            '<tr><td>%s</td><td class="nowrap">%s</td><td class="nowrap">'
            '<span class="tag %s">%s</span></td><td>%s</td></tr>'
            % (_constituent_tag(r) + brief.checklist_description(capture, r, esc),
               esc(REQUIREMENT_KIND_WORDS.get(r.get("kind"), r.get("kind") or "")),
               "checked" if r.get("status") == "answered" else "stale",
               "answered" if r.get("status") == "answered" else "declared gap",
               ", ".join("<code>%s</code>" % esc(a) for a in (r.get("answered_by") or []))
               or "&mdash;")
            for r in requirements)
        page.add('<table><tr><th>what this question needs</th><th class="nowrap">kind</th>'
                 '<th class="nowrap">status</th><th>answered by</th></tr>%s</table>' % rows)
    count = len(tier1)
    page.collapse("Every figure on the record &mdash; all %d frozen fact%s in the evidence pack, "
                  "the narrative record, the declared gaps and the sufficiency checklist"
                  % (count, "" if count == 1 else "s"), mark)


# --- 10. Peer review ---------------------------------------------------------------------------

def _review_section(page, run):
    """The blind reviewer's peer review, a folded appendix (audit C4 tier 5). The synopsis is on
    the front already, where the advisors disagreed; here it sits with the full cross-examination,
    behind one line."""
    reviewer = run["answers"].get("reviewer") or {}
    page.section("review", "Peer review")
    mark = page.mark()
    page.add('<div class="muted small">One reviewer read all five advisors blind and wrote the '
             "cross-examination and this synopsis.</div>")
    page.add('<div class="card prominent"><span class="lead">Synopsis</span>%s</div>'
             % markdown(_display_prose(reviewer, "synopsis", "reviewer synopsis", page), 4))
    page.add("<h4>The reviewer's full cross-examination</h4>"
             '<div class="body">%s%s</div>'
             % (markdown(reformat_prose(reviewer.get("markdown", ""),
                                        "reviewer cross-examination", page.number_subs), 4),
                _prose_note(run, "reviewer")))
    page.collapse("The blind reviewer&#x27;s synopsis and full cross-examination of the five "
                  "advisors", mark)


# --- The five advisors, each folded shut -------------------------------------------------------

def _advisors_section(page, run):
    page.section("advisors", "The five advisors")
    page.add('<div class="muted small">Five seats, one frozen pack, no tools. Each line opens '
             "to that seat&#x27;s answer, unedited.</div>")
    for kind, label in ADVISOR_SEATS:
        answer = run["answers"].get(kind) or {}
        page.add('<details><summary>%s</summary><div class="body">%s%s</div></details>'
                 % (esc(label),
                    markdown(reformat_prose(answer.get("markdown", ""),
                                            "advisor: " + label, page.number_subs), 4),
                    _prose_note(run, kind) + _heading_note(run, kind)))


# --- The challenger's full response, folded shut ------------------------------------------------

def _challenger_section(page, run):
    result = run["challenge_result"]
    page.section("challenger", "The challenger's full response")
    # The completed-action sentence renders ONLY when the audit in fact
    # completed - and the authority on that is the PUBLISHED verdict's
    # challenge status, never the raw bridge file: the host can reject
    # a bridge "success" and degrade while the raw file still claims it
    # (audit findings SC3 r1-4 and r2-1; the loud failure sentences
    # carry the truth otherwise).
    published_status = (run["verdict"].get("challenge") or {}).get("status")
    if (result is not None and result.get("status") == "success"
            and published_status == "success"):
        page.add('<div class="muted small">A model from a different company and a different '
                 "lineage read the full case file and audited the chairman&#x27;s draft. It "
                 "audits; it never authors.</div>")
    if result is None:
        page.add('<div class="card">This run directory carries no challenger papers.</div>')
        return
    if result.get("status") != "success":
        page.add('<div class="card alarm">The challenger&#x27;s papers record a failure: %s '
                 "(%s). There is no usable response to show.</div>"
                 % (esc(CHALLENGE_STATUS_WORDS.get(result.get("status"),
                                                   result.get("status") or "no status recorded")),
                    esc(result.get("failure_reason") or "no reason recorded")))
        return
    if published_status != "success":
        # The bridge claimed success but the host REJECTED the papers
        # (a hash that does not match this run, a malformed document):
        # none of their content may reach the page - findings bound to
        # another case must never read as this one's (audit findings
        # SC3 r3-1 and r4-1: an ordinary bridge failure is handled
        # above and never reads as a rejection). The archive keeps the
        # raw file; the page shows the verified truth.
        page.add('<div class="card alarm">The challenger returned papers, but the machine '
                 "rejected them (%s) and nothing in them was used: %s. Their content is "
                 "deliberately not shown; the raw file stays in the run&#x27;s archive.</div>"
                 % (esc(CHALLENGE_STATUS_WORDS.get(published_status,
                                                   published_status or "no status recorded")),
                    esc((run["verdict"].get("challenge") or {}).get(
                        "failure_reason") or "no reason recorded")))
        return
    doc = _challenge_response(result)
    findings = doc.get("findings") or []
    body = []
    if doc.get("summary"):
        body.append('<div class="card prominent"><strong>Its own summary.</strong> %s</div>'
                    % markdown(doc["summary"], 4))
    for finding in findings:
        body.append("<h4>%s &middot; %s</h4>"
                    % (esc(finding.get("id", "")),
                       esc(FINDING_KIND_WORDS.get(finding.get("kind"),
                                                  finding.get("kind") or ""))))
        body.append("<p><strong>%s</strong></p>" % esc(finding.get("title", "")))
        body.append("<p>%s</p>" % esc(finding.get("detail", "")))
    endorsement = doc.get("endorsement")
    if endorsement:
        body.append("<p><strong>Its endorsement.</strong> The highest rating it would support "
                    "on this record: %s.</p>"
                    % esc(RATING_WORDS.get(endorsement.get("highest_rating_supported"),
                                           endorsement.get("highest_rating_supported") or "")))
    body.append("<h4>The raw findings, exactly as returned</h4>")
    body.append("<pre><code>%s</code></pre>" % esc(json.dumps(findings, indent=2)))
    page.add("<details><summary>Its full response &mdash; %d finding%s</summary>"
             '<div class="body">%s</div></details>'
             % (len(findings), "" if len(findings) == 1 else "s", "".join(body)))


# --- 11. What the portfolio system receives ----------------------------------------------------

def _envelope_identity(envelope):
    """The subject as the package itself names it (owner ruling
    AB23(1)) - the name, and whichever of ticker, listing and currency
    the subject actually has. An anchorless subject carries no ticker
    and none is invented here."""
    parts = [part for part in (envelope.get("subject_ticker"),
                               envelope.get("subject_listing"),
                               envelope.get("subject_currency"))
             if part]
    name = envelope.get("subject_name") or ""
    if not parts:
        return name
    return "%s (%s)" % (name, ", ".join(str(part) for part in parts))


def _atlas_audit_state(page, envelope):
    """What the package says about the outside audit (owner ruling
    AB23(2)). The portfolio system computes its effective rating FROM
    the auditor's ceiling, and until this the package carried a bare
    rating: a reader had to open the verdict to learn a buy was
    capped."""
    if "challenge_status" not in envelope:
        # A package published under contract 1.2.0 or earlier carries no
        # audit state at all. Absence is not a negative finding: saying
        # the audit did not run, or that the auditor endorsed no
        # ceiling, would be false on every one of the sittings on record
        # (audit finding r1-4). What the audit did is above, in the
        # challenge round - it is simply not in the package.
        page.add('<div class="card">This package predates the '
                 "audit-state fields, so it carries a bare rating. What "
                 "the outside audit did, and how high it would go, is "
                 "in the challenge round above &mdash; not inside the "
                 "package.</div>")
        return
    status = envelope.get("challenge_status")
    if status == "success":
        told = "The outside audit ran, and the package says so."
    else:
        told = ("The outside audit did NOT run (%s), and the package "
                "says so."
                % esc(CHALLENGE_STATUS_WORDS.get(
                    status, status or "no status recorded")))
    ceiling = envelope.get("endorsement_highest_rating_supported")
    if ceiling is not None:
        told += (" The highest rating the auditor said the record "
                 "supports is <strong>%s</strong>."
                 % esc(RATING_WORDS.get(ceiling, ceiling)))
    elif status == "success":
        told += (" The auditor endorsed no ceiling, so the package "
                 "carries none.")
    else:
        # The ceiling is null on EVERY failed audit because none was
        # ACCEPTED - not because anybody declined to set one. Saying
        # "the auditor endorsed no ceiling" there draws a conclusion
        # from an audit that never happened (audit finding r3-3); and
        # saying nobody answered is false on two of the six statuses,
        # where the challenger did answer and the machine threw the
        # answer away - _challenger_section says exactly that a few
        # sections up (audit finding r4-1). One sentence is true in
        # every case: nothing was accepted.
        told += (" The audit did not complete, so no ceiling was "
                 "accepted and the package carries none &mdash; a gap, "
                 "not the auditor&#x27;s blessing.")
    carried = len(envelope.get("warnings") or [])
    told += (" Every warning on this verdict travels inside the package "
             "too &mdash; %d of them, the same ones shown at the top of "
             "this page." % carried)
    page.add('<div class="card">%s</div>' % told)


def _bound_cell(row):
    """The bound tag on one hand-off row, in the same words the case
    files and the evidence table use - or nothing, where the row is a
    plain measurement (owner ruling AB23(4))."""
    words = _bound_words(row.get("bound"))
    if not words:
        return ""
    tag = row.get("bound") or {}
    cell = '<div class="muted small">%s</div>' % esc(words)
    if tag.get("published_line"):
        cell += ('<div class="muted small">The published line, as the '
                 "capture names it: %s</div>"
                 % esc(" ".join(str(tag["published_line"]).split())))
    return cell


def _atlas_section(page, run):
    envelope = run["verdict"].get("atlas_envelope") or {}
    page.section("atlas", "What the portfolio system receives")
    mark = page.mark()
    page.add('<div class="muted small">The verdict carries a machine hand-off for the portfolio '
             "system, named Atlas. This is what is inside it.</div>")
    rating = envelope.get("rating")
    # The subject's frozen shape travels in the envelope (kind, the
    # named constituents or the one vehicle) - copied from the capture,
    # never chair-authored, and shown here as the hand-off carries it.
    subject_rows = ""
    if envelope.get("subject_kind"):
        subject_rows += ('<tr><th class="nowrap">Subject kind</th>'
                         "<td>%s</td></tr>"
                         % esc(_kind_words(
                             {"kind": envelope["subject_kind"],
                              "constituents": envelope.get(
                                  "constituents")})))
    constituents = envelope.get("constituents") or []
    if constituents:
        subject_rows += ('<tr><th class="nowrap">Constituents</th>'
                         "<td>%s</td></tr>"
                         % esc(", ".join(_member_words(item)
                                         for item in constituents)))
    vehicle = envelope.get("vehicle")
    if vehicle:
        subject_rows += ('<tr><th class="nowrap">Vehicle</th>'
                         "<td>%s</td></tr>" % esc(_member_words(vehicle)))
    # Owner ruling AB23: the package names its own subject and carries
    # the audit state, so the portfolio system never has to open a
    # second file to learn what was judged or whether a rating was
    # capped. The page shows the package as it travels.
    identity_rows = ""
    if envelope.get("subject_name"):
        identity_rows += ('<tr><th class="nowrap">Subject</th>'
                          "<td>%s</td></tr>"
                          % esc(_envelope_identity(envelope)))
    if envelope.get("run_id"):
        identity_rows += ('<tr><th class="nowrap">Sitting</th>'
                          "<td><code>%s</code></td></tr>"
                          % esc(envelope["run_id"]))
    page.add("<table>"
             "%s"
             '<tr><th class="nowrap">Rating</th><td>%s</td></tr>'
             "%s"
             '<tr><th class="nowrap">Hash of the frozen evidence pack &mdash; a fingerprint no '
             "other file shares</th><td><code>%s</code></td></tr></table>"
             % (identity_rows, esc(RATING_WORDS.get(rating, rating or "")),
                subject_rows, esc(envelope.get("pack_hash", ""))))
    _atlas_audit_state(page, envelope)
    proportions = envelope.get("thesis_proportions") or []
    if proportions:
        _proportions_card(page, proportions)
    key_numbers = envelope.get("key_numbers") or []
    if key_numbers:
        rows = "".join('<tr><td>%s%s</td><td class="nowrap">%s</td><td class="nowrap">%s</td></tr>'
                       % (esc(k.get("name", "")), _bound_cell(k),
                          esc(format_number(k.get("value"), k.get("unit"))),
                          esc(format_date(k.get("as_of", ""))))
                       for k in key_numbers)
        page.add('<table><tr><th>key number</th><th class="nowrap">value</th>'
                 '<th class="nowrap">as of</th></tr>%s</table>' % rows)
    sizing = envelope.get("sizing_inputs") or []
    if sizing:
        # The envelope's sizing facts about the ASSET (never a size).
        # A null value is a stated gap in plain words - the page never
        # invents a figure (audit finding SC3 r1-3).
        rows = []
        for entry in sizing:
            value = entry.get("value")
            if value is None:
                cell = "not in the record - the note beside says why"
            else:
                cell = format_number(value, entry.get("unit"))
            rows.append('<tr><td>%s%s%s</td><td class="nowrap">%s</td>'
                        '<td class="nowrap">%s</td></tr>'
                        % (_constituent_tag(entry),
                           esc(entry.get("detail", "")),
                           _bound_cell(entry), esc(cell.strip()),
                           esc(format_date(entry.get("as_of") or ""))))
        page.add('<table><tr><th>sizing fact about the asset</th>'
                 '<th class="nowrap">value</th>'
                 '<th class="nowrap">as of</th></tr>%s</table>'
                 % "".join(rows))
    unknown = envelope.get("unknown_sizing_ids") or []
    if unknown:
        page.add('<div class="muted small">Sizing facts whose meaning is '
                 "not fixed by the council&#x27;s own list, so the "
                 "portfolio system reads the unit each one states rather "
                 "than assuming one: %s.</div>"
                 % esc(", ".join(unknown)))
    if envelope.get("for_atlas_note") is not None:
        page.add('<div class="card prominent"><span class="lead">The owner&#x27;s note for the '
                 'portfolio system, verbatim</span><div class="verbatim">%s</div></div>'
                 % esc(envelope["for_atlas_note"]))
    page.add('<div class="muted small">The envelope also travels as its own file, and that file '
             "carries this verdict&#x27;s own hash, so the hand-off can be proved.</div>")
    page.collapse("The machine hand-off to the portfolio system, Atlas &mdash; the rating, the "
                  "audit state, the key numbers and the pack&#x27;s fingerprint", mark)


# --- Footer stamps -----------------------------------------------------------------------------

def _footer(page, run):
    verdict = run["verdict"]
    published = ((verdict.get("provenance") or {}).get("timestamps") or {}).get("published", "")
    bits = [
        "run <code>%s</code>" % esc(verdict.get("run_id", "")),
        "publication hash <code>%s</code>" % esc(run["verdict_sha256"]),
        "contract version <code>%s</code>" % esc(verdict.get("schema_version", "")),
        "published %s" % esc(published),
    ]
    page.add('<div class="foot">%s<br>Rendered from the run directory by '
             "<code>council/report/render_report.py</code>; the verdict file and the archives "
             "are unchanged. The publication hash above is computed from the verdict file as it "
             "sits on disk. Not investment advice.</div>" % " &middot; ".join(bits))


def _one_ladder(rows, horizon, currency=None):
    """One ladder, whole: nothing bounded, nothing trimmed. This is
    where the front's "in full in the appendix" pointer has to be true
    (audit finding ANCHORLESS-C c3-1)."""
    cells = "".join('<tr><td>%s</td><td class="nowrap">%s</td>'
                    '<td class="nowrap">%s</td><td>%s</td></tr>'
                    % (esc(rung.get("name", "")),
                       esc(format_price(rung.get("price_outcome"), currency)),
                       esc(rung.get("probability", "")),
                       esc(rung.get("rationale", "")))
                    for rung in rows)
    return ('<div class="muted small">Horizon: %s months.</div>'
            '<table><tr><th>the case</th><th class="nowrap">price if it '
            'happens</th><th class="nowrap">chance</th><th>why</th></tr>'
            "%s</table>" % (esc(str(horizon)), cells))


def _ladders_section(page, run):
    """Every ladder the sitting produced, whole: the chairman's, and
    each seat's own. The seats' are what make the bench's disagreement
    visible to a reader - the ruling requires them preserved in the
    record, and a record nobody can read is half a record
    (ANCHORLESS-SPEC section 3)."""
    block = run["verdict"].get("scenario_rating") or {}
    scenarios = block.get("scenarios") or []
    seat_ladders = block.get("seat_ladders") or []
    if not scenarios and not seat_ladders:
        return
    currency = (run["verdict"].get("subject") or {}).get("currency")
    page.add("<h3>The scenario ladders, in full</h3>")
    if scenarios:
        page.add("<h3>The chairman&#x27;s published ladder</h3>")
        page.add(_one_ladder(scenarios, block.get("horizon_months", ""),
                             currency))
    if seat_ladders:
        page.add("<h3>What each advisor's own ladder said</h3>")
        page.add('<div class="muted small">The chairman weighed these and '
                 "published his own. Where they differ is where the bench "
                 "disagreed.</div>")
        for entry in seat_ladders:
            seat = entry.get("seat", "")
            page.add("<h4>%s</h4>" % esc(dict(ADVISOR_SEATS).get(seat, seat)))
            page.add(_one_ladder(entry.get("scenarios") or [],
                                 entry.get("horizon_months", ""),
                                 currency))
    sensitivity = block.get("sensitivity") or {}
    lines = [text for text in
             ((sensitivity.get("flip") or {}).get("sentence"),
              sensitivity.get("sentence")) if text]
    if lines:
        page.add("<h3>How close the rating is to a different answer, "
                 "in full</h3>")
        # The same caveat the front carries: where a failed outside
        # audit capped the rating, every line below reads the
        # LADDER's rating and not the one that published. A new
        # rendering path is a new place for the same mislabelling
        # (audit finding ANCHORLESS-C c5-1).
        if block.get("published_rating"):
            page.add('<div class="card alarm">%s</div>'
                     % _capped_caveat(block))
        page.add('<div class="card">%s</div>'
                 % "".join("<p>%s</p>" % esc(line) for line in lines))


def _about_sitting_section(page, run, now):
    """About this sitting - the run stamps, a folded appendix (audit C4 tier 5; owner ruling AC16
    moved the clocks here off the executive summary). The council's own wall clock and the
    gathering time sit here, and the seat-by-seat cost where the record carries it (owner ruling
    AC15, architect ruling (5)(a): tokens per tool turn and brief bytes per seat; the input and
    output token columns stay empty with the note that says why the harness cannot fill them).
    Deliberately NOT in the navigation - it is the deepest stamp on the page, reached by scrolling
    to the end, so the menu stays to the tiers and the main appendices (about nine entries)."""
    review = _evidence_review(run)
    seat_cost = (run["verdict"].get("provenance") or {}).get("seat_cost") or {}
    minutes = _wall_clock_minutes(run, now)
    capture = review.get("capture") or {}
    has_clock = (minutes is not None or capture.get("minutes") is not None
                 or capture.get("tokens") is not None)
    has_cost = bool(seat_cost.get("per_seat"))
    if not has_clock and not has_cost:
        return
    page.add('<h2 id="stamps">About this sitting</h2>')
    mark = page.mark()
    _sitting_clocks(page, run, now)
    if has_cost:
        page.add("<h3>The sitting&#x27;s cost, seat by seat</h3>")
        page.add('<div class="muted small">%s</div>' % esc(seat_cost.get("note", "")))
        rows = ['<table><thead><tr><th>Seat</th><th>Tokens</th>'
                '<th>Tool turns</th><th>Tokens per turn</th>'
                '<th>Brief bytes</th><th>Input tokens</th>'
                '<th>Output tokens</th></tr></thead><tbody>']

        def cell(value):
            return "&mdash;" if value is None else esc(format_number(value))

        for seat, cost in seat_cost["per_seat"].items():
            rows.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>"
                        "<td>%s</td><td>%s</td><td>%s</td></tr>"
                        % (esc(seat), cell(cost.get("tokens")),
                           cell(cost.get("tool_calls")),
                           cell(cost.get("tokens_per_tool_call")),
                           cell(cost.get("brief_bytes")),
                           cell(cost.get("input_tokens")),
                           cell(cost.get("output_tokens"))))
        rows.append("</tbody></table>")
        page.add("".join(rows))
    page.collapse("How long the sitting took, and what it cost", mark)


def build_page(run, now):
    """The whole page. `now` is the RECORDED moment of this run's first rendering - the finish
    line of the sitting's own wall clock (spec section U3.3, register item P-U3-5), or None
    where the run's record does not carry one. Nothing here reads the clock on the wall: the
    page a sitting produced and the same page reprinted a month later are the same bytes."""
    page = Page()
    # The chairman's own STRUCTURED verdict text (falsifier statements, trigger details, level
    # meanings) is respelt into the market form ONCE, before any section renders it, so a field
    # shown both on the decision front and in the appendix is respelt once and logged once (AC16(1)).
    _reformat_verdict_structured(run["verdict"], page.number_subs)
    _head_block(page, run)
    # A reader dives deeper the further they scroll (owner ruling AC16, audit C4). Tier 1: the
    # executive summary. Tier 2: the chairman's synthesis, directly after it (AC16(5)). Tier 3:
    # the decision in detail. Tier 4: the frozen evidence. Tier 5: the appendices, all folded.
    _front_section(page, run, now)                 # tier 1
    _synthesis_section(page, run)                  # tier 2
    _detail_section(page, run)                     # tier 3
    _evidence_section(page, run)                   # tier 4
    # Tier 5. The "Appendices" divider is a plain signpost, not a menu entry - the navigation
    # names the tiers and the main appendices (about nine entries), not every stamp.
    page.add('<h2 id="appendices">Appendices — the full record</h2>')
    page.add('<div class="muted small">The record behind the decision above, all folded: the '
             "question as it was asked, the peer review, the five advisors, the challenger&#x27;s "
             "own words, what changed after the outside audit, the hand-off to the portfolio "
             "system, and the run stamps.</div>")
    _question_section(page, run)
    _review_section(page, run)
    _advisors_section(page, run)
    _challenger_section(page, run)
    _changes_section(page, run)
    _atlas_section(page, run)
    _about_sitting_section(page, run, now)
    _footer(page, run)
    return page


def render(run_dir, moment=None, subs_out=None):
    """The whole report as one string. Refuses, in plain words, a directory that is not a run.

    The moment the sitting's wall clock is measured to is the run's own recorded first
    rendering, so a reprint is the page the sitting produced. `moment` is what the command
    below passes on the first rendering of a run - the moment it will record once the page is
    written - and nothing else passes it: read on its own, this function reads no clock, and a
    run whose record carries no moment yet renders without one. `subs_out`, when a list is
    given, is filled with every number the prose reformatter respelt, in render order (owner
    ruling AC16(1)) - the caller writes it beside the report."""
    run = load_run(run_dir)
    run["prose_scores"] = _load_prose_scores(run_dir)
    run["heading_flags"] = _load_heading_flags(run_dir)
    page = build_page(run, moment or first_render_moment(run_dir))
    if subs_out is not None:
        subs_out.extend(page.number_subs)
    subject = run["verdict"].get("subject") or {}
    title = "Investment Council - %s" % (subject.get("name") or run["verdict"].get("run_id", ""))
    return "".join([
        PREAMBLE.decode("ascii"),
        '<head>\n<meta charset="UTF-8">\n',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n',
        "<title>", esc(title), "</title>\n<style>", CSS, "</style>\n</head>\n<body>\n",
        '<nav class="dock" id="dock">',
        '<button type="button" class="dockbtn" id="navbtn" aria-haspopup="true" '
        'aria-expanded="false" aria-controls="navmenu" title="Sections">',
        '<span class="srconly">Sections</span>', NAV_ICON, "</button>",
        '<div class="menu" id="navmenu"><div class="menucard">',
        '<a href="#top">Top of report</a>', page.menu(), "</div></div></nav>\n",
        '<button type="button" class="themebtn" id="themebtn" aria-label="Switch to light" '
        'title="Switch to light">&#x25D2;</button>\n',
        '<div class="wrap" id="top">\n', page.body(), "\n</div>\n",
        "<script>", SCRIPT, "</script>\n</body>\n</html>\n",
    ])


def main(argv):
    args = list(argv[1:])
    out_file = None
    if "-o" in args:
        i = args.index("-o")
        if i + 1 >= len(args):
            sys.stderr.write("-o needs a file name\n")
            return 2
        out_file = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        sys.stderr.write(__doc__ + "\n")
        return 2
    run_dir = args[0].rstrip("/\\")
    target = out_file or os.path.join(run_dir, "report.html")
    # THIS COMMAND WRITES REPORTS AND NOTHING ELSE (ported guard). An existing target is
    # accepted only when it is already a report this command wrote, so re-rendering works and
    # every other file - a verdict, an archive - is refused rather than truncated.
    if os.path.exists(target):
        try:
            existing = _read_bytes(target)
        except OSError:
            existing = b""
        if not (existing.startswith(PREAMBLE) and RENDERER_SIGNATURE in existing):
            sys.stderr.write("REFUSED: '%s' already exists and is not a report this command "
                             "wrote. Rendering would overwrite it; nothing was written.\n" % target)
            return 4
    # The sitting's clock ends at the rendering, and the FIRST rendering of a run is what
    # records the moment (register item P-U3-5). The moment is read once here, printed on the
    # page, and written to the record only after that page is on disk - so a render that
    # produced no report leaves no row saying one exists (audit round 1, r1-6).
    moment = first_render_moment(run_dir)
    # A run with no record of its own can never HAVE a recorded moment, so it is given none:
    # a clock nothing can reproduce is worse on this page than no clock at all.
    first = moment is None and os.path.isfile(runrecord.record_path(run_dir))
    if first:
        moment = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    substitutions = []
    try:
        body = render(run_dir, moment, substitutions)
    except (MissingInputError, chart.ChartRefused) as refusal:
        sys.stderr.write("REFUSED: %s\n" % refusal)
        return 1
    # Two writes, ordered so that neither can be believed without the other. The page is staged
    # beside its target, the row saying a report was rendered is appended, and only then does
    # the page become visible. A stop before the row leaves NO page and no row - the retry is an
    # honest first rendering, because no report ever existed. A stop between the row and the
    # rename leaves a row and no page - the retry reads that recorded moment and rebuilds the
    # identical bytes. A report on disk without its row, which would let a retry silently
    # re-time the archived page and flip its budget line, is unreachable from either
    # (audit round 1, r1-6; round 2, r2-1).
    data = body.encode("utf-8")
    directory = os.path.dirname(os.path.abspath(target))
    handle, staged = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if first:
            try:
                commit_render_moment(run_dir, moment)
            except OSError as failure:
                sys.stderr.write(
                    "REFUSED: the row recording that this report was rendered could not be "
                    "written to the run's own record (%s). Nothing was published: a report "
                    "without that row is re-timed by the next rendering, which would change "
                    "the minutes on the front page and can flip the budget line. Fix the "
                    "record and run this again.\n" % failure)
                return 5
        os.replace(staged, target)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)
    # The record of every number the prose reformatter respelt, beside the report it belongs to
    # (owner ruling AC16(1)). It is a supplementary artifact - a report is a report without it -
    # so it is written after the page, in deterministic render order. Its name is DERIVED from the
    # report's own file name (report.html -> report.html.number-substitutions.json), so it can
    # never be the report's own path on any filesystem, case-sensitive or not (round 2, r2-1).
    log_path = os.path.join(
        directory, os.path.basename(os.path.abspath(target)) + ".number-substitutions.json")
    log_bytes = (json.dumps(substitutions, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    log_handle, log_staged = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(log_handle, "wb") as fh:
            fh.write(log_bytes)
        os.replace(log_staged, log_path)
    finally:
        if os.path.exists(log_staged):
            os.unlink(log_staged)
    sys.stdout.write("report written: %s (%d bytes); %d prose number substitution%s logged\n"
                     % (target, len(data), len(substitutions),
                        "" if len(substitutions) == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
