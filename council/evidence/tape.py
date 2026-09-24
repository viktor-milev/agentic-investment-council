"""The tape table (spec U4.3, owner ruling AC4).

At the freeze the daily closes the pack carries are turned into the
figures a seat would otherwise read off a chart: the distance from the
50-, 100- and 200-bar averages and each average's own price (unit
U4(b)), the 200-bar average's slope, the place in the 52-week range,
the drawdown, the returns (absolute and minus the benchmark), the
realized volatility, the volume signature and the extremes. Every figure is a derived Tier-1 fact whose operation is
"series_stat", whose operands name the series it was read from, whose
window is stated in BARS (trading days, never calendar days; the 52-week
window is the last 252 bars) and whose formula prints the arithmetic a
reader recomputes it from.

Nothing else is computed: the table is the seats' chart, not a quant
library. A figure the series is too short for, or that has no benchmark
close to be set against, is a declared gap - never a crash, never a
guess.

Precision. The freeze rounds nothing: every other derived figure in a
pack recomputes EXACTLY from its operands (PRECISION-REG-1). A tape
figure cannot always be exact - a logarithm, a square root, a division
by 21 or 63 - so every tape figure is computed at WORKING_PRECISION
significant digits and rounded ONCE, half-up, to PLACES decimal places.
A close, a date and a count are printed exactly as observed or counted.
The same series gives the same strings on every machine: decimal
division, logarithm and square root are correctly rounded at a stated
precision, so the gate can recompute every row and compare strings.

Benchmark matching (closes register item P-U4a1-9). The benchmark may
trade on other days than the subject. A return window's two dates are
each matched to the benchmark's last close ON OR BEFORE that date; where
the benchmark has no close on or before it, that row is a declared gap.

Standard library only. No network, no broker call: the series arrive in
the pack.
"""

from bisect import bisect_right
from decimal import ROUND_HALF_UP, Decimal, localcontext

OPERATION = "series_stat"
WORKING_PRECISION = 60
PLACES = 10
TRADING_DAYS_A_YEAR = 252

SMA_WINDOWS = (50, 100, 200)
RETURN_WINDOWS = (21, 63, 126, 252)
VOLATILITY_WINDOWS = (21, 63, 252)
YEAR_BARS = 252
SLOPE_BARS = 60
VOLUME_SHORT, VOLUME_LONG = 20, 250

# Every figure the spec's sentence names, in its order. No more.
ROW_IDS = (
    tuple("tape_close_vs_sma%d" % k for k in SMA_WINDOWS)
    + ("tape_sma200_slope_60", "tape_range_place_252",
       "tape_drawdown_from_high_252")
    + tuple("tape_return_%d" % k for k in RETURN_WINDOWS)
    + tuple("tape_return_vs_benchmark_%d" % k for k in RETURN_WINDOWS)
    + tuple("tape_realized_vol_%d" % k for k in VOLATILITY_WINDOWS)
    + ("tape_volume_20_vs_250", "tape_largest_fall_252",
       "tape_high_close_252", "tape_low_close_252",
       "tape_closes_above_sma200_252"))

# Unit U4(b): the three average prices themselves, appended after the
# spec's figures so every figure keeps its place. A seat can then say
# where the 200-day average stands from the record, not only how far the
# price is from it. The page's display table leaves them out (the chart
# draws each average as a line).
LEVEL_IDS = tuple("tape_sma%d_level" % k for k in SMA_WINDOWS)
ROW_IDS = ROW_IDS + LEVEL_IDS

