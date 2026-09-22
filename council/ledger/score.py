"""Score the ledger against what happened (UPGRADE-2 U7.2, U7.3).

    python -m council.ledger.score <ledger.jsonl> <observations.json> [-o out]

The observation file is captured by a session the way evidence is: for each
due horizon the subject's close and the benchmark's close, each an exact
string with a source and an as-of date; the published figure for each
falsifier with the session's three-way resolution; and whether each
tripwire and named trigger fired. THIS SCRIPT NEVER FETCHES. It reads the
figures the session recorded and applies the scoring rules that live as
DATA in council/floors/scoring-rules.json (owner ruling AC7):

  - excess return at a horizon = subject return minus benchmark return,
    or the subject's own return where the class has no benchmark;
  - right or wrong per rating word at 252 trading days;
  - the mispricing read scored by direction against the 252-day excess;
  - falsifiers tallied for / against / unresolved as the session resolved
    them; tripwires and triggers tallied as fired or not.

It writes a scored file (default: scored.json beside the ledger) that the
scorecard renders, and prints a plain summary.
"""

import datetime
import decimal
import json
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, validate  # noqa: E402
from council.ledger import ledger  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBSERVATION_SCHEMA = os.path.join(
    ROOT, "council", "schemas", "observation_schema.json")

SCORED_VERSION = "1.0.0"


def _num(text):
    if text is None:
        return None
    try:
        return decimal.Decimal(str(text).strip())
    except (decimal.InvalidOperation, ValueError):
        return None


_PREC_MARGIN = 12


def _exact_prec(*values):
    """A working precision wide enough that arithmetic here never rounds away
    the precision the operands themselves carry before a right/wrong threshold
    rides on the result: the significant digits of every operand, plus a
    margin, and never below Decimal's default. Without it a close given to more
    than 28 significant figures is rounded onto the bar before the excess it
    feeds is compared (audit round 8 finding r8-2, extending r7-4)."""
    digits = sum(len(value.as_tuple().digits) for value in values)
    return max(digits + _PREC_MARGIN, decimal.getcontext().prec)


def _return_pct(close, base):
    """Per-cent change from base to close, or None when either is missing
    or the base is zero. The division runs at a precision derived from the
    operands, so a long-but-exact close is not rounded before the excess it
    feeds is compared to a threshold."""
    close, base = _num(close), _num(base)
    if close is None or base is None or base == 0:
        return None
    with decimal.localcontext() as context:
        context.prec = _exact_prec(close, base)
        return (close / base - 1) * 100


def _as_float(value):
    return None if value is None else float(value)


def load_observations(path):
    """Accept a single observation object, a list of them, or
    {"observations": [...]}. Returns a list."""
    doc = canonical.read_json(path)
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict) and "observations" in doc:
        return doc["observations"]
    return [doc]


def _validate_observations(observations):
    schema = canonical.read_json(OBSERVATION_SCHEMA)
    problems = []
    for index, obs in enumerate(observations):
        errors = validate.validate(obs, schema)
        if errors:
            problems.append("observation %d (%s):\n    %s" % (
                index, obs.get("ledger_row_id", "?"),
                "\n    ".join(errors)))
    return problems


def _unit_mismatch(a, b):
    """`a` is the baseline (the row's own) unit, `b` the observed one. A known
    baseline unit demands a matching observed unit: a priced-per-share baseline
    against an observed close with no unit, or with a different unit, is not a
    real return, so the horizon reads incomplete, not scored. A baseline whose
    unit could not be resolved (None) can verify nothing about the observed
    close, so it never agrees: r7-1 binds an anchorless baseline's unit from
    its reference fact, so a None baseline unit means that fact was ABSENT
    (audit round 8 finding r8-1, extended by U7b finding P-U7-9). The horizon
    then reads incomplete whatever the observed unit, INCLUDING an observed
    close that is itself unitless - two nulls do not agree when the baseline
    null is an unresolved unit, never a verified one. Only a resolved baseline
    unit equal to the observed unit scores."""
    return a is None or a != b


