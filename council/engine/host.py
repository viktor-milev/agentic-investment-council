"""The stepped council host: python -m council.engine.host init|step|status.

The host is never a long-running process. `init` creates the run; each
`step` reads what is on disk, advances the run as far as it can (writing
seat requests, ingesting valid answers, transitioning state), and exits.
The hosting session loops: step -> dispatch the pending seats as isolated
subagents -> step again. All durable state lives in the run directory;
progress is derived from the append-only run record on every invocation,
so there is no in-memory state to lose.

Owner ruling M5, as this protocol carries it: dispatching pending work is
the protocol, never crash-resume. A seat invocation that dies without
writing its answer file simply never happened; an answer is recorded
atomically at the moment it is ingested; a run that fails validation twice
is FAILED and publishes nothing.
"""

import argparse
import copy
import json
import math
import os
import random
import re
import secrets
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, prose, subjects, validate  # noqa: E402
from council.engine import briefs, ladder, publisher  # noqa: E402
from council.engine import runrecord, seal  # noqa: E402
from council.bridge import codex_bridge  # noqa: E402
from council.evidence import brief, gate  # noqa: E402
from council.evidence import sufficiency as sufficiency_check  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_DIR = os.path.join(ROOT, "council", "schemas")
FLOORS_PATH = os.path.join(ROOT, "council", "floors", "floors.json")

ADVISOR_SEATS = briefs.ADVISOR_SEATS
# The SUGGESTED challenger model, from council/floors/seats.json (owner
# ruling AC24 with item 6). The request is written with the operator's
# choice - codex_bridge.challenger_choice: environment over the file.
CHALLENGER_MODEL = codex_bridge.DEFAULT_MODEL
CHALLENGE_STATUSES = ("success", "launch_failure", "timeout",
                      "malformed_output", "schema_failure",
                      "binding_failure", "internal_failure")
REQUIRED_SIZING_IDS = ("realized_volatility", "liquidity", "event_dates",
                       "drawdown_shape")
TERMINAL_STATES = ("DONE", "REFUSED", "FAILED")
DEFAULT_MINUTES_CAP = 90

# The evidence stage's own folder (owner ruling AC3, spec section U3.2).
# The mode is chosen ONCE, at the very start of the sitting; the go -
# where a person gives one - is taken on the one-page brief. Both files
# live beside the capture, the outside audit and its resolution, and the
# host copies them into the run so the run stands alone.
MODE_NAME = "mode.json"
APPROVAL_NAME = "approval.json"
CAPTURE_USAGE_NAME = "capture-usage.json"
# The one page itself. The run directory is the archive (RUNBOOK 5), so
# the page a person said go on rides in beside the choice and the go -
# an evidence folder cleared after the sitting must not take the exact
# wording of what was approved with it.
#
# A sitting whose one page was never generated does not start, in BOTH
# modes (architect ruling, register item P-U3-3). The approval file is
# written by the sitting agent, which is model output: without this
# check nothing at all stands between "Reviewed by <name> before the
# council sat." on the report's front and a page nobody could have read.
BRIEF_NAME = "brief.md"
# Owner ruling AC15 (P6): in reviewed mode the document a person approves
# is the WHOLE evidence rendered for a reader (python -m
# council.evidence.brief --full), not the one-page cut - the one page is
# its summary at the top. init refuses a reviewed sitting whose full
# document is missing; and because the go is taken ON this evidence (owner
# ruling AC3), the approval MUST name both what it approved - the sha256 of
# the full document - and the pack that document summarizes, or init
# refuses. It refuses too when either no longer matches: a document
# rewritten after it was read, or a pack the council was not handed. So the
# go can never stand over a document nobody approved or a pack nobody saw.
# The document rides into the run's archive beside the one page. (Register
# items P-U3d-3 and P-U3d-4.)
FULL_DOCUMENT_NAME = "EVIDENCE-FULL.md"
EVIDENCE_MODES = ("reviewed", "unattended")
# How far ahead of this machine's own clock a stamp written by the
# sitting may stand. The capture gate has carried exactly this allowance
# since its own audit, for exactly this reason: the owner has two
# machines, and a sitting captured on one and opened on the other must
# not be refused over a few seconds of drift. It is TAKEN from the gate
# rather than copied, so the council can never come to hold two
# different allowances for one clock (register item P-U3-4).
_CLOCK_SKEW_SECONDS = gate._CLOCK_SKEW_SECONDS
# The outside auditor's own folder inside the sitting's evidence
# directory, and the bridge's record of that call inside it - written
# on every path the call takes. The host reads the record and never
# the prompt: what the auditor was SENT is a number only the bridge
# can know (register item P-U3-8).
CHALLENGE_DIR = "challenge"
CHALLENGE_RESULT_NAME = "result.json"

_RUN_ID = "[a-z0-9][a-z0-9-]*"


class HostError(Exception):
    """A hard usage error: nothing was advanced."""


def _now_utc():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(text):
    """One recorded moment as an aware UTC datetime, or None where the
    string is not a moment. A stamp written without a zone is read as
    UTC: every clock in this pipeline is UTC, and refusing a sitting over
    a missing 'Z' would teach nobody anything."""
    import datetime
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        moment = datetime.datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=datetime.timezone.utc)
    return moment.astimezone(datetime.timezone.utc)


def _norm(text):
    return " ".join(str(text).split())


def _seat_schemas():
    with open(os.path.join(SCHEMA_DIR, "seat_answers.json"), "rb") as handle:
        doc = json.loads(handle.read().decode("utf-8"))
    return {name: schema for name, schema in doc.items()
            if isinstance(schema, dict)}


def _read_state(run_dir):
    return canonical.read_json(os.path.join(run_dir, "state.json"))


def _write_state(run_dir, state, detail):
    canonical.write_canonical_json(os.path.join(run_dir, "state.json"),
                                   {"state": state, "detail": detail})


# ------------------------------------------------------ the evidence stage


def _stage_json(evidence_dir, name, what):
    """One of the evidence stage's own files, read by path. Absence and
    unreadable bytes are refusals in the same words: the sitting cannot
    say what happened before it, so it does not start."""
    path = os.path.join(evidence_dir, name)
    if not os.path.exists(path):
        raise HostError("%s is missing - %s. %s"
                        % (path, what, _STAGE_HELP))
    try:
        return canonical.read_json(path)
    except ValueError as error:
        raise HostError("%s is not readable JSON (%s) - %s"
                        % (path, error, what))


_STAGE_HELP = ("The mode is chosen ONCE, at the very start of the sitting, "
               "and the capture stage records its own time and tokens; a "
               "run that cannot say which was chosen, or what the evidence "
               "cost, is not started (owner ruling AC3).")


def _refuse_a_future_stamp(what, stamp_text, moment, consequence):
    """Nothing the sitting wrote may be dated ahead of this machine's
    own clock (register item P-U3-4) - the mirror of P-U3-1's lower
    bound, and the sharper of the two.

    MEASURED before the fix, with an approval dated 2099-01-01: the run
    opened, the sitting's clock started in 2099, the elapsed time came
    out at -38,033,190 minutes, the budget-overrun event - the only
    record anywhere that a sitting missed its budget - could never fire,
    and the report's front page printed the negative number to the
    owner. A typo, a local time written as UTC, or the sitting agent
    stamping the file is all it takes."""
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    if (moment - now).total_seconds() <= _CLOCK_SKEW_SECONDS:
        return
    raise HostError(
        "%s is dated %s, ahead of this machine's own clock: it is stamped "
        "in the future, and nothing the sitting writes about itself can "
        "be. %s (A stamp up to %d seconds ahead stands, because the owner "
        "captures on one machine and sits on the other.)"
        % (what, stamp_text, consequence, _CLOCK_SKEW_SECONDS))


def _read_mode(evidence_dir, captured_at):
    """The mode, chosen at the start (owner ruling AC3)."""
    doc = _stage_json(evidence_dir, MODE_NAME,
                      "the sitting never recorded whether a person would "
                      "review the evidence or the council would run "
                      "unattended")
    mode = doc.get("mode")
    if mode not in EVIDENCE_MODES:
        raise HostError("the mode is %r; it is one of %s - 'reviewed' means "
                        "a person reads the one-page brief and approves it "
                        "before any seat is paid, 'unattended' means the "
                        "council sits without that step and the report says "
                        "so" % (mode, " or ".join(repr(word)
                                                  for word in EVIDENCE_MODES)))
    if not str(doc.get("chosen_by") or "").strip():
        raise HostError("the mode names nobody who chose it: 'chosen_by' is "
                        "the person who was asked, or 'atlas' where the "
                        "portfolio system invoked this sitting")
    chosen_at = _parse_iso(doc.get("at"))
    if chosen_at is None:
        raise HostError("the mode carries no readable moment in 'at' (%r): "
                        "the choice is made at the start of the sitting, so "
                        "when it was made is what proves it"
                        % (doc.get("at"),))
    captured = _parse_iso(captured_at)
    if captured is not None and chosen_at > captured:
        raise HostError(
            "the mode was chosen after the evidence existed: it is dated %s "
            "and the capture is dated %s. The choice is made at the very "
            "start of the sitting, before a single figure is gathered - a "
            "choice made afterwards is a choice made knowing what the "
            "evidence says" % (doc.get("at"), captured_at))
    # The check above needs the capture's own stamp; a pack that carries
    # none leaves the mode with no upper bound at all.
    _refuse_a_future_stamp(
        "the mode", doc.get("at"), chosen_at,
        "The mode is chosen at the very start of the sitting, which is "
        "not a moment that has yet to arrive.")
    return {"mode": mode,
            "chosen_by": str(doc["chosen_by"]).strip(),
            "at": str(doc["at"]).strip()}


def _require_brief(evidence_dir):
    """The one page itself, generated before the run opens - in BOTH
    modes (register item P-U3-3).

    Spec section U3.2 sequences the sitting's work around this page: in
    the reviewed mode a person says go ON it, and in auto-mode the run
    "proceeds after the brief is generated". Nothing enforced the
    sequence, so an approval could be written - and every seat paid -
    for a page that was never rendered, with the report's front page
    still printing that a person reviewed the evidence.

    A page of nothing is no page: the brief command writes its rendered
    text in one atomic write and can never leave an empty file, so zero
    bytes means the render did not happen."""
    path = os.path.join(evidence_dir, BRIEF_NAME)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise HostError(
            "%s is missing - the one-page evidence brief was never "
            "generated, and it is the page this whole stage is about: in "
            "the reviewed mode it is what a person reads and says go on, "
            "and in auto-mode it is the page the run is archived with. "
            "Generate it first: python -m council.evidence.brief "
            "<pack.json> --out %s" % (path, path))


def _read_approval(evidence_dir, mode, captured_at):
    """The go, taken on the brief. Required in reviewed mode; a
    contradiction in unattended mode, and a contradiction is never
    resolved silently."""
    path = os.path.join(evidence_dir, APPROVAL_NAME)
    if mode == "unattended":
        if os.path.exists(path):
            raise HostError(
                "this sitting chose auto-mode, and %s stands beside it. One "
                "of the two is wrong and the host will not guess which: "
                "either the mode was unattended and nobody approved "
                "anything, or a person did approve and the mode should say "
                "'reviewed'" % path)
        return None
    doc = _stage_json(evidence_dir, APPROVAL_NAME,
                      "this sitting chose the reviewed mode, so no seat is "
                      "paid until a person has read the one-page brief and "
                      "said go")
    if not str(doc.get("by") or "").strip():
        raise HostError("the approval names nobody: 'by' is the person who "
                        "read the brief")
    approved_at = _parse_iso(doc.get("at"))
    if approved_at is None:
        raise HostError("the approval carries no readable moment in 'at' "
                        "(%r): the sitting's 1.5-hour clock starts there"
                        % (doc.get("at"),))
    if not str(doc.get("note") or "").strip():
        raise HostError("the approval's note is empty: 'note' says what was "
                        "checked or changed, and an approval that says "
                        "nothing records nothing")
    captured = _parse_iso(captured_at)
    if captured is not None and approved_at < captured:
        raise HostError(
            "the approval predates the evidence it approves: it is dated %s "
            "and the capture is dated %s. Nobody read a one-page brief that "
            "did not exist yet, and the sitting's 1.5-hour clock starts at "
            "that stamp - an earlier one would start the clock before the "
            "evidence was gathered and count the capture stage's own hours "
            "against the council" % (doc.get("at"), captured_at))
    _refuse_a_future_stamp(
        "the approval", doc.get("at"), approved_at,
        "The sitting's 1.5-hour clock starts at that stamp, so a stamp "
        "ahead of the clock makes the sitting appear to have taken "
        "negative time: the budget it is measured against could never be "
        "missed, and the report's front page would print the negative "
        "number to the owner.")
    return {"by": str(doc["by"]).strip(), "at": str(doc["at"]).strip(),
            "note": str(doc["note"]).strip()}


def _rendered_full_sha256(evidence_dir, pack_doc, pack_sha256):
    """The sha256 of the full evidence document as it renders from the pack the
    council was handed and the capture-cost sidecar beside it, through the ONE
    renderer the brief command also calls (brief.render_full) so the two cannot
    drift. Both reviewed and unattended init compare the document against it."""
    given = str(pack_sha256 or "").strip().lower()
    usage = None
    usage_path = os.path.join(evidence_dir, CAPTURE_USAGE_NAME)
    if os.path.isfile(usage_path):
        try:
            usage = canonical.read_json(usage_path)
        except ValueError:
            usage = None
    rendered = brief.render_full(pack_doc, given, usage).encode("utf-8")
    return canonical.sha256_bytes(rendered)


