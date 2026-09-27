"""The chairman's fields (UPGRADE-2 U5(b), owner rulings AC5 and AC35(3),
the spec's chair section; READ-C1, owner ruling AC44(1)): the one line
answering the owner's question, what decided it, the business in his own
words, and the decisive numbers as he reads them. Also the two checks
READ-C1 adds on his tripwire lists: one threshold per measure on the
scorecard (AC44(2)) and the price-level tolerance (AC44(4)).

The keys and their plain labels are data in the seat-answer contracts
(`chair_fields` in seat_answers.json), so the report, the chair's brief and
this check read one list. The shape of each field is the published verdict
contract's own (verdict_schema.json), so a field this module passes can
never make the publisher refuse the verdict.

Pure functions, shared by the host (the soft check at ingest and its one
re-ask) and the publisher (which writes null for a field that is not in
its shape) - the publisher cannot import the host, so the rules live here.
Nothing here refuses a document: a problem is asked about once, then the
answer stands.
"""

import decimal
import json
import os
import re

from council.evidence import gate, tape, trace
from council.lib import subjects, validate

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SEAT_ANSWERS_PATH = os.path.join(ROOT, "council", "schemas",
                                 "seat_answers.json")
VERDICT_SCHEMA_PATH = os.path.join(ROOT, "council", "schemas",
                                   "verdict_schema.json")

# The business read's word cap (the spec's chair section), counted on
# whitespace-separated words as the gate counts every word limit.
BUSINESS_READ_WORDS = 120

# The one-line answer's word cap (owner ruling AC44(1), the READ-C seed),
# counted the same way.
ANSWER_LINE_WORDS = 30

_WORD_CAPS = {"business_read": BUSINESS_READ_WORDS,
              "answer_line": ANSWER_LINE_WORDS}