def _score_horizon(row, horizon_obs):
    """One horizon's returns, as `(display, exact_excess)`. `display` carries
    the serialized figures (floats, for the scorecard); `exact_excess` is the
    exact Decimal excess a right/wrong rule is compared against, or None when
    the horizon has no excess - so a threshold decision is never taken on a
    float-rounded figure (a value just below a bar must not read as on it).
    Each leg is computed on its own. Absolute where the row's class has no
    benchmark (the subject return is the excess); absolute with the excess left
    null where the class expects a benchmark but the pack carries no level for
    it (the subject return is still recorded, and the benchmark unit check does
    not run); excess where the benchmark level and its observed close are both
    on file; incomplete where the observed close and the baseline it is
    measured against carry different or unverifiable units, or a needed return
    cannot be computed."""
    incomplete = ({"subject_return_pct": None, "benchmark_return_pct": None,
                   "excess_pct": None, "basis": "incomplete"}, None)
    price_info = row.get("price_at_verdict") or {}
    subject_close = horizon_obs.get("subject_close") or {}
    if _unit_mismatch(price_info.get("unit"), subject_close.get("unit")):
        return incomplete
    subject_return = _return_pct(subject_close.get("value"),
                                 price_info.get("value"))
    benchmark = row.get("benchmark")
    if not benchmark:
        # No benchmark by asset class: the product is scored on its own
        # return, which IS the excess the rating rules are compared against.
        return ({"subject_return_pct": _as_float(subject_return),
                 "benchmark_return_pct": None,
                 "excess_pct": _as_float(subject_return),
                 "basis": "absolute" if subject_return is not None
                 else "incomplete"}, subject_return)
    if benchmark.get("level_at_verdict") is None:
        # A benchmark is expected by asset class but the pack carries no level
        # for it. The subject's own return is still recorded; with no level to
        # measure against, the excess is left uncomputed. The benchmark unit
        # check does NOT run here, so a benchmark close in the capture cannot
        # erase the subject leg.
        return ({"subject_return_pct": _as_float(subject_return),
                 "benchmark_return_pct": None,
                 "excess_pct": None,
                 "basis": "absolute" if subject_return is not None
                 else "incomplete"}, None)
    bench_obs = horizon_obs.get("benchmark_close") or {}
    if _unit_mismatch(benchmark.get("unit"), bench_obs.get("unit")):
        return incomplete
    benchmark_return = _return_pct(
        bench_obs.get("value"), benchmark.get("level_at_verdict"))
    if subject_return is None or benchmark_return is None:
        return ({"subject_return_pct": _as_float(subject_return),
                 "benchmark_return_pct": _as_float(benchmark_return),
                 "excess_pct": None, "basis": "incomplete"}, None)
    with decimal.localcontext() as context:
        context.prec = _exact_prec(subject_return, benchmark_return)
        excess = subject_return - benchmark_return
    return ({"subject_return_pct": _as_float(subject_return),
             "benchmark_return_pct": _as_float(benchmark_return),
             "excess_pct": _as_float(excess), "basis": "excess"}, excess)


def _test(excess_pct, test, threshold_pct):
    if excess_pct is None:
        return None
    excess = decimal.Decimal(str(excess_pct))
    threshold = decimal.Decimal(str(threshold_pct))
    if test == "ge":
        return excess >= threshold
    if test == "gt":
        return excess > threshold
    if test == "lt":
        return excess < threshold
    if test == "abs_le":
        return abs(excess) <= threshold
    return None


def _mispricing_correct(read, excess_pct, rules):
    rule = (rules.get("mispricing_direction") or {}).get(read)
    if rule is None:
        return None
    return _test(excess_pct, rule["test"], rule["threshold_pct"])


def _is_iso_date(text):
    """True only for a real calendar date written YYYY-MM-DD. A malformed
    value such as 0000-00-00 is not one, so it cannot be shown to fall within
    a window - the lexical comparison alone would wrongly accept it."""
    try:
        datetime.date.fromisoformat(text)
        return True
    except (TypeError, ValueError):
        return False