# The plain-English name the owner's evidence document prints instead of
# the id (the fact's optional label, owner ruling AC15 P5): at most eight
# words, and never a word that would make a figure read as an annual one.
LABELS = dict(
    [("tape_close_vs_sma%d" % k, "Price against its %d-day average" % k)
     for k in SMA_WINDOWS]
    + [("tape_sma200_slope_60", "Slope of the 200-day average, 60 days"),
       ("tape_range_place_252", "Place in the 52-week price range"),
       ("tape_drawdown_from_high_252", "Fall from the 52-week closing high")]
    + [("tape_return_%d" % k, "Price return over %d trading days" % k)
       for k in RETURN_WINDOWS]
    + [("tape_return_vs_benchmark_%d" % k,
        "Return against the benchmark, %d trading days" % k)
       for k in RETURN_WINDOWS]
    + [("tape_realized_vol_%d" % k,
        "Realized volatility over %d trading days" % k)
       for k in VOLATILITY_WINDOWS]
    + [("tape_volume_20_vs_250",
        "Recent trading volume against its usual level"),
       ("tape_largest_fall_252", "Largest one-day fall in 52 weeks"),
       ("tape_high_close_252", "Highest close in 52 weeks"),
       ("tape_low_close_252", "Lowest close in 52 weeks"),
       ("tape_closes_above_sma200_252",
        "Days closing above the 200-day average, 52 weeks")]
    + [("tape_sma%d_level" % k, "The %d-day average price" % k)
       for k in SMA_WINDOWS])

_WEAKENED = ("the seats read the tape without this figure; the "
             "market-structure and risk reads lean on the rows that remain")


class _Gap(Exception):
    """A row that cannot be computed: its reason and its reason kind."""

    def __init__(self, reason, reason_kind="other"):
        super().__init__(reason)
        self.reason = reason
        self.reason_kind = reason_kind


def _rounded(value, places=PLACES):
    """`value` rounded half-up to `places` decimal places, plain digits,
    never a negative zero."""
    result = value.quantize(Decimal(1).scaleb(-places),
                            rounding=ROUND_HALF_UP)
    if result.is_zero():
        result = result.copy_abs()
    return format(result, "f")


def _working(value):
    """A working figure exactly as computed (WORKING_PRECISION digits),
    trailing zeros dropped, plain digits, never a negative zero - so a
    reader recomputing from it gets the frozen figure (P-U4a2-1)."""
    value = value.normalize()
    return format(value.copy_abs() if value.is_zero() else value, "f")


def _plain(value):
    """An exact figure (a sum, an exact average) in plain digits."""
    return format(value, "f")


class _Series:
    """One series read once: its dates, its closes as exact strings and
    as Decimals, its volumes, and the running sums the averages use."""

    def __init__(self, series):
        bars = series["bars"]
        self.ticker = series["ticker"]
        self.dates = [bar["date"] for bar in bars]
        self.close_text = [bar["close"] for bar in bars]
        self.closes = [Decimal(text) for text in self.close_text]
        self.volumes = [Decimal(bar["volume"]) for bar in bars]
        self.count = len(bars)
        self.last = self.count - 1
        running = [Decimal(0)]
        for close in self.closes:
            running.append(running[-1] + close)
        self._running = running

    def need(self, bars, what):
        if self.count < bars:
            raise _Gap("the series has %d bars; %s needs %d"
                       % (self.count, what, bars))

    def close_sum(self, end, bars):
        """The sum of the `bars` closes ending at bar `end` (exact)."""
        return self._running[end + 1] - self._running[end + 1 - bars]

    def average(self, end, bars):
        return self.close_sum(end, bars) / bars

    def first_of_last(self, bars):
        """The date of the first of the last `bars` bars."""
        return self.dates[self.count - bars]

    def on_or_before(self, day):
        """The index of the last bar dated on or before `day`, or None."""
        index = bisect_right(self.dates, day) - 1
        return index if index >= 0 else None


def _last_bars(subject, bars):
    return "last %d bars, %s to %s" % (
        bars, subject.first_of_last(bars), subject.dates[subject.last])


def _sma(subject, bars):
    """The `bars`-bar average ending on the last bar: (its exact sum, the
    average, the sentence that prints the division). The one computation
    both the distance row and the average price row read."""
    subject.need(bars, "a %d-bar average" % bars)
    total = subject.close_sum(subject.last, bars)
    division = ("%d-bar average = %s (the sum of the %d closes) / %d"
                % (bars, _plain(total), bars, bars))
    return total / bars, division


def _close_vs_sma(subject, bars):
    average, division = _sma(subject, bars)
    value = (subject.closes[subject.last] / average - 1) * 100
    formula = ("(last close %s / %d-bar average %s - 1) * 100; %s"
               % (subject.close_text[subject.last], bars, _plain(average),
                  division))
    return "%", _rounded(value), _last_bars(subject, bars), formula, None


