"""Owner rulings AC78-AC81: the protocol chairman's hard checks.

The stage and the draft share the declared range. Every refusal is data;
the arithmetic extends the existing ladder, never a second rating engine.
"""

from council.evidence import gate, sufficiency
from council.lib import subjects
from council.engine import ladder


def derate_refusal(floors, case):
    """AC67(3), AC80(2): a named record must establish its pace."""
    rule = floors["asset_classes"]["crypto"]["protocol_rule"]
    record = rule["derate_cases"][case]["record"]
    if not record["release_pace"]["established"]:
        return rule["derate_not_usable_refusal"] + ": " + case + "; " + "; ".join(record["gaps"])
    return None


def declared_range(pack, floors, in_force):
    """C4: the one reader of the method named at the pause, no default."""
    rule = floors["asset_classes"]["crypto"]["protocol_rule"]
    spec = rule["opening"]
    method = (in_force or {}).get("range_method", spec["no_method"])
    values = sufficiency.protocol_value_readings(pack, floors, in_force)
    if values is None:
        return rule["readings_refusal"]
    only = values["scenarios_only"]
    if only and method != spec["no_method"]:
        return rule["range_method_scenarios_only_refusal"]
    if not only and method == spec["no_method"]:
        return rule["range_method_missing_refusal"]
    if only:
        return dict(scenarios_only=True, method=method, low=None, high=None, per=None)
    if method not in spec["range_methods"]:
        return rule["range_method_value_refusal"]
    reading = values["methods"][method]
    if not reading["used"]:
        return rule["range_method_unused_refusal"] + ": " + reading["why"]
    supply = sufficiency.protocol_supply_readings(pack, floors)
    return dict(scenarios_only=False, method=method, low=reading["low"], high=reading["high"],
                per=supply["twelve_month_supply"])


def claim_floor(rated, claim, pack, floors):
    """AC81(2), R8: the ladder's exact chance, on the claim's own measure."""
    rule = floors["asset_classes"]["crypto"]["protocol_rule"]
    measures = rule["opening"]["claim_measures"]
    if claim["measure"] == measures[0]:
        per = sufficiency.protocol_supply_readings(pack, floors)["twelve_month_supply"]
    elif claim["measure"] == measures[1]:
        fid = rule["roles"]["supply_total"]["id"]
        per = gate._decimal_or_none(next(f["value"] for f in pack["capture"]["tier1"] if f["id"] == fid))
    else:
        per = 1
    return ladder.mass_at_or_above(rated, claim["level"], per)


def problems(draft, pack, floors, in_force):
    """C5-C8: range, protocol read and claim, after existing reasons."""
    rule = floors["asset_classes"]["crypto"]["protocol_rule"]
    rated = draft.get("scenario_rating") or {}
    if not subjects.is_protocol_kind(pack["capture"]["subject"], floors):
        return ([rule["read_on_other_kind_refusal"]] if "protocol_read" in draft else []) + (
            [rule["catalyst_on_other_kind_refusal"]] if any("catalyst" in s for s in rated.get("scenarios") or ()) else [])
    reasons = []
    if gate._decimal_or_none(rated.get("horizon_months")) != rule["chair"]["ladder_horizon_months"]:
        reasons.append(rule["horizon_refusal"])
    range_read = declared_range(pack, floors, in_force)
    usable = rated.get("aggregated") and not ladder.check_shape(
        rated, {f["id"]: f for f in pack["capture"]["tier1"]})
    if isinstance(range_read, str):
        reasons.append(range_read)
    elif usable and not range_read["scenarios_only"]:
        reasons.extend(ladder.range_reasons(rated, range_read["low"], range_read["high"], range_read["per"],
                       dict(base_rung=rule["base_rung_refusal"], bull_catalyst=rule["bull_catalyst_refusal"])))
    if "protocol_read" not in draft:
        return reasons + [rule["read_missing_refusal"]]
    read = draft["protocol_read"]
    # The host validates this value against the one verdict shape first.
    if not isinstance(read, dict):
        return reasons + [rule["read_missing_refusal"]]
    case = (in_force or {}).get("derate_case")
    comparison = sufficiency.protocol_derate_comparison(pack, floors, case)
    deciding = (read.get("comparison") or {}).get("deciding_measure")
    if not comparison or not any(m["id"] == deciding and m["both_sides"] for m in comparison["measures"]):
        reasons.append(rule["deciding_measure_refusal"])
    cells = read.get("near_term") or []
    pairs = [(c.get("horizon"), c.get("side")) for c in cells]
    expected = {(h, s) for h in rule["near_term"]["horizons"] for s in rule["near_term"]["sides"]}
    invalid = len(pairs) != len(expected) or set(pairs) != expected
    for cell in cells:
        low, high, chance = [gate._decimal_or_none(cell.get(k)) for k in ("price_low", "price_high", "probability")]
        if low is None or high is None or chance is None or low <= 0 or low > high or not 0 < chance < 1:
            invalid = True
    if invalid:
        reasons.append(rule["near_term_refusal"])
    claim = (in_force or {}).get("claim", rule["opening"]["no_claim"])
    tested = read.get("claim")
    if claim == rule["opening"]["no_claim"]:
        if tested is not None:
            reasons.append(rule["claim_without_opening_refusal"])
        return reasons
    chance = gate._decimal_or_none((tested or {}).get("probability"))
    if chance is None or not 0 <= chance <= 1:
        return reasons + [rule["claim_missing_refusal"]]
    if usable:
        mass = claim_floor(rated, claim, pack, floors)
        if chance < mass:
            reasons.append(rule["claim_floor_refusal"] + ": %s < %s" % (chance, mass))
    return reasons
