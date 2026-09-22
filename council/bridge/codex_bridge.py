"""The codex bridge - the council's two paid outside-model calls
(REBUILD-SPEC section 7; owner rulings AB4 and AC2).

TWO calls per sitting, one launch discipline. The verdict challenge audits
the chairman's draft (AB4); the evidence audit reads the evidence before any
seat is paid (AC2). Both run the same command with the same confinement and
the same success rules; they differ in the schema the answer is judged
against and the fields it echoes back. No retries: the engine owns policy,
this module owns the launch and its result discipline. The flag surface, the
stdin prompt path, the isolated working directory and the success rules
mirror the proven PowerShell bridge (bridge/challenger-bridge.ps1) and the
spike findings behind it:

- The prompt always travels on stdin. The old bridge redirects stdin from a
  payload file and passes NO trailing prompt argument; codex reads the prompt
  from the pipe. This module does the same with subprocess.Popen(stdin=PIPE).
  The case-file bytes are sent verbatim: the engine already wrote the task
  header and the echo tokens into the case file.
- Every path handed to codex is absolute (the spike proved relative paths
  resolve against the invocation cwd, not -C).
- codex runs confined to a fresh isolated directory containing only a copy
  of the output schema; nothing else on this disk is readable there by
  design. MEASURED at the U2 spike, 2026-09-08: the confined shell has NO
  network (curl cannot resolve a host), but the reviewer's own reader tool
  DOES reach the public web - it read a live figure and the figure checked
  out against an independent read minutes later. That is why an evidence
  finding may carry the page it read and the figure it saw.
- Success requires ALL of: exit code 0, the -o file parses as JSON, local
  schema validation passes, and the stage's echoes match the request. The
  "it never authors" law is carried by each schema's own pinned false -
  authored_verdict for the verdict challenge, authored_frame for the
  evidence audit. Stderr is IGNORED for success or failure: it carries
  benign noise even on a good run (proven).
- On a wall-clock expiry the WHOLE process tree is killed (Windows: taskkill
  /F /T; POSIX: a new session killed with killpg) and partial output is
  never promoted.

Statuses match the verdict schema's challenge enum exactly: success,
launch_failure, timeout, malformed_output, schema_failure, binding_failure,
internal_failure. The evidence audit records the same words in the capture's
evidence_challenge block when its call fails.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

from council.evidence import gate
from council.lib import canonical, validate

DEFAULT_MODEL = "gpt-5.6-sol"
SMOKE_TIMEOUT_S = 120
# How much of the prompt is written into the child at a time. A prompt
# larger than the operating system's pipe buffer (typically 65,536
# bytes) cannot go in one call - the write blocks until the child drains
# it - so the bridge writes it in pieces and counts the pieces that got
# through (register item P-U3-8).
STDIN_CHUNK_BYTES = 65536

RESULT_NAME = "result.json"
# Owner ruling AC15 (per-pass archive): result.json is the CURRENT
# pass, and every pass is ALSO kept whole under its own number, so a
# re-dispatched audit no longer overwrites the first (the debrief's
# defect 6). evidence writes result.pass<N>.json beside result.json;
# evidence-record writes resolution.pass<N>.json beside the resolution
# it used, and builds the block's prior_passes from the pair.
RESULT_PASS_TEMPLATE = "result.pass%d.json"
RESOLUTION_PASS_TEMPLATE = "resolution.pass%d.json"
# Every attempt this council has made at THIS sitting's evidence audit,
# one row each. It survives the runbook's documented re-dispatch, which
# deletes result.json, so the cost of a second call can be added to the
# first (register item P-U3-14).
ATTEMPTS_NAME = "attempts.jsonl"
RESPONSE_NAME = "response.json"
EVENTS_NAME = "events.jsonl"
STDERR_NAME = "stderr.log"
ISOLATED_DIRNAME = "isolated"
SCHEMA_COPY_NAME = "challenge_findings_schema.json"

# The evidence-stage call (owner ruling AC2): the same command, the same
# confinement and the same result discipline as the verdict challenge, a
# different schema and a different pair of echoes. There is no run_id to
# bind to - the host has not been started when this call is made - so the
# evidence's own hash and a one-time token carry the binding.
EVIDENCE_SCHEMA_NAME = "evidence_findings_schema.json"
BRIEF_NAME = "brief.md"
REQUEST_NAME = "request.json"
RESOLUTION_NAME = "challenge-resolution.json"
SCHEMA_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "schemas"))
EVIDENCE_TIMEOUT_S = 1800

_ECHO_FIELDS = (
    ("run_id_echo", "run_id"),
    ("nonce_echo", "nonce"),
    ("casefile_sha256_echo", "casefile_sha256"),
)

_EVIDENCE_ECHO_FIELDS = (
    ("nonce_echo", "nonce"),
    ("capture_sha256_echo", "capture_sha256"),
)


# ---------------------------------------------------------------------------
# Command construction: the exact proven flag surface.
# ---------------------------------------------------------------------------

def build_challenge_argv(model, effort, isolated_dir, schema_path, out_path):
    """The one challenge command. No trailing prompt argument: the prompt
    travels on stdin, exactly as the proven bridge sends it."""
    return [
        "codex", "exec",
        "--model", model,
        "-c", "model_reasoning_effort=" + effort,
        "--sandbox", "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "-C", isolated_dir,
        "--output-schema", schema_path,
        "--json",
        "-o", out_path,
    ]


def build_smoke_argv(model):
    """The standing unpaid smoke test, verbatim from the run books."""
    return [
        "codex", "exec",
        "-m", model,
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--sandbox", "read-only",
        "--ephemeral",
        "Reply OK",
    ]


# ---------------------------------------------------------------------------
# The default launcher: spawn, feed stdin, enforce the wall clock, tree-kill.
# Tests replace this callable; nothing else in the module talks to the OS
# about processes.
# ---------------------------------------------------------------------------

def _kill_tree(proc):
    """Kill the whole process tree, best effort, then fall back to killing
    the direct child. Mirrors the old bridge's taskkill /F /T discipline."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15)
            return
        except Exception:
            pass
    else:
        try:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            return
        except Exception:
            pass
    try:
        proc.kill()
    except Exception:
        pass