def _read(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def fields(path=None):
    """The chairman's fields in reading order, each {"key", "label"}."""
    return [dict(field) for field in
            _read(path or SEAT_ANSWERS_PATH)["chair_fields"]]


def keys():
    return [field["key"] for field in fields()]


def labels():
    return {field["key"]: field["label"] for field in fields()}


def _shapes():
    properties = _read(VERDICT_SCHEMA_PATH)["properties"]
    return {key: properties[key] for key in keys()}


def shape_problem(key, value, shapes=None):
    """Why VALUE is not the field in the shape the verdict publishes, or
    None where it is. Null or absent is a problem: the verdict's null means
    the chairman did not supply the field."""
    if value is None:
        return "it is missing"
    errors = validate.validate(value, (shapes or _shapes())[key], key)
    if errors:
        return "it is not in the shape asked: %s" % "; ".join(errors[:3])
    return None


def published_value(key, value, shapes=None):
    """What the publisher writes: the chairman's value where it is in the
    verdict's shape, else null."""
    return value if shape_problem(key, value, shapes) is None else None


def _fold(text):
    return " ".join(str(text).split()).casefold()


def required_rows(capture):
    """One (constituent, metric name) per decisive metric of every business
    frame in the capture, in capture order. The constituent is the frame's
    ticker where it names a member of the subject's expression (a basket's
    or a theme's constituent, or its vehicle), else None - a single name's
    own frame. A subject with no frame has none."""
    members = subjects.expression_tickers(capture.get("subject") or {})
    rows = []
    for ticker, frame in (capture.get("business_frame") or {}).items():
        constituent = ticker if ticker in members else None
        for metric in (frame or {}).get("decisive_metrics") or []:
            rows.append((constituent, metric.get("name")))
    return rows


ROW_RULE = ("a row names the metric as the case file's table does and, on "
            "a basket or a theme, carries its constituent's ticker; on a "
            "single name its constituent is null")


def _row_words(constituent, name):
    return ('"%s"' % name if constituent is None
            else '"%s" of %s' % (name, constituent))


def missing_rows(rows, capture):
    """The decisive metrics ROWS carries no row for, in capture order. A row
    matches on its constituent exactly and its metric's name after trimming
    and case-folding; extra rows are allowed."""
    have = {(row.get("constituent"), _fold(row.get("metric")))
            for row in rows if isinstance(row, dict)}
    return [(constituent, name) for constituent, name
            in required_rows(capture)
            if (constituent, _fold(name)) not in have]


def problems(verdict, capture):
    """Every field of this chair verdict the soft check asks about, as
    [{"key", "problem"}] in reading order; empty means every field
    stands."""
    shapes = _shapes()
    found = []
    for key in keys():
        value = verdict.get(key)
        problem = shape_problem(key, value, shapes)
        if problem is None and key in _WORD_CAPS:
            words = len(value.split())
            if words > _WORD_CAPS[key]:
                problem = ("it is %d words; the cap is %d"
                           % (words, _WORD_CAPS[key]))
        if problem is None and key == "decisive_metrics_read":
            missing = missing_rows(value, capture)
            if missing:
                problem = ("it carries no row for the decisive metric(s) %s"
                           " - %s"
                           % (", ".join(_row_words(constituent, name)
                                        for constituent, name in missing),
                              ROW_RULE))
        if problem is not None:
            found.append({"key": key, "problem": problem})
    return found


# The decisive-numbers row mark (architect ruling closing P-U5b-2, owner
# rulings AC13(1) and AC19): a row whose value writes a figure that traces
# to none of the facts its metric is answered by - read by the prose
# marker's own rule - carries this mark and the verdict one warning line.
# A MARK, never a refusal and never a re-ask.
ROW_MARK = "not traced to a recorded fact"


def _metric_bases(capture, cfg):
    """{(constituent, folded metric name): [bases]} - each decisive metric's
    answered_by facts, any derived fact computed from them alone (on a
    basket or a theme only one wearing no member suffix or the row's own,
    P-U5b-4), and the figures an answering passage declares (P-U5b-3)."""
    subject = capture.get("subject") or {}
    members = subjects.expression_tickers(subject)
    tier1 = capture.get("tier1") or []
    by_id = {fact.get("id"): fact for fact in tier1}
    passages = {passage.get("id"): passage
                for passage in capture.get("tier2") or []}
    found = {}
    for ticker, frame in (capture.get("business_frame") or {}).items():
        constituent = ticker if ticker in members else None
        suffix = gate.frame_suffix(subject, ticker)
        for metric in (frame or {}).get("decisive_metrics") or []:
            ids = set(metric.get("answered_by") or [])
            facts = [by_id[i] for i in metric.get("answered_by") or []
                     if i in by_id] + [
                fact for fact in tier1 if fact.get("id") not in ids
                and (fact.get("derived") or {}).get("operands")
                and {op.get("fact_id") for op in
                     fact["derived"]["operands"]} <= ids
                and not (suffix and gate._id_suffix(fact.get("id"))
                         not in ("", suffix))]
            bases = trace.facts_bases(facts, cfg)
            for i in metric.get("answered_by") or []:
                if i in passages:
                    bases += trace.figures_bases(
                        passages[i].get("figures"), cfg,
                        passages[i].get("text"))
            found.setdefault((constituent, _fold(metric.get("name"))),
                             []).extend(bases)
    return found


def mark_rows(rows, capture, cfg):
    """(ROWS as published, the metric names marked): each row copied, the
    mark written by the host alone - set where the row's value writes a
    figure that traces to no fact of its metric, removed otherwise."""
    if not isinstance(rows, list):
        return rows, []
    found = _metric_bases(capture, cfg)
    published, marked = [], []
    for row in rows:
        row = dict(row)
        row.pop("mark", None)
        bases = found.get((row.get("constituent"), _fold(row.get("metric"))),
                          [])
        if trace.untraced(row.get("value"), bases, cfg):
            row["mark"] = ROW_MARK
            marked.append(row.get("metric"))
        published.append(row)
    return published, marked


# The keys the host writes onto a field after the chairman wrote it: the
# row mark. A field compared with what he wrote ignores them (P-U5b-5).
HOST_KEYS = ("mark",)


def as_written(key, value):
    """VALUE of field KEY with every host-written key removed - the field
    as the chairman wrote it."""
    if key == "decisive_metrics_read" and isinstance(value, list):
        return [{k: v for k, v in row.items() if k not in HOST_KEYS}
                if isinstance(row, dict) else row for row in value]
    return value


def rows_warning(marked):
    """The one warnings line naming every marked row, or None."""
    if not marked:
        return None
    return ("The chairman's decisive numbers: the value he gave for %s is "
            "not traced to a recorded fact of the case file, and is marked "
            "in the table." % ", ".join('"%s"' % name for name in marked))


# The one-line answer's figures (owner rulings AC44(1) and AC19): traced to
# the case file's recorded facts and the chairman's own key numbers by the
# prose marker's rule. An untraced figure is MARKED where the page prints the
# line - never refused, never re-asked.

def answer_line_bases(key_numbers, capture, cfg):
    """The bases the one-line answer is traced against: every recorded fact
    of the case file, every figure a case-file passage declares (read as
    mark_rows reads an answering passage's - audit r5-1) and every key
    number the chairman gave."""
    return (trace.facts_bases(capture.get("tier1") or [], cfg)
            + [base for passage in capture.get("tier2") or []
               for base in trace.figures_bases(
                   passage.get("figures"), cfg, passage.get("text"))]
            + trace.facts_bases(key_numbers or [], cfg))


def answer_line_untraced(text, key_numbers, capture, cfg):
    """The figures the one-line answer TEXT writes that trace to none of
    answer_line_bases, as written - the figures the page marks."""
    return [token.text for token in trace._classify(
        str(text or ""), answer_line_bases(key_numbers, capture, cfg), cfg)
        if token.status == "untraced"]


# The scorecard (owner ruling AC44(2), option (b)): each entry of the three
# tripwire lists may name the measure it tests, and the chairman gives one
# threshold per measure. A measure given two different numbers draws ONE
# plain line in the warnings - a mark, never a refusal - and a flag on its
# row of the page. Each constituent of a basket is its own row (audit
# UPGRADE2-READ-C1 r1-4).
#
# The number reader (the architect's ruling of round three, replacing the
# reader rounds one and two patched - r2-1, r2-2): an entry's number is the
# level it carries with its recorded unit or, where it carries none (a
# falsifier, an event trigger), the first figure its words write with the
# unit or scale word beside it, after every date form is cut out of the
# words. Both go through ONE function, canonical(), into a kind and a
# magnitude: a percent or a fraction is a percent number, a multiple is its
# own kind, a currency amount is in base units at its scale, a count is
# itself, and an unknown unit keeps its own kind. Two numbers of one measure
# conflict only when their kind is the same and their magnitude is not. A
# price trigger gives no number: the chairman's buy level and add-more level
# are steps of one price measure, never a conflict (r1-6).
LISTS = ("invalidation_levels", "reopening_triggers", "falsifiers")
SCORECARD_WARNING_OPEN = "The chairman's scorecard tests one measure at more "

_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_SIGNED_FIGURE = re.compile(r"[+-]?\d[\d,]*(?:\.\d+)?")

# The words beside a figure that make it a currency amount, besides a
# currency sign and the currency codes the ruled scale units name.
_CURRENCY_WORDS = ("dollar", "dollars")
_AMOUNT_SIGNS = ("$", "\u20ac", "\u00a3")
_MULTIPLE_UNITS = ("x", "\u00d7")
_COUNT_UNITS = ("", "count")
_FRACTION = "fraction_"
_WORD_BEFORE = re.compile(r"(?<![A-Za-z])([A-Za-z]+)\s*$")


def measure_name(entry):
    """The entry's measure as written, spaces collapsed, or None."""
    name = entry.get("measure") if isinstance(entry, dict) else None
    if not isinstance(name, str) or not name.strip():
        return None
    return " ".join(name.split())


def _currency_codes(cfg):
    """The currency codes the ruled scale units are written in, and the
    codes whose signs the price-level warning writes."""
    return ({unit.split("_")[0] for unit in cfg["currency_scale_units"]}
            | set(_CURRENCY_SIGNS))


def _fraction_units(cfg):
    """Every fraction unit: the prose marks' own and every fraction unit
    the floors allow a capture to use."""
    return (set(cfg["fraction_units"])
            | set(cfg.get("allowed_fraction_units") or ()))


def _fraction_phrases(cfg):
    """{the words a fraction is written with in prose: its unit} - the
    unit's own tail after its fraction prefix: "of price" for
    fraction_of_price, "annualized" for fraction_annualized."""
    return {unit[len(_FRACTION):].replace("_", " ").lower(): unit
            for unit in _fraction_units(cfg) if unit.startswith(_FRACTION)}


def _scale_exponent(scale, cfg):
    """The power of ten a scale word or letter multiplies by, or None."""
    scale = str(scale or "").strip()
    if len(scale) == 1:
        return cfg["scale_words"].get(scale)
    return cfg["scale_words_ci"].get(scale.lower())


def canonical(value, unit, cfg, scale=None):
    """A figure VALUE with its UNIT (a recorded unit, or the unit word or
    sign beside it in prose) and its SCALE word as (kind, magnitude). The one
    reader of a number on both sides of the scorecard: a percent or a
    fraction is a percent number; a multiple is its own kind; a currency
    amount is in base units, scaled by its recorded unit or its scale word;
    a count is itself; any other unit keeps its own kind, so it is compared
    only with the same unit."""
    unit = str(unit or "").strip()
    lowered = unit.lower()
    exponent = _scale_exponent(scale, cfg) or 0
    if (unit in cfg["percent_units"] or lowered in cfg["percent_words"]
            or lowered == "per cent"):
        return "percent", value
    if unit in _fraction_units(cfg) or lowered in _fraction_phrases(cfg):
        return "percent", value * 100
    if lowered in _MULTIPLE_UNITS:
        return "multiple", value
    codes = _currency_codes(cfg)
    if unit in cfg["currency_scale_units"]:
        exponent += cfg["currency_scale_units"][unit]
    elif not (unit in codes or unit in _AMOUNT_SIGNS
              or lowered in _CURRENCY_WORDS
              or lowered in {code.lower() for code in codes}
              or any(unit.startswith(code + "_per_") for code in codes)):
        if lowered in _COUNT_UNITS:
            return "count", value.scaleb(exponent)
        return "unit " + unit, value.scaleb(exponent)
    return "currency", value.scaleb(exponent)


def _level_number(entry, cfg):
    """(the level as written, its kind and magnitude) or None."""
    match = _SIGNED_FIGURE.search(str(entry.get("level") or ""))
    value = trace._decimal(match.group(0).lstrip("+")) if match else None
    if value is None:
        return None
    unit = str(entry.get("unit") or "")
    written = match.group(0)
    if unit in cfg["percent_units"]:
        written += "%"
    return written, canonical(value, unit, cfg)


# Every date form, cut out of the words before they are read, so no digit of
# a date is ever a threshold: an ISO date; a period label (a quarter, a
# half, a fiscal or calendar year, digits written onto letters, or a
# quarter written number-first); a month name with its day, either order;
# an ordinal; a bare four-digit year in the ruled range (below).
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_PERIOD_LABEL = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z]+['\u2019]?\d+|\d[QqHh](?:['\u2019]?\d+)?)"
    r"(?![A-Za-z0-9])")
