"""The scorecard: one page showing the council's track record (U7.4).

    python -m council.ledger.report [--ledger PATH] [--scored PATH] [-o OUT]

Bare, it reads the ledger at its default location and the scored file
beside it (scored.json), and writes scorecard.html there. With no scored
file it renders the record with every outcome pending. The page shows the
table of verdicts with their outcomes, the hit rate by rating word, the
mean excess by horizon, and the falsifiers for and against; and ONLY when
at least twenty rows carry a 252-day outcome does it show tokens per
sitting against excess return, with the sentence that n is small and this
is a record, not a proof. Below twenty it prints the count and refuses the
correlation (owner ruling AC7).

One self-contained file, no network, dark by default with a light toggle -
the Slate & Ember language of the council's report (owner ruling Y).
"""

import datetime
import html
import math
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical  # noqa: E402
from council.ledger import ledger, score  # noqa: E402

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Slate & Ember tokens (owner ruling Y; the report renderer's palette).
# Dark by default; the light values apply only under data-theme="light".
CSS = """
:root{
  --base:#161616; --panel:#202020; --panel-open:#262625; --chrome:#1D1D1C;
  --text:#E8E6E0; --muted:#94918A; --line:rgba(255,255,255,0.09);
  --ember:#DD8B5A; --bear:#A85C50; --mid:#5F5C55; --bull:#7F9468;
  --alarm:#D2603F; --shadow:rgba(0,0,0,0.5);
}
:root[data-theme="light"]{
  --base:#FAF8F3; --panel:#F1EDE5; --panel-open:#E9E4DA; --chrome:#F1EDE5;
  --text:#1F1E1B; --muted:#615D55; --line:rgba(0,0,0,0.14);
  --ember:#A8571B; --bear:#8C3B2F; --mid:#6F6B62; --bull:#4B6837;
  --alarm:#992D14; --shadow:rgba(0,0,0,0.18);
}
*{box-sizing:border-box}
body{margin:0;background:var(--base);color:var(--text);
     font-family:system-ui,"Segoe UI",sans-serif;line-height:1.55;
     font-size:15.5px}
.wrap{max-width:1000px;margin:0 auto;padding:40px 22px 60px}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}
h1,h2,h3{font-family:Georgia,Cambria,serif;line-height:1.25}
h1{font-size:26px;margin:0 0 4px}
h2{font-size:19px;margin:34px 0 10px;padding-bottom:7px;
   border-bottom:1px solid var(--ember)}
.meta{color:var(--muted);font-size:13px;margin-bottom:8px}
.themebtn{background:var(--chrome);color:var(--ember);
  border:1px solid var(--line);border-radius:5px;cursor:pointer;
  padding:7px 12px;font-size:13px}
.cards{display:flex;flex-wrap:wrap;gap:12px;margin:16px 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:4px;
  padding:14px 18px;min-width:150px}
.card .n{font-family:Georgia,serif;font-size:24px;color:var(--ember)}
.card .l{color:var(--muted);font-size:12.5px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:10px 0}
td,th{border:1px solid var(--line);padding:8px 10px;vertical-align:top;
  text-align:left}
th{color:var(--muted)}
td.num,th.num{text-align:right;white-space:nowrap;
  font-variant-numeric:tabular-nums}
.right{color:var(--bull)}
.wrong{color:var(--bear)}
.pending{color:var(--muted)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:3px;
  padding:1px 7px;font-size:11.5px;letter-spacing:.04em}
.refuse{background:var(--panel);border:1px solid var(--ember);
  border-left:3px solid var(--ember);border-radius:4px;padding:14px 18px;
  margin:14px 0}
.caveat{color:var(--muted);font-style:italic;margin:8px 0}
.foot{margin-top:44px;padding-top:14px;border-top:1px solid var(--line);
  color:var(--muted);font-size:12.5px}
"""

_THEME_SCRIPT = (
    "<script>(function(){var b=document.getElementById('theme');"
    "if(!b)return;b.addEventListener('click',function(){"
    "var r=document.documentElement;"
    "r.setAttribute('data-theme',r.getAttribute('data-theme')==='light'"
    "?'dark':'light');});})();</script>")


def esc(text):
    return html.escape("" if text is None else str(text))


def fmt_pct(value):
    if value is None:
        return "—"
    return "%+.1f%%" % float(value)


def fmt_pct_plain(value):
    if value is None:
        return "—"
    return "%.1f%%" % float(value)


def fmt_int(value):
    if value is None:
        return "—"
    return "{:,}".format(int(value))


def fmt_date(iso):
    if not iso:
        return "—"
    try:
        parts = iso.split("-")
        return "%d %s %s" % (int(parts[2]), _MONTHS[int(parts[1]) - 1],
                             parts[0])
    except (ValueError, IndexError):
        return iso


def _rating_words(rating):
    return "" if rating is None else str(rating).replace("_", " ")


def sitting_tokens(ledger_row):
    """Total Anthropic tokens a sitting spent: capture, the evidence
    challenge, every seat, and the verdict challenge - the figures the row
    carries, skipping the ones an older sitting never recorded."""
    if not ledger_row:
        return None
    stage = ledger_row.get("tokens_by_stage") or {}
    total = 0
    seen = False
    for key in ("capture", "evidence_challenge", "verdict_challenge"):
        value = stage.get(key)
        if isinstance(value, int):
            total += value
            seen = True
    for value in (stage.get("seats") or {}).values():
        if isinstance(value, int):
            total += value
            seen = True
    return total if seen else None


def _outcome_cell(outcome):
    correct = outcome.get("correct")
    if not outcome.get("has_252_outcome") and correct is None:
        return '<span class="pending">pending</span>'
    if correct is True:
        return '<span class="right">right</span>'
    if correct is False:
        return '<span class="wrong">wrong</span>'
    return '<span class="pending">not scored</span>'


def _excess_252(scored_row):
    for horizon in scored_row.get("horizons", []):
        if horizon.get("trading_days") == \
                scored_row_scoring_horizon(scored_row):
            return horizon.get("excess_pct")
    return None


def scored_row_scoring_horizon(scored_row):
    return scored_row.get("rating_outcome", {}).get(
        "scored_horizon_trading_days", 252)


def _pearson(pairs):
    n = len(pairs)
    if n < 2:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


# ---- page sections -------------------------------------------------------

def _verdict_table(scored, ledger_by_id):
    head = ("<tr><th>Subject</th><th>Date</th><th>Rating</th>"
            "<th>Read</th><th class='num'>Price</th>"
            "<th class='num'>252-day excess</th><th>Outcome</th>"
            "<th>Falsifiers f/a/u</th></tr>")
    body = []
    for row in scored:
        subject = row.get("subject") or {}
        name = subject.get("name")
        ticker = subject.get("ticker")
        label = esc(name) + (" (%s)" % esc(ticker) if ticker else "")
        ledger_row = ledger_by_id.get(row.get("ledger_row_id")) or {}
        price = (ledger_row.get("price_at_verdict") or {}).get("value")
        excess = _excess_252(row)
        fals = row.get("falsifiers") or {}
        body.append(
            "<tr><td>%s</td><td class='num'>%s</td><td>%s</td><td>%s</td>"
            "<td class='num'>%s</td><td class='num'>%s</td><td>%s</td>"
            "<td class='num'>%d / %d / %d</td></tr>" % (
                label, esc(fmt_date(row.get("verdict_date"))),
                esc(_rating_words(row.get("rating"))),
                esc((row.get("mispricing") or {}).get("read")),
                esc(price) if price else "—",
                fmt_pct(excess), _outcome_cell(row.get("rating_outcome", {})),
                fals.get("for", 0), fals.get("against", 0),
                fals.get("unresolved", 0)))
    return "<table>%s%s</table>" % (head, "".join(body))


def _hit_rate_table(scored):
    words = ["strong_buy", "buy", "hold", "sell", "monitor"]
    rows = []
    for word in words:
        scored_word = [r for r in scored
                       if r.get("rating") == word
                       and r["rating_outcome"]["has_252_outcome"]]
        right = [r for r in scored_word
                 if r["rating_outcome"]["correct"] is True]
        rate = ("%.1f%%" % (100.0 * len(right) / len(scored_word))
                if scored_word else "—")
        rows.append("<tr><td>%s</td><td class='num'>%d</td>"
                    "<td class='num'>%d</td><td class='num'>%s</td></tr>" % (
                        esc(_rating_words(word)), len(scored_word),
                        len(right), rate))
    head = ("<tr><th>Rating</th><th class='num'>Scored</th>"
            "<th class='num'>Right</th><th class='num'>Hit rate</th></tr>")
    return "<table>%s%s</table>" % (head, "".join(rows))


def _mean_excess_table(scored, rules):
    rows = []
    for days in rules["horizons_trading_days"]:
        values = []
        for row in scored:
            for horizon in row.get("horizons", []):
                if horizon.get("trading_days") == days and \
                        horizon.get("excess_pct") is not None:
                    values.append(horizon["excess_pct"])
        mean = sum(values) / len(values) if values else None
        rows.append("<tr><td class='num'>%d</td><td class='num'>%d</td>"
                    "<td class='num'>%s</td></tr>" % (
                        days, len(values), fmt_pct(mean)))
    head = ("<tr><th class='num'>Trading days</th>"
            "<th class='num'>Rows</th>"
            "<th class='num'>Mean excess</th></tr>")
    return "<table>%s%s</table>" % (head, "".join(rows))


def _falsifier_totals(scored):
    total = {"for": 0, "against": 0, "unresolved": 0}
    for row in scored:
        for key in total:
            total[key] += (row.get("falsifiers") or {}).get(key, 0)
    return ("<div class='cards'>"
            "<div class='card'><div class='n'>%d</div>"
            "<div class='l'>resolved for the council</div></div>"
            "<div class='card'><div class='n'>%d</div>"
            "<div class='l'>resolved against</div></div>"
            "<div class='card'><div class='n'>%d</div>"
            "<div class='l'>unresolved</div></div></div>" % (
                total["for"], total["against"], total["unresolved"]))


def _tokens_section(scored, ledger_by_id, rules):
    min_rows = rules.get("correlation_min_rows", 20)
    pairs = []
    table_rows = []
    for row in scored:
        if not row["rating_outcome"]["has_252_outcome"]:
            continue
        excess = _excess_252(row)
        tokens = sitting_tokens(ledger_by_id.get(row.get("ledger_row_id")))
        if excess is None or tokens is None:
            continue
        pairs.append((float(tokens), float(excess)))
        subject = row.get("subject") or {}
        table_rows.append((subject.get("name"), tokens, excess))
    n = len(pairs)
    if n < min_rows:
        return ("<div class='refuse'>The correlation of tokens against "
                "return is refused below %d scored rows. %d row%s "
                "carr%s a 252-day outcome with the tokens to pair it. "
                "This is a record; it is not yet enough to say whether "
                "each token buys return.</div>" % (
                    min_rows, n, "" if n == 1 else "s",
                    "ies" if n == 1 else "y"))
    coefficient = _pearson(pairs)
    body = []
    for name, tokens, excess in table_rows:
        body.append("<tr><td>%s</td><td class='num'>%s</td>"
                    "<td class='num'>%s</td></tr>" % (
                        esc(name), fmt_int(tokens), fmt_pct(excess)))
    head = ("<tr><th>Sitting</th><th class='num'>Tokens</th>"
            "<th class='num'>252-day excess</th></tr>")
    coefficient_line = ("Correlation of tokens against 252-day excess "
                        "return across %d sittings: %s." % (
                            n, "%.2f" % coefficient
                            if coefficient is not None else "—"))
    caveat = rules.get("correlation_caveat", "n is small; this is a record, "
                       "not a proof")
    return ("<p>%s</p><p class='caveat'>%s.</p><table>%s%s</table>" % (
        esc(coefficient_line), esc(caveat), head, "".join(body)))


def render(scored, ledger_by_id, rules):
    rows = scored["rows"]
    observed = [r for r in rows if r["observed"]]
    with_252 = [r for r in rows if r["rating_outcome"]["has_252_outcome"]]
    right = [r for r in with_252 if r["rating_outcome"]["correct"] is True]
    hit_rate = ("%.1f%%" % (100.0 * len(right) / len(with_252))
                if with_252 else "—")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    cards = ("<div class='cards'>"
             "<div class='card'><div class='n'>%d</div>"
             "<div class='l'>verdicts on record</div></div>"
             "<div class='card'><div class='n'>%d</div>"
             "<div class='l'>with observations</div></div>"
             "<div class='card'><div class='n'>%d</div>"
             "<div class='l'>with a 252-day outcome</div></div>"
             "<div class='card'><div class='n'>%s</div>"
             "<div class='l'>right at 252 trading days</div></div></div>" % (
                 len(rows), len(observed), len(with_252), hit_rate))
    parts = [
        "<!doctype html><html lang='en' data-theme='dark'><head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Council ledger — the track record</title>",
        "<style>%s</style></head><body><div class='wrap'>" % CSS,
        "<div class='top'><div>",
        "<h1>Council ledger — the track record</h1>",
        "<div class='meta'>Every published verdict, scored against what "
        "happened. Book-blind: identity only, no size and no holding. "
        "Rendered %s.</div></div>" % esc(stamp),
        "<button id='theme' class='themebtn' type='button'>Light / dark"
        "</button></div>",
        cards,
        "<h2>Verdicts and outcomes</h2>",
        _verdict_table(rows, ledger_by_id),
        "<h2>Hit rate by rating word</h2>",
        _hit_rate_table(rows),
        "<h2>Mean excess by horizon</h2>",
        _mean_excess_table(rows, rules),
        "<h2>Falsifiers</h2>",
        _falsifier_totals(rows),
        "<h2>Tokens per sitting against excess return</h2>",
        _tokens_section(rows, ledger_by_id, rules),
        "<div class='foot'>Scoring rules version %s (owner ruling AC7). "
        "The scoring script never fetches; every figure was recorded by a "
        "capture session. This page opens from disk with no network."
        "</div>" % esc(scored.get("scoring_rules_version")),
        "</div>", _THEME_SCRIPT, "</body></html>"]
    return "".join(parts)


def _reconcile_with_ledger(scored_rows, ledger_rows, rules):
    """Every published verdict must appear on the page, in ledger order. A
    row scored earlier keeps its outcome; a row appended AFTER the last
    scoring run is shown as pending - so the page's 'every published verdict'
    and its count stay true instead of silently omitting one."""
    by_id = {r.get("ledger_row_id"): r for r in scored_rows}
    return [by_id.get(row.get("ledger_row_id"))
            or score.score_row(row, None, rules) for row in ledger_rows]


def build_page(ledger_path=None, scored_path=None, rules=None):
    rules = rules or ledger.load_rules()
    ledger_path = ledger_path or ledger.default_path()
    ledger_rows = ledger.confirmed_rows(ledger.read_rows(ledger_path))
    ledger_by_id = {r.get("ledger_row_id"): r for r in ledger_rows}
    if scored_path is None:
        candidate = os.path.join(
            os.path.dirname(os.path.abspath(ledger_path)), "scored.json")
        scored_path = candidate if os.path.exists(candidate) else None
    if scored_path and os.path.exists(scored_path):
        scored = canonical.read_json(scored_path)
        scored["rows"] = _reconcile_with_ledger(
            scored.get("rows", []), ledger_rows, rules)
    else:
        scored = {"scored_version": score.SCORED_VERSION,
                  "scoring_rules_version": rules.get("scoring_rules_version"),
                  "scoring_horizon_trading_days":
                      rules["scoring_horizon_trading_days"],
                  "rows": [score.score_row(row, None, rules)
                           for row in ledger_rows]}
    return render(scored, ledger_by_id, rules)


def main(argv):
    ledger_path = None
    scored_path = None
    out = None
    index = 0
    while index < len(argv):
        flag = argv[index]
        if flag == "--ledger" and index + 1 < len(argv):
            ledger_path = argv[index + 1]
            index += 2
        elif flag == "--scored" and index + 1 < len(argv):
            scored_path = argv[index + 1]
            index += 2
        elif flag == "-o" and index + 1 < len(argv):
            out = argv[index + 1]
            index += 2
        else:
            print(__doc__)
            return 2
    resolved_ledger = ledger_path or ledger.default_path()
    page = build_page(resolved_ledger, scored_path)
    if out is None:
        out = os.path.join(os.path.dirname(os.path.abspath(resolved_ledger)),
                           "scorecard.html")
    canonical.write_bytes_atomic(out, page.encode("utf-8"))
    print("scorecard written to %s (%d bytes)" % (out, len(page)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
