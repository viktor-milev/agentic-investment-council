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
import json
import os
import random
import secrets
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, subjects, validate  # noqa: E402
from council.engine import briefs, ladder, publisher  # noqa: E402
from council.engine import runrecord, seal  # noqa: E402
from council.evidence import sufficiency as sufficiency_check  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_DIR = os.path.join(ROOT, "council", "schemas")
FLOORS_PATH = os.path.join(ROOT, "council", "floors", "floors.json")

ADVISOR_SEATS = briefs.ADVISOR_SEATS
CHALLENGER_MODEL = "gpt-5.6-sol"
CHALLENGE_STATUSES = ("success", "launch_failure", "timeout",
                      "malformed_output", "schema_failure",
                      "binding_failure", "internal_failure")
REQUIRED_SIZING_IDS = ("realized_volatility", "liquidity", "event_dates",
                       "drawdown_shape")
TERMINAL_STATES = ("DONE", "REFUSED", "FAILED")
DEFAULT_MINUTES_CAP = 90

_RUN_ID = "[a-z0-9][a-z0-9-]*"


class HostError(Exception):
    """A hard usage error: nothing was advanced."""


def _now_utc():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


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


# ---------------------------------------------------------------- init


def init(runs_root, run_id, pack, pack_sha256, sufficiency, question_file,
         subject_json, config=None):
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
        cited = entry.get("pack_fact_ids", [])
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
                for field in ("value", "unit", "as_of"):
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
            kwargs["challenger_model"] = CHALLENGER_MODEL
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


def _ingest_answers(ctx):
    """Process every pending request whose answer file exists. Returns True
    when anything changed. May end the run FAILED."""
    changed = False
    for number, seat in ctx.pending():
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
    case_bytes = body_bytes + (
        "\ncasefile_sha256: %s\n" % body_hash).encode("utf-8")
    case_path = os.path.join(ctx.run_dir, "challenge", "casefile.md")
    canonical.write_bytes_atomic(case_path, case_bytes)
    request = {"run_id": ctx.invocation["run_id"], "nonce": nonce,
               "casefile": os.path.abspath(case_path),
               "casefile_sha256": body_hash,
               "schema_path": os.path.abspath(os.path.join(
                   SCHEMA_DIR, "challenge_findings_schema.json")),
               "model": CHALLENGER_MODEL, "effort": "high",
               "timeout_s": 1800}
    canonical.write_canonical_json(
        os.path.join(ctx.run_dir, "challenge", "request.json"), request)
    runrecord.append_event(ctx.run_dir, "challenge_requested",
                           {"nonce": nonce,
                            "casefile_sha256": request["casefile_sha256"],
                            "model": CHALLENGER_MODEL})
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
    import datetime
    try:
        started = datetime.datetime.strptime(
            ctx.invocation["created_at"],
            "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - started).total_seconds() / 60.0


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
                                  config)
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