_ORDINAL = re.compile(r"(?<![\d.,])\d+(?:st|nd|rd|th)(?![A-Za-z])",
                      re.IGNORECASE)
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
_NOT_A_FIGURE_AFTER = r"(?![\d%]|[.,]\d|\s*(?:%|per\s*cent\b|percent\b))"


def _month_days(cfg):
    """The two orders of a month name with its day: month first, day first."""
    months = "|".join(sorted((re.escape(m) for m in cfg["month_words"]),
                             key=len, reverse=True))
    if not months:
        return []
    return [re.compile(r"(?<![A-Za-z])(?:%s)\.?\s+%s%s(?![A-Za-z])"
                       % (months, _DAY, _NOT_A_FIGURE_AFTER), re.IGNORECASE),
            re.compile(r"(?<![\d.,$\u20ac\u00a3])%s\s+(?:%s)(?![A-Za-z])"
                       % (_DAY, months), re.IGNORECASE)]


def _without_dates(text, cfg):
    """TEXT with every date form blanked to spaces, offsets unchanged."""
    spans = [m.span() for m in _ISO_DATE.finditer(text)]
    spans += [m.span() for m in _PERIOD_LABEL.finditer(text)]
    spans += [m.span() for m in _ORDINAL.finditer(text)]
    for pattern in _month_days(cfg):
        spans += [m.span() for m in pattern.finditer(text)
                  if cfg["day_min"] <= int(m.group(1)) <= cfg["day_max"]]
    for match in trace._TOKEN.finditer(text):
        digits = match.group("digits")
        exponent, _end, is_percent = trace._read_after(text, match, cfg)[:3]
        if (len(digits) == 4 and digits.isdigit() and exponent is None
                and not is_percent and not match.group("currency")
                and not match.group("sign_pre") and not match.group("sign")
                and cfg["year_min"] <= int(digits) <= cfg["year_max"]):
            spans.append(match.span())
    chars = list(text)
    for lo, hi in spans:
        chars[lo:hi] = " " * (hi - lo)
    return "".join(chars)


