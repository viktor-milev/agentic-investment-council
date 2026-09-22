"""Bridge suite: the codex challenger bridge (REBUILD-SPEC section 7).

No paid model calls anywhere in this file: every test injects a fake
launcher, and the timeout test launches a slow python child through the
REAL launcher path - never the codex CLI."""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.bridge import codex_bridge as bridge  # noqa: E402
from council.evidence import gate  # noqa: E402
from council.lib import canonical  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_PATH = os.path.join(
    ROOT, "council", "schemas", "challenge_findings_schema.json")
FIXTURES = os.path.join(ROOT, "council", "tests", "fixtures", "bridge")


def fixture_bytes(name):
    with open(os.path.join(FIXTURES, name), "rb") as handle:
        return handle.read()


def fixture_text(name):
    return fixture_bytes(name).decode("utf-8")


CASEFILE_BYTES = fixture_bytes("casefile.md")
GOOD_TEXT = fixture_text("findings_good.json")
GOOD_DOC = json.loads(GOOD_TEXT)


def make_request(**overrides):
    request = json.loads(fixture_text("request.json"))
    request["schema_path"] = SCHEMA_PATH
    request.update(overrides)
    return request


class FakeLauncher:
    """Stands in for the codex CLI: records every call and writes scripted
    files exactly where the argv points. A smoke call is recognised by its
    -m flag; a challenge call by --model and -o."""

    def __init__(self, returncode=0, timed_out=False, response_text=None,
                 events_lines=None, stderr_text="",
                 smoke_returncode=0, smoke_stdout="OK\n", sent_bytes=None):
        self.calls = []
        self.returncode = returncode
        self.timed_out = timed_out
        self.response_text = response_text
        self.events_lines = events_lines or []
        self.stderr_text = stderr_text
        self.smoke_returncode = smoke_returncode
        self.smoke_stdout = smoke_stdout
        # How much of the prompt this stand-in says it delivered: None
        # for all of it, a number where the child stopped reading part
        # way through (register item P-U3-8).
        self.sent_bytes = sent_bytes

    def _sent(self, stdin_bytes):
        if stdin_bytes is None:
            return None
        return len(stdin_bytes) if self.sent_bytes is None else self.sent_bytes

    def __call__(self, argv, stdin_bytes, stdout_path, stderr_path, timeout_s):
        self.calls.append({"argv": list(argv), "stdin": stdin_bytes,
                           "timeout_s": timeout_s})
        if "-m" in argv:
            with open(stdout_path, "wb") as handle:
                handle.write(self.smoke_stdout.encode("utf-8"))
            with open(stderr_path, "wb") as handle:
                handle.write(b"")
            return self.smoke_returncode, False, self._sent(stdin_bytes)
        with open(stdout_path, "wb") as handle:
            if self.events_lines:
                handle.write(("\n".join(self.events_lines) + "\n")
                             .encode("utf-8"))
        with open(stderr_path, "wb") as handle:
            handle.write(self.stderr_text.encode("utf-8"))
        if self.response_text is not None:
            out_path = argv[argv.index("-o") + 1]
            with open(out_path, "wb") as handle:
                handle.write(self.response_text.encode("utf-8"))
        return self.returncode, self.timed_out, self._sent(stdin_bytes)

    def challenge_calls(self):
        return [c for c in self.calls if "--model" in c["argv"]]

    def smoke_calls(self):
        return [c for c in self.calls if "-m" in c["argv"]]


def pid_alive(pid):
    """True while the process with this pid is still running."""
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
        if not handle:
            return False
        try:
            code = ctypes.c_ulong(0)
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bridge-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.out_dir = os.path.join(self.tmp, "challenge")

    def run_bridge(self, fake, request=None, casefile=CASEFILE_BYTES):
        return bridge.run_challenge(request or make_request(), casefile,
                                    self.out_dir, launcher=fake)

    def result_on_disk(self):
        return canonical.read_json(os.path.join(self.out_dir, "result.json"))


class TestCommandSurface(BridgeCase):
    def test_challenge_argv_is_the_exact_proven_surface(self):
        fake = FakeLauncher(response_text=GOOD_TEXT)
        self.run_bridge(fake)
        calls = fake.challenge_calls()
        self.assertEqual(len(calls), 1)
        out_abs = os.path.abspath(self.out_dir)
        isolated = os.path.join(out_abs, "isolated")
        expected = [
            "codex", "exec",
            "--model", "gpt-5.6-sol",
            "-c", "model_reasoning_effort=high",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "-C", isolated,
            "--output-schema",
            os.path.join(isolated, "challenge_findings_schema.json"),
            "--json",
            "-o", os.path.join(out_abs, "response.json"),
        ]
        # Full-list equality: order, completeness, and NO trailing prompt
        # argument - the prompt travels on stdin, as the proven bridge sends it.
        self.assertEqual(calls[0]["argv"], expected)
        for index in (12, 14, 17):
            self.assertTrue(os.path.isabs(expected[index]))
        self.assertEqual(calls[0]["stdin"], CASEFILE_BYTES)
        self.assertEqual(calls[0]["timeout_s"], 120)

    def test_smoke_argv_is_the_standing_command(self):
        fake = FakeLauncher()
        ok, detail = bridge.smoke(launcher=fake)
        self.assertTrue(ok, detail)
        self.assertEqual(fake.calls[0]["argv"], [
            "codex", "exec",
            "-m", "gpt-5.6-sol",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--sandbox", "read-only",
            "--ephemeral",
            "Reply OK",
        ])
        self.assertIsNone(fake.calls[0]["stdin"])


class TestIsolatedDirectory(BridgeCase):
    def test_contains_only_the_schema_copy_and_is_rebuilt_fresh(self):
        isolated = os.path.join(self.out_dir, "isolated")
        os.makedirs(isolated)
        with open(os.path.join(isolated, "leftover.txt"), "wb") as handle:
            handle.write(b"junk from an earlier attempt")
        fake = FakeLauncher(response_text=GOOD_TEXT)
        self.run_bridge(fake)
        self.assertEqual(os.listdir(isolated),
                         ["challenge_findings_schema.json"])
        with open(os.path.join(isolated, "challenge_findings_schema.json"),
                  "rb") as handle:
            copied = handle.read()
        with open(SCHEMA_PATH, "rb") as handle:
            self.assertEqual(copied, handle.read())


class TestResultDiscipline(BridgeCase):
    def test_good_response_is_success_and_result_json_matches(self):
        fake = FakeLauncher(response_text=GOOD_TEXT)
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "success")
        self.assertIsNone(result["failure_reason"])
        self.assertEqual(result["findings"], GOOD_DOC)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["raw_output"], "response.json")
        self.assertIsNone(result["usage_tokens"])  # no event stream scripted
        self.assertEqual(self.result_on_disk(), result)

    def test_usage_total_is_extracted_from_the_event_stream(self):
        fake = FakeLauncher(response_text=GOOD_TEXT, events_lines=[
            '{"type":"thread.started","thread_id":"t1"}',
            'not json at all',
            '{"type":"turn.completed","usage":{"input_tokens":1200,'
            '"cached_input_tokens":100,"output_tokens":300}}',
        ])
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["usage_tokens"], 1500)

    def test_nonzero_exit_is_launch_failure_and_stale_output_is_removed(self):
        os.makedirs(self.out_dir)
        stale = os.path.join(self.out_dir, "response.json")
        with open(stale, "wb") as handle:
            handle.write(GOOD_TEXT.encode("utf-8"))
        fake = FakeLauncher(returncode=1)
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "launch_failure")
        self.assertIn("exit code 1", result["failure_reason"])
        self.assertIsNone(result["findings"])
        self.assertFalse(os.path.exists(stale))

    def test_spawn_exception_is_launch_failure(self):
        def exploding(argv, stdin_bytes, stdout_path, stderr_path, timeout_s):
            raise OSError("no such executable")
        result = self.run_bridge(exploding)
        self.assertEqual(result["status"], "launch_failure")
        self.assertIn("spawn failed", result["failure_reason"])

    def test_missing_response_file_is_malformed_output(self):
        fake = FakeLauncher(response_text=None)
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "malformed_output")

    def test_unparseable_response_is_malformed_output(self):
        fake = FakeLauncher(response_text="{this is not json")
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "malformed_output")

    def test_schema_invalid_response_is_schema_failure(self):
        fake = FakeLauncher(
            response_text=fixture_text("findings_invalid_shape.json"))
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "schema_failure")
        self.assertIn("kind", result["failure_reason"])

    def test_authored_verdict_true_is_schema_failure(self):
        fake = FakeLauncher(
            response_text=fixture_text("findings_authored_true.json"))
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "schema_failure")
        self.assertIn("authored_verdict", result["failure_reason"])

    def test_wrong_nonce_is_binding_failure(self):
        fake = FakeLauncher(
            response_text=fixture_text("findings_bad_nonce.json"))
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "binding_failure")
        self.assertIn("nonce_echo", result["failure_reason"])

    def test_wrong_run_id_is_binding_failure(self):
        doc = json.loads(GOOD_TEXT)
        doc["run_id_echo"] = "some-other-run"
        fake = FakeLauncher(response_text=json.dumps(doc))
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "binding_failure")
        self.assertIn("run_id_echo", result["failure_reason"])

    def test_wrong_casefile_hash_is_binding_failure(self):
        doc = json.loads(GOOD_TEXT)
        doc["casefile_sha256_echo"] = "0" * 64
        fake = FakeLauncher(response_text=json.dumps(doc))
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "binding_failure")
        self.assertIn("casefile_sha256_echo", result["failure_reason"])

    def test_stderr_noise_does_not_fail_a_good_run(self):
        fake = FakeLauncher(
            response_text=GOOD_TEXT,
            stderr_text="ERROR codex_models_manager::cache benign noise\n")
        result = self.run_bridge(fake)
        self.assertEqual(result["status"], "success")

    def test_every_failure_still_writes_result_json(self):
        fake = FakeLauncher(returncode=1)
        result = self.run_bridge(fake)
        self.assertEqual(self.result_on_disk(), result)


