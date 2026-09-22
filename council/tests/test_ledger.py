"""Ledger suite: the row, the append and its hash in read-back, the
scoring rules read from data, and the scorecard that refuses the
correlation below twenty rows (UPGRADE-2 U7).

Run:  python council/tests/test_ledger.py     (exit code authoritative)

Zero model calls; invented fixtures only; the scoring script never fetches.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, validate  # noqa: E402
from council.ledger import ledger, score  # noqa: E402
from council.ledger import report as ledger_report  # noqa: E402
from council.engine import readback, runrecord  # noqa: E402
from council.tests import test_engine  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_DIR = os.path.join(ROOT, "council", "schemas")
FIX = os.path.join(ROOT, "council", "tests", "fixtures", "ledger")
RULES = ledger.load_rules()


def _cli(*args):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run([sys.executable, "-m"] + list(args), cwd=ROOT,
                          env=env, capture_output=True, text=True)


# ---- invented rows and observations, with known outcomes -----------------

def _row(row_id, rating, **over):
    """A valid ledger row with sane defaults; overrides set what a test
    turns on. Book-blind: identity only."""
    row = {
        "ledger_row_version": "1.0.0",
        "ledger_row_id": row_id,
        "run_id": row_id,
        "verdict_schema_version": "1.4.0",
        "prior_ledger_row_id": None,
        "subject": {"kind": "single_stock", "name": "Example Corp",
                    "ticker": "EXMP", "listing": "NASDAQ", "currency": "USD"},
        "asset_class": "equity",
        "verdict_date": "2026-01-05",
        "rating": rating,
        "mispricing": {"read": "no_view", "magnitude": None},
        "price_at_verdict": {"value": "100", "unit": "USD_per_share",
                             "fact_id": "price_last"},
        "benchmark": {"name": "SPDR S&P 500 ETF", "ticker": "SPY",
                      "level_at_verdict": "100", "unit": "index",
                      "fact_id": "benchmark_level_at_sitting"},
        "horizons": [{"trading_days": 63, "due_date": "2026-04-06"},
                     {"trading_days": 126, "due_date": "2026-07-06"},
                     {"trading_days": 252, "due_date": "2027-01-04"}],
        "tripwire_levels": [{"level": "80", "unit": "USD_per_share",
                             "meaning": "the invalidation price"}],
        "reopening_triggers": [{"kind": "event", "detail": "results",
                                "level": None, "unit": None, "date": None}],
        "falsifiers": [{"figure_name": "quarterly cash flow",
                        "date": "2026-05-01", "source": "the 10-Q"}],
        "tokens_by_stage": {"capture": 100000, "evidence_challenge": 20000,
                            "seats": {"advisor_bull": 50000},
                            "verdict_challenge": 30000},
        "wall_clock_minutes": 60.0,
        "models": {"seats": {"advisor_bull": "opus"},
                   "challenger": "gpt-5.6-sol"},
    }
    row.update(over)
    return row


def _obs(row_id, subj_252, bench_252=None, falsifiers=None, tripwires=None,
         triggers=None):
    subject_close = {"value": str(subj_252), "unit": "USD_per_share",
                     "as_of": "2027-01-04", "source": "the broker history"}
    benchmark_close = None
    if bench_252 is not None:
        benchmark_close = {"value": str(bench_252), "unit": "index",
                           "as_of": "2027-01-04",
                           "source": "the broker history"}
    return {
        "observation_version": "1.0.0",
        "ledger_row_id": row_id,
        "run_id": row_id,
        "horizon_observations": [
            {"trading_days": 252, "due_date": "2027-01-04",
             "subject_close": subject_close,
             "benchmark_close": benchmark_close}],
        "falsifier_observations": falsifiers or [],
        "tripwire_events": tripwires or [],
        "trigger_events": triggers or [],
    }


def _fired_trigger(date="2026-06-01", detail="results"):
    return {"detail": detail, "fired": True, "date": date,
            "source": "the 8-K"}


def _verdict(run_id, version="1.4.0", published="2026-01-05T11:00:00Z"):
    """A minimal synthetic verdict that build_row turns into a valid row,
    for the back-fill batch: its own run_id and publish date, else fixed."""
    return {
        "schema_version": version,
        "run_id": run_id,
        "subject": {"kind": "single_stock", "asset_class": "equity",
                    "name": "Example Corp", "ticker": "EXMP",
                    "listing": "NASDAQ", "currency": "USD"},
        "rating": "buy",
        "mispricing": {"read": "fair", "magnitude": None, "arithmetic": None},
        "tripwires": {
            "invalidation_levels": [{"level": "80", "unit": "USD_per_share",
                                     "meaning": "invalidation"}],
            "reopening_triggers": [{"kind": "event", "detail": "results"}],
            "falsifiers": [{"statement": "s", "figure_name": "f",
                            "source": "src", "date": "2026-05-01"}]},
        "atlas_envelope": {"key_numbers": [
            {"name": "price", "value": "100", "unit": "USD_per_share",
             "as_of": "2026-01-05", "pack_fact_id": "price_last"}]},
        "provenance": {
            "pack_hash": "c" * 64,
            "ledger_row_id": run_id,
            "models_per_seat": {"advisor_bull": "opus"},
            "challenger_model_requested": "gpt-5.6-sol",
            "timestamps": {"run_started": "2026-01-05T10:00:00Z",
                           "published": published},
            "tokens": {"per_seat": {"advisor_bull": 1}, "seats_total": 1,
                       "challenger": 1},
            "prompt_bytes_total": 1}}


def known_ledger_rows():
    """Rows whose 252-day outcome is fixed by construction, one per branch
    of U7.3. price 100 and benchmark 100 throughout, so the subject close
    IS the excess in per cent."""
    return [
        _row("strong-buy-right", "strong_buy"),      # subj 115 -> +15% >=10
        _row("strong-buy-wrong", "strong_buy"),      # subj 108 -> +8%  <10
        _row("buy-right", "buy"),                     # subj 105 -> +5%  >0
        _row("buy-wrong", "buy"),                     # subj 96  -> -4%  <=0
        _row("sell-right", "sell"),                   # subj 95  -> -5%  <0
        _row("hold-right", "hold"),                   # subj 103 -> +3%  band
        _row("monitor-right", "monitor"),            # a trigger fired
        _row("monitor-wrong", "monitor"),            # no trigger
        _row("cheap-right", "hold",                   # subj 106 -> +6%
             mispricing={"read": "cheap", "magnitude": "a little cheap"}),
        _row("crypto-abs", "strong_buy", asset_class="crypto",
             benchmark=None,
             subject={"kind": "bitcoin", "name": "Bitcoin", "ticker": None,
                      "listing": None, "currency": "USD"}),  # subj 130 -> +30
    ]


def known_observations():
    return [
        _obs("strong-buy-right", 115, 100),
        _obs("strong-buy-wrong", 108, 100),
        _obs("buy-right", 105, 100),
        _obs("buy-wrong", 96, 100),
        _obs("sell-right", 95, 100),
        _obs("hold-right", 103, 100),
        _obs("monitor-right", 100, 100, triggers=[_fired_trigger()]),
        _obs("monitor-wrong", 100, 100, triggers=[]),
        _obs("cheap-right", 106, 100,
             falsifiers=[{"figure_name": "cash flow", "published_value": "5",
                          "unit": "USD", "date": "2026-05-01",
                          "source": "10-Q", "resolved": "for"},
                         {"figure_name": "revenue", "published_value": "9",
                          "unit": "USD", "date": "2026-05-01",
                          "source": "10-Q", "resolved": "against"},
                         {"figure_name": "margin", "published_value": None,
                          "unit": None, "date": "2026-05-01",
                          "source": "10-Q", "resolved": "unresolved"}],
             tripwires=[{"detail": "price broke the level", "level": "80",
                         "unit": "USD_per_share", "fired": True,
                         "date": "2026-03-01", "source": "the tape"}]),
        _obs("crypto-abs", 130),
    ]


def _write_ledger(path, rows):
    for row in rows:
        canonical.append_jsonl(path, row)


def _write_run_record(runs_root, run_id, events):
    """A run archive under the runs root, for the reader gate that drops a
    row whose run did not finish (U7.1 / owner rulings M5, O1)."""
    run_dir = os.path.join(runs_root, run_id)
    os.makedirs(run_dir, exist_ok=True)
    for event in events:
        canonical.append_jsonl(os.path.join(run_dir, "runrecord.jsonl"), event)


def _scored_by_id(scored):
    return {r["ledger_row_id"]: r for r in scored["rows"]}


class LedgerTempCase(unittest.TestCase):
    """Every ledger the suite writes lives in its own temp base and never
    touches the repo ledger."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name
        self.ledger_path = os.path.join(self.base, "ledger.jsonl")
        self.runs_root = os.path.join(self.base, "runs")
        self._env = {name: os.environ.get(name)
                     for name in ("COUNCIL_LEDGER_PATH", "COUNCIL_RUNS_PATH")}
        os.environ["COUNCIL_LEDGER_PATH"] = self.ledger_path
        os.environ["COUNCIL_RUNS_PATH"] = self.runs_root

    def tearDown(self):
        for name, prev in self._env.items():
            if prev is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = prev
        self._tmp.cleanup()