def _sma_level(subject, bars, price_unit):
    """The average price itself, in the unit the closes are quoted in,
    rounded once to PLACES; its formula prints the exact division."""
    average, division = _sma(subject, bars)
    return (price_unit, _rounded(average), _last_bars(subject, bars),
            division, None)


def _sma200_slope(subject):
    bars = 200 + SLOPE_BARS
    subject.need(bars, "the 200-bar average's slope over 60 bars")
    then = subject.last - SLOPE_BARS
    now_total = subject.close_sum(subject.last, 200)
    then_total = subject.close_sum(then, 200)
    now_average, then_average = now_total / 200, then_total / 200
    value = (now_average / then_average - 1) * 100
    window = ("last %d bars: the 200-bar average ending %s against the "
              "one ending %s, 60 bars earlier"
              % (bars, subject.dates[subject.last], subject.dates[then]))
    formula = ("(200-bar average %s / 200-bar average %s - 1) * 100; "
               "%s = %s / 200 (the closes ending %s); %s = %s / 200 "
               "(the closes ending %s)"
               % (_plain(now_average), _plain(then_average),
                  _plain(now_average), _plain(now_total),
                  subject.dates[subject.last], _plain(then_average),
                  _plain(then_total), subject.dates[then]))
    return "%", _rounded(value), window, formula, None


def _year_extremes(subject):
    """(index of the highest, index of the lowest) of the last 252
    closes; the earliest such bar on a tie."""
    subject.need(YEAR_BARS, "the 52-week window (252 bars)")
    indexes = range(subject.count - YEAR_BARS, subject.count)
    high = min(indexes, key=lambda i: (-subject.closes[i], i))
    low = min(indexes, key=lambda i: (subject.closes[i], i))
    return high, low


def _range_place(subject):
    high, low = _year_extremes(subject)
    width = subject.closes[high] - subject.closes[low]
    if width == 0:
        raise _Gap("the last 252 closes are all equal, so the 52-week "
                   "range has no width to place the last close in")
    value = (subject.closes[subject.last] - subject.closes[low]) / width
    formula = ("(last close %s - lowest close %s) / (highest close %s - "
               "lowest close %s)"
               % (subject.close_text[subject.last], subject.close_text[low],
                  subject.close_text[high], subject.close_text[low]))
    return ("fraction_of_range", _rounded(value),
            _last_bars(subject, YEAR_BARS), formula, None)


def _drawdown(subject):
    high, _ = _year_extremes(subject)
    value = (subject.closes[subject.last] / subject.closes[high] - 1) * 100
    formula = ("(last close %s / highest close %s on %s - 1) * 100"
               % (subject.close_text[subject.last],
                  subject.close_text[high], subject.dates[high]))
    return "%", _rounded(value), _last_bars(subject, YEAR_BARS), formula, None


def _return(subject, bars):
    subject.need(bars + 1, "a %d-bar return (%d closes)" % (bars, bars + 1))
    start = subject.last - bars
    value = (subject.closes[subject.last] / subject.closes[start] - 1) * 100
    window = ("%d bars, close %s to close %s"
              % (bars, subject.dates[start], subject.dates[subject.last]))
    formula = ("(close %s on %s / close %s on %s - 1) * 100"
               % (subject.close_text[subject.last],
                  subject.dates[subject.last], subject.close_text[start],
                  subject.dates[start]))
    return value, window, formula


def _absolute_return(subject, bars):
    value, window, formula = _return(subject, bars)
    return "%", _rounded(value), window, formula, None


