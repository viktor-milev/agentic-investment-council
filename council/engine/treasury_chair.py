"""Owner rulings AC92(1)-(2): the treasury ladder and the chairman's read.
The evidence reader owns the figures; all ruled words and limits are data.
"""

from copy import deepcopy
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from fractions import Fraction

from council.evidence import gate, sufficiency
from council.engine import ladder
from council.lib import canonical, subjects


def _rule(floors=None):
    if floors is None:
        floors = canonical.read_json(str(Path(__file__).resolve().parents[1] / "floors" / "floors.json"))
    return floors["archetype_measures"]["holding_rule"]["treasury"]


def declared(pack, floors):
    """M1: the evidence reader's declaration, from the ruled day only."""
    capture = (pack or {}).get("capture") or {}
    pair = sufficiency.treasury_frame(floors, capture) if capture.get("subject") else None
    return pair if pair and date.fromisoformat(capture["captured_at"][:10]) >= date.fromisoformat(_rule(floors)["applies_from"]) else None


def ladder_rated(subject, pack, floors):
    from council.engine import preferred_chair
    return subjects.is_anchorless(subject) or declared(pack, floors) is not None or preferred_chair.declared(pack, floors) is not None


def coin_on_record(runs_root, coin, floors):
    """M2: read verdicts alone, newest publication first, any contract."""
    found = []
    for path in Path(runs_root).glob("*/verdict.json"):
        doc = canonical.read_json(str(path))
        subject = doc.get("subject") or {}
        if (subjects.coin(subject, floors) or subjects.protocol_token(subject, floors)) != coin:
            continue
        published = doc["provenance"]["timestamps"]["published"]
        rated = doc.get("scenario_rating") or {}
        found.append((sufficiency._as_of_moment(published), dict(
            run_id=doc.get("run_id", path.parent.name), published=published[:10], rating=doc["rating"],
            aggregated=bool(rated.get("aggregated")), horizon_months=rated.get("horizon_months"),
            scenarios=[{k: s[k] for k in ("name", "price_outcome", "probability")} for s in rated.get("scenarios") or []])))
    return max(found, key=lambda row: row[0])[1] if found else None


def _largest(readings):
    return max(readings["coins"], key=lambda c: c["value"])


def layer_for(pack, floors, latest):
    """M2, C1: age at capture, strictly below the ruled limit."""
    readings = sufficiency.treasury_readings(pack, floors)
    age = (date.fromisoformat(pack["capture"]["captured_at"][:10]) - date.fromisoformat(latest["published"])).days if latest else None
    cited = latest and latest["aggregated"] and 0 <= age < _rule(floors)["coin_layer"]["max_age_days"]
    return dict(coin=_largest(readings)["coin"], source="on_record" if cited else "this_sitting",
                latest={k: latest[k] for k in ("run_id", "published", "rating")} if latest else None,
                horizon_months=latest["horizon_months"] if cited else _rule(floors)["ladder_rules"]["horizon_months"],
                scenarios=deepcopy(latest["scenarios"]) if cited else [])


def read_layer(folder):
    path = Path(folder) / _rule()["coin_layer"]["file"]
    return canonical.read_json(str(path)) if path.is_file() else None


def treasury_in_force(opening, approval, rule, layer=None):
    """M8: validate and apply ordered changes once, including redirects."""
    choice = deepcopy(opening["preferred_treatment"])
    changes = (approval or {}).get("preferred_changes", [])
    if not isinstance(changes, list):
        raise ValueError(rule["pause"]["change_shape_refusal"])
    for change in changes:
        if (not isinstance(change, dict) or set(change) != {"preferred", "from", "to", "why"}
                or not isinstance(change["preferred"], str) or change["preferred"] not in choice
                or type(change["from"]) is not bool or type(change["to"]) is not bool
                or not isinstance(change["why"], str) or not change["why"].strip()):
            raise ValueError(rule["pause"]["change_shape_refusal"])
        if change["from"] != choice[change["preferred"]]["as_debt"]:
            raise ValueError(rule["pause"]["change_from_refusal"])
        choice[change["preferred"]] = dict(as_debt=change["to"], why=change["why"])
    return dict(preferred_treatment=choice, opening_treatment=deepcopy(opening["preferred_treatment"]),
                preferred_changes=deepcopy(changes), chosen_by=opening["chosen_by"],
                coin_sitting=opening["coin_sitting"], coin_layer=layer)