class TestTimeout(BridgeCase):
    def test_slow_child_is_killed_and_no_output_is_promoted(self):
        child_code = ("import os, sys, time; "
                      "sys.stdout.write(str(os.getpid())); "
                      "sys.stdout.flush(); time.sleep(60)")

        def slow_launcher(argv, stdin_bytes, stdout_path, stderr_path,
                          timeout_s):
            # The REAL launcher path (Popen, wall clock, tree-kill), but the
            # child is a slow python process - never the codex CLI.
            return bridge.default_launcher(
                [sys.executable, "-c", child_code],
                stdin_bytes, stdout_path, stderr_path, timeout_s)

        os.makedirs(self.out_dir)
        stale = os.path.join(self.out_dir, "response.json")
        with open(stale, "wb") as handle:
            handle.write(GOOD_TEXT.encode("utf-8"))

        started = time.monotonic()
        result = self.run_bridge(slow_launcher,
                                 request=make_request(timeout_s=2),
                                 casefile=b"small case file\n")
        elapsed = time.monotonic() - started

        self.assertEqual(result["status"], "timeout")
        self.assertIsNone(result["findings"])
        self.assertLess(elapsed, 20)  # never waits out the 60s sleep
        self.assertEqual(self.result_on_disk()["status"], "timeout")
        # Nothing promoted: the stale response was cleared and never re-read.
        self.assertFalse(os.path.exists(stale))
        # The child was reaped by the launcher (a wait returned a code)...
        self.assertIsNotNone(result["returncode"])
        # ...and the process itself is dead.
        pid_text = ""
        with open(os.path.join(self.out_dir, "events.jsonl"), "rb") as handle:
            pid_text = handle.read().decode("ascii", errors="replace").strip()
        self.assertTrue(pid_text.isdigit(), "child never reported its pid")
        pid = int(pid_text)
        deadline = time.monotonic() + 3
        while pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertFalse(pid_alive(pid), "slow child survived the tree-kill")


class TestSmoke(BridgeCase):
    def test_exit_zero_with_ok_passes(self):
        ok, detail = bridge.smoke(launcher=FakeLauncher())
        self.assertTrue(ok, detail)

    def test_nonzero_exit_fails(self):
        ok, detail = bridge.smoke(launcher=FakeLauncher(smoke_returncode=1))
        self.assertFalse(ok)
        self.assertIn("exit code 1", detail)

    def test_reply_without_ok_fails(self):
        ok, detail = bridge.smoke(
            launcher=FakeLauncher(smoke_stdout="READY\n"))
        self.assertFalse(ok)
        self.assertIn("OK", detail)


class TestCli(BridgeCase):
    def make_run_dir(self):
        run_dir = os.path.join(self.tmp, "run")
        challenge_dir = os.path.join(run_dir, "challenge")
        os.makedirs(challenge_dir)
        with open(os.path.join(challenge_dir, "casefile.md"), "wb") as handle:
            handle.write(CASEFILE_BYTES)
        request = make_request()
        with open(os.path.join(challenge_dir, "request.json"), "wb") as handle:
            handle.write(json.dumps(request).encode("utf-8"))
        return run_dir, challenge_dir

    def main_with(self, fake, args):
        original = bridge.default_launcher
        bridge.default_launcher = fake
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = bridge.main(args)
            return code, buffer.getvalue()
        finally:
            bridge.default_launcher = original

    def test_challenge_end_to_end_success(self):
        run_dir, challenge_dir = self.make_run_dir()
        fake = FakeLauncher(response_text=GOOD_TEXT)
        code, printed = self.main_with(fake, ["challenge", run_dir])
        self.assertEqual(code, 0, printed)
        self.assertEqual(len(fake.smoke_calls()), 1)
        self.assertEqual(len(fake.challenge_calls()), 1)
        written = canonical.read_json(
            os.path.join(challenge_dir, "result.json"))
        self.assertEqual(written["status"], "success")
        self.assertEqual(written["findings"], GOOD_DOC)
        self.assertIn("success", printed)

    def test_no_smoke_flag_skips_the_smoke_call(self):
        run_dir, _ = self.make_run_dir()
        fake = FakeLauncher(response_text=GOOD_TEXT)
        code, _ = self.main_with(fake, ["challenge", run_dir, "--no-smoke"])
        self.assertEqual(code, 0)
        self.assertEqual(fake.smoke_calls(), [])
        self.assertEqual(len(fake.challenge_calls()), 1)

    def test_failing_smoke_refuses_the_paid_call(self):
        run_dir, challenge_dir = self.make_run_dir()
        fake = FakeLauncher(response_text=GOOD_TEXT, smoke_returncode=1)
        code, printed = self.main_with(fake, ["challenge", run_dir])
        self.assertEqual(code, 3)
        self.assertEqual(fake.challenge_calls(), [],
                         "the paid call must not happen after a failed smoke")
        written = canonical.read_json(
            os.path.join(challenge_dir, "result.json"))
        self.assertEqual(written["status"], "launch_failure")
        self.assertTrue(
            written["failure_reason"].startswith("smoke test failed"))
        self.assertIn("refused", printed)

    def test_failure_status_exits_3(self):
        run_dir, challenge_dir = self.make_run_dir()
        fake = FakeLauncher(
            response_text=fixture_text("findings_authored_true.json"))
        code, _ = self.main_with(fake, ["challenge", run_dir, "--no-smoke"])
        self.assertEqual(code, 3)
        written = canonical.read_json(
            os.path.join(challenge_dir, "result.json"))
        self.assertEqual(written["status"], "schema_failure")

    def test_smoke_subcommand(self):
        code, printed = self.main_with(FakeLauncher(), ["smoke"])
        self.assertEqual(code, 0)
        self.assertIn("ok", printed)

    def test_missing_run_dir_is_a_crash_exit_1(self):
        code, printed = self.main_with(
            FakeLauncher(), ["challenge",
                             os.path.join(self.tmp, "does-not-exist"),
                             "--no-smoke"])
        self.assertEqual(code, 1)
        self.assertIn("crashed", printed)