class TestSchemasAndRulesAreData(unittest.TestCase):
    def test_the_two_new_schemas_parse_and_are_enforceable(self):
        for name in ("ledger_row.json", "observation_schema.json"):
            with open(os.path.join(SCHEMA_DIR, name), "rb") as handle:
                schema = json.loads(handle.read().decode("utf-8"))
            validate.check_schema(schema)  # raises on an unsupported keyword

    def test_scoring_rules_carry_the_ac7_defaults(self):
        self.assertEqual(RULES["horizons_trading_days"], [63, 126, 252])
        self.assertEqual(RULES["scoring_horizon_trading_days"], 252)
        self.assertEqual(RULES["correlation_min_rows"], 20)
        self.assertEqual(RULES["rating_rules"]["strong_buy"]["threshold_pct"],
                         10.0)
        # benchmark by asset class (U4.2): equity keyed to SPY, the
        # earnings-free classes scored on their own return.
        self.assertEqual(RULES["benchmarks"]["equity"]["ticker"], "SPY")
        self.assertIsNone(RULES["benchmarks"]["crypto"])
        self.assertIsNone(RULES["benchmarks"]["gold"])
        self.assertIsNone(RULES["benchmarks"]["commodity"])


class TestRowBuilder(LedgerTempCase):
    def _verdict(self):
        return {
            "schema_version": "1.4.0",
            "run_id": "council-demo-2026-01-05",
            "subject": {"kind": "single_stock", "asset_class": "equity",
                        "name": "Example Corp", "ticker": "EXMP",
                        "listing": "NASDAQ", "currency": "USD"},
            "rating": "buy",
            "mispricing": {"read": "cheap", "magnitude": "a fifth cheap",
                           "arithmetic": None},
            "scenario_rating": None,
            "tripwires": {
                "invalidation_levels": [
                    {"level": "80", "unit": "USD_per_share",
                     "meaning": "invalidation"}],
                "reopening_triggers": [
                    {"kind": "price", "detail": "back above", "level": "120",
                     "unit": "USD_per_share", "date": None}],
                "falsifiers": [
                    {"statement": "cash flow falls", "figure_name": "FCF",
                     "source": "the 10-Q", "date": "2026-05-01"}]},
            "atlas_envelope": {"key_numbers": [
                {"name": "price at the sitting", "value": "100",
                 "unit": "USD_per_share", "as_of": "2026-01-05",
                 "pack_fact_id": "price_last", "bound": None},
                {"name": "the benchmark", "value": "6000", "unit": "index",
                 "as_of": "2026-01-05",
                 "pack_fact_id": "benchmark_level_at_sitting",
                 "bound": None}]},
            "provenance": {
                "pack_hash": "a" * 64,
                "ledger_row_id": "council-demo-2026-01-05",
                "models_per_seat": {"advisor_bull": "opus"},
                "challenger_model_requested": "gpt-5.6-sol",
                "timestamps": {"run_started": "2026-01-05T10:00:00Z",
                               "published": "2026-01-05T11:30:00Z"},
                "tokens": {"per_seat": {"advisor_bull": 50000},
                           "seats_total": 50000, "challenger": 30000},
                "prompt_bytes_total": 1000,
                "evidence": {"mode": "unattended", "chosen_by": "atlas",
                             "chosen_at": "2026-01-05T09:00:00Z",
                             "approved_by": None, "approved_at": None,
                             "approval_note": None,
                             "clock_started": "2026-01-05T10:00:00Z",
                             "capture": {"tokens": 100000, "minutes": 30.0,
                                         "model": "opus",
                                         "evidence_challenge_tokens": 20000,
                                         "evidence_challenge_prompt_bytes":
                                             500}}}}

    def test_a_row_is_built_and_validates(self):
        row = ledger.build_row(self._verdict(), RULES)
        errors = validate.validate(row, ledger._schema())
        self.assertEqual(errors, [])
        self.assertEqual(row["ledger_row_id"], "council-demo-2026-01-05")
        self.assertEqual(row["rating"], "buy")
        self.assertEqual(row["verdict_date"], "2026-01-05")
        self.assertEqual(row["price_at_verdict"],
                         {"value": "100", "unit": "USD_per_share",
                          "fact_id": "price_last"})
        self.assertEqual(row["benchmark"]["ticker"], "SPY")
        self.assertEqual(row["benchmark"]["level_at_verdict"], "6000")
        self.assertEqual(row["tokens_by_stage"]["capture"], 100000)
        self.assertEqual(row["tokens_by_stage"]["evidence_challenge"], 20000)
        self.assertEqual(row["tokens_by_stage"]["verdict_challenge"], 30000)
        self.assertEqual(row["wall_clock_minutes"], 90.0)
        self.assertEqual([h["trading_days"] for h in row["horizons"]],
                         [63, 126, 252])

    def test_horizon_due_dates_count_business_days(self):
        # ten business days after Monday 5 Jan 2026 is Monday 19 Jan 2026.
        import datetime
        got = ledger.add_trading_days(datetime.date(2026, 1, 5), 10)
        self.assertEqual(got.isoformat(), "2026-01-19")

    def test_the_anchorless_price_comes_from_the_scenario_reference(self):
        verdict = self._verdict()
        verdict["subject"]["asset_class"] = "crypto"
        verdict["scenario_rating"] = {"reference_price": 77313.49,
                                      "reference_price_fact_id": "price_last"}
        row = ledger.build_row(verdict, RULES)
        self.assertEqual(row["price_at_verdict"]["value"], "77313.49")
        self.assertEqual(row["price_at_verdict"]["fact_id"], "price_last")
        self.assertIsNone(row["benchmark"])  # crypto is scored absolute