def _unit_word_end(text, at, unit):
    """Where the recorded UNIT, written as words at AT of TEXT (any case,
    singular or plural), ends - or None."""
    words = [word for word in re.split(r"[\s_]+", unit.strip()) if word]
    if not words or not all(word.isalpha() for word in words):
        return None
    last = words[-1]
    forms = {last, last + "s", last + "es"}
    for tail in ("s", "es"):
        if last.lower().endswith(tail) and len(last) > len(tail):
            forms.add(last[:-len(tail)])
    pattern = re.compile(
        r"\s*%s(?:%s)(?![A-Za-z])" % (
            "".join(re.escape(word) + r"\s+" for word in words[:-1]),
            "|".join(sorted((re.escape(form) for form in forms),
                            key=len, reverse=True))),
        re.IGNORECASE)
    found = pattern.match(text, at)
    return found.end() if found else None


def _words_unit(text, match, value, cfg, units=()):
    """(the unit word or sign beside a figure MATCH of TEXT, its scale word,
    where the figure as written starts and ends). A currency code before or
    after the figure, a fraction unit's own tail word, and a word naming
    one of UNITS - the measure's own recorded units - are each the figure's
    unit; a bare figure below one, no word beside it, against a
    fraction level is that fraction."""
    exponent, end, is_percent, following, after_number = trace._read_after(
        text, match, cfg)
    scale = text[after_number:end].strip() if exponent is not None else None
    start = match.start()
    if is_percent:
        return "%", scale, start, end
    if match.group("currency"):
        return match.group("currency"), scale, start, end
    rest = text[end:]
    if rest[:1].lower() in _MULTIPLE_UNITS and not rest[1:2].isalpha():
        return rest[:1], scale, start, end + 1
    word = trace._WORD_AFTER.match(text, end)
    codes = {code.lower() for code in _currency_codes(cfg)}
    if word and word.group(1).lower() in codes.union(_CURRENCY_WORDS):
        after = trace._SCALE_AFTER.match(text, word.end())
        if (scale is None and after
                and _scale_exponent(after.group("scale"), cfg) is not None):
            return word.group(1), after.group("scale"), start, end
        return word.group(1), scale, start, end
    before = _WORD_BEFORE.search(text[:start])
    if before and before.group(1).lower() in codes:
        return before.group(1), scale, before.start(1), end
    lowered = " ".join(rest.lower().split())
    for phrase, unit in _fraction_phrases(cfg).items():
        if (lowered.startswith(phrase)
                and not lowered[len(phrase):len(phrase) + 1].isalpha()):
            return unit, scale, start, end
    for unit in units:
        for at, at_scale in ((after_number, None), (end, scale)):
            unit_end = _unit_word_end(text, at, unit)
            if unit_end is not None:
                return unit, at_scale, start, unit_end
    fractions = [unit for unit in units if unit in _fraction_units(cfg)]
    if (scale is None and fractions and abs(value) < 1
            and not trace._WORD_AFTER.match(text, end)):
        return fractions[0], None, start, end
    return "", scale, start, end


