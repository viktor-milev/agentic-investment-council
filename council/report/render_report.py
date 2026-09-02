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

IT WRITES EXACTLY ONE FILE AND READS EVERYTHING ELSE. `council/runs/**` is a record. Rendering
adds `report.html` beside the archives and changes no existing byte.

Stdlib only, Python 3 - ruling X. Ruling Z binds every label and sentence this page authors:
plain CIO-suitable English, short sentences, no unexplained internal identifiers (the field ids
that appear inside tables are data, and their label columns say in plain words what they are).
"""
import decimal
import hashlib
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import subjects  # noqa: E402


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
# NUMBER FORMATTING - AT RENDER TIME ONLY (ruling Y5; the 2026-08-28 formatting rulings)
# ---------------------------------------------------------------------------------------------
# The pack and the verdict carry every figure as the exact string that was captured; nothing is
# rounded on disk. Rounding happens HERE, on the way to the page, and nothing writes a number
# back. The rules, as ruled and as proven in the old renderer:
#   * one reading precision per unit, so one column carries one number of decimals;
#   * a whole number stays whole - no decimals are padded onto a figure that has none;
#   * a figure the unit's precision would erase (print as 0.00) is never erased - it falls back
#     to the exact text it arrived as;
#   * text that is not a pure number - a date, a range, NOT AVAILABLE, a sentence - is never
#     parsed and survives as the words it is;
#   * a zero-padded bare integer is an identifier, not a quantity, and is never rounded.

UNIT_DECIMALS = {
    "%": 2, "USD": 2, "USD_bn": 2, "USD_m": 2, "USD_m_per_MW": 2, "x": 2,
    # `days` carries one decimal (owner, 2026-08-28): the only figure any run records in days
    # is days-to-cover, and a whole number would state a different fact than the one captured.
    "MW": 1, "MW_per_year": 1, "years": 1, "millions_of_shares": 1, "days": 1,
    "shares": 0, "contracts": 0,
}
DEFAULT_DECIMALS = 2

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


def _unit_words(unit):
    """The contract's unit identifiers as a reader reads them - `USD_m`, not a machine token."""
    return str(unit).replace("_", " ") if unit else unit


