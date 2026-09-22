"""The correction loop (owner ruling AC15, P7) - a user correction never
rebuilds the pack.

The owner's words: "the evidence pack does not get rebuilt in full after
user corrections. That is pure waste of tokens. This is an absolute must."

This command patches ONE tier-1 fact's value in place, re-strikes every
derived figure that rests on it - so a stale dependent is never left
behind (the debrief's caveat) - records the correction on the capture's
`corrections` list with whether it only narrows a claim or rebuilds what
the seats reason from, keeps the audit block's record of what moved
honest, and re-runs the deterministic chain (gate -> freeze ->
sufficiency -> brief) with NO model call. Nothing here is gathered and
nothing is audited: it prints which facts' readings the correction made
stale, for a human to re-gather, and a rebuilding correction is sent back
to the outside auditor as a delta by a separate command
(`python -m council.bridge.codex_bridge evidence --delta`).

CLI:
    python -m council.evidence.correct <capture.json> --set <fact_id>=<value>
        [--source <text>] [--reason <text>] [--by <name>] --out <dir>

Exit codes: 0 the correction applied and the chain re-ran and passed,
3 the correction or a re-strike was refused (nothing was written), 1 crash.
"""

import argparse
import datetime
import os
import sys
import tempfile
from decimal import Decimal, Inexact, InvalidOperation, localcontext

from council.evidence import gate, freeze, sufficiency, brief
from council.lib import canonical

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
_FLOORS_PATH = os.path.join(_REPO_ROOT, "council", "floors", "floors.json")


def load_floors():
    return canonical.read_json(_FLOORS_PATH)


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _restrike_value(original_value, computed):
    """The re-struck figure as a string: the original fact's own decimal
    places where the new exact value fits them, so a re-struck integer
    stays an integer and a two-place figure stays two places; the exact
    plain form otherwise. Never scientific notation, never a rounded
    figure - the gate recomputes it exactly or this command has already
    refused."""
    with localcontext() as context:
        context.prec = gate._EXACT_PRECISION
        context.traps[Inexact] = True
        try:
            quantized = computed.quantize(Decimal(original_value))
            return format(quantized, "f")
        except (Inexact, InvalidOperation):
            return format(computed, "f")


def restrike(capture, changed_id):
    """Re-strike every derived figure resting on the changed fact, in
    dependency order (owner ruling AC15, P7). Returns (restruck, error):
    a list of {id, old, new} for each figure re-struck, or an error
    string when a figure cannot be re-struck as an exact decimal - in
    which case nothing is left half-done, because the caller works on a
    copy and discards it on error."""
    facts_by_id = {fact["id"]: fact for fact in capture["tier1"]}
    remaining = set(gate.derived_dependents(capture, [changed_id]))
    restruck = []
    progressed = True
    while remaining and progressed:
        progressed = False
        for fact_id in sorted(remaining):
            fact = facts_by_id[fact_id]
            derived = fact["derived"]
            operand_refs = {operand.get("fact_id")
                            for operand in derived["operands"]
                            if operand.get("fact_id") is not None}
            # A figure whose operands include another still-unsettled
            # dependent must wait until that one is re-struck.
            if operand_refs & remaining:
                continue
            for operand in derived["operands"]:
                reference = operand.get("fact_id")
                if reference is not None and reference in facts_by_id:
                    operand["value"] = facts_by_id[reference]["value"]
            try:
                values = [Decimal(operand["value"])
                          for operand in derived["operands"]]
                with localcontext() as context:
                    context.prec = gate._EXACT_PRECISION
                    context.traps[Inexact] = True
                    computed = gate._compute(derived["operation"], values)
            except Inexact:
                return restruck, (
                    "the figure '%s', struck from the corrected fact, has "
                    "no exact decimal value once '%s' changes (its division "
                    "no longer terminates) - it cannot be re-struck "
                    "deterministically. Correct it directly with its own "
                    "source, or re-gather the chain; nothing was written."
                    % (fact_id, changed_id))
            except (InvalidOperation, ArithmeticError) as exc:
                return restruck, (
                    "the figure '%s', struck from the corrected fact, "
                    "cannot be re-struck: %r; nothing was written."
                    % (fact_id, exc))
            old_value = fact["value"]
            new_value = _restrike_value(old_value, computed)
            fact["value"] = new_value
            if new_value != old_value:
                restruck.append({"id": fact_id, "change": "changed",
                                 "old": old_value, "new": new_value})
            remaining.discard(fact_id)
            progressed = True
    if remaining:
        return restruck, (
            "the figures %s rest on the corrected fact but could not be "
            "ordered for re-striking - a cycle among derived facts the gate "
            "would already refuse; nothing was written."
            % ", ".join("'%s'" % fid for fid in sorted(remaining)))
    return restruck, None