def _words_number(text, cfg, units=()):
    """(the first figure TEXT writes once its dates are cut out, as written,
    with its kind and magnitude) or None. UNITS are the measure's own
    recorded units, read when a word beside the figure names one."""
    text = _without_dates(str(text or ""), cfg)
    match = trace._TOKEN.search(text)
    value = trace._decimal(match.group("digits")) if match else None
    if value is None:
        return None
    if (match.group("sign_pre") or match.group("sign")) == "-":
        value = -value
    unit, scale, start, end = _words_unit(text, match, value, cfg, units)
    return (text[start:end].strip(), canonical(value, unit, cfg, scale))


def _number(list_name, entry, cfg, units=()):
    """(the number as written, its kind and magnitude) for one tripwire
    entry, or None. UNITS are its measure's recorded units."""
    if list_name == "falsifiers":
        return _words_number(entry.get("statement"), cfg, units)
    if list_name == "reopening_triggers":
        if entry.get("kind") == "price":
            return None
        return (_level_number(entry, cfg)
                or _words_number(entry.get("detail"), cfg, units))
    return _level_number(entry, cfg)


def _recorded_units(lists, cfg):
    """The units the measure's lines record beside a level, in the order
    met: the words its figures in prose are read against."""
    units = []
    for list_name in ("invalidation_levels", "reopening_triggers"):
        for entry in lists[list_name]:
            unit = str(entry.get("unit") or "").strip()
            if (unit and unit not in units
                    and not (list_name == "reopening_triggers"
                             and entry.get("kind") == "price")
                    and _level_number(entry, cfg) is not None):
                units.append(unit)
    return units


