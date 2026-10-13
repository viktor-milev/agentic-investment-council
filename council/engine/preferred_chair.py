"""AC92(3), M8-M9: machine dividends and the chairman's cover line."""
from datetime import date
from decimal import Decimal, localcontext
from fractions import Fraction
from council.evidence import gate, sufficiency


def _rule(floors):
    return floors["archetype_measures"].get("holding_rule", {}).get("treasury", {}).get("listed_preferred", {})


def _ratio_words(value):
    """AC16(4), M5-M6: display only, one place cut toward zero."""
    if not value: return None
    cut = int(Fraction(value["numerator"])/Fraction(value["denominator"])*10)
    return ("-" if cut<0 else "")+str(abs(cut)//10)+"."+str(abs(cut)%10)


def _exact_words(value, currency=None, percent=False):
    from council.report.render_report import _currency_prefix
    if value is None: return None
    text = format(value,"f")
    return (_currency_prefix(currency)+text) if currency else (text if "." in text else text+".0")+"%" if percent else text


def _cover_words(value, floors, why=None):
    rule = _rule(floors)
    return _ratio_words(value)+" "+rule["page_words"]["cover_unit_words"] if value else why or rule["page_words"]["cover_missing_words"]


def declared(pack, floors):
    capture = (pack or {}).get("capture") or {}; rule = _rule(floors)
    if not rule or capture.get("subject", {}).get("kind") != rule["kind"]: return None
    triple = sufficiency.preferred_frame(floors, capture)
    return triple if triple and date.fromisoformat(capture["captured_at"][:10]) >= date.fromisoformat(rule["applies_from"]) else None


def _outcome(cell, readings, rule):
    case = rule["dividend_cases"].get(cell.get("dividend")); price = gate._decimal_or_none(cell.get("price")); coin = gate._decimal_or_none(cell.get("coin_price"))
    if not case or price is None or coin is None or min(price,coin) < 0 or readings.get("dividend") is None: return None
    with localcontext() as exact:
        exact.prec = 100 + len(str(price)) + len(str(readings["dividend"]))
        return price + (readings["dividend"] if case["pays"] else Decimal(0))


def fill_dividends(rated, pack, floors):
    if not declared(pack,floors) or not isinstance(rated,dict): return []
    readings = sufficiency.preferred_readings(pack,floors); rule = _rule(floors); reasons = []
    for block in [rated,*(rated.get("seat_ladders") or [])]:
        for row in block.get("scenarios") or []:
            cell = row.get("dividend_cell"); outcome = _outcome(cell,readings,rule) if isinstance(cell,dict) else None
            if outcome is not None:
                if row.get("price_outcome") is not None and gate._decimal_or_none(row["price_outcome"]) != outcome: reasons.append(rule["ladder_words"]["cell_price_refusal"])
                row["price_outcome"] = str(outcome)
    return reasons


def ladder_reasons(rated, pack, floors):
    rule = _rule(floors); rows = (rated or {}).get("scenarios") or []; words = rule.get("ladder_words", {})
    if not declared(pack,floors): return [words["cell_on_other_refusal"]] if any("dividend_cell" in r for r in rows) and words else []
    readings = sufficiency.preferred_readings(pack,floors); reasons = []; present = set()
    for row in rows:
        cell = row.get("dividend_cell"); outcome = _outcome(cell,readings,rule) if isinstance(cell,dict) and set(cell)=={"dividend","coin_price","price"} else None
        if outcome is None: reasons.append(words["cell_missing_refusal"]); continue
        case = rule["dividend_cases"][cell["dividend"]]
        if case.get("cumulative_only") and not readings["cumulative"]: reasons.append(words["deferred_case_refusal"])
        if gate._decimal_or_none(row.get("price_outcome")) != outcome: reasons.append(words["cell_price_refusal"])
        odds = gate._decimal_or_none(row.get("probability"))
        if odds is not None and odds>0: present.add(case["pays"])
    if True not in present: reasons.append(words["paid_case_refusal"])
    if False not in present: reasons.append(words["unpaid_case_refusal"])
    if len(rows)<floors["archetype_measures"]["holding_rule"]["treasury"]["ladder_rules"]["minimum_scenarios"]: reasons.append(words["cell_missing_refusal"])
    return reasons


def problems(draft, pack, floors):
    rule = _rule(floors); words = rule.get("ladder_words", {}); rated = draft.get("scenario_rating") or {}; read = draft.get("cover_read")
    reasons = ladder_reasons(rated,pack,floors)
    for block in rated.get("seat_ladders") or []: reasons.extend(ladder_reasons(block,pack,floors))
    if not declared(pack,floors): return reasons + ([words["read_on_other_kind_refusal"]] if "cover_read" in draft and words else [])
    if not isinstance(read,dict) or set(read)!={"cover"} or not isinstance(read.get("cover"),str) or not read["cover"].strip(): reasons.append(words["read_missing_refusal"])
    elif len(read["cover"].splitlines())!=1 or len(read["cover"].split())>floors["archetype_measures"]["holding_rule"]["treasury"]["ladder_rules"]["line_max_words"]: reasons.append(words["line_refusal"])
    return reasons


def case_odds(block, readings, floors):
    result = []; rule = _rule(floors)
    for key, case in rule["dividend_cases"].items():
        cells = [r for r in (block or {}).get("scenarios",[]) if (r.get("dividend_cell") or {}).get("dividend")==key]
        covers = [sufficiency.preferred_cover(readings,gate._decimal_or_none(r["dividend_cell"].get("coin_price"))) for r in cells]
        covers = [c["cover"] for c in covers if c and c["cover"]]
        with localcontext() as exact:
            exact.prec = 100 + sum(len(str(r.get("probability"))) for r in cells)
            result.append(dict(case=key,label=case["label"],odds=sum((gate._decimal_or_none(r.get("probability")) or Decimal(0) for r in cells),Decimal(0)),cover=min(covers,key=lambda c:Fraction(c["numerator"])/Fraction(c["denominator"])) if covers else None))
    return result


def casefile_lines(readings, words):
    if not readings.get("cover"): return [words["lead"]]
    from council.report.render_report import format_protocol_number
    issuer = readings["issuer_readings"]; largest = max(issuer["coins"],key=lambda c:c["value"])
    other = sufficiency.preferred_cover(readings,Decimal(0))["treasury"]-issuer["cash"]
    values = [largest["count"],other,issuer["cash"],readings["claims_ahead"],readings["claims_alongside"]]
    shown = [format_protocol_number(str(v),"number" if n==0 else "money",currency=readings["currency"]) for n,v in enumerate(values)]
    from council.evidence.brief import _format_date
    dividend = words["dividend_words"] % (_exact_words(readings["dividend"],readings["currency"]) or readings["why"]["dividend"],_exact_words(readings["rate"],percent=True) or readings["why"]["rate"],_format_date(readings["rate_date"]))
    return [words["lead"],dividend,words["cover_formula_words"] % tuple(shown)]