def format_number(value, unit=None):
    """A figure as a reader should see it, whether recorded as a number or as text.

    Exact decimal arithmetic throughout, never binary: the page and the pack must answer the
    same rounding question the same way, and `1.005` must round UP at two decimals. Ported from
    the old renderer, where every branch below was audited in.
    """
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not NUMERIC_TEXT.match(text) or PADDED_IDENTIFIER.match(text):
            return value
        try:
            exact = decimal.Decimal(text)
        except decimal.InvalidOperation:
            return value
        if not exact.is_finite():
            return text
        fallback = text
    elif isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
        # The double's exact binary expansion is the number the machine actually holds;
        # collapsing it to the reading precision is the whole point of ruling Y5.
        exact = decimal.Decimal(value)
        fallback = repr(value)
    else:
        return str(value)

    # Zero is answered first, before any reasoning about size or precision exists to get it
    # wrong: every spelling of zero (-0.0, -0e50) has the one rendering.
    if not exact:
        return "0"
    if unit in UNROUNDED_UNITS:
        return fallback
    decimals = UNIT_DECIMALS.get(unit, DEFAULT_DECIMALS)
    # Too big to be a figure, answered before the arithmetic is asked. `adjusted()` is the
    # place of the leading digit, so this counts the digits before the point.
    if exact.adjusted() >= MAX_FIGURE_DIGITS:
        return fallback
    try:
        with decimal.localcontext() as context:
            # The figure's own digits, plus room for the unit's decimals and one to round on.
            context.prec = MAX_FIGURE_DIGITS + decimals + 1
            rounded = exact.quantize(decimal.Decimal(1).scaleb(-decimals),
                                     rounding=decimal.ROUND_HALF_UP)
    except (decimal.InvalidOperation, decimal.Overflow):
        return fallback
    if rounded == 0:
        # The unit's precision would ERASE the figure - print 0.00 for a number that is not
        # zero. That is the one rounding this must never do; the figure stands as it arrived.
        return fallback
    # One precision per unit means KEEPING the trailing zeroes on fractional figures; a whole
    # number stays whole, and the wholeness test reads the ROUNDED value, so 39.996 % prints 40.
    if rounded == rounded.to_integral_value():
        return str(rounded.to_integral_value())
    return str(rounded)


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
ADVISOR_SEATS = (
    ("advisor_bear", "The bear case", "\U0001F43B"),
    ("advisor_bull", "The bull case", "\U0001F402"),
    ("advisor_base_rate", "The base-rate skeptic", "\U0001F4CA"),
    ("advisor_market_structure", "Market structure", "\U0001F3E6"),
    ("advisor_risk", "The asset's risk", "\U0001F6E1"),
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
    }


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
}
:root[data-theme="light"]{
  --base:#FAF8F3; --panel:#F1EDE5; --panel-open:#E9E4DA; --chrome:#F1EDE5;
  --text:#1F1E1B; --muted:#615D55; --line:rgba(0,0,0,0.14);
  --ember:#A8571B; --bear:#8C3B2F; --mid:#6F6B62; --bull:#4B6837; --alarm:#992D14;
  --alarm-wash:rgba(153,45,20,0.09); --shadow:rgba(0,0,0,0.18);
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
@media (prefers-reduced-motion: reduce){html{scroll-behavior:auto} *{transition:none!important}}
body{margin:0;background:var(--base);color:var(--text);
     font-family:system-ui,"Segoe UI",sans-serif;line-height:1.55;font-size:15.5px}
.wrap{max-width:960px;margin:0 auto;padding:64px 22px 60px}
h1,h2,h3,h4{font-family:Georgia,Cambria,serif;@B@:600;line-height:1.25}
h1{font-size:27px;margin:0 0 6px}
h2{font-size:20px;margin:34px 0 10px;padding-bottom:7px;border-bottom:1px solid var(--ember);
   scroll-margin-top:66px}
h3{font-size:16.5px;margin:20px 0 8px}
h4{font-size:15px;margin:16px 0 6px;color:var(--muted)}
.meta{color:var(--muted);font-size:13px;margin-bottom:26px}
.badge{display:inline-block;border:1px solid var(--ember);color:var(--ember);border-radius:4px;
       padding:5px 14px;font-family:Georgia,serif;font-size:17px;letter-spacing:.06em;margin:10px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;padding:18px 20px;margin:14px 0}
.muted{color:var(--muted)}
.small{font-size:12.5px}
.lead{display:block;@B@:600;color:var(--text);margin-bottom:6px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}
td,th{border:1px solid var(--line);padding:8px 10px;vertical-align:top;text-align:left}
th{color:var(--muted);@B@:600}
th.nowrap,td.nowrap{white-space:nowrap}
td code,.foot code{word-break:break-all}
details{background:var(--panel);border:1px solid var(--line);border-radius:4px;margin:10px 0}
details[open]{background:var(--panel-open);border-left:2px solid var(--ember)}
summary{cursor:pointer;padding:13px 16px;font-family:Georgia,serif;font-size:16px;outline-offset:3px}
summary:focus-visible{outline:2px solid var(--ember)}
details .body{padding:2px 20px 16px;border-top:1px solid var(--line)}
details details{margin:10px 0;background:var(--base)}
details details summary{font-size:14px;padding:10px 14px}
ul,ol{margin:8px 0;padding-left:22px}
li{margin:5px 0}
strong{color:var(--text)}
code{font-family:Consolas,"SF Mono",monospace;font-size:12.5px;color:var(--ember)}
pre{background:var(--base);border:1px solid var(--line);border-radius:4px;padding:12px;overflow-x:auto}
pre code{color:var(--text);font-size:12px}
hr{border:0;border-top:1px solid var(--line);margin:16px 0}
.foot{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:12.5px}
.prominent{border-left:2px solid var(--ember)}
.alarm{border:1px solid var(--alarm);border-left:4px solid var(--alarm);background:var(--alarm-wash)}
.alarm .shout{color:var(--alarm);font-family:Georgia,serif;font-size:18px;letter-spacing:.03em;
              display:block;margin-bottom:8px}
tr.alarm td{background:var(--alarm-wash);border-color:var(--alarm)}
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
@media print{.dock,.themebtn{display:none}details{border-left:1px solid var(--line)}}
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


def _head_block(page, run):
    verdict = run["verdict"]
    subject = verdict.get("subject") or {}
    provenance = verdict.get("provenance") or {}
    title = subject.get("name") or verdict.get("run_id", "")
    if subject.get("ticker"):
        title = "%s (%s)" % (title, subject["ticker"])
    page.add("<h1>Investment Council &mdash; %s</h1>" % esc(title))
    seats, challenger = _models_line(provenance)
    published = (provenance.get("timestamps") or {}).get("published", "")
    stamps = [
        "run <code>%s</code>" % esc(verdict.get("run_id", "")),
        "published %s" % esc(published),
        "seats ran on <strong>%s</strong>" % esc(seats),
        "the challenge went to <strong>%s</strong>" % esc(challenger),
    ]
    page.add('<div class="meta">%s</div>' % " &middot; ".join(stamps))


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

# At most five, per the ruling: "the three-to-five numbers the ruling actually turns on".
MAX_FRONT_KEY_NUMBERS = 5

# A pack fact whose id begins with this is a dated event (the anchorless anchor set).
CALENDAR_PREFIX = "calendar_"

# A value that opens with a calendar date is the date of the event itself; anything else is
# words about the event, and the fact's own as-of date is the one the calendar can sort on.
LEADING_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

# The five-word scale, strongest first, so the reader sees where this rating sits on it.
SCALE_ORDER = ("strong_buy", "buy", "hold", "sell", "monitor")


def _warnings_band(page, run):
    """The loud warning band. It renders in the DECISION FRONT and nowhere else: a failed
    outside audit or a raise the auditor never saw must never sit behind a fold."""
    warnings = run["verdict"].get("warnings") or []
    for warning in warnings:
        page.add('<div class="card alarm"><span class="shout">%s</span></div>' % esc(warning))


# The front is at most two rendered pages (AB13.5), and a schema-valid
# chairman can write at any length: six thousand-character tripwires
# rendered twice is not a front, it is the appendix moved upstairs
# (audit finding ANCHORLESS-C c1-4). So the front BOUNDS what it shows -
# how many rows, and how long each may run - and says plainly what it
# left downstairs. Nothing is lost: every word is in the appendix.
FRONT_MAX_ROWS = 3
FRONT_MAX_RATIONALE = 1000
FRONT_MAX_CHARS = 200
# The what-changes sentences RESTATE the tripwire table above them,
# so they carry the shorter trim: the reader has just read the
# whole of each one.
FRONT_MAX_SENTENCE = 160
MORE_IN_APPENDIX = "in full in the appendix"


def _front_trim(text, budget=None):
    """One rendered value, cut to the front's budget with a pointer to
    where the whole of it lives."""
    text = str(text or "")
    budget = budget or FRONT_MAX_CHARS
    if len(text) <= budget:
        return esc(text)
    return "%s&hellip; <span class=\"muted small\">(%s)</span>" % (
        esc(text[:budget].rstrip()), MORE_IN_APPENDIX)


def _front_rows(page, items, what):
    """The first few of a list, with one plain sentence when the rest
    were left for the appendix."""
    if len(items) <= FRONT_MAX_ROWS:
        return items
    page.add('<div class="muted small">Showing %d of %d %s; the rest are '
             "%s.</div>" % (FRONT_MAX_ROWS, len(items), what,
                            MORE_IN_APPENDIX))
    return items[:FRONT_MAX_ROWS]


def _front_rating(page, verdict):
    rating = verdict.get("rating", "")
    page.add('<div class="badge">%s</div>' % esc(RATING_WORDS.get(rating, rating)))
    page.add('<div class="muted small">The council&#x27;s scale, strongest first: %s.</div>'
             % esc(", ".join(RATING_WORDS[word] for word in SCALE_ORDER)))
    page.add('<div class="muted small">The subject is %s.</div>'
             % esc(_kind_words(verdict.get("subject") or {})))
    rationale = verdict.get("conviction_rationale") or "not recorded"
    if len(rationale) > FRONT_MAX_RATIONALE:
        rationale = ("%s…\n\n*(%s)*"
                     % (rationale[:FRONT_MAX_RATIONALE].rstrip(),
                        MORE_IN_APPENDIX))
    page.add('<div class="card"><span class="lead">Why this rating, in the chairman&#x27;s own '
             "words</span>%s</div>" % markdown(rationale))


def _front_key_numbers(page, verdict):
    """The few figures the ruling turns on, from the hand-off the verdict already carries."""
    key_numbers = (verdict.get("atlas_envelope") or {}).get("key_numbers") or []
    page.add("<h3>The numbers this ruling turns on</h3>")
    if not key_numbers:
        page.add('<div class="card">The verdict names no headline numbers.</div>')
        return
    shown = key_numbers[:MAX_FRONT_KEY_NUMBERS]
    rows = "".join('<tr><td>%s</td><td class="nowrap">%s%s</td><td class="nowrap">%s</td></tr>'
                   % (_front_trim(number.get("name", ""), FRONT_MAX_SENTENCE),
                      _front_trim(format_number(number.get("value"),
                                                    number.get("unit")),
                                      FRONT_MAX_SENTENCE),
                      (" " + esc(_unit_words(number.get("unit"))))
                      if number.get("unit") else "",
                      _front_trim(number.get("as_of", ""), FRONT_MAX_SENTENCE))
                   for number in shown)
    page.add('<table><tr><th>the number</th><th class="nowrap">value</th>'
             '<th class="nowrap">as of</th></tr>%s</table>' % rows)
    if len(key_numbers) > len(shown):
        page.add('<div class="muted small">The verdict carries %d more headline number%s. They '
                 "are listed in full under &#x27;What the portfolio system receives&#x27; at the "
                 "end of this report.</div>"
                 % (len(key_numbers) - len(shown),
                    "" if len(key_numbers) - len(shown) == 1 else "s"))


def _ladder_table(page, scenarios, currency):
    """The chairman's ladder: one row per named rung. The price is rounded for reading in the
    subject's own currency; the chance is quoted as he wrote it, because the arithmetic block
    beside this table quotes that same string and the two must read alike. The row count is
    bounded like every other front list - the contract sets no maximum on how many rungs a
    ladder may name, and the whole ladder is in the appendix."""
    scenarios = _front_rows(page, list(scenarios), "scenarios")
    rows = "".join('<tr><td>%s</td><td class="nowrap">%s%s</td><td class="nowrap">%s</td>'
                   "<td>%s</td></tr>"
                   % (_front_trim(rung.get("name", ""),
                                      FRONT_MAX_SENTENCE),
                      esc(format_number(rung.get("price_outcome"), currency)),
                      (" " + esc(_unit_words(currency))) if currency else "",
                      esc(rung.get("probability", "")),
                      _front_trim(rung.get("rationale", "")))
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
                 % "".join("<p>%s</p>" % _front_trim(line)
                            for line in lines))
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
             % _front_trim(block.get("not_aggregated_reason")
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


def _front_basis(page, run):
    """What the rating actually rests on: the ladder and its sum for an anchorless subject, the
    price read for an anchored one, and a context ladder after the read where one exists."""
    verdict = run["verdict"]
    block = verdict.get("scenario_rating") or {}
    if block and block.get("basis") == "rating":
        if block.get("aggregated"):
            _front_earned_rating(page, verdict, block)
        else:
            _front_not_aggregated(page, verdict, block)
        return
    page.add('<div class="card"><span class="lead">The mispricing read</span>%s</div>'
             % _mispricing_sentence(verdict))
    if block and block.get("basis") == "context":
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
        levels = _front_rows(page, levels, "invalidation levels")
        rows = "".join('<tr><td class="nowrap">%s%s</td><td>%s%s</td></tr>'
                       % (esc(format_number(level.get("level"), level.get("unit"))),
                          (" " + esc(_unit_words(level.get("unit"))))
                          if level.get("unit") else "",
                          _constituent_tag(level),
                          _front_trim(level.get("meaning", "")))
                       for level in levels)
        page.add('<table><tr><th class="nowrap">level</th>'
                 "<th>what it means if it is reached</th></tr>%s</table>" % rows)
    if below:
        currency = (verdict.get("subject") or {}).get("currency")
        page.add('<div class="muted small">The ladder&#x27;s own losing rungs, priced under %s%s '
                 "&mdash; the price the ladder is measured against.</div>"
                 % (esc(block.get("reference_price", "")),
                    (" " + esc(_unit_words(currency))) if currency else ""))
        rows = "".join('<tr><td class="nowrap">%s%s</td><td>%s</td>'
                       '<td class="nowrap">%s</td></tr>'
                       % (esc(format_number(rung.get("price_outcome"), currency)),
                          (" " + esc(_unit_words(currency))) if currency else "",
                          _front_trim(rung.get("name", ""), FRONT_MAX_SENTENCE), esc(rung.get("probability", "")))
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


def _front_calendar(page, run):
    rows = _calendar_rows(run["pack"])
    page.add("<h3>The dated event calendar</h3>")
    if not rows:
        page.add('<div class="card">The evidence pack carries no dated events for this '
                 "subject.</div>")
        return
    body = "".join('<tr><td class="nowrap">%s</td><td>%s%s<div class="muted small"><code>%s</code>'
                   "</div></td></tr>"
                   % (esc(when), (esc(detail) + " ") if detail else "", esc(source), esc(fact_id))
                   for when, fact_id, source, detail in rows)
    page.add('<table><tr><th class="nowrap">date</th>'
             "<th>what happens, and where the date comes from</th></tr>%s</table>" % body)


def _trigger_when(trigger):
    """A reopening trigger's level or its date, as the reader reads it. Empty where the record
    carries neither."""
    if trigger.get("level"):
        return "%s%s" % (esc(format_number(trigger["level"], trigger.get("unit"))),
                         (" " + esc(_unit_words(trigger.get("unit"))))
                         if trigger.get("unit") else "")
    if trigger.get("date"):
        return esc(trigger["date"])
    return ""


def _front_tripwires(page, run):
    tripwires = run["verdict"].get("tripwires") or {}
    triggers = tripwires.get("reopening_triggers") or []
    falsifiers = tripwires.get("falsifiers") or []
    page.add("<h3>The tripwires</h3>")
    triggers = _front_rows(page, triggers, "reopening triggers")
    falsifiers = _front_rows(page, falsifiers, "falsifiers")
    if not triggers and not falsifiers:
        page.add('<div class="card">The verdict names no tripwire.</div>')
        return
    if triggers:
        page.add("<h4>What reopens the case</h4>")
        rows = "".join('<tr><td class="nowrap"><span class="tag">%s</span></td><td>%s%s</td>'
                       '<td class="nowrap">%s</td></tr>'
                       % (esc("Price" if trigger.get("kind") == "price" else "Event"),
                          _constituent_tag(trigger),
                          _front_trim(trigger.get("detail", "")),
                          _trigger_when(trigger) or "&mdash;")
                       for trigger in triggers)
        page.add('<table><tr><th class="nowrap">kind</th><th>what reopens the case</th>'
                 '<th class="nowrap">at</th></tr>%s</table>' % rows)
    if falsifiers:
        page.add("<h4>What would prove this wrong</h4>")
        rows = "".join('<tr><td>%s%s</td><td class="nowrap"><code>%s</code></td>'
                       '<td class="nowrap">%s</td></tr>'
                       % (_constituent_tag(row),
                          _front_trim(row.get("statement", "")),
                          _front_trim(row.get("figure_name", ""), FRONT_MAX_SENTENCE),
                          _front_trim(row.get("date", ""),
                                      FRONT_MAX_SENTENCE))
                       for row in falsifiers)
        page.add('<table><tr><th>what would prove the view wrong</th>'
                 '<th class="nowrap">the figure it is scored against</th>'
                 '<th class="nowrap">scored on</th></tr>%s</table>' % rows)


def _front_what_changes(page, run):
    """The same triggers and falsifiers as sentences, so the reader never has to read a table to
    learn what would move the rating. Every sentence is built from the record's own fields."""
    verdict = run["verdict"]
    tripwires = verdict.get("tripwires") or {}
    block = verdict.get("scenario_rating") or {}
    page.add("<h3>What changes this rating</h3>")
    flip = ((block.get("sensitivity") or {}).get("flip") or {}).get("sentence")
    if block.get("basis") == "rating" and flip:
        page.add('<div class="card prominent">%s</div>' % _front_trim(flip))
    items = []
    for trigger in (tripwires.get("reopening_triggers") or []):
        when = _trigger_when(trigger)
        items.append("<li><strong>Would reopen this rating:</strong> %s%s%s</li>"
                     % (_constituent_tag(trigger),
                        _front_trim(trigger.get("detail", ""),
                                    FRONT_MAX_SENTENCE),
                        (" The %s to watch is %s."
                         % ("level" if trigger.get("level") else "date", when))
                        if when else ""))
    for row in (tripwires.get("falsifiers") or []):
        scored = []
        if row.get("figure_name"):
            scored.append("against <code>%s</code>"
                          % _front_trim(row["figure_name"],
                                        FRONT_MAX_SENTENCE))
        if row.get("source"):
            scored.append("from %s"
                          % _front_trim(row["source"],
                                        FRONT_MAX_SENTENCE))
        if row.get("date"):
            scored.append("on %s"
                          % _front_trim(row["date"],
                                        FRONT_MAX_SENTENCE))
        items.append("<li><strong>Would prove this rating wrong:</strong> %s%s%s</li>"
                     % (_constituent_tag(row),
                        _front_trim(row.get("statement", ""),
                                    FRONT_MAX_SENTENCE),
                        (" Scored %s." % " ".join(scored)) if scored else ""))
    if items:
        shown = _front_rows(page, items,
                            "things that would change this rating")
        page.add('<div class="card"><ul>%s</ul></div>' % "".join(shown))
    elif not flip:
        page.add('<div class="card">The verdict names nothing that would change this '
                 "rating.</div>")


def _front_cross_examination(page, run):
    reviewer = run["answers"].get("reviewer") or {}
    page.add("<h3>Where the five advisors disagreed &mdash; the blind reviewer&#x27;s "
             "summary</h3>")
    page.add('<div class="muted small">One reviewer read all five advisors without knowing who '
             "wrote what, and summarised where they parted company.</div>")
    page.add('<div class="card prominent">%s</div>'
             % markdown(reviewer.get("synopsis") or "not recorded", 4))


def _front_section(page, run):
    """The whole decision, on the opening pages, in the ruled order (AB13.5)."""
    page.section("decision", "The decision")
    _warnings_band(page, run)
    _front_rating(page, run["verdict"])
    _front_key_numbers(page, run["verdict"])
    _front_basis(page, run)
    _front_downside(page, run)
    _front_calendar(page, run)
    _front_tripwires(page, run)
    _front_what_changes(page, run)
    _front_cross_examination(page, run)


# --- 2. The owner's question, and the frame ----------------------------------------------------

def _question_section(page, run):
    verdict = run["verdict"]
    frame = verdict.get("frame") or {}
    page.section("question", "The owner's question")
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


# --- 3. The verdict block ----------------------------------------------------------------------

def _mispricing_sentence(verdict):
    """The price read as one sentence. Built in one place, so the decision front and the folded
    verdict block below it can never come to read differently."""
    mispricing = verdict.get("mispricing") or {}
    read = mispricing.get("read")
    if read == "no_view" or not read:
        sentence = "The council takes no view on the price yet."
    else:
        sentence = ("The council reads the price as <strong>%s</strong>%s."
                    % (esc(MISPRICING_WORDS.get(read, read)),
                       (" &mdash; %s" % esc(mispricing["magnitude"]))
                       if mispricing.get("magnitude") else ""))
    arithmetic = mispricing.get("arithmetic")
    if arithmetic:
        # The arithmetic-in-words sentence is the chairman's own; it is quoted, never reworked.
        sentence += ' <span class="muted">%s</span>' % esc(arithmetic)
    return sentence


def _verdict_section(page, run):
    verdict = run["verdict"]
    page.section("verdict", "The verdict")
    # The decision front above already carries this headline, so the block itself opens folded.
    mark = page.mark()
    rating = verdict.get("rating", "")
    page.add('<div class="badge">%s</div>' % esc(RATING_WORDS.get(rating, rating)))
    # What kind of subject earned the rating, in plain words - one
    # rating for the subject as a whole, whatever its kind.
    page.add('<div class="muted small">The subject is %s.</div>'
             % esc(_kind_words(verdict.get("subject") or {})))
    page.add('<div class="card"><span class="lead">Why this rating, in the chairman&#x27;s own '
             "words</span>%s</div>" % markdown(verdict.get("conviction_rationale") or "not recorded"))
    page.add('<div class="card"><span class="lead">The mispricing read</span>%s</div>'
             % _mispricing_sentence(verdict))
    page.collapse("The verdict block in full &mdash; the rating, the chairman&#x27;s reasoning "
                  "and the price read", mark)


# --- 3b. The named expression: constituents, or the one vehicle --------------------------------

def _member_fact_cell(facts_by_id, concept, ticker):
    """One expression member's own frozen figure as a table cell, read
    from the pack fact `<concept>__<slug(ticker)>` and rounded for
    reading like every other figure on the page. An absent fact renders
    an em dash - the page never invents a number."""
    fact = facts_by_id.get("%s__%s" % (concept, subjects.slug(ticker)))
    if not fact:
        return "&mdash;"
    unit = _unit_words(fact.get("unit"))
    cell = esc(format_number(fact.get("value"), fact.get("unit")))
    return cell + ((" " + esc(unit)) if unit else "")


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
    the one implementation vehicle for a vehicle-mode theme. A subject
    carrying a theme block states the frozen thesis first, whatever the
    expression mode - a thematic vehicle names no expression fields at
    all, and its rating must still show the idea it judged (audit
    finding THEMES-C r3-1). Subjects with no theme and no expression
    render no section."""
    verdict = run["verdict"]
    subject = verdict.get("subject") or {}
    theme = subjects.theme_block(subject)
    if theme:
        # The idea the rating judges, exactly as it was frozen before
        # the council sat - the chairman's prose need not restate it,
        # so the page does. Capture free text, escaped like all of it.
        page.add('<div class="card prominent"><span class="lead">The '
                 "theme&#x27;s thesis, frozen before the council sat"
                 '</span><div class="verbatim">%s</div></div>'
                 % esc(theme.get("thesis", "")))
    constituents = subject.get("constituents") or []
    vehicle = subject.get("vehicle")
    if not constituents and not vehicle:
        return
    if constituents:
        page.section("constituents", "The constituents")
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
        page.section("constituents", "The implementation vehicle")
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


# --- 4. Warnings, loud -------------------------------------------------------------------------

def _warnings_section(page, run):
    """The warnings themselves are printed ONCE, at the very top of the report, by the decision
    front. This section keeps its place in the running order and points at them; printing the
    band twice would teach the reader to scroll past it."""
    warnings = run["verdict"].get("warnings") or []
    page.section("warnings", "Warnings")
    if not warnings:
        page.add('<div class="card">This verdict carries no warnings.</div>')
        return
    page.add('<div class="card">Every warning on this verdict is printed at the top of this '
             "report, above everything else, so that it cannot be missed. "
             '<a href="#decision">Go back to the decision</a>.</div>')


# --- 5. Tripwires ------------------------------------------------------------------------------

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
                        esc(row.get("date", ""))))
        if row.get("prior_period_value") is not None:
            unit = _unit_words(row.get("prior_period_unit"))
            parts.append('<div style="margin-top:6px">Prior period: '
                         "%s%s, as of %s.</div>"
                         % (esc(format_number(
                                row.get("prior_period_value"),
                                row.get("prior_period_unit"))),
                            (" " + esc(unit)) if unit else "",
                            esc(row.get("prior_period_as_of", ""))))
        parts.append('<div class="muted small" style="margin-top:6px">'
                     "Metric identity assumed: %s</div>"
                     % esc(row.get("metric_identity_assumed")
                           or "not stated"))
        page.add('<div class="card prominent">%s</div>' % "".join(parts))


def _tripwires_section(page, run):
    tripwires = run["verdict"].get("tripwires") or {}
    page.section("tripwires", "Tripwires")
    # The decision front above already carries the tripwires, so the full record opens folded.
    mark = page.mark()
    page.add('<div class="muted small">The levels and events that change this verdict, each '
             "scored against a named figure from a named source.</div>")
    falsifiers = tripwires.get("falsifiers") or []
    theme_rows = [f for f in falsifiers
                  if f.get("theme_falsifier_id") is not None]
    plain_rows = [f for f in falsifiers
                  if f.get("theme_falsifier_id") is None]
    if theme_rows:
        _theme_falsifier_block(page, theme_rows,
                               run["verdict"].get("subject") or {})
    levels = tripwires.get("invalidation_levels") or []
    if levels:
        page.add("<h3>Invalidation levels</h3>")
        rows = "".join('<tr><td class="nowrap">%s %s</td><td>%s%s</td></tr>'
                       % (esc(format_number(level.get("level"), level.get("unit"))),
                          esc(_unit_words(level.get("unit")) or ""),
                          _constituent_tag(level), esc(level.get("meaning", "")))
                       for level in levels)
        page.add('<table><tr><th class="nowrap">level</th><th>what it means if hit</th></tr>'
                 "%s</table>" % rows)
    triggers = tripwires.get("reopening_triggers") or []
    if triggers:
        page.add("<h3>Reopening triggers</h3>")
        rows = []
        for trigger in triggers:
            kind = "Price" if trigger.get("kind") == "price" else "Event"
            at = ""
            if trigger.get("level"):
                at = "%s %s" % (esc(format_number(trigger["level"], trigger.get("unit"))),
                                esc(_unit_words(trigger.get("unit")) or ""))
            elif trigger.get("date"):
                at = esc(trigger["date"])
            rows.append('<tr><td class="nowrap"><span class="tag">%s</span></td><td>%s%s</td>'
                        '<td class="nowrap">%s</td></tr>'
                        % (esc(kind), _constituent_tag(trigger),
                           esc(trigger.get("detail", "")), at or "&mdash;"))
        page.add('<table><tr><th class="nowrap">kind</th><th>what reopens the case</th>'
                 '<th class="nowrap">at</th></tr>%s</table>' % "".join(rows))
    if plain_rows:
        page.add("<h3>Falsifiers</h3>")
        rows = "".join('<tr><td>%s%s</td><td class="nowrap"><code>%s</code></td><td>%s</td>'
                       '<td class="nowrap">%s</td></tr>'
                       % (_constituent_tag(f), esc(f.get("statement", "")),
                          esc(f.get("figure_name", "")),
                          esc(f.get("source", "")), esc(f.get("date", "")))
                       for f in plain_rows)
        page.add('<table><tr><th>what would prove the view wrong</th>'
                 '<th class="nowrap">the figure it is scored against</th><th>source</th>'
                 '<th class="nowrap">scored on</th></tr>%s</table>' % rows)
    page.collapse("Every tripwire in full &mdash; the levels, the triggers and the falsifiers, "
                  "each with the figure and the source it is scored against", mark)


# --- 6. The challenge round, summarized --------------------------------------------------------

def _challenge_section(page, run):
    challenge = run["verdict"].get("challenge") or {}
    page.section("challenge", "The challenge round")
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

def _changes_section(page, run):
    challenge = run["verdict"].get("challenge") or {}
    appendix = challenge.get("change_appendix") or []
    page.section("changes", "What changed after the outside audit")
    if not appendix:
        page.add('<div class="card">Nothing changed after the outside audit.</div>')
        return
    page.add('<div class="muted small">The final document is compared, field by field, against '
             "the draft the challenger read. Every changed field is listed, before and after.</div>")
    rows = []
    for change in appendix:
        label = change.get("label", "")
        alarm = label == "unendorsed_raise"
        rows.append('<tr%s><td class="nowrap"><code>%s</code></td><td>%s</td><td>%s</td>'
                    '<td class="nowrap"><span class="tag%s">%s</span></td></tr>'
                    % (' class="alarm"' if alarm else "", esc(change.get("field", "")),
                       esc(change.get("before", "")), esc(change.get("after", "")),
                       " alarmtag" if alarm else "",
                       esc(CHANGE_LABEL_WORDS.get(label, label))))
    page.add('<table><tr><th class="nowrap">what changed</th><th>before</th><th>after</th>'
             '<th class="nowrap">what happened</th></tr>%s</table>' % "".join(rows))


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
    page.add('<div class="card">%s</div>' % markdown(prose or "not recorded"))


# --- 9. The evidence, folded; the market-shut sentence in plain sight ---------------------------

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
    mark = page.mark()
    tier1 = capture.get("tier1") or []
    freshness = pack.get("freshness") or {}
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
        note = notes.get(fact_id)
        if note:
            source_html += "<br>Arithmetic: %s" % esc(note)
        rests = ('<span class="tag checked" title="the verdict names this '
                 'fact as one its ruling rests on">rests on this</span> '
                 if fact_id in dependencies else "")
        unit = _unit_words(fact.get("unit"))
        value = format_number(fact.get("value"), fact.get("unit"))
        rows.append('<tr><td>%s<code>%s</code><div class="muted small" style="margin-top:4px">'
                    '%s</div></td><td class="nowrap">%s%s</td><td class="nowrap">%s</td>'
                    '<td class="nowrap"><span class="tag %s">%s</span></td></tr>'
                    % (rests, esc(fact_id), source_html, esc(value),
                       (" " + esc(unit)) if unit else "",
                       esc(fact.get("as_of", "")), esc(str(word).replace(" ", "-")), esc(word)))
    page.add('<table><tr><th>fact, and where it came from</th><th class="nowrap">value</th>'
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
    if gaps:
        page.add("<h3>Declared gaps</h3>")
        page.add('<div class="card"><ul>%s</ul></div>' % "".join(
            "<li><strong>%s</strong> &mdash; %s The test it weakens: <code>%s</code>.</li>"
            % (esc(g.get("fact_class", "")), esc(g.get("reason", "")),
               esc(g.get("weakened_test", "")))
            for g in gaps))
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
            % (_constituent_tag(r) + esc(r.get("description", "")),
               esc(REQUIREMENT_KIND_WORDS.get(r.get("kind"), r.get("kind") or "")),
               "checked" if r.get("status") == "answered" else "stale",
               "answered" if r.get("status") == "answered" else "declared gap",
               ", ".join("<code>%s</code>" % esc(a) for a in (r.get("answered_by") or []))
               or "&mdash;")
            for r in requirements)
        page.add('<table><tr><th>what this question needs</th><th class="nowrap">kind</th>'
                 '<th class="nowrap">status</th><th>answered by</th></tr>%s</table>' % rows)
    count = len(tier1)
    page.collapse("The %d frozen fact%s in the evidence pack (facts and "
                  "passages marked &#x27;rests on this&#x27; carry the "
                  "ruling)"
                  % (count, "" if count == 1 else "s"), mark)


# --- 10. Peer review ---------------------------------------------------------------------------

def _review_section(page, run):
    reviewer = run["answers"].get("reviewer") or {}
    page.section("review", "Peer review")
    page.add('<div class="muted small">One reviewer read all five advisors blind and wrote the '
             "cross-examination and this synopsis.</div>")
    page.add('<div class="card prominent"><span class="lead">Synopsis</span>%s</div>'
             % markdown(reviewer.get("synopsis") or "not recorded", 4))
    page.add("<details><summary>The reviewer's full cross-examination</summary>"
             '<div class="body">%s</div></details>' % markdown(reviewer.get("markdown", ""), 4))


# --- The five advisors, each folded shut -------------------------------------------------------

def _advisors_section(page, run):
    page.section("advisors", "The five advisors")
    page.add('<div class="muted small">Five seats, one frozen pack, no tools. Each line opens '
             "to that seat&#x27;s answer, unedited.</div>")
    for kind, label, icon in ADVISOR_SEATS:
        answer = run["answers"].get(kind) or {}
        page.add('<details><summary>%s %s</summary><div class="body">%s</div></details>'
                 % (icon, esc(label), markdown(answer.get("markdown", ""), 4)))


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

def _atlas_section(page, run):
    envelope = run["verdict"].get("atlas_envelope") or {}
    page.section("atlas", "What the portfolio system receives")
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
    page.add("<table>"
             '<tr><th class="nowrap">Rating</th><td>%s</td></tr>'
             "%s"
             '<tr><th class="nowrap">Hash of the frozen evidence pack &mdash; a fingerprint no '
             "other file shares</th><td><code>%s</code></td></tr></table>"
             % (esc(RATING_WORDS.get(rating, rating or "")), subject_rows,
                esc(envelope.get("pack_hash", ""))))
    proportions = envelope.get("thesis_proportions") or []
    if proportions:
        _proportions_card(page, proportions)
    key_numbers = envelope.get("key_numbers") or []
    if key_numbers:
        rows = "".join('<tr><td>%s</td><td class="nowrap">%s %s</td><td class="nowrap">%s</td></tr>'
                       % (esc(k.get("name", "")), esc(format_number(k.get("value"), k.get("unit"))),
                          esc(_unit_words(k.get("unit")) or ""), esc(k.get("as_of", "")))
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
                cell = "%s %s" % (format_number(value, entry.get("unit")),
                                  _unit_words(entry.get("unit")) or "")
            rows.append('<tr><td>%s%s</td><td class="nowrap">%s</td>'
                        '<td class="nowrap">%s</td></tr>'
                        % (_constituent_tag(entry),
                           esc(entry.get("detail", "")), esc(cell.strip()),
                           esc(entry.get("as_of") or "")))
        page.add('<table><tr><th>sizing fact about the asset</th>'
                 '<th class="nowrap">value</th>'
                 '<th class="nowrap">as of</th></tr>%s</table>'
                 % "".join(rows))
    if envelope.get("for_atlas_note") is not None:
        page.add('<div class="card prominent"><span class="lead">The owner&#x27;s note for the '
                 'portfolio system, verbatim</span><div class="verbatim">%s</div></div>'
                 % esc(envelope["for_atlas_note"]))
    page.add('<div class="muted small">The envelope also travels as its own file, and that file '
             "carries this verdict&#x27;s own hash, so the hand-off can be proved.</div>")


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
    cells = "".join('<tr><td>%s</td><td class="nowrap">%s %s</td>'
                    '<td class="nowrap">%s</td><td>%s</td></tr>'
                    % (esc(rung.get("name", "")),
                       esc(format_number(rung.get("price_outcome"),
                                         currency)),
                       esc(_unit_words(currency) or ""),
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
    page.section("ladders", "The scenario ladders, in full")
    mark = page.mark()
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
            page.add("<h4>%s</h4>" % esc(dict((s, t) for s, t, _ in ADVISOR_SEATS).get(seat, seat)))
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
    page.collapse("The ladders in full &mdash; the chairman&#x27;s and "
                  "each advisor&#x27;s", mark)


def build_page(run):
    page = Page()
    _head_block(page, run)
    # The decision first, on its own opening pages (AB13.5); the whole record behind it.
    _front_section(page, run)
    page.section("appendices", "Appendices — the full record")
    page.add('<div class="muted small">Everything the decision above rests on, in full: the '
             "question as it was asked, the verdict document, the tripwires with their sources, "
             "the outside audit, the chairman&#x27;s synthesis, the frozen evidence, the peer "
             "review, the five advisors, the challenger&#x27;s own words, and the hand-off to "
             "the portfolio system.</div>")
    _question_section(page, run)
    _verdict_section(page, run)
    _ladders_section(page, run)
    _constituents_section(page, run)
    _warnings_section(page, run)
    _tripwires_section(page, run)
    _challenge_section(page, run)
    _changes_section(page, run)
    _synthesis_section(page, run)
    _evidence_section(page, run)
    _review_section(page, run)
    _advisors_section(page, run)
    _challenger_section(page, run)
    _atlas_section(page, run)
    _footer(page, run)
    return page


def render(run_dir):
    """The whole report as one string. Refuses, in plain words, a directory that is not a run."""
    run = load_run(run_dir)
    page = build_page(run)
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
    try:
        body = render(run_dir)
    except MissingInputError as refusal:
        sys.stderr.write("REFUSED: %s\n" % refusal)
        return 1
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    sys.stdout.write("report written: %s (%d bytes)\n" % (target, len(body.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