class TestReadsEverySchemaVersion(unittest.TestCase):
    def _minimal(self, version):
        return {
            "schema_version": version,
            "run_id": "council-v-" + version.replace(".", "-"),
            "subject": {"kind": "single_stock", "asset_class": None,
                        "name": "Legacy Co", "ticker": "LGCY",
                        "listing": "NASDAQ", "currency": "USD"},
            "rating": "hold",
            "mispricing": {"read": "fair", "magnitude": None,
                           "arithmetic": None},
            "tripwires": {
                "invalidation_levels": [{"level": "1", "unit": "x",
                                         "meaning": "m"}],
                "reopening_triggers": [{"kind": "event", "detail": "d"}],
                "falsifiers": [{"statement": "s", "figure_name": "f",
                                "source": "src", "date": "2026-05-01"}]},
            "atlas_envelope": {"key_numbers": [
                {"name": "price", "value": "10", "unit": "USD_per_share",
                 "as_of": "2026-01-05", "pack_fact_id": "price_last"}]},
            "provenance": {
                "pack_hash": "b" * 64,
                "models_per_seat": {"advisor_bull": "opus"},
                "challenger_model_requested": "gpt-5.6-sol",
                "timestamps": {"run_started": "2026-01-05T10:00:00Z",
                               "published": "2026-01-05T11:00:00Z"},
                "tokens": {"per_seat": {"advisor_bull": 1},
                           "seats_total": 1, "challenger": 1},
                "prompt_bytes_total": 1}}

    def test_every_version_builds_a_valid_row(self):
        for version in ("1.0.0", "1.1.0", "1.2.0", "1.3.1", "1.4.0"):
            row = ledger.build_row(self._minimal(version), RULES)
            self.assertEqual(validate.validate(row, ledger._schema()), [],
                             version)
            # pre-1.3.1 carried no capture stage: those come through null,
            # not as a crash.
            self.assertIsNone(row["tokens_by_stage"]["capture"])
            self.assertEqual(row["verdict_schema_version"], version)


def _real_verdicts():
    root = os.path.join(ROOT, "council", "runs")
    if not os.path.isdir(root):
        return []
    found = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, "verdict.json")
        if os.path.exists(path):
            found.append(path)
    return found


@unittest.skipUnless(_real_verdicts(),
                     "no run records in this checkout (the public copy)")
class TestTheBackFillReadsRealVerdicts(unittest.TestCase):
    """The row builder reads every verdict on record - 1.0.0 through 1.3.1
    - without touching council/runs (the back-fill proper is an
    owner-launched session)."""

    def test_each_real_verdict_builds_a_valid_row(self):
        versions = set()
        for path in _real_verdicts():
            verdict = canonical.read_json(path)
            row = ledger.build_row(verdict, RULES)
            self.assertEqual(validate.validate(row, ledger._schema()), [],
                             os.path.basename(os.path.dirname(path)))
            versions.add(verdict["schema_version"])
        for expected in ("1.0.0", "1.1.0", "1.2.0", "1.3.1"):
            self.assertIn(expected, versions)


class TestAppendAndPriorLink(LedgerTempCase):
    def test_append_validates_and_hashes_stably(self):
        row = _row("first", "buy")
        row_hash, written = ledger.append_row(row, self.ledger_path)
        self.assertEqual(row_hash, ledger.row_hash(written))
        rows = ledger.read_rows(self.ledger_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ledger_row_id"], "first")

    def test_a_resit_links_the_prior_row_for_the_same_subject(self):
        ledger.append_row(_row("first", "buy"), self.ledger_path)
        _, second = ledger.append_row(_row("second", "hold"),
                                      self.ledger_path)
        self.assertEqual(second["prior_ledger_row_id"], "first")

    def test_a_different_subject_does_not_link(self):
        ledger.append_row(_row("first", "buy"), self.ledger_path)
        other = _row("other", "buy",
                     subject={"kind": "single_stock", "name": "Other Inc",
                              "ticker": "OTHR", "listing": "NYSE",
                              "currency": "USD"})
        _, written = ledger.append_row(other, self.ledger_path)
        self.assertIsNone(written["prior_ledger_row_id"])

    def test_an_invalid_row_is_refused(self):
        bad = _row("bad", "buy")
        bad["rating"] = "wonderful"  # not one of the five words
        with self.assertRaises(ValueError):
            ledger.append_row(bad, self.ledger_path)

    def test_a_duplicate_row_id_is_refused_and_not_written(self):
        # A re-run of a publish (or of the back-fill) must not write a
        # second row for one verdict and double-count it (envelope item 5).
        ledger.append_row(_row("dup", "buy"), self.ledger_path)
        with self.assertRaises(ledger.DuplicateLedgerRow):
            ledger.append_row(_row("dup", "hold"), self.ledger_path)
        rows = ledger.read_rows(self.ledger_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rating"], "buy")


class TestBackFillIsIdempotent(LedgerTempCase):
    """The back-fill of past verdicts runs through the same build_row and
    append_row the publisher uses; re-run over a partly-filled ledger it
    skips the rows already on file and reports them, never double-counting
    or failing the batch (envelope item 5)."""

    def test_back_fill_appends_then_skips_and_reports_on_a_re_run(self):
        verdicts = [_verdict("bf-1"), _verdict("bf-2")]
        appended, skipped = ledger.back_fill(verdicts, self.ledger_path)
        self.assertEqual(appended, ["bf-1", "bf-2"])
        self.assertEqual(skipped, [])
        appended2, skipped2 = ledger.back_fill(verdicts, self.ledger_path)
        self.assertEqual(appended2, [])
        self.assertEqual(skipped2, ["bf-1", "bf-2"])
        self.assertEqual(len(ledger.read_rows(self.ledger_path)), 2)


class TestRound2AuditFixes(LedgerTempCase):
    """UPGRADE-2 U7 audit round 2 findings, each proven to FAIL against the
    pre-fix code (r2-2 unit, r2-3 unreadable record, r2-4 event date, r2-5
    back-fill order)."""

    def test_a_unitless_observed_close_against_a_known_baseline_is_incomplete(
            self):
        # r2-2: baseline 100 USD_per_share vs observed 12000 with NO unit is
        # not a real +11,900% return; it is INCOMPLETE, not scored.
        row = _row("u", "buy")
        horizon_obs = {"trading_days": 252, "due_date": "2027-01-04",
                       "subject_close": {"value": "12000", "unit": None,
                                         "as_of": "2027-01-04", "source": "s"},
                       "benchmark_close": {"value": "100", "unit": "index",
                                           "as_of": "2027-01-04",
                                           "source": "s"}}
        display, exact = score._score_horizon(row, horizon_obs)
        self.assertEqual(display["basis"], "incomplete")
        self.assertIsNone(display["subject_return_pct"])
        self.assertIsNone(exact)

    def test_a_present_but_unreadable_run_record_is_not_counted(self):
        # r2-3: a run record left as a partial JSON line by a crash mid-append
        # cannot be confirmed finished, so its row is dropped, not counted.
        ledger.append_row(_row("crashy", "buy"), self.ledger_path)
        run_dir = os.path.join(self.runs_root, "crashy")
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "runrecord.jsonl"), "w",
                  encoding="utf-8") as handle:
            handle.write('{"event":"run_started","state":"OPEN"}\n')
            handle.write('{"event":"ledger_row_appended", "row_hash"')
        rows = ledger.read_rows(self.ledger_path)
        confirmed = ledger.confirmed_rows(rows, self.runs_root)
        self.assertEqual([r["ledger_row_id"] for r in confirmed], [])

    def test_a_malformed_trigger_date_does_not_credit_a_monitor(self):
        # r2-4: 0000-00-00 is not a real date and must not count as fired
        # within the window; a valid date still does.
        self.assertEqual(
            score._fired_within([{"detail": "x", "fired": True,
                                  "date": "0000-00-00", "source": "s"}],
                                "2027-01-04"), [])
        self.assertEqual(
            [e["date"] for e in score._fired_within(
                [{"detail": "x", "fired": True, "date": "2026-06-01",
                  "source": "s"}], "2027-01-04")],
            ["2026-06-01"])

    def test_back_fill_orders_the_resit_chain_by_verdict_date(self):
        # r2-5: given the same subject newest-first, the re-sit chain must
        # still link the newer row to the older, never the reverse (U7.5).
        v_old = _verdict("resit-old", published="2026-01-05T11:00:00Z")
        v_new = _verdict("resit-new", published="2026-06-05T11:00:00Z")
        ledger.back_fill([v_new, v_old], self.ledger_path)
        by_id = {r["ledger_row_id"]: r
                 for r in ledger.read_rows(self.ledger_path)}
        self.assertEqual(by_id["resit-new"]["prior_ledger_row_id"],
                         "resit-old")
        self.assertIsNone(by_id["resit-old"]["prior_ledger_row_id"])