def _in_conflict(numbers):
    """Of NUMBERS ({(kind, magnitude): as written}), the ones that conflict -
    every number of a kind given more than one magnitude - as written, in
    the order met."""
    kinds = {}
    for kind, _magnitude in numbers:
        kinds[kind] = kinds.get(kind, 0) + 1
    return [written for (kind, _magnitude), written in numbers.items()
            if kinds[kind] > 1]


def scorecard(tripwires, cfg):
    """The measured entries grouped by measure, in the order each measure
    first appears across the three lists: [(name, {list: [entries]},
    [the numbers in conflict, as written])] - the last is empty unless the
    measure was given two magnitudes of one kind. Two names are one measure
    after trimming and case-folding; the name shown is the first spelling
    met, with the constituent after it where the entry is bound to one -
    each constituent is its own row. Entries without a measure are not
    here: they keep their own place."""
    groups = {}
    for list_name in LISTS:
        for entry in (tripwires or {}).get(list_name) or []:
            name = measure_name(entry)
            if name is None:
                continue
            constituent = str(entry.get("constituent") or "").strip()
            shown = "%s (%s)" % (name, constituent) if constituent else name
            group = groups.setdefault(
                (_fold(constituent), _fold(name)),
                (shown, {key: [] for key in LISTS}, {}))
            group[1][list_name].append(entry)
    for _name, lists, numbers in groups.values():
        units = _recorded_units(lists, cfg)
        for list_name in LISTS:
            for entry in lists[list_name]:
                found = _number(list_name, entry, cfg, units)
                if found is not None:
                    numbers.setdefault(found[1], found[0])
    return [(name, lists, _in_conflict(numbers))
            for name, lists, numbers in groups.values()]