def _fired_within(events, due_date, allowed_details=None, verdict_date=None):
    """The fired events within the window that opens at the verdict and closes
    on the due date. An event with no date, a date that is not a real calendar
    date, a date after the due date, or - when `verdict_date` is given - a date
    BEFORE the verdict, does NOT count: it cannot be shown to have fired within
    the post-verdict window, and a trigger dated before the ruling fired before
    the call was even made. When `allowed_details` is given, only an event
    whose detail names one of those declared markers counts: U7.3 scores a
    monitor on whether a NAMED reopening trigger fired, not on any event the
    observation happens to carry."""
    fired = []
    for event in events:
        if not event.get("fired"):
            continue
        if allowed_details is not None \
                and event.get("detail") not in allowed_details:
            continue
        date = event.get("date")
        if date is None or not _is_iso_date(date) or not due_date \
                or date > due_date:
            continue
        if verdict_date and _is_iso_date(verdict_date) and date < verdict_date:
            continue
        fired.append({"detail": event.get("detail"), "date": date})
    return fired


def _due_date(row, trading_days):
    for horizon in row.get("horizons", []):
        if horizon.get("trading_days") == trading_days:
            return horizon.get("due_date")
    return None


def _rating_outcome(row, obs, horizons_by_days, exact_by_days, rules):
    """Right / wrong / None at the scoring horizon, per rating word. Rule
    comparisons use the EXACT Decimal excess (`exact_by_days`); the serialized
    `excess_pct` stays the display float, so a threshold decision never rides on
    a rounded figure."""
    scored_days = rules["scoring_horizon_trading_days"]
    rule = (rules.get("rating_rules") or {}).get(row.get("rating"))
    horizon = horizons_by_days.get(scored_days)
    display_excess = horizon.get("excess_pct") if horizon else None
    excess = exact_by_days.get(scored_days)
    has_252 = horizon is not None and excess is not None
    result = {"scored_horizon_trading_days": scored_days,
              "rating": row.get("rating"), "has_252_outcome": has_252,
              "excess_pct": display_excess, "correct": None, "reason": None}
    if rule is None:
        result["reason"] = "no rule for this rating word"
        return result
    kind = rule["kind"]
    if kind == "excess":
        result["correct"] = _test(excess, rule["test"], rule["threshold_pct"])
        result["reason"] = "252-day excess %s %s%%" % (
            rule["test"], rule["threshold_pct"])
    elif kind == "hold":
        band = _test(excess, "abs_le", rule["band_pct"])
        direction = _mispricing_correct(
            (row.get("mispricing") or {}).get("read"), excess, rules)
        if band is None and direction is None:
            result["correct"] = None
        else:
            result["correct"] = bool(band) or bool(direction)
        result["reason"] = ("|252-day excess| <= %s%% or the mispricing "
                            "read's direction was right" % rule["band_pct"])
    elif kind == "trigger_within":
        names = [t.get("detail")
                 for t in (row.get("reopening_triggers") or [])]
        fired = _fired_within(obs.get("trigger_events", []) if obs else [],
                              _due_date(row, rule["trading_days"]),
                              allowed_details=names,
                              verdict_date=row.get("verdict_date"))
        window_closed = bool(fired) or any(
            h.get("trading_days") == scored_days
            for h in (obs.get("horizon_observations", []) if obs else []))
        result["correct"] = (True if fired
                             else False if window_closed else None)
        result["has_252_outcome"] = window_closed
        result["excess_pct"] = None
        result["reason"] = ("a named reopening trigger fired within %d "
                            "trading days" % rule["trading_days"])
        result["triggers_fired"] = fired
    return result


