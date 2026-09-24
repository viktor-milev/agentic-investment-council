"""chart.py - the price chart and the tape's one-page display on the report page (spec U4, the
chart on the page; unit U4(c); owner rulings AC16 and AC27).

The owner's page shows the chart the seats read: the daily closes the pack carries, the moving
averages the tape carries, the benchmark beside them, the 52-week range, the price the ruling is
made against and every price level the verdict says would reopen the case - and under it the
tape's figures in plain words, on one page.

WHAT IS DRAWN, AND FROM WHAT. Nothing here is a new figure. The closes and the benchmark's closes
are the pack's series; the band is the tape's own highest and lowest close; the levels are the
verdict's price triggers, read exactly as the "What changes this rating" table reads them; the
marker is the rating box's leading key number, where it cites the pack's own price fact. The one
thing computed is the moving average, and only to DRAW it: the tape records the price's distance
from each average, not the average's level.
Every average drawn is checked against the tape before a single coordinate is written - the price's
distance from the drawn line's last point, rounded as the tape rounds, must be the tape's figure,
or the render is refused by name (architect ruling 2). The page never shows a line that disagrees
with the record.

DETERMINISTIC. A fixed drawing area in the SVG's own units, every coordinate computed in Decimal and
printed rounded half-up to COORD_PLACES decimal places; no float ever reaches the page, so two
renders of one run are the same bytes.

BOTH THEMES. Colour comes only from classes the page's stylesheet styles with its theme tokens; no
colour is written into the drawing. The dark screen, the light toggle and the light print follow.

Standard library only; no script is needed to see the chart or to print it.
"""

import html
import re
from bisect import bisect_right
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, localcontext

from council.evidence import gate, tape


class ChartRefused(Exception):
    """The chart would disagree with the pack's own record. The message says where, in plain
    words; the report is not rendered."""


# The drawing area, in the SVG's own units: the page scales it to its width, height by aspect.
VIEW_WIDTH = 800
VIEW_HEIGHT = 360
PLOT_LEFT = 72
LABEL_CHAR_UNITS = 11
PLOT_RIGHT = 788
PLOT_TOP = 16
PLOT_BOTTOM = 330
DATE_LABEL_DROP = 22
TICK_LABEL_GAP = 8
LABEL_LIFT = 5
MARK_RADIUS = 4
BAND_MIN_HEIGHT = Decimal(2)
COORD_PLACES = 1
COORD_PRECISION = 40

PRICE_TICKS = 5
DATE_TICKS = 5
RANGE_PAD = Decimal("0.05")
NICE_STEPS = (1, 2, 5, 10)

LEVEL_WORDS = "— reopen the case"
REBASED_WORDS = "rebased to the first close"
GAP_WORDS = "no figure — declared gap"
MISSING_WORDS = "the pack carries neither this figure nor a declared gap for it"

# The spec's fifteen display rows over the tape's facts (architect ruling 6): the grouping is
# DATA, kept here beside the page that prints it rather than in the floors. Each row is its short
# title (None: the one fact's own label) and its figures, each named within the row (None: the
# row's only figure). Every fact of tape.ROW_IDS appears exactly once, except the three average
# prices of tape.LEVEL_IDS (unit U4(b)), which appear in no row: the chart draws each average as
# a line. A suite test holds it.
TAPE_DISPLAY_ROWS = (
    (None, (("tape_close_vs_sma50", None),)),
    (None, (("tape_close_vs_sma100", None),)),
    (None, (("tape_close_vs_sma200", None),)),
    (None, (("tape_sma200_slope_60", None),)),
    (None, (("tape_range_place_252", None),)),
    (None, (("tape_drawdown_from_high_252", None),)),
    ("Return over 21 trading days", (("tape_return_21", "the price"),
                                     ("tape_return_vs_benchmark_21", "against the benchmark"))),
    ("Return over 63 trading days", (("tape_return_63", "the price"),
                                     ("tape_return_vs_benchmark_63", "against the benchmark"))),
    ("Return over 126 trading days", (("tape_return_126", "the price"),
                                      ("tape_return_vs_benchmark_126", "against the benchmark"))),
    ("Return over 252 trading days", (("tape_return_252", "the price"),
                                      ("tape_return_vs_benchmark_252", "against the benchmark"))),
    ("Realized volatility, annualized", (("tape_realized_vol_21", "21 trading days"),
                                         ("tape_realized_vol_63", "63 trading days"),
                                         ("tape_realized_vol_252", "252 trading days"))),
    (None, (("tape_volume_20_vs_250", None),)),
    (None, (("tape_largest_fall_252", None),)),
    ("Highest and lowest close in 52 weeks", (("tape_high_close_252", "highest"),
                                              ("tape_low_close_252", "lowest"))),
    (None, (("tape_closes_above_sma200_252", None),)),
)

