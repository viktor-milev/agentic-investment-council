"""The scenario-earned rating (ANCHORLESS-SPEC section 3, owner rulings
AB13.1 to AB13.3).

An asset with no earnings cannot be rated off the four canonical tests,
and the council that tries can only ever say hold - the Bitcoin cold
read's central finding, which the owner accepted. So the rating is
EARNED instead: the chairman publishes a ladder of named scenarios, each
with a price outcome and a probability that is the council's own
disciplined judgment, and the rating follows from whether the expected
result clears a risk-adjusted bar.

The division of labour here is deliberate. The LADDER is judgment and
belongs to the chairman: which scenarios, at what prices, with what
odds. The ARITHMETIC is not judgment and belongs to the machine: the
expected outcome, the annualised result, the bar, the band, and the
sensitivity are computed here, from the ladder and from PACK FACTS - the
five-year volatility and the cash rate are read from the frozen record,
never invented by a seat (AB13.3). That is what "no rating without its
arithmetic on the page" means in practice: the chairman cannot state a
rating his own ladder does not produce, and the page carries the sum.

Every figure the caller publishes comes back as a string, rounded once,
here. The band comparisons are made on those SAME rounded figures, so
the rating a reader can check by hand is the rating the machine gave:
there is no twelfth decimal deciding anything.
"""

from decimal import (Decimal, InvalidOperation, ROUND_HALF_UP,
                     localcontext)

# The five-word scale, weakest first - the mapping below is monotone in
# the expected result, and this order is what "the next rating down"
# means when the sensitivity is computed.
LADDER_RATINGS = ("sell", "hold", "buy", "strong_buy")

# Published precision. Percentages read to two decimals; the internal
# context is wide enough that the rounding happens exactly once, at the
# end, on figures that are already settled.
_PCT = Decimal("0.01")
_PRECISION = 34


class LadderError(ValueError):
    """The ladder cannot be turned into a rating, in plain words."""


def _decimal(text, what):
    try:
        value = Decimal(str(text).strip())
    except (InvalidOperation, AttributeError, TypeError):
        raise LadderError("%s is not a number the machine can read: %r"
                          % (what, text))
    if not value.is_finite():
        raise LadderError("%s is not a finite number: %r" % (what, text))
    return value


def _percent_fact(facts, fact_id, what):
    """A pack fact read as a percentage. The unit must SAY percent: a
    rate carried as a fraction and read as a percentage would move the
    bar by a factor of a hundred, and nothing downstream would notice."""
    fact = facts.get(fact_id)
    if fact is None:
        raise LadderError(
            "the ladder names '%s' as %s, but no such fact is in the "
            "frozen pack - the bar's inputs are pack facts, never seat "
            "inventions" % (fact_id, what))
    unit = str(fact.get("unit") or "")
    if "percent" not in unit.lower() and "%" not in unit:
        raise LadderError(
            "the ladder reads '%s' as %s, but the pack states its unit "
            "as '%s' - a rate must be carried in percent, or the bar is "
            "wrong by a factor of a hundred" % (fact_id, what, unit))
    return _decimal(fact.get("value"), "'%s'" % fact_id)


def _price_fact(facts, fact_id, what):
    fact = facts.get(fact_id)
    if fact is None:
        raise LadderError(
            "the ladder names '%s' as %s, but no such fact is in the "
            "frozen pack" % (fact_id, what))
    value = _decimal(fact.get("value"), "'%s'" % fact_id)
    if value <= 0:
        raise LadderError("'%s' is %s, and a price the ladder is measured "
                          "against must be above zero"
                          % (fact_id, fact.get("value")))
    return value


def _annualise(total_return, horizon_months):
    """A total return over the horizon, expressed as a yearly rate.
    Twelve months is the common case and is left exactly alone; any
    other horizon is compounded through the natural logarithm, which
    the decimal library computes to the context's precision and
    therefore identically on every machine."""
    if horizon_months == 12:
        return total_return
    growth = Decimal(1) + total_return
    if growth <= 0:
        # A total loss cannot be annualised: the yearly rate is -100%
        # however long the horizon, and saying so beats a crash.
        return Decimal(-1)
    exponent = Decimal(12) / Decimal(horizon_months)
    return (growth.ln() * exponent).exp() - Decimal(1)


def _total_for_annualised(annualised, horizon_months):
    """The inverse of _annualise: the total return over the horizon that
    would show up as this yearly rate."""
    if horizon_months == 12:
        return annualised
    growth = Decimal(1) + annualised
    if growth <= 0:
        return Decimal(-1)
    exponent = Decimal(horizon_months) / Decimal(12)
    return (growth.ln() * exponent).exp() - Decimal(1)


