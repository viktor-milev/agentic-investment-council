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
                 smoke_returncode=0, smoke_stdout="OK\n"):
        self.calls = []
        self.returncode = returncode
        self.timed_out = timed_out
        self.response_text = response_text
        self.events_lines = events_lines or []
        self.stderr_text = stderr_text
        self.smoke_returncode = smoke_returncode
        self.smoke_stdout = smoke_stdout

    def __call__(self, argv, stdin_bytes, stdout_path, stderr_path, timeout_s):
        self.calls.append({"argv": list(argv), "stdin": stdin_bytes,
                           "timeout_s": timeout_s})
        if "-m" in argv:
            with open(stdout_path, "wb") as handle:
                handle.write(self.smoke_stdout.encode("utf-8"))
            with open(stderr_path, "wb") as handle:
                handle.write(b"")
            return self.smoke_returncode, False
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
        return self.returncode, self.timed_out

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