# A value "reads as a number" exactly as the page's own formatter reads one.
_NUMERIC = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _esc(text):
    return html.escape("" if text is None else str(text), quote=True)


def _number(value):
    """The value as a Decimal where it reads as a plain number, else None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return Decimal(text) if _NUMERIC.match(text) else None


def tape_entries(capture):
    """(facts by id, declared gaps by id) - the tape's rows as the pack carries them."""
    facts = {fact.get("id"): fact for fact in capture.get("tier1") or []
             if fact.get("id") in tape.LABELS}
    gaps = {gap.get("fact_class"): gap for gap in capture.get("gaps") or []
            if gap.get("fact_class") in tape.LABELS}
    return facts, gaps


def _price_fact(capture, ticker):
    """The pack's price fact for the series' instrument, read as the freeze reads it: the
    member's price_last__<ticker> in an expression, else price_last. (id, fact), or (None, {})."""
    facts = {fact.get("id"): fact for fact in capture.get("tier1") or []}
    for fact_id in ("price_last" + gate.frame_suffix(capture.get("subject") or {}, ticker),
                    "price_last"):
        if facts.get(fact_id):
            return fact_id, facts[fact_id]
    return None, {}


# --- what is drawn -----------------------------------------------------------------------------

def _checked_average(closes, window, fact):
    """The rolling simple average of `window` closes, as [(bar, average)], FOR DRAWING - refused
    unless its last point gives the tape's own figure for the price's distance from it."""
    name = "%d-day average" % window
    if len(closes) < window:
        raise ChartRefused(
            "the tape records the price against its %s, but the series has only %d closes, so "
            "the chart cannot draw that average; the report is not rendered" % (name, len(closes)))
    running = [Decimal(0)]
    for close in closes:
        running.append(running[-1] + close)
    line = [(end, (running[end + 1] - running[end + 1 - window]) / window)
            for end in range(window - 1, len(closes))]
    distance = ((closes[-1] / line[-1][1] - 1) * 100).quantize(
        Decimal(1).scaleb(-tape.PLACES), rounding=ROUND_HALF_UP)
    if distance.is_zero():
        distance = distance.copy_abs()
    if format(distance, "f") != str(fact.get("value")):
        raise ChartRefused(
            "the %s drawn from the pack's closes puts the last close %s%% from it, but the tape "
            "records %s%%: the chart would disagree with the record, so the report is not "
            "rendered" % (name, format(distance, "f"), fact.get("value")))
    return line


def _rebased_benchmark(series, benchmark, closes):
    """The benchmark's closes as [(bar, value)]: each subject date matched to the benchmark's last
    close on or before it (the tape's own rule), rebased to the subject's close at the first
    matched date. None where there is no benchmark series or no date matches."""
    if not benchmark or not benchmark.get("bars"):
        return None
    days = [bar["date"] for bar in benchmark["bars"]]
    theirs = [Decimal(bar["close"]) for bar in benchmark["bars"]]
    points, base = [], None
    for index, bar in enumerate(series["bars"]):
        match = bisect_right(days, bar["date"]) - 1
        if match < 0:
            continue
        if base is None:
            base = (theirs[match], closes[index])
        points.append((index, theirs[match] / base[0] * base[1]))
    return points or None


def _drawn_levels(verdict, ticker, unit, single):
    """Every price trigger the "What changes this rating" table lists that can be drawn on this
    series: a level that reads as a number, in the price's own unit, bound to this series'
    instrument (a constituent's level only on that constituent's series; on a basket or theme a
    level bound to no member draws nothing). An event trigger, a falsifier and an invalidation
    level draw nothing (architect ruling 1)."""
    triggers = (verdict.get("tripwires") or {}).get("reopening_triggers") or []
    drawn = []
    for trigger in triggers:
        if trigger.get("kind") != "price" or not trigger.get("level"):
            continue
        value = _number(trigger["level"])
        bound = trigger.get("constituent")
        if value is None or trigger.get("unit") != unit:
            continue
        if (bound and str(bound) != str(ticker)) or (not bound and not single):
            continue
        drawn.append((value, trigger))
    return drawn