def _feed_stdin(proc, stdin_bytes, sent):
    """Write the prompt into the child's stdin, counting what actually
    goes, then close it.

    On its own thread, because this write BLOCKS once the operating
    system's pipe buffer is full and the wall clock has to keep running
    while it does. A child that stalls, or one that exits without
    reading, leaves the rest of the prompt undelivered - and `sent` then
    says how much of it the outside model was really given (register
    item P-U3-8). Only a piece flushed to the pipe is counted."""
    try:
        for start in range(0, len(stdin_bytes), STDIN_CHUNK_BYTES):
            piece = stdin_bytes[start:start + STDIN_CHUNK_BYTES]
            proc.stdin.write(piece)
            proc.stdin.flush()
            sent[0] += len(piece)
    except Exception:
        pass                   # the child stopped reading; what went, went
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass


def default_launcher(argv, stdin_bytes, stdout_path, stderr_path, timeout_s):
    """Run argv with stdin_bytes piped in (None means no input), stdout and
    stderr streamed to the named files, and a hard wall clock. Returns
    (returncode_or_None, timed_out, prompt_bytes_sent). On expiry the
    whole tree is killed and the child is reaped before returning.

    `prompt_bytes_sent` is how many bytes of the prompt this launcher
    actually wrote into the child, or None where there was no prompt to
    write. It is NOT the size of the payload: the write is the part that
    can be cut short, so the size of the file proves nothing about what
    a stalled or timed-out call was given."""
    executable = shutil.which(argv[0]) or argv[0]
    real_argv = [executable] + list(argv[1:])
    popen_kwargs = {}
    if os.name != "nt":
        # A new session makes the child its own process-group leader, so an
        # expiry can kill the whole tree with one killpg.
        popen_kwargs["start_new_session"] = True
    stdin_mode = subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL
    sent = [0]
    with open(stdout_path, "wb") as stdout_handle, \
            open(stderr_path, "wb") as stderr_handle:
        proc = subprocess.Popen(
            real_argv, stdin=stdin_mode,
            stdout=stdout_handle, stderr=stderr_handle, **popen_kwargs)
        feeder = None
        if stdin_bytes is not None:
            feeder = threading.Thread(target=_feed_stdin,
                                      args=(proc, stdin_bytes, sent),
                                      daemon=True)
            feeder.start()
        timed_out = False
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            try:
                proc.wait(timeout=10)
            except Exception:
                pass
        if feeder is not None:
            # The kill above breaks the pipe, so a feeder blocked on a
            # full buffer is already free by the time this waits on it.
            feeder.join(timeout=10)
        return (proc.poll(), timed_out,
                None if stdin_bytes is None else sent[0])


# ---------------------------------------------------------------------------
# Usage extraction from the --json event stream. Best effort, never fatal.
# ---------------------------------------------------------------------------