def _frame_cited_facts(capture, sections):
    """Every fact id the business frame's reading rests on, across the
    named sections and every frame in the capture (owner ruling AC15,
    P8). The union is what a rebuilding correction is measured against."""
    cited = set()
    for frame in (capture.get("business_frame") or {}).values():
        if "decisive_metrics" in sections:
            for row in frame.get("decisive_metrics") or []:
                cited.update(row.get("answered_by") or [])
        if "how_it_earns" in sections:
            for row in frame.get("how_it_earns") or []:
                cited.update(row.get("facts") or [])
        if "headline_decline_read" in sections:
            reading = frame.get("headline_decline_read") or {}
            cited.update(reading.get("facts") or [])
        if "what_is_changing" in sections:
            cited.update((frame.get("what_is_changing") or {}).get("facts")
                         or [])
    return cited


def _headline_ids(capture):
    """Every headline-pair fact id the capture could carry, subject and
    member suffixes included: a correction to one of these rebuilds what
    the seats reason from even where no frame cites it."""
    bases = set()
    for current, prior in gate.HEADLINE_PAIRS:
        bases.add(current)
        bases.add(prior)
    ids = set()
    for fact in capture.get("tier1", []):
        fact_id = fact["id"]
        for base in bases:
            if fact_id == base or fact_id.startswith(base + "__"):
                ids.add(fact_id)
    return ids


def classify_correction(capture, changed_id, restruck_ids, floors):
    """narrowing or rebuilding (owner ruling AC15, P8). Rebuilding when
    the corrected fact, or any figure struck from it, is one the business
    frame's reading rests on or a headline pair; narrowing otherwise. The
    sections that make it rebuilding are DATA in floors.json, so a ruling
    can widen or narrow the rule without a code change - the same
    discipline the revenue families live under. A new fact or a new
    derived chain would also rebuild, but this command sets an existing,
    non-derived fact's value only and can produce neither."""
    rule = floors.get("correction_reaudit") or {}
    sections = set(rule.get("rebuilding_frame_sections") or [])
    touched = {changed_id} | set(restruck_ids)
    if touched & _frame_cited_facts(capture, sections):
        return "rebuilding"
    if rule.get("rebuilding_on_headline_pair") and (
            touched & _headline_ids(capture)):
        return "rebuilding"
    return "narrowing"