def _ruling_mark(verdict, price_id, unit, single):
    """The rating box's leading key number, for a single subject, where it cites the pack's own
    price fact (`price_id`) and is a number in the price's own unit: (value, key number) or None.
    The envelope's order is model-authored, so a leading figure that merely shares the price's
    unit - a dividend per share, a price target - is never marked as the price (audit round 1
    of U4(c), r1-1)."""
    numbers = (verdict.get("atlas_envelope") or {}).get("key_numbers") or []
    if not single or not numbers or price_id is None:
        return None
    if numbers[0].get("pack_fact_id") != price_id:
        return None
    value = _number(numbers[0].get("value"))
    if value is None or numbers[0].get("unit") != unit:
        return None
    return value, numbers[0]


# --- geometry ----------------------------------------------------------------------------------

def _q(value):
    """A coordinate as printed: rounded half-up to COORD_PLACES decimal places, plain digits."""
    return format(Decimal(value).quantize(Decimal(1).scaleb(-COORD_PLACES),
                                          rounding=ROUND_HALF_UP), "f")


def _nice_step(raw):
    unit = Decimal(1).scaleb(raw.adjusted())
    for multiple in NICE_STEPS:
        if multiple * unit >= raw:
            return multiple * unit
    return NICE_STEPS[-1] * unit


class _Frame(object):
    """Bars to x, prices to y, over the drawing area."""

    def __init__(self, count, low, high):
        span = high - low
        pad = span * RANGE_PAD if span else (abs(high) * RANGE_PAD or Decimal(1))
        self.low, self.high, self.count = low - pad, high + pad, count
        self.left = PLOT_LEFT

    def x(self, bar):
        if self.count < 2:
            return _q(Decimal(self.left + PLOT_RIGHT) / 2)
        return _q(self.left + Decimal(PLOT_RIGHT - self.left) * bar / (self.count - 1))

    def y(self, value):
        return _q(PLOT_TOP + Decimal(PLOT_BOTTOM - PLOT_TOP) * (self.high - value)
                  / (self.high - self.low))

    def points(self, line):
        return " ".join("%s,%s" % (self.x(bar), self.y(value)) for bar, value in line)

    def price_ticks(self):
        step = _nice_step((self.high - self.low) / (PRICE_TICKS - 1))
        tick = (self.low / step).to_integral_value(rounding=ROUND_CEILING) * step
        ticks = []
        while tick <= self.high:
            ticks.append(tick)
            tick += step
        return ticks


# --- the figure --------------------------------------------------------------------------------

def _joined(words):
    """Words as a reader lists them: a, b and c."""
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]


def _swatch(shape):
    return ('<svg class="ch-key" viewBox="0 0 24 10" aria-hidden="true" focusable="false">%s'
            "</svg>" % shape)


def _line_swatch(css_class):
    return _swatch('<line class="%s" x1="0" y1="5" x2="24" y2="5"/>' % css_class)