def _require_full_document(evidence_dir, mode, captured_at, pack_sha256,
                           pack_doc):
    """The full evidence document, in reviewed mode (owner rulings AC15 P6
    and AC3). The document a person approves is the WHOLE evidence, not the
    one-page cut; a reviewed sitting whose full document is missing does not
    start.

    The go is taken ON this evidence (AC3), so it must be tie-able to the
    exact document and pack the council sits on. The approval MUST name both
    the sha256 of the full document it approved and the pack that document
    summarizes; init refuses when either is absent, when the document on disk
    no longer hashes to the recorded value (it was rewritten after it was
    read), or when the recorded pack is not the one the council was handed
    (the go was taken on a different pack). As the final check it re-renders
    the full document from the pack the council was handed and refuses unless
    the bytes are the ones that were approved, so the BODY - not only the head
    line - has to be the rendering of this pack. Returns the document's
    sha256, or None in the unattended mode. (Closes register items P-U3d-3,
    P-U3d-4 and P-U3d-7.)

    In the UNATTENDED mode the full document must still EXIST, as the record of
    what the council sat on, though no person approves it (owner ruling
    AC18(2), closing P-U3d-2): a missing document refuses the sitting, naming
    the file to produce. As that record it must also BE the rendering of the
    pack the council was handed, so init re-renders and compares as reviewed
    mode does, but with NO approval (architect ruling closing P-U6-15); the
    approval checks below are the reviewed mode's alone."""
    if mode == "unattended":
        path = os.path.join(evidence_dir, FULL_DOCUMENT_NAME)
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise HostError(
                "%s is missing - in the unattended mode the full evidence "
                "document must still exist as the record of what the council "
                "sat on, though no person approves it (owner ruling AC18). "
                "Generate it first: python -m council.evidence.brief "
                "<pack.json> --out %s --full" % (path, path))
        # AC18(2): the document IS that record, so it must be the rendering of
        # the pack the council was handed, not a stale one from another pack.
        # No person approves it, so re-render from the handed pack and refuse a
        # mismatch (architect ruling closing P-U6-15); no approval is involved.
        actual = canonical.sha256_file(path)
        expected = _rendered_full_sha256(evidence_dir, pack_doc, pack_sha256)
        if expected != actual:
            raise HostError(
                "%s does not belong to this evidence pack: it hashes to %s and "
                "the document rendered from the pack the council was handed "
                "hashes to %s. In the unattended mode this document stands as "
                "the record of what the council sat on (owner ruling AC18), so "
                "it must BE the rendering of this pack. Regenerate it: python "
                "-m council.evidence.brief <pack.json> --out %s --full."
                % (path, actual, expected, path))
        return None
    if mode != "reviewed":
        return None
    path = os.path.join(evidence_dir, FULL_DOCUMENT_NAME)
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise HostError(
            "%s is missing - in the reviewed mode the document a person "
            "approves is the WHOLE evidence, not the one page (owner ruling "
            "AC15). Generate it first: python -m council.evidence.brief "
            "<pack.json> --out %s --full" % (path, path))
    actual = canonical.sha256_file(path)
    # What was approved rides in the approval file beside who approved and
    # when; both hashes are read raw here because the approval dict the
    # stage returns keeps only who/when/what-changed.
    approval = {}
    approval_path = os.path.join(evidence_dir, APPROVAL_NAME)
    if os.path.isfile(approval_path):
        try:
            approval = canonical.read_json(approval_path) or {}
        except ValueError:
            approval = {}
    recorded_doc = str(approval.get("document_sha256") or "").strip()
    if not recorded_doc:
        raise HostError(
            "the approval does not record the full document it approved: "
            "'document_sha256' is missing. In the reviewed mode the go is "
            "taken ON this document (owner rulings AC15, AC3), so an approval "
            "that cannot name the document it approved is not that go. Record "
            "its sha256 (shasum -a 256 %s)." % path)
    if recorded_doc != actual:
        raise HostError(
            "the approval records approving a full document that hashes to "
            "%s, and the one at %s hashes to %s - the document was rewritten "
            "after it was approved. Approve the document the council will "
            "sit on." % (recorded_doc, path, actual))
    recorded_pack = str(approval.get("pack_sha256") or "").strip().lower()
    given = str(pack_sha256 or "").strip().lower()
    if not recorded_pack:
        raise HostError(
            "the approval does not record which pack it approved: "
            "'pack_sha256' is missing. The go is taken on the evidence of a "
            "named pack (owner ruling AC3); an approval that cannot name that "
            "pack is not a go on this evidence. Record the pack's sha256, "
            "which the full document prints at its head.")
    if recorded_pack != given:
        raise HostError(
            "the approval records approving the pack that hashes to %s, and "
            "the council was handed the pack that hashes to %s - the approval "
            "was taken on a different pack, so the council would sit on facts "
            "nobody approved. Approve the pack the council will sit on."
            % (recorded_pack, given))
    # The go is taken ON the document the person read (owner ruling AC3),
    # and that document NAMES the pack it summarizes on its head line. The
    # two checks above compare the APPROVAL's own recorded hashes; this one
    # reads the pack out of the bytes he actually approved (whose hash is
    # checked above) and refuses when the document describes a pack other
    # than the one the council was handed (register item P-U3d-5). Without
    # it a caller could render the document from one pack, record another
    # pack's hash in the approval and hand the council that other pack -
    # every check above passes while the person approved a document about a
    # different pack. Parsed from the one line the renderer prints; never
    # re-rendered. This reads the same file hashed above; one operator on
    # one machine, no concurrent writer (the envelope), so the two reads see
    # the same bytes (fix-checklist 8a).
    with open(path, encoding="utf-8") as handle:
        head_pack = brief.pack_sha256_at_head(handle.read())
    if head_pack is None:
        raise HostError(
            "the approved full document at %s does not name the pack it "
            "summarizes on its head line, so the council cannot confirm the "
            "document a person approved describes the pack it was handed "
            "(owner ruling AC3). Render it with python -m "
            "council.evidence.brief <pack.json> --out %s --full."
            % (path, path))
    if head_pack != given:
        raise HostError(
            "the approved full document at %s describes the pack that hashes "
            "to %s, and the council was handed the pack that hashes to %s - "
            "the document a person approved summarizes a different evidence "
            "pack. Approve the document rendered from the pack the council "
            "will sit on." % (path, head_pack, given))
    # Every check above trusts the document's OWN head line, which the sitting
    # agent writes and can edit: render the document from pack A, rewrite only
    # that one line to name pack B, record the edited document's hash and pack
    # B's hash, and hand the council pack B - the document hashes to what the
    # approval records, the recorded pack matches the pack handed in, and the
    # head line names pack B, so all three checks pass while the BODY a person
    # read still describes pack A (register item P-U3d-7). The go is taken ON
    # this evidence (owner ruling AC3), so the document approved must BE the
    # rendering of the pack the council sits on. The full document is
    # deterministic - no model call, no clock - and a pure function of the
    # pack and the capture-cost sidecar beside it: exactly the two inputs the
    # brief command read (`--out <evidence>/EVIDENCE-FULL.md` reads
    # `capture-usage.json` from that same folder). Re-render it here from the
    # pack init was handed and that same sidecar, through the ONE renderer the
    # brief command also calls (brief.render_full, so the two cannot drift),
    # and refuse unless the bytes hash to what was approved. A missing sidecar
    # is read as None here exactly as the brief command reads it; the run is
    # refused for it a moment later in _read_capture_usage.
    expected = _rendered_full_sha256(evidence_dir, pack_doc, pack_sha256)
    if expected != recorded_doc:
        raise HostError(
            "the approved full document at %s is not the rendering of this "
            "evidence pack: it hashes to %s, and the document rendered from "
            "the pack the council was handed hashes to %s. The go is taken ON "
            "this evidence (owner ruling AC3), so the document a person "
            "approved must BE the full rendering of the pack the council sits "
            "on - render it with python -m council.evidence.brief <pack.json> "
            "--out %s --full and approve that." % (path, recorded_doc,
                                                    expected, path))
    return actual


def _real_minutes(value):
    """A number of minutes this record can hold and the rest of the
    pipeline can use: not a true/false, not infinity or NaN, not
    negative, and not so large it cannot be a duration at all.

    `1e999` and `NaN` are valid JSON and this sidecar is hand-written by
    the capture session. Infinity is a float and is not below zero, so
    it passed the old guard - and then the run was CREATED, two events
    were written, and the third crashed on a value no record can hold,
    leaving a run directory with no state at all (closing pass, r7-4).
    The finiteness test is asked inside a try because it converts an int
    to a double first, and a 309-digit integer overflows that conversion
    (closing incremental, r8-3) - in a guard whose whole purpose is that
    every refusal happens BEFORE the run directory exists, and a
    traceback in place of the ruled refusal line is the one outcome that
    must not happen."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _challenge_result(evidence_dir):
    """The bridge's own record of the evidence-challenge call, or None
    where there is none to read. The bridge writes this file on EVERY
    path it takes - a refused call, a timeout, a good answer - and it is
    the council's own artifact, while the capture sidecar beside it is
    written by the capture session, which is model output.

    One reader, so the two figures this file carries - what the call
    cost and how much of the prompt went - can never be taken from two
    different snapshots of it."""
    path = os.path.join(evidence_dir, CHALLENGE_DIR,
                        CHALLENGE_RESULT_NAME)
    if not os.path.isfile(path):
        return None
    try:
        result = canonical.read_json(path)
    except ValueError:
        return None
    return result if isinstance(result, dict) else None


def _plain_count(value):
    """A whole number of things, or None where the record does not say
    one. The same shape `brief.challenge_tokens` reads the sidecar with,
    so the two sources are judged by one rule."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _challenge_prompt_bytes(result):
    """How many bytes of prompt the outside auditor was actually SENT, or
    None where nothing here can say.

    It is the bridge's own count, and only the bridge's. Two earlier
    answers were both wrong. The brief standing on disk proves nothing:
    the bridge writes it BEFORE its smoke test decides whether the paid
    call may be made, so a refused call left tens of thousands of bytes
    recorded as sent (closing pass, r7-2). The call's STATUS proves only
    that a process was started: a stalled model that never drains a
    prompt bigger than the operating system's pipe buffer is killed
    part-way through the write, and the rest of the prompt was never
    delivered (register item P-U3-8). The launcher is the one party that
    knows how much went, so it counts as it writes and the bridge
    records the count."""
    return _plain_count((result or {}).get("prompt_bytes_sent"))


def _attempted_challenge_tokens(result):
    """What the outside auditor's call COST, out of the bridge's own
    record: the SUM over every attempt the bridge made at this sitting's
    evidence audit (register item P-U3-14, architect's mechanism ruling
    2026-09-09).

    The runbook's own way of calling the auditor again is to delete
    `result.json`, which took the first call's cost with it - so the
    record, the verdict and the approved page could carry only the LAST
    call's tokens, and the owner's budget (AB11, AC8) is judged on that
    figure. The bridge now logs every attempt beside the result and
    carries the list into it, so the two calls can be added up.

    None where no attempt recorded a count at all - a legitimate outcome
    on a call whose event stream said nothing usable - and the sidecar
    then stands alone. A result written by an older bridge carries no
    list, and its single count is read exactly as it was before."""
    attempts = (result or {}).get("attempts")
    if not isinstance(attempts, list) or not attempts:
        return _plain_count((result or {}).get("usage_tokens"))
    counted = [_plain_count((attempt or {}).get("usage_tokens"))
               for attempt in attempts]
    counted = [count for count in counted if count is not None]
    return sum(counted) if counted else None


def _agreed_challenge_tokens(usage_doc, result):
    """What the outside auditor's call cost - one number, and the same
    number wherever it is read (register item P-U3-7).

    Two files carry it. `capture-usage.json` is written by the capture
    session, which is model output; `challenge/result.json` is written
    by the council's own bridge on every path the call takes. Nothing
    compared them, and a sidecar claiming 1 beside a bridge result
    recording 74,000 put 1 on the approved page and 1 in the published
    verdict - the figure the owner's budget acceptance is judged on
    (AB11, AC8).

    So: where the bridge recorded a count, that count is the answer and
    the sidecar must agree with it; where the bridge recorded none - a
    legitimate outcome on a call whose event stream said nothing usable
    - the sidecar stands alone. A disagreement is REFUSED rather than
    resolved: after the runbook's own documented re-dispatch the sidecar
    may carry the honest total of both calls while the bridge holds only
    the last, and a host that silently preferred either would sometimes
    publish the smaller. A silent sidecar beside a bridge that recorded
    the cost is refused the same way, so the page a person approves and
    the record the verdict carries can never say two different things.

    The refusal names what to do, and says plainly where there is
    nothing yet to do: after a re-dispatch NO value opens the sitting
    honestly, because the bridge keeps one result per call and the two
    calls cannot be added up. That gap is register item P-U3-14, and the
    line used to send the operator round it in a circle - it advised
    putting the honest total in the sidecar, which is the disagreement
    itself (closing full pass, r3-1)."""
    said = brief.challenge_tokens(usage_doc)
    recorded = _attempted_challenge_tokens(result)
    attempts = (result or {}).get("attempts")
    calls = len(attempts) if isinstance(attempts, list) else 1
    if recorded is not None and said != recorded:
        raise HostError(
            "the capture stage's sidecar says the outside auditor cost "
            "%s, and the council's own bridge recorded %d across %d call(s) "
            "at this sitting's evidence. One of the two is wrong and the "
            "host will not guess which: the owner's budget acceptance is "
            "judged on this figure, and the page a person approves prints "
            "it. The runbook takes this number from the bridge's own "
            "result.json, which now carries every attempt, so a "
            "RE-DISPATCHED audit is the two calls added up - put that "
            "total in the sidecar, or correct the total if it is the one "
            "that is wrong, and run this again."
            % ("nothing" if said is None else "%d tokens" % said, recorded,
               calls))
    return said if recorded is None else recorded


def _read_capture_usage(evidence_dir):
    """What the capture stage itself cost (owner ruling AC3). A missing
    sidecar is a refusal in BOTH modes: the stage that gathers the
    evidence was the one stage nobody was charged for."""
    doc = _stage_json(evidence_dir, CAPTURE_USAGE_NAME,
                      "the capture stage's own time and tokens are recorded "
                      "on every sitting")
    tokens = doc.get("tokens")
    minutes = doc.get("minutes")
    if not isinstance(tokens, int) or isinstance(tokens, bool) or tokens < 0:
        raise HostError("the capture stage's sidecar records %s tokens: it "
                        "is a whole number, and 0 only where the stage "
                        "truly cost nothing"
                        % ("no" if tokens is None else repr(tokens)))
    # A REAL number of minutes, not merely a number (closing pass, r7-4).
    if not _real_minutes(minutes):
        raise HostError("the capture stage's sidecar records %s minutes: it "
                        "is a real number of minutes"
                        % ("no" if minutes is None else repr(minutes)))
    # Owner ruling AC15 (P5(b)): the sidecar says whether its figures are
    # an ESTIMATE. The WULF sitting's capture cost was a ~700,000-token
    # estimate that nothing on record marked as one; the flag forces the
    # session to say so, and the report prints "estimated" beside the
    # figures where it is true. A session counter that was reset means the
    # true figure cannot be known and the flag is true.
    estimated = doc.get("estimated")
    if not isinstance(estimated, bool):
        raise HostError(
            "the capture stage's sidecar records %s for 'estimated': it is "
            "true or false - true where the token or minute figures are an "
            "estimate (a session counter was reset, say), false where they "
            "are counted. The report prints 'estimated' beside an estimated "
            "figure, and a figure that might be an estimate must say so"
            % ("no value" if estimated is None else repr(estimated)))
    # The one-page brief read this same file BEFORE this run existed and
    # printed what it found. Both readings go through the brief's own two
    # helpers, so the archived page and the published verdict can never
    # give one sitting two different answers (audit rounds 1 and 2, r1-4
    # and r2-1).
    result = _challenge_result(evidence_dir)
    challenge_tokens = _agreed_challenge_tokens(doc, result)
    prompt_bytes = _challenge_prompt_bytes(result)
    return {"tokens": tokens, "minutes": minutes,
            "model": brief.capture_model(doc),
            "estimated": estimated,
            "evidence_challenge_tokens": challenge_tokens,
            "evidence_challenge_prompt_bytes": prompt_bytes}