class TestRound3AuditFixes(LedgerTempCase):
    def test_back_fill_orders_same_day_resits_by_publication_time(self):
        # r3-1: two sittings of one subject on the SAME day; the chain must
        # link the later time to the earlier, never the reverse, though
        # verdict_date is the same YYYY-MM-DD for both (U7.5).
        v_early = _verdict("resit-am", published="2026-01-05T09:00:00Z")
        v_late = _verdict("resit-pm", published="2026-01-05T15:00:00Z")
        ledger.back_fill([v_late, v_early], self.ledger_path)
        by_id = {r["ledger_row_id"]: r
                 for r in ledger.read_rows(self.ledger_path)}
        self.assertEqual(by_id["resit-pm"]["prior_ledger_row_id"], "resit-am")
        self.assertIsNone(by_id["resit-am"]["prior_ledger_row_id"])

    def test_back_filling_before_an_existing_later_resit_is_refused(self):
        # r3-2: a later sitting (June) is already on file; back-filling its
        # January predecessor afterwards would link January -> June and
        # reverse the chain, so it is refused loudly, not written wrong (U7.5).
        v_jan = _verdict("resit-jan", published="2026-01-05T11:00:00Z")
        v_june = _verdict("resit-june", published="2026-06-05T11:00:00Z")
        ledger.back_fill([v_june], self.ledger_path)
        with self.assertRaises(ledger.LedgerOutOfOrder):
            ledger.back_fill([v_jan, v_june], self.ledger_path)
        rows = ledger.read_rows(self.ledger_path)
        self.assertEqual([r["ledger_row_id"] for r in rows], ["resit-june"])


class TestRound4AuditFixes(LedgerTempCase):
    def test_back_filling_an_earlier_same_day_sitting_after_a_later_one_is_refused(
            self):
        # r4-1: a later-TIME sitting (15:00) of a subject is already on file;
        # back-filling its earlier-TIME predecessor from the SAME day (09:00)
        # afterwards would link 09:00 -> 15:00 and reverse the chain, so it is
        # refused loudly, not written wrong. verdict_date is the same
        # YYYY-MM-DD for both, so the day-only guard let it through before the
        # append_row guard compared the full publication time too (U7.5).
        v_am = _verdict("resit-am", published="2026-06-05T09:00:00Z")
        v_pm = _verdict("resit-pm", published="2026-06-05T15:00:00Z")
        ledger.back_fill([v_pm], self.ledger_path)
        with self.assertRaises(ledger.LedgerOutOfOrder):
            ledger.back_fill([v_am, v_pm], self.ledger_path)
        rows = ledger.read_rows(self.ledger_path)
        self.assertEqual([r["ledger_row_id"] for r in rows], ["resit-pm"])


class TestRound5AuditFixes(LedgerTempCase):
    def test_back_filling_a_timestamped_sitting_after_a_same_day_legacy_row_is_refused(
            self):
        # r5-1: a same-subject row already on file predates the published_at
        # field, so it carries no intra-day time; its order key falls back to
        # (day, ""), which sorts before EVERY timestamped row of that day.
        # Back-filling a 09:00 sitting after it must NOT quietly succeed and
        # link 09:00 -> the legacy row: the legacy row's true time is unknown,
        # so the same-day order is ambiguous and the append is refused loudly
        # rather than written with a possibly-reversed re-sit chain (U7.5).
        # Proven to FAIL against the round-4 code, where the empty-string
        # fallback made the legacy row sort earliest and let the reversed
        # link through.
        legacy = _row("resit-legacy", "buy")     # a row written before the
        legacy.pop("published_at", None)          # published_at field existed
        _write_ledger(self.ledger_path, [legacy])
        v_am = _verdict("resit-am", published="2026-01-05T09:00:00Z")
        with self.assertRaises(ledger.LedgerOutOfOrder):
            ledger.append_row(ledger.build_row(v_am, RULES), self.ledger_path)
        rows = ledger.read_rows(self.ledger_path)
        self.assertEqual([r["ledger_row_id"] for r in rows], ["resit-legacy"])

    def test_two_same_day_rows_that_both_predate_the_field_still_append(self):
        # r5-1 sibling: the ambiguity refusal is narrow. When BOTH the row on
        # file and the row being appended predate published_at (no intra-day
        # time on either), the order stays at the accepted day-granularity
        # fallback and the append still links by file order - it is NOT
        # refused. Guards the round-4 behaviour the fix must leave intact.
        first = _row("legacy-first", "buy")
        first.pop("published_at", None)
        second = _row("legacy-second", "hold")
        second.pop("published_at", None)
        ledger.append_row(first, self.ledger_path)
        _, written = ledger.append_row(second, self.ledger_path)
        self.assertEqual(written["prior_ledger_row_id"], "legacy-first")


class TestPublishWritesLedgerRowAndReadBackVerifiesIt(test_engine.EngineTest):
    """Drives a real publish through the host and proves the row was
    written and read-back verifies it. FAILS against the pre-U7 publisher
    and read-back, which wrote no row and checked none."""

    def _ledger_path(self):
        return os.environ["COUNCIL_LEDGER_PATH"]

    def test_publish_appends_one_row_hashing_to_the_recorded_value(self):
        run = self.harness(run_id="ledger-run")
        run.drive()
        events = runrecord.read_events(run.run_dir)
        appended = [e for e in events if e["event"] == "ledger_row_appended"]
        self.assertEqual(len(appended), 1)
        rows = canonical.read_jsonl(self._ledger_path())
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            canonical.sha256_bytes(canonical.canonical_bytes(rows[0])),
            appended[-1]["row_hash"])
        self.assertEqual(rows[0]["ledger_row_id"], "ledger-run")
        verdict = run.verdict()
        self.assertEqual(verdict["provenance"]["ledger_row_id"], "ledger-run")
        self.assertEqual(test_engine.quiet_readback(run.run_dir), 0)

    def test_read_back_catches_a_tampered_ledger_row(self):
        run = self.harness(run_id="tamper-run")
        run.drive()
        self.assertEqual(test_engine.quiet_readback(run.run_dir), 0)
        rows = canonical.read_jsonl(self._ledger_path())
        rows[0]["rating"] = "strong_buy"  # rewrite the record after the fact
        with open(self._ledger_path(), "wb") as handle:
            for row in rows:
                handle.write(canonical.canonical_bytes(row))
        self.assertNotEqual(test_engine.quiet_readback(run.run_dir), 0)

    def test_read_back_catches_a_missing_ledger_file(self):
        run = self.harness(run_id="missing-run")
        run.drive()
        os.remove(self._ledger_path())
        self.assertNotEqual(test_engine.quiet_readback(run.run_dir), 0)