def figure(capture, verdict, single, format_number, format_date):
    """The chart as one <figure> of inline SVG. `single` is False for a basket or theme;
    `format_number` and `format_date` are the page's own display rules. Raises ChartRefused where
    a drawn average would disagree with the tape."""
    series = capture["price_series"]
    bars = series["bars"]
    ticker = str(series.get("ticker") or "")
    price_id, price = _price_fact(capture, ticker)
    unit = price.get("unit")
    facts, _gaps = tape_entries(capture)
    with localcontext() as context:
        context.prec = tape.WORKING_PRECISION
        closes = [Decimal(bar["close"]) for bar in bars]
        averages = [(window, _checked_average(closes, window, facts["tape_close_vs_sma%d"
                                                                    % window]))
                    for window in tape.SMA_WINDOWS if "tape_close_vs_sma%d" % window in facts]
        bench = _rebased_benchmark(series, capture.get("benchmark_series"), closes)
    high, low = facts.get("tape_high_close_252"), facts.get("tape_low_close_252")
    band = None
    if high and low and _number(high.get("value")) is not None \
            and _number(low.get("value")) is not None and len(bars) >= tape.YEAR_BARS:
        band = (_number(high["value"]), _number(low["value"]))
    levels = _drawn_levels(verdict, ticker, unit, single)
    mark = _ruling_mark(verdict, price_id, unit, single)

    with localcontext() as context:
        context.prec = COORD_PRECISION
        values = list(closes)
        for _window, line in averages:
            values.extend(value for _bar, value in line)
        values.extend(value for _bar, value in bench or [])
        values.extend(band or [])
        values.extend(value for value, _trigger in levels)
        if mark:
            values.append(mark[0])
        frame = _Frame(len(bars), min(values), max(values))
        ticks = [(tick, format_number(format(tick.normalize(), "f"), unit))
                 for tick in frame.price_ticks()]
        # The price labels sit left of the drawing; a long one (a large price, a rate unit) widens
        # that margin rather than being cut off at the edge.
        frame.left = max([PLOT_LEFT] + [TICK_LABEL_GAP + LABEL_CHAR_UNITS * len(text)
                                        for _tick, text in ticks])
        parts = []
        if band:
            first = len(bars) - tape.YEAR_BARS
            top, bottom = frame.y(band[0]), frame.y(band[1])
            title = ("<title>The 52-week range of closes, %s to %s</title>"
                     % (_esc(format_number(low["value"], unit)),
                        _esc(format_number(high["value"], unit))))
            height = Decimal(bottom) - Decimal(top)
            if height < BAND_MIN_HEIGHT:
                # A year of (nearly) one price: a rectangle this thin would not show, so the range
                # is drawn as a line of visible thickness at its middle (audit round 3, r3-2).
                y = _q((Decimal(bottom) + Decimal(top)) / 2)
                parts.append('<line class="ch-bandline" x1="%s" y1="%s" x2="%s" y2="%s">%s'
                             "</line>" % (frame.x(first), y, frame.x(len(bars) - 1), y, title))
            else:
                parts.append('<rect class="ch-band" x="%s" y="%s" width="%s" height="%s">%s</rect>'
                             % (frame.x(first), top, _q(Decimal(frame.x(len(bars) - 1))
                                                        - Decimal(frame.x(first))),
                                _q(height), title))
        for tick, text in ticks:
            y = frame.y(tick)
            parts.append('<line class="ch-grid" x1="%d" y1="%s" x2="%d" y2="%s"/>'
                         '<text class="ch-txt" x="%d" y="%s" text-anchor="end">%s</text>'
                         % (frame.left, y, PLOT_RIGHT, y, frame.left - TICK_LABEL_GAP, y,
                            _esc(text)))
        count = len(bars)
        marks = sorted({(count - 1) * k // (DATE_TICKS - 1) for k in range(DATE_TICKS)})
        for bar in marks:
            anchor = ("start" if bar == 0 and count > 1 else
                      "end" if bar == count - 1 and count > 1 else "middle")
            parts.append('<text class="ch-txt" x="%s" y="%d" text-anchor="%s">%s</text>'
                         % (frame.x(bar), PLOT_BOTTOM + DATE_LABEL_DROP, anchor,
                            _esc(format_date(bars[bar]["date"]))))
        parts.append('<line class="ch-axis" x1="%d" y1="%d" x2="%d" y2="%d"/>'
                     % (frame.left, PLOT_BOTTOM, PLOT_RIGHT, PLOT_BOTTOM))
        if bench:
            parts.append('<polyline class="ch-bench" points="%s"/>' % frame.points(bench))
        for window, line in averages:
            parts.append('<polyline class="ch-sma%d" points="%s"/>'
                         % (window, frame.points(line)))
        if count > 1:
            parts.append('<polyline class="ch-close" points="%s"/>'
                         % frame.points(enumerate(closes)))
        else:
            parts.append('<circle class="ch-close" cx="%s" cy="%s" r="%d"/>'
                         % (frame.x(0), frame.y(closes[0]), MARK_RADIUS))
        for value, trigger in levels:
            y = frame.y(value)
            parts.append('<g class="ch-levelmark"><title>%s</title>'
                         '<line class="ch-level" x1="%d" y1="%s" x2="%d" y2="%s"/>'
                         '<text class="ch-leveltxt" x="%d" y="%s">%s %s</text></g>'
                         % (_esc(trigger.get("detail", "")), frame.left, y, PLOT_RIGHT, y,
                            frame.left + TICK_LABEL_GAP, _q(Decimal(y) - LABEL_LIFT),
                            _esc(format_number(trigger["level"], unit)), _esc(LEVEL_WORDS)))
        if mark:
            y = frame.y(mark[0])
            shown = "%s %s" % (mark[1].get("name", ""),
                               format_number(mark[1].get("value"), unit))
            parts.append('<g class="ch-markgroup"><title>The price the ruling is made against: '
                         '%s</title><circle class="ch-mark" cx="%d" cy="%s" r="%d"/>'
                         '<text class="ch-marktxt" x="%d" y="%s" text-anchor="end">%s</text></g>'
                         % (_esc(shown.strip()), PLOT_RIGHT, y, MARK_RADIUS,
                            PLOT_RIGHT - TICK_LABEL_GAP, _q(Decimal(y) - LABEL_LIFT),
                            _esc(shown.strip())))

    windows = [window for window, _line in averages]
    legend = [(_line_swatch("ch-close"), "Daily close of %s" % ticker)]
    legend += [(_line_swatch("ch-sma%d" % window), "%d-day average" % window)
               for window in windows]
    drawn = ["the daily closes of %s over %d trading days, %s to %s"
             % (ticker, count, format_date(bars[0]["date"]), format_date(bars[-1]["date"]))]
    if windows:
        drawn.append("the %s average%s" % (_joined(["%d-day" % window for window in windows]),
                                           "s" if len(windows) > 1 else ""))
    if bench:
        name = capture["benchmark_series"].get("ticker") or "the benchmark"
        legend.append((_line_swatch("ch-bench"), "%s, the benchmark, %s" % (name, REBASED_WORDS)))
        drawn.append("%s %s" % (name, REBASED_WORDS))
    if band:
        legend.append((_swatch('<rect class="ch-band" x="0" y="0" width="24" height="10"/>'),
                       "The 52-week range of closes"))
        drawn.append("the 52-week range")
    if levels:
        legend.append((_line_swatch("ch-level"), "A price that would reopen the case"))
        drawn.append("%d price level%s that would reopen the case"
                     % (len(levels), "" if len(levels) == 1 else "s"))
    if mark:
        legend.append((_swatch('<circle class="ch-mark" cx="12" cy="5" r="%d"/>' % MARK_RADIUS),
                       "The price the ruling is made against"))
        drawn.append("the price the ruling is made against")
    desc = "The chart shows %s." % _joined(drawn)
    caption = ["Daily closes from %s, as of %s." % (series.get("source", ""),
                                                   format_date(series.get("as_of", "")))]
    if bench:
        caption.append("The benchmark's closes from %s, as of %s."
                       % (capture["benchmark_series"].get("source", ""),
                          format_date(capture["benchmark_series"].get("as_of", ""))))
    if windows:
        caption.append("Each average is drawn from these closes and agrees with the tape's "
                       "figure for it.")
    return "".join([
        '<figure class="tapechart"><svg viewBox="0 0 %d %d" width="100%%" role="img" '
        'aria-labelledby="tapechart-title tapechart-desc">' % (VIEW_WIDTH, VIEW_HEIGHT),
        '<title id="tapechart-title">Price chart of %s</title>' % _esc(ticker),
        '<desc id="tapechart-desc">%s</desc>' % _esc(desc),
        "".join(parts), "</svg>",
        '<ul class="ch-legend">%s</ul>' % "".join(
            "<li>%s%s</li>" % (swatch, _esc(words)) for swatch, words in legend),
        "<figcaption>%s</figcaption></figure>" % _esc(" ".join(caption)),
    ])


# --- the tape's one-page display ---------------------------------------------------------------

def _figure_line(fact_id, name, facts, gaps, format_number, format_date):
    """One figure of a display row, through the page's display rules; a declared gap as a gap."""
    lead = "%s: " % name if name else ""
    fact = facts.get(fact_id)
    if fact is None:
        reason = (gaps.get(fact_id) or {}).get("reason") or MISSING_WORDS
        return ('<div>%s%s<div class="muted small">%s</div></div>'
                % (_esc(lead), _esc(GAP_WORDS), _esc(reason)))
    shown = format_number(fact.get("value"), fact.get("unit"))
    dated = (fact.get("derived") or {}).get("date")
    if dated:
        shown += " on %s" % format_date(dated)
    return "<div>%s%s</div>" % (_esc(lead), _esc(shown))


def tape_table(capture, format_number, format_date):
    """The fifteen display rows as one table, or None where every row is a declared gap (the
    caller prints the brief's own all-gaps line instead)."""
    facts, gaps = tape_entries(capture)
    if not facts and all(fact_id in gaps for fact_id in tape.ROW_IDS):
        return None
    rows = []
    for title, figures in TAPE_DISPLAY_ROWS:
        if title is None:
            fact_id = figures[0][0]
            title = (facts.get(fact_id) or {}).get("label") or tape.LABELS[fact_id]
        rows.append('<tr class="taperow"><td>%s</td><td>%s</td></tr>'
                    % (_esc(title), "".join(
                        _figure_line(fact_id, name, facts, gaps, format_number, format_date)
                        for fact_id, name in figures)))
    return ('<table class="tapetable"><tr><th>what the tape shows</th><th>the figure</th></tr>'
            "%s</table>" % "".join(rows))
