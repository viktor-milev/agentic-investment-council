"""Owner ruling AC87(1): the holder ladder and chairman's hard checks.
Every case, threshold and refusal is read from the product's ruled data.
"""

from council.evidence import gate
from council.lib import subjects
from council.engine import ladder


def ladder_reasons(rated, subject, floors, reference=None):
    """M4-M5: the ruled horizon and named cases, or no added reasons."""
    row = subjects.holder_product(subject, floors)
    if not row:
        return []
    rule = row["rule"]["ladder"]
    reasons = []
    if gate._decimal_or_none(rated.get("horizon_months")) != row["horizon_months"]:
        reasons.append(rule["horizon_refusal"])
    try:
        reasons.extend(ladder.named_case_reasons(rated, rule["downside_cases"], rule["shared_refusal"],
                       reference, rule["below_refusal"]))
    except ladder.LadderError:
        # The existing shape check names malformed prices before this check.
        pass
    return reasons


def problems(draft, pack, floors, in_force):
    """M7-M8: after all existing draft reasons; judgment never rates it."""
    subject = pack["capture"]["subject"]
    row = subjects.holder_product(subject, floors)
    if not row:
        if "uranium_read" not in draft:
            return []
        product = floors["archetype_measures"]["uranium_producer_rule"]["product"]
        rule = floors["asset_classes"]["commodity"]["products"][product]["rule"]["ladder"]
        return [rule["read_on_other_kind_refusal"]] if "uranium_read" in draft else []
    rule, rated = row["rule"]["ladder"], draft.get("scenario_rating") or {}
    reference_id = floors["anchorless_rating"]["bar_inputs"]["reference_price"]
    reference = next((f["value"] for f in pack["capture"]["tier1"] if f["id"] == reference_id), None)
    reasons = ladder_reasons(rated, subject, floors, reference) if rated.get("aggregated") else []
    read = draft.get("uranium_read")
    if not isinstance(read, dict):
        return reasons + [rule["read_missing_refusal"]]
    fall = read.get("past_fall") or {}
    if fall.get("case") != (in_force or {}).get("past_fall"):
        reasons.append(rule["case_refusal"])
    for text in (fall.get("comparison"), read.get("longer_cycle")):
        if not isinstance(text, str) or not text.strip() or text.splitlines() != [text] or len(text.split()) > rule["line_max_words"]:
            reasons.append(rule["line_refusal"])
    return reasons