def score_row(row, obs, rules):
    horizons = []
    horizons_by_days = {}
    exact_by_days = {}
    obs_by_days = {}
    for horizon_obs in (obs.get("horizon_observations", []) if obs else []):
        obs_by_days[horizon_obs.get("trading_days")] = horizon_obs
    for horizon in row.get("horizons", []):
        days = horizon.get("trading_days")
        horizon_obs = obs_by_days.get(days)
        scored = {"trading_days": days, "due_date": horizon.get("due_date")}
        exact = None
        if horizon_obs is None:
            scored.update({"subject_return_pct": None,
                           "benchmark_return_pct": None,
                           "excess_pct": None, "basis": "pending"})
        else:
            display, exact = _score_horizon(row, horizon_obs)
            scored.update(display)
        horizons.append(scored)
        horizons_by_days[days] = scored
        exact_by_days[days] = exact
    falsifiers = {"for": 0, "against": 0, "unresolved": 0}
    for observed in (obs.get("falsifier_observations", []) if obs else []):
        resolved = observed.get("resolved")
        if resolved in falsifiers:
            falsifiers[resolved] += 1
    tripwires_fired = _fired_within(
        obs.get("tripwire_events", []) if obs else [],
        _due_date(row, rules["scoring_horizon_trading_days"]),
        verdict_date=row.get("verdict_date"))
    outcome = _rating_outcome(row, obs, horizons_by_days, exact_by_days, rules)
    return {
        "ledger_row_id": row.get("ledger_row_id"),
        "run_id": row.get("run_id"),
        "subject": row.get("subject"),
        "asset_class": row.get("asset_class"),
        "verdict_date": row.get("verdict_date"),
        "rating": row.get("rating"),
        "observed": obs is not None,
        "horizons": horizons,
        "rating_outcome": outcome,
        "mispricing": {
            "read": (row.get("mispricing") or {}).get("read"),
            "correct": _mispricing_correct(
                (row.get("mispricing") or {}).get("read"),
                exact_by_days.get(rules["scoring_horizon_trading_days"]),
                rules)},
        "falsifiers": falsifiers,
        "tripwires_fired": tripwires_fired,
    }


def _within_close_window(due_date, as_of, rules):
    """True when a close observed on `as_of` may score a horizon that came due
    on `due_date`: on the due date, up to `close_window_days_after_due`
    calendar days after it, and no earlier than `close_days_before_due_allowed`
    days before it (0 by default). A close outside that window is hindsight or
    premature, not the horizon's outcome. Both dates must be real calendar
    dates; a malformed one is never within the window."""
    if not (_is_iso_date(due_date) and _is_iso_date(as_of)):
        return False
    delta_days = (datetime.date.fromisoformat(as_of)
                  - datetime.date.fromisoformat(due_date)).days
    before = rules.get("close_days_before_due_allowed", 0)
    after = rules.get("close_window_days_after_due", 5)
    return -before <= delta_days <= after


def _check_horizons(row, obs, rules):
    """Every horizon the observation carries must be one the row declares,
    dated to the row's due date, and scored from a close struck within the
    ruled window around that due date. A wrong or duplicated horizon date, or
    a close observed outside the window, would score a close against the wrong
    window (a 2028 close read as the 252-day reading for a 2027 due date is
    hindsight, not an outcome)."""
    row_due = {h.get("trading_days"): h.get("due_date")
               for h in row.get("horizons", [])}
    seen = set()
    for horizon_obs in obs.get("horizon_observations", []):
        days = horizon_obs.get("trading_days")
        if days in seen:
            raise ValueError(
                "the observation for ledger row %r carries two %s-day "
                "horizons" % (row.get("ledger_row_id"), days))
        seen.add(days)
        if days not in row_due:
            raise ValueError(
                "the observation for ledger row %r carries a %s-day horizon "
                "the row does not" % (row.get("ledger_row_id"), days))
        if horizon_obs.get("due_date") != row_due[days]:
            raise ValueError(
                "the observation for ledger row %r dates its %s-day horizon "
                "%r but the row's due date is %r"
                % (row.get("ledger_row_id"), days,
                   horizon_obs.get("due_date"), row_due[days]))
        due_date = row_due[days]
        for which, close in (("subject", horizon_obs.get("subject_close")),
                             ("benchmark", horizon_obs.get("benchmark_close"))):
            if not close:
                continue
            if not _within_close_window(due_date, close.get("as_of"), rules):
                raise ValueError(
                    "the observation for ledger row %r scores its %s-day "
                    "horizon due %r from a %s close observed %r, outside the "
                    "window (the due date to %s calendar days after it)"
                    % (row.get("ledger_row_id"), days, due_date, which,
                       close.get("as_of"),
                       rules.get("close_window_days_after_due", 5)))
        subject_close = horizon_obs.get("subject_close")
        benchmark_close = horizon_obs.get("benchmark_close")
        if subject_close and benchmark_close:
            subject_as_of = subject_close.get("as_of")
            benchmark_as_of = benchmark_close.get("as_of")
            if subject_as_of != benchmark_as_of:
                raise ValueError(
                    "the observation for ledger row %r scores its %s-day "
                    "horizon from a subject close observed %r and a benchmark "
                    "close observed %r; an excess return is one window, so the "
                    "two closes must be struck on the same session (one as-of "
                    "date)"
                    % (row.get("ledger_row_id"), days,
                       subject_as_of, benchmark_as_of))