class TestSC3Round1Regressions(unittest.TestCase):
    """SC3 round-1 findings at the bridge; both FAILED pre-fix."""

    # r1-1: re-running the CLI repeated the paid call and overwrote the
    # standing result.
    def test_a_standing_result_refuses_a_second_dispatch(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            challenge = os.path.join(tmp, "challenge")
            os.makedirs(challenge)
            with open(os.path.join(challenge, "request.json"), "w",
                      encoding="utf-8") as handle:
                json.dump({"run_id": "r", "nonce": "n",
                           "casefile_sha256": "c" * 64,
                           "schema_path": SCHEMA_PATH,
                           "model": "gpt-5.6-sol", "effort": "high",
                           "timeout_s": 5}, handle)
            with open(os.path.join(challenge, "casefile.md"), "wb") as handle:
                handle.write(b"case")
            standing = {"status": "success", "failure_reason": None,
                        "findings": {"marker": "DO-NOT-TOUCH"},
                        "usage_tokens": 7, "raw_output": "response.json",
                        "returncode": 0}
            with open(os.path.join(challenge, "result.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(standing, handle)
            calls = []
            original_smoke = bridge.smoke
            original_run = bridge.run_challenge
            bridge.smoke = lambda **kw: calls.append("smoke") or (
                True, "ok")
            bridge.run_challenge = (
                lambda *a, **kw: calls.append("paid") or standing)
            try:
                code = bridge.main(["challenge", tmp])
            finally:
                bridge.smoke = original_smoke
                bridge.run_challenge = original_run
            self.assertEqual(calls, [])
            self.assertNotEqual(code, 0)
            with open(os.path.join(challenge, "result.json"),
                      encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), standing)

    # r6-1: a negative count is not a token figure.
    def test_negative_usage_yields_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = os.path.join(tmp, "events.jsonl")
            with open(events, "w", encoding="utf-8") as handle:
                handle.write('{"type":"turn.completed",'
                             '"usage":{"total_tokens":-1}}\n')
            self.assertIsNone(bridge._usage_from_events(events))

    # r1-2: a partial usage record became the challenger's "total".
    def test_partial_usage_yields_null_not_a_subtotal(self):
        with tempfile.TemporaryDirectory() as tmp:
            events = os.path.join(tmp, "events.jsonl")
            with open(events, "w", encoding="utf-8") as handle:
                handle.write('{"type":"turn.completed",'
                             '"usage":{"input_tokens":1200}}\n')
            self.assertIsNone(bridge._usage_from_events(events))


# ---------------------------------------------------------------------
# The EVIDENCE-stage audit (owner ruling AC2): a second paid call, made
# BEFORE any seat is paid, over the evidence itself. Same command, same
# confinement, same result discipline; a different schema and a
# different pair of echoes. No paid calls here either.
# ---------------------------------------------------------------------

EVIDENCE_SCHEMA_PATH = os.path.join(
    ROOT, "council", "schemas", "evidence_findings_schema.json")
CAPTURE_PATH = os.path.join(
    ROOT, "council", "tests", "fixtures", "evidence", "exmp-pass.json")


def evidence_finding(**overrides):
    finding = {"id": "E1",
               "kind": "missing_decisive_fact",
               "severity": "material",
               "detail": "INVENTED - the pack carries no rent per unit.",
               "fact_ids": [],
               "where_it_likely_lives": "INVENTED - the segment note",
               "source_url": None,
               "figure_at_source": None}
    finding.update(overrides)
    return finding


def evidence_answer(nonce, capture_sha256, findings=None, overall=None):
    return {"nonce_echo": nonce,
            "capture_sha256_echo": capture_sha256,
            "authored_frame": False,
            "findings": [evidence_finding()] if findings is None else findings,
            "overall": overall}


class EvidenceLauncher(FakeLauncher):
    """The fake CLI for the evidence stage. The nonce and the evidence
    hash are minted inside the command under test, so the scripted
    answer is built from the request the command just wrote rather than
    from a constant this suite would have to guess."""

    def __init__(self, findings=None, overall=None, echo_override=None,
                 **kwargs):
        FakeLauncher.__init__(self, **kwargs)
        self.findings = findings
        self.overall = overall
        self.echo_override = echo_override or {}

    def __call__(self, argv, stdin_bytes, stdout_path, stderr_path,
                 timeout_s):
        if "-o" in argv and self.response_text is None:
            out_dir = os.path.dirname(argv[argv.index("-o") + 1])
            request = canonical.read_json(
                os.path.join(out_dir, bridge.REQUEST_NAME))
            answer = evidence_answer(request["nonce"],
                                     request["capture_sha256"],
                                     self.findings, self.overall)
            answer.update(self.echo_override)
            self.response_text = json.dumps(answer)
        return FakeLauncher.__call__(self, argv, stdin_bytes, stdout_path,
                                     stderr_path, timeout_s)


class EvidenceCase(BridgeCase):
    def make_capture(self):
        path = os.path.join(self.tmp, "capture.json")
        shutil.copyfile(CAPTURE_PATH, path)
        return path

    def out_path(self):
        return os.path.join(self.tmp, "evidence", "challenge")

    def main_with(self, fake, args):
        original = bridge.default_launcher
        bridge.default_launcher = fake
        try:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = bridge.main(args)
            return code, buffer.getvalue()
        finally:
            bridge.default_launcher = original

    def run_evidence(self, fake, args=()):
        capture = self.make_capture()
        code, printed = self.main_with(
            fake, ["evidence", capture, self.out_path()] + list(args))
        return capture, code, printed


class TestEvidenceCommandSurface(EvidenceCase):
    def test_the_evidence_call_uses_the_same_confined_surface(self):
        fake = EvidenceLauncher()
        _, code, printed = self.run_evidence(fake)
        self.assertEqual(code, 0, printed)
        calls = fake.challenge_calls()
        self.assertEqual(len(calls), 1)
        out_abs = os.path.abspath(self.out_path())
        isolated = os.path.join(out_abs, "isolated")
        self.assertEqual(calls[0]["argv"], [
            "codex", "exec",
            "--model", "gpt-5.6-sol",
            "-c", "model_reasoning_effort=high",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "--ephemeral",
            "--ignore-user-config",
            "-C", isolated,
            "--output-schema",
            os.path.join(isolated, "evidence_findings_schema.json"),
            "--json",
            "-o", os.path.join(out_abs, "response.json"),
        ])

    def test_the_brief_travels_on_stdin_and_is_kept(self):
        """No trailing prompt argument, and the bytes sent are the bytes
        on disk: what the auditor read is recoverable afterwards."""
        fake = EvidenceLauncher()
        _, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        sent = fake.challenge_calls()[0]["stdin"]
        with open(os.path.join(self.out_path(), bridge.BRIEF_NAME),
                  "rb") as handle:
            self.assertEqual(handle.read(), sent)
        self.assertGreater(len(sent), 4096)
        self.assertNotIn(sent.decode("utf-8"), fake.calls[0]["argv"])

    def test_the_isolated_directory_holds_only_the_evidence_schema(self):
        fake = EvidenceLauncher()
        self.run_evidence(fake)
        isolated = os.path.join(self.out_path(), "isolated")
        self.assertEqual(os.listdir(isolated),
                         ["evidence_findings_schema.json"])
        with open(os.path.join(isolated,
                               "evidence_findings_schema.json"),
                  "rb") as handle:
            copied = handle.read()
        with open(EVIDENCE_SCHEMA_PATH, "rb") as handle:
            self.assertEqual(copied, handle.read())

    def test_the_brief_carries_the_evidence_and_the_law(self):
        fake = EvidenceLauncher()
        self.run_evidence(fake)
        with open(os.path.join(self.out_path(), bridge.BRIEF_NAME),
                  encoding="utf-8") as handle:
            brief = handle.read()
        for needle in ("audit the EVIDENCE",
                       "You never gather",
                       "You are NOT a compliance auditor",
                       "missing_decisive_fact", "suspect_figure",
                       "framing_error", "missing_checklist_row",
                       "source_doubt",
                       "at most 60 words",
                       "The question the council was asked",
                       "Tier-1 facts", "Tier-2 passages",
                       "Declared gaps",
                       "The sufficiency checklist",
                       "The evidence minimums this council already demands"):
            self.assertIn(needle, brief, needle)

    def test_the_brief_says_when_the_evidence_was_captured(self):
        """Audit round 1, r1-8. The auditor is asked to name a figure
        that is stale for what it is being used for, and every fact
        carries its own as-of date - but the date those are measured
        FROM was withheld, so an audit run a week after the capture
        would judge a then-fresh figure against the wrong day."""
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        with open(os.path.join(self.out_path(), bridge.BRIEF_NAME),
                  encoding="utf-8") as handle:
            brief = handle.read()
        captured_at = canonical.read_json(capture_path)["captured_at"]
        self.assertIn(captured_at, brief)
        self.assertIn("Judge every as-of date below against that day",
                      brief)

    def test_the_obligation_precedes_the_evidence(self):
        """MAC-1, one seat over: a reader whose first read stops early
        has read what it must produce, not half a fact table."""
        fake = EvidenceLauncher()
        self.run_evidence(fake)
        with open(os.path.join(self.out_path(), bridge.BRIEF_NAME),
                  encoding="utf-8") as handle:
            brief = handle.read()
        self.assertLess(brief.index("Answer as ONE JSON object"),
                        brief.index("Tier-1 facts"))


class TestEvidenceResultDiscipline(EvidenceCase):
    def test_a_good_answer_is_success_and_is_written_whole(self):
        fake = EvidenceLauncher(overall="INVENTED - the record is thin.")
        _, code, printed = self.run_evidence(fake)
        self.assertEqual(code, 0, printed)
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["findings"]["overall"],
                         "INVENTED - the record is thin.")
        self.assertEqual(len(result["findings"]["findings"]), 1)
        self.assertIn("1 finding(s), 0 blocking", printed)

    def test_a_wrong_echo_is_a_binding_failure(self):
        fake = EvidenceLauncher(echo_override={"nonce_echo": "not the one"})
        _, code, printed = self.run_evidence(fake)
        self.assertEqual(code, 3)
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result["status"], "binding_failure")
        self.assertIn("nonce_echo", result["failure_reason"])

    def test_an_answer_outside_the_schema_is_a_schema_failure(self):
        fake = EvidenceLauncher(
            response_text=json.dumps({"nonce_echo": "x",
                                      "capture_sha256_echo": "y",
                                      "authored_frame": True,
                                      "findings": [], "overall": None}))
        _, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 3)
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result["status"], "schema_failure")

    def test_an_unruled_kind_of_finding_is_refused(self):
        """The five kinds are the whole vocabulary (AC2, spec U2.2): a
        sixth is not a finding this council knows how to answer."""
        fake = EvidenceLauncher(
            findings=[evidence_finding(kind="formatting_nit")])
        _, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 3)
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result["status"], "schema_failure")

    def test_the_smoke_test_runs_first_and_refuses_the_paid_call(self):
        fake = EvidenceLauncher(smoke_returncode=1)
        _, code, printed = self.run_evidence(fake)
        self.assertEqual(code, 3)
        self.assertEqual(fake.challenge_calls(), [])
        self.assertIn("smoke test failed", printed)
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result["status"], "launch_failure")

    def test_no_smoke_skips_it(self):
        fake = EvidenceLauncher()
        _, code, _ = self.run_evidence(fake, ["--no-smoke"])
        self.assertEqual(code, 0)
        self.assertEqual(fake.smoke_calls(), [])
        self.assertEqual(len(fake.challenge_calls()), 1)

    def test_a_standing_result_refuses_a_second_paid_call(self):
        """One evidence audit per sitting, the rule the verdict
        challenge already lives under: re-running the command must not
        buy a second call or overwrite the answer on record."""
        fake = EvidenceLauncher()
        capture, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        standing = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        second = EvidenceLauncher()
        code, printed = self.main_with(
            second, ["evidence", capture, self.out_path()])
        self.assertEqual(code, 3)
        self.assertEqual(second.calls, [])
        self.assertIn("a result already stands", printed)
        self.assertEqual(canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME)), standing)