def _update_audit_record(capture, moved):
    """Keep the audit block's record of what moved honest after a
    correction (owner ruling AC13.2): every corrected or re-struck figure
    is listed, and the recorded hash is set to the pack the council would
    now sit on, so the sufficiency gate's what-moved check stays
    satisfied. A rebuilding correction is stopped separately, by the P8
    check on the corrections list, until a delta re-audit covers it."""
    block = capture.get("evidence_challenge")
    if not block:
        return
    existing = {entry["id"]: entry
                for entry in block.get("post_audit_changes") or []}
    for entry in moved:
        if entry["id"] in existing:
            # The auditor's own reading of this id is kept as `old`; only
            # what the council now sits on moves.
            existing[entry["id"]]["new"] = entry["new"]
        else:
            existing[entry["id"]] = dict(entry)
    # A correction that reverts one this record already carried returns the
    # figure to the value the auditor read - `old == new`, nothing moved -
    # so it is dropped rather than left telling the owner's page and every
    # seat that a figure changed after the audit when it has not (audit
    # round 1, r1-6). Two guards keep the drop honest:
    #   - only an id THIS correction touched is pruned: a bridge-listed
    #     change whose DIGEST moved while its value string did not is
    #     `old == new` too and is a real change that must stand;
    #   - the id must not carry a source change the auditor never folded
    #     into a baseline, because `apply_correction` changes only value
    #     and (optionally) source and never unit or date. A value that
    #     returned with no such source change is the whole fact back at the
    #     audited digest; a value that returned while the source still
    #     differs from what the auditor read is a real change that must
    #     stand (audit round 2, r2-1). A source change that HAS been
    #     re-audited is part of the new baseline, so it no longer differs
    #     and does not keep the id alive (audit round 3, r3-1).
    # (An exact drop would compare each fact against a STORED audited
    # per-fact baseline; the block carries none, so this proxy stands. Its
    # only residual is a phantom old==new entry - the safe over-report
    # direction, never a hidden change - proposed for the owner in BUILD-LOG.)
    moved_ids = {entry["id"] for entry in moved}
    sourced_ids = {c.get("fact_id") for c in capture.get("corrections") or []
                   if c.get("source") is not None and not c.get("reaudited")}
    block["post_audit_changes"] = [
        existing[key] for key in sorted(existing)
        if not (key in moved_ids
                and existing[key]["old"] == existing[key]["new"]
                and key not in sourced_ids)]
    block["post_audit_sha256"] = gate.evidence_body_sha256(capture)


def apply_correction(capture, fact_id, new_value, source, reason, by,
                     floors, at=None):
    """Patch one fact in place, re-strike its dependents, record the
    correction. Mutates `capture`. Returns {"error": str} on refusal
    (nothing usable was changed - the caller discards the copy) or
    {"correction": .., "restruck": [ids], "stale": [ids]} on success."""
    facts_by_id = {fact["id"]: fact for fact in capture["tier1"]}
    if fact_id not in facts_by_id:
        return {"error": "no fact '%s' is in this capture - a correction "
                         "changes a fact that exists; to add one is to "
                         "re-gather, which is a human act this command does "
                         "not do" % fact_id}
    fact = facts_by_id[fact_id]
    if fact.get("derived"):
        return {"error": "'%s' is a derived figure - it is struck from its "
                         "operands and re-struck when they change, never set "
                         "directly. Correct the fact it rests on instead."
                         % fact_id}
    old_value = fact["value"]
    if new_value == old_value:
        return {"error": "'%s' already reads '%s' - a correction changes a "
                         "value" % (fact_id, old_value)}
    fact["value"] = new_value
    if source is not None:
        fact["source"] = source
    restruck, error = restrike(capture, fact_id)
    if error is not None:
        return {"error": error}
    moved = ([{"id": fact_id, "change": "changed",
               "old": old_value, "new": new_value}] + restruck)
    classification = classify_correction(
        capture, fact_id, [item["id"] for item in restruck], floors)
    correction = {"fact_id": fact_id, "old": old_value, "new": new_value,
                  "source": source, "reason": reason,
                  "by": by or "unknown", "at": at or _now_utc(),
                  "classification": classification, "reaudited": False}
    capture.setdefault("corrections", []).append(correction)
    _update_audit_record(capture, moved)
    # Which readings are stale now, read from the SAME rule every durable
    # renderer uses (gate.stale_reading_ids), so the console message the
    # command prints cannot contradict the page and case files (audit round
    # 3, r3-2): a source-less move away and back is not stale, because the
    # original source supports the restored value. "Re-gather" is the human
    # act this command only names.
    stale = sorted(gate.stale_reading_ids(capture))
    return {"correction": correction,
            "restruck": [item["id"] for item in restruck],
            "stale": stale}


