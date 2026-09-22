"""The publisher: the chairman's FINAL document becomes the verdict.

Publication is transparency, not a gate (REBUILD-SPEC section 7). The final
document is diffed field by field against the challenged draft and every
change is listed in the change appendix; a rating raised past the challenged
draft without a challenger endorsement publishes WITH a prominent warning,
never silently; and whenever the published rating differs from the
challenger's endorsed ceiling in EITHER direction, a note names both
ratings (owner ruling AB16(5)). When the outside audit did not run, the
draft publishes
degraded: capped at hold when it said buy or strong buy, with a loud warning
that nothing was challenged.

The only refusals here are mechanical (REBUILD-SPEC section 7): a
schema-invalid assembly, a pack hash mismatch, or an unfinished run raise -
and the host records the run FAILED. There is no refusal on content.

On the verdict hash: verdict.json cannot carry its own hash, so inside
verdict.json the Atlas envelope's verdict_hash is null. The standalone
atlas-envelope.json is written after the verdict and carries the real hash
of verdict.json; the read-back entry point proves the two agree.

Owner ruling AB23 made the hand-off self-sufficient. It now names its own
subject, states the audit outcome the portfolio system computes its
effective rating from, and tags every row that rests on a declared bound
rather than a measurement. Two things about the ASSEMBLY carry that
ruling and must not be reordered: the warnings list is complete before the
envelope is built (the AB16(5) note is appended above), and both copies -
the one inside the verdict and the standalone file - are built from the
same dict, so read-back's field-for-field comparison keeps holding.
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, subjects, validate  # noqa: E402
from council.engine import briefs, ladder, runrecord  # noqa: E402
from council.ledger import ledger  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_DIR = os.path.join(ROOT, "council", "schemas")
FLOORS_PATH = os.path.join(ROOT, "council", "floors", "floors.json")

RANK = {"sell": 0, "hold": 1, "buy": 2, "strong_buy": 3}

DIFF_FIELDS = (
    ("rating", "rating"),
    ("conviction_rationale", "conviction_rationale"),
    ("mispricing.read", ("mispricing", "read")),
    ("mispricing.magnitude", ("mispricing", "magnitude")),
    ("mispricing.arithmetic", ("mispricing", "arithmetic")),
    ("scenario_rating", "scenario_rating"),
    ("tripwires", "tripwires"),
    ("sizing_inputs", "sizing_inputs"),
    ("constituent_notes", "constituent_notes"),
    ("evidence_dependencies", "evidence_dependencies"),
    ("key_numbers", "key_numbers"),
)

SEAT_ORDER = ["frame"] + briefs.ADVISOR_SEATS + [
    "reviewer", "chair_draft", "chair_resolve"]

# The chairman's ONE prose re-ask (owner ruling AC6) is written under its own
# seat so the gate can dispatch and splice it, but its tokens are the chairman's
# and count toward the owner's budget (AB6/AB11, discarded attempts included).
# Fold each prose seat's request into the parent chair seat's per-seat sum, so
# the published token total counts the re-ask exactly as the host's interim
# figure does (audit finding r4-3). No new seat row: per_seat is keyed by
# SEAT_ORDER, which the prose seats are deliberately not in. The names mirror
# host._PROSE_REASK_SEATS - host imports publisher, so this cannot import back.
_PROSE_REASK_CHAIR = {"chair_draft_prose": "chair_draft",
                      "chair_resolve_prose": "chair_resolve"}


class PublishRefusal(Exception):
    """A mechanical refusal: the run is not in a publishable condition."""


def _now_utc():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _get(document, key):
    if isinstance(key, tuple):
        value = document
        for part in key:
            value = value.get(part) if isinstance(value, dict) else None
        return value
    return document.get(key)


def _render(value):
    """Appendix cell: strings as themselves, everything else as canonical
    JSON text."""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"))


def _is_raise(before, after):
    if before in RANK and after in RANK:
        return RANK[after] > RANK[before]
    return before == "monitor" and after in ("buy", "strong_buy")


def _rating_words(rating):
    return str(rating).replace("_", " ")


def build_change_appendix(challenged, final, endorsement):
    """One row per changed field, the rating row labeled for raises.
    Returns (appendix_rows, warnings)."""
    rows = []
    warnings = []
    for name, key in DIFF_FIELDS:
        before = _get(challenged, key)
        after = _get(final, key)
        if before == after:
            continue
        label = "change"
        if name == "rating" and _is_raise(before, after):
            supported = (endorsement or {}).get("highest_rating_supported")
            if (supported in RANK and after in RANK
                    and RANK[supported] >= RANK[after]):
                label = "endorsed_raise"
            else:
                label = "unendorsed_raise"
                warnings.append(
                    "The outside auditor did not see this rating: the "
                    "chairman raised it to %s after the challenge round, "
                    "without a challenger endorsement."
                    % _rating_words(after))
        rows.append({"field": name, "before": _render(before),
                     "after": _render(after), "label": label})
    return rows, warnings


def endorsement_note(published_rating, endorsement):
    """The note that names the published rating and the challenger's
    endorsed ceiling together (owner ruling AB16(5)).

    It fires whenever the two words differ, in EITHER direction - the
    raise check above catches only ratings pushed past the ceiling, so
    a council that published sell under a ceiling of monitor said
    nothing at all on the page. No ordering is invented here: monitor
    is a watch-state and not a rank, and a plain difference needs no
    rank to be true.

    The wording NAMES and never judges. A rating below a ranked ceiling
    sits inside what the auditor endorsed, so a note calling that a
    divergence would be false; naming both ratings is true in every
    case. Transparency only - nothing here gates, blocks or degrades
    what publishes.

    Returns a one-element list, or an empty one when the two agree or
    the challenger endorsed no ceiling."""
    ceiling = (endorsement or {}).get("highest_rating_supported")
    if ceiling is None or ceiling == published_rating:
        return []
    return ["Rating against the outside auditor's ceiling: the council "
            "published %s; the highest rating the auditor said the record "
            "supports was %s."
            % (_rating_words(published_rating), _rating_words(ceiling))]


def degrade_scenario_rating(published, earned, publishing):
    """The published rating is a SECOND READ of the same rating the
    ladder earned, and the fix-checklist's rule 8a binds every read of
    one entity the same way. When the outside audit did not run, the
    publisher caps the rating at hold - and without this the scenario
    block beside the badge still ended 'so the rating is buy', so the
    page showed a Hold above a sum that said otherwise.

    The ladder's own answer is never falsified: `rating` stays what the
    arithmetic earned. `published_rating` names what actually publishes,
    and one plain sentence closes the sum with the reason."""
    if published is None:
        return None
    published = dict(published)
    published["published_rating"] = (
        publishing if publishing != earned else None)
    if publishing == earned:
        return published
    published["arithmetic"] = list(published.get("arithmetic") or []) + [
        "The outside audit did not run, so nothing stronger than hold "
        "publishes: the rating on this page is %s, not the %s this "
        "ladder earns."
        % (_rating_words(publishing), _rating_words(earned))]
    return published


def _challenge_record(run_dir, events):
    """What the run record and bridge files say about the challenge."""
    verified = [e for e in events if e["event"] == "challenge_result"]
    if not verified:
        raise PublishRefusal("no challenge result is recorded; the run is "
                             "unfinished")
    status = verified[-1]["status"]
    failure_reason = verified[-1].get("failure_reason")
    request_path = os.path.join(run_dir, "challenge", "request.json")
    request = canonical.read_json(request_path)
    result_path = os.path.join(run_dir, "challenge", "result.json")
    result = {}
    if os.path.exists(result_path):
        try:
            result = canonical.read_json(result_path)
        except ValueError:
            result = {}
    doc = result.get("findings") or {}
    findings = doc.get("findings", []) if status == "success" else []
    endorsement = doc.get("endorsement") if status == "success" else None
    # Architect ruling (spec section 17): the challenger's overall view
    # travels in the published record verbatim - null on a failed
    # challenge, never fabricated.
    summary = doc.get("summary") if status == "success" else None
    challenger_tokens = result.get("usage_tokens")
    if not isinstance(challenger_tokens, int):
        challenger_tokens = None
    return {"status": status, "failure_reason": failure_reason,
            "model_requested": request["model"], "findings": findings,
            "endorsement": endorsement, "summary": summary,
            "challenger_tokens": challenger_tokens}


def _usage_by_request(run_dir, events):
    """Read every usage sidecar directly off disk (a sidecar may land after
    its answer was ingested); map request number -> usage dict."""
    numbers = {e["number"]: e["seat"] for e in events
               if e["event"] == "request_written"}
    usage = {}
    rpc = os.path.join(run_dir, "rpc")
    for number, seat in numbers.items():
        path = os.path.join(rpc, "%s-usage.json" % number)
        if not os.path.exists(path):
            continue
        try:
            usage[number] = (seat, canonical.read_json(path))
        except ValueError:
            continue
    return usage


def _evidence_provenance(events, run_started):
    """What the sitting decided and spent BEFORE the run existed (owner
    ruling AC3, spec section U3.3), out of the run record and into the
    published document.

    The report's front page reads its mode sentence and the capture's own
    clocks from here, so the page can never say less about who reviewed
    the evidence than the record knows."""
    mode = {}
    approval = None
    usage = {}
    for event in events:
        if event["event"] == "evidence_mode":
            mode = event
        elif event["event"] == "evidence_approved":
            approval = event
        elif event["event"] == "capture_usage_recorded":
            usage = event
    return {
        "mode": mode.get("mode"),
        "chosen_by": mode.get("chosen_by"),
        "chosen_at": mode.get("at"),
        "approved_by": None if approval is None else approval.get("by"),
        "approved_at": None if approval is None else approval.get("at"),
        "approval_note": None if approval is None else approval.get("note"),
        "clock_started": runrecord.clock_start(events, run_started),
        "capture": {
            "tokens": usage.get("tokens"),
            "minutes": usage.get("minutes"),
            "model": usage.get("model"),
            # Owner ruling AC15 (P5(b)): whether the capture-stage figures
            # are an estimate. The report prints "estimated" beside them
            # where it is true.
            "estimated": usage.get("estimated"),
            "evidence_challenge_tokens": usage.get(
                "evidence_challenge_tokens"),
            "evidence_challenge_prompt_bytes": usage.get(
                "evidence_challenge_prompt_bytes"),
        },
    }


def _complete_seat_sum(usage, numbers, key):
    """Sum a per-request usage metric over every request a seat made, or
    None where that total cannot be known to be COMPLETE. A request whose
    usage sidecar is missing or unreadable, or whose metric is not a whole
    number, leaves the seat only PARTLY measured - a retried seat whose paid
    first attempt wrote no sidecar, say - and a partial cost must never be
    published as the seat's whole cost (audit UPGRADE2-U3d-c r9). A seat that
    recorded nothing at all is None as it always was, and is left out of the
    run total exactly as an unmeasured seat always has been."""
    total = None
    for number in numbers:
        entry = usage.get(number)
        if entry is None:
            return None
        value = entry[1].get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            return None
        total = value if total is None else total + value
    return total


def _seat_cost(run_dir, events):
    """The seat-cost measure AC8 is revisited on (owner ruling AC15,
    architect ruling (5)(a)): tokens per tool turn and brief bytes, per
    seat. Spec U5.5's input/output token split is unobtainable from the
    dispatch harness - it returns one token figure, its tool turns and
    its wall clock - so those two fields stay null with the note that
    says why. Computed into the published record so the report's appendix
    can print it."""
    brief_bytes = {}
    seat_numbers = {}
    for event in events:
        if event["event"] == "request_written":
            seat = _PROSE_REASK_CHAIR.get(event["seat"], event["seat"])
            brief_bytes[seat] = (brief_bytes.get(seat, 0)
                                 + (event.get("brief_bytes") or 0))
            seat_numbers.setdefault(seat, []).append(event["number"])
    usage = _usage_by_request(run_dir, events)
    per_seat = {}
    for seat in SEAT_ORDER:
        if seat not in seat_numbers:
            continue
        numbers = seat_numbers[seat]
        tokens = _complete_seat_sum(usage, numbers, "tokens")
        tool_calls = _complete_seat_sum(usage, numbers, "tool_calls")
        ratio = None
        if isinstance(tokens, int) and isinstance(tool_calls, int) \
                and tool_calls > 0:
            ratio = round(tokens / tool_calls, 1)
        per_seat[seat] = {"tokens": tokens, "tool_calls": tool_calls,
                          "tokens_per_tool_call": ratio,
                          "brief_bytes": brief_bytes.get(seat),
                          "input_tokens": None, "output_tokens": None}
    return {
        "note": "The dispatch harness returns one token figure per seat, "
                "its tool turns and its wall clock - not the input/output "
                "split spec U5.5 named, which is unobtainable here. The "
                "seat-cost lever AC8's cap is revisited on is therefore "
                "tokens per tool turn and brief bytes per seat; the "
                "input and output token fields stay null (architect ruling "
                "AC15(5)(a)).",
        "per_seat": per_seat}


def _provenance(run_dir, events, invocation, challenger_tokens,
                challenger_model):
    accepted = {}
    seat_numbers = {}
    for event in events:
        if event["event"] == "request_written":
            seat = _PROSE_REASK_CHAIR.get(event["seat"], event["seat"])
            seat_numbers.setdefault(seat, []).append(event["number"])
        elif event["event"] == "answer_accepted":
            accepted[event["seat"]] = event["number"]
    usage = _usage_by_request(run_dir, events)
    models = {}
    per_seat = {}
    for seat in SEAT_ORDER:
        if seat not in accepted:
            continue
        accepted_usage = usage.get(accepted[seat])
        model = accepted_usage[1].get("model") if accepted_usage else None
        models[seat] = model if isinstance(model, str) else None
        # The same completeness rule as the seat-cost appendix (fix checklist
        # 8a): per_seat here and seat_cost[seat]["tokens"] are the one quantity
        # and must agree, so a partly measured seat is None in both. seats_total
        # then sums the seats known in full and leaves out a seat whose cost is
        # unknown, exactly as it always has for a seat that recorded nothing.
        per_seat[seat] = _complete_seat_sum(
            usage, seat_numbers.get(seat, []), "tokens")
    known = [t for t in per_seat.values() if isinstance(t, int)]
    seats_total = sum(known) if known else None
    run_started = invocation["created_at"]
    return {"pack_hash": invocation["pack_sha256"],
            "ledger_row_id": invocation["run_id"],
            "models_per_seat": models,
            "challenger_model_requested": challenger_model,
            "timestamps": {"run_started": run_started,
                           "published": _now_utc()},
            "tokens": {"per_seat": per_seat, "seats_total": seats_total,
                       "challenger": challenger_tokens},
            "seat_cost": _seat_cost(run_dir, events),
            "prompt_bytes_total": briefs.total_prompt_bytes(run_dir),
            "evidence": _evidence_provenance(events, run_started)}


def _accepted_answer(run_dir, events, seat):
    for event in reversed(events):
        if event["event"] == "answer_accepted" and event["seat"] == seat:
            return canonical.read_json(os.path.join(run_dir, event["path"]))
    raise PublishRefusal("no accepted %s answer is on record; the run is "
                         "unfinished" % seat)


def _optional_answer(run_dir, events, seat):
    """An accepted seat answer where one exists, else None."""
    try:
        return _accepted_answer(run_dir, events, seat)
    except PublishRefusal:
        return None


def _scenario_rating(final, subject, pack, run_dir, events):
    """The published scenario block (ANCHORLESS-SPEC section 3).

    The chairman's ladder travels as he wrote it; the ARITHMETIC beside
    it is recomputed here from the same frozen facts the host checked it
    against, so the figures on the page are the machine's and not a
    seat's. Each advisor's own headline ladder rides along, because the
    ruling requires the seats' divergence to stay visible in the record.
    On an equity the ladder is supporting context and earns nothing: the
    block publishes without a rating, labelled as context."""
    block = final.get("scenario_rating")
    if block is None:
        return None
    facts = {fact["id"]: fact
             for fact in (pack.get("capture") or {}).get("tier1", [])}
    seat_ladders = []
    for seat in briefs.ADVISOR_SEATS:
        answer = _optional_answer(run_dir, events, seat) or {}
        seat_ladder = answer.get("scenario_ladder")
        if seat_ladder:
            seat_ladders.append({"seat": seat,
                                 "horizon_months":
                                     str(seat_ladder["horizon_months"]),
                                 "scenarios": seat_ladder["scenarios"]})
    published = {
        "aggregated": bool(block.get("aggregated")),
        "basis": "rating" if subjects.is_anchorless(subject) else "context",
        "not_aggregated_reason": block.get("not_aggregated_reason"),
        "horizon_months": str(block.get("horizon_months")),
        "scenarios": block.get("scenarios") or [],
        "reference_price_fact_id": block.get("reference_price_fact_id"),
        "volatility_fact_id": block.get("volatility_fact_id"),
        "cash_rate_fact_id": block.get("cash_rate_fact_id"),
        "seat_ladders": seat_ladders,
        "arithmetic": [],
    }
    if not published["aggregated"] or published["basis"] != "rating":
        return published
    floors = canonical.read_json(FLOORS_PATH)
    computed = ladder.compute(block, facts, floors)
    for key in ("reference_price", "expected_price", "expected_total_pct",
                "expected_annualised_pct", "cash_pct", "volatility_pct",
                "bar_pct", "excess_over_bar_pp", "rating", "constants",
                "arithmetic", "sensitivity"):
        published[key] = computed[key]
    return published


def _bound_of(row, fact_ids, facts):
    """The bound tag for one hand-off row (owner ruling AB23(4)).

    A row that QUOTES one tier-1 fact inherits whatever that fact
    declares: a capital-spending figure standing in for a line the filer
    never published is a ceiling, and the free cash flow built on it a
    floor (AB19/AB20/AB22). A row the council COMPUTED carries null -
    the direction of a bound can invert through arithmetic, and nothing
    here can know which way, so the publisher declines to guess rather
    than print a bound it cannot stand behind.

    QUOTES, not merely cites. A sizing row may RESTATE a percentage as
    the fraction its id is pinned to, and for a fall that restatement
    takes the magnitude - which reverses the order. A signed ceiling on
    a drawdown recorded as a negative percentage says the true value is
    no HIGHER than that; as a positive depth the same statement is a
    FLOOR, saying the true fall is no shallower. Copying the word
    across would have told Atlas a fall can only be shallower when it
    can only be deeper (audit finding r3-2). Flipping the word instead
    is not sound either: a signed FLOOR admits values above zero, where
    the magnitude is bounded in neither direction. So the same policy
    the paragraph above states applies here - a transformed reading
    carries no bound.

    Read from the frozen pack, never from the chairman: his contract has
    no field to write it in."""
    ids = [rid for rid in fact_ids if rid is not None]
    if len(ids) != 1 or ids[0] not in facts:
        return None
    fact = facts[ids[0]]
    if (row.get("value") != fact.get("value")
            or row.get("unit") != fact.get("unit")):
        return None
    return fact.get("bound") or None


def _tag_rows(rows, id_key, facts):
    """Every hand-off row, with its bound tag resolved from the pack."""
    tagged = []
    for row in rows:
        cited = row.get(id_key)
        if not isinstance(cited, list):
            cited = [cited]
        entry = dict(row)
        entry["bound"] = _bound_of(row, cited, facts)
        tagged.append(entry)
    return tagged


def assemble_and_publish(run_dir):
    """Assemble the verdict from the chairman's final document (or the
    draft, degraded, when the audit did not run), validate it, write
    verdict.json and atlas-envelope.json, and record the hash. Returns the
    verdict hash. Raises PublishRefusal on mechanical defects only."""
    events = runrecord.read_events(run_dir)
    # Owner ruling M5, before anything else: a record already carrying a
    # publication event belongs to a run that died inside the publication
    # window - it is never resumed and never republished (round-11
    # finding).
    if any(e["event"] in ("publish_authorized", "published")
           for e in events):
        raise PublishRefusal("a publication event already stands in the "
                             "record; a run interrupted mid-publication "
                             "is dead and is discarded whole (M5)")
    state = canonical.read_json(os.path.join(run_dir, "state.json"))
    if state["state"] != "PUBLISH":
        raise PublishRefusal("the run is in state %s, not PUBLISH; an "
                             "unfinished run publishes nothing"
                             % state["state"])
    invocation = canonical.read_json(os.path.join(run_dir,
                                                  "invocation.json"))
    pack_path = os.path.join(run_dir, "pack", "pack.json")
    pack_hash = canonical.sha256_file(pack_path)
    if pack_hash != invocation["pack_sha256"]:
        raise PublishRefusal("the pack on disk no longer hashes to the "
                             "frozen value; publishing nothing")
    frame = _accepted_answer(run_dir, events, "frame")
    challenged_path = os.path.join(run_dir, "chair", "draft-verdict.json")
    if not os.path.exists(challenged_path):
        raise PublishRefusal("no challenged draft is on record; the run is "
                             "unfinished")
    challenged = canonical.read_json(challenged_path)
    challenge = _challenge_record(run_dir, events)
    warnings = []
    degraded_from = None
    if challenge["status"] == "success":
        resolve_path = os.path.join(run_dir, "chair", "resolve.json")
        if not os.path.exists(resolve_path):
            raise PublishRefusal("the challenge succeeded but no resolved "
                                 "document is on record; the run is "
                                 "unfinished")
        resolve = canonical.read_json(resolve_path)
        final = resolve["final_verdict"]
        dispositions = resolve["dispositions"]
        appendix, raise_warnings = build_change_appendix(
            challenged, final, challenge["endorsement"])
        warnings.extend(raise_warnings)
    else:
        final = dict(challenged)
        dispositions = []
        appendix = []
        if challenged["rating"] in ("buy", "strong_buy"):
            final["rating"] = "hold"
            degraded_from = challenged["rating"]
            appendix.append({"field": "rating",
                             "before": challenged["rating"],
                             "after": "hold",
                             "label": "degradation_cap"})
        warnings.append(
            "The outside audit did not run (%s). Nothing stronger than "
            "hold publishes on a failed audit; this document was not "
            "challenged by the cross-model auditor."
            % (challenge["failure_reason"] or challenge["status"]))
    warnings.extend(endorsement_note(final["rating"],
                                     challenge["endorsement"]))
    provenance = _provenance(run_dir, events, invocation,
                             challenge["challenger_tokens"],
                             challenge["model_requested"])
    subject = invocation["subject"]
    pack = canonical.read_json(pack_path)
    tier1_by_id = {fact["id"]: fact
                   for fact in (pack.get("capture") or {}).get("tier1", [])}
    # The scenario block is computed ONCE, from the frozen pack, and the
    # same object travels into both the verdict and the hand-off: Atlas
    # must never receive a different reading of the same ladder.
    verdict_scenario_rating = _scenario_rating(
        final, subject, pack, run_dir, events)
    if degraded_from is not None:
        verdict_scenario_rating = degrade_scenario_rating(
            verdict_scenario_rating, degraded_from, final["rating"])
    verdict = {
        "schema_version": "1.4.0",
        "run_id": invocation["run_id"],
        "subject": subject,
        "question_verbatim": invocation["question_verbatim"],
        "frame": frame,
        "rating": final["rating"],
        "conviction_rationale": final["conviction_rationale"],
        "mispricing": final["mispricing"],
        "scenario_rating": verdict_scenario_rating,
        "tripwires": final["tripwires"],
        "sizing_inputs": final["sizing_inputs"],
        "constituent_notes": final.get("constituent_notes"),
        "evidence_dependencies": final["evidence_dependencies"],
        "challenge": {
            "status": challenge["status"],
            "model_requested": challenge["model_requested"],
            "failure_reason": challenge["failure_reason"],
            "findings": challenge["findings"],
            "dispositions": dispositions,
            "endorsement": challenge["endorsement"],
            "summary": challenge["summary"],
            "change_appendix": appendix,
        },
        "warnings": warnings,
        "atlas_envelope": {
            "rating": final["rating"],
            "key_numbers": _tag_rows(final["key_numbers"],
                                     "pack_fact_id", tier1_by_id),
            "tripwires": final["tripwires"],
            "sizing_inputs": _tag_rows(final["sizing_inputs"],
                                       "pack_fact_ids", tier1_by_id),
            "scenario_rating": verdict_scenario_rating,
            # The subject's frozen shape travels to Atlas as captured -
            # copied from the invocation, never chair-authored. Since
            # AB23(1) that includes the identity, so the standalone
            # package can be verified without opening the verdict.
            "subject_kind": subject.get("kind"),
            "asset_class": subject.get("asset_class"),
            "product": subject.get("product"),
            "run_id": invocation["run_id"],
            "subject_name": subject.get("name"),
            "subject_ticker": subject.get("ticker"),
            "subject_listing": subject.get("listing"),
            "subject_currency": subject.get("currency"),
            # The audit state (AB23(2)): Atlas computes its effective
            # rating FROM the ceiling, and a consumer that had to open a
            # second file to learn a buy was capped was one refactor
            # away from acting on a bare rating. The warnings list is
            # final by this line - the AB16(5) note is appended above.
            "challenge_status": challenge["status"],
            "endorsement_highest_rating_supported": (
                (challenge["endorsement"] or {}).get(
                    "highest_rating_supported")),
            "warnings": warnings,
            "unknown_sizing_ids": [
                entry["id"] for entry in final["sizing_inputs"]
                if briefs.pinned_sizing_unit(entry["id"]) is None],
            "constituents": subject.get("constituents"),
            "vehicle": subject.get("vehicle"),
            "thesis_proportions": subject.get("thesis_proportions"),
            "for_atlas_note": frame["for_atlas"],
            "pack_hash": pack_hash,
            # A document cannot carry its own hash: null here, and the
            # standalone atlas-envelope.json carries the real value.
            "verdict_hash": None,
        },
        "provenance": provenance,
    }
    schema_path = os.path.join(SCHEMA_DIR, "verdict_schema.json")
    with open(schema_path, "rb") as handle:
        schema = json.loads(handle.read().decode("utf-8"))
    errors = validate.validate(verdict, schema)
    if errors:
        raise PublishRefusal("the assembled verdict does not match its own "
                             "schema:\n  " + "\n  ".join(errors))
    verdict_bytes = canonical.canonical_bytes(verdict)
    verdict_hash = canonical.sha256_bytes(verdict_bytes)
    runrecord.append_event(run_dir, "publish_authorized",
                           {"verdict_hash": verdict_hash})
    canonical.write_bytes_atomic(os.path.join(run_dir, "verdict.json"),
                                 verdict_bytes)
    envelope = dict(verdict["atlas_envelope"])
    envelope["verdict_hash"] = verdict_hash
    errors = validate.validate(
        envelope, schema["properties"]["atlas_envelope"])
    if errors:
        raise PublishRefusal("the Atlas envelope does not match its "
                             "schema:\n  " + "\n  ".join(errors))
    canonical.write_canonical_json(
        os.path.join(run_dir, "atlas-envelope.json"), envelope)
    # The verdict is now judgeable: one append-only row into the shared
    # ledger, its hash recorded so read-back proves the row is the row
    # this run wrote (owner ruling AC7, spec U7.1). Book-blind - identity,
    # never a size.
    row = ledger.build_row(verdict)
    ledger_row_hash, _written = ledger.append_row(row)
    runrecord.append_event(run_dir, "ledger_row_appended",
                           {"ledger_row_id": row["ledger_row_id"],
                            "row_hash": ledger_row_hash})
    runrecord.append_event(run_dir, "published",
                           {"verdict_hash": verdict_hash,
                            "warnings": len(warnings),
                            "appendix_rows": len(appendix)})
    return verdict_hash