def _relative_return(subject, benchmark, bars):
    if benchmark is None:
        raise _Gap("the sitting has no benchmark (its asset class is rated "
                   "absolutely), so a return minus a benchmark does not "
                   "exist", "absent_by_design")
    own, window, own_formula = _return(subject, bars)
    end_day = subject.dates[subject.last]
    start_day = subject.dates[subject.last - bars]
    matched = {}
    for which, day in (("end", end_day), ("start", start_day)):
        index = benchmark.on_or_before(day)
        if index is None:
            raise _Gap("the benchmark has no %s close on or before %s, the "
                       "subject's %s date for the %d-bar return"
                       % (benchmark.ticker, day, which, bars))
        matched[which] = index
    end, start = matched["end"], matched["start"]
    theirs = (benchmark.closes[end] / benchmark.closes[start] - 1) * 100
    formula = ("%s - (%s close %s on %s / %s close %s on %s - 1) * 100; "
               "the benchmark matched by date - its last close on or "
               "before %s and on or before %s"
               % (own_formula, benchmark.ticker, benchmark.close_text[end],
                  benchmark.dates[end], benchmark.ticker,
                  benchmark.close_text[start], benchmark.dates[start],
                  end_day, start_day))
    return ("percentage_points", _rounded(own - theirs), window, formula,
            None)


def _realized_volatility(subject, bars):
    subject.need(bars + 1, "%d daily returns (%d closes)" % (bars, bars + 1))
    first = subject.last - bars + 1
    logs = [(subject.closes[i] / subject.closes[i - 1]).ln()
            for i in range(first, subject.count)]
    mean = sum(logs) / bars
    squares = sum((value - mean) ** 2 for value in logs)
    value = (squares / (bars - 1) * TRADING_DAYS_A_YEAR).sqrt()
    window = ("%d bars of daily log returns, close %s to close %s"
              % (bars, subject.dates[first - 1], subject.dates[subject.last]))
    formula = ("sqrt(S / (%d - 1) * %d): the sample standard deviation of "
               "the %d daily log returns ln(close / prior close), times "
               "sqrt(%d); mean return %s and S = %s, the sum of squared "
               "deviations from it (both exactly as computed)"
               % (bars, TRADING_DAYS_A_YEAR, bars, TRADING_DAYS_A_YEAR,
                  _working(mean), _working(squares)))
    return "fraction_annualized", _rounded(value), window, formula, None


def _volume_ratio(subject):
    subject.need(VOLUME_LONG, "a %d-bar average volume" % VOLUME_LONG)
    short = sum(subject.volumes[subject.count - VOLUME_SHORT:])
    long = sum(subject.volumes[subject.count - VOLUME_LONG:])
    if long == 0:
        raise _Gap("the last %d volumes are all zero, so the ratio has no "
                   "base" % VOLUME_LONG)
    value = (short / VOLUME_SHORT) / (long / VOLUME_LONG)
    window = ("last %d bars against last %d bars, %s and %s to %s"
              % (VOLUME_SHORT, VOLUME_LONG,
                 subject.first_of_last(VOLUME_SHORT),
                 subject.first_of_last(VOLUME_LONG),
                 subject.dates[subject.last]))
    formula = ("(%s / %d) / (%s / %d): the average volume of the last %d "
               "bars over the average of the last %d"
               % (_plain(short), VOLUME_SHORT, _plain(long), VOLUME_LONG,
                  VOLUME_SHORT, VOLUME_LONG))
    return "x", _rounded(value), window, formula, None


def _largest_fall(subject):
    subject.need(YEAR_BARS + 1, "252 one-day changes (253 closes)")
    first = subject.count - YEAR_BARS
    worst = min(range(first, subject.count),
                key=lambda i: (subject.closes[i] / subject.closes[i - 1], i))
    ratio = subject.closes[worst] / subject.closes[worst - 1]
    if ratio >= 1:
        raise _Gap("none of the 252 one-day changes from %s to %s is a fall"
                   % (subject.dates[first], subject.dates[subject.last]))
    window = ("last 253 bars: 252 one-day changes, close %s to close %s"
              % (subject.dates[first - 1], subject.dates[subject.last]))
    formula = ("(close %s on %s / close %s on %s - 1) * 100: the largest "
               "of the one-day falls"
               % (subject.close_text[worst], subject.dates[worst],
                  subject.close_text[worst - 1], subject.dates[worst - 1]))
    return ("%", _rounded((ratio - 1) * 100), window, formula,
            subject.dates[worst])