class TestScoring(LedgerTempCase):
    def _score(self):
        _write_ledger(self.ledger_path, known_ledger_rows())
        obs_path = os.path.join(self.base, "observations.json")
        canonical.write_canonical_json(obs_path, known_observations())
        return score.score(self.ledger_path, obs_path, RULES)

    def test_each_rating_word_is_scored_by_its_rule(self):
        by_id = _scored_by_id(self._score())

        def correct(row_id):
            return by_id[row_id]["rating_outcome"]["correct"]

        self.assertIs(correct("strong-buy-right"), True)
        self.assertIs(correct("strong-buy-wrong"), False)
        self.assertIs(correct("buy-right"), True)
        self.assertIs(correct("buy-wrong"), False)
        self.assertIs(correct("sell-right"), True)
        self.assertIs(correct("hold-right"), True)
        self.assertIs(correct("monitor-right"), True)
        self.assertIs(correct("monitor-wrong"), False)

    def test_excess_is_subject_minus_benchmark_and_absolute_with_no_bench(
            self):
        by_id = _scored_by_id(self._score())
        # equity: subject +15%, benchmark 0% -> excess +15%
        h = [x for x in by_id["strong-buy-right"]["horizons"]
             if x["trading_days"] == 252][0]
        self.assertEqual(h["basis"], "excess")
        self.assertAlmostEqual(h["excess_pct"], 15.0, places=6)
        # crypto: no benchmark -> absolute +30%
        c = [x for x in by_id["crypto-abs"]["horizons"]
             if x["trading_days"] == 252][0]
        self.assertEqual(c["basis"], "absolute")
        self.assertAlmostEqual(c["excess_pct"], 30.0, places=6)

    def test_mispricing_direction_and_falsifiers_and_tripwires(self):
        by_id = _scored_by_id(self._score())
        cheap = by_id["cheap-right"]
        self.assertIs(cheap["mispricing"]["correct"], True)  # cheap, +6%
        self.assertEqual(cheap["falsifiers"],
                         {"for": 1, "against": 1, "unresolved": 1})
        self.assertEqual(len(cheap["tripwires_fired"]), 1)

    def test_the_scoring_threshold_is_read_from_data_not_code(self):
        # Move strong_buy's bar to +20%; the +15% row now reads WRONG.
        rules = copy.deepcopy(RULES)
        rules["rating_rules"]["strong_buy"]["threshold_pct"] = 20.0
        _write_ledger(self.ledger_path, [_row("sbr", "strong_buy")])
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [_obs("sbr", 115, 100)])
        by_id = _scored_by_id(score.score(self.ledger_path, obs_path, rules))
        self.assertIs(by_id["sbr"]["rating_outcome"]["correct"], False)

    def test_the_committed_fixtures_match_the_builders(self):
        # The fixture files on disk are the invented set, so the audit can
        # read them; the builders and the files must not drift.
        fixture_rows = ledger.read_rows(os.path.join(FIX, "ledger.jsonl"))
        self.assertEqual(fixture_rows, known_ledger_rows())
        with open(os.path.join(FIX, "observations.json"), "rb") as handle:
            fixture_obs = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(fixture_obs, known_observations())


class TestScorerRefusesABadObservation(LedgerTempCase):
    def test_an_observation_with_a_bad_resolution_is_refused(self):
        _write_ledger(self.ledger_path, [_row("r", "buy")])
        bad = _obs("r", 105, 100)
        bad["falsifier_observations"] = [
            {"figure_name": "x", "published_value": "1", "unit": None,
             "date": "2026-05-01", "source": "s", "resolved": "maybe"}]
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [bad])
        with self.assertRaises(ValueError):
            score.score(self.ledger_path, obs_path, RULES)

    def test_the_cli_refuses_and_exits_nonzero(self):
        _write_ledger(self.ledger_path, [_row("r", "buy")])
        bad = _obs("r", 105, 100)
        bad["observation_version"] = "9.9.9"
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [bad])
        proc = _cli("council.ledger.score", self.ledger_path, obs_path)
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("REFUSED", proc.stdout + proc.stderr)


class TestObservationGate(LedgerTempCase):
    """The observation file is captured by a session and is UNTRUSTED; the
    scorer refuses one that is not bound to exactly one ledger row, dates a
    horizon wrongly, and does not compute a return across incompatible
    units (U7.2 'the gate validates it')."""

    def _score(self, rows, observations):
        _write_ledger(self.ledger_path, rows)
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, observations)
        return score.score(self.ledger_path, obs_path, RULES)

    def test_an_observation_for_an_unknown_ledger_row_is_refused(self):
        with self.assertRaises(ValueError):
            self._score([_row("r", "buy")], [_obs("nope", 105, 100)])

    def test_two_observations_for_one_row_are_refused(self):
        with self.assertRaises(ValueError):
            self._score([_row("r", "buy")],
                        [_obs("r", 105, 100), _obs("r", 106, 100)])

    def test_an_observation_with_a_mismatched_run_id_is_refused(self):
        obs = _obs("r", 105, 100)
        obs["run_id"] = "some-other-run"
        with self.assertRaises(ValueError):
            self._score([_row("r", "buy")], [obs])

    def test_a_horizon_observation_with_the_wrong_due_date_is_refused(self):
        obs = _obs("r", 105, 100)
        obs["horizon_observations"][0]["due_date"] = "2099-01-01"
        with self.assertRaises(ValueError):
            self._score([_row("r", "buy")], [obs])

    def test_a_unit_mismatch_is_not_scored_as_a_return(self):
        obs = _obs("r", 12000, 100)
        obs["horizon_observations"][0]["subject_close"]["unit"] = \
            "cents_per_share"
        by_id = _scored_by_id(self._score([_row("r", "buy")], [obs]))
        h = [x for x in by_id["r"]["horizons"]
             if x["trading_days"] == 252][0]
        self.assertEqual(h["basis"], "incomplete")
        self.assertIsNone(h["excess_pct"])

    def test_a_close_observed_long_after_the_due_date_is_refused(self):
        """A hindsight close - observed months after the horizon's due date -
        is not the close ON the horizon; the gate refuses it rather than
        scoring hindsight as today's outcome (P-U7-7)."""
        obs = _obs("r", 115, 100)
        obs["horizon_observations"][0]["subject_close"]["as_of"] = "2027-06-01"
        with self.assertRaises(ValueError):
            self._score([_row("r", "buy")], [obs])

    def test_a_hindsight_benchmark_close_is_refused(self):
        """The window guards every close that scores the horizon: a benchmark
        close struck long after the due date is refused too (P-U7-7)."""
        obs = _obs("r", 115, 100)
        obs["horizon_observations"][0]["benchmark_close"]["as_of"] = \
            "2027-06-01"
        with self.assertRaises(ValueError):
            self._score([_row("r", "buy")], [obs])

    def test_a_close_observed_before_the_due_date_is_refused(self):
        """close_days_before_due_allowed is 0: a close struck before the
        horizon came due is not that horizon's outcome, so it is refused."""
        obs = _obs("r", 115, 100)
        obs["horizon_observations"][0]["subject_close"]["as_of"] = "2026-12-31"
        with self.assertRaises(ValueError):
            self._score([_row("r", "buy")], [obs])

    def test_a_close_within_the_window_after_the_due_date_is_scored(self):
        """The window runs to close_window_days_after_due (5) calendar days,
        so a close a few sessions late - a due date that fell on a weekend or
        holiday - still scores the horizon."""
        obs = _obs("r", 115, 100)
        for close in ("subject_close", "benchmark_close"):
            obs["horizon_observations"][0][close]["as_of"] = "2027-01-09"
        by_id = _scored_by_id(self._score([_row("r", "buy")], [obs]))
        h = [x for x in by_id["r"]["horizons"]
             if x["trading_days"] == 252][0]
        self.assertEqual(h["basis"], "excess")

    def test_subject_and_benchmark_closes_of_one_horizon_share_a_session(self):
        """An excess return is one window: the subject close and the benchmark
        close that score a horizon must be struck on the SAME session (one
        as-of date). Two closes on different sessions - even both inside the
        window after the due date - mix sessions and distort, up to reversing,
        the excess, so the gate refuses the pair naming the row, the horizon
        and both dates (P-U7-8)."""
        obs = _obs("r", 115, 100)
        obs["horizon_observations"][0]["subject_close"]["as_of"] = "2027-01-04"
        obs["horizon_observations"][0]["benchmark_close"]["as_of"] = \
            "2027-01-06"
        with self.assertRaises(ValueError) as caught:
            self._score([_row("r", "buy")], [obs])
        message = str(caught.exception)
        self.assertIn("'r'", message)
        self.assertIn("252", message)
        self.assertIn("2027-01-04", message)
        self.assertIn("2027-01-06", message)