CONSTANT_KEYS = ("bar_volatility_multiple", "bar_scaling_step",
                 "buy_excess_multiple", "strong_buy_excess_multiple")


def constants(floors):
    """The four ruled constants, as decimals. They live in the floors
    data (ANCHORLESS-SPEC section 3: the scaling rule and the band
    arithmetic are fixed in DATA and stated in the verdict)."""
    block = floors.get("anchorless_rating")
    if not block:
        raise LadderError(
            "the floors file carries no anchorless_rating block, so the "
            "bar and its bands have no ruled constants - no rating could "
            "be earned, and the file must be fixed before any anchorless "
            "subject is judged")
    out = {}
    for key in CONSTANT_KEYS:
        if key not in block:
            raise LadderError(
                "the floors file's anchorless_rating block carries no "
                "'%s' - the rating bands cannot be computed without it"
                % key)
        out[key] = _decimal(block[key], "the ruled constant '%s'" % key)
    return out


def constant_texts(floors):
    """The same constants as the exact strings the floors file states -
    the prose quotes the ruled value as written, never a normalized
    rendering of it."""
    block = floors.get("anchorless_rating") or {}
    return {key: str(block.get(key)) for key in CONSTANT_KEYS}


def _edge(cash, volatility, ruled, excess_key):
    """One band's lower edge, rounded to the precision the page prints.

    Rounding the INPUTS and then comparing against an unrounded edge
    computed from them is the same defect one level deeper: the page
    could show a bar of 20.70 while the machine compared against
    25.5645, and a reader recomputing from the printed figures would
    reach a different rating (audit finding ANCHORLESS-C c2-1). Every
    figure in the comparison is the figure on the page."""
    return (cash + (ruled["bar_volatility_multiple"]
                    + ruled[excess_key]) * volatility
            ).quantize(_PCT, rounding=ROUND_HALF_UP)


def rating_for(annualised, cash, volatility, ruled):
    """The ruled mapping, monotone in the expected result: below cash is
    a sell; clearing cash without clearing the bar decisively is a hold;
    clearing it by the ruled margins earns buy and strong buy."""
    if annualised < cash:
        return "sell"
    if annualised >= _edge(cash, volatility, ruled,
                           "strong_buy_excess_multiple"):
        return "strong_buy"
    if annualised >= _edge(cash, volatility, ruled,
                           "buy_excess_multiple"):
        return "buy"
    return "hold"


def _thresholds(cash, volatility, ruled):
    """The lower edge of each band, weakest first, at the precision the
    page prints. `sell` has no lower edge; the others begin where the
    band below them ends."""
    return {
        "hold": cash,
        "buy": _edge(cash, volatility, ruled, "buy_excess_multiple"),
        "strong_buy": _edge(cash, volatility, ruled,
                            "strong_buy_excess_multiple"),
    }


def _pct(value):
    return str(value.quantize(_PCT, rounding=ROUND_HALF_UP))


def _plain(value):
    """A decimal without a trailing exponent, for prose."""
    text = format(value.normalize(), "f")
    return text