def conflicting_measures(tripwires, cfg):
    """Each measure given two numbers of one kind: [(name, [numbers])]."""
    return [(name, numbers) for name, _lists, numbers
            in scorecard(tripwires, cfg) if numbers]


def and_list(words):
    """WORDS joined as a reader writes a list: "a, b and c"."""
    words = list(words)
    if len(words) < 2:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def scorecard_warning(conflicts):
    """The one warnings line naming every measure given two numbers, or
    None."""
    if not conflicts:
        return None
    return (SCORECARD_WARNING_OPEN + "than one number: %s. Each measure "
            "should be tested at one number." % "; ".join(
                '"%s" at %s' % (name, and_list(numbers))
                for name, numbers in conflicts))


def without_measures(tripwires):
    """TRIPWIRES as the Atlas hand-off carries them: every entry copied
    without its measure, so the hand-off reads the lists exactly as it did
    before a measure could be named (AC44(2))."""
    return {key: ([{k: v for k, v in entry.items() if k != "measure"}
                   if isinstance(entry, dict) else entry for entry in value]
                  if isinstance(value, list) else value)
            for key, value in (tripwires or {}).items()}


# The chairman's price-level mark (UPGRADE-2 U5(b), the architect's ruling 5
# on spec U4.4; widened and reworded by owner ruling AC44(4)). A MARK, never
# a refusal (the AC19 principle): the verdict carries one line in its
# warnings list where no price tripwire sits at a level the market-structure
# advisor named, or at or within the ruled tolerance of a turning point the
# price history carries - the year's lowest or highest close, a moving
# average. The line says, in plain words, which level is the chairman's own
# judgement and names the nearest turning point.
PRICE_LEVEL_JUDGEMENT = "price level is the chairman's own judgement"
# A verdict with no price trigger at all still draws the line, as it did
# before the wording changed (audit UPGRADE2-READ-C1 r1-3).
NO_PRICE_LEVEL_WARNING = (
    "The chairman named no price level, so none of his levels can be "
    "checked against the price history.")

# What the market-structure answer writes that is never a price level: a
# percentage and a written date's parts (audit round 1, r1-2).
_NOT_A_LEVEL = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d[\d,]*(?:\.\d+)?\s?(?:%|percent\b|per cent\b)",
    re.IGNORECASE)

_CURRENCY_SIGNS = {"USD": "$", "EUR": "€", "GBP": "£"}


def price_level_tolerance(path=None):
    """The ruled tolerance, as a share of the turning point's own value,
    read from the seat-answer contracts (owner ruling AC44(4))."""
    return decimal.Decimal(str(_read(path or SEAT_ANSWERS_PATH)
                               ["price_level_tolerance"]))


def _figure(text):
    """The first figure written in TEXT as a Decimal, or None."""
    match = _FIGURE.search(str(text or ""))
    if match is None:
        return None
    try:
        return decimal.Decimal(match.group(0).replace(",", ""))
    except decimal.InvalidOperation:
        return None


def _at_its_precision(value, level):
    """True where VALUE, rounded to the places LEVEL is written to, is
    LEVEL: a tape average carried to many places is named by a level
    written to the cent."""
    figure = _figure(value)
    if figure is None:
        return False
    try:
        rounded = figure.quantize(decimal.Decimal(1).scaleb(
            min(level.as_tuple().exponent, 0)), rounding=decimal.ROUND_HALF_UP)
    except decimal.InvalidOperation:
        return False
    return rounded == level


def _near(value, level, tolerance):
    """True where LEVEL sits at VALUE read at its precision, or within
    TOLERANCE of it as a share of VALUE."""
    if _at_its_precision(value, level):
        return True
    figure = _figure(value)
    if figure is None or figure == 0:
        return False
    return abs(level - figure) <= tolerance * abs(figure)