def _year_close(subject, price_unit, highest):
    high, low = _year_extremes(subject)
    index = high if highest else low
    formula = ("the %s of the last 252 closes: %s on %s (the earliest "
               "such close on a tie)"
               % ("highest" if highest else "lowest",
                  subject.close_text[index], subject.dates[index]))
    return (price_unit, subject.close_text[index],
            _last_bars(subject, YEAR_BARS), formula, subject.dates[index])


def _closes_above_sma200(subject):
    subject.need(YEAR_BARS + 199,
                 "a 200-bar average on each of the last 252 bars (451 "
                 "closes)")
    first = subject.count - YEAR_BARS
    count = sum(1 for i in range(first, subject.count)
                if subject.closes[i] > subject.average(i, 200))
    formula = ("the number of the last 252 closes strictly above the "
               "average of the 200 closes ending on the same bar")
    return ("bars", str(count), _last_bars(subject, YEAR_BARS), formula,
            None)


def _row(row_id, subject, benchmark, price_unit):
    """(unit, value, window, formula, bar date or None) for one row, or
    raise _Gap."""
    for k in SMA_WINDOWS:
        if row_id == "tape_close_vs_sma%d" % k:
            return _close_vs_sma(subject, k)
        if row_id == "tape_sma%d_level" % k:
            return _sma_level(subject, k, price_unit)
    for k in RETURN_WINDOWS:
        if row_id == "tape_return_%d" % k:
            return _absolute_return(subject, k)
        if row_id == "tape_return_vs_benchmark_%d" % k:
            return _relative_return(subject, benchmark, k)
    for k in VOLATILITY_WINDOWS:
        if row_id == "tape_realized_vol_%d" % k:
            return _realized_volatility(subject, k)
    return {
        "tape_sma200_slope_60": lambda: _sma200_slope(subject),
        "tape_range_place_252": lambda: _range_place(subject),
        "tape_drawdown_from_high_252": lambda: _drawdown(subject),
        "tape_volume_20_vs_250": lambda: _volume_ratio(subject),
        "tape_largest_fall_252": lambda: _largest_fall(subject),
        "tape_high_close_252":
            lambda: _year_close(subject, price_unit, True),
        "tape_low_close_252":
            lambda: _year_close(subject, price_unit, False),
        "tape_closes_above_sma200_252":
            lambda: _closes_above_sma200(subject),
    }[row_id]()


def tape_table(price_series, benchmark_series=None, *, price_unit,
               freshness_rule_days):
    """The tape table over one subject series and, where the sitting has
    a benchmark, its series (None on an absolute sitting).

    Returns {"facts": [...], "gaps": [...]}: every id of ROW_IDS appears
    exactly once, in that order, either as a derived Tier-1 fact or as a
    declared gap shaped like a capture gap. `price_unit` is the unit the
    closes are quoted in (the highest and lowest close and the three
    average prices carry it);
    `freshness_rule_days` is the freshness rule each fact carries. The
    inputs are read, never rewritten."""
    with localcontext() as context:
        context.prec = WORKING_PRECISION
        subject = _Series(price_series)
        benchmark = (_Series(benchmark_series)
                     if benchmark_series is not None else None)
        facts, gaps = [], []
        for row_id in ROW_IDS:
            try:
                unit, value, window, formula, bar_date = _row(
                    row_id, subject, benchmark, price_unit)
            except _Gap as gap:
                gaps.append({"fact_class": row_id, "reason": gap.reason,
                             "reason_kind": gap.reason_kind,
                             "weakened_test": _WEAKENED})
                continue
            operands = [{"label": "price_series", "value": subject.ticker}]
            if row_id.startswith("tape_return_vs_benchmark_"):
                operands.append({"label": "benchmark_series",
                                 "value": benchmark.ticker})
            derived = {"operation": OPERATION, "operands": operands,
                       "window": window, "formula": formula}
            if bar_date is not None:
                derived["date"] = bar_date
            facts.append({
                "id": row_id, "label": LABELS[row_id], "value": value,
                "unit": unit,
                "as_of": subject.dates[subject.last],
                "source": ("tape table computed at freeze from the daily "
                           "series (%s)" % price_series["source"]),
                "freshness_rule_days": freshness_rule_days,
                "derived": derived})
        return {"facts": facts, "gaps": gaps}