class TestMonitorScoring(LedgerTempCase):
    """A monitor is scored only once its 252-day window has resolved, and
    only a NAMED reopening trigger fired within the window credits it
    (AC7, U7.3)."""

    def _score_one(self, row, obs):
        _write_ledger(self.ledger_path, [row])
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [obs])
        scored = score.score(self.ledger_path, obs_path, RULES)
        return _scored_by_id(scored)[row["ledger_row_id"]]["rating_outcome"]

    def test_a_monitor_with_only_an_interim_observation_is_pending(self):
        row = _row("mon-pending", "monitor")
        obs = _obs("mon-pending", 100, 100)
        obs["horizon_observations"][0]["trading_days"] = 63
        obs["horizon_observations"][0]["due_date"] = "2026-04-06"
        for close in ("subject_close", "benchmark_close"):
            obs["horizon_observations"][0][close]["as_of"] = "2026-04-06"
        outcome = self._score_one(row, obs)
        self.assertIs(outcome["has_252_outcome"], False)
        self.assertIsNone(outcome["correct"])

    def test_a_monitor_is_credited_only_by_a_named_trigger(self):
        row = _row("mon-named", "monitor")
        obs = _obs("mon-named", 100, 100,
                   triggers=[_fired_trigger(detail="weather")])
        self.assertIs(self._score_one(row, obs)["correct"], False)

    def test_an_undated_fired_trigger_does_not_credit_a_monitor(self):
        row = _row("mon-undated", "monitor")
        obs = _obs("mon-undated", 100, 100,
                   triggers=[_fired_trigger(date=None, detail="results")])
        self.assertIs(self._score_one(row, obs)["correct"], False)


class TestOrphanRowsAreNotCounted(LedgerTempCase):
    """A run that crashed after appending its ledger row but before it
    published is discarded whole (owner rulings M5, O1: a run has published
    only if it also finished). The append-only row it left behind must NOT
    be scored or shown as a published verdict (U7.1: one row PER PUBLISHED
    verdict). Rows whose run archive is absent - the invented fixtures - are
    kept."""

    def _scored_ids(self):
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [])
        return {r["ledger_row_id"]
                for r in score.score(self.ledger_path, obs_path,
                                     RULES)["rows"]}

    def test_a_crashed_runs_orphan_row_is_not_scored_or_shown(self):
        _write_ledger(self.ledger_path,
                      [_row("good-run", "buy"), _row("orphan-run", "buy")])
        _write_run_record(self.runs_root, "good-run", [
            {"event": "publish_authorized"},
            {"event": "run_finished", "state": "DONE"}])
        _write_run_record(self.runs_root, "orphan-run", [
            {"event": "publish_authorized"},
            {"event": "ledger_row_appended"},
            {"event": "run_failed", "reason": "interrupted"}])
        ids = self._scored_ids()
        self.assertIn("good-run", ids)
        self.assertNotIn("orphan-run", ids)
        page = ledger_report.build_page(self.ledger_path, None, RULES)
        self.assertIn("<div class='n'>1</div>"
                      "<div class='l'>verdicts on record</div>", page)


class TestScorecard(LedgerTempCase):
    def _render(self, rows, observations):
        _write_ledger(self.ledger_path, rows)
        obs_path = os.path.join(self.base, "observations.json")
        canonical.write_canonical_json(obs_path, observations)
        scored = score.score(self.ledger_path, obs_path, RULES)
        scored_path = os.path.join(self.base, "scored.json")
        canonical.write_canonical_json(scored_path, scored)
        return ledger_report.build_page(self.ledger_path, scored_path, RULES)

    def test_below_twenty_the_correlation_is_refused_with_the_count(self):
        page = self._render(known_ledger_rows(), known_observations())
        self.assertIn("refused below 20 scored rows", page)
        self.assertIn("Hit rate by rating word", page)
        self.assertIn("Mean excess by horizon", page)

    def test_at_twenty_the_correlation_and_caveat_show(self):
        rows, observations = [], []
        for index in range(22):
            row_id = "row-%02d" % index
            rows.append(_row(row_id, "buy"))
            observations.append(_obs(row_id, 100 + index, 100))
        page = self._render(rows, observations)
        self.assertNotIn("refused below", page)
        self.assertIn("n is small; this is a record, not a proof", page)
        self.assertIn("Correlation of tokens against", page)

    def test_the_page_is_self_contained_and_offline(self):
        page = self._render(known_ledger_rows(), known_observations())
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)
        self.assertNotIn("<script src", page)
        self.assertGreater(len(page), 3000)

    def test_the_cli_writes_a_scorecard_file(self):
        _write_ledger(self.ledger_path, known_ledger_rows())
        obs_path = os.path.join(self.base, "observations.json")
        canonical.write_canonical_json(obs_path, known_observations())
        self.assertEqual(_cli("council.ledger.score", self.ledger_path,
                              obs_path).returncode, 0)
        proc = _cli("council.ledger.report")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(os.path.exists(
            os.path.join(self.base, "scorecard.html")))

    def test_a_verdict_published_after_scoring_still_appears(self):
        rows = known_ledger_rows()
        _write_ledger(self.ledger_path, rows)
        obs_path = os.path.join(self.base, "observations.json")
        canonical.write_canonical_json(obs_path, known_observations())
        scored = score.score(self.ledger_path, obs_path, RULES)
        scored_path = os.path.join(self.base, "scored.json")
        canonical.write_canonical_json(scored_path, scored)
        # A verdict published AFTER the last scoring run: the page must still
        # count it and show it (pending), or it silently claims to show every
        # published verdict while omitting one.
        canonical.append_jsonl(self.ledger_path, _row(
            "published-later", "buy",
            subject={"kind": "single_stock", "name": "Later Corp",
                     "ticker": "LATR", "listing": "NASDAQ",
                     "currency": "USD"}))
        page = ledger_report.build_page(self.ledger_path, scored_path, RULES)
        self.assertIn("<div class='n'>%d</div>"
                      "<div class='l'>verdicts on record</div>"
                      % (len(rows) + 1), page)
        self.assertIn("Later Corp", page)