def check_shape(ladder, facts):
    """Every reason this ladder cannot earn a rating, in plain words.
    Empty list = the ladder is usable. Shape only: the arithmetic is
    `compute`."""
    reasons = []
    scenarios = ladder.get("scenarios") or []
    if len(scenarios) < 3:
        reasons.append(
            "the ladder carries %d scenario(s) - a ladder names at least "
            "three: a case where the thesis works, a case where it "
            "roughly holds, and a case where it fails"
            % len(scenarios))
    names = [str(item.get("name") or "").strip() for item in scenarios]
    for name in sorted({n for n in names if names.count(n) > 1}):
        reasons.append("two scenarios are both named %r - each rung of "
                       "the ladder carries its own name" % name)
    if any(not name for name in names):
        reasons.append("a scenario carries no name - every rung is named, "
                       "so the reader can see what it assumes")
    total = Decimal(0)
    prices = []
    for index, item in enumerate(scenarios):
        label = str(item.get("name") or "#%d" % (index + 1))
        try:
            probability = _decimal(item.get("probability"),
                                   "the probability of %r" % label)
            price = _decimal(item.get("price_outcome"),
                             "the price outcome of %r" % label)
        except LadderError as failure:
            reasons.append(str(failure))
            continue
        if probability <= 0 or probability >= 1:
            reasons.append(
                "the probability of %r is %s - every scenario carries a "
                "probability strictly between 0 and 1; a certainty is not "
                "a scenario" % (label, item.get("probability")))
        if price <= 0:
            reasons.append("the price outcome of %r is %s, and a price "
                           "outcome must be above zero"
                           % (label, item.get("price_outcome")))
        total += probability
        prices.append(price)
        if not str(item.get("rationale") or "").strip():
            reasons.append("the scenario %r carries no rationale - one "
                           "sentence saying why this outcome, or the rung "
                           "is a number from nowhere" % label)
    if scenarios and total != Decimal(1):
        reasons.append(
            "the scenario probabilities add to %s, not 1 - a ladder that "
            "does not add up cannot produce an expected result"
            % _plain(total))
    horizon = ladder.get("horizon_months")
    try:
        months = int(str(horizon))
    except (TypeError, ValueError):
        months = 0
        reasons.append("the ladder's horizon is %r - state it as a whole "
                       "number of months, because every figure below is "
                       "annualised from it" % horizon)
    if months and (months < 1 or months > 120):
        reasons.append("the ladder's horizon is %d months - state a "
                       "horizon between 1 and 120 months" % months)
    reference_id = ladder.get("reference_price_fact_id")
    if prices and reference_id in facts:
        try:
            reference = _price_fact(facts, reference_id,
                                    "the price the ladder is measured "
                                    "against")
        except LadderError as failure:
            reasons.append(str(failure))
        else:
            if not any(price > reference for price in prices):
                reasons.append(
                    "no scenario prices the asset above %s, the price the "
                    "ladder is measured against - a ladder with no upside "
                    "rung has not been built, it has been assumed"
                    % _plain(reference))
            if not any(price < reference for price in prices):
                reasons.append(
                    "no scenario prices the asset below %s, the price the "
                    "ladder is measured against - a ladder with no "
                    "downside rung has not been built, it has been assumed"
                    % _plain(reference))
    return reasons


def compute(ladder, facts, floors):
    """The whole arithmetic of the rating, from the chairman's ladder and
    the frozen pack. Raises LadderError with a plain reason where the
    ladder cannot produce a rating at all."""
    with localcontext() as context:
        context.prec = _PRECISION
        return _compute(ladder, facts, floors)


def _compute(ladder, facts, floors):
    ruled = constants(floors)
    shape = check_shape(ladder, facts)
    if shape:
        raise LadderError(shape[0])
    months = int(str(ladder["horizon_months"]))
    reference = _price_fact(facts, ladder["reference_price_fact_id"],
                            "the price the ladder is measured against")
    # The reference price is a FROZEN FACT, so it is quoted exactly as
    # the pack states it - 60000.00 stays 60000.00. Only figures this
    # module computes are rendered in its own normalized form.
    reference_text = str(
        facts[ladder["reference_price_fact_id"]]["value"]).strip()
    # Rounded HERE, once, before anything is compared: the module's
    # promise is that the bands are judged on the same figures the page
    # prints, and cash and volatility are printed to two decimals. Left
    # unrounded they set a hidden threshold, so a reader recomputing
    # from the page could reach a different rating than the machine did
    # (audit finding ANCHORLESS-B r1-5).
    volatility = _percent_fact(
        facts, ladder["volatility_fact_id"],
        "the asset's five-year realized volatility").quantize(_PCT, rounding=ROUND_HALF_UP)
    cash = _percent_fact(facts, ladder["cash_rate_fact_id"],
                         "the cash rate the bar starts at").quantize(_PCT, rounding=ROUND_HALF_UP)
    if volatility <= 0:
        raise LadderError(
            "the five-year volatility reads %s - the bar is cash plus a "
            "premium scaled to it, and a volatility of zero would ask the "
            "asset to beat cash by nothing" % _plain(volatility))

    rungs = []
    expected_price = Decimal(0)
    for item in ladder["scenarios"]:
        probability = _decimal(item["probability"], "a probability")
        price = _decimal(item["price_outcome"], "a price outcome")
        expected_price += probability * price
        # The chairman's own strings travel into the prose beside the
        # decimals: a probability he wrote as 0.30 is quoted as 0.30.
        rungs.append((str(item["name"]).strip(), probability, price,
                      str(item["probability"]).strip(),
                      str(item["price_outcome"]).strip()))

    total_return = expected_price / reference - Decimal(1)
    annualised = _annualise(total_return, months) * Decimal(100)
    annualised = annualised.quantize(_PCT, rounding=ROUND_HALF_UP)
    bar = (cash + ruled["bar_volatility_multiple"] * volatility
           ).quantize(_PCT, rounding=ROUND_HALF_UP)
    rating = rating_for(annualised, cash, volatility, ruled)
    excess = (annualised - bar).quantize(_PCT, rounding=ROUND_HALF_UP)

    return {
        "rating": rating,
        "horizon_months": str(months),
        "reference_price": reference_text,
        "reference_price_fact_id": ladder["reference_price_fact_id"],
        "expected_price": _plain(expected_price),
        "expected_total_pct": _pct(total_return * Decimal(100)),
        "expected_annualised_pct": str(annualised),
        "cash_pct": _pct(cash),
        "cash_rate_fact_id": ladder["cash_rate_fact_id"],
        "volatility_pct": _pct(volatility),
        "volatility_fact_id": ladder["volatility_fact_id"],
        "bar_pct": str(bar),
        "excess_over_bar_pp": str(excess),
        "constants": {key: _plain(value) for key, value in ruled.items()},
        "arithmetic": _arithmetic(rungs, expected_price, reference_text,
                                  total_return, annualised, months, cash,
                                  volatility, bar, ruled, rating,
                                  constant_texts(floors)),
        "sensitivity": _sensitivity(rungs, expected_price, reference,
                                    months, cash, volatility, ruled,
                                    rating),
    }