def _rerun_chain(capture, out_dir, floors):
    """Re-run gate -> freeze -> sufficiency -> brief over the corrected
    capture, with NO model call (owner ruling AC15, P7). Writes pack.json,
    freeze-record.json, sufficiency-result.json and brief.md into out_dir.
    Returns (ok, lines)."""
    lines = []
    checked = gate.validate_capture(capture, gate.load_capture_schema())
    if checked["result"] != "accepted":
        lines.append("gate: refused after the correction -")
        for reason in checked["reasons"]:
            lines.append("  - " + reason)
        return False, lines
    lines.append("gate: accepted")
    # Freeze twice and prove byte-identical, exactly as the freeze command
    # does, so a corrected pack is kept to the same determinism.
    pack = freeze.build_pack(capture)
    pack_a = os.path.join(out_dir, "pack.json")
    sha_a = canonical.write_canonical_json(pack_a, pack)
    with tempfile.TemporaryDirectory() as scratch:
        sha_b = canonical.write_canonical_json(
            os.path.join(scratch, "pack.json"), freeze.build_pack(capture))
    if sha_a != sha_b:
        lines.append("freeze: MISMATCH - the corrected pack does not freeze "
                     "byte-identically; nothing about it can be trusted")
        return False, lines
    canonical.write_canonical_json(
        os.path.join(out_dir, "freeze-record.json"),
        {"pack_sha256": sha_a, "byte_identical": True,
         "tier1_count": len(capture["tier1"]),
         "tier2_count": len(capture["tier2"])})
    lines.append("freeze: byte-identical - sha256 %s" % sha_a)
    outcome = sufficiency.check(pack, floors)
    canonical.write_canonical_json(
        os.path.join(out_dir, "sufficiency-result.json"), outcome)
    if outcome["result"] != "pass":
        lines.append("sufficiency: refused - %s"
                     % (outcome.get("message") or "").splitlines()[0])
        return False, lines
    lines.append("sufficiency: pass (%d requirement(s) checked)"
                 % outcome.get("requirements_checked", 0))
    usage = _capture_usage_beside(out_dir)
    page = brief.render(pack, sha_a, usage)
    canonical.write_bytes_atomic(os.path.join(out_dir, "brief.md"),
                                 page.encode("utf-8"))
    lines.append("brief: rebuilt at zero model cost")
    return True, lines


def _capture_usage_beside(out_dir):
    """The capture stage's own cost sidecar, if it sits in out_dir, so the
    rebuilt one-page brief prints what the full one did; None otherwise -
    brief.render tolerates it."""
    path = os.path.join(out_dir, "capture-usage.json")
    if os.path.isfile(path):
        try:
            return canonical.read_json(path)
        except ValueError:
            return None
    return None


def _invalidate_reviewed_evidence(capture_path):
    """A correction changes the pack, so the reviewed-mode approval AND the
    one-page brief taken on the pre-correction evidence no longer describe
    what the council would now sit on. Remove both from the sitting's
    evidence folder - the one holding this capture (audit round 1, r1-5;
    round 2, r2-3). The corrected brief is rebuilt under --out: when that is
    this same folder the chain regenerates it here, and when it is
    elsewhere the host refuses the sitting until a corrected page is
    generated - it will NOT accept a re-approval taken on the stale page,
    which it checks only for existence. An unattended sitting carries no
    approval, so only the brief is removed there. The removal is done
    BEFORE the corrected capture is written, so a crash between the two
    leaves the OLD evidence needing a fresh page and approval - harmless -
    never the corrected evidence wearing a page and approval nobody gave it.
    The full evidence document (P6, sub-charge b) is removed for the same
    reason and is the one a reviewed sitting actually approves, so removing
    it forces a fresh full document before re-approval (audit sub-charge b,
    r1-3 correction path). `approval.json`/`brief.md`/`EVIDENCE-FULL.md` are
    the names the host and runbook use. Returns what was removed."""
    evidence_dir = os.path.dirname(os.path.abspath(capture_path))
    removed = []
    for name, words in (("approval.json", "the reviewed-mode approval"),
                        ("brief.md", "the one-page brief"),
                        ("EVIDENCE-FULL.md", "the full evidence document")):
        path = os.path.join(evidence_dir, name)
        if os.path.isfile(path):
            os.remove(path)
            removed.append(words)
    return removed