class TestRound7AuditFixes(LedgerTempCase):
    """Round 7 (the closing full pass) findings. Every new-behaviour test was
    proven to FAIL against the pre-fix code before its fix was written."""

    def _anchorless_verdict(self):
        """A published anchorless (crypto) verdict: the scenario ladder writes
        reference_price as the VALUE of reference_price_fact_id, whose unit
        lives on the matching atlas_envelope key number."""
        return {
            "schema_version": "1.4.0", "run_id": "btc-2026-01-05",
            "subject": {"kind": "bitcoin", "asset_class": "crypto",
                        "name": "Bitcoin", "ticker": None, "listing": None,
                        "currency": "USD"},
            "rating": "strong_buy",
            "mispricing": {"read": "no_view", "magnitude": None,
                           "arithmetic": None},
            "scenario_rating": {"reference_price": 77313.49,
                                "reference_price_fact_id": "price_last"},
            "tripwires": {"invalidation_levels": [], "reopening_triggers": [],
                          "falsifiers": []},
            "atlas_envelope": {"key_numbers": [
                {"name": "price on the record", "value": "77313.49",
                 "unit": "USD", "as_of": "2026-01-05",
                 "pack_fact_id": "price_last"}]},
            "provenance": {
                "pack_hash": "c" * 64, "ledger_row_id": "btc-2026-01-05",
                "models_per_seat": {"advisor_bull": "opus"},
                "challenger_model_requested": "gpt-5.6-sol",
                "timestamps": {"run_started": "2026-01-05T10:00:00Z",
                               "published": "2026-01-05T11:00:00Z"},
                "tokens": {"per_seat": {"advisor_bull": 1}, "seats_total": 1,
                           "challenger": 1}, "prompt_bytes_total": 1}}

    def _score_one(self, row, obs):
        _write_ledger(self.ledger_path, [row])
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [obs])
        return _scored_by_id(
            score.score(self.ledger_path, obs_path, RULES))[
                row["ledger_row_id"]]

    # r7-1: the anchorless baseline dropped a recoverable unit, so a
    # unit-mismatched observed close scored as a spurious return.
    def test_r7_1_anchorless_baseline_carries_the_reference_facts_unit(self):
        row = ledger.build_row(self._anchorless_verdict(), RULES)
        self.assertEqual(row["price_at_verdict"]["unit"], "USD")

    def test_r7_1_a_unit_mismatched_anchorless_close_is_incomplete(self):
        row = ledger.build_row(self._anchorless_verdict(), RULES)
        ledger.append_row(row, self.ledger_path)
        due = [h["due_date"] for h in row["horizons"]
               if h["trading_days"] == 252][0]
        obs = _obs("btc-2026-01-05", "7731349")
        horizon_obs = obs["horizon_observations"][0]
        horizon_obs["due_date"] = due
        horizon_obs["subject_close"]["as_of"] = due
        horizon_obs["subject_close"]["unit"] = "cents"
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [obs])
        by_id = _scored_by_id(score.score(self.ledger_path, obs_path, RULES))
        h = [x for x in by_id["btc-2026-01-05"]["horizons"]
             if x["trading_days"] == 252][0]
        self.assertEqual(h["basis"], "incomplete")

    # r7-2: a fired event dated before the verdict is not within the
    # post-verdict window - the same reasoning that excludes undated ones.
    def test_r7_2_a_trigger_before_the_verdict_does_not_credit_a_monitor(self):
        row = _row("mon-early", "monitor")            # verdict_date 2026-01-05
        obs = _obs("mon-early", 100, 100,
                   triggers=[_fired_trigger(date="2025-12-01",
                                            detail="results")])
        self.assertIs(
            self._score_one(row, obs)["rating_outcome"]["correct"], False)

    def test_r7_2_a_tripwire_before_the_verdict_is_not_counted(self):
        row = _row("tw-early", "hold")
        obs = _obs("tw-early", 103, 100,
                   tripwires=[{"detail": "broke the level", "level": "80",
                               "unit": "USD_per_share", "fired": True,
                               "date": "2025-12-01", "source": "the tape"}])
        self.assertEqual(self._score_one(row, obs)["tripwires_fired"], [])

    # r7-4: a right/wrong threshold was decided on a float, which could round
    # an exact excess just below the bar up onto it.
    def test_r7_4_a_threshold_decision_uses_exact_decimal_not_float(self):
        row = _row("sb-edge", "strong_buy", asset_class="crypto",
                   benchmark=None,
                   subject={"kind": "bitcoin", "name": "Bitcoin",
                            "ticker": None, "listing": None,
                            "currency": "USD"})
        obs = _obs("sb-edge", "109.9999999999999999999999999")
        self.assertIs(
            self._score_one(row, obs)["rating_outcome"]["correct"], False)

    # r7-5: a ticker is unique only within its listing; two securities that
    # reuse one across exchanges must not share a re-sit chain.
    def test_r7_5_same_ticker_different_listing_is_not_the_same_subject(self):
        alpha = _row("alpha", "buy", verdict_date="2026-01-05",
                     subject={"kind": "single_stock", "name": "Alpha Inc",
                              "ticker": "ABC", "listing": "NYSE",
                              "currency": "USD"})
        beta = _row("beta", "buy", verdict_date="2026-02-05",
                    subject={"kind": "single_stock", "name": "Beta plc",
                             "ticker": "ABC", "listing": "LSE",
                             "currency": "GBP"})
        ledger.append_row(alpha, self.ledger_path)
        ledger.append_row(beta, self.ledger_path)
        rows = {r["ledger_row_id"]: r
                for r in ledger.read_rows(self.ledger_path)}
        self.assertIsNone(rows["beta"]["prior_ledger_row_id"])