def _read_evidence_stage(evidence_dir, captured_at, pack_sha256, pack_doc):
    """Everything the sitting decided and spent before the run existed.
    Every refusal here happens before the run directory is created:
    nothing is half-started."""
    if not evidence_dir:
        raise HostError(
            "no evidence folder was named (--evidence-dir): it is the "
            "sitting's own folder, the one holding the capture, the outside "
            "audit and its resolution, and it carries %s, %s, %s and - in "
            "the reviewed mode - %s. %s"
            % (MODE_NAME, BRIEF_NAME, CAPTURE_USAGE_NAME, APPROVAL_NAME,
               _STAGE_HELP))
    if not os.path.isdir(evidence_dir):
        raise HostError("the evidence folder %s is not a directory"
                        % evidence_dir)
    mode = _read_mode(evidence_dir, captured_at)
    _require_brief(evidence_dir)
    approval = _read_approval(evidence_dir, mode["mode"], captured_at)
    _require_full_document(evidence_dir, mode["mode"], captured_at,
                           pack_sha256, pack_doc)
    usage = _read_capture_usage(evidence_dir)
    return {"mode": mode, "approval": approval, "usage": usage}


# ---------------------------------------------------------------- init


def init(runs_root, run_id, pack, pack_sha256, sufficiency, question_file,
         subject_json, config=None, evidence_dir=None):
    """Create the run. Returns (state, run_dir). Refuses (raises HostError,
    creating nothing) on a pack hash mismatch or bad arguments; creates the
    run in state REFUSED when the sufficiency result does not say pass -
    the council is never paid on an insufficient pack."""
    import re
    if not re.fullmatch(_RUN_ID, run_id):
        raise HostError("run id %r must match %s" % (run_id, _RUN_ID))
    with open(pack, "rb") as handle:
        pack_bytes = handle.read()
    actual = canonical.sha256_bytes(pack_bytes)
    if actual != str(pack_sha256).lower():
        raise HostError(
            "the pack file does not hash to the value given: expected %s, "
            "the file is %s; refusing to create the run" %
            (pack_sha256, actual))
    with open(sufficiency, "rb") as handle:
        sufficiency_bytes = handle.read()
    sufficiency_doc = json.loads(sufficiency_bytes.decode("utf-8"))
    if isinstance(subject_json, str) and subject_json.strip().startswith("{"):
        subject = json.loads(subject_json)
    else:
        subject = canonical.read_json(subject_json)
    subject_schema = _verdict_schema()["properties"]["subject"]
    errors = validate.validate(subject, subject_schema)
    if errors:
        raise HostError("the subject is not valid:\n  " + "\n  ".join(errors))
    pack_doc = json.loads(pack_bytes.decode("utf-8"))
    if "capture" not in pack_doc:
        raise HostError("the pack file is not a frozen pack: the capture "
                        "wrapper is missing - hand the host the freeze's "
                        "pack.json, never a raw capture")
    capture_doc = pack_doc["capture"]
    if "subject" in capture_doc and capture_doc["subject"] != subject:
        raise HostError("the subject given to init does not match the "
                        "pack's own subject")
    with open(question_file, "rb") as handle:
        question = handle.read().decode("utf-8").rstrip("\r\n")
    if not question.strip():
        raise HostError("the question file is empty")
    if _norm(question) != _norm(capture_doc.get("question_verbatim")):
        raise HostError("the question file does not carry the same words "
                        "as the frozen capture's own question - the "
                        "council answers the one question the evidence "
                        "was gathered for; refusing to create the run")
    cfg = {"minutes_cap": DEFAULT_MINUTES_CAP}
    for key, value in (config or {}).items():
        if key != "minutes_cap":
            raise HostError("unknown config key %r; the only knob is "
                            "minutes_cap" % key)
        cfg["minutes_cap"] = int(value)
    stage = _read_evidence_stage(evidence_dir,
                                 capture_doc.get("captured_at"), actual,
                                 pack_doc)
    run_dir = os.path.join(runs_root, run_id)
    if os.path.exists(run_dir):
        raise HostError("run directory already exists: %s (a dead run is "
                        "discarded whole, never reused - pick a new id)"
                        % run_dir)
    for sub in ("pack", "rpc", "blind", "challenge", "chair"):
        os.makedirs(os.path.join(run_dir, sub))
    canonical.write_bytes_atomic(os.path.join(run_dir, "pack", "pack.json"),
                                 pack_bytes)
    canonical.write_bytes_atomic(
        os.path.join(run_dir, "pack", "sufficiency-result.json"),
        sufficiency_bytes)
    invocation = {"run_id": run_id, "subject": subject,
                  "question_verbatim": question,
                  "pack_sha256": actual, "created_at": _now_utc(),
                  "config": cfg}
    canonical.write_canonical_json(os.path.join(run_dir, "invocation.json"),
                                   invocation)
    runrecord.append_event(run_dir, "run_created",
                           {"run_id": run_id, "pack_sha256": actual})
    # What the sitting decided and spent BEFORE this run existed, copied
    # into the record so the run stands alone (owner ruling AC3). The two
    # provenance files ride into the pack folder beside the evidence they
    # are about; neither is inside the pack's hash, because the pack IS
    # the evidence and who chose and who approved is provenance.
    for name in (MODE_NAME, CAPTURE_USAGE_NAME, APPROVAL_NAME, BRIEF_NAME,
                 FULL_DOCUMENT_NAME):
        source = os.path.join(evidence_dir, name)
        if os.path.isfile(source):
            with open(source, "rb") as handle:
                canonical.write_bytes_atomic(
                    os.path.join(run_dir, "pack", name), handle.read())
    runrecord.append_event(run_dir, "evidence_mode", dict(stage["mode"]))
    if stage["approval"] is not None:
        runrecord.append_event(run_dir, "evidence_approved",
                               dict(stage["approval"]))
    runrecord.append_event(run_dir, "capture_usage_recorded",
                           dict(stage["usage"]))
    word = (sufficiency_doc.get("result") or sufficiency_doc.get("status"))
    if word != "pass":
        reason = ("the sufficiency result says %r, not 'pass': the council "
                  "is never paid on an insufficient pack" % word)
        _write_state(run_dir, "REFUSED", reason)
        runrecord.append_event(run_dir, "run_refused", {"reason": reason})
        return "REFUSED", run_dir
    # The word alone is never trusted: the host re-runs the sufficiency
    # check itself, over the pack and the ruled floors, before a seat is
    # paid (audit finding r1-2).
    recomputed = sufficiency_check.check(
        pack_doc, canonical.read_json(FLOORS_PATH))
    if recomputed["result"] != "pass":
        named = "; ".join("%s (%s)" % (item.get("what"),
                                       item.get("why_needed"))
                          for item in recomputed.get("missing", [])[:3])
        reason = ("the sufficiency file says pass, but the host's own "
                  "re-check of the pack against the ruled floors does "
                  "not: %s" % (named or "the recomputation refused"))
        _write_state(run_dir, "REFUSED", reason)
        runrecord.append_event(run_dir, "run_refused", {"reason": reason})
        return "REFUSED", run_dir
    _write_state(run_dir, "INIT",
                 "run created; step to dispatch the frame seat")
    return "INIT", run_dir


