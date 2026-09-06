"""The end-to-end rehearsal (REBUILD-SPEC section 13): one invented capture
driven through the REAL chain - gate, two-directory freeze, sufficiency,
host, canned seats, canned challenge result, publish, read-back - with ZERO
model calls. The evidence stages run as the real commands; the seat answers
are canned fixtures; the challenge result is written by this test in the
bridge's exact result shape."""

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, validate  # noqa: E402
from council.engine import briefs, host, readback  # noqa: E402
from council.engine import runrecord  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REH = os.path.join(ROOT, "council", "tests", "fixtures", "rehearsal")
CAPTURE = os.path.join(ROOT, "council", "tests", "fixtures", "evidence",
                       "exmp-pass.json")
RUN_ID = "rehearsal-exmp-zero-model"


def cli(*args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, "-m"] + list(args), cwd=ROOT,
                          env=env, capture_output=True, text=True)


def fixture(name):
    with open(os.path.join(REH, name), "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


class TestEndToEndRehearsal(unittest.TestCase):
    """One test class, one story, asserted stage by stage."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="council-rehearsal-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def test_the_whole_chain_with_zero_model_calls(self):
        base = self.base

        # Stage 1 - the gate, as the real command.
        gate_out = os.path.join(base, "gate-result.json")
        proc = cli("council.evidence.gate", CAPTURE, "--out", gate_out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Stage 2 - the freeze, twice, byte-identical, as the real command.
        dir_a = os.path.join(base, "freeze-a")
        dir_b = os.path.join(base, "freeze-b")
        proc = cli("council.evidence.freeze", CAPTURE, dir_a, dir_b)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        record = canonical.read_json(
            os.path.join(dir_a, "freeze-record.json"))
        self.assertTrue(record["byte_identical"])
        pack_path = os.path.join(dir_a, "pack.json")
        pack_sha = record["pack_sha256"]
        self.assertEqual(canonical.sha256_file(pack_path), pack_sha)

        # Stage 3 - sufficiency, as the real command; pass required.
        suff_out = os.path.join(base, "sufficiency-result.json")
        proc = cli("council.evidence.sufficiency", pack_path,
                   "--out", suff_out)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Stage 4 - the council, stepped; every seat answered from a canned
        # fixture; usage sidecars written for every seat.
        state, run_dir = host.init(
            base, RUN_ID, pack_path, pack_sha, suff_out,
            os.path.join(REH, "question.txt"),
            os.path.join(REH, "subject.json"))
        seat_tokens = {}
        for _ in range(40):
            host.step(run_dir)
            status = host.status(run_dir)
            if status["state"] in ("DONE", "REFUSED", "FAILED"):
                break
            progressed = False
            for item in status["pending"]:
                seat = item["seat"]
                payload = fixture(seat + ".json")
                with open(os.path.join(run_dir, item["answer"]), "w",
                          encoding="utf-8") as handle:
                    json.dump(payload, handle)
                tokens = 10000 + 1000 * len(seat)
                seat_tokens[seat] = tokens
                usage = {"tokens": tokens, "tool_calls": 2, "minutes": 2.5,
                         "model": "canned-fixture-model"}
                with open(os.path.join(run_dir, "rpc",
                                       "%s-usage.json" % item["number"]),
                          "w", encoding="utf-8") as handle:
                    json.dump(usage, handle)
                progressed = True
            request_path = os.path.join(run_dir, "challenge", "request.json")
            result_path = os.path.join(run_dir, "challenge", "result.json")
            if os.path.exists(request_path) and not os.path.exists(
                    result_path):
                request = canonical.read_json(request_path)
                doc = fixture("challenge-findings.json")
                doc["run_id_echo"] = request["run_id"]
                doc["nonce_echo"] = request["nonce"]
                doc["casefile_sha256_echo"] = request["casefile_sha256"]
                canonical.write_canonical_json(result_path, {
                    "status": "success", "failure_reason": None,
                    "findings": doc, "usage_tokens": 142000,
                    "raw_output": "response.json", "returncode": 0})
                progressed = True
            if not progressed and status["state"] not in (
                    "DONE", "REFUSED", "FAILED"):
                self.fail("the host stopped asking for anything in state %s"
                          % status["state"])
        self.assertEqual(host.status(run_dir)["state"], "DONE")

        # Stage 5 - read-back: the separate verifier agrees (exit-style 0).
        self.assertEqual(readback.check(run_dir), 0)

        # The published verdict is schema-valid and says what the canned
        # council said.
        verdict = canonical.read_json(os.path.join(run_dir, "verdict.json"))
        with open(os.path.join(ROOT, "council", "schemas",
                               "verdict_schema.json"), "rb") as handle:
            schema = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(validate.validate(verdict, schema), [])
        self.assertEqual(verdict["rating"], "buy")
        self.assertEqual(verdict["warnings"], [])
        self.assertEqual(verdict["mispricing"]["read"], "cheap")
        self.assertEqual(verdict["provenance"]["pack_hash"], pack_sha)

        # The change appendix carries exactly the chairman's one rewording,
        # labeled a plain change - transparency with nothing to warn about.
        appendix = verdict["challenge"]["change_appendix"]
        self.assertEqual([row["field"] for row in appendix],
                         ["conviction_rationale"])
        self.assertEqual(appendix[0]["label"], "change")

        # Every finding disposed of by name.
        dispositions = {d["finding_id"]: d["disposition"]
                        for d in verdict["challenge"]["dispositions"]}
        self.assertEqual(set(dispositions), {"F1", "F2"})

        # Token accounting: every seat's sidecar reached provenance; the
        # challenger's cost is the bridge result's own number.
        tokens = verdict["provenance"]["tokens"]
        self.assertEqual(tokens["per_seat"],
                         {seat: seat_tokens[seat] for seat in seat_tokens})
        self.assertEqual(tokens["seats_total"], sum(seat_tokens.values()))
        self.assertEqual(tokens["challenger"], 142000)
        self.assertGreater(verdict["provenance"]["prompt_bytes_total"], 0)

        # The Atlas envelope: null hash inside the verdict (a document
        # cannot carry its own hash); the standalone file carries the real
        # one, and it matches the published bytes.
        self.assertIsNone(verdict["atlas_envelope"]["verdict_hash"])
        envelope = canonical.read_json(
            os.path.join(run_dir, "atlas-envelope.json"))
        self.assertEqual(envelope["verdict_hash"],
                         canonical.sha256_file(
                             os.path.join(run_dir, "verdict.json")))
        self.assertEqual(envelope["pack_hash"], pack_sha)

        # Zero model calls, shown on the record: every answer was written by
        # this test, and the run record holds no bridge launch - the
        # challenge result appeared as a file, exactly as the protocol has
        # the session do it.
        events = [e["event"] for e in runrecord.read_events(run_dir)]
        self.assertIn("challenge_requested", events)
        self.assertIn("published", events)
        self.assertEqual(events[-1], "run_finished")

        # Stage 6 - the report, rendered by the real renderer over this
        # run directory, as the real command.
        proc = cli("council.report.render_report", run_dir)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report_path = os.path.join(run_dir, "report.html")
        with open(report_path, "rb") as handle:
            page = handle.read().decode("utf-8")
        self.assertGreater(len(page), 10000)
        # Self-contained: no external reference anywhere on the page.
        import re
        self.assertEqual(
            re.findall(r'(?:src|href)\s*=\s*"https?://', page), [])
        # The rating in plain words, the empty-warnings sentence, and the
        # change appendix showing the chairman's one rewording.
        self.assertIn("Buy", page)
        self.assertIn("This verdict carries no warnings.", page)
        self.assertIn("grew 12 percent on the year", page)
        self.assertIn("one quarter, not yet a trend", page)
        # The footer carries the same hash the envelope recorded.
        self.assertIn(envelope["verdict_hash"], page)

        # Owner ruling AB23: the standalone package stands alone. It
        # names its own subject and sitting, states the audit outcome
        # and the auditor's ceiling, carries the whole warnings list,
        # tags every row for bounds, and flags any sizing id the
        # council's own list does not pin.
        self.assertEqual(verdict["schema_version"], "1.3.0")
        subject = verdict["subject"]
        self.assertEqual(envelope["subject_name"], subject["name"])
        self.assertEqual(envelope["subject_ticker"], subject["ticker"])
        self.assertEqual(envelope["subject_listing"], subject["listing"])
        self.assertEqual(envelope["subject_currency"],
                         subject["currency"])
        self.assertEqual(envelope["run_id"], RUN_ID)
        self.assertEqual(envelope["challenge_status"], "success")
        self.assertEqual(envelope["warnings"], verdict["warnings"])
        self.assertEqual(envelope["unknown_sizing_ids"], [])
        for row in envelope["key_numbers"] + envelope["sizing_inputs"]:
            self.assertIn("bound", row)
        # Every sizing row speaks the unit its id is pinned to.
        for row in envelope["sizing_inputs"]:
            pinned = briefs.pinned_sizing_unit(row["id"])
            if row["value"] is not None:
                self.assertEqual(row["unit"], pinned, row["id"])
        # And the page shows the package as it travels.
        atlas = page[page.index('<h2 id="atlas">'):]
        self.assertIn(html.escape(subject["name"], quote=True), atlas)
        self.assertIn("The outside audit ran, and the package says so.",
                      atlas)


class TestKindRehearsals(unittest.TestCase):
    """THEMES part 3: the same REAL chain, kind by kind - one canned
    BASKET run and one canned THEME run (universe mode) driven gate ->
    freeze -> sufficiency -> host -> nine canned seats -> canned
    challenge result -> publish -> read-back -> rendered report, plus
    the ruled empty-theme refusal (the shopping list, at capture cost).
    The captures are the part-1 evidence pass fixtures; the canned
    answers live under fixtures/rehearsal/<kind>/. Zero model calls."""

    @classmethod
    def setUpClass(cls):
        cls.base = tempfile.mkdtemp(prefix="council-kind-rehearsal-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.base, ignore_errors=True)

    def kind_fixture(self, kind, name):
        with open(os.path.join(REH, kind, name), "rb") as handle:
            return json.loads(handle.read().decode("utf-8"))

    def evidence_stages(self, work, capture_path):
        """Gate, two-directory freeze and sufficiency as the real
        commands. Returns (pack_path, pack_sha256, sufficiency_path)."""
        proc = cli("council.evidence.gate", capture_path, "--out",
                   os.path.join(work, "gate-result.json"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        dir_a = os.path.join(work, "freeze-a")
        dir_b = os.path.join(work, "freeze-b")
        proc = cli("council.evidence.freeze", capture_path, dir_a, dir_b)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        record = canonical.read_json(
            os.path.join(dir_a, "freeze-record.json"))
        self.assertTrue(record["byte_identical"])
        pack_path = os.path.join(dir_a, "pack.json")
        suff_path = os.path.join(work, "sufficiency-result.json")
        proc = cli("council.evidence.sufficiency", pack_path,
                   "--out", suff_path)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return pack_path, record["pack_sha256"], suff_path

    def drive_canned(self, kind, run_id, capture_name,
                     canned_mutate=None):
        """One whole canned run. Returns (verdict, page). `canned_mutate`
        is called as (name, payload) on each canned answer before it is
        written and on the canned challenge document (name "challenge"),
        so one rehearsal can be driven into a named shape."""
        work = os.path.join(self.base, run_id)
        os.makedirs(work)
        capture_path = os.path.join(
            ROOT, "council", "tests", "fixtures", "evidence",
            capture_name)
        capture = canonical.read_json(capture_path)
        pack_path, pack_sha, suff_path = self.evidence_stages(
            work, capture_path)
        question_path = os.path.join(work, "question.txt")
        with open(question_path, "w", encoding="utf-8") as handle:
            handle.write(capture["question_verbatim"])
        subject_path = os.path.join(work, "subject.json")
        canonical.write_canonical_json(subject_path, capture["subject"])
        state, run_dir = host.init(work, run_id, pack_path, pack_sha,
                                   suff_path, question_path, subject_path)
        self.assertEqual(state, "INIT")
        for _ in range(40):
            host.step(run_dir)
            status = host.status(run_dir)
            if status["state"] in ("DONE", "REFUSED", "FAILED"):
                break
            progressed = False
            for item in status["pending"]:
                payload = self.kind_fixture(kind, item["seat"] + ".json")
                if canned_mutate:
                    canned_mutate(item["seat"], payload)
                with open(os.path.join(run_dir, item["answer"]), "w",
                          encoding="utf-8") as handle:
                    json.dump(payload, handle)
                progressed = True
            request_path = os.path.join(run_dir, "challenge",
                                        "request.json")
            result_path = os.path.join(run_dir, "challenge",
                                       "result.json")
            if os.path.exists(request_path) and not os.path.exists(
                    result_path):
                request = canonical.read_json(request_path)
                doc = self.kind_fixture(kind, "challenge-findings.json")
                if canned_mutate:
                    canned_mutate("challenge", doc)
                doc["run_id_echo"] = request["run_id"]
                doc["nonce_echo"] = request["nonce"]
                doc["casefile_sha256_echo"] = request["casefile_sha256"]
                canonical.write_canonical_json(result_path, {
                    "status": "success", "failure_reason": None,
                    "findings": doc, "usage_tokens": 101000,
                    "raw_output": "response.json", "returncode": 0})
                progressed = True
            if not progressed and status["state"] not in (
                    "DONE", "REFUSED", "FAILED"):
                self.fail("the host stopped asking for anything in "
                          "state %s" % status["state"])
        self.assertEqual(host.status(run_dir)["state"], "DONE")
        self.assertEqual(readback.check(run_dir), 0)
        verdict = canonical.read_json(os.path.join(run_dir,
                                                   "verdict.json"))
        with open(os.path.join(ROOT, "council", "schemas",
                               "verdict_schema.json"), "rb") as handle:
            schema = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(validate.validate(verdict, schema), [])
        proc = cli("council.report.render_report", run_dir)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        with open(os.path.join(run_dir, "report.html"), "rb") as handle:
            page = handle.read().decode("utf-8")
        self.last_run_dir = run_dir
        return verdict, page


    def envelope_stands_alone(self, verdict, page, run_id):
        """AB23, asserted the same way on every kind: the package names
        its subject, carries the audit state, tags its rows, and the
        read-back still holds field for field against the verdict's own
        copy."""
        envelope = canonical.read_json(
            os.path.join(self.last_run_dir, "atlas-envelope.json"))
        subject = verdict["subject"]
        self.assertEqual(verdict["schema_version"], "1.3.0")
        self.assertEqual(envelope["subject_name"], subject["name"])
        self.assertEqual(envelope["subject_ticker"], subject["ticker"])
        self.assertEqual(envelope["run_id"], run_id)
        self.assertEqual(envelope["challenge_status"],
                         verdict["challenge"]["status"])
        self.assertEqual(
            envelope["endorsement_highest_rating_supported"],
            (verdict["challenge"]["endorsement"] or {}).get(
                "highest_rating_supported"))
        self.assertEqual(envelope["warnings"], verdict["warnings"])
        for row in envelope["key_numbers"] + envelope["sizing_inputs"]:
            self.assertIn("bound", row)
        for row in envelope["sizing_inputs"]:
            if row["value"] is not None:
                self.assertEqual(row["unit"],
                                 briefs.pinned_sizing_unit(row["id"]),
                                 row["id"])
        atlas = page[page.index('<h2 id="atlas">'):]
        self.assertIn(html.escape(subject["name"], quote=True), atlas)
        self.assertEqual(readback.check(self.last_run_dir), 0)
        return envelope

    def test_a_canned_basket_run_end_to_end(self):
        verdict, page = self.drive_canned(
            "basket", "rehearsal-basket-zero-model", "basket-pass.json")
        subject = verdict["subject"]
        self.assertEqual(verdict["rating"], "buy")
        # The chairman's one note per named constituent travels whole.
        canned = self.kind_fixture("basket", "chair_draft.json")
        self.assertEqual(verdict["constituent_notes"],
                         canned["draft_verdict"]["constituent_notes"])
        # The envelope's kind fields are the frozen subject's, never
        # chair-authored.
        envelope = verdict["atlas_envelope"]
        self.assertEqual(envelope["subject_kind"], "basket")
        self.assertEqual(envelope["constituents"],
                         subject["constituents"])
        self.assertEqual(envelope["thesis_proportions"],
                         subject["thesis_proportions"])
        self.assertIsNone(envelope["vehicle"])
        # The bound tripwire kept its constituent tag.
        self.assertEqual(
            verdict["tripwires"]["reopening_triggers"][0]["constituent"],
            "ACHP")
        # The rendered page speaks the kind: the sentence, the table
        # with a frozen price, and the ruled emphasis label verbatim.
        self.assertIn("The subject is a basket of 2 named instruments "
                      "judged as one idea.", page)
        self.assertIn('<td class="nowrap">231.40 USD</td>', page)
        self.assertIn("internal emphasis — a statement about the thesis "
                      "itself, never an instruction to any portfolio:",
                      page)
        self.envelope_stands_alone(verdict, page,
                                   "rehearsal-basket-zero-model")

    def test_a_canned_theme_run_end_to_end(self):
        verdict, page = self.drive_canned(
            "theme", "rehearsal-theme-zero-model", "theme-pass.json")
        self.assertEqual(verdict["rating"], "monitor")
        # Every declared falsifier is answered by exactly one row, and
        # the level row quotes the prior-period fact byte-for-byte.
        rows = verdict["tripwires"]["falsifiers"]
        self.assertEqual([row.get("theme_falsifier_id") for row in rows],
                         ["storage_install_growth",
                          "storage_credit_repeal"])
        self.assertEqual(rows[0]["prior_period_value"], "9.1")
        self.assertEqual(rows[0]["prior_period_unit"], "GW")
        self.assertEqual(rows[0]["prior_period_as_of"], "2025-08-15")
        self.assertIsNone(rows[1]["prior_period_value"])
        envelope = verdict["atlas_envelope"]
        self.assertEqual(envelope["subject_kind"], "theme")
        self.assertEqual(envelope["constituents"],
                         verdict["subject"]["constituents"])
        self.assertIsNone(envelope["thesis_proportions"])
        # The price trigger stays bound to the member its own words
        # name - a member-specific trigger must never publish as
        # subject-wide (audit finding THEMES-D r1-1).
        self.assertEqual(
            verdict["tripwires"]["reopening_triggers"][0]["constituent"],
            "GSTA")
        # The page: the falsifier block with the prior period and the
        # REG-18 metric-identity line - and the trigger row carries the
        # member tag beside the trigger's own words.
        self.assertIn("The theme's falsifiers", page)
        self.assertIn("Prior period: 9.10 GW, as of 2025-08-15.", page)
        self.assertIn("Metric identity assumed: ", page)
        self.assertIn('<span class="tag">GSTA</span> INVENTED FIXTURE - '
                      "reopen if Grid Storage Alpha closes at or under "
                      "40.00 USD.", page)
        self.envelope_stands_alone(verdict, page,
                                   "rehearsal-theme-zero-model")

    def test_a_canned_anchorless_run_end_to_end(self):
        """ANCHORLESS-SPEC section 9: one canned rehearsal on an asset
        with no earnings, through the real chain, zero model calls. The
        thing this whole unit exists to prove is the first assertion -
        the rating is NOT hold."""
        verdict, page = self.drive_canned(
            "anchorless", "rehearsal-anchorless-zero-model",
            "btc-pass.json")
        # The failure this unit exists to fix: an asset with no earnings
        # could only ever be rated hold.
        self.assertEqual(verdict["rating"], "buy")

        block = verdict["scenario_rating"]
        self.assertEqual(block["basis"], "rating")
        self.assertTrue(block["aggregated"])
        self.assertIsNone(block["not_aggregated_reason"])
        # The rating the published block computes IS the published
        # rating: a verdict can never state one the ladder does not earn.
        self.assertEqual(block["rating"], verdict["rating"])

        # The arithmetic is on the page, computed by the machine from
        # frozen pack facts - never a seat's mental arithmetic.
        self.assertEqual(block["reference_price"], "60000.00")
        self.assertEqual(block["expected_price"], "83400")          # 0.25x42000 + 0.45x72000 + 0.30x135000
        self.assertEqual(block["expected_annualised_pct"], "39.00")
        self.assertEqual(block["cash_pct"], "3.68")
        self.assertEqual(block["volatility_pct"], "48.60")
        self.assertEqual(block["bar_pct"], "20.69")
        self.assertEqual(block["cash_rate_fact_id"], "risk_free_rate_3m")
        self.assertEqual(block["volatility_fact_id"],
                         "realized_volatility_5y")

        # The sensitivity is printed EVERY time (AB13.2): the odds at
        # which the rating changes, and the bar one ruled step either
        # side of where it stands.
        flip = block["sensitivity"]["flip"]
        self.assertEqual(flip["flips_to"], "hold")
        self.assertIsNotNone(flip["probability_at_flip"])
        self.assertEqual([step["label"] for step
                          in block["sensitivity"]["bar_steps"]],
                         ["one step lower", "as ruled", "one step higher"])

        # Every seat's own odds survive into the record, so where the
        # chairman departed from the bench is visible.
        seats = {row["seat"]: row for row in block["seat_ladders"]}
        self.assertEqual(len(seats), 5)
        bear = {row["name"]: row["probability"]
                for row in seats["advisor_bear"]["scenarios"]}
        bull = {row["name"]: row["probability"]
                for row in seats["advisor_bull"]["scenarios"]}
        self.assertEqual(bear["Custody unwind"], "0.40")
        self.assertEqual(bull["Custody unwind"], "0.15")

        # The hand-off carries the class, the block and the shape.
        envelope = verdict["atlas_envelope"]
        self.assertEqual(envelope["subject_kind"], "bitcoin")
        self.assertEqual(envelope["asset_class"], "crypto")
        self.assertIsNone(envelope["product"])
        self.assertEqual(envelope["scenario_rating"], block)

        # The cold read's four complaints, answered on the page.
        self.assertIn("Bitcoin", page)
        self.assertIn("39.00", page)          # the earned result
        self.assertIn("20.69", page)          # the bar it cleared
        self.assertIn("25", page)             # the recovery duration
        self.assertIn("2026-09-16", page)     # the dated calendar

        # AB23 on an anchorless subject: the package stands alone, and
        # the sizing rows speak the pinned units even though the bar
        # reads the SAME volatility fact as a percentage - the one
        # restatement the contract allows, checked by the machine.
        package = self.envelope_stands_alone(
            verdict, page, "rehearsal-anchorless-zero-model")
        rows = {row["id"]: row for row in package["sizing_inputs"]}
        self.assertEqual(rows["realized_volatility"]["value"], "0.486")
        self.assertEqual(rows["realized_volatility"]["unit"],
                         "fraction_annualized")
        self.assertEqual(block["volatility_pct"], "48.60")
        self.assertEqual(rows["drawdown_shape"]["unit"],
                         "fraction_of_price")
        self.assertEqual(rows["event_dates"]["unit"], "iso_date")

    def test_a_canned_anchorless_run_refuses_an_unearned_rating(self):
        """The same canned bench with the chairman's rating raised one
        band above what his own ladder earns: the host refuses it, names
        both ratings, and no verdict publishes."""
        work = os.path.join(self.base, "unearned")
        os.makedirs(work)
        capture_path = os.path.join(
            ROOT, "council", "tests", "fixtures", "evidence",
            "btc-pass.json")
        capture = canonical.read_json(capture_path)
        pack_path, pack_sha, suff_path = self.evidence_stages(
            work, capture_path)
        question_path = os.path.join(work, "question.txt")
        with open(question_path, "w", encoding="utf-8") as handle:
            handle.write(capture["question_verbatim"])
        subject_path = os.path.join(work, "subject.json")
        canonical.write_canonical_json(subject_path, capture["subject"])
        state, run_dir = host.init(work, "rehearsal-unearned-rating",
                                   pack_path, pack_sha, suff_path,
                                   question_path, subject_path)
        self.assertEqual(state, "INIT")
        refusal = None
        for _ in range(40):
            host.step(run_dir)
            status = host.status(run_dir)
            if status["state"] in ("DONE", "REFUSED", "FAILED"):
                break
            for item in status["pending"]:
                payload = self.kind_fixture("anchorless",
                                            item["seat"] + ".json")
                if item["seat"] == "chair_draft":
                    payload = json.loads(json.dumps(payload))
                    payload["draft_verdict"]["rating"] = "strong_buy"
                with open(os.path.join(run_dir, item["answer"]), "w",
                          encoding="utf-8") as handle:
                    json.dump(payload, handle)
            events = runrecord.read_events(run_dir)
            rejected = [event for event in events
                        if event["event"] == "answer_rejected"
                        and event["seat"] == "chair_draft"]
            if rejected:
                refusal = rejected[0]
                break
        self.assertIsNotNone(refusal, "the unearned rating was accepted")
        reason = " ".join(refusal.get("reasons") or [refusal.get("reason")
                                                     or ""])
        self.assertIn("rates this strong buy", reason)
        self.assertIn("earns buy", reason)
        self.assertFalse(os.path.exists(os.path.join(run_dir,
                                                     "verdict.json")))

    def test_a_divergent_endorsement_is_named_on_the_page(self):
        """Owner ruling AB16(5), the whole chain: the challenger endorses
        a ceiling of monitor, the chairman publishes sell, and the note
        naming both ratings reaches the RENDERED PAGE - in the loud band
        at the top, where the reader cannot miss it. The live Bitcoin run
        that earned this change published exactly this pair and said
        nothing. Nothing is gated: the chairman's sell still publishes."""

        def mutate(name, payload):
            if name == "chair_resolve":
                payload["final_verdict"]["rating"] = "sell"
            elif name == "challenge":
                payload["endorsement"] = {
                    "highest_rating_supported": "monitor"}

        verdict, page = self.drive_canned(
            "basket", "rehearsal-divergent-endorsement", "basket-pass.json",
            canned_mutate=mutate)
        self.assertEqual(verdict["rating"], "sell")
        self.assertEqual(verdict["challenge"]["endorsement"],
                         {"highest_rating_supported": "monitor"})
        notes = [w for w in verdict["warnings"]
                 if w.startswith("Rating against the outside auditor")]
        self.assertEqual(len(notes), 1)
        self.assertIn("published sell", notes[0])
        self.assertIn("monitor", notes[0])
        # The band escapes what it prints, so the page is checked against
        # the escaped note - the reader's own text, not the raw string.
        self.assertIn('<div class="card alarm"><span class="shout">%s</span>'
                      "</div>" % html.escape(notes[0], quote=True), page)
        # AB23(2): and the same note is INSIDE the package, so a reader
        # that never opens the verdict still learns the council
        # published sell under a ceiling of monitor.
        package = canonical.read_json(
            os.path.join(self.last_run_dir, "atlas-envelope.json"))
        self.assertEqual(package["rating"], "sell")
        self.assertEqual(package["endorsement_highest_rating_supported"],
                         "monitor")
        self.assertIn(notes[0], package["warnings"])
        self.assertEqual(readback.check(self.last_run_dir), 0)

    def test_an_empty_theme_is_refused_with_the_shopping_list(self):
        work = os.path.join(self.base, "empty-theme")
        runs_root = os.path.join(work, "runs")
        os.makedirs(runs_root)
        capture = canonical.read_json(os.path.join(
            ROOT, "council", "tests", "fixtures", "evidence",
            "theme-pass.json"))
        # The theme stripped of its expression and its falsifiers - and
        # of the checklist rows bound to the names it no longer has.
        del capture["subject"]["constituents"]
        del capture["subject"]["theme"]
        capture["sufficiency"]["requirements"] = [
            row for row in capture["sufficiency"]["requirements"]
            if row["kind"] != "constituent_essential"]
        stripped_path = os.path.join(work, "stripped-theme.json")
        canonical.write_canonical_json(stripped_path, capture)
        # The gate accepts: nothing present is malformed - the absence
        # belongs to the sufficiency gate's ruled refusal.
        proc = cli("council.evidence.gate", stripped_path, "--out",
                   os.path.join(work, "gate-result.json"))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        dir_a = os.path.join(work, "freeze-a")
        dir_b = os.path.join(work, "freeze-b")
        proc = cli("council.evidence.freeze", stripped_path, dir_a, dir_b)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = cli("council.evidence.sufficiency",
                   os.path.join(dir_a, "pack.json"),
                   "--out", os.path.join(work, "sufficiency-result.json"))
        # Exit 3, and the message IS the product: the shopping list of
        # what would make the question sittable, at capture cost.
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("an investable expression - names or a vehicle",
                      proc.stdout)
        self.assertIn("a fact that could prove the theme wrong",
                      proc.stdout)
        self.assertIn("2 to 8 named instruments", proc.stdout)
        self.assertIn("Gather the items above and capture again",
                      proc.stdout)
        # No seat was paid and no run directory was created.
        self.assertEqual(os.listdir(runs_root), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