class TestTheCallLeavesItsOwnMark(EvidenceCase):
    """Owner ruling AC13.3 (register item P-U2-5). The bridge issues a
    one-time token for every evidence call and knows the hash of the
    evidence it sent; both are written into its own result, on every
    path a call can take, and `evidence-record` copies them into the
    capture. A block that carries neither was written by hand, and the
    sufficiency gate refuses it. Every test below FAILS against the
    pre-fix code."""

    def result(self):
        return canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))

    def test_a_good_call_records_its_token_and_the_evidence_it_sent(self):
        fake = EvidenceLauncher()
        capture_path, code, printed = self.run_evidence(fake)
        self.assertEqual(code, 0, printed)
        result = self.result()
        request = canonical.read_json(
            os.path.join(self.out_path(), bridge.REQUEST_NAME))
        self.assertEqual(result["nonce"], request["nonce"])
        self.assertEqual(result["evidence_sha256"],
                         request["capture_body_sha256"])
        self.assertEqual(
            result["evidence_sha256"],
            gate.evidence_body_sha256(canonical.read_json(capture_path)))

    def test_the_token_is_fresh_on_every_call(self):
        self.run_evidence(EvidenceLauncher())
        first_nonce = self.result()["nonce"]
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.run_evidence(EvidenceLauncher())
        self.assertNotEqual(self.result()["nonce"], first_nonce)
        self.assertEqual(len(first_nonce), 32)

    def test_a_refused_call_is_stamped_the_same_way(self):
        """The forged FAILURE is the quieter half of the finding, and an
        operator obtains that block honestly with no codex on the
        path."""
        fake = EvidenceLauncher(smoke_returncode=1)
        _, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 3)
        result = self.result()
        self.assertEqual(result["status"], "launch_failure")
        self.assertEqual(len(result["nonce"]), 32)
        self.assertEqual(len(result["evidence_sha256"]), 64)

    def test_a_binding_failure_is_stamped_too(self):
        fake = EvidenceLauncher(echo_override={"nonce_echo": "not the one"})
        _, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 3)
        self.assertEqual(self.result()["status"], "binding_failure")
        self.assertEqual(len(self.result()["nonce"]), 32)

    def test_every_attempt_is_logged_and_survives_a_re_dispatch(self):
        """Register item P-U3-14, ruled by the architect after this
        unit's audit. The runbook's own way of calling the auditor again
        is to delete `result.json` - which took the first call's cost
        with it, so the sitting could publish only the last call's
        tokens and the owner's budget is judged on that figure. The log
        of attempts is not what the re-dispatch deletes."""
        first = EvidenceLauncher(
            events_lines=['{"type":"turn.completed",'
                          '"usage":{"total_tokens":40000}}'])
        capture_path, code, _ = self.run_evidence(first)
        self.assertEqual(code, 0)
        self.assertEqual(self.result()["usage_tokens"], 40000)
        self.assertEqual([row["usage_tokens"]
                          for row in self.result()["attempts"]], [40000])

        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        second = EvidenceLauncher(
            events_lines=['{"type":"turn.completed",'
                          '"usage":{"total_tokens":34000}}'])
        code, printed = self.main_with(
            second, ["evidence", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        result = self.result()
        self.assertEqual(result["usage_tokens"], 34000)
        self.assertEqual([row["usage_tokens"] for row in result["attempts"]],
                         [40000, 34000])
        # Each row names the call it was, so two attempts can never be
        # read as one recorded twice.
        self.assertEqual(len({row["nonce"] for row in result["attempts"]}), 2)
        self.assertEqual([row["status"] for row in result["attempts"]],
                         ["success", "success"])

    def test_a_refused_call_is_an_attempt_too(self):
        """A smoke failure bought nothing, and the log says so with no
        count rather than leaving the call out of the history."""
        self.run_evidence(EvidenceLauncher(smoke_returncode=1))
        self.assertEqual(self.result()["attempts"],
                         [{"nonce": self.result()["nonce"],
                           "status": "launch_failure",
                           "usage_tokens": None}])

    def test_the_block_carries_both_across_from_the_result(self):
        block = bridge.evidence_challenge_block(
            {"status": "success",
             "findings": {"findings": [], "overall": None},
             "nonce": "n" * 32, "evidence_sha256": "e" * 64},
            {}, "gpt-5.6-sol")
        self.assertEqual(block["nonce"], "n" * 32)
        self.assertEqual(block["evidence_sha256"], "e" * 64)

    def test_a_failed_block_carries_both_across_as_well(self):
        block = bridge.evidence_challenge_block(
            {"status": "timeout", "failure_reason": "INVENTED",
             "nonce": "n" * 32, "evidence_sha256": "e" * 64},
            {}, "gpt-5.6-sol")
        self.assertEqual(block["status"], "failed")
        self.assertEqual(block["nonce"], "n" * 32)
        self.assertEqual(block["evidence_sha256"], "e" * 64)


class TestEvidenceRecord(EvidenceCase):
    """The deterministic merge: the auditor's own words plus the capture
    session's answers, written INTO the capture so the freeze's hash
    covers both. No model call."""

    def gather_fact(self, capture_path, fact_id="rent_per_megawatt_q"):
        """What a `captured` answer MEANS: the session went and got the
        figure, and it is in the pack now. Returns the id, to be named
        in the answer."""
        capture = canonical.read_json(capture_path)
        gathered = dict(capture["tier1"][0])
        gathered["id"] = fact_id
        gathered["derived"] = None
        capture["tier1"].append(gathered)
        canonical.write_canonical_json(capture_path, capture)
        return fact_id

    def resolution_file(self, entries):
        path = os.path.join(self.tmp, "evidence",
                            bridge.RESOLUTION_NAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        canonical.write_canonical_json(path, {"resolutions": entries})
        return path

    def test_a_successful_audit_and_its_answers_reach_the_capture(self):
        fake = EvidenceLauncher(overall="INVENTED - thin on unit economics.")
        capture_path, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        gathered = self.gather_fact(capture_path)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        block = canonical.read_json(capture_path)["evidence_challenge"]
        self.assertEqual(block["status"], "success")
        self.assertEqual(block["model"], "gpt-5.6-sol")
        self.assertIsNone(block["failure_status"])
        self.assertEqual(block["overall"],
                         "INVENTED - thin on unit economics.")
        self.assertEqual(block["findings"][0]["id"], "E1")
        # Every key the contract asks of a resolution is filled in, so a
        # hand-written file carries only what its disposition needs.
        self.assertEqual(block["resolutions"]["E1"],
                         {"disposition": "captured",
                          "fact_ids": ["rent_per_megawatt_q"],
                          "reason": None, "weakened_test": None})
        # Owner ruling AC13.3: the token this call was issued and the
        # hash of the evidence it was given travel into the capture, so
        # the sufficiency gate can refuse a block nobody's bridge wrote.
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(block["nonce"], result["nonce"])
        self.assertEqual(block["evidence_sha256"],
                         result["evidence_sha256"])

    def test_the_recorded_capture_still_clears_the_gate(self):
        from council.evidence import gate
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        gathered = self.gather_fact(capture_path)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        code, printed = self.main_with(fake, ["evidence-record",
                                              capture_path,
                                              self.out_path()])
        self.assertEqual(code, 0, printed)
        capture = canonical.read_json(capture_path)
        checked = gate.validate_capture(capture, gate.load_capture_schema())
        self.assertEqual(checked["result"], "accepted", checked["reasons"])

    def test_a_captured_answer_that_gathered_nothing_is_refused(self):
        """Audit round 5, r5-2. Spec section U2.3 defines the answer as
        `captured` (NEW fact ids); the contract calls it "the evidence
        was gathered and is now in the pack"; the runbook says "you went
        and got it". An answer pointing at a figure that was there
        before the auditor read a word says all three falsely - to nine
        paid seats, and on the owner's page as "gathered, and it is in
        the evidence below"."""
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": ["price_last"]}})
        before = canonical.read_json(capture_path)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 3, printed)
        self.assertIn("'price_last'", printed)
        self.assertIn("Nothing was gathered", printed)
        self.assertEqual(canonical.read_json(capture_path), before)

    def test_a_figure_the_session_went_back_and_re_read_still_counts(self):
        """The control the rule must not refuse: the session went to the
        source, and what came back was the same number under a fresh
        reading. The fact's own entry moved - its source and its date -
        so the record grew, and the answer stands."""
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        capture = canonical.read_json(capture_path)
        capture["tier1"][0]["source"] = ("INVENTED FIXTURE - re-read at "
                                         "the exchange's own quote page")
        canonical.write_canonical_json(capture_path, capture)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": ["price_last"]}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)

    def test_a_failed_call_is_recorded_and_the_sitting_goes_on(self):
        fake = EvidenceLauncher(returncode=7)
        capture_path, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 3)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        block = canonical.read_json(capture_path)["evidence_challenge"]
        self.assertEqual(block["status"], "failed")
        self.assertEqual(block["failure_status"], "launch_failure")
        self.assertIn("exit code 7", block["failure_reason"])
        self.assertEqual(block["findings"], [])
        self.assertEqual(block["resolutions"], {})
        self.assertIn("the outside auditor did not check the evidence",
                      printed)

    def test_a_successful_audit_with_no_answers_is_refused_early(self):
        """The record cannot be written half-done: the sufficiency gate
        would refuse it anyway, and saying so here costs nothing."""
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        before = canonical.read_json(capture_path)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 3)
        self.assertIn("does not exist", printed)
        self.assertEqual(canonical.read_json(capture_path), before)

    def test_recording_before_the_audit_says_so(self):
        capture_path = self.make_capture()
        fake = EvidenceLauncher()
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 3)
        self.assertIn("Run the evidence audit first", printed)

    def test_another_captures_audit_cannot_be_recorded_into_this_one(self):
        """Audit round 1, r1-2. The auditor read ONE capture. Recording
        its answer into a different one puts a reading of pack A on pack
        B - and a FAILED result for A would let B sit as though its own
        audit had been attempted, which is precisely what the sufficiency
        gate exists to stop."""
        fake = EvidenceLauncher(returncode=7)
        audited, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 3)
        other = os.path.join(self.tmp, "other-capture.json")
        shutil.copyfile(CAPTURE_PATH, other)
        before = canonical.read_json(other)
        code, printed = self.main_with(
            fake, ["evidence-record", other, self.out_path()])
        self.assertEqual(code, 3, printed)
        self.assertIn("audited a different capture", printed)
        self.assertIn(os.path.abspath(audited), printed)
        self.assertIn(os.path.abspath(other), printed)
        self.assertEqual(canonical.read_json(other), before)

    def test_the_capture_it_did_audit_still_records(self):
        """The control: the same result against the capture the request
        names goes in exactly as before."""
        fake = EvidenceLauncher(returncode=7)
        capture_path, _, _ = self.run_evidence(fake)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        self.assertEqual(canonical.read_json(
            capture_path)["evidence_challenge"]["status"], "failed")

    def swap_capture_for(self, capture_path, fixture_name):
        """The same path, different contents: the operator edits or
        replaces the capture between the audit and the recording."""
        shutil.copyfile(
            os.path.join(ROOT, "council", "tests", "fixtures", "evidence",
                         fixture_name), capture_path)

    def test_a_successful_audit_cannot_be_moved_onto_another_pack(self):
        """Audit round 2, found in triage beneath r2-1. Round 1 bound the
        recording to the capture's PATH. Replace the file at that path
        and one pack's findings - and the capture session's answers to
        them - land on another pack's record, reach nine seat prompts,
        and are printed to the owner attributed to a model that never
        saw it."""
        fake = EvidenceLauncher()
        capture_path, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": ["revenue_q"]}})
        self.swap_capture_for(capture_path, "aapl-pass.json")
        before = canonical.read_json(capture_path)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 3, printed)
        self.assertIn("read a different capture from the one now at "
                      "that path", printed)
        self.assertEqual(canonical.read_json(capture_path), before)

    def test_a_failed_audit_cannot_be_moved_onto_other_contents(self):
        """Audit round 2, r2-1. On a failure the capture cannot
        legitimately change - there are no findings to go and capture -
        so the recording is bound to the bytes that were sent."""
        fake = EvidenceLauncher(returncode=7)
        capture_path, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 3)
        capture = canonical.read_json(capture_path)
        capture["question_verbatim"] = capture["question_verbatim"] + " Now?"
        canonical.write_canonical_json(capture_path, capture)
        before = canonical.read_json(capture_path)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 3, printed)
        self.assertEqual(canonical.read_json(capture_path), before)

    def changed_after_the_call(self, fake, capture_path, value):
        """One figure moved after the auditor read the evidence, and the
        recording run over it. Returns (exit code, what it printed, the
        block that was written)."""
        capture = canonical.read_json(capture_path)
        capture["tier1"][0]["value"] = value
        canonical.write_canonical_json(capture_path, capture)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        block = (canonical.read_json(capture_path).get("evidence_challenge")
                 or {})
        return code, printed, block

    def test_a_change_after_a_failed_call_is_listed_not_refused(self):
        """PREMISE MOVED by owner ruling AC13.2, and recorded: this case
        used to REFUSE the recording. The capture may change what the
        auditor did not ask about, and every such change is listed -
        here, in every seat's case file and on the owner's report."""
        fake = EvidenceLauncher(returncode=7)
        capture_path, _, _ = self.run_evidence(fake)
        was = canonical.read_json(capture_path)["tier1"][0]["value"]
        code, printed, block = self.changed_after_the_call(
            fake, capture_path, "INVENTED - 1.0")
        self.assertEqual(code, 0, printed)
        self.assertEqual(block["status"], "failed")
        self.assertEqual(block["post_audit_changes"],
                         [{"id": "price_last", "change": "changed",
                           "old": was, "new": "INVENTED - 1.0"}])

    def test_a_change_after_a_clean_audit_is_listed_with_both_values(self):
        """Audit round 3, r3-1, under the new ruling: an audit that found
        nothing sends nobody to gather anything, so a figure that moves
        afterwards is one no outside model read - and the record now says
        which one, from what, to what."""
        fake = EvidenceLauncher(findings=[])
        capture_path, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        self.resolution_file({})
        was = canonical.read_json(capture_path)["tier1"][0]["value"]
        code, printed, block = self.changed_after_the_call(
            fake, capture_path, "INVENTED - 999.9")
        self.assertEqual(code, 0, printed)
        self.assertEqual(block["post_audit_changes"],
                         [{"id": "price_last", "change": "changed",
                           "old": was, "new": "INVENTED - 999.9"}])
        self.assertIn("1 figure(s) changed after the auditor read the "
                      "evidence", printed)
        self.assertIn("'price_last' changed", printed)

    def test_a_gathered_fact_is_listed_as_added(self):
        """The other two words: an entry the session went and got after
        the audit is `added`, and one it took out is `removed`."""
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        gathered = self.gather_fact(capture_path)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        capture = canonical.read_json(capture_path)
        dropped = capture["tier2"].pop()
        canonical.write_canonical_json(capture_path, capture)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        listed = canonical.read_json(
            capture_path)["evidence_challenge"]["post_audit_changes"]
        by_id = dict((item["id"], item) for item in listed)
        self.assertEqual(by_id[gathered]["change"], "added")
        self.assertIsNone(by_id[gathered]["old"])
        self.assertEqual(by_id[dropped["id"]],
                         {"id": dropped["id"], "change": "removed",
                          "old": dropped["text"], "new": None})

    def test_a_change_that_leaves_the_value_alone_is_still_listed(self):
        """An entry is compared on its whole record, not on its number:
        a figure re-read from another source on another date is a change
        the auditor did not see, and old and new say the value stands."""
        fake = EvidenceLauncher(findings=[])
        capture_path, _, _ = self.run_evidence(fake)
        self.resolution_file({})
        capture = canonical.read_json(capture_path)
        was = capture["tier1"][0]["value"]
        capture["tier1"][0]["source"] = "INVENTED - re-read elsewhere"
        canonical.write_canonical_json(capture_path, capture)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        listed = canonical.read_json(
            capture_path)["evidence_challenge"]["post_audit_changes"]
        self.assertEqual(listed, [{"id": "price_last", "change": "changed",
                                   "old": was, "new": was}])

    def test_an_edit_after_a_recorded_failure_is_listed_on_the_next_record(
            self):
        """Audit round 3, r3-2, under the new ruling. The first recording
        changes the capture, so the comparison is over the evidence
        WITHOUT the audit block - the one part the recording never
        touches - and the edit is still seen the second time round."""
        fake = EvidenceLauncher(returncode=7)
        capture_path, _, _ = self.run_evidence(fake)
        first, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(first, 0, printed)
        was = canonical.read_json(capture_path)["tier1"][0]["value"]
        code, printed, block = self.changed_after_the_call(
            fake, capture_path, "INVENTED - 999.9")
        self.assertEqual(code, 0, printed)
        self.assertEqual(block["post_audit_changes"],
                         [{"id": "price_last", "change": "changed",
                           "old": was, "new": "INVENTED - 999.9"}])

    def test_a_change_outside_the_fact_table_is_listed_too(self):
        """Closing full pass, r5-1. The auditor is shown the business
        frame, the declared gaps and the checklist as well as the fact
        table, and the gate compares the WHOLE of the evidence - so a
        snapshot of the fact table alone let a rewritten frame ride
        along beside a listed fact change, unlisted, while the pack
        passed. Every seat reads that frame before it reaches the
        numbers."""
        fake = EvidenceLauncher(findings=[])
        capture_path, _, _ = self.run_evidence(fake)
        self.resolution_file({})
        capture = canonical.read_json(capture_path)
        capture["tier1"][0]["value"] = "INVENTED - 999.9"
        frame = capture["business_frame"]["EXMP"]
        was = frame["what_it_does"]
        frame["what_it_does"] = ("INVENTED FIXTURE - it sells one product "
                                 "to one buyer and nothing else.")
        canonical.write_canonical_json(capture_path, capture)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        listed = canonical.read_json(
            capture_path)["evidence_challenge"]["post_audit_changes"]
        by_id = dict((item["id"], item) for item in listed)
        self.assertIn("price_last", by_id)
        self.assertIn("capture.business_frame.EXMP.what_it_does", by_id)
        self.assertEqual(
            by_id["capture.business_frame.EXMP.what_it_does"]["old"], was)
        self.assertEqual(
            by_id["capture.business_frame.EXMP.what_it_does"]["new"],
            frame["what_it_does"])

    def test_nothing_still_in_the_pack_is_reported_as_having_left_it(self):
        """Closing incremental, r6-1. Two readings of a list cannot be
        lined up row by row: one taken out of the middle shifts every
        row after it, so rows that never moved were reported as
        rewritten and the last one as removed while it sat in the pack.
        Measured on a sitting on record, taking one declared gap out of
        five listed eighteen changes of which fourteen were false - and
        the case file then said a gap had been removed four sections
        below where it printed that same gap as standing.

        The honest mutation below is the runbook's own: a row is dropped
        from a list of objects and an id is put at the FRONT of a list
        of plain strings, which no stable key can rescue."""
        fake = EvidenceLauncher(findings=[])
        capture_path, _, _ = self.run_evidence(fake)
        self.resolution_file({})
        capture = canonical.read_json(capture_path)
        metrics = capture["business_frame"]["EXMP"]["decisive_metrics"]
        rows = capture["sufficiency"]["requirements"]
        answered = [row for row in rows if row.get("answered_by")][0]
        # Everything that is STILL in the pack after the edit, and so
        # may never be reported as having left it.
        stood = ([str(row["name"]) for row in metrics[1:]]
                 + [str(item) for item in answered["answered_by"]])
        del metrics[0]
        answered["answered_by"].insert(0, "price_last")
        canonical.write_canonical_json(capture_path, capture)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        listed = canonical.read_json(
            capture_path)["evidence_challenge"]["post_audit_changes"]
        self.assertTrue(listed)
        gone = [item["old"] for item in listed
                if item["change"] == "removed"]
        for value in stood:
            self.assertNotIn(value, gone, listed)

    def test_the_runbooks_declared_gap_row_does_not_deadlock(self):
        """The other half of r5-1, found in triage. The runbook says a
        `gap_declared` answer adds the ordinary `gaps` row too - and a
        `gaps` row is not a fact, so the list came back EMPTY while the
        evidence hash had moved, and sufficiency refused the sequence
        its own runbook prescribes. Nothing the session could do made
        the list non-empty short of buying a second paid call."""
        from council.evidence import freeze, sufficiency
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        self.resolution_file({"E1": {
            "disposition": "gap_declared", "fact_ids": [],
            "reason": "INVENTED - the filer publishes it annually only.",
            "weakened_test": "profit_growth"}})
        capture = canonical.read_json(capture_path)
        capture["gaps"].append(
            {"fact_class": "rent_per_unit",
             "reason": "INVENTED - the filer publishes it annually only.",
             "reason_kind": "other",
             "weakened_test": "profit_growth"})
        canonical.write_canonical_json(capture_path, capture)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        capture = canonical.read_json(capture_path)
        self.assertTrue(capture["evidence_challenge"]["post_audit_changes"])
        floors = canonical.read_json(
            os.path.join(ROOT, "council", "floors", "floors.json"))
        outcome = sufficiency.check(freeze.build_pack(capture), floors)
        self.assertEqual(outcome["result"], "pass",
                         [item["what"] for item in outcome["missing"]])

    def test_nothing_moving_leaves_the_list_empty(self):
        """The control: a sitting where the auditor was answered in words
        alone lists nothing, and the sufficiency gate then holds the
        evidence to the hash it was audited at."""
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        self.resolution_file({"E1": {"disposition": "overruled",
                                     "reason": "INVENTED - twenty five "
                                               "words would go here and "
                                               "sufficiency counts them, "
                                               "which is a check of its "
                                               "own and not this one."}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        block = canonical.read_json(capture_path)["evidence_challenge"]
        self.assertEqual(block["post_audit_changes"], [])
        self.assertEqual(block["evidence_sha256"],
                         gate.evidence_body_sha256(
                             canonical.read_json(capture_path)))

    def test_recording_the_same_success_twice_is_the_same_record(self):
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        self.resolution_file({"E1": {"disposition": "overruled",
                                     "reason": "INVENTED - a reason."}})
        first, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(first, 0, printed)
        block = canonical.read_json(capture_path)["evidence_challenge"]
        second, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(second, 0, printed)
        self.assertEqual(canonical.read_json(
            capture_path)["evidence_challenge"], block)

    def test_recording_the_same_failure_twice_is_the_same_record(self):
        """The control the hash rule must not break: an operator who
        runs the command twice gets the same block, not a refusal about
        a capture that changed because the first run changed it."""
        fake = EvidenceLauncher(returncode=7)
        capture_path, _, _ = self.run_evidence(fake)
        first, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(first, 0, printed)
        block = canonical.read_json(capture_path)["evidence_challenge"]
        second, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(second, 0, printed)
        self.assertEqual(canonical.read_json(
            capture_path)["evidence_challenge"], block)

    def test_the_capture_a_finding_sent_the_session_to_gather_still_records(self):
        """The control the binding must not refuse: a `captured` answer
        REQUIRES the capture to gain a fact between the call and this
        command, and the gate refuses an answer naming a fact nobody can
        read. The subject and the question are what may not move."""
        fake = EvidenceLauncher()
        capture_path, _, _ = self.run_evidence(fake)
        gathered = self.gather_fact(capture_path)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 0, printed)
        self.assertEqual(canonical.read_json(
            capture_path)["evidence_challenge"]["status"], "success")

    def test_a_result_with_no_request_beside_it_is_refused(self):
        """Nothing the bridge writes can produce one - the request is
        written before the call - so a result standing alone is a
        hand-built directory, and what it audited cannot be known."""
        fake = EvidenceLauncher(returncode=7)
        capture_path, _, _ = self.run_evidence(fake)
        os.remove(os.path.join(os.path.abspath(self.out_path()),
                               bridge.REQUEST_NAME))
        before = canonical.read_json(capture_path)
        code, printed = self.main_with(
            fake, ["evidence-record", capture_path, self.out_path()])
        self.assertEqual(code, 3, printed)
        self.assertIn("names no capture", printed)
        self.assertEqual(canonical.read_json(capture_path), before)

class TestThePromptBytesActuallyDelivered(BridgeCase):
    """Register item P-U3-8, ruled by the architect after unit U3's
    audit. The host publishes how many bytes of prompt the outside
    auditor was given. It used to take the size of the file on disk,
    which is right only when the whole of it reached the other side: a
    model that stalls without draining a prompt bigger than the
    operating system's pipe buffer is killed part way through the write,
    and the rest was never delivered. The bridge counts what it wrote."""

    def real_launcher_for(self, child_code):
        def launcher(argv, stdin_bytes, stdout_path, stderr_path,
                     timeout_s):
            # The REAL launcher path - Popen, the feeding thread, the
            # wall clock, the tree-kill - with a python child in place of
            # the codex CLI.
            return bridge.default_launcher(
                [sys.executable, "-c", child_code],
                stdin_bytes, stdout_path, stderr_path, timeout_s)
        return launcher

    def test_a_stalled_child_records_only_what_went_into_the_pipe(self):
        """The finding, reproduced: a child that never reads, and a
        prompt eight times the usual pipe buffer."""
        payload = b"z" * (bridge.STDIN_CHUNK_BYTES * 8)
        started = time.monotonic()
        result = self.run_bridge(
            self.real_launcher_for("import time; time.sleep(60)"),
            request=make_request(timeout_s=2), casefile=payload)
        self.assertLess(time.monotonic() - started, 20)
        self.assertEqual(result["status"], "timeout")
        self.assertIsNotNone(result["prompt_bytes_sent"])
        self.assertLess(result["prompt_bytes_sent"], len(payload))
        self.assertEqual(self.result_on_disk()["prompt_bytes_sent"],
                         result["prompt_bytes_sent"])

    def test_a_child_that_reads_it_all_records_the_whole_prompt(self):
        """The other side of the same measurement, on the same size of
        payload: everything written is everything counted."""
        payload = b"z" * (bridge.STDIN_CHUNK_BYTES * 8)
        result = self.run_bridge(
            self.real_launcher_for("import sys; sys.stdin.buffer.read()"),
            request=make_request(timeout_s=30), casefile=payload)
        self.assertEqual(result["prompt_bytes_sent"], len(payload))

    def test_a_call_that_never_spawned_records_no_bytes(self):
        """A launcher that raises never wrote anything, and the result
        must not carry a count for a call that did not happen."""
        def refusing_launcher(*_args, **_kwargs):
            raise OSError("INVENTED FIXTURE - no codex on this machine")
        result = self.run_bridge(refusing_launcher)
        self.assertEqual(result["status"], "launch_failure")
        self.assertIsNone(result["prompt_bytes_sent"])
        self.assertIsNone(self.result_on_disk()["prompt_bytes_sent"])

    def test_the_smoke_call_sends_no_prompt_and_counts_none(self):
        """The unpaid smoke test passes no input at all; there is
        nothing to count and the launcher says so."""
        stdout_path = os.path.join(self.tmp, "smoke-out.txt")
        stderr_path = os.path.join(self.tmp, "smoke-err.txt")
        code, timed_out, sent = bridge.default_launcher(
            [sys.executable, "-c", "print('OK')"], None,
            stdout_path, stderr_path, 30)
        self.assertEqual((code, timed_out), (0, False))
        self.assertIsNone(sent)

    def test_every_result_the_bridge_writes_carries_the_field(self):
        fake = FakeLauncher(response_text=GOOD_TEXT)
        self.run_bridge(fake)
        self.assertIn("prompt_bytes_sent", self.result_on_disk())


# ---------------------------------------------------------------------------
# Owner ruling AC15 (unit U3d): the per-pass archive (P8) and the delta
# re-audit. A re-dispatched evidence audit no longer overwrites the first
# pass's findings and dispositions - the debrief's defect 6 - and a
# rebuilding correction goes back to the auditor as a delta only.
# ---------------------------------------------------------------------------

class ArchiveCase(EvidenceCase):
    """The two evidence-record helpers, without re-running the whole of
    TestEvidenceRecord under a second class name."""

    def gather_fact(self, capture_path, fact_id="rent_per_megawatt_q"):
        capture = canonical.read_json(capture_path)
        gathered = dict(capture["tier1"][0])
        gathered["id"] = fact_id
        gathered["derived"] = None
        capture["tier1"].append(gathered)
        canonical.write_canonical_json(capture_path, capture)
        return fact_id

    def resolution_file(self, entries):
        path = os.path.join(self.tmp, "evidence", bridge.RESOLUTION_NAME)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        canonical.write_canonical_json(path, {"resolutions": entries})
        return path


class TestPerPassArchive(ArchiveCase):
    """A re-dispatched evidence audit keeps every pass whole."""

    def first_pass(self):
        fake = EvidenceLauncher(overall="pass 1 overall")
        capture, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        gathered = self.gather_fact(capture)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture, self.out_path()])
        self.assertEqual(code, 0, printed)
        return capture

    def test_a_single_pass_numbers_itself_one_and_carries_no_prior(self):
        capture = self.first_pass()
        block = canonical.read_json(capture)["evidence_challenge"]
        self.assertEqual(block["current_pass"], 1)
        self.assertEqual(block["prior_passes"], [])
        self.assertEqual(block["scope"], "full")
        self.assertTrue(os.path.isfile(
            os.path.join(self.out_path(), "result.pass1.json")))
        self.assertTrue(os.path.isfile(
            os.path.join(self.out_path(), "resolution.pass1.json")))

    def test_a_redispatched_audit_keeps_the_first_passs_findings(self):
        """The debrief's defect 6: pass-1 dispositions must exist
        somewhere in the run. Now they are kept whole in prior_passes."""
        capture = self.first_pass()
        # Re-dispatch: the runbook removes result.json; the numbered pass
        # files stay. The second pass raises a DIFFERENT finding.
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        fake2 = EvidenceLauncher(
            findings=[evidence_finding(id="E2", detail="INVENTED - pass 2 "
                                       "doubts the peer set.")],
            overall="pass 2 overall")
        code, _ = self.main_with(
            fake2, ["evidence", capture, self.out_path()])
        self.assertEqual(code, 0)
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result["pass"], 2)
        self.resolution_file({"E2": {"disposition": "overruled",
                                     "reason": "INVENTED - the peer set "
                                     "here is honest because every name "
                                     "shares the same contract structure "
                                     "and duration, which the record "
                                     "already carries in full for all."}})
        code, printed = self.main_with(
            fake2, ["evidence-record", capture, self.out_path()])
        self.assertEqual(code, 0, printed)
        block = canonical.read_json(capture)["evidence_challenge"]
        self.assertEqual(block["current_pass"], 2)
        self.assertEqual(len(block["prior_passes"]), 1)
        prior = block["prior_passes"][0]
        self.assertEqual(prior["pass"], 1)
        self.assertEqual(prior["overall"], "pass 1 overall")
        self.assertEqual(prior["findings"][0]["id"], "E1")
        # The pass-1 DISPOSITION survives - the whole point of the fix.
        self.assertEqual(prior["resolutions"]["E1"]["disposition"],
                         "captured")
        # The current pass is pass 2, its own finding and answer.
        self.assertEqual(block["findings"][0]["id"], "E2")
        self.assertEqual(block["resolutions"]["E2"]["disposition"],
                         "overruled")

    def test_a_missing_numbered_pass_is_backfilled_at_record(self):
        """Audit round 5 (r5-3): if a crash left result.json without its
        numbered archive copy, evidence-record backfills the copy, so a
        later re-dispatch numbers PAST it instead of silently reusing pass 1
        and overwriting it (the debrief's defect 6 returning)."""
        fake = EvidenceLauncher(overall="pass 1")
        capture, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        # Emulate the crash: the numbered copy never reached disk.
        numbered = os.path.join(self.out_path(),
                                bridge.RESULT_PASS_TEMPLATE % 1)
        os.remove(numbered)
        gathered = self.gather_fact(capture)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture, self.out_path()])
        self.assertEqual(code, 0, printed)
        # The numbered copy is backfilled ...
        self.assertTrue(os.path.exists(numbered))
        # ... so a re-dispatch numbers past it rather than reusing pass 1.
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.main_with(EvidenceLauncher(overall="pass 2"),
                       ["evidence", capture, self.out_path()])
        result2 = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result2["pass"], 2)

    def test_a_pass2_raw_result_crash_does_not_corrupt_the_archive(self):
        """Audit round 6 (r6-1): a crash on pass 2 that leaves the RAW
        result.json (no `pass` field) must still number as pass 2 - not
        default to 1, overwrite pass 1's resolution, and record pass 2 as
        current_pass 1, losing pass 1's record."""
        capture = self.first_pass()
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        fake2 = EvidenceLauncher(
            findings=[evidence_finding(id="E2", detail="INVENTED - pass 2 "
                                       "doubts the peer set.")],
            overall="pass 2 overall")
        self.main_with(fake2, ["evidence", capture, self.out_path()])
        # Emulate the crash: the raw result.json (no pass) is on disk and
        # the numbered pass-2 copy never landed.
        out = self.out_path()
        raw = canonical.read_json(os.path.join(out, bridge.RESULT_NAME))
        raw.pop("pass", None)
        raw.pop("scope", None)
        canonical.write_canonical_json(os.path.join(out, bridge.RESULT_NAME),
                                       raw)
        os.remove(os.path.join(out, bridge.RESULT_PASS_TEMPLATE % 2))
        self.resolution_file({"E2": {"disposition": "overruled",
                                     "reason": "INVENTED - the peer set here "
                                     "is honest because every name shares the "
                                     "same contract structure and duration "
                                     "the record already carries."}})
        code, printed = self.main_with(
            fake2, ["evidence-record", capture, out])
        self.assertEqual(code, 0, printed)
        block = canonical.read_json(capture)["evidence_challenge"]
        self.assertEqual(block["current_pass"], 2)
        self.assertEqual(len(block["prior_passes"]), 1)
        self.assertEqual(block["prior_passes"][0]["pass"], 1)
        self.assertEqual(
            block["prior_passes"][0]["resolutions"]["E1"]["disposition"],
            "captured")
        self.assertEqual(
            canonical.read_json(
                os.path.join(out, bridge.RESOLUTION_PASS_TEMPLATE % 1))
            ["resolutions"]["E1"]["disposition"], "captured")


