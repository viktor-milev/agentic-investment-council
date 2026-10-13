"""The broker's daily price history, turned into a capture's series block.

A gatherer seat asks the broker for the daily history (a market-data call);
the host then runs this helper on THAT seat's own session transcript, so the
long reply never enters the host's own context and no bar is ever retyped:

    python -m council.evidence.series <transcript.jsonl> --contract <id>
        --ticker <T> --calendar <C> --as-of <D> --source <text>
        [--last-date <D>] --out <file>

It reads the LAST tool result that answers a `get_price_history` call for
that contract id and writes one object in the shape of the capture's
`price_series` (or `benchmark_series`): the ticker, calendar, source and
as-of the host names, and the bars zipped from the reply's `time`, `close`
and `volume` lists. It fetches nothing and computes nothing: every close
and volume is the reply's own number literal, read as a string, and a bar's
date is the first ten characters of its own time stamp. `--last-date`
drops any bar dated after it (a bar for a day still trading). The gate
checks the series afterwards, exactly as it checks one written by hand.

It refuses, exit 1 and in plain words, when the transcript holds no such
reply, when that last reply is marked as failed (refused before anything
is read from it), when the reply is not a price history, when its lists
are not the same length, when a stamp is not text beginning with a date
written YYYY-MM-DD, or when a close or a volume did not arrive as a number
- a quoted figure, whatever it spells, a null or a missing figure refuses,
naming the bar and its date.

AC72, architect M5: alternatively save the public daily-history reply
and use --coinmetrics <reply.json> --asset <id>, without a transcript or
contract. Its data rows carry a date and a string PriceUSD; the close is
kept exactly and no volume is invented. One calendar day separates each
row, and enough rows remain after --last-date for every tape window.
The code fetches nothing. The gate checks the operator's source words.

AC87(1), AC88(2), URANIUM(c): --sprott reads the exact named daily
value series from a saved public page. --swings-days measures the last
calendar-day window with the tape's arithmetic; the operator records
the printed yearly percent, history days and window days as evidence.
"""

import argparse
import json
import re
import sys
from datetime import date, timedelta
from decimal import Decimal, localcontext

from council.lib import canonical
from council.evidence import gate, tape

_TOOL_SUFFIX = "get_price_history"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class Refusal(Exception):
    """A plain-words reason the helper writes nothing."""


class _Number(str):
    """A figure that arrived in the reply as a JSON number, kept as the
    reply's own literal."""


def _texts(content):
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [block.get("text", "") for block in content
                if isinstance(block, dict) and block.get("type") == "text"]
    return []