def _bind_observations(rows, observations, rules):
    """Bind each observation to exactly one ledger row before scoring. The
    observation file is captured by a session and is UNTRUSTED (U7.2 'the
    gate validates it'), so a mis-filed, duplicated or wrongly-dated
    observation is REFUSED loudly, never silently mis-scored or dropped."""
    rows_by_id = {row.get("ledger_row_id"): row for row in rows}
    obs_by_row = {}
    for obs in observations:
        row_id = obs.get("ledger_row_id")
        if row_id in obs_by_row:
            raise ValueError(
                "two observations name ledger row %r; each row is "
                "observed once" % row_id)
        target = rows_by_id.get(row_id)
        if target is None:
            raise ValueError(
                "an observation names ledger row %r, which is not in the "
                "ledger" % row_id)
        if obs.get("run_id") != target.get("run_id"):
            raise ValueError(
                "the observation for ledger row %r names run %r but the "
                "row's run is %r" % (row_id, obs.get("run_id"),
                                     target.get("run_id")))
        _check_horizons(target, obs, rules)
        obs_by_row[row_id] = obs
    return obs_by_row


def score(ledger_path, observations_path, rules=None):
    """Return the scored document. Raises ValueError on an invalid
    observation file."""
    rules = rules or ledger.load_rules()
    rows = ledger.confirmed_rows(ledger.read_rows(ledger_path))
    observations = load_observations(observations_path)
    problems = _validate_observations(observations)
    if problems:
        raise ValueError("the observation file is not valid:\n  "
                         + "\n  ".join(problems))
    obs_by_row = _bind_observations(rows, observations, rules)
    scored_rows = [score_row(row, obs_by_row.get(row.get("ledger_row_id")),
                             rules) for row in rows]
    return {"scored_version": SCORED_VERSION,
            "scoring_rules_version": rules.get("scoring_rules_version"),
            "scoring_horizon_trading_days":
                rules["scoring_horizon_trading_days"],
            "rows": scored_rows}


def _summary_lines(scored):
    lines = []
    rows = scored["rows"]
    observed = [r for r in rows if r["observed"]]
    with_252 = [r for r in rows if r["rating_outcome"]["has_252_outcome"]]
    correct = [r for r in with_252 if r["rating_outcome"]["correct"] is True]
    lines.append("ledger rows: %d; with observations: %d; with a 252-day "
                 "outcome: %d" % (len(rows), len(observed), len(with_252)))
    if with_252:
        lines.append("right at 252 trading days: %d of %d"
                     % (len(correct), len(with_252)))
    return lines


def main(argv):
    out = None
    positional = []
    index = 0
    while index < len(argv):
        if argv[index] == "-o" and index + 1 < len(argv):
            out = argv[index + 1]
            index += 2
            continue
        positional.append(argv[index])
        index += 1
    if len(positional) != 2:
        print(__doc__)
        return 2
    ledger_path, observations_path = positional
    try:
        scored = score(ledger_path, observations_path)
    except ValueError as error:
        print("REFUSED: %s" % error)
        return 1
    if out is None:
        out = os.path.join(os.path.dirname(os.path.abspath(ledger_path)),
                           "scored.json")
    canonical.write_canonical_json(out, scored)
    for line in _summary_lines(scored):
        print(line)
    print("scored file written to %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