class TestDeltaReaudit(ArchiveCase):
    """Owner ruling AC15 (P8): a rebuilding correction goes back to the
    auditor as a delta - the changed facts and the prior findings, never
    the whole record - and the delta clears the correction."""

    def audited_capture_with_correction(self):
        fake = EvidenceLauncher(overall="first full pass")
        capture, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        gathered = self.gather_fact(capture)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        self.main_with(fake, ["evidence-record", capture, self.out_path()])
        # A rebuilding correction, as the correct command would record it.
        doc = canonical.read_json(capture)
        fact = doc["tier1"][0]
        doc.setdefault("corrections", []).append(
            {"fact_id": fact["id"], "old": fact["value"], "new": "0.01",
             "source": "corrected", "reason": None, "by": "test",
             "at": "2026-09-15T00:00:00Z",
             "classification": "rebuilding", "reaudited": False})
        canonical.write_canonical_json(capture, doc)
        return capture, fact["id"]

    def test_delta_refuses_without_a_prior_audit(self):
        capture = self.make_capture()
        doc = canonical.read_json(capture)
        doc.pop("evidence_challenge", None)
        canonical.write_canonical_json(capture, doc)
        code, printed = self.main_with(
            EvidenceLauncher(), ["evidence", capture, self.out_path(),
                                 "--delta"])
        self.assertEqual(code, 3)
        self.assertIn("SUCCESSFUL full", printed)

    def test_delta_refuses_when_no_rebuilding_correction_awaits(self):
        fake = EvidenceLauncher()
        capture, _, _ = self.run_evidence(fake)
        gathered = self.gather_fact(capture)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        self.main_with(fake, ["evidence-record", capture, self.out_path()])
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        code, printed = self.main_with(
            fake, ["evidence", capture, self.out_path(), "--delta"])
        self.assertEqual(code, 3)
        self.assertIn("no rebuilding correction", printed)

    def test_the_delta_brief_carries_only_the_change_and_prior_findings(self):
        capture, fact_id = self.audited_capture_with_correction()
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        fake = EvidenceLauncher(overall="delta pass")
        code, _ = self.main_with(
            fake, ["evidence", capture, self.out_path(), "--delta"])
        self.assertEqual(code, 0)
        with open(os.path.join(self.out_path(), bridge.BRIEF_NAME),
                  encoding="utf-8") as handle:
            brief = handle.read()
        self.assertIn("A DELTA RE-AUDIT", brief)
        self.assertIn("What was corrected", brief)
        self.assertIn(fact_id, brief)
        self.assertIn("prior pass, staged", brief)
        result = canonical.read_json(
            os.path.join(self.out_path(), bridge.RESULT_NAME))
        self.assertEqual(result["scope"], "delta")
        self.assertEqual(result["pass"], 2)

    def test_recording_the_delta_clears_the_rebuilding_correction(self):
        capture, _ = self.audited_capture_with_correction()
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        fake = EvidenceLauncher(overall="delta pass")
        self.main_with(fake, ["evidence", capture, self.out_path(),
                              "--delta"])
        self.resolution_file({"E1": {"disposition": "overruled",
                                     "reason": "INVENTED - the delta pass "
                                     "finds the corrected figure sound "
                                     "against the source the record now "
                                     "carries, so nothing here needs "
                                     "gathering or a declared gap at all."}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture, self.out_path()])
        self.assertEqual(code, 0, printed)
        doc = canonical.read_json(capture)
        self.assertTrue(doc["corrections"][0]["reaudited"])
        block = doc["evidence_challenge"]
        self.assertEqual(block["scope"], "delta")
        self.assertEqual(block["current_pass"], 2)
        self.assertEqual(len(block["prior_passes"]), 1)

    def test_the_delta_brief_carries_the_frame_rows_that_cite_the_correction(
            self):
        """Audit round 1 (r1-2): the delta brief must carry the business
        frame that cites the corrected fact, or the auditor cannot judge
        whether the frame's reading has gone inconsistent with the new
        figure."""
        fake = EvidenceLauncher(overall="first full pass")
        capture, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        gathered = self.gather_fact(capture)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        self.main_with(fake, ["evidence-record", capture, self.out_path()])
        # A rebuilding correction to a fact the frame's decisive-metric
        # row cites (exmp: "Service revenue against last year").
        doc = canonical.read_json(capture)
        cited = "segment_revenue_service_q"
        fact = next(f for f in doc["tier1"] if f["id"] == cited)
        doc.setdefault("corrections", []).append(
            {"fact_id": cited, "old": fact["value"], "new": "1",
             "source": "corrected", "reason": None, "by": "test",
             "at": "2026-09-15T00:00:00Z",
             "classification": "rebuilding", "reaudited": False})
        canonical.write_canonical_json(capture, doc)
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        code, _ = self.main_with(
            EvidenceLauncher(overall="delta"),
            ["evidence", capture, self.out_path(), "--delta"])
        self.assertEqual(code, 0)
        with open(os.path.join(self.out_path(), bridge.BRIEF_NAME),
                  encoding="utf-8") as handle:
            brief_text = handle.read()
        self.assertIn("business-frame passages that cite the correction",
                      brief_text)
        self.assertIn("Service revenue against last year", brief_text)

    def test_record_clears_only_the_dispatched_correction(self):
        """Audit round 1 (r1-3): a rebuilding correction applied AFTER the
        delta was dispatched was in no brief the auditor read, so
        recording the delta must not mark it re-audited."""
        capture, first_id = self.audited_capture_with_correction()
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        fake = EvidenceLauncher(overall="delta pass")
        # The delta is dispatched; it covers the first correction only.
        self.main_with(fake, ["evidence", capture, self.out_path(),
                              "--delta"])
        # A SECOND rebuilding correction is applied before recording.
        doc = canonical.read_json(capture)
        second = next(f for f in doc["tier1"] if f["id"] != first_id)
        doc["corrections"].append(
            {"fact_id": second["id"], "old": second["value"], "new": "1",
             "source": "corrected", "reason": None, "by": "test",
             "at": "2026-09-15T09:00:00Z",
             "classification": "rebuilding", "reaudited": False})
        canonical.write_canonical_json(capture, doc)
        self.resolution_file({"E1": {"disposition": "overruled",
                                     "reason": "INVENTED - the delta pass "
                                     "finds the corrected figure sound "
                                     "against the source the record now "
                                     "carries, so nothing needs gathering."}})
        code, printed = self.main_with(
            fake, ["evidence-record", capture, self.out_path()])
        self.assertEqual(code, 0, printed)
        doc = canonical.read_json(capture)
        by_at = {(c["fact_id"], c["at"]): c for c in doc["corrections"]}
        self.assertTrue(
            by_at[(first_id, "2026-09-15T00:00:00Z")]["reaudited"])
        self.assertFalse(
            by_at[(second["id"], "2026-09-15T09:00:00Z")]["reaudited"])

    def test_delta_refuses_when_the_only_prior_full_pass_failed(self):
        """Audit round 5 (r5-1): a delta needs a SUCCESSFUL full audit to
        build on. A FAILED full audit records a block too, but a delta over
        it would replace the failure with a success the report reads as an
        outside model having checked evidence none saw."""
        fail = FakeLauncher(returncode=1)
        capture, code, _ = self.run_evidence(fail)
        self.assertEqual(code, 3)
        self.main_with(fail, ["evidence-record", capture, self.out_path()])
        block = canonical.read_json(capture)["evidence_challenge"]
        self.assertEqual(block["status"], "failed")
        doc = canonical.read_json(capture)
        fact = doc["tier1"][0]
        doc.setdefault("corrections", []).append(
            {"fact_id": fact["id"], "old": fact["value"], "new": "0.01",
             "source": "corrected", "reason": None, "by": "test",
             "at": "2026-09-15T00:00:00Z",
             "classification": "rebuilding", "reaudited": False})
        canonical.write_canonical_json(capture, doc)
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        code, printed = self.main_with(
            FakeLauncher(returncode=1),
            ["evidence", capture, self.out_path(), "--delta"])
        self.assertEqual(code, 3)
        self.assertIn("SUCCESSFUL full", printed)

    def test_a_full_reaudit_folds_a_narrowing_sourced_correction(self):
        """Audit round 5 (r5-4): a successful full re-audit re-reads the
        whole pack, so it folds EVERY correction on record into the
        baseline - a narrowing sourced correction included, not only the
        rebuilding ones - or the post-audit record keeps calling a later
        reverted figure changed after the audit."""
        fake = EvidenceLauncher(overall="first full pass")
        capture, code, _ = self.run_evidence(fake)
        self.assertEqual(code, 0)
        gathered = self.gather_fact(capture)
        self.resolution_file({"E1": {"disposition": "captured",
                                     "fact_ids": [gathered]}})
        self.main_with(fake, ["evidence-record", capture, self.out_path()])
        # A narrowing sourced correction, as the correct command records it.
        doc = canonical.read_json(capture)
        fact = doc["tier1"][0]
        doc.setdefault("corrections", []).append(
            {"fact_id": fact["id"], "old": fact["value"], "new": "1",
             "source": "a new source", "reason": None, "by": "test",
             "at": "2026-09-15T02:00:00Z",
             "classification": "narrowing", "reaudited": False})
        canonical.write_canonical_json(capture, doc)
        # A full RE-audit re-reads the whole pack and folds the narrowing
        # correction into the baseline.
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        fake2 = EvidenceLauncher(overall="second full pass")
        self.main_with(fake2, ["evidence", capture, self.out_path()])
        self.resolution_file({"E1": {"disposition": "overruled",
                                     "reason": "INVENTED - the second full "
                                     "pass finds the pack sound; nothing "
                                     "here needs gathering or a gap."}})
        code, printed = self.main_with(
            fake2, ["evidence-record", capture, self.out_path()])
        self.assertEqual(code, 0, printed)
        doc = canonical.read_json(capture)
        narrowing = [c for c in doc["corrections"]
                     if c["classification"] == "narrowing"][0]
        self.assertTrue(narrowing["reaudited"])

    def test_delta_accepts_a_legacy_full_pass_without_scope(self):
        """Audit round 6 (r6-2): a pre-1.5.0 success block carries no
        scope; the schema defines an omitted scope as a full audit, so a
        delta must build on it rather than refuse it."""
        capture, _ = self.audited_capture_with_correction()
        doc = canonical.read_json(capture)
        doc["evidence_challenge"].pop("scope", None)
        canonical.write_canonical_json(capture, doc)
        os.remove(os.path.join(self.out_path(), bridge.RESULT_NAME))
        code, printed = self.main_with(
            EvidenceLauncher(overall="delta pass"),
            ["evidence", capture, self.out_path(), "--delta"])
        self.assertEqual(code, 0, printed)
        self.assertNotIn("SUCCESSFUL full", printed)


if __name__ == "__main__":
    unittest.main(verbosity=1)