def last_reply(transcript_path, contract):
    """The text of the last tool result answering a price-history call
    for `contract` (compared as text), or None. Refuses when that last
    result is marked as failed, before anything is read from it."""
    asked = {}
    reply = None
    failed = False
    with open(transcript_path, encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            message = record.get("message") if isinstance(record, dict) \
                else None
            content = message.get("content") \
                if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if (block.get("type") == "tool_use"
                        and str(block.get("name", "")).endswith(_TOOL_SUFFIX)):
                    wanted = (block.get("input") or {}).get("contract_id")
                    asked[block.get("id")] = str(wanted)
                elif (block.get("type") == "tool_result"
                        and asked.get(block.get("tool_use_id")) == contract):
                    reply = "".join(_texts(block.get("content")))
                    failed = bool(block.get("is_error"))
    if failed:
        raise Refusal("the last price-history reply for contract %s is "
                      "marked as failed, so nothing is read from it: %s"
                      % (contract, reply[:200]))
    return reply


def _is_date(text):
    if not _DATE.fullmatch(text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _date(stamp, index):
    day = stamp[:10] if isinstance(stamp, str) \
        and not isinstance(stamp, _Number) else None
    if day is None or not _is_date(day):
        raise Refusal("bar %d's time stamp %r does not begin with a date "
                      "written YYYY-MM-DD" % (index + 1, stamp))
    return day


def bars_from_reply(text, last_date=None):
    try:
        reply = json.loads(text, parse_float=_Number, parse_int=_Number)
    except ValueError:
        raise Refusal("the last reply for this contract is not a price "
                      "history - it does not read as the broker's answer: "
                      "%s" % text[:200])
    missing = [key for key in ("time", "close", "volume")
               if not isinstance(reply, dict)
               or not isinstance(reply.get(key), list)]
    if missing:
        raise Refusal("the last reply for this contract carries no %s "
                      "list - it is not a price history"
                      % " or ".join(missing))
    times, closes, volumes = reply["time"], reply["close"], reply["volume"]
    if not len(times) == len(closes) == len(volumes):
        raise Refusal("the reply's lists are not the same length: %d times, "
                      "%d closes, %d volumes - a bar would be matched to "
                      "another day's figure" % (len(times), len(closes),
                                                len(volumes)))
    bars = []
    for index, (stamp, close, volume) in enumerate(zip(times, closes,
                                                       volumes)):
        day = _date(stamp, index)
        for name, figure in (("close", close), ("volume", volume)):
            if not isinstance(figure, _Number):
                raise Refusal("bar %d (%s) has a %s that did not arrive as "
                              "a number: %r" % (index + 1, day, name,
                                                figure))
        if last_date is not None and day > last_date:
            continue
        bars.append({"date": day, "close": str(close),
                     "volume": str(volume)})
    return bars


def bars_from_coinmetrics(text, asset, last_date=None, *, calendar="CRYPTO_24_7"):
    """AC72: the saved community reply, closes only, exactly as observed."""
    try:
        reply = json.loads(text)
    except ValueError:
        raise Refusal("the daily-history reply is not an object with a data list")
    if not isinstance(reply, dict) or not isinstance(reply.get("data"), list):
        raise Refusal("the daily-history reply is not an object with a data list")
    pattern = gate.load_capture_schema()["properties"]["price_series"][
        "properties"]["bars"]["items"]["properties"]["close"]["pattern"]
    bars, previous = [], None
    for index, row in enumerate(reply["data"], 1):
        stamp = row.get("time") if isinstance(row, dict) else None
        day = stamp[:10] if isinstance(stamp, str) else "unknown date"
        hint = "row %d (%s)" % (index, day)
        if not _is_date(day):
            raise Refusal("%s has no real date written YYYY-MM-DD" % hint)
        if row.get("asset") != asset:
            raise Refusal("%s names asset %r rather than %s" % (hint, row.get("asset"), asset))
        close = row.get("PriceUSD")
        if (not isinstance(close, str) or re.fullmatch(pattern, close) is None
                or Decimal(close) <= 0):
            raise Refusal("%s has no price string above zero: %r" % (hint, close))
        current = date.fromisoformat(day)
        if previous is not None and current - previous != timedelta(days=1):
            raise Refusal("%s does not follow %s by exactly one calendar day" % (hint, previous))
        previous = current
        if last_date is None or day <= last_date:
            bars.append({"date": day, "close": close})
    floors = canonical.read_json(gate._FLOORS_PATH)
    # M5 defaults to all days; the CLI supplies its own declared calendar.
    capture = {"price_series": {"calendar": calendar}}
    needed = tape.bars_needed(tape.series_year_bars(capture, floors))
    if len(bars) < needed:
        raise Refusal("the daily history has %d rows on or before the last date; the tape needs %d"
                      % (len(bars), needed))
    return bars


def bars_from_sprott(text, label, last_date=None):
    """AC87(1), S1: whole quoted label, zero-based month, exact strings."""
    names = list(re.finditer(r"\bname\s*:\s*(['\"])" + re.escape(label) + r"\1\s*,", text))
    if len(names) != 1:
        raise Refusal("series label %r must occur exactly once; found %d" % (label, len(names)))
    header = re.match(r"\s*color\s*:\s*['\"][^'\"]+['\"]\s*,\s*lineWidth\s*:\s*\d+\s*,"
                      r"\s*marker\s*:\s*\{\s*radius\s*:\s*\d+\s*\}\s*,\s*data\s*:\s*\[",
                      text[names[0].end():])
    if header is None:
        raise Refusal("series label %r has no daily-pair array in the saved format" % label)
    start = names[0].end() + header.end()
    cursor, bars, previous = start, [], None
    pattern = gate.load_capture_schema()["properties"]["price_series"][
        "properties"]["bars"]["items"]["properties"]["close"]["pattern"]
    pair = re.compile(r"\s*\[Date\.UTC\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)\s*,\s*([^\]]+)\]")
    while True:
        match = pair.match(text, cursor)
        hint = "pair %d" % (len(bars) + 1)
        if match is None:
            raise Refusal("%s in series %r is not a daily date and decimal pair" % (hint, label))
        try:
            day = date(int(match[1]), int(match[2]) + 1, int(match[3])).isoformat()
        except ValueError:
            raise Refusal("%s has no real date: %s" % (hint, match.group(0)))
        close = match[4].strip()
        if re.fullmatch(pattern, close) is None or Decimal(close) <= 0:
            raise Refusal("%s (%s) has no decimal close above zero: %r" % (hint, day, close))
        if previous is not None and day <= previous:
            raise Refusal("%s (%s) does not follow %s in strictly rising dates" % (hint, day, previous))
        previous = day
        bars.append({"date": day, "close": close})
        cursor = match.end()
        tail = re.match(r"\s*([,\]])", text[cursor:])
        if tail is None:
            raise Refusal("%s (%s) has no next pair or array end" % (hint, day))
        cursor += tail.end()
        if tail[1] == "]":
            break
    return [b for b in bars if last_date is None or b["date"] <= last_date]


def swings_line(bars, days, calendar, floors):
    """AC87(1): calendar span, tape log returns and its calendar year."""
    if days <= 0:
        raise Refusal("--swings-days must be above zero")
    last = date.fromisoformat(bars[-1]["date"])
    history_days = (last - date.fromisoformat(bars[0]["date"])).days
    window_days = min(days, history_days)
    first = (last - timedelta(days=window_days)).isoformat()
    selected = [b for b in bars if b["date"] >= first]
    if len(selected) < 3:
        raise Refusal("the swings window needs at least three closes for sample daily returns")
    year = tape.series_year_bars({"price_series": {"calendar": calendar}}, floors)
    product = floors["archetype_measures"]["uranium_producer_rule"]["product"]
    rule = floors["asset_classes"]["commodity"]["products"][product]["rule"]
    with localcontext() as context:
        context.prec = tape.WORKING_PRECISION
        value = tape._realized_volatility(tape._Series({"ticker": "", "bars": selected}, year), len(selected) - 1)
        percent = Decimal(value[1]) * 100
    return ("swings: %s %s; %s %d; %s %d; %s to %s; %d bars; %s" % (
             percent, rule["roles"]["volatility"]["unit"], rule["swings"]["history_id"], history_days,
             rule["swings"]["window_id"], window_days,
             selected[0]["date"], selected[-1]["date"], len(selected), value[3]))


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stdout)
        print("series: %s" % message)
        raise SystemExit(1)


def main(argv=None):
    parser = _Parser(prog="python -m council.evidence.series",
                     description="Write a capture series block from the "
                                 "broker's price-history reply in a "
                                 "session transcript.")
    parser.add_argument("transcript", nargs="?")
    parser.add_argument("--coinmetrics")
    parser.add_argument("--sprott")
    parser.add_argument("--label")
    parser.add_argument("--swings-days", type=int)
    parser.add_argument("--asset")
    parser.add_argument("--contract")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--calendar", required=True)
    parser.add_argument("--as-of", required=True, dest="as_of")
    parser.add_argument("--source", required=True)
    parser.add_argument("--last-date", dest="last_date")
    parser.add_argument("--out", required=True)
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else 1
    try:
        if args.sprott:
            if args.transcript or args.coinmetrics or args.asset or args.contract or not args.label:
                raise Refusal("--sprott needs --label and no other input")
        elif bool(args.transcript) == bool(args.coinmetrics):
            raise Refusal("name exactly one input: a transcript or --coinmetrics")
        if args.coinmetrics and (not args.asset or args.contract):
            raise Refusal("--coinmetrics needs --asset and no --contract")
        if args.transcript and (not args.contract or args.asset):
            raise Refusal("a transcript needs --contract and no --asset")
        if args.last_date is not None and not _is_date(args.last_date):
            raise Refusal("--last-date %r is not a date written YYYY-MM-DD"
                          % args.last_date)
        if args.sprott:
            with open(args.sprott, encoding="utf-8") as handle:
                bars = bars_from_sprott(handle.read(), args.label, args.last_date)
        elif args.coinmetrics:
            with open(args.coinmetrics, encoding="utf-8") as handle:
                bars = bars_from_coinmetrics(handle.read(), args.asset, args.last_date,
                                             calendar=args.calendar)
        else:
            text = last_reply(args.transcript, str(args.contract))
            if text is None:
                raise Refusal("no price-history reply for contract %s in %s"
                              % (args.contract, args.transcript))
            bars = bars_from_reply(text, args.last_date)
        if not bars:
            raise Refusal("the reply carries no bar%s" % (
                "" if args.last_date is None
                else " dated on or before %s" % args.last_date))
        swings = swings_line(bars, args.swings_days, args.calendar,
                             canonical.read_json(gate._FLOORS_PATH)) if args.swings_days is not None else None
    except (Refusal, OSError) as refusal:
        print("series: refused - %s" % refusal)
        return 1
    canonical.write_canonical_json(args.out, {
        "ticker": args.ticker, "calendar": args.calendar,
        "source": args.source, "as_of": args.as_of, "bars": bars})
    print("series: %d bars, %s to %s -> %s"
          % (len(bars), bars[0]["date"], bars[-1]["date"], args.out))
    if swings is not None:
        print(swings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
