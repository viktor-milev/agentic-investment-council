"""The codex challenger bridge (REBUILD-SPEC section 7).

One paid cross-model audit call per challenge cycle, no retries: the engine
owns policy, this module owns one launch and its result discipline. The flag
surface, the stdin prompt path, the isolated working directory and the
success rules mirror the proven PowerShell bridge (bridge/challenger-bridge.ps1)
and the spike findings behind it:

- The prompt always travels on stdin. The old bridge redirects stdin from a
  payload file and passes NO trailing prompt argument; codex reads the prompt
  from the pipe. This module does the same with subprocess.Popen(stdin=PIPE).
  The case-file bytes are sent verbatim: the engine already wrote the task
  header and the echo tokens into the case file.
- Every path handed to codex is absolute (the spike proved relative paths
  resolve against the invocation cwd, not -C).
- codex runs confined to a fresh isolated directory containing only a copy
  of the output schema; nothing else is readable there by design.
- Success requires ALL of: exit code 0, the -o file parses as JSON, local
  schema validation passes, the three echoes match the request, and
  authored_verdict is false. Stderr is IGNORED for success or failure: it
  carries benign noise even on a good run (proven).
- On a wall-clock expiry the WHOLE process tree is killed (Windows: taskkill
  /F /T; POSIX: a new session killed with killpg) and partial output is
  never promoted.

Statuses match the verdict schema's challenge enum exactly: success,
launch_failure, timeout, malformed_output, schema_failure, binding_failure,
internal_failure.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

from council.lib import canonical, validate

DEFAULT_MODEL = "gpt-5.6-sol"
SMOKE_TIMEOUT_S = 120

RESULT_NAME = "result.json"
RESPONSE_NAME = "response.json"
EVENTS_NAME = "events.jsonl"
STDERR_NAME = "stderr.log"
ISOLATED_DIRNAME = "isolated"
SCHEMA_COPY_NAME = "challenge_findings_schema.json"

_ECHO_FIELDS = (
    ("run_id_echo", "run_id"),
    ("nonce_echo", "nonce"),
    ("casefile_sha256_echo", "casefile_sha256"),
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


def default_launcher(argv, stdin_bytes, stdout_path, stderr_path, timeout_s):
    """Run argv with stdin_bytes piped in (None means no input), stdout and
    stderr streamed to the named files, and a hard wall clock. Returns
    (returncode_or_None, timed_out). On expiry the whole tree is killed and
    the child is reaped before returning."""
    executable = shutil.which(argv[0]) or argv[0]
    real_argv = [executable] + list(argv[1:])
    popen_kwargs = {}
    if os.name != "nt":
        # A new session makes the child its own process-group leader, so an
        # expiry can kill the whole tree with one killpg.
        popen_kwargs["start_new_session"] = True
    stdin_mode = subprocess.PIPE if stdin_bytes is not None else subprocess.DEVNULL
    with open(stdout_path, "wb") as stdout_handle, \
            open(stderr_path, "wb") as stderr_handle:
        proc = subprocess.Popen(
            real_argv, stdin=stdin_mode,
            stdout=stdout_handle, stderr=stderr_handle, **popen_kwargs)
        try:
            proc.communicate(input=stdin_bytes, timeout=timeout_s)
            return proc.returncode, False
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                proc.communicate(timeout=10)
            except Exception:
                pass
            return proc.poll(), True


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
    }


def _fail(result, status, reason):
    result["status"] = status
    result["failure_reason"] = reason
    result["findings"] = None


def _run_challenge_inner(request, casefile_bytes, out_dir, launcher, result):
    if launcher is None:
        launcher = default_launcher

    # Fresh isolated directory holding only the schema copy.
    schema_src = os.path.abspath(request["schema_path"])
    isolated_dir = os.path.join(out_dir, ISOLATED_DIRNAME)
    if os.path.isdir(isolated_dir):
        shutil.rmtree(isolated_dir)
    os.makedirs(isolated_dir)
    schema_in_isolated = os.path.join(isolated_dir, SCHEMA_COPY_NAME)
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
        returncode, timed_out = launcher(
            argv, casefile_bytes, events_path, stderr_path,
            request["timeout_s"])
    except Exception as exc:
        _fail(result, "launch_failure", "spawn failed: %r" % (exc,))
        return
    result["returncode"] = returncode
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

    mismatched = [echo for echo, key in _ECHO_FIELDS
                  if doc[echo] != request[key]]
    if mismatched:
        _fail(result, "binding_failure",
              "echo mismatch: " + ", ".join(mismatched))
        return

    result["status"] = "success"
    result["failure_reason"] = None
    result["findings"] = doc


def run_challenge(request, casefile_bytes, out_dir, launcher=None):
    """One challenge cycle. Writes <out_dir>/result.json (canonical JSON)
    and returns the same dict. Never raises for a failed call: every failure
    is a typed status the engine reads from the result."""
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    result = _new_result()
    try:
        _run_challenge_inner(request, casefile_bytes, out_dir, launcher, result)
    except Exception as exc:
        _fail(result, "internal_failure", "unexpected: %r" % (exc,))
    canonical.write_canonical_json(os.path.join(out_dir, RESULT_NAME), result)
    return result


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
            returncode, timed_out = launcher(
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
#      python -m council.bridge.codex_bridge smoke
# ---------------------------------------------------------------------------

_USAGE = ("usage: python -m council.bridge.codex_bridge "
          "challenge <run_dir> [--no-smoke] | smoke")


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
        print(_USAGE)
        return 1
    except Exception as exc:
        print("challenge bridge crashed: %r" % (exc,))
        return 1


if __name__ == "__main__":
    sys.exit(main())