def _turning_points(capture, unit):
    """The price history's turning points in UNIT: every tape fact written
    in the trigger's own unit (the year's lowest and highest close and the
    moving averages)."""
    return [fact for fact in capture.get("tier1") or []
            if (fact.get("derived") or {}).get("operation") == tape.OPERATION
            and fact.get("unit") == unit]


def _price_triggers(verdict):
    return [trigger for trigger in
            ((verdict.get("tripwires") or {}).get("reopening_triggers") or [])
            if isinstance(trigger, dict) and trigger.get("kind") == "price"]


def _named_levels(market_structure_text):
    return {_figure(token) for token in _FIGURE.findall(
        _NOT_A_LEVEL.sub(" ", market_structure_text or ""))}


def price_level_named(verdict, capture, market_structure_text):
    """True where at least one reopening trigger of kind price names a level
    the market-structure answer writes (not a percentage or part of a date),
    or sits at or within the ruled tolerance of a turning point the tape
    carries in the trigger's own unit."""
    named = _named_levels(market_structure_text)
    tolerance = price_level_tolerance()
    for trigger in _price_triggers(verdict):
        level = _figure(trigger.get("level"))
        if level is None:
            continue
        if level in named:
            return True
        if any(_near(fact.get("value"), level, tolerance)
               for fact in _turning_points(capture, trigger.get("unit"))):
            return True
    return False


def _price_words(written, unit):
    """A price as a reader reads it: the currency sign before the level as
    written where the unit names a currency, else the level and its unit."""
    sign = _CURRENCY_SIGNS.get(str(unit or "").split("_")[0])
    return "%s%s" % (sign, written) if sign else "%s %s" % (written, unit)


def _turning_point_name(fact):
    label = tape.LABELS.get(fact.get("id"), str(fact.get("id")))
    label = label[:1].lower() + label[1:]
    return label if label.startswith("the ") else "the " + label


def _level_sentence(trigger, capture, tolerance):
    written = str(trigger.get("level") or "").strip()
    level = _figure(written)
    unit = trigger.get("unit")
    if level is None:
        return ("The chairman's price level %s is his own judgement: it is "
                "not written as a figure the price history can be compared "
                "with." % json.dumps(written, ensure_ascii=False))
    shown = _price_words(written, unit)
    points = [(abs(level - _figure(fact.get("value"))), fact)
              for fact in _turning_points(capture, unit)
              if _figure(fact.get("value"))]
    if not points:
        return ("The %s %s: the price history carries no turning point to "
                "compare it with." % (shown, PRICE_LEVEL_JUDGEMENT))
    _gap, nearest = min(points, key=lambda pair: pair[0])
    value = _figure(nearest.get("value"))
    places = decimal.Decimal(1).scaleb(min(level.as_tuple().exponent, 0))
    away = (abs(level - value) / value * 100).quantize(
        decimal.Decimal("0.1"), rounding=decimal.ROUND_HALF_UP)
    return ("The %s %s: the price history shows no earlier turning point "
            "within %s%% of it. The nearest is %s, %s, %s%% away."
            % (shown, PRICE_LEVEL_JUDGEMENT,
               format((tolerance * 100).normalize(), "f"),
               _turning_point_name(nearest),
               _price_words(str(value.quantize(
                   places, rounding=decimal.ROUND_HALF_UP)), unit),
               away))


def price_level_warning(verdict, capture, market_structure_text):
    """The warnings line where no price tripwire is supported, else None:
    one plain sentence per price level, naming the nearest turning point,
    or NO_PRICE_LEVEL_WARNING where the chairman named none."""
    if price_level_named(verdict, capture, market_structure_text):
        return None
    tolerance = price_level_tolerance()
    sentences = [_level_sentence(trigger, capture, tolerance)
                 for trigger in _price_triggers(verdict)]
    return " ".join(sentences) or NO_PRICE_LEVEL_WARNING