_USAGE = ("usage: python -m council.evidence.correct <capture.json> "
          "--set <fact_id>=<value> [--source <text>] [--reason <text>] "
          "[--by <name>] --out <dir>")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="python -m council.evidence.correct", add_help=True,
        description="Correct one fact in place and re-run the chain at "
                    "zero model cost (owner ruling AC15, P7).")
    parser.add_argument("capture")
    parser.add_argument("--set", dest="setter", required=True,
                        metavar="fact_id=value",
                        help="the fact to correct and its new value")
    parser.add_argument("--source", default=None,
                        help="the corrected fact's new source sentence; "
                             "without it the fact's reading is named stale")
    parser.add_argument("--reason", default=None,
                        help="why the correction is made, recorded")
    parser.add_argument("--by", default=None,
                        help="who is making the correction, recorded")
    parser.add_argument("--out", required=True,
                        help="where pack.json, sufficiency-result.json and "
                             "brief.md are rebuilt")
    try:
        parsed = parser.parse_args(args)
    except SystemExit:
        return 1
    if "=" not in parsed.setter:
        print(_USAGE)
        print("  --set looks like price_last=15.64")
        return 1
    fact_id, new_value = parsed.setter.split("=", 1)
    fact_id = fact_id.strip()
    try:
        capture = canonical.read_json(parsed.capture)
        floors = load_floors()
        result = apply_correction(capture, fact_id, new_value,
                                  parsed.source, parsed.reason, parsed.by,
                                  floors)
        if "error" in result:
            print("correct: refused - " + result["error"])
            return 3
        # The corrected capture is written back in place BEFORE the chain
        # re-runs, so the pack the chain builds is the pack on disk.
        from council.bridge import codex_bridge
        # Remove the pre-correction approval and one-page brief from the
        # evidence folder before the corrected capture is written
        # (_invalidate_reviewed_evidence explains the order and the split
        # --out case). The corrected page is rebuilt below by _rerun_chain.
        invalidated = _invalidate_reviewed_evidence(parsed.capture)
        codex_bridge._write_capture(parsed.capture, capture)
        out_dir = os.path.abspath(parsed.out)
        os.makedirs(out_dir, exist_ok=True)
        ok, lines = _rerun_chain(capture, out_dir, floors)
        correction = result["correction"]
        print("correct: '%s' %s -> %s (%s)"
              % (fact_id, _short(correction["old"]),
                 _short(correction["new"]), correction["classification"]))
        if result["restruck"]:
            print("  re-struck %d dependent figure(s): %s"
                  % (len(result["restruck"]),
                     ", ".join("'%s'" % i for i in result["restruck"])))
        else:
            print("  no derived figure rested on it")
        if result["stale"]:
            print("  RE-GATHER (reading now stale, no new source given): %s"
                  % ", ".join("'%s'" % i for i in result["stale"]))
        if invalidated:
            print("  invalidated on this evidence (the correction changed "
                  "the pack): %s. Regenerate the one-page brief and approve "
                  "the corrected evidence before the council sits."
                  % ", ".join(invalidated))
        for line in lines:
            print("  " + line)
        if correction["classification"] == "rebuilding":
            print("  this correction REBUILDS what the seats reason from: a "
                  "delta re-audit is required before sufficiency passes - "
                  "run 'python -m council.bridge.codex_bridge evidence "
                  "--delta <capture.json> <run>/evidence/challenge' then "
                  "'evidence-record'.")
        return 0 if ok else 3
    except Exception as exc:
        print("correct crashed: %r" % (exc,))
        return 1


def _short(text):
    text = str(text)
    return text if len(text) <= 40 else text[:37] + "..."


if __name__ == "__main__":
    sys.exit(main())