def _inputs(readings):
    largest = _largest(readings)
    other = sum(c["value"] for c in readings["coins"]) + readings["other_coins"] - largest["value"]
    preferred = readings["true_debt_value"] - readings["preferred_value"]
    return largest["count"], other, readings["cash"], readings["true_debt"], preferred, readings["shares_in_issue"]


def cell_value(readings, coin_price, premium):
    """M4, C6, AC41(2): exact rational arithmetic; round once to cents."""
    values = _inputs(readings)
    count, other, cash, debt, preferred, shares = map(Fraction, values)
    value = (count * Fraction(coin_price) + other + cash - debt - preferred) / shares
    amount = value * (1 + Fraction(premium) / 100) if value > 0 else Fraction(0)
    cents = amount * 100
    # ROUND_HALF_UP also preserves the merged result for a negative written price.
    rounded = abs(cents) + Fraction(1, 2)
    rounded = (rounded.numerator // rounded.denominator) * (-1 if cents < 0 else 1)
    with localcontext() as exact:
        exact.prec = len(str(abs(rounded))) + 2
        price = Decimal(rounded).scaleb(-2)
    rule = _rule()
    arithmetic = rule["casefile_words"]["cell_formula_words"] % tuple(map(str, values))
    arithmetic += " [%s; %s%%; %s]" % (coin_price, premium, price)
    if value <= 0:
        arithmetic += "; " + rule["ladder_rules"]["cell_zero_words"]
    return price, arithmetic


def zero_yardstick_words(readings, rule=None):
    """G2-1: the chosen-basis refusal names the claims that caused it."""
    rule = rule or _rule()
    key = "preferred_zero_yardstick" if readings["true_debt_value"] > 0 else "zero_yardstick"
    return rule[key]["words"]


def case_ratio(readings, key, cases):
    """AC41(2), architect fix round 6: select the basis before rounding."""
    today = readings["comparable_premium"]
    if today is None:
        return None
    if key == next(iter(cases)):
        ratios = [r["discount"] for r in readings["history"]] + [today]
        return max(ratios, key=lambda r: Fraction(r["numerator"]) / Fraction(r["denominator"]))
    return today if today["numerator"] > 0 else None


def falls_premium(readings):
    cases = _rule()["ladder_rules"]["premium_cases"]
    ratio = case_ratio(readings, next(iter(cases)), cases)
    return -ratio["percent"] if ratio else None


def case_price(readings, coin_price, key, cases, premium=None):
    """AC41(2): the one cell calculation, given the exact case premium."""
    ratio = case_ratio(readings, key, cases)
    premium = -100 * Fraction(ratio["numerator"]) / Fraction(ratio["denominator"]) if ratio else cases[key]["first_point_premium"] if key in cases else premium
    return cell_value(readings, coin_price, premium)[0] if premium is not None else None


def case_key(row, cases):
    keys = [key for key, case in cases.items() if _case_cells([row], case)]
    return keys[0] if len(keys) == 1 else None


def case_premium(readings, key, cases):
    ratio = case_ratio(readings, key, cases)
    return -ratio["percent"] if ratio else Decimal(cases[key]["first_point_premium"])


def fill_premium_cases(rated, pack, floors, in_force):
    """Architect fix round 7 replaces C13: only the two machine figures."""
    if not declared(pack, floors) or not isinstance(rated, dict):
        return
    readings = sufficiency.treasury_readings(pack, floors, (in_force or {}).get("preferred_treatment"))
    if not readings or "comparable_premium" not in readings or falls_premium(readings) is None:
        return
    cases = _rule(floors)["ladder_rules"]["premium_cases"]
    for block in [rated, *(rated.get("seat_ladders") or [])]:
        for row in block.get("scenarios") or []:
            key = case_key(row, cases)
            cell = row.get("cell")
            if key and isinstance(cell, dict) and _cell_number(cell.get("coin_price")) is not None:
                cell["premium"] = str(case_premium(readings, key, cases))
                row["price_outcome"] = str(case_price(readings, cell["coin_price"], key, cases))


def _groups(rated):
    groups = {}
    for s in rated.get("scenarios") or []:
        cell = s.get("cell")
        if isinstance(cell, dict):
            groups.setdefault(cell.get("coin_scenario"), []).append(s)
    return groups


def _cell_number(text):
    try:
        return ladder._decimal(text, "cell")
    except ladder.LadderError:
        return None


def _sum_odds(cells):
    """C3: exact sums, including decimal tails beyond the default context."""
    values = [Decimal(s["probability"]) for s in cells]
    with localcontext() as exact:
        exact.prec = max([0] + [v.adjusted() for v in values]) - min([0] + [v.as_tuple().exponent for v in values]) + len(str(len(values))) + 1
        return sum(values, Decimal(0))


def _case_cells(cells, case):
    return [s for s in cells if ladder.case_scenario({"scenarios": [s]}, case["name_words"]) is not None]


def case_odds(block, premium_cases):
    return {key: _sum_odds([s for cells in _groups(block).values() for s in _case_cells(cells, case)])
            for key, case in premium_cases.items()}


def ladder_reasons(rated, pack, floors, in_force):
    """M5: recorded coin odds; named cases per group; every written price."""
    if not declared(pack, floors):
        return [_rule(floors)["ladder_rules"]["cell_on_other_refusal"]] if any("cell" in s for s in rated.get("scenarios") or []) else []
    rule = _rule(floors)["ladder_rules"]
    reasons = []
    try:
        months = int(str(rated.get("horizon_months")))
    except (ValueError, TypeError):
        months = None
    if months != rule["horizon_months"]:
        reasons.append(rule["horizon_refusal"])
    for s in rated.get("scenarios") or []:
        cell = s.get("cell")
        if (not isinstance(cell, dict) or set(cell) != {"coin_scenario", "coin_price", "premium"}
                or any(not isinstance(cell.get(k), str) or not cell[k].strip() for k in ("coin_scenario", "coin_price", "premium"))
                or any(_cell_number(cell.get(k)) is None for k in ("coin_price", "premium"))):
            reasons.append(rule["cell_missing_refusal"] + ": " + str(s.get("name")))
    if reasons and any(rule["cell_missing_refusal"] in r for r in reasons):
        return reasons
    groups = _groups(rated)
    if any(_cell_number(s.get("probability")) is None for s in rated.get("scenarios") or []):
        return reasons  # The shared ladder shape check already names it.
    layer = (in_force or {}).get("coin_layer") or {}
    readings = sufficiency.treasury_readings(pack, floors, (in_force or {}).get("preferred_treatment"))
    if falls_premium(readings) is None:
        return reasons + [zero_yardstick_words(readings, _rule(floors))]
    today = -readings["comparable_premium"]["percent"]
    odds = {name: _sum_odds(cells) for name, cells in groups.items()}
    if layer.get("source") == "on_record":
        recorded = {s["name"]: s for s in layer["scenarios"]}
        if set(groups) != set(recorded) or any(odds[n] != Decimal(recorded[n]["probability"]) for n in groups if n in recorded):
            reasons.append(rule["coin_odds_refusal"])
        for name, cells in groups.items():
            if name not in recorded or any(Decimal(s["cell"]["coin_price"]) != Decimal(recorded[name]["price_outcome"]) for s in cells):
                reasons.append(rule["coin_scenario_refusal"] + ": " + str(name))
    else:
        if len(groups) < rule["minimum_scenarios"] or any(len({Decimal(s["cell"]["coin_price"]) for s in cells}) != 1 for cells in groups.values()):
            reasons.append(rule["coin_layer_refusal"])
        key = _largest(readings)["coin"]
        registry, row = subjects.admitted_coin(floors, key)
        if row.get("privacy_coin"):
            coin_rule = floors["asset_classes"]["crypto"]["monetary_coin_rule"]
            reason = ladder.delisting_reason({"scenarios": [dict(name=n, probability=str(o)) for n, o in odds.items()]},
                coin_rule["delisting_scenario_words"], coin_rule["delisting_refusal"], coin_rule["delisting_zero_refusal"])
            if reason:
                reasons.append(reason)
    for name, cells in groups.items():
        grouped = {"scenarios": cells}
        reasons.extend(str(name) + ": " + r for r in ladder.named_case_reasons(grouped, rule["premium_cases"], rule["shared_refusal"]))
        for key, case in rule["premium_cases"].items():
            matches = _case_cells(cells, case)
            reasons.extend(str(name) + ": " + rule["duplicate_case_refusal"] + ": " + s["name"] for s in matches[1:])
            first = matches[0] if matches else None
            if first:
                premium = Decimal(first["cell"]["premium"])
                if key == next(iter(rule["premium_cases"])) and premium != falls_premium(readings):
                    reasons.append(str(name) + ": " + rule["falls_premium_refusal"])
            if key != next(iter(rule["premium_cases"])):
                for matched in matches:
                    premium = Decimal(matched["cell"]["premium"])
                    if readings["comparable_premium"]["numerator"] > 0 and premium != today:
                        reasons.append(str(name) + ": " + rule["today_discount_refusal"])
                    elif readings["comparable_premium"]["numerator"] <= 0 and premium != Decimal(case["first_point_premium"]):
                        reasons.append(str(name) + ": " + rule["discount_refusal"])
    for s in rated.get("scenarios") or []:
        key = case_key(s, rule["premium_cases"])
        price = case_price(readings, s["cell"]["coin_price"], key, rule["premium_cases"], s["cell"]["premium"]) if key else cell_value(readings, s["cell"]["coin_price"], s["cell"]["premium"])[0]
        if gate._decimal_or_none(s.get("price_outcome")) != price:
            reasons.append(rule["cell_price_refusal"] + ": %s; %s != %s" % (s["name"], s.get("price_outcome"), price))
    return reasons


def problems(draft, pack, floors, in_force):
    """M6: last hard check, even when the ladder could not be added up."""
    rated = draft.get("scenario_rating") or {}
    if not declared(pack, floors):
        return ladder_reasons(rated, pack, floors, in_force) + ([_rule(floors)["ladder_rules"]["read_on_other_kind_refusal"]] if "treasury_read" in draft else [])
    rule = _rule(floors)["ladder_rules"]
    reasons = ladder_reasons(rated, pack, floors, in_force) if rated.get("aggregated") else []
    read = draft.get("treasury_read")
    if not isinstance(read, dict):
        return reasons + [rule["read_missing_refusal"]]
    force = in_force or {}
    layer = force.get("coin_layer") or {}
    expected = dict(source=layer.get("source"), run_id=force.get("coin_sitting") if layer.get("source") == "on_record" else None)
    if read.get("coin_layer") != expected:
        reasons.append(rule["layer_read_refusal"])
    preferred = read.get("preferred") or []
    choices = force.get("preferred_treatment") or {}
    if (len(preferred) != len(choices) or {p.get("key") for p in preferred} != set(choices)
            or any(p.get("as_debt") != choices[p["key"]]["as_debt"] for p in preferred if p.get("key") in choices)):
        reasons.append(rule["preferred_read_refusal"])
    objection = read.get("objection") or {}
    for text in [p.get("why") for p in preferred] + [objection.get("objection"), objection.get("answer")]:
        if not isinstance(text, str) or not text.strip() or text.splitlines() != [text] or len(text.split()) > rule["line_max_words"]:
            reasons.append(rule["line_refusal"])
    return reasons


def casefile_lines(readings, in_force, words):
    """M11: one raw block, escaped by the case file's existing path."""
    premium = falls_premium(readings)
    if premium is None:
        return [zero_yardstick_words(readings)]
    lines = []
    layer = in_force["coin_layer"]
    if layer["source"] == "on_record":
        lines += [words["coin_layer_lead"], " | ".join(words["head"])]
        for s in layer["scenarios"]:
            value, _ = cell_value(readings, s["price_outcome"], "0")
            lines.append(" | ".join((s["name"], s["price_outcome"], s["probability"], str(value))))
    lines.append(words["basis_with_preferred"] if readings.get("history_preferred_as_debt") else words["basis_without_preferred"])
    lines.extend(readings.get("history_gaps", []))
    counts = words["yearend_count_words"] % (sum(p["annual"] for p in readings["periods"]), len(readings["history"]))
    lines.append(words["falls_premium_words" if readings["history"] else "falls_premium_today_words"] % (str(premium) + "%", counts))
    lines.append(words["cell_formula_words"] % tuple(map(str, _inputs(readings))))
    return lines