def _arithmetic(rungs, expected_price, reference_text, total_return,
                annualised, months, cash, volatility, bar, ruled, rating,
                texts):
    """The sum, written out, in the order a reader would check it. These
    sentences ARE the 'arithmetic on the page' the ruling requires."""
    weighted = " plus ".join(
        "%s of %s" % (probability_text, price_text)
        for _name, _p, _price, probability_text, price_text in rungs)
    lines = [
        "The ladder's expected outcome is %s: %s."
        % (_plain(expected_price), weighted),
        "Against %s on the record that is %s%% over %d month(s), or "
        "%s%% a year."
        % (reference_text, _pct(total_return * Decimal(100)), months,
           str(annualised)),
        "The bar is cash at %s%% plus %s times the asset's own five-year "
        "volatility of %s%%, which is %s%%."
        % (_pct(cash), texts["bar_volatility_multiple"],
           _pct(volatility), str(bar)),
    ]
    if rating == "sell":
        lines.append(
            "%s%% a year is below cash at %s%%: the expected result loses "
            "against a Treasury bill, so the rating is sell."
            % (str(annualised), _pct(cash)))
    elif rating == "hold":
        lines.append(
            "%s%% a year clears cash at %s%% but not the bar at %s%% by "
            "the ruled margin of %s times volatility: it beats cash "
            "without paying for the risk taken, so the rating is hold."
            % (str(annualised), _pct(cash), str(bar),
               texts["buy_excess_multiple"]))
    else:
        needed = ruled["buy_excess_multiple"]
        needed_text = texts["buy_excess_multiple"]
        word = "buy"
        if rating == "strong_buy":
            needed = ruled["strong_buy_excess_multiple"]
            needed_text = texts["strong_buy_excess_multiple"]
            word = "strong buy"
        lines.append(
            "%s%% a year clears the bar at %s%% by more than the ruled "
            "%s times volatility (%s%%), so the rating is %s."
            % (str(annualised), str(bar), needed_text,
               _pct(needed * volatility), word))
    return lines


_FLIP_STEP = Decimal("0.001")


def _rating_at(probability_of_worst, rest, worst_price, reference, months,
               cash, volatility, ruled):
    """The rating this ladder would earn if the worst rung carried this
    probability and the others kept their odds relative to each other."""
    expected = (worst_price * probability_of_worst
                + rest * (Decimal(1) - probability_of_worst))
    annualised = (_annualise(expected / reference - Decimal(1), months)
                  * Decimal(100)).quantize(_PCT, rounding=ROUND_HALF_UP)
    return rating_for(annualised, cash, volatility, ruled)


def _landed_flip(crossing, now, rest, worst_price, reference, months,
                 cash, volatility, ruled, rating):
    """The published flip probability: the crossing rounded to three
    decimals AWAY from the band it leaves, and then stepped until the
    recomputed rating has actually changed. None where no probability in
    range moves it - said plainly rather than printed as a figure that
    does nothing."""
    direction = _FLIP_STEP if crossing > now else -_FLIP_STEP
    rounding = "ROUND_CEILING" if direction > 0 else "ROUND_FLOOR"
    landed = crossing.quantize(_FLIP_STEP, rounding=rounding)
    for _ in range(50):
        if landed < Decimal(0) or landed > Decimal(1):
            return None
        if _rating_at(landed, rest, worst_price, reference, months, cash,
                      volatility, ruled) != rating:
            return landed
        landed += direction
    return None