def _verdict_schema():
    with open(os.path.join(SCHEMA_DIR, "verdict_schema.json"),
              "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _floors():
    """The ruled floors data, which carries the anchorless rating's own
    constants (ANCHORLESS-SPEC section 3)."""
    return canonical.read_json(FLOORS_PATH)


# ------------------------------------------------------------- context


class _Ctx(object):
    """Everything one step invocation derives from disk."""

    def __init__(self, run_dir):
        self.run_dir = run_dir
        self.invocation = canonical.read_json(
            os.path.join(run_dir, "invocation.json"))
        self.pack = canonical.read_json(
            os.path.join(run_dir, "pack", "pack.json"))
        self.sufficiency = canonical.read_json(
            os.path.join(run_dir, "pack", "sufficiency-result.json"))
        self.schemas = _seat_schemas()
        self.lines = []
        self.refresh()

    def refresh(self):
        self.events = runrecord.read_events(self.run_dir)
        self.requests = {}
        self.accepted = {}
        self.rejections = {}
        self.disposed = set()
        for event in self.events:
            name = event["event"]
            if name == "request_written":
                self.requests[event["number"]] = {
                    "seat": event["seat"],
                    "retry_of": event.get("retry_of")}
            elif name == "answer_accepted":
                self.accepted[event["seat"]] = event["number"]
                self.disposed.add(event["number"])
            elif name == "answer_rejected":
                self.rejections[event["seat"]] = (
                    self.rejections.get(event["seat"], 0) + 1)
                self.disposed.add(event["number"])
            elif (name == "headings_checked"
                  and event.get("outcome") == "reasked"):
                # Sent back for a missing heading: disposed, never a
                # rejection, so the seat keeps its one ordinary retry.
                self.disposed.add(event["number"])

    def say(self, text):
        self.lines.append(text)

    # -- paths ---------------------------------------------------------

    def rpc_path(self, name):
        return os.path.join(self.run_dir, "rpc", name)

    def answer_name(self, number, seat):
        return "%s-answer-%s.json" % (number, seat)

    def pending(self):
        out = []
        for number in sorted(self.requests):
            if number not in self.disposed:
                out.append((number, self.requests[number]["seat"]))
        return out

    # -- answer access -------------------------------------------------

    def answer(self, seat):
        number = self.accepted[seat]
        return canonical.read_json(
            self.rpc_path(self.answer_name(number, seat)))

    def frame(self):
        return self.answer("frame")

    def casefile(self):
        frame = self.frame()
        return briefs.render_casefile(self.pack, self.sufficiency,
                                      frame["question_for_council"],
                                      self.invocation["subject"])

    def advisor_markdowns(self):
        return {seat: self.answer(seat)["markdown"]
                for seat in ADVISOR_SEATS}

    def advisor_ladders(self):
        """Each seat's own scenario ladder where it gave one - the
        chairman sees the five side by side, and the record keeps them
        so his departures from the bench stay visible."""
        return {seat: self.answer(seat).get("scenario_ladder")
                for seat in ADVISOR_SEATS}

    def blind_mapping(self):
        path = os.path.join(self.run_dir, "blind", "draw.json")
        if os.path.exists(path):
            return canonical.read_json(path)["mapping"]
        seed = secrets.token_hex(16)
        order = list(ADVISOR_SEATS)
        random.Random(seed).shuffle(order)
        mapping = dict(zip(briefs.BLIND_LETTERS, order))
        canonical.write_canonical_json(path, {"seed": seed,
                                              "mapping": mapping})
        runrecord.append_event(self.run_dir, "blind_draw",
                               {"seed": seed, "mapping": mapping})
        self.say("blind draw recorded: letters A-E assigned to the five "
                 "advisor seats")
        return mapping


# ------------------------------------------------------- answer checks


# Unicode's Default_Ignorable_Code_Point ranges (inclusive), transcribed
# from DerivedCoreProperties.txt of Unicode 16.0.0 - the version this
# Python's unicodedata module carries. The stdlib does not expose the
# property itself, so the derived list travels here as constants
# (adjacent source rows merged; 4174 code points, the property's own
# total). These are the code points renderers show as NOTHING even when
# their categories fall outside the C and Z classes - soft hyphen,
# combining grapheme joiner, Hangul fillers, variation selectors, tag
# characters and their reserved neighbours (THEMES-B finding r3-1).
_DEFAULT_IGNORABLE = (
    (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C),
    (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F),
    (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
    (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))


def _visible(value):
    """A value counts as present only when at least one character
    actually renders: its category falls OUTSIDE Unicode's invisible
    categories - the C classes (controls, formats, surrogates,
    private use, unassigned) and the Z separators - AND it is not a
    default-ignorable code point from the table above, AND it is not
    U+2800 BRAILLE PATTERN BLANK, an empty-looking cell that is NOT
    default-ignorable, named by hand for that reason. History:
    dropping only Cf and whitespace let every other control pass
    (r12-1); the category classes alone let a combining grapheme
    joiner or a Hangul filler pass (THEMES-B r2-1, then r3-1).
    BOUNDARY, deliberate: beyond the named property plus the braille
    blank, render-odd typography (a bare combining mark, lookalike
    letters) is NOT policed here - a wider net is an open-ended
    chase, so moving this line is a new finding, not a longer list."""
    import unicodedata
    if value is None:
        return False
    for ch in str(value):
        if unicodedata.category(ch)[0] in "CZ":
            continue
        point = ord(ch)
        if point == 0x2800:
            continue
        if any(low <= point <= high
               for low, high in _DEFAULT_IGNORABLE):
            continue
        return True
    return False


def _sizing_value_reasons(sizing_id, unit, value):
    """Whether the VALUE says what its pinned unit means (AB23(6)).
    A unit label alone does not stop the misreading the ruling names:
    `fraction_annualized` beside the number 52 is still a percentage,
    and `iso_date` beside a sentence about the calendar is still a
    sentence. Returns the one reason it is refused, or nothing."""
    text = str(value).strip()
    meaning = briefs.SIZING_UNIT_MEANINGS[unit]

    def refuse(what):
        return ["sizing input %r is stated in %s (%s), but its value %r "
                "%s" % (sizing_id, unit, meaning, value, what)]

    if unit == "iso_date":
        dates = text.replace(",", " ").replace(";", " ").split()
        if not dates:
            return refuse("names no date at all")
        import datetime
        for one in dates:
            # The SHAPE first, then the calendar. This runtime's
            # fromisoformat also reads the basic and week-date forms -
            # `20260910` and `2026-W37` both parse, and a week date
            # resolves to a Monday nobody wrote (audit finding r1-2).
            try:
                if (len(one) != 10 or one[4] != "-" or one[7] != "-"):
                    raise ValueError(one)
                datetime.date.fromisoformat(one)
            except ValueError:
                return refuse("is not a date, nor a list of dates, "
                              "written as YYYY-MM-DD")
        return []
    try:
        number = float(text)
    except ValueError:
        return refuse("is not a number")
    if number != number or number in (float("inf"), float("-inf")):
        return refuse("is not a finite number")
    if unit == "fraction_annualized" and not 0 <= number < 5:
        return refuse("is not a fraction of 1 - a percentage written "
                      "here reads a hundred times too large")
    if unit == "fraction_of_price" and not 0 <= number <= 1:
        return refuse("is not a fall between nothing and the whole "
                      "price, counted downward as a positive depth")
    if unit == "USD_per_day" and number < 0:
        return refuse("is negative, and a day's traded value cannot be")
    return []


FRACTION_UNITS = ("fraction_annualized", "fraction_of_price")


def _is_percent_unit(unit):
    """The project's own test for a unit that says percent, reused
    verbatim from the anchorless bar (council/engine/ladder.py)."""
    text = str(unit or "")
    return "percent" in text.lower() or "%" in text


def _restated_percent(entry, fact, pinned):
    """Whether a single-cited pinned row is THE ONE restatement the
    contract allows: a percentage carried in the pack, published as the
    fraction the row's id is pinned to.

    It exists because two ruled requirements meet on one fact. The
    anchorless bar reads the five-year volatility as a PERCENTAGE and
    refuses any other unit, precisely so the bar cannot be wrong by a
    hundred (ladder._percent_fact); the hand-off publishes the same
    reading as a FRACTION (AB23(6)), for exactly the same reason.
    Without this the capture would have to carry one measurement twice,
    in two units, for two readers - and two copies of one number are a
    disagreement waiting to happen.

    Nothing here is taken on trust: the machine does the arithmetic. A
    fall recorded as a negative percentage publishes as the positive
    depth the ruling defines, in the same sentence
    briefs.SIZING_UNIT_MEANINGS carries.

    Returns None when the row is not a restatement at all (the ordinary
    exact quote applies), True when it restates its fact correctly, and
    False when it was meant as one and the arithmetic does not hold."""
    if pinned not in FRACTION_UNITS or entry.get("unit") != pinned:
        return None
    if not _is_percent_unit(fact.get("unit")):
        return None
    import decimal
    # EVERY decimal operation sits inside the guard, comparison
    # included. `Decimal("sNaN")` constructs happily and signals on the
    # comparison instead, so a chairman writing that one word raised
    # out of this checker, past _ingest_answers, and left the run in a
    # state no event explained - wedged again on every retry (audit
    # finding r3-1). A value this cannot read is a refused value, never
    # a crash.
    try:
        stated = decimal.Decimal(str(entry.get("value")).strip())
        published = decimal.Decimal(str(fact.get("value")).strip()) / 100
        if pinned == "fraction_of_price":
            published = abs(published)
        return stated == published
    except (ArithmeticError, ValueError):
        return False


def _sizing_unit_reasons(entry):
    """AB23(6): ONE unit per sizing-input id, so an automated reader can
    never take a fraction for a percentage. The ids were stable across
    all seven published sittings; the units were not.

    A row with no figure carries no unit and is left alone - a stated
    gap has nothing in it to misread. A row that HAS a figure carries
    the pinned unit and a value that means what the unit says. An id
    the ruling does not pin must declare its own unit, and the hand-off
    flags it."""
    sizing_id = entry.get("id")
    unit = entry.get("unit")
    value = entry.get("value")
    pinned = briefs.pinned_sizing_unit(sizing_id)
    if pinned is None:
        if _visible(unit):
            return []
        return ["sizing input %r is not one of the ids the ruling pins a "
                "unit to, so it must DECLARE its own unit - the hand-off "
                "flags an unknown id and the portfolio system refuses to "
                "guess what it is measured in. The pinned ids are: %s"
                % (sizing_id, ", ".join(sorted(briefs.SIZING_UNITS)))]
    if unit is None:
        if value is None:
            return []
        return ["sizing input %r carries a value with no unit; it must "
                "carry %r (%s)"
                % (sizing_id, pinned, briefs.SIZING_UNIT_MEANINGS[pinned])]
    if unit != pinned:
        return ["sizing input %r must be stated in %r (%s); it is stated "
                "in %r. The unit is pinned one per id, so quote a pack "
                "fact already in that unit, or compute the reading into "
                "it citing every operand, or set the value to null with "
                "the gap explained in the detail."
                % (sizing_id, pinned,
                   briefs.SIZING_UNIT_MEANINGS[pinned], unit)]
    if value is None:
        return []
    return _sizing_value_reasons(sizing_id, pinned, value)


def check_draft_verdict(draft, pack, schemas):
    """Every reason this draft verdict is refused, in plain words.
    Empty list = the draft stands."""
    reasons = validate.validate(draft, schemas["draft_verdict"])
    if reasons:
        return reasons
    mispricing = draft["mispricing"]
    magnitude = mispricing["magnitude"]
    arithmetic = mispricing["arithmetic"]
    if mispricing["read"] != "no_view" and (
            not _visible(magnitude) or not _visible(arithmetic)):
        reasons.append(
            "the mispricing read is %r but magnitude or arithmetic is "
            "null or blank: a priced read must carry both, written out "
            "in words" % mispricing["read"])
    if mispricing["read"] == "no_view" and (
            mispricing["magnitude"] is not None
            or mispricing["arithmetic"] is not None):
        reasons.append(
            "the mispricing read is no_view but magnitude or arithmetic "
            "carries a value: a no-view read carries null for both, as "
            "the contract states")
    kinds = {t["kind"] for t in draft["tripwires"]["reopening_triggers"]}
    if "price" not in kinds:
        reasons.append("tripwires must carry at least one PRICE reopening "
                       "trigger")
    if "event" not in kinds:
        reasons.append("tripwires must carry at least one EVENT reopening "
                       "trigger")
    for trigger in draft["tripwires"]["reopening_triggers"]:
        if trigger["kind"] == "price":
            if (not _visible(trigger.get("level"))
                    or not _visible(trigger.get("unit"))):
                reasons.append("a PRICE reopening trigger must carry a "
                               "usable level and unit; %r leaves one "
                               "null or blank" % trigger.get("detail"))
    for entry in draft["tripwires"]["invalidation_levels"]:
        for field in ("level", "unit", "meaning"):
            if not _visible(entry.get(field)):
                reasons.append(
                    "an invalidation level must carry a visible %s - "
                    "an uncrossable level is the worst blank there is"
                    % field)
    capture = pack.get("capture", {})
    pack_ids = ({fact["id"] for fact in capture.get("tier1", [])}
                | {p["id"] for p in capture.get("tier2", [])})
    sizing_id_list = [entry["id"] for entry in draft["sizing_inputs"]]
    for rid in sorted({sid for sid in sizing_id_list
                       if sizing_id_list.count(sid) > 1}):
        reasons.append("sizing input id %r appears more than once - each "
                       "sizing concept carries exactly one entry" % rid)
    sizing_ids = set(sizing_id_list)
    missing = [rid for rid in REQUIRED_SIZING_IDS if rid not in sizing_ids]
    if missing:
        reasons.append("sizing_inputs must carry all four required ids; "
                       "missing: %s" % ", ".join(missing))
    tier1_by_id = {fact["id"]: fact for fact in capture.get("tier1", [])}
    for entry in draft["sizing_inputs"]:
        reasons.extend(_sizing_unit_reasons(entry))
        cited = entry.get("pack_fact_ids", [])
        # A row rests on each fact ONCE. Citing one fact twice made the
        # row look computed to every check below - the exact-quote test
        # is `len(cited) == 1` - so any figure at all could ride one
        # real fact id, and the publisher read the same length and
        # dropped the fact's bound tag (audit finding r1-3).
        if len(set(cited)) != len(cited):
            reasons.append(
                "sizing input %r cites the same pack fact more than "
                "once - a row rests on each fact once, and a row "
                "resting on one fact quotes it exactly"
                % entry.get("id"))
        for rid in cited:
            if rid not in pack_ids:
                reasons.append("sizing input %r rests on %r, which is not "
                               "a fact or passage id in the pack"
                               % (entry.get("id"), rid))
        value = entry.get("value")
        if (value is not None and cited
                and all(rid not in tier1_by_id for rid in cited)):
            reasons.append(
                "sizing input %r rests on passages alone - passages "
                "cannot bind a figure however many are cited; cite the "
                "tier-1 facts the reading comes from, or set the value "
                "to null with the gap explained in the detail"
                % entry.get("id"))
        elif value is not None and not cited:
            reasons.append(
                "sizing input %r carries the value %r but cites no pack "
                "fact - a number from nowhere cannot enter the hand-off; "
                "cite the facts it reads from, or set the value to null "
                "with the gap explained in the detail"
                % (entry.get("id"), value))
        elif value is not None and len(cited) == 1:
            if cited[0] in tier1_by_id:
                fact = tier1_by_id[cited[0]]
                # A pinned row may restate a percentage as its own
                # fraction and nothing else; the machine checks that
                # arithmetic, and the date still quotes the fact.
                restated = _restated_percent(
                    entry, fact, briefs.pinned_sizing_unit(entry.get("id")))
                checked = (("value", "unit", "as_of") if restated is None
                           else ("as_of",))
                if restated is False:
                    reasons.append(
                        "sizing input %r restates the pack's %r (%s %s) "
                        "as %s, but %r is not that reading as a "
                        "fraction - a restatement moves the decimal "
                        "point and changes nothing else"
                        % (entry.get("id"), cited[0], fact.get("value"),
                           fact.get("unit"), entry.get("unit"),
                           entry.get("value")))
                for field in checked:
                    if entry.get(field) != fact.get(field):
                        reasons.append(
                            "sizing input %r cites only %r but its %s "
                            "%r does not match the pack's %r - a "
                            "single-cited reading quotes its fact "
                            "exactly; a computed reading cites every "
                            "operand"
                            % (entry.get("id"), cited[0], field,
                               entry.get(field), fact.get(field)))
            else:
                reasons.append(
                    "sizing input %r rests only on passage %r - a "
                    "passage cannot bind a figure (no unit travels "
                    "with it); cite the tier-1 facts the reading "
                    "comes from, or set the value to null with the "
                    "gap explained in the detail"
                    % (entry.get("id"), cited[0]))
    for dep in draft["evidence_dependencies"]:
        if dep not in pack_ids:
            reasons.append("evidence dependency %r is not a fact or passage "
                           "id in the pack" % dep)
    facts_by_id = {fact["id"]: fact for fact in capture.get("tier1", [])}
    passages_by_id = {p["id"]: p for p in capture.get("tier2", [])}
    for number in draft["key_numbers"]:
        ref = number.get("pack_fact_id")
        if ref is None:
            continue
        if ref not in pack_ids:
            reasons.append("key number %r cites pack fact %r, which is not "
                           "in the pack" % (number.get("name"), ref))
            continue
        if ref in facts_by_id:
            fact = facts_by_id[ref]
            for field in ("value", "unit", "as_of"):
                if number.get(field) != fact.get(field):
                    reasons.append(
                        "key number %r cites %r but its %s %r does not "
                        "match the pack's %r - quote the pack exactly"
                        % (number.get("name"), ref, field,
                           number.get(field), fact.get(field)))
        else:
            # A passage carries no unit field, so a passage-backed
            # number can never be FULLY bound - and a half-bound figure
            # in the hand-off is a mislabelling waiting to happen
            # (round-2 finding). Cite the tier-1 fact, or leave
            # pack_fact_id null for a computed number whose arithmetic
            # the rationale shows.
            reasons.append(
                "key number %r cites passage %r - a passage-backed "
                "number cannot be fully bound (no unit travels with a "
                "passage); cite a tier-1 fact by id, or set "
                "pack_fact_id to null for a computed number and show "
                "its arithmetic in the rationale"
                % (number.get("name"), ref))
    # ---- kind-aware checks (THEMES-BASKETS-SPEC section 6): the
    # subject's declared constituents, vehicle and theme block bind
    # what the verdict may tag, note and score.
    subject = capture.get("subject", {})
    declared = subjects.constituent_tickers(subject)
    vehicle = subject.get("vehicle")
    valid_tags = set(declared)
    if vehicle:
        valid_tags.add(vehicle["ticker"])
    tagged = ([("an invalidation level", entry) for entry
               in draft["tripwires"]["invalidation_levels"]]
              + [("a reopening trigger", entry) for entry
                 in draft["tripwires"]["reopening_triggers"]]
              + [("a falsifier row", entry) for entry
                 in draft["tripwires"]["falsifiers"]]
              + [("a sizing input", entry) for entry
                 in draft["sizing_inputs"]]
              + [("a constituent note", entry) for entry
                 in draft.get("constituent_notes") or []])
    for label, entry in tagged:
        tag = entry.get("constituent")
        if tag is not None and tag not in valid_tags:
            reasons.append(
                "%s names constituent %r, which the subject does not "
                "declare - a constituent tag quotes a declared "
                "constituent's ticker (or the vehicle's) exactly"
                % (label, tag))
    # A per-member sizing entry's id and its constituent tag must AGREE
    # (the chair contract: `<concept>` plus the member's own stated
    # suffix, with the tag set), and the four required subject-level
    # ids stay untagged -
    # Atlas must never receive a sizing row whose id names one member
    # and whose tag names another (audit finding THEMES-B r1-2).
    members = list(declared)
    if vehicle:
        members.append(vehicle["ticker"])
    if members:
        for entry in draft["sizing_inputs"]:
            sid = entry["id"]
            tag = entry.get("constituent")
            if sid in REQUIRED_SIZING_IDS:
                if tag is not None:
                    reasons.append(
                        "sizing input %r is one of the four required "
                        "subject-level ids but carries the constituent "
                        "tag %r - the required ids describe the "
                        "subject as a whole and stay untagged"
                        % (sid, tag))
                continue
            suffix_of = [t for t in members
                         if sid.endswith("__" + subjects.slug(t))]
            if tag is not None:
                if tag not in suffix_of:
                    reasons.append(
                        "sizing input %r carries the constituent tag "
                        "%r but its id does not end with that member's "
                        "own suffix __%s - a per-member entry's id and "
                        "tag name the same member"
                        % (sid, tag, subjects.slug(tag)))
            elif suffix_of:
                reasons.append(
                    "sizing input %r carries the member suffix of %s "
                    "but no constituent tag - a per-member entry "
                    "carries its member's ticker in the constituent "
                    "field" % (sid, " and ".join(sorted(suffix_of))))
            elif "__" in sid:
                reasons.append(
                    "sizing input %r is in the per-member form "
                    "<concept>__<ticker> but its suffix matches no "
                    "declared member - per-member entries name a "
                    "declared constituent (or the vehicle) by id "
                    "suffix and tag together" % sid)
    notes = draft.get("constituent_notes")
    if subjects.has_constituents(subject):
        named = [entry.get("constituent") for entry in notes or []]
        if not named:
            reasons.append(
                "the draft carries no constituent_notes - this subject "
                "names %d constituents, and the verdict writes exactly "
                "one short note per named constituent" % len(declared))
        else:
            for ticker in declared:
                count = named.count(ticker)
                if count == 0:
                    reasons.append(
                        "constituent_notes carries no entry for "
                        "constituent %s - one note per named "
                        "constituent, none missing" % ticker)
                elif count > 1:
                    reasons.append(
                        "constituent_notes carries %d entries for "
                        "constituent %s - exactly one note per named "
                        "constituent" % (count, ticker))
            for name in named:
                if name not in declared:
                    reasons.append(
                        "constituent_notes names %r, which is not a "
                        "declared constituent - none invented" % name)
            # The contract's required note content must be VISIBLE, not
            # merely non-empty: the schema's length rule cannot see
            # whitespace or invisible characters, and a nominal note
            # whose content is blank publishes a silently missing
            # record (audit finding THEMES-B r1-3).
            for entry in notes:
                name = entry.get("constituent")
                for field in ("role_in_thesis", "load_bearing_metric"):
                    if not _visible(entry.get(field)):
                        reasons.append(
                            "the constituent note for %s leaves %s "
                            "blank - a note states its content in "
                            "visible words, never whitespace or "
                            "invisible characters" % (name, field))
                tripwire = entry.get("tripwire")
                if tripwire is not None and not _visible(tripwire):
                    reasons.append(
                        "the constituent note for %s carries a blank "
                        "tripwire - state the trigger in visible "
                        "words, or leave the field null" % name)
    elif notes:
        reasons.append(
            "the draft carries constituent_notes but the subject "
            "declares no constituents - notes belong to basket and "
            "theme subjects with a named universe; leave the field "
            "null or empty here")
    theme = subjects.theme_block(subject)
    rows = draft["tripwires"]["falsifiers"]
    if theme:
        declarations = {f["id"]: f for f in theme["falsifiers"]}
        answered = {}
        for row in rows:
            fid = row.get("theme_falsifier_id")
            if fid is None:
                continue
            if fid not in declarations:
                reasons.append(
                    "a falsifier row carries theme_falsifier_id %r, "
                    "which matches no falsifier the subject declares"
                    % fid)
                continue
            answered.setdefault(fid, []).append(row)
        for fid, declaration in declarations.items():
            matched = answered.get(fid, [])
            if not matched:
                reasons.append(
                    "no falsifier row answers the subject's declared "
                    "falsifier %r - every declaration is scored in the "
                    "verdict, exactly one row per declared id" % fid)
                continue
            if len(matched) > 1:
                reasons.append(
                    "%d falsifier rows carry theme_falsifier_id %r - "
                    "exactly one row per declared falsifier"
                    % (len(matched), fid))
                continue
            row = matched[0]
            if not _visible(row.get("metric_identity_assumed")):
                reasons.append(
                    "the falsifier row for %r leaves "
                    "metric_identity_assumed null or blank - the row "
                    "names, in plain words, which metric the figure "
                    "and its prior period both measure" % fid)
            if declaration["kind"] == "level":
                prior = tier1_by_id.get(declaration.get("prior_fact_id"))
                if prior is None:
                    reasons.append(
                        "the declared falsifier %r names prior-period "
                        "fact %r, which is not a tier-1 fact in the "
                        "pack" % (fid, declaration.get("prior_fact_id")))
                    continue
                for row_field, fact_field in (
                        ("prior_period_value", "value"),
                        ("prior_period_unit", "unit"),
                        ("prior_period_as_of", "as_of")):
                    if row.get(row_field) != prior.get(fact_field):
                        reasons.append(
                            "the falsifier row for %r carries %s %r "
                            "but the pack's prior-period fact %r says "
                            "%r - the prior period is quoted exactly "
                            "as the pack states it"
                            % (fid, row_field, row.get(row_field),
                               prior["id"], prior.get(fact_field)))
            else:
                for row_field in ("prior_period_value",
                                  "prior_period_unit",
                                  "prior_period_as_of"):
                    if row.get(row_field) is not None:
                        reasons.append(
                            "the falsifier row for %r answers a %s "
                            "declaration but carries %s - only a level "
                            "carries a prior period; leave the three "
                            "prior fields null"
                            % (fid, declaration["kind"], row_field))
    else:
        for row in rows:
            if row.get("theme_falsifier_id") is not None:
                reasons.append(
                    "a falsifier row carries theme_falsifier_id %r but "
                    "the subject declares no theme block"
                    % row.get("theme_falsifier_id"))
    reasons.extend(check_scenario_rating(draft, subject, tier1_by_id))
    return reasons


def check_scenario_rating(draft, subject, tier1_by_id):
    """The scenario-earned rating (ANCHORLESS-SPEC section 3). For an
    asset with no earnings the ladder is not decoration: the rating is
    computed from it, and a chairman who states a rating his own ladder
    does not produce is refused. For an equity the ladder is welcome as
    supporting context and drives nothing.

    Empty list = the block stands."""
    reasons = []
    block = draft.get("scenario_rating")
    anchorless = subjects.is_anchorless(subject)
    if not anchorless:
        if block is None:
            return reasons
        if not block.get("aggregated"):
            reasons.append(
                "the subject is judged on the anchor basis, but its "
                "scenario ladder says it could not be aggregated - on "
                "this subject the ladder is supporting context only, so "
                "either build one or leave the field null")
            return reasons
        reasons.extend(
            "the supporting scenario ladder: %s" % reason
            for reason in ladder.check_shape(block, tier1_by_id))
        return reasons

    if block is None:
        reasons.append(
            "this asset has no earnings, so its rating is EARNED from a "
            "scenario ladder and cannot be stated without one - name the "
            "scenarios with their price outcomes and probabilities, or "
            "say the ladder could not be aggregated and rate monitor")
        return reasons

    if not block.get("aggregated"):
        if not _visible(block.get("not_aggregated_reason")):
            reasons.append(
                "the ladder is declared un-aggregatable but no reason is "
                "given - a watch-state is a judgment and says why")
        if draft["rating"] != "monitor":
            reasons.append(
                "the ladder could not be aggregated, so no expected "
                "result exists and no rating can be earned from it - the "
                "only honest answer is monitor, and this draft says %r"
                % draft["rating"])
        return reasons

    if block.get("not_aggregated_reason") is not None:
        reasons.append(
            "the ladder is aggregated but still carries a reason for not "
            "aggregating it - leave that field null")
    # The three inputs are named in the floors data, in ONE place, and
    # the ladder is bound to the fact it CLAIMS rather than to any
    # figure carried in the same unit: a funding rate is a percentage
    # too, and a bar built on 0.0091 instead of the 3.68 bill rate rates
    # a losing ladder hold (audit finding ANCHORLESS-B r1-4).
    ruled_inputs = (_floors().get("anchorless_rating") or {}).get(
        "bar_inputs") or {}
    for field, what, expected in (
            ("reference_price_fact_id", "the price the ladder is measured "
                                        "against",
             ruled_inputs.get("reference_price")),
            ("volatility_fact_id", "the asset's five-year realized "
                                   "volatility",
             ruled_inputs.get("volatility")),
            ("cash_rate_fact_id", "the cash rate the bar starts at",
             ruled_inputs.get("cash_prefix"))):
        fact_id = block.get(field)
        if fact_id is None:
            reasons.append(
                "the ladder names no %s - it is a frozen pack fact, and "
                "the rating is computed from it, so it is named by id"
                % what)
            continue
        if fact_id not in tier1_by_id:
            reasons.append(
                "the ladder names %r as %s, which is not a tier-1 fact in "
                "the pack - the bar's inputs are pack facts, never seat "
                "inventions" % (fact_id, what))
            continue
        if expected is None:
            continue
        fits = (fact_id.startswith(expected)
                if field == "cash_rate_fact_id" else fact_id == expected)
        if not fits:
            reasons.append(
                "the ladder reads %r as %s, but the ruled anchors name "
                "%r for that - a figure in the same unit is not the same "
                "figure, and the rating is computed from this one"
                % (fact_id, what, expected))
    if reasons:
        return reasons
    reasons.extend(ladder.check_shape(block, tier1_by_id))
    if reasons:
        return reasons
    try:
        computed = ladder.compute(block, tier1_by_id, _floors())
    except ladder.LadderError as failure:
        return ["the scenario ladder cannot produce a rating: %s" % failure]
    if computed["rating"] != draft["rating"]:
        reasons.append(
            "the draft rates this %s, but its own ladder earns %s: %s "
            "Change the ladder or change the rating - a rating the "
            "arithmetic does not produce is the failure this basis "
            "exists to prevent."
            % (draft["rating"].replace("_", " "),
               computed["rating"].replace("_", " "),
               " ".join(computed["arithmetic"][1:])))
    return reasons


def _check_frame(payload, ctx):
    errors = validate.validate(payload, ctx.schemas["frame"])
    if errors:
        return errors
    question = _norm(ctx.invocation["question_verbatim"])
    reasons = []
    # Each half is one or more verbatim passages, ONE PER LINE - a question
    # whose halves are scattered through the text is captured as several
    # exact spans, never as a paraphrase. Within a half the spans must
    # match at monotonically increasing offsets: a rearrangement of the
    # owner's own sentences is an edit, not a split (round-11 finding).
    cursor = 0
    for span in _frame_spans(payload["question_for_council"]):
        if span not in question:
            reasons.append("this line of question_for_council is not a "
                           "verbatim span of the owner's question: %r - "
                           "copy exact passages, one per line, never a "
                           "paraphrase" % span[:80])
            continue
        index = question.find(span, cursor)
        if index == -1:
            reasons.append("this line of question_for_council appears in "
                           "the owner's question only before the line "
                           "above it: %r - passages must appear in the "
                           "question's own order" % span[:80])
            continue
        cursor = index + len(span)
    for_atlas = payload["for_atlas"]
    if for_atlas is not None:
        atlas_spans = _frame_spans(for_atlas)
        if not atlas_spans:
            reasons.append("for_atlas must be null when the question has "
                           "no inventory half, never an empty string")
        council_text = _norm(payload["question_for_council"])
        atlas_cursor = 0
        for span in atlas_spans:
            if span not in question:
                reasons.append("this line of for_atlas is not a verbatim "
                               "span of the owner's question: %r - copy "
                               "exact passages, one per line, never a "
                               "paraphrase" % span[:80])
                continue
            if span in council_text:
                reasons.append("the two halves overlap: a for_atlas line "
                               "also appears inside question_for_council, "
                               "and that half travels to every seat - keep "
                               "the halves disjoint: %r" % span[:80])
            index = question.find(span, atlas_cursor)
            if index == -1:
                reasons.append("this line of for_atlas appears in the "
                               "owner's question only before the line "
                               "above it: %r - passages must appear in "
                               "the question's own order" % span[:80])
                continue
            atlas_cursor = index + len(span)
    if seal.inventory_hit(str(payload["question_for_council"])):
        reasons.append("question_for_council carries wording that belongs "
                       "to the inventory half and travels to no seat - "
                       "route it to for_atlas")
    return reasons


def _frame_spans(text):
    """The non-empty whitespace-normalized lines of one frame half."""
    return [_norm(line) for line in str(text).splitlines() if _norm(line)]


def _check_advisor(payload, ctx):
    errors = validate.validate(payload, ctx.schemas["advisor"])
    if errors:
        return errors
    # On an asset with no earnings every seat states its own ladder, so
    # the chairman aggregates real judgments and the record shows where
    # the seats disagreed (ANCHORLESS-SPEC section 3). The bracket check
    # is the chairman's: this seat is not told which fact prices the
    # subject, only what the case file says it costs.
    subject = (ctx.pack.get("capture") or {}).get("subject") or {}
    seat_ladder = payload.get("scenario_ladder")
    if subjects.is_anchorless(subject):
        if seat_ladder is None:
            return ["this asset has no earnings, so every seat states a "
                    "scenario ladder: at least three named outcomes, each "
                    "with a price, a probability and one sentence of "
                    "reasoning, the probabilities adding to 1"]
        shape = ladder.check_shape(seat_ladder, {})
        if shape:
            return ["your scenario ladder: " + reason for reason in shape]
    elif seat_ladder is not None:
        # This subject is rated on the anchor basis, so no seat was
        # asked for a ladder and neither the reviewer nor the chairman
        # is shown one. An unasked-for ladder would publish in the
        # record having been seen by nobody (audit finding
        # ANCHORLESS-B r1-9).
        return ["this subject is rated on the anchor basis and no "
                "scenario ladder was asked for: leave the field out. A "
                "ladder nobody asked for is read by no other seat and "
                "would publish unexamined"]
    # The seal and the reach scan read the seat's PROSE wherever it
    # writes prose: a lens named in a scenario's reasoning unblinds the
    # review exactly as one named in the essay would.
    text = payload["markdown"]
    for scenario in (seat_ladder or {}).get("scenarios") or ():
        text += "\n%s\n%s" % (scenario.get("name", ""),
                              scenario.get("rationale", ""))
    violations = seal.scan_advisor(text)
    reaches = seal.reach_scan(text, ctx.pack)
    if violations or reaches:
        return [seal.violation_reason(violations, reaches)]
    return []


def _check_reviewer(payload, ctx):
    """Returns (schema_errors, overrun). Overrun is judged only on an
    otherwise-valid answer. The reviewer reasons over the frozen pack like
    every seat: a URL reaching outside it is refused (the identity lenses
    of the blind seal do not apply to this seat)."""
    errors = validate.validate(payload, ctx.schemas["reviewer"])
    if errors:
        return errors, False
    reaches = seal.reach_scan(
        payload["markdown"] + "\n" + payload["synopsis"], ctx.pack)
    if reaches:
        return [seal.violation_reason([], reaches)], False
    words = len(payload["synopsis"].split())
    return [], words > 180


def _check_chair_draft(payload, ctx):
    errors = validate.validate(payload, ctx.schemas["chair_draft"])
    if errors:
        return errors
    reasons = check_draft_verdict(payload["draft_verdict"], ctx.pack,
                                  ctx.schemas)
    reaches = seal.reach_scan(json.dumps(payload), ctx.pack)
    if reaches:
        reasons.append(seal.violation_reason([], reaches))
    return reasons


def _challenge_findings(ctx):
    result = canonical.read_json(
        os.path.join(ctx.run_dir, "challenge", "result.json"))
    doc = result.get("findings") or {}
    return (doc.get("findings", []), doc.get("endorsement"),
            doc.get("summary"))


def _check_chair_resolve(payload, ctx):
    errors = validate.validate(payload, ctx.schemas["chair_resolve"])
    if errors:
        return errors
    reasons = []
    findings, _, _ = _challenge_findings(ctx)
    finding_ids = [f["id"] for f in findings]
    disposed = [d["finding_id"] for d in payload["dispositions"]]
    for fid in finding_ids:
        if disposed.count(fid) == 0:
            reasons.append("finding %r has no disposition; every finding "
                           "is disposed of by name" % fid)
        elif disposed.count(fid) > 1:
            reasons.append("finding %r is disposed of more than once" % fid)
    for fid in disposed:
        if fid not in finding_ids:
            reasons.append("disposition names %r, which is not a finding "
                           "the challenger returned" % fid)
    reasons.extend("final_verdict: %s" % r for r in check_draft_verdict(
        payload["final_verdict"], ctx.pack, ctx.schemas))
    reaches = seal.reach_scan(json.dumps(payload), ctx.pack)
    if reaches:
        reasons.append(seal.violation_reason([], reaches))
    return reasons


# ------------------------------------------------------ request writing


def _write_request(ctx, seat, retry_of=None, reason=None):
    number = "%03d" % (len(ctx.requests) + 1)
    answer_name = ctx.answer_name(number, seat)
    answer_path = os.path.abspath(ctx.rpc_path(answer_name))
    kwargs = {"retry_reason": reason}
    if retry_of:
        # A re-ask REPAIRS: the seat's own prior answer travels verbatim
        # so the rewrite cannot silently lose rules the first answer
        # followed (the acceptance sitting's charter, fix 2).
        prior_path = ctx.rpc_path(ctx.answer_name(retry_of, seat))
        try:
            with open(prior_path, "rb") as handle:
                kwargs["prior_answer"] = handle.read().decode(
                    "utf-8", errors="replace")
        except OSError:
            kwargs["prior_answer"] = None
    if seat == "frame":
        kwargs["question_verbatim"] = ctx.invocation["question_verbatim"]
    else:
        frame = ctx.frame()
        kwargs["casefile"] = ctx.casefile()
        kwargs["for_atlas"] = frame["for_atlas"]
        # EVERY seat that reads the case file is told what the subject
        # IS. The advisors need it as much as the chair does: their
        # answer contract and their evidence emphasis are both derived
        # from the asset class (ANCHORLESS-SPEC sections 3 and 6). Handed
        # only to the chair and the reviewer, the five advisors on an
        # asset with no earnings were briefed against the ANCHORED
        # contract - told to answer one key, refused for not carrying a
        # ladder, and re-asked from a brief that still showed them the
        # wrong contract (audit finding ANCHORLESS-A1 r1-6).
        kwargs["subject"] = ctx.invocation["subject"]
        if seat in briefs.ADVISOR_SEATS or seat == "reviewer":
            # The method paragraphs and the reviewer's table line name the
            # business frame's tables: only where the capture carries one.
            kwargs["framed"] = bool(
                (ctx.pack.get("capture") or {}).get("business_frame"))
            kwargs["taped"] = bool(
                (ctx.pack.get("capture") or {}).get("price_series"))
        if seat == "reviewer":
            kwargs["advisor_answers"] = ctx.advisor_markdowns()
            kwargs["advisor_ladders"] = ctx.advisor_ladders()
            kwargs["blind_mapping"] = ctx.blind_mapping()
        elif seat == "chair_draft":
            kwargs["advisor_answers"] = ctx.advisor_markdowns()
            kwargs["advisor_ladders"] = ctx.advisor_ladders()
            kwargs["reviewer_answer"] = ctx.answer("reviewer")
        elif seat == "chair_resolve":
            findings, endorsement, summary = _challenge_findings(ctx)
            kwargs["draft_verdict"] = ctx.answer(
                "chair_draft")["draft_verdict"]
            kwargs["findings"] = findings
            kwargs["endorsement"] = endorsement
            kwargs["summary"] = summary
            # The model the request actually named - the record, not
            # whatever the environment says now.
            kwargs["challenger_model"] = canonical.read_json(os.path.join(
                ctx.run_dir, "challenge", "request.json"))["model"]
    try:
        brief = briefs.build_brief(seat, ctx.invocation["run_id"],
                                   answer_path, **kwargs)
    except ValueError:
        if not kwargs.get("retry_reason"):
            raise
        # A quoted prior answer - or the refusal reason itself, which
        # can echo a colliding key from the rejected answer - happens
        # to contain the for_atlas text. An ordinary lexical collision,
        # not a leak by this host: fall back rather than stranding the
        # run nonterminal (REBUILD-ACCEPT findings r6-2 and r7-1). The
        # full reason already stands in the rejection event.
        kwargs["prior_answer"] = None
        try:
            brief = briefs.build_brief(seat, ctx.invocation["run_id"],
                                       answer_path, **kwargs)
            omitted = "the prior answer"
        except ValueError:
            kwargs["retry_reason"] = (
                "your previous answer was refused by a machine check; "
                "the stated reason could not travel with this brief "
                "because it collides with text that may reach no seat. "
                "Repair your answer against the contract below - the "
                "full reason is in the run record.")
            brief = briefs.build_brief(seat, ctx.invocation["run_id"],
                                       answer_path, **kwargs)
            omitted = "the prior answer and the stated reason"
        runrecord.append_event(ctx.run_dir, "retry_content_omitted", {
            "seat": seat, "request": number,
            "reason": "%s collide with the for_atlas text; the re-ask "
                      "carries a sanitized brief" % omitted})
    brief_bytes = brief.encode("utf-8")
    brief_name = "%s-brief-%s.md" % (number, seat)
    canonical.write_bytes_atomic(ctx.rpc_path(brief_name), brief_bytes)
    request = {"run_id": ctx.invocation["run_id"], "request_id": number,
               "seat": seat, "brief": "rpc/" + brief_name,
               "answer": "rpc/" + answer_name,
               "retry_of": retry_of, "reason": reason}
    canonical.write_canonical_json(
        ctx.rpc_path("%s-request-%s.json" % (number, seat)), request)
    runrecord.append_event(ctx.run_dir, "request_written",
                           {"number": number, "seat": seat,
                            "retry_of": retry_of,
                            "brief_bytes": len(brief_bytes)})
    ctx.refresh()
    if retry_of:
        ctx.say("re-asked %s (request %s, retry of %s): %s"
                % (seat, number, retry_of, reason))
    else:
        ctx.say("request %s written for %s" % (number, seat))
    return number


def _ingest_usage(ctx, number, seat):
    path = ctx.rpc_path("%s-usage.json" % number)
    if not os.path.exists(path):
        return
    try:
        usage = canonical.read_json(path)
    except ValueError:
        ctx.say("usage sidecar %s-usage.json is not valid JSON; ignored"
                % number)
        return
    runrecord.append_event(ctx.run_dir, "usage_recorded", {
        "number": number, "seat": seat,
        "tokens": usage.get("tokens"),
        "tool_calls": usage.get("tool_calls"),
        "minutes": usage.get("minutes"),
        "model": usage.get("model")})


def _fail(ctx, reason):
    _write_state(ctx.run_dir, "FAILED", reason)
    runrecord.append_event(ctx.run_dir, "run_failed", {"reason": reason})
    ctx.say("RUN FAILED: %s" % reason)


# ------------------------------------------------------- the prose measure


_PROSE_RULES = None


def _prose_rules():
    """The ruled prose thresholds and pattern lists, read once (owner ruling
    AC6). Data, never code: the council's voice lives in the briefs and here."""
    global _PROSE_RULES
    if _PROSE_RULES is None:
        _PROSE_RULES = prose.load_rules()
    return _PROSE_RULES


def _chair_measured_text(answer):
    """The chairman's prose the measure runs over, and the rationale's own word
    count. The gate measures the conviction rationale and the mispricing
    magnitude - the prose the report prints on the front - not the long
    synthesis and not the mispricing ARITHMETIC, which is quoted math with
    number ranges, never prose (report design audit section C3)."""
    verdict = (answer.get("final_verdict") if "final_verdict" in answer
               else answer.get("draft_verdict")) or {}
    rationale = verdict.get("conviction_rationale") or ""
    magnitude = ((verdict.get("mispricing") or {}).get("magnitude")) or ""
    text = rationale + ("\n\n" + magnitude if magnitude else "")
    return text, prose.count_words(rationale)


def _record_advisory_prose(ctx, number, seat, text):
    """Score one seat's prose and write it to the run record, advisory only -
    never re-asked (spec U6.4, architect Step 0). The report renders it in the
    collapsed appendix beside the seat's answer. Used for the advisors' and the
    reviewer's answers and, under distinct keys, the chairman's long synthesis
    prose - which the gate never measures."""
    score = prose.measure(text or "", _prose_rules())
    runrecord.append_event(ctx.run_dir, "prose_scored", {
        "seat": seat, "number": number, "judged": False,
        "over_threshold": False, "reask_count": 0, "warned": False,
        "score": score, "failures": []})


# The chairman's ONE prose re-ask travels on a DISTINCT seat per chair seat,
# so a prose rewrite is never validated or re-asked as a full chair document
# (owner ruling AC6, the architect's splice ruling): it carries only the
# rewritten measured prose fields, which the host splices onto the accepted
# original. Nothing but those two fields can change, so no number and no rating
# can move - by construction, not by a comparison after the fact.
_PROSE_REASK_SEATS = {"chair_draft": "chair_draft_prose",
                      "chair_resolve": "chair_resolve_prose"}

# The parent chair seat each prose seat belongs to, so the one prose re-ask's
# tokens are recorded under the chairman (audit finding P-U6-11).
_PROSE_REASK_CHAIR = {prose: chair
                      for chair, prose in _PROSE_REASK_SEATS.items()}

# A tripwire against a changed figure, NOT a number parser: digits with an
# optional sign, currency, decimal point, thousands commas, percent, and a
# scale letter or word - one regex, with a balanced "(...)" wrap kept as its
# own distinct token. Two texts carry the same figures when these
# tokens match IN ORDER after commas and whitespace are stripped; comparing them
# as an unordered set let a rewrite SWAP two figures' places and still pass,
# moving one figure onto a different claim the reader sees (audit finding r3-1).
# Reading the parentheses as nothing let a rewrite drop them and flip a negative
# figure to a positive one - "($10M)" to "$10M" - and splice (finding r7-2);
# normalising a wrap to a leading "-" then equated a natural-language aside
# "(20%)" with the explicit negative "-20%", so a sign-flip still spliced
# (finding r8-1). A balanced wrap is now its own token "($10m)", equal only to
# the same bracketed figure - never "-$10m", never the bare "$10m"; strictly
# more conservative, it can only make a rewrite unusable. A mere reformat ("$10
# million" -> "$10M") reads as a change and the rewrite is rejected; that is
# ACCEPTED - the accepted original then publishes warned, never a silently
# changed number (owner ruling AC6).
_NUMBER_TOKEN = re.compile(
    r"\(?[-+]?\$?\d[\d,]*(?:\.\d+)?%?"
    r"(?:\s?(?:[KMBT]|thousand|million|billion|trillion))?\)?",
    re.IGNORECASE)


def _number_tokens(text):
    tokens = []
    for token in _NUMBER_TOKEN.findall(text or ""):
        negative = token.startswith("(") and token.endswith(")")
        cleaned = re.sub(r"[(),\s]", "", token).lower()
        tokens.append("(" + cleaned + ")" if negative else cleaned)
    return tokens


def _chair_verdict(answer, seat):
    return answer["final_verdict" if seat == "chair_resolve"
                  else "draft_verdict"]


def _chair_prose_fields(answer, seat):
    """The measured prose fields the one re-ask may rewrite, as {key: text} -
    exactly what `_chair_measured_text` reads. The conviction rationale always;
    the mispricing magnitude only when the read is priced, because a `no_view`
    read carries a null magnitude the chair check requires stay null, so it is
    never asked for and never spliced (owner ruling AC6)."""
    verdict = _chair_verdict(answer, seat)
    fields = {"conviction_rationale": verdict.get("conviction_rationale") or ""}
    magnitude = (verdict.get("mispricing") or {}).get("magnitude")
    if isinstance(magnitude, str) and magnitude.strip():
        fields["mispricing_magnitude"] = magnitude
    return fields


def _splice_prose(original, seat, rewrite):
    """The published answer: the accepted ORIGINAL with only the measured prose
    fields replaced. The rating, every other structured field, the synthesis,
    the tripwires and the dispositions are the original's by construction -
    nothing the chair checked can change except the two prose fields (owner
    ruling AC6, the architect's splice ruling)."""
    spliced = copy.deepcopy(original)
    verdict = _chair_verdict(spliced, seat)
    verdict["conviction_rationale"] = rewrite["conviction_rationale"]
    if "mispricing_magnitude" in rewrite:
        verdict["mispricing"]["magnitude"] = rewrite["mispricing_magnitude"]
    return spliced


def _write_prose_reask(ctx, seat, original, failures):
    """Issue the chairman's ONE prose re-ask on the ordinary request path, as a
    new request kind (owner ruling AC6): return only the rewritten measured
    prose fields, as a small JSON object with exactly those keys, changing no
    number and no rating. It is never itself re-asked - the gate issues it at
    most once per gated document - and it counts against the token budget like
    any other call."""
    prose_seat = _PROSE_REASK_SEATS[seat]
    number = "%03d" % (len(ctx.requests) + 1)
    answer_name = ctx.answer_name(number, prose_seat)
    answer_path = os.path.abspath(ctx.rpc_path(answer_name))
    brief = briefs.build_prose_reask_brief(
        ctx.invocation["run_id"], answer_path,
        _chair_prose_fields(original, seat), failures)
    brief_bytes = brief.encode("utf-8")
    brief_name = "%s-brief-%s.md" % (number, prose_seat)
    canonical.write_bytes_atomic(ctx.rpc_path(brief_name), brief_bytes)
    request = {"run_id": ctx.invocation["run_id"], "request_id": number,
               "seat": prose_seat, "brief": "rpc/" + brief_name,
               "answer": "rpc/" + answer_name,
               "retry_of": None, "reason": "prose rewrite"}
    canonical.write_canonical_json(
        ctx.rpc_path("%s-request-%s.json" % (number, prose_seat)), request)
    runrecord.append_event(ctx.run_dir, "request_written",
                           {"number": number, "seat": prose_seat,
                            "retry_of": None, "brief_bytes": len(brief_bytes)})
    ctx.refresh()
    ctx.say("prose re-ask written for %s (request %s)" % (seat, number))
    return number


def _read_rewrite(ctx, seat, original, rewrite_path):
    """Read the chairman's small prose-rewrite object and either return the
    original SPLICED with it, or say why it is not usable (owner ruling AC6, the
    architect's splice ruling). Usable requires all of: well-formed JSON;
    EXACTLY the measured prose keys, no more and no fewer; each a non-empty
    string; the figures in each field unchanged from the original (the ordered
    list of number tokens); and the spliced answer still passing every chair
    check that
    reads those fields. Returns (spliced, None) or (None, reason)."""
    fields = _chair_prose_fields(original, seat)
    try:
        with open(rewrite_path, "rb") as handle:
            obj = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError) as error:
        return None, "the rewrite is not valid JSON (%s)" % error
    if not isinstance(obj, dict):
        return None, "the rewrite is not a JSON object"
    if set(obj) != set(fields):
        return None, ("the rewrite must carry EXACTLY the keys %s, not %s"
                      % (sorted(fields), sorted(obj)))
    for key, original_text in fields.items():
        value = obj[key]
        if not isinstance(value, str) or not value.strip():
            return None, "%r is not a non-empty string" % key
        if _number_tokens(value) != _number_tokens(original_text):
            return None, ("the figures in %r changed; a prose rewrite changes "
                          "no number" % key)
    spliced = _splice_prose(original, seat, obj)
    # Re-run the full chair check on the spliced answer. Only the two prose
    # fields differ from the accepted original, which already passed, so nothing
    # else can newly fail; this re-runs exactly the checks that read those
    # fields (the schema, the priced-read/magnitude rule, the reach scan). A
    # failure means the rewrite is not usable.
    reasons = (_check_chair_resolve(spliced, ctx) if seat == "chair_resolve"
               else _check_chair_draft(spliced, ctx))
    if reasons:
        return None, ("the spliced answer fails a chair check: %s"
                      % "; ".join(reasons))
    return spliced, None


def _apply_prose_rewrite(ctx, seat, original, original_number):
    """Process the answer to the one prose re-ask: splice it, or keep the
    accepted original. Writes the disk state - the spliced answer and its
    accept, or a rejection that disposes the re-ask - BEFORE the caller records
    the gated score (the finalization marker), so a crash before that marker
    re-derives to the same outcome. Returns (published_answer, its number)."""
    prose_seat = _PROSE_REASK_SEATS[seat]
    prose_number = next(number for number, req in ctx.requests.items()
                        if req["seat"] == prose_seat)
    rewrite_path = ctx.rpc_path(ctx.answer_name(prose_number, prose_seat))
    spliced, reason = _read_rewrite(ctx, seat, original, rewrite_path)
    if spliced is not None:
        canonical.write_canonical_json(
            ctx.rpc_path(ctx.answer_name(prose_number, seat)), spliced)
        runrecord.append_event(ctx.run_dir, "answer_accepted", {
            "number": prose_number, "seat": seat,
            "path": "rpc/" + ctx.answer_name(prose_number, seat),
            "prose_spliced": True})
        ctx.refresh()
        ctx.say("prose rewrite spliced onto %s (request %s)"
                % (seat, prose_number))
        return spliced, prose_number
    runrecord.append_event(ctx.run_dir, "answer_rejected", {
        "number": prose_number, "seat": prose_seat, "reason": reason})
    ctx.refresh()
    ctx.say("prose rewrite not usable (%s); the audited original stands, warned"
            % reason)
    return original, original_number


def _record_gated_prose(ctx, seat, number, score, fails, spliced):
    """Record the chairman's judged writing score - the score of the text that
    ACTUALLY publishes (spliced or original). This is the gate's finalization
    marker: once it is on disk the prose state never re-executes. `warned` is
    true when the published text still misses the rules, so it publishes with
    the score shown, never frozen (spec U6.4, the AB4 spirit)."""
    runrecord.append_event(ctx.run_dir, "prose_scored", {
        "seat": seat, "number": number, "judged": True,
        "over_threshold": bool(fails),
        "reask_count": sum(1 for event in ctx.events
                           if event["event"] == "prose_reask"
                           and event.get("seat") == seat),
        "warned": bool(fails), "score": score, "failures": fails,
        "spliced": spliced})
    ctx.refresh()


def _resolve_chair_prose(ctx, seat):
    """The chairman's ONE prose re-ask, as a SPLICE (owner ruling AC6, the
    architect's splice ruling replacing the round-1/2 drift guard). The host
    measures the accepted chair document; over a threshold or the word cap it
    asks the chairman ONCE for only the rewritten measured prose fields, then
    builds the published answer by copying the accepted original and replacing
    only those fields. No number and no rating can change - they are the
    original's by construction - and a rewrite whose figures moved, whose keys
    are wrong, or that fails a chair check is simply not usable: the original
    publishes, warned. A second miss (the spliced text still mannered) also
    publishes, with the score shown - never a freeze (the AB4 spirit). Returns
    'reasked' / 'wait' / 'ready'. Crash-safe by re-derivation: the gated score
    is the last write and the finalization marker, and the re-ask is anchored to
    the accepted original's own id recorded in the `prose_reask` event, never
    walked from `retry_of` (audit finding r2-2)."""
    # Idempotent: once the judged score is on disk, the prose state is final.
    if any(event["event"] == "prose_scored" and event.get("seat") == seat
           for event in ctx.events):
        return "ready"
    rules = _prose_rules()
    reask = next((event for event in ctx.events
                  if event["event"] == "prose_reask"
                  and event.get("seat") == seat), None)
    if reask is None:
        original_number = ctx.accepted[seat]
        text, words = _chair_measured_text(ctx.answer(seat))
        score = prose.measure(text, rules)
        fails = prose.failures(score, rules, words)
        if not fails:
            _record_gated_prose(ctx, seat, original_number, score, fails,
                                spliced=False)
            return "ready"
        # Over threshold: issue the one re-ask, anchored to the accepted
        # original's own id (never walked from retry_of - audit finding r2-2).
        runrecord.append_event(ctx.run_dir, "prose_reask", {
            "seat": seat, "original_number": original_number,
            "score": score, "failures": fails})
        ctx.refresh()
        _write_prose_reask(ctx, seat, ctx.answer(seat), fails)
        return "reasked"
    prose_seat = _PROSE_REASK_SEATS[seat]
    original_number = reask["original_number"]
    # Re-issue the re-ask if the marker beat its request onto disk (a crash
    # between the two - audit finding r1-2 / P-U6-2). The rewrite is never
    # skipped: the one attempt is re-issued, and the original still publishes
    # warned even if it were not.
    if not any(req["seat"] == prose_seat for req in ctx.requests.values()):
        original = canonical.read_json(
            ctx.rpc_path(ctx.answer_name(original_number, seat)))
        _write_prose_reask(ctx, seat, original, reask["failures"])
        return "reasked"
    prose_number = next(number for number, req in ctx.requests.items()
                        if req["seat"] == prose_seat)
    if not os.path.exists(
            ctx.rpc_path(ctx.answer_name(prose_number, prose_seat))):
        return "wait"
    # The rewrite is here: splice it or keep the original, then score and
    # publish the text that ACTUALLY publishes (spliced or original).
    original = canonical.read_json(
        ctx.rpc_path(ctx.answer_name(original_number, seat)))
    published, published_number = _apply_prose_rewrite(
        ctx, seat, original, original_number)
    text, words = _chair_measured_text(published)
    score = prose.measure(text, rules)
    fails = prose.failures(score, rules, words)
    _record_gated_prose(ctx, seat, published_number, score, fails,
                        spliced=(published_number != original_number))
    return "ready"


# ------------------------------------------------------- the heading check


# A required heading counts as present when a line carries it as a markdown
# heading ("## ...") or opens with it in bold ("**...**"), matched exactly
# after trimming and case-folding - one check, no fuzzy matching (owner ruling
# AC5, the architect's mechanism ruling). Text inside a fenced code block, or
# indented four spaces or more, is code and never a heading (audit r1-1).
_HEADING_LINE = re.compile(r" {0,3}(?:#{1,6}\s+(.+)|\*\*(.+?)\*\*)")
_FENCE_LINE = re.compile(r" {0,3}(`{3,}|~{3,})")


def missing_headings(markdown):
    """The required headings (read from seat_answers.json) this markdown does
    not carry, in their contract order."""
    found = set()
    fence = None
    for line in (markdown or "").splitlines():
        marker = _FENCE_LINE.match(line)
        if fence is None and marker:
            fence = marker.group(1)
            continue
        if fence is not None:
            if (marker and marker.group(1)[0] == fence[0]
                    and len(marker.group(1)) >= len(fence)
                    and not line[marker.end():].strip()):
                fence = None
            continue
        match = _HEADING_LINE.match(line)
        if match:
            found.add((match.group(1) or match.group(2)).strip().casefold())
    return [heading for heading in briefs.required_headings()
            if heading.strip().casefold() not in found]


def _headings_reason(missing):
    return ("your answer is missing the required heading(s) %s - add the "
            "missing heading(s); change no number and no conclusion. Return "
            "your WHOLE answer with each heading written exactly as named, "
            "as a markdown heading on its own line."
            % ", ".join('"%s"' % heading for heading in missing))


def _ingest_usage_once(ctx, number, seat):
    """Record a request's usage unless it already is: a write made before the
    answer is disposed must not double-count the total on a resume."""
    if not any(event["event"] == "usage_recorded"
               and event.get("number") == number for event in ctx.events):
        _ingest_usage(ctx, number, seat)


def _check_headings(ctx, number, seat, payload):
    """The advisor's ONE heading re-ask (owner ruling AC5, spec U5.1). A
    missing heading, on a seat not yet sent back for one, re-asks on the
    ordinary request path with the answer quoted back; the whole rewrite
    replaces the first, which stays on disk and in the record. After that
    one re-ask the answer stands as given - recorded, never refused, never
    frozen. The `reasked` event is the marker: written after the first
    answer's usage and before the request, so a crash re-derives from disk
    (see _reissue_heading_reasks). Returns True when the answer was sent
    back rather than accepted."""
    missing = missing_headings(payload.get("markdown"))
    reasked = any(event["event"] == "headings_checked"
                  and event["seat"] == seat
                  and event["outcome"] == "reasked" for event in ctx.events)
    if missing and not reasked:
        _ingest_usage_once(ctx, number, seat)
        runrecord.append_event(ctx.run_dir, "headings_checked", {
            "number": number, "seat": seat, "missing": missing,
            "outcome": "reasked"})
        ctx.refresh()
        _write_request(ctx, seat, retry_of=number,
                       reason=_headings_reason(missing))
        return True
    if not any(event["event"] == "headings_checked"
               and event.get("number") == number for event in ctx.events):
        record = {"number": number, "seat": seat, "missing": missing,
                  "outcome": "accepted_missing" if missing else "present"}
        first = [event["number"] for event in ctx.events
                 if event["event"] == "headings_checked"
                 and event["seat"] == seat
                 and event["outcome"] == "reasked"]
        if first:
            # The re-answer replaces the first whole; a moved figure is
            # flagged with the chairman's figure tripwire, never refused
            # (architect ruling closing P-U5a-3).
            before = _answer_figures(canonical.read_json(
                ctx.rpc_path(ctx.answer_name(first[0], seat))))
            after = _answer_figures(payload)
            record["figures_changed"] = before != after
            record["figures_differing"] = {
                "first": list(dict.fromkeys(t for t in before
                                            if t not in after)),
                "rewrite": list(dict.fromkeys(t for t in after
                                              if t not in before))}
        runrecord.append_event(ctx.run_dir, "headings_checked", record)
        ctx.refresh()
    if missing:
        ctx.say("%s still lacks %s after its one re-ask; accepted as given "
                "and recorded" % (seat, ", ".join(missing)))
    return False


def _answer_figures(payload):
    """An advisor answer's figures in order: its prose, then any structured
    field (an anchorless ladder), through the chairman's tripwire."""
    rest = {key: value for key, value in payload.items() if key != "markdown"}
    return (_number_tokens(payload.get("markdown"))
            + _number_tokens(json.dumps(rest, sort_keys=True,
                                        ensure_ascii=False)))


def _reissue_heading_reasks(ctx):
    """A `reasked` marker whose request never reached disk (a crash between
    the two writes) re-issues the same re-ask, never a second one."""
    changed = False
    for event in ctx.events:
        if (event["event"] == "headings_checked"
                and event["outcome"] == "reasked"
                and not any(req["seat"] == event["seat"]
                            and req["retry_of"] == event["number"]
                            for req in ctx.requests.values())):
            _write_request(ctx, event["seat"], retry_of=event["number"],
                           reason=_headings_reason(event["missing"]))
            changed = True
    return changed


def _ingest_answers(ctx):
    """Process every pending request whose answer file exists. Returns True
    when anything changed. May end the run FAILED."""
    changed = _reissue_heading_reasks(ctx)
    for number, seat in ctx.pending():
        if seat in _PROSE_REASK_SEATS.values():
            # A prose re-ask is validated and spliced by the gate
            # (_resolve_chair_prose), never by this ordinary seat-check path:
            # it is not a chair document and must never be re-asked as one
            # (owner ruling AC6, the architect's splice ruling). But its tokens
            # still count toward the sitting budget - an owner acceptance
            # criterion, discarded attempts included (audit finding P-U6-11).
            # Ingest its usage under the parent chair seat once its answer is on
            # disk. This write precedes the gate's dispose, so it is made
            # idempotent (audit finding r4-4): skip when this request's usage is
            # already recorded, so a crash-and-resume before the dispose cannot
            # double-count the total. Guarded on the answer file (as the ordinary
            # path is) so usage is never counted before its answer lands.
            already = any(event["event"] == "usage_recorded"
                          and event.get("number") == number
                          for event in ctx.events)
            if not already and os.path.exists(
                    ctx.rpc_path(ctx.answer_name(number, seat))):
                _ingest_usage(ctx, number, _PROSE_REASK_CHAIR[seat])
            continue
        path = ctx.rpc_path(ctx.answer_name(number, seat))
        if not os.path.exists(path):
            continue
        overrun = False
        try:
            payload = canonical.read_json(path)
        except ValueError as error:
            payload = None
            reasons = ["the answer file is not valid JSON: %s" % error]
        else:
            if seat == "frame":
                reasons = _check_frame(payload, ctx)
            elif seat in ADVISOR_SEATS:
                reasons = _check_advisor(payload, ctx)
            elif seat == "reviewer":
                reasons, overrun = _check_reviewer(payload, ctx)
            elif seat == "chair_draft":
                reasons = _check_chair_draft(payload, ctx)
            elif seat == "chair_resolve":
                reasons = _check_chair_resolve(payload, ctx)
            else:
                reasons = ["unknown seat kind %r" % seat]
        retried_before = ctx.rejections.get(seat, 0) > 0
        if not reasons and overrun:
            if retried_before:
                runrecord.append_event(ctx.run_dir, "synopsis_overrun", {
                    "number": number, "seat": seat,
                    "words": len(payload["synopsis"].split())})
                ctx.say("the synopsis overran 180 words AGAIN; accepted as "
                        "written and recorded loudly - editing a council's "
                        "words is not the host's to do")
            else:
                reasons = ["the synopsis is %d words; the cap is 180 - "
                           "tighten it and answer again"
                           % len(payload["synopsis"].split())]
        if reasons:
            reason = "; ".join(reasons)
            runrecord.append_event(ctx.run_dir, "answer_rejected",
                                   {"number": number, "seat": seat,
                                    "reason": reason})
            ctx.refresh()
            changed = True
            if retried_before:
                _fail(ctx, "the %s seat failed twice; last reason: %s"
                      % (seat, reason))
                return True
            _write_request(ctx, seat, retry_of=number, reason=reason)
            continue
        if seat in ADVISOR_SEATS and _check_headings(ctx, number, seat,
                                                     payload):
            changed = True
            continue
        # The advisors and the reviewer are scored for the record only -
        # advisory, never re-asked (spec U6.4). The chairman's gated rationale
        # is measured in the state advance, where the one re-ask lives; its
        # long synthesis prose is scored advisory here, under a distinct key,
        # so the gate's idempotency guard on the chair seat is untouched
        # (architect Step 0). The advisory score is written BEFORE the answer
        # is accepted, so a crash between the two writes can never drop the
        # score silently on a resume (audit finding r1-3 / P-U6-3).
        if seat in ADVISOR_SEATS or seat == "reviewer":
            _record_advisory_prose(ctx, number, seat,
                                   payload.get("markdown") or "")
        elif seat == "chair_draft":
            _record_advisory_prose(ctx, number, "chair_draft_synthesis",
                                   payload.get("synthesis_markdown") or "")
        elif seat == "chair_resolve":
            _record_advisory_prose(ctx, number, "chair_resolve_synthesis",
                                   payload.get("final_markdown") or "")
        runrecord.append_event(ctx.run_dir, "answer_accepted",
                               {"number": number, "seat": seat,
                                "path": "rpc/" + ctx.answer_name(number,
                                                                 seat)})
        _ingest_usage(ctx, number, seat)
        ctx.refresh()
        ctx.say("answer accepted from %s (request %s)" % (seat, number))
        changed = True
    return changed


# ------------------------------------------------------- state advance


def _write_challenge(ctx):
    frame = ctx.frame()
    draft = ctx.answer("chair_draft")["draft_verdict"]
    nonce = secrets.token_hex(16)
    casefile_md = briefs.build_challenge_casefile(
        ctx.invocation["run_id"], nonce, ctx.casefile(),
        ctx.advisor_markdowns(), ctx.answer("reviewer"), draft)
    for_atlas = frame["for_atlas"]
    if for_atlas and _norm(for_atlas) in _norm(casefile_md):
        raise HostError("the for_atlas note reached the challenge case "
                        "file; that half of the question travels to no "
                        "seat and no challenger")
    body_bytes = casefile_md.encode("utf-8")
    # The hash covers the BODY; it is then printed as the file's final line
    # so the challenger can read and echo it (a file cannot contain its own
    # hash). The bridge sends the file verbatim and verifies the echo
    # against the request value.
    body_hash = canonical.sha256_bytes(body_bytes)
    model, effort = codex_bridge.challenger_choice()
    case_bytes = body_bytes + (
        "\ncasefile_sha256: %s\n" % body_hash).encode("utf-8")
    case_path = os.path.join(ctx.run_dir, "challenge", "casefile.md")
    canonical.write_bytes_atomic(case_path, case_bytes)
    request = {"run_id": ctx.invocation["run_id"], "nonce": nonce,
               "casefile": os.path.abspath(case_path),
               "casefile_sha256": body_hash,
               "schema_path": os.path.abspath(os.path.join(
                   SCHEMA_DIR, "challenge_findings_schema.json")),
               "model": model, "effort": effort,
               "timeout_s": 1800}
    canonical.write_canonical_json(
        os.path.join(ctx.run_dir, "challenge", "request.json"), request)
    runrecord.append_event(ctx.run_dir, "challenge_requested",
                           {"nonce": nonce,
                            "casefile_sha256": request["casefile_sha256"],
                            "model": model})
    ctx.say("challenge request written; the session must now run the "
            "bridge: python -m council.bridge.codex_bridge challenge %s"
            % ctx.run_dir)


def _challenge_schema():
    with open(os.path.join(SCHEMA_DIR, "challenge_findings_schema.json"),
              "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _verify_challenge(ctx):
    """Trust but verify: re-check the bridge's result before believing it.
    Returns (status, failure_reason)."""
    request = canonical.read_json(
        os.path.join(ctx.run_dir, "challenge", "request.json"))
    result_path = os.path.join(ctx.run_dir, "challenge", "result.json")
    try:
        result = canonical.read_json(result_path)
    except ValueError as error:
        return "malformed_output", ("the bridge result is not valid "
                                    "JSON: %s" % error)
    status = result.get("status")
    if status == "posture_breach":
        # BRIDGE-POSTURE: the challenger called a tool beyond reading its
        # case file. Treated exactly as an unreadable answer - the sitting
        # proceeds unaudited on the degraded path - with the bridge's
        # reason, which names the tool.
        return "malformed_output", (result.get("failure_reason")
                                    or "the challenger stepped outside "
                                    "its case file")
    if status not in CHALLENGE_STATUSES:
        return "internal_failure", ("the bridge reported an unknown "
                                    "status %r" % status)
    if status != "success":
        return status, (result.get("failure_reason")
                        or "the bridge reported %s" % status)
    doc = result.get("findings")
    errors = validate.validate(doc, _challenge_schema())
    if errors:
        return "schema_failure", ("the challenger's answer does not match "
                                  "the findings schema: "
                                  + "; ".join(errors[:5]))
    finding_ids = [f.get("id") for f in doc.get("findings", [])]
    repeated = sorted({fid for fid in finding_ids
                       if finding_ids.count(fid) > 1})
    if repeated:
        return "schema_failure", (
            "the challenger's findings repeat the id %s - every finding "
            "carries its own id, or no disposition can answer it by name"
            % ", ".join(repr(fid) for fid in repeated))
    with open(os.path.join(ctx.run_dir, "challenge", "casefile.md"),
              "rb") as handle:
        case_bytes = handle.read()
    # The file's final line prints the body hash; the hash covers what
    # precedes that line (see _write_challenge).
    marker = case_bytes.rfind(b"\ncasefile_sha256: ")
    body_bytes = case_bytes[:marker] if marker != -1 else case_bytes
    if canonical.sha256_bytes(body_bytes) != request["casefile_sha256"]:
        return "binding_failure", ("the challenge case file on disk no "
                                   "longer hashes to the dispatched value")
    echoes = (("run_id_echo", ctx.invocation["run_id"]),
              ("nonce_echo", request["nonce"]),
              ("casefile_sha256_echo", request["casefile_sha256"]))
    for field, expected in echoes:
        if doc.get(field) != expected:
            return "binding_failure", (
                "the challenger's %s does not match this run's dispatch"
                % field)
    return "success", None


def _advance(ctx):
    """One pass of forward motion from the current derived progress.
    Returns True when anything changed."""
    state = _read_state(ctx.run_dir)["state"]
    if state in TERMINAL_STATES:
        return False
    have = ctx.accepted
    requested_seats = {req["seat"] for req in ctx.requests.values()}
    if state == "INIT":
        _write_request(ctx, "frame")
        _write_state(ctx.run_dir, "FRAME", "waiting on the frame seat")
        ctx.say("state: FRAME")
        return True
    if state == "FRAME" and "frame" in have:
        for seat in ADVISOR_SEATS:
            if seat not in requested_seats:
                _write_request(ctx, seat)
        _write_state(ctx.run_dir, "ADVISORS",
                     "five advisor seats dispatched in parallel")
        ctx.say("state: ADVISORS (five requests out at once)")
        return True
    if state == "ADVISORS" and all(s in have for s in ADVISOR_SEATS):
        if "reviewer" not in requested_seats:
            _write_request(ctx, "reviewer")
        _write_state(ctx.run_dir, "REVIEW",
                     "waiting on the one blind reviewer")
        ctx.say("state: REVIEW")
        return True
    if state == "REVIEW" and "reviewer" in have:
        if "chair_draft" not in requested_seats:
            _write_request(ctx, "chair_draft")
        _write_state(ctx.run_dir, "CHAIR_DRAFT",
                     "waiting on the chairman's draft")
        ctx.say("state: CHAIR_DRAFT")
        return True
    if state == "CHAIR_DRAFT" and "chair_draft" in have:
        outcome = _resolve_chair_prose(ctx, "chair_draft")
        if outcome == "reasked":
            return True
        if outcome == "wait":
            return False
        draft = ctx.answer("chair_draft")["draft_verdict"]
        canonical.write_canonical_json(
            os.path.join(ctx.run_dir, "chair", "draft-verdict.json"), draft)
        _write_challenge(ctx)
        _write_state(ctx.run_dir, "CHALLENGE",
                     "challenge dispatched; waiting on the bridge result")
        ctx.say("state: CHALLENGE")
        return True
    if state == "CHALLENGE":
        result_path = os.path.join(ctx.run_dir, "challenge", "result.json")
        if not os.path.exists(result_path):
            return False
        status, failure_reason = _verify_challenge(ctx)
        runrecord.append_event(ctx.run_dir, "challenge_result",
                               {"status": status,
                                "failure_reason": failure_reason})
        ctx.refresh()
        if status == "success":
            ctx.say("challenge result verified: success")
            _write_request(ctx, "chair_resolve")
            _write_state(ctx.run_dir, "CHAIR_RESOLVE",
                         "waiting on the chairman's final document")
            ctx.say("state: CHAIR_RESOLVE")
        else:
            ctx.say("challenge FAILED (%s: %s); skipping the resolve seat - "
                    "nothing to resolve; publishing degraded"
                    % (status, failure_reason))
            _write_state(ctx.run_dir, "PUBLISH",
                         "degraded publication: the outside audit did not "
                         "run")
            ctx.say("state: PUBLISH (degraded)")
        return True
    if state == "CHAIR_RESOLVE" and "chair_resolve" in have:
        outcome = _resolve_chair_prose(ctx, "chair_resolve")
        if outcome == "reasked":
            return True
        if outcome == "wait":
            return False
        resolve = ctx.answer("chair_resolve")
        canonical.write_canonical_json(
            os.path.join(ctx.run_dir, "chair", "resolve.json"), resolve)
        _write_state(ctx.run_dir, "PUBLISH",
                     "every finding disposed; assembling the verdict")
        ctx.say("state: PUBLISH")
        return True
    if state == "PUBLISH":
        try:
            verdict_hash = publisher.assemble_and_publish(ctx.run_dir)
        except Exception as error:  # mechanical refusal: the run dies
            _fail(ctx, "publication refused: %s" % error)
            return True
        _write_state(ctx.run_dir, "DONE", "published")
        runrecord.append_event(ctx.run_dir, "run_finished",
                               {"state": "DONE"})
        ctx.say("published verdict.json (sha256 %s) and "
                "atlas-envelope.json" % verdict_hash)
        ctx.say("state: DONE")
        return True
    return False


def _elapsed_minutes(ctx):
    """How long this sitting has run, and never less than no time.

    The go may be stamped up to the clock-skew allowance ahead of this
    machine, because the owner captures on one machine and sits on the
    other; inside that window the subtraction went negative, `status`
    printed the negative number, and a negative elapsed can never pass
    a cap (audit round 1, r1-5)."""
    import datetime
    started = _parse_iso(runrecord.clock_start(
        ctx.events, ctx.invocation["created_at"]))
    if started is None:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    return max(0.0, (now - started).total_seconds() / 60.0)


def _budget_check(ctx):
    cap = ctx.invocation.get("config", {}).get("minutes_cap",
                                               DEFAULT_MINUTES_CAP)
    elapsed = _elapsed_minutes(ctx)
    if elapsed is None or elapsed <= cap:
        return
    ctx.say("WARNING: %.1f minutes elapsed against the %d-minute budget - "
            "the budget is the acceptance criterion; this run has missed "
            "it and the miss is recorded" % (elapsed, cap))
    if not any(e["event"] == "budget_overrun" for e in ctx.events):
        runrecord.append_event(ctx.run_dir, "budget_overrun",
                               {"elapsed_minutes": round(elapsed, 1),
                                "minutes_cap": cap})
        ctx.refresh()


def step(run_dir):
    """Advance the run as far as the disk allows, in one invocation.
    Never sleeps, never waits. Returns {"state", "lines"}."""
    state = _read_state(run_dir)["state"]
    if state in TERMINAL_STATES:
        return {"state": state,
                "lines": ["state: %s (terminal; nothing to do)" % state]}
    ctx = _Ctx(run_dir)
    _budget_check(ctx)
    changed = True
    while changed:
        changed = False
        if _ingest_answers(ctx):
            changed = True
        if _read_state(run_dir)["state"] in TERMINAL_STATES:
            break
        if _advance(ctx):
            changed = True
    final = _read_state(run_dir)["state"]
    if not ctx.lines:
        ctx.say("nothing new on disk; state: %s" % final)
    return {"state": final, "lines": ctx.lines}


def status(run_dir):
    state_doc = _read_state(run_dir)
    ctx = _Ctx(run_dir)
    pending = [{"number": number, "seat": seat,
                "answer": "rpc/" + ctx.answer_name(number, seat)}
               for number, seat in ctx.pending()]
    tokens = 0
    tokens_known = False
    for event in ctx.events:
        if event["event"] == "usage_recorded" and isinstance(
                event.get("tokens"), int):
            tokens += event["tokens"]
            tokens_known = True
    elapsed = _elapsed_minutes(ctx)
    return {"state": state_doc["state"], "detail": state_doc["detail"],
            "pending": pending,
            "elapsed_minutes": None if elapsed is None else round(elapsed, 1),
            "tokens_recorded": tokens if tokens_known else None,
            "prompt_bytes_total": briefs.total_prompt_bytes(run_dir)}


# ----------------------------------------------------------------- CLI


def main(argv):
    parser = argparse.ArgumentParser(
        prog="python -m council.engine.host",
        description="The stepped council host.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_init = sub.add_parser("init", help="create a run")
    p_init.add_argument("--runs-root", required=True)
    p_init.add_argument("--run-id", required=True)
    p_init.add_argument("--pack", required=True)
    p_init.add_argument("--pack-sha256", required=True)
    p_init.add_argument("--sufficiency", required=True)
    p_init.add_argument("--question-file", required=True)
    p_init.add_argument("--subject-json", required=True,
                        help="a JSON object inline, or a path to one")
    p_init.add_argument("--evidence-dir", required=True,
                        help="the sitting's evidence folder: it carries "
                             "%s, %s and - in the reviewed mode - %s"
                             % (MODE_NAME, CAPTURE_USAGE_NAME,
                                APPROVAL_NAME))
    p_init.add_argument("--config", action="append", default=[],
                        metavar="KEY=VALUE",
                        help="only minutes_cap is recognized")
    p_step = sub.add_parser("step", help="advance a run as far as it can go")
    p_step.add_argument("run_dir")
    p_status = sub.add_parser("status", help="print where a run stands")
    p_status.add_argument("run_dir")
    args = parser.parse_args(argv)

    if args.command == "init":
        config = {}
        for item in args.config:
            if "=" not in item:
                print("config entries look like minutes_cap=90; got %r"
                      % item)
                return 1
            key, value = item.split("=", 1)
            config[key] = value
        try:
            state, run_dir = init(args.runs_root, args.run_id, args.pack,
                                  args.pack_sha256, args.sufficiency,
                                  args.question_file, args.subject_json,
                                  config, args.evidence_dir)
        except HostError as error:
            print("REFUSED: %s" % error)
            return 1
        print("run created at %s" % run_dir)
        print("state: %s" % state)
        if state == "REFUSED":
            print(_read_state(run_dir)["detail"])
            return 3
        return 0
    if args.command == "step":
        result = step(args.run_dir)
        for line in result["lines"]:
            print(line)
        print("state: %s" % result["state"])
        return 0
    if args.command == "status":
        info = status(args.run_dir)
        print("state: %s - %s" % (info["state"], info["detail"]))
        if info["elapsed_minutes"] is not None:
            print("elapsed: %.1f minutes" % info["elapsed_minutes"])
        print("prompt bytes so far: %d" % info["prompt_bytes_total"])
        if info["tokens_recorded"] is None:
            print("tokens recorded so far: none reported")
        else:
            print("tokens recorded so far: %d" % info["tokens_recorded"])
        if info["pending"]:
            for item in info["pending"]:
                print("pending: %s (request %s) -> answer to %s"
                      % (item["seat"], item["number"], item["answer"]))
        else:
            print("pending: nothing - the host is waiting on no seat")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