def _is_plain_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _usage_from_events(events_path):
    """One integer token total from the event stream, or None. Sums every
    turn.completed event: total_tokens when present, else input + output."""
    try:
        with open(events_path, "rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
        total = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") != "turn.completed":
                continue
            usage = event.get("usage")
            if not isinstance(usage, dict):
                continue
            subtotal = usage.get("total_tokens")
            if _is_plain_int(subtotal) and subtotal < 0:
                # A negative count is not a token figure - null is the
                # ruled honest form for a stream that states nonsense
                # (audit finding SC3 r6-1).
                return None
            if not _is_plain_int(subtotal):
                parts = [usage.get("input_tokens"), usage.get("output_tokens")]
                if any(_is_plain_int(p) and p < 0 for p in parts):
                    return None
                if not all(_is_plain_int(p) for p in parts):
                    # A half-known figure must not become a "total":
                    # null is the ruled honest form for a figure the
                    # stream did not fully state (audit finding SC3
                    # r1-2).
                    return None
                subtotal = sum(parts)
            total = (0 if total is None else total) + subtotal
        return total
    except Exception:
        return None


# ---------------------------------------------------------------------------
# The challenge call.
# ---------------------------------------------------------------------------

def _new_result():
    return {
        "status": "internal_failure",
        "failure_reason": None,
        "findings": None,
        "usage_tokens": None,
        "raw_output": RESPONSE_NAME,
        "returncode": None,
        # How many bytes of the prompt were actually handed over. Null
        # until the launcher returns, and never the size of the payload:
        # a stalled or killed call takes only what it read (register
        # item P-U3-8). The host publishes this figure, so a call that
        # never left the machine must not carry one.
        "prompt_bytes_sent": None,
    }


def _fail(result, status, reason):
    result["status"] = status
    result["failure_reason"] = reason
    result["findings"] = None


def _run_call_inner(request, payload_bytes, out_dir, launcher, result,
                    echo_fields, schema_copy_name):
    """One paid call, whichever stage asked for it. The two stages
    differ in the schema the answer is judged against and the fields it
    must echo back, and in nothing else: the command, the confinement,
    the wall clock, the tree-kill and the success rules are one
    discipline, written once (owner ruling AC2 put a second call beside
    the verdict challenge of AB4)."""
    if launcher is None:
        launcher = default_launcher

    # Fresh isolated directory holding only the schema copy.
    schema_src = os.path.abspath(request["schema_path"])
    isolated_dir = os.path.join(out_dir, ISOLATED_DIRNAME)
    if os.path.isdir(isolated_dir):
        shutil.rmtree(isolated_dir)
    os.makedirs(isolated_dir)
    schema_in_isolated = os.path.join(isolated_dir, schema_copy_name)
    shutil.copyfile(schema_src, schema_in_isolated)

    response_path = os.path.join(out_dir, RESPONSE_NAME)
    events_path = os.path.join(out_dir, EVENTS_NAME)
    stderr_path = os.path.join(out_dir, STDERR_NAME)
    # A stale response from an earlier attempt must never be promoted.
    if os.path.exists(response_path):
        os.remove(response_path)

    argv = build_challenge_argv(
        request["model"], request["effort"],
        isolated_dir, schema_in_isolated, response_path)

    try:
        returncode, timed_out, prompt_bytes_sent = launcher(
            argv, payload_bytes, events_path, stderr_path,
            request["timeout_s"])
    except Exception as exc:
        _fail(result, "launch_failure", "spawn failed: %r" % (exc,))
        return
    result["returncode"] = returncode
    result["prompt_bytes_sent"] = prompt_bytes_sent
    result["usage_tokens"] = _usage_from_events(events_path)

    if timed_out:
        _fail(result, "timeout",
              "no answer within %s seconds; the process tree was killed"
              % request["timeout_s"])
        return
    if returncode != 0:
        _fail(result, "launch_failure", "exit code %s" % returncode)
        return

    if not os.path.isfile(response_path):
        _fail(result, "malformed_output", "the -o response file is missing")
        return
    with open(response_path, "rb") as handle:
        raw = handle.read()
    try:
        text = raw.decode("utf-8-sig")  # codex may emit a BOM; strip it
        doc = json.loads(text)
    except (UnicodeDecodeError, ValueError) as exc:
        _fail(result, "malformed_output",
              "the -o response is not parseable JSON: %s" % exc)
        return

    schema = canonical.read_json(schema_src)
    validate.check_schema(schema)
    errors = validate.validate(doc, schema)
    if errors:
        _fail(result, "schema_failure",
              "response failed schema validation: " + "; ".join(errors[:5]))
        return

    mismatched = [echo for echo, key in echo_fields
                  if doc[echo] != request[key]]
    if mismatched:
        _fail(result, "binding_failure",
              "echo mismatch: " + ", ".join(mismatched))
        return

    result["status"] = "success"
    result["failure_reason"] = None
    result["findings"] = doc


def _run_call(request, payload_bytes, out_dir, launcher, echo_fields,
              schema_copy_name):
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    result = _new_result()
    try:
        _run_call_inner(request, payload_bytes, out_dir, launcher, result,
                        echo_fields, schema_copy_name)
    except Exception as exc:
        _fail(result, "internal_failure", "unexpected: %r" % (exc,))
    canonical.write_canonical_json(os.path.join(out_dir, RESULT_NAME), result)
    return result


def run_challenge(request, casefile_bytes, out_dir, launcher=None):
    """One challenge cycle. Writes <out_dir>/result.json (canonical JSON)
    and returns the same dict. Never raises for a failed call: every failure
    is a typed status the engine reads from the result."""
    return _run_call(request, casefile_bytes, out_dir, launcher,
                     _ECHO_FIELDS, SCHEMA_COPY_NAME)


def run_evidence(request, brief_bytes, out_dir, launcher=None):
    """One evidence-stage audit (owner ruling AC2). Same discipline as
    run_challenge, judged against the evidence findings schema and bound
    by the evidence hash rather than a run id."""
    return _run_call(request, brief_bytes, out_dir, launcher,
                     _EVIDENCE_ECHO_FIELDS, EVIDENCE_SCHEMA_NAME)


# ---------------------------------------------------------------------------
# The standing smoke test: unpaid, precedes every paid call.
# ---------------------------------------------------------------------------

def smoke(launcher=None, model=DEFAULT_MODEL):
    """Returns (ok, detail). Success = exit 0 and "OK" in stdout."""
    if launcher is None:
        launcher = default_launcher
    workdir = tempfile.mkdtemp(prefix="council-smoke-")
    try:
        stdout_path = os.path.join(workdir, "stdout.txt")
        stderr_path = os.path.join(workdir, "stderr.txt")
        try:
            returncode, timed_out, _sent = launcher(
                build_smoke_argv(model), None,
                stdout_path, stderr_path, SMOKE_TIMEOUT_S)
        except Exception as exc:
            return False, "smoke spawn failed: %r" % (exc,)
        if timed_out:
            return False, "smoke timed out after %s seconds" % SMOKE_TIMEOUT_S
        stdout_text = ""
        if os.path.isfile(stdout_path):
            with open(stdout_path, "rb") as handle:
                stdout_text = handle.read().decode("utf-8", errors="replace")
        if returncode != 0:
            return False, "smoke exit code %s" % returncode
        if "OK" not in stdout_text:
            return False, "smoke reply did not contain OK"
        return True, "smoke ok"
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI: python -m council.bridge.codex_bridge challenge <run_dir> [--no-smoke]
#      python -m council.bridge.codex_bridge evidence <capture.json> <out_dir>
#                                                     [--no-smoke]
#      python -m council.bridge.codex_bridge evidence-record <capture.json>
#                                            <out_dir> [--resolution <path>]
#      python -m council.bridge.codex_bridge smoke
# ---------------------------------------------------------------------------

_USAGE = ("usage: python -m council.bridge.codex_bridge\n"
          "  challenge <run_dir> [--no-smoke]\n"
          "  evidence <capture.json> <out_dir> [--delta] [--no-smoke]\n"
          "  evidence-record <capture.json> <out_dir> "
          "[--resolution <path>]\n"
          "  smoke\n"
          "  (--delta: re-audit only a correction's changed facts, their\n"
          "   dependents and the frame passages that cite them, with the\n"
          "   prior pass's findings staged - owner ruling AC15, P8)")


def _cli_challenge(run_dir, no_smoke):
    challenge_dir = os.path.join(os.path.abspath(run_dir), "challenge")
    standing_path = os.path.join(challenge_dir, RESULT_NAME)
    if os.path.exists(standing_path):
        # One paid challenge cycle (REBUILD-SPEC section 7): a result
        # that already stands is never re-dispatched - the publisher's
        # M5 refusal, applied at the operator surface. Re-running the
        # printed command must not buy a second cycle or overwrite the
        # recorded answer (audit finding SC3 r1-1).
        try:
            standing = canonical.read_json(standing_path)
            status = standing.get("status")
        except ValueError:
            status = "unreadable"
        print("challenge: a result already stands in this run "
              "(status: %s) - the paid call is refused; one challenge "
              "cycle is the rule. To re-dispatch DELIBERATELY, remove "
              "challenge/result.json first (a smoke-failure result "
              "counts too - remove it the same way after fixing the "
              "cause)." % status)
        return 3
    request = canonical.read_json(os.path.join(challenge_dir, "request.json"))
    with open(os.path.join(challenge_dir, "casefile.md"), "rb") as handle:
        casefile_bytes = handle.read()

    if not no_smoke:
        ok, detail = smoke(model=request.get("model", DEFAULT_MODEL))
        if not ok:
            result = _new_result()
            _fail(result, "launch_failure", "smoke test failed: " + detail)
            canonical.write_canonical_json(
                os.path.join(challenge_dir, RESULT_NAME), result)
            print("challenge: launch_failure - smoke test failed, "
                  "the paid call was refused (%s)" % detail)
            return 3

    result = run_challenge(request, casefile_bytes, challenge_dir)
    if result["status"] == "success":
        count = len(result["findings"]["findings"])
        print("challenge: success - %d finding(s), result.json written" % count)
        return 0
    print("challenge: %s - %s" % (result["status"], result["failure_reason"]))
    return 3


# ---------------------------------------------------------------------------
# The evidence-stage audit (owner ruling AC2): the outside model reads
# the evidence BEFORE any seat is paid, and what it said plus what the
# capture session did about it is recorded INSIDE the capture, so the
# freeze's hash covers both.
# ---------------------------------------------------------------------------

def _empty_resolution():
    """Every key the contract asks of a resolution. The capture session
    writes only the ones its disposition needs; the rest are filled in
    here rather than demanded of a hand-written file."""
    return {"disposition": None, "fact_ids": [], "reason": None,
            "weakened_test": None}


def _pass_record(block):
    """One archived pass from a finished block: its own findings and
    resolutions and the identity that bound it (owner ruling AC15,
    per-pass archive). It is a copy of an already-validated block, so it
    carries no post-audit list of its own - that belongs to the current
    reading of the evidence, not to a pass that has been superseded."""
    return {"pass": block.get("current_pass"),
            "scope": block.get("scope"),
            "status": block.get("status"),
            "model": block.get("model"),
            "failure_status": block.get("failure_status"),
            "failure_reason": block.get("failure_reason"),
            "findings": list(block.get("findings") or []),
            "overall": block.get("overall"),
            "resolutions": dict(block.get("resolutions") or {}),
            "nonce": block.get("nonce"),
            "evidence_sha256": block.get("evidence_sha256")}


def evidence_challenge_block(result, resolution, model,
                             changes=None, recorded_sha256=None,
                             scope="full", prior_passes=None,
                             current_pass=1):
    """The capture's `evidence_challenge`, built from the bridge's own
    result and the capture session's resolution file. Deterministic, no
    call: this is the merge that keeps the auditor's words the
    auditor's, instead of hand-copied into a capture.

    Owner ruling AC13.3: the block carries the one-time token this
    bridge issued for the call and the hash of the evidence it sent, on
    a failed call as much as on a good one. Both are copied out of the
    bridge's own result and out of nothing else, so a block a person
    typed is missing them and the sufficiency gate says so. A
    cost-raiser, not a proof - no deterministic check can show that a
    paid call happened, because the capture session writes every file
    in that folder.

    Owner ruling AC15 (per-pass archive, P8): the flat fields are the
    CURRENT pass; `prior_passes` holds every earlier one, whole, so a
    re-dispatched audit no longer overwrites the first; `current_pass`
    numbers the current one and `scope` says whether it audited the
    whole evidence ('full') or only a correction's delta ('delta')."""
    archive = {"scope": scope,
               "current_pass": current_pass,
               "prior_passes": list(prior_passes or [])}
    if result.get("status") != "success":
        # The six status words stand for eight different causes - no
        # codex installed, an exit code, a killed process tree, an answer
        # that would not parse - and the runbook promises the reason.
        # Carrying only the word left the frozen pack unable to tell a
        # missing program from a model that answered nonsense (audit
        # round 5, r5-4).
        block = {"status": "failed",
                 "model": model,
                 "failure_status": result.get("status"),
                 "failure_reason": result.get("failure_reason"),
                 "findings": [],
                 "overall": None,
                 "resolutions": {},
                 "nonce": result.get("nonce"),
                 "evidence_sha256": result.get("evidence_sha256"),
                 "post_audit_changes": list(changes or []),
                 "post_audit_sha256": recorded_sha256}
        block.update(archive)
        return block
    answer = result.get("findings") or {}
    resolutions = {}
    for finding_id, entry in (resolution or {}).items():
        merged = _empty_resolution()
        merged.update(entry or {})
        resolutions[finding_id] = merged
    block = {"status": "success",
             "model": model,
             "failure_reason": None,
             "failure_status": None,
             "findings": answer.get("findings") or [],
             "overall": answer.get("overall"),
             "resolutions": resolutions,
             "nonce": result.get("nonce"),
             "evidence_sha256": result.get("evidence_sha256"),
             "post_audit_changes": list(changes or []),
             "post_audit_sha256": recorded_sha256}
    block.update(archive)
    return block


def _next_pass_number(out_dir):
    """The number of the pass about to be dispatched: one past the
    highest result.pass<N>.json already on disk (owner ruling AC15,
    per-pass archive). The runbook's re-dispatch removes result.json but
    never the numbered files, so the count of them is the count of
    passes already made."""
    number = 0
    while os.path.exists(os.path.join(out_dir,
                                      RESULT_PASS_TEMPLATE % (number + 1))):
        number += 1
    return number + 1


def _prior_passes(out_dir, current_pass, default_model):
    """Every pass before the current one, rebuilt whole from the
    result.pass<M>.json and resolution.pass<M>.json the bridge kept
    (owner ruling AC15, per-pass archive). A pass whose result file is
    gone is skipped rather than invented."""
    passes = []
    for number in range(1, current_pass):
        result_path = os.path.join(out_dir, RESULT_PASS_TEMPLATE % number)
        if not os.path.isfile(result_path):
            continue
        result = canonical.read_json(result_path)
        resolution = {}
        res_path = os.path.join(out_dir, RESOLUTION_PASS_TEMPLATE % number)
        if os.path.isfile(res_path):
            resolution = (canonical.read_json(res_path) or {}).get(
                "resolutions") or {}
        block = evidence_challenge_block(
            result, resolution, result.get("model") or default_model,
            scope=result.get("scope") or "full", current_pass=number)
        passes.append(_pass_record(block))
    return passes


def _write_capture(path, capture):
    """The capture back to its own file, readable and deterministic. It
    stays a file a person edits when the gate refuses, so it is not
    written in the one-line canonical form the pack uses; the pack's
    hash is taken over the parsed object, never over these bytes."""
    text = json.dumps(capture, indent=2, sort_keys=True, ensure_ascii=True,
                      allow_nan=False)
    canonical.write_bytes_atomic(path, text.encode("utf-8") + b"\n")


def _corrections_to_reaudit(capture):
    """The corrections a delta re-audit must cover: every rebuilding
    correction the record has not yet had re-audited (owner ruling AC15,
    P8). A narrowing correction needs none, so it is never here."""
    return [c for c in (capture.get("corrections") or [])
            if c.get("classification") == "rebuilding"
            and not c.get("reaudited")]


def _cli_evidence(capture_path, out_dir, no_smoke, delta=False):
    import secrets  # local: nothing else in this module needs randomness

    from council.engine import briefs

    out_dir = os.path.abspath(out_dir)
    standing_path = os.path.join(out_dir, RESULT_NAME)
    if os.path.exists(standing_path):
        # One paid evidence audit per sitting, the same rule the verdict
        # challenge lives under: re-running the printed command must not
        # buy a second call or overwrite the recorded answer.
        try:
            status = canonical.read_json(standing_path).get("status")
        except ValueError:
            status = "unreadable"
        print("evidence: a result already stands for this capture "
              "(status: %s) - the paid call is refused; one evidence "
              "audit per sitting is the rule. To re-dispatch "
              "DELIBERATELY, remove %s first."
              % (status, os.path.join(out_dir, RESULT_NAME)))
        return 3
    capture = canonical.read_json(capture_path)
    scope = "delta" if delta else "full"
    prior_block = capture.get("evidence_challenge") or {}
    corrections = []
    if delta:
        # A delta re-audit only makes sense over a pack a full audit
        # SUCCEEDED on and was then corrected (owner ruling AC15, P8): the
        # auditor is shown the correction's own facts and the prior
        # findings, not the whole evidence again. A merely-present block is
        # not enough - a FAILED full audit records a block too, and a delta
        # over it would replace the failure with a success the report reads
        # as "an outside model read this evidence" when none read the full
        # pack (audit round 5, r5-1). Require a successful full pass, on the
        # standing block or kept in the archive.
        def _full_success(candidate):
            # A block that omits `scope` is a full audit - the schema says
            # so, and every pass before this contract was full (audit round
            # 6, r6-2). A recorded delta always carries scope="delta"
            # explicitly, so a missing scope can only mean a legacy full.
            return (candidate.get("status") == "success"
                    and (candidate.get("scope") or "full") == "full")

        has_full_success = _full_success(prior_block) or any(
            _full_success(past) for past in prior_block.get("prior_passes")
            or [])
        if not has_full_success:
            print("evidence --delta: this capture has no SUCCESSFUL full "
                  "evidence audit to build a delta against - a delta "
                  "re-audits a correction on top of a full read that "
                  "happened. Run a full evidence audit and record a success "
                  "first.")
            return 3
        corrections = _corrections_to_reaudit(capture)
        if not corrections:
            print("evidence --delta: this capture carries no rebuilding "
                  "correction awaiting re-audit - a narrowing correction "
                  "needs none, and there is nothing here to re-audit.")
            return 3
    # The corrections THIS audit covers (owner ruling AC15, P8; audit
    # round 1, r1-3; round 5, r5-4). A DELTA shows only the rebuilding
    # corrections it narrows to, and folds exactly those. A FULL pass
    # re-reads the WHOLE pack, so it folds EVERY correction on record into
    # the new baseline - a narrowing sourced correction included, or the
    # post-audit record keeps calling it "changed after the audit" forever.
    # Their identities are written into the request so recording clears
    # ONLY these - a correction applied after the brief was sent was in
    # nothing the auditor read.
    dispatched = (corrections if delta
                  else [c for c in capture.get("corrections") or []
                        if not c.get("reaudited")])
    dispatched_ids = [{"fact_id": c.get("fact_id"), "at": c.get("at")}
                      for c in dispatched]
    pass_number = _next_pass_number(out_dir)
    nonce = secrets.token_hex(16)
    capture_sha256 = canonical.sha256_bytes(canonical.canonical_bytes(capture))
    if delta:
        brief = briefs.build_evidence_delta_brief(
            capture, nonce, capture_sha256, corrections, prior_block)
    else:
        brief = briefs.build_evidence_brief(capture, nonce, capture_sha256)
    brief_bytes = brief.encode("utf-8")
    os.makedirs(out_dir, exist_ok=True)
    canonical.write_bytes_atomic(os.path.join(out_dir, BRIEF_NAME),
                                 brief_bytes)
    body_sha256 = gate.evidence_body_sha256(capture)
    request = {"nonce": nonce,
               "capture": os.path.abspath(capture_path),
               "capture_sha256": capture_sha256,
               "capture_body_sha256": body_sha256,
               "capture_fact_digests": _capture_fact_digests(capture),
               "capture_entry_values": _capture_entry_values(capture),
               "capture_identity": _capture_identity(capture),
               "reaudit_corrections": dispatched_ids,
               # The intended pass number, written BEFORE the call, so a
               # crash that leaves the raw result.json (which carries no
               # pass) still lets evidence-record number this pass right -
               # never default it to 1 and overwrite pass 1's archive
               # (audit round 6, r6-1).
               "pass": pass_number,
               "schema_path": os.path.join(SCHEMA_DIR, EVIDENCE_SCHEMA_NAME),
               "model": DEFAULT_MODEL, "effort": "high",
               "timeout_s": EVIDENCE_TIMEOUT_S}
    canonical.write_canonical_json(os.path.join(out_dir, REQUEST_NAME),
                                   request)

    def stamped(result):
        """This attempt's own record, and every attempt before it.

        The token this bridge issued for the call and the hash of the
        evidence it was given (owner ruling AC13.3) are written on EVERY
        path a call can take, because a block recording a failure is as
        forgeable as one recording an answer - and it is the block that
        tells nine seats and the owner's page whether an outside model
        read these figures.

        The attempt itself is appended to a log the re-dispatch does not
        delete (register item P-U3-14). The runbook's own way of calling
        the auditor again is to remove result.json, which took the first
        call's cost with it: the sitting could then publish only the
        LAST call's tokens, and the owner's budget is judged on that
        figure. The result carries every attempt, so the host can add
        them up."""
        result["nonce"] = nonce
        result["evidence_sha256"] = body_sha256
        # Owner ruling AC15 (per-pass archive): the result carries its own
        # pass number, scope and model, so a re-dispatched audit is kept
        # whole beside the first instead of overwriting it. result.json is
        # the current pass; result.pass<N>.json is its durable copy.
        result["pass"] = pass_number
        result["scope"] = scope
        result["model"] = request["model"]
        canonical.append_jsonl(
            os.path.join(out_dir, ATTEMPTS_NAME),
            {"nonce": nonce, "status": result.get("status"),
             "usage_tokens": result.get("usage_tokens")})
        result["attempts"] = canonical.read_jsonl(
            os.path.join(out_dir, ATTEMPTS_NAME))
        # The numbered archive copy is written FIRST, then the standing
        # result.json (audit round 5, r5-3). A crash between the two then
        # leaves the numbered pass without a result.json - which
        # evidence-record refuses loudly and a re-dispatch numbers past -
        # never a result.json whose pass has no archive copy, which a later
        # re-dispatch would silently reuse and overwrite (the debrief's
        # defect 6 returning). result.json never stands without its copy.
        canonical.write_canonical_json(
            os.path.join(out_dir, RESULT_PASS_TEMPLATE % pass_number), result)
        canonical.write_canonical_json(standing_path, result)
        return result

    if not no_smoke:
        ok, detail = smoke(model=request["model"])
        if not ok:
            result = _new_result()
            _fail(result, "launch_failure", "smoke test failed: " + detail)
            stamped(result)
            print("evidence: launch_failure - smoke test failed, the "
                  "paid call was refused (%s)" % detail)
            return 3

    result = stamped(run_evidence(request, brief_bytes, out_dir))
    if result["status"] == "success":
        findings = result["findings"]["findings"]
        blocking = sum(1 for item in findings
                       if item.get("severity") == "blocking")
        print("evidence: success (%s pass %d) - %d finding(s), %d blocking; "
              "%d prompt bytes sent, result.json and result.pass%d.json "
              "written"
              % (scope, pass_number, len(findings), blocking,
                 len(brief_bytes), pass_number))
        return 0
    print("evidence: %s pass %d - %s - result.pass%d.json kept"
          % (scope, pass_number, result["failure_reason"], pass_number))
    return 3


def _capture_identity(capture):
    """What a capture may not stop being between the audit and the
    recording of it: the subject it is about and the owner's question.
    Facts may be gathered in between - a `captured` answer requires it -
    but a pack that changed either of these is another pack, and the
    audit on this disk was not of it (audit round 2, r2-1)."""
    return {"subject": capture.get("subject"),
            "question_verbatim": capture.get("question_verbatim")}


# What the outside auditor is SHOWN, part by part. Every part of the
# capture except the audit block itself travels in the brief the bridge
# sends (council/engine/briefs.build_evidence_brief): the business frame,
# the fact table, the passages, the declared gaps, the checklist, the
# market state, the day it was captured. So every part of it is
# snapshotted, or a change the auditor never saw goes unlisted while the
# gate - which compares the WHOLE body - passes the pack anyway (closing
# full pass, r5-1). A tier-1 fact and a tier-2 passage keep their own
# ids; every other part is named by its path under this prefix, which no
# fact id can wear because a fact id carries no dot. Dicts are opened key
# by key; a list is one part (see _leaf_parts).
_PART_PREFIX = "capture."


def _leaf_parts(node, path, out):
    """Every part of one section of the capture, keyed by its path.

    A dict is opened key by key. A LIST is not: two readings of a list
    cannot be lined up row by row, and one taken out of the middle
    shifts every row after it - so an index-keyed comparison reported
    rows that never moved as rewritten, and the last row as removed
    while it sat in the pack. Measured on a sitting on record: taking
    one declared gap out of five produced eighteen listed changes, of
    which fourteen were false, and the case file then said a gap had
    been removed four sections below where it printed that same gap as
    standing (closing incremental, r6-1). Keying rows by a stable field
    fixes the half that has one and leaves a list of plain strings -
    a checklist row's answering fact ids - exactly as wrong. So a list
    is ONE part, compared and shown whole: bulkier to read, and never
    false."""
    if isinstance(node, dict):
        for key in sorted(node):
            _leaf_parts(node[key], "%s.%s" % (path, key), out)
    else:
        out[path] = node


def _capture_parts(capture):
    """The capture as the auditor was shown it, part by part: one entry
    per tier-1 fact and tier-2 passage under its own id, and one per leaf
    of everything else under its path."""
    parts = {}
    for section in ("tier1", "tier2"):
        for entry in capture.get(section) or []:
            if isinstance(entry, dict) and entry.get("id") is not None:
                parts[str(entry["id"])] = entry
    rest = dict(capture)
    # `corrections` is excluded for the same reason evidence_body_sha256
    # excludes it (owner ruling AC15, P7): it is the bookkeeping of the
    # correction process, not evidence the auditor read, and the corrected
    # facts themselves are in tier1 where they are compared part by part.
    for section in ("evidence_challenge", "corrections", "tier1", "tier2"):
        rest.pop(section, None)
    leaves = {}
    for key in sorted(rest):
        _leaf_parts(rest[key], _PART_PREFIX + key, leaves)
    parts.update(leaves)
    return parts


def _capture_fact_digests(capture):
    """One hash per part of the capture, keyed on that part's own name:
    the evidence the auditor read, piece by piece. It lets the recording
    say WHICH figure moved, rather than only that something did (audit
    round 5, r5-2), and it covers the whole of what was sent rather than
    the fact table alone (closing full pass, r5-1)."""
    return dict((key, canonical.sha256_bytes(canonical.canonical_bytes(part)))
                for key, part in _capture_parts(capture).items())


def _capture_entry_values(capture):
    """What each part of the capture SAYS, keyed on its own name: a
    fact's value, a passage's text, and for every other part the leaf
    itself. The digests above say that a part moved; these say from what
    to what, which is what owner ruling AC13.2 puts in front of every
    seat and on the owner's page."""
    values = {}
    for key, part in _capture_parts(capture).items():
        if isinstance(part, dict):
            said = part.get("text" if "text" in part else "value")
        elif isinstance(part, list):
            # One part, shown whole, in the pack's own canonical form -
            # so two readings of it are compared as one thing and read
            # as one thing (closing incremental, r6-1).
            said = canonical.canonical_bytes(part).decode("utf-8").strip()
        else:
            said = part
        values[key] = None if said is None else str(said)
    return values


def post_audit_changes(audited_digests, audited_values, capture):
    """Every entry of the record that MOVED between the moment the
    outside auditor was sent this evidence and this recording of its
    answer (owner ruling AC13.2), in id order.

    The capture may change what the auditor never asked about - a figure
    re-read at the source, a passage corrected, a fact dropped - and
    before this ruling the recording simply refused, which deadlocked an
    honest sequence and left the seats reading a record that said the
    auditor had seen figures it had not. Now every such change is
    listed, and the sufficiency gate refuses only a pack whose evidence
    moved with an empty list beside it.

    An entry is compared on its DIGEST, so a change to its unit, its
    date or its source counts as much as a change to the number; the
    values printed beside it are what the entry says, which is what a
    reader needs. Where the digest moved and the value did not, old and
    new are equal and say so."""
    digests_now = _capture_fact_digests(capture)
    values_now = _capture_entry_values(capture)
    audited_digests = audited_digests or {}
    audited_values = audited_values or {}
    changes = []
    for entry_id in sorted(set(audited_digests) | set(digests_now)):
        before = audited_digests.get(entry_id)
        after = digests_now.get(entry_id)
        if before == after:
            continue
        if before is None:
            word, old, new = "added", None, values_now.get(entry_id)
        elif after is None:
            word, old, new = "removed", audited_values.get(entry_id), None
        else:
            word = "changed"
            old, new = (audited_values.get(entry_id),
                        values_now.get(entry_id))
        changes.append({"id": entry_id, "change": word,
                        "old": old, "new": new})
    return changes


def _ungathered(block, audited_digests, digests):
    """The ids a `captured` answer names that were in the pack before the
    audit and have not moved since - sorted, or empty.

    Spec section U2.3 defines the answer as `captured` (NEW fact ids),
    the capture contract calls it "the evidence was gathered and is now
    in the pack", and the runbook says "you went and got it". A `captured`
    answer naming a figure that was there all along says all three of
    those things falsely, to nine paid seats and on the owner's page
    (audit round 5, r5-2). Where the session went, looked, and found the
    auditor wrong, the honest answer is `overruled`."""
    raised = set(str(item.get("id")) for item in block.get("findings") or [])
    named = set()
    for finding_id, entry in (block.get("resolutions") or {}).items():
        if (str(finding_id) not in raised
                or (entry or {}).get("disposition") != "captured"):
            continue
        for fact_id in (entry or {}).get("fact_ids") or []:
            named.add(str(fact_id))
    return sorted(fact_id for fact_id in named
                  if fact_id in (audited_digests or {})
                  and (audited_digests or {})[fact_id] == (
                      digests or {}).get(fact_id))


def _identity_words(identity):
    """One capture's identity, for a refusal a person has to act on."""
    subject = (identity or {}).get("subject") or {}
    question = str((identity or {}).get("question_verbatim") or "")
    if len(question) > 60:
        question = question[:57] + "..."
    return ("%s (%s) asked '%s'"
            % (subject.get("name") or "an unnamed subject",
               subject.get("ticker") or "no ticker", question))


def _cli_evidence_record(capture_path, out_dir, resolution_path):
    out_dir = os.path.abspath(out_dir)
    result_path = os.path.join(out_dir, RESULT_NAME)
    if not os.path.isfile(result_path):
        print("evidence-record: no result to record - %s does not exist. "
              "Run the evidence audit first." % result_path)
        return 3
    result = canonical.read_json(result_path)
    if resolution_path is None:
        resolution_path = os.path.join(os.path.dirname(out_dir),
                                       RESOLUTION_NAME)
    resolution = {}
    if result.get("status") == "success":
        if not os.path.isfile(resolution_path):
            print("evidence-record: the auditor answered, and %s does "
                  "not exist. Write one entry per finding - captured, "
                  "gap_declared or overruled - and record again; the "
                  "sufficiency gate refuses a finding nobody answered."
                  % resolution_path)
            return 3
        resolution = (canonical.read_json(resolution_path) or {}).get(
            "resolutions") or {}
    # The auditor read ONE capture, and the request says which (audit
    # round 1, r1-2; round 2, r2-1). Recording this answer into any
    # other capture puts a reading of one pack on another - and a FAILED
    # result recorded onto a capture nobody audited misstates why no
    # audit exists. Three bindings, each as tight as the honest flow
    # allows:
    #   the PATH, so the answer cannot be pointed at another file;
    #   the IDENTITY - the subject and the owner's question - so the
    #     file at that path cannot be swapped for another pack;
    #   the EVIDENCE ITSELF, unless one of the auditor's own findings
    #     sent the capture session back to gather (audit round 3).
    # The evidence is bound on its hash WITHOUT the audit block, because
    # writing that block is the one change this command itself makes.
    # It is not bound where a `captured` or `gap_declared` answer stands:
    # that answer REQUIRES the capture to move, and the gate refuses an
    # answer naming a fact nobody can read.
    request_path = os.path.join(out_dir, REQUEST_NAME)
    request = {}
    if os.path.isfile(request_path):
        request = canonical.read_json(request_path)
    audited = request.get("capture")
    if not audited:
        print("evidence-record: %s names no capture, so what the auditor "
              "read cannot be known. The audit command writes it before "
              "the call; re-run the audit rather than recording this."
              % request_path)
        return 3
    if os.path.abspath(audited) != os.path.abspath(capture_path):
        print("evidence-record: this audit audited a different capture. "
              "It read %s; you are recording it into %s. An answer about "
              "one pack says nothing about another - record it into the "
              "capture it read, or audit this one."
              % (os.path.abspath(audited), os.path.abspath(capture_path)))
        return 3
    capture = canonical.read_json(capture_path)
    identity = _capture_identity(capture)
    if request.get("capture_identity") != identity:
        print("evidence-record: this audit read a different capture from "
              "the one now at that path. It audited %s; the file now "
              "holds %s. Facts may be gathered between the audit and this "
              "command, but the subject and the question may not move - "
              "that is a different pack. Audit the one you mean to sit."
              % (_identity_words(request.get("capture_identity")),
                 _identity_words(identity)))
        return 3
    model = request.get("model") or DEFAULT_MODEL
    sent = request.get("capture_body_sha256")
    if not sent or request.get("capture_entry_values") is None:
        print("evidence-record: %s does not say which evidence was sent, "
              "so this answer cannot be shown to be an answer about it. "
              "It was written by an older bridge; run the audit again."
              % request_path)
        return 3
    # Owner ruling AC13.2: the capture MAY change what the auditor did
    # not ask about, and every such change is LISTED rather than
    # refused. Refusing deadlocked an honest sequence - a declared gap
    # that removes an unsourceable fact had no legal path - and it
    # closed little, because a change any finding licensed was exempt
    # anyway. This command holds both readings of the evidence, so it is
    # the one place that can say what moved.
    changes = post_audit_changes(request.get("capture_fact_digests"),
                                 request.get("capture_entry_values"),
                                 capture)
    # Owner ruling AC15 (per-pass archive): this pass's own resolution is
    # kept beside its result, and every pass before it is rebuilt whole
    # from the pair the bridge kept - so a re-dispatched audit's first
    # findings and dispositions are no longer overwritten (the debrief's
    # defect 6). scope says whether this pass audited the whole evidence
    # or only a correction's delta.
    # The pass number comes from the request FIRST (written before the
    # call, so it survives a crash that left only the raw result.json,
    # which carries no pass), then the result, then 1 (audit round 6,
    # r6-1). Getting this wrong defaults a crashed pass 2 to pass 1 and
    # overwrites pass 1's archive.
    pass_number = request.get("pass") or result.get("pass") or 1
    scope = result.get("scope") or "full"
    # If a crash left result.json without its numbered archive copy - the
    # copy is written before result.json in `stamped`, but the call itself
    # (_run_call) writes result.json earlier still - backfill it here, so
    # the pass is durably numbered and a later re-dispatch numbers PAST it
    # instead of silently reusing this number and overwriting the pass
    # (audit round 5, r5-3; the debrief's defect 6 returning).
    numbered_result = os.path.join(out_dir, RESULT_PASS_TEMPLATE % pass_number)
    if not os.path.isfile(numbered_result):
        canonical.write_canonical_json(numbered_result, result)
    canonical.write_canonical_json(
        os.path.join(out_dir, RESOLUTION_PASS_TEMPLATE % pass_number),
        {"resolutions": resolution})
    prior_passes = _prior_passes(out_dir, pass_number, model)
    block = evidence_challenge_block(result, resolution, model, changes,
                                     gate.evidence_body_sha256(capture),
                                     scope=scope, prior_passes=prior_passes,
                                     current_pass=pass_number)
    ungathered = _ungathered(block, request.get("capture_fact_digests"),
                             _capture_fact_digests(capture))
    if ungathered:
        print("evidence-record: the record says these figures were "
              "gathered in answer to the auditor, and every one of them "
              "was in the pack before it read a word and has not moved "
              "since: %s. Nothing was gathered. Go and get what the "
              "auditor asked for, or say in your own words why it is "
              "wrong - an answer that points at what was already there "
              "tells every seat, and the owner's page, that the record "
              "grew when it did not."
              % ", ".join("'%s'" % item for item in ungathered))
        return 3
    capture["evidence_challenge"] = block
    # Owner ruling AC15 (P8): a re-audit - full or delta - that reaches
    # this recording has put every rebuilding correction awaiting one in
    # front of the outside model (or recorded that no model could be
    # reached, the same terms the first audit's failure lives under). The
    # sufficiency gate stops on a rebuilding correction that was NEVER
    # re-audited; once it has been, the gate lets the pack sit.
    # Audit round 1 (r1-3): mark re-audited ONLY the corrections this
    # audit actually carried, identified by the set the dispatch recorded
    # in the request. A rebuilding correction applied AFTER the brief was
    # sent was in nothing the auditor read; clearing it here would let the
    # pack sit on a change no outside model saw. A request written before
    # this field existed carries no set, so it clears nothing - loud, not
    # silently wrong.
    dispatched = {(c.get("fact_id"), c.get("at"))
                  for c in request.get("reaudit_corrections") or []}
    reaudited_count = 0
    for correction in capture.get("corrections") or []:
        # Mark folded any correction THIS audit carried (its identity is in
        # the dispatched set) - a delta's set is its rebuilding targets, a
        # full pass's set is every correction on record (audit round 5,
        # r5-4). The classification is not re-checked here: the dispatched
        # set already says what the auditor saw.
        if (not correction.get("reaudited")
                and (correction.get("fact_id"),
                     correction.get("at")) in dispatched):
            correction["reaudited"] = True
            reaudited_count += 1
    _write_capture(capture_path, capture)
    moved = ("" if not changes else
             " %d figure(s) changed after the auditor read the evidence "
             "and are listed in the record, in every seat's case file and "
             "on the report: %s."
             % (len(changes),
                ", ".join("'%s' %s" % (item["id"], item["change"])
                          for item in changes[:6])
                + (", and more" if len(changes) > 6 else "")))
    reaudited = ("" if not reaudited_count else
                 " %d correction(s) marked re-audited; the sufficiency gate "
                 "will now let the pack sit." % reaudited_count)
    passes = ("" if not prior_passes else
              " Pass %d recorded; %d earlier pass(es) kept whole in the "
              "archive." % (pass_number, len(prior_passes)))
    if block["status"] == "success":
        print("evidence-record: recorded into %s - %d finding(s), %d "
              "resolved.%s%s%s Gate, freeze and sufficiency next."
              % (capture_path, len(block["findings"]),
                 len(block["resolutions"]), moved, passes, reaudited))
    else:
        print("evidence-record: recorded into %s - the call FAILED (%s). "
              "The sitting goes on; every seat is told, and the report's "
              "front page says the outside auditor did not check the "
              "evidence.%s%s" % (capture_path, block["failure_status"],
                                 passes, reaudited))
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if not args:
            print(_USAGE)
            return 1
        command, rest = args[0], args[1:]
        if command == "smoke":
            ok, detail = smoke()
            print("smoke: %s - %s" % ("ok" if ok else "FAILED", detail))
            return 0 if ok else 3
        if command == "challenge":
            no_smoke = "--no-smoke" in rest
            rest = [a for a in rest if a != "--no-smoke"]
            if len(rest) != 1:
                print(_USAGE)
                return 1
            return _cli_challenge(rest[0], no_smoke)
        if command == "evidence":
            no_smoke = "--no-smoke" in rest
            delta = "--delta" in rest
            rest = [a for a in rest
                    if a not in ("--no-smoke", "--delta")]
            if len(rest) != 2:
                print(_USAGE)
                return 1
            return _cli_evidence(rest[0], rest[1], no_smoke, delta)
        if command == "evidence-record":
            resolution_path = None
            if "--resolution" in rest:
                index = rest.index("--resolution")
                if index + 1 >= len(rest):
                    print(_USAGE)
                    return 1
                resolution_path = rest[index + 1]
                rest = rest[:index] + rest[index + 2:]
            if len(rest) != 2:
                print(_USAGE)
                return 1
            return _cli_evidence_record(rest[0], rest[1], resolution_path)
        print(_USAGE)
        return 1
    except Exception as exc:
        print("challenge bridge crashed: %r" % (exc,))
        return 1


if __name__ == "__main__":
    sys.exit(main())