def _sensitivity(rungs, expected_price, reference, months, cash,
                 volatility, ruled, rating):
    """How the rating moves as the bar and the probabilities move - the
    ruling requires this printed EVERY time (AB13.2). Two dials, both
    honest: the odds of the worst case, and the bar itself.

    The probability dial turns ONE number - the chance of the worst rung
    - and keeps the other rungs' odds relative to each other. The
    expected outcome falls as that dial is turned up, so the point where
    the rating changes is a single crossing, computed rather than
    searched for."""
    edges = _thresholds(cash, volatility, ruled)
    index = LADDER_RATINGS.index(rating)
    if index == 0:
        target, direction = LADDER_RATINGS[1], "up to"
        edge = edges[LADDER_RATINGS[1]]
    else:
        target, direction = LADDER_RATINGS[index - 1], "down to"
        edge = edges[rating]

    worst_index = min(range(len(rungs)), key=lambda i: rungs[i][2])
    worst_name, worst_probability, worst_price, worst_text, _pt = \
        rungs[worst_index]
    others = [(p, price) for i, (_n, p, price, _t, _u) in enumerate(rungs)
              if i != worst_index]
    remaining = sum((p for p, _price in others), Decimal(0))
    flip = {"scenario": worst_name,
            "probability_now": worst_text,
            "flips_to": target,
            "direction": direction,
            "probability_at_flip": None,
            "sentence": None}
    if remaining > 0:
        rest = sum((p * price for p, price in others), Decimal(0)) / remaining
        # The expected outcome the boundary demands, then the probability
        # of the worst rung that would produce it. Linear in one dial, so
        # the crossing point is arithmetic, never a search.
        wanted_total = _total_for_annualised(edge / Decimal(100), months)
        wanted_price = reference * (Decimal(1) + wanted_total)
        denominator = worst_price - rest
        if denominator != 0:
            crossing = (wanted_price - rest) / denominator
            if Decimal(0) <= crossing <= Decimal(1):
                # The published probability must ACTUALLY flip the
                # rating when a reader applies it. The exact crossing
                # sits ON an inclusive band edge, and rounding it to
                # three decimals can land it back inside the band it was
                # meant to leave - the page would then print a figure
                # that changes nothing (audit finding ANCHORLESS-B
                # r1-6). Round AWAY from the current band, then step
                # until the recomputed rating has genuinely moved.
                landed = _landed_flip(crossing, worst_probability, rest,
                                      worst_price, reference, months,
                                      cash, volatility, ruled, rating)
                if landed is not None:
                    flip["probability_at_flip"] = str(landed)
                    # Raising the worst case's odds lowers the rating and
                    # lowering them raises it: the verb follows which way
                    # the crossing actually lies, never the band's name.
                    verb = ("rises" if landed > worst_probability
                            else "falls")
                    flip["sentence"] = (
                        "The rating moves %s %s if the chance of %r %s "
                        "from %s to %s."
                        % (direction, target.replace("_", " "), worst_name,
                           verb, worst_text, str(landed)))
    if flip["sentence"] is None:
        flip["sentence"] = (
            "No probability for %r between 0 and 1 moves the rating %s "
            "%s: on this ladder the rating does not turn on that one "
            "chance alone."
            % (worst_name, direction, target.replace("_", " ")))

    step = ruled["bar_scaling_step"]
    steps = []
    for label, multiple in (
            ("one step lower",
             ruled["bar_volatility_multiple"] - step),
            ("as ruled", ruled["bar_volatility_multiple"]),
            ("one step higher",
             ruled["bar_volatility_multiple"] + step)):
        stepped_ruled = dict(ruled)
        stepped_ruled["bar_volatility_multiple"] = multiple
        total_return = expected_price / reference - Decimal(1)
        annualised = (_annualise(total_return, months)
                      * Decimal(100)).quantize(_PCT, rounding=ROUND_HALF_UP)
        steps.append({
            "label": label,
            "volatility_multiple": _plain(multiple),
            "bar_pct": _pct(cash + multiple * volatility),
            "rating": rating_for(annualised, cash, volatility,
                                 stepped_ruled)})
    return {"flip": flip, "bar_steps": steps,
            "step_size": _plain(step),
            "sentence": ("The bar is a ruled constant, not a law: at one "
                         "scaling step either side of it the rating "
                         "reads %s, %s and %s."
                         % tuple(entry["rating"].replace("_", " ")
                                 for entry in steps))}