class TestRound8AuditFixes(LedgerTempCase):
    """Round 8 (the closing incremental) findings. Each new-behaviour test was
    proven to FAIL against the pre-fix code before its fix was written."""

    def _anchorless_verdict(self):
        """A published anchorless (crypto) verdict whose scenario reference
        price is bound to reference_price_fact_id."""
        return {
            "schema_version": "1.4.0", "run_id": "btc-2026-01-05",
            "subject": {"kind": "bitcoin", "asset_class": "crypto",
                        "name": "Bitcoin", "ticker": None, "listing": None,
                        "currency": "USD"},
            "rating": "strong_buy",
            "mispricing": {"read": "no_view", "magnitude": None,
                           "arithmetic": None},
            "scenario_rating": {"reference_price": 77313.49,
                                "reference_price_fact_id": "price_last"},
            "tripwires": {"invalidation_levels": [], "reopening_triggers": [],
                          "falsifiers": []},
            "atlas_envelope": {"key_numbers": [
                {"name": "price on the record", "value": "77313.49",
                 "unit": "USD", "as_of": "2026-01-05",
                 "pack_fact_id": "price_last"}]},
            "provenance": {
                "pack_hash": "c" * 64, "ledger_row_id": "btc-2026-01-05",
                "models_per_seat": {"advisor_bull": "opus"},
                "challenger_model_requested": "gpt-5.6-sol",
                "timestamps": {"run_started": "2026-01-05T10:00:00Z",
                               "published": "2026-01-05T11:00:00Z"},
                "tokens": {"per_seat": {"advisor_bull": 1}, "seats_total": 1,
                           "challenger": 1}, "prompt_bytes_total": 1}}

    def _score_one(self, row, obs):
        _write_ledger(self.ledger_path, [row])
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [obs])
        return _scored_by_id(
            score.score(self.ledger_path, obs_path, RULES))[
                row["ledger_row_id"]]

    # r8-1: r7-1 bound the anchorless baseline unit from the reference fact,
    # but a chair may OMIT that fact from key_numbers (schema and host gate
    # permit it), leaving the baseline unit unresolved (None). A None baseline
    # unit tolerated any observed unit, so a cents-vs-USD close scored a ~100x
    # phantom return able to mark a strong_buy correct. With no verifiable unit
    # the horizon must read incomplete, not scored.
    def test_r8_1_an_anchorless_close_without_a_resolvable_unit_is_incomplete(
            self):
        verdict = self._anchorless_verdict()
        verdict["atlas_envelope"]["key_numbers"] = []   # reference fact omitted
        row = ledger.build_row(verdict, RULES)
        self.assertIsNone(row["price_at_verdict"]["unit"])  # unit unresolved
        ledger.append_row(row, self.ledger_path)
        due = [h["due_date"] for h in row["horizons"]
               if h["trading_days"] == 252][0]
        obs = _obs("btc-2026-01-05", "7731349")         # a cents-scale close
        horizon_obs = obs["horizon_observations"][0]
        horizon_obs["due_date"] = due
        horizon_obs["subject_close"]["as_of"] = due
        horizon_obs["subject_close"]["unit"] = "cents"
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [obs])
        by_id = _scored_by_id(score.score(self.ledger_path, obs_path, RULES))
        h = [x for x in by_id["btc-2026-01-05"]["horizons"]
             if x["trading_days"] == 252][0]
        self.assertEqual(h["basis"], "incomplete")

    # r8-2: r7-4 compared the excess as a Decimal, but _return_pct divided
    # under Decimal's default 28-digit context, so a close carrying more than
    # 28 significant digits was rounded UP onto the bar before the comparison.
    # A close a hair below the strong_buy bar (the value below) must read
    # WRONG, not be rounded up onto the bar and marked correct.
    def test_r8_2_a_threshold_decision_survives_precision_beyond_28_digits(
            self):
        row = _row("sb-edge-2", "strong_buy", asset_class="crypto",
                   benchmark=None,
                   subject={"kind": "bitcoin", "name": "Bitcoin",
                            "ticker": None, "listing": None,
                            "currency": "USD"})
        obs = _obs("sb-edge-2",
                   "109.999999999999999999999999999999999")  # 33 nines, < +10%
        self.assertIs(
            self._score_one(row, obs)["rating_outcome"]["correct"], False)


class TestU7bScorerFixes(LedgerTempCase):
    """UPGRADE-2 U7b: the two scorer defects registered at the U7 round cap,
    P-U7-9 and P-U7-10. Each new-behaviour test was proven to FAIL against the
    pre-fix code at base 1a3260e before its fix was written."""

    def _anchorless_verdict(self):
        """A published anchorless (crypto) verdict whose scenario reference
        price is bound to reference_price_fact_id."""
        return {
            "schema_version": "1.4.0", "run_id": "btc-2026-01-05",
            "subject": {"kind": "bitcoin", "asset_class": "crypto",
                        "name": "Bitcoin", "ticker": None, "listing": None,
                        "currency": "USD"},
            "rating": "strong_buy",
            "mispricing": {"read": "no_view", "magnitude": None,
                           "arithmetic": None},
            "scenario_rating": {"reference_price": 77313.49,
                                "reference_price_fact_id": "price_last"},
            "tripwires": {"invalidation_levels": [], "reopening_triggers": [],
                          "falsifiers": []},
            "atlas_envelope": {"key_numbers": [
                {"name": "price on the record", "value": "77313.49",
                 "unit": "USD", "as_of": "2026-01-05",
                 "pack_fact_id": "price_last"}]},
            "provenance": {
                "pack_hash": "c" * 64, "ledger_row_id": "btc-2026-01-05",
                "models_per_seat": {"advisor_bull": "opus"},
                "challenger_model_requested": "gpt-5.6-sol",
                "timestamps": {"run_started": "2026-01-05T10:00:00Z",
                               "published": "2026-01-05T11:00:00Z"},
                "tokens": {"per_seat": {"advisor_bull": 1}, "seats_total": 1,
                           "challenger": 1}, "prompt_bytes_total": 1}}

    # P-U7-9: r8-1 made a None (unresolved) baseline unit read incomplete
    # against a unit-bearing observed close, but _unit_mismatch of two nulls
    # still returned False, so a unitless observed close against the same
    # unresolved baseline was scored. An anchorless verdict that omits its
    # reference fact leaves the baseline unit unresolved; a schema-valid
    # observation may carry a null subject-close unit; the two nulls must not
    # agree and score a phantom return able to mark a strong_buy correct.
    def test_p_u7_9_a_unitless_close_against_an_unresolved_baseline_incomplete(
            self):
        verdict = self._anchorless_verdict()
        verdict["atlas_envelope"]["key_numbers"] = []   # reference fact omitted
        row = ledger.build_row(verdict, RULES)
        self.assertIsNone(row["price_at_verdict"]["unit"])  # unit unresolved
        ledger.append_row(row, self.ledger_path)
        due = [h["due_date"] for h in row["horizons"]
               if h["trading_days"] == 252][0]
        obs = _obs("btc-2026-01-05", "7731349")     # a hundred times the base
        horizon_obs = obs["horizon_observations"][0]
        horizon_obs["due_date"] = due
        horizon_obs["subject_close"]["as_of"] = due
        horizon_obs["subject_close"]["unit"] = None     # both units null
        obs_path = os.path.join(self.base, "obs.json")
        canonical.write_canonical_json(obs_path, [obs])
        by_id = _scored_by_id(score.score(self.ledger_path, obs_path, RULES))
        scored = by_id["btc-2026-01-05"]
        h = [x for x in scored["horizons"] if x["trading_days"] == 252][0]
        self.assertEqual(h["basis"], "incomplete")
        self.assertIsNone(h["excess_pct"])
        self.assertIsNone(scored["rating_outcome"]["correct"])

    # P-U7-10: an equity carries a benchmark object even when the pack has no
    # benchmark level (level_at_verdict None); _score_horizon ran the benchmark
    # unit check regardless, so a unit-bearing index close in the capture made
    # the None benchmark unit mismatch and returned the all-null incomplete,
    # erasing the subject's own return. Each leg is now computed independently:
    # with no benchmark level the subject return is recorded, the excess is
    # null, the basis is absolute, and the benchmark unit check does not run.
    def test_p_u7_10_a_missing_benchmark_level_keeps_the_subject_return(self):
        row = _row("eq-no-bench-level", "buy",
                   benchmark={"name": "SPDR S&P 500 ETF", "ticker": "SPY",
                              "level_at_verdict": None, "unit": None,
                              "fact_id": None})
        horizon_obs = {
            "trading_days": 252, "due_date": "2027-01-04",
            "subject_close": {"value": "110", "unit": "USD_per_share",
                              "as_of": "2027-01-04", "source": "s"},
            "benchmark_close": {"value": "6000", "unit": "index",
                                "as_of": "2027-01-04", "source": "s"}}
        display, exact = score._score_horizon(row, horizon_obs)
        self.assertAlmostEqual(display["subject_return_pct"], 10.0, places=6)
        self.assertIsNone(display["excess_pct"])
        self.assertEqual(display["basis"], "absolute")
        self.assertIsNone(exact)


if __name__ == "__main__":
    unittest.main()
