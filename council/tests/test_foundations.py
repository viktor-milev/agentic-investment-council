"""Foundations suite: canonical bytes, the schema validator, the contract
schemas, the floors data, and the split's language rule (REBUILD-SPEC
section 2) enforced over every file in the council tree."""

import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, validate  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_DIR = os.path.join(ROOT, "council", "schemas")


class TestCanonical(unittest.TestCase):
    def test_key_order_never_changes_the_bytes(self):
        a = canonical.canonical_bytes({"b": 1, "a": [1, 2], "c": {"y": "x"}})
        b = canonical.canonical_bytes({"c": {"y": "x"}, "a": [1, 2], "b": 1})
        self.assertEqual(a, b)

    def test_bytes_end_with_one_lf_and_are_ascii(self):
        data = canonical.canonical_bytes({"k": "münchen"})
        self.assertTrue(data.endswith(b"\n"))
        self.assertFalse(data.endswith(b"\n\n"))
        data.decode("ascii")

    def test_values_are_carried_exactly(self):
        data = canonical.canonical_bytes({"v": "25.150000000000002"})
        self.assertIn(b"25.150000000000002", data)

    def test_known_hash_is_stable(self):
        self.assertEqual(
            canonical.sha256_bytes(b"{}\n"),
            "ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356")

    def test_write_read_roundtrip_and_file_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.json")
            digest = canonical.write_canonical_json(path, {"a": "1"})
            self.assertEqual(canonical.read_json(path), {"a": "1"})
            self.assertEqual(canonical.sha256_file(path), digest)

    def test_atomic_write_replaces_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.bin")
            canonical.write_bytes_atomic(path, b"first version, longer")
            canonical.write_bytes_atomic(path, b"second")
            with open(path, "rb") as handle:
                self.assertEqual(handle.read(), b"second")

    def test_jsonl_appends_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.jsonl")
            canonical.append_jsonl(path, {"n": 1})
            canonical.append_jsonl(path, {"n": 2})
            self.assertEqual(canonical.read_jsonl(path),
                             [{"n": 1}, {"n": 2}])


class TestValidator(unittest.TestCase):
    def test_unknown_keyword_is_refused_at_load(self):
        with self.assertRaises(validate.SchemaError):
            validate.check_schema({"type": "object", "oneOf": []})

    def test_boolean_is_not_an_integer(self):
        errors = validate.validate(True, {"type": "integer"})
        self.assertTrue(errors)

    def test_type_list_allows_null(self):
        self.assertEqual(validate.validate(None, {"type": ["string", "null"]}), [])
        self.assertEqual(validate.validate("x", {"type": ["string", "null"]}), [])

    def test_required_and_unexpected_fields_are_named(self):
        schema = {"type": "object", "additionalProperties": False,
                  "required": ["a"], "properties": {"a": {"type": "string"}}}
        errors = validate.validate({"b": 1}, schema)
        text = "\n".join(errors)
        self.assertIn("'a'", text)
        self.assertIn("'b'", text)

    def test_pattern_is_anchored(self):
        schema = {"type": "string", "pattern": "[a-f0-9]{4}"}
        self.assertEqual(validate.validate("ab12", schema), [])
        self.assertTrue(validate.validate("ab123", schema))
        self.assertTrue(validate.validate("zab12", schema))

    def test_error_paths_point_at_the_field(self):
        schema = {"type": "object", "properties": {
            "list": {"type": "array", "items": {"type": "object", "properties": {
                "v": {"enum": ["x"]}}}}}}
        errors = validate.validate({"list": [{"v": "y"}]}, schema)
        self.assertIn("$.list[0].v", errors[0])

    def test_const_enum_bounds_lengths(self):
        self.assertTrue(validate.validate("1.0.1", {"const": "1.0.0"}))
        self.assertTrue(validate.validate(0, {"type": "integer", "minimum": 1}))
        self.assertTrue(validate.validate("", {"type": "string", "minLength": 1}))
        self.assertTrue(validate.validate([1], {"type": "array", "minItems": 2}))


class TestContractSchemas(unittest.TestCase):
    def files(self):
        return [os.path.join(SCHEMA_DIR, name)
                for name in sorted(os.listdir(SCHEMA_DIR))
                if name.endswith(".json")]

    def test_every_schema_file_parses_and_is_enforceable(self):
        self.assertTrue(self.files())
        for path in self.files():
            with open(path, "rb") as handle:
                doc = json.loads(handle.read().decode("utf-8"))
            if os.path.basename(path) == "seat_answers.json":
                for member, schema in doc.items():
                    if isinstance(schema, dict):
                        validate.check_schema(schema, member)
            else:
                validate.check_schema(doc, os.path.basename(path))

    def test_verdict_schema_is_version_1_4_0(self):
        # 1.3.0 was unit ENVELOPE-ATLAS (owner ruling AB23): the hand-off
        # gained identity, audit state, bound tags and pinned sizing
        # units. 1.3.1 is UPGRADE-2 U3 (owner ruling AC3): the
        # provenance gained what the sitting decided and spent before a
        # seat was paid. 1.4.0 is UPGRADE-2 U7 (owner ruling AC7): the
        # provenance names the ledger row this verdict is recorded under.
        # Runs already published keep the version they were written under
        # and are never rewritten.
        with open(os.path.join(SCHEMA_DIR, "verdict_schema.json"), "rb") as f:
            doc = json.loads(f.read().decode("utf-8"))
        self.assertEqual(doc["properties"]["schema_version"]["const"], "1.4.0")

    def test_the_evidence_finding_shape_is_written_once_in_two_files(self):
        """The auditor's answer and the capture's record of it carry the
        SAME finding (owner ruling AC2). The validator subset has no
        $ref, so the shape is written in both contracts - and pinned
        equal here, because two copies that drift are one contract
        nobody can trust."""
        with open(os.path.join(SCHEMA_DIR, "evidence_findings_schema.json"),
                  "rb") as f:
            answer = json.loads(f.read().decode("utf-8"))
        with open(os.path.join(SCHEMA_DIR, "capture_schema.json"),
                  "rb") as f:
            capture = json.loads(f.read().decode("utf-8"))
        recorded = (capture["properties"]["evidence_challenge"]
                    ["properties"]["findings"]["items"])
        declared = answer["properties"]["findings"]["items"]

        def bare(schema):
            """The shape, without the prose: a description belongs to
            its reader, and the auditor's reader is not the pack's."""
            if isinstance(schema, dict):
                return dict((key, bare(value))
                            for key, value in schema.items()
                            if key != "description")
            if isinstance(schema, list):
                return [bare(item) for item in schema]
            return schema

        self.assertEqual(bare(recorded), bare(declared))

    def test_capture_contract_is_version_1_8_0(self):
        # MINOR, unit UPGRADE-2 FI-ARCHETYPE (owner rulings AC28, AC30 and
        # AC32): the financial-institution archetype and its optional frame
        # fields, and the owner's one-line question. All optional in the
        # contract; the gate and the sufficiency gate enforce them.
        #
        # Before that:
        # PATCH 1.7.1, unit UPGRADE-2 U4(a2): a derived fact may be a tape
        # row ("series_stat", with its optional window, formula and date,
        # one operand allowed) - computed at freeze from the series.
        #
        # Before that, bumped by unit UPGRADE-2 U4(a) (owner ruling AC4): an optional
        # price_series and benchmark_series (the daily closes the tape table
        # is computed from) and an optional per-sitting benchmark. All three
        # are optional, so a pack that carries none - every capture written
        # before this unit, a coin, bullion - is still valid unchanged.
        #
        # Before that, bumped by unit UPGRADE-2 U3e (owner ruling AC15, P2 and P4): the
        # business frame gains the subject's archetype and why, and whether
        # its thesis rests on an identifiable cycle and why; the third
        # canonical test gains the rating measure that archetype calls for;
        # and an optional top-level cycle block carries three to five dated
        # series for that cycle, or the declared gap. Every addition is
        # optional in the contract and enforced for a single name only, so a
        # pack that carries none is still valid. Runs already on record keep
        # the version they were written under and are never rewritten.
        with open(os.path.join(SCHEMA_DIR, "capture_schema.json"),
                  "rb") as f:
            doc = json.loads(f.read().decode("utf-8"))
        self.assertEqual(doc["properties"]["capture_version"]["const"],
                         "1.8.0")
        for optional in ("price_series", "benchmark_series", "benchmark",
                         "question_line"):
            self.assertIn(optional, doc["properties"])
            self.assertNotIn(optional, doc["required"])

    def test_floors_data_is_version_1_7_0(self):
        # MINOR, unit UPGRADE-2 FI-ARCHETYPE (owner rulings AC28 and AC30):
        # the financial-institution archetype row with its sub-types, the
        # capital and cost-of-risk families, and the sub-type floors. MINOR
        # again, unit U4(b) (owner ruling AC4): insiders' dealings and the
        # company's own buying, two conditional single-stock floors.
        with open(os.path.join(ROOT, "council", "floors", "floors.json"),
                  "rb") as f:
            floors = json.loads(f.read().decode("utf-8"))
        self.assertEqual(floors["floors_version"], "1.7.0")
        table = floors["archetype_measures"]["table"]
        self.assertEqual(sorted(table["financial_institution"]["subtypes"]),
                         ["alternative_asset_manager", "bank",
                          "financial_holding", "insurer", "reinsurer",
                          "traditional_asset_manager"])
        for key in ("fi_families", "archetype_floors"):
            self.assertIn(key, floors)

    def test_rating_scale_is_the_owners_five_words(self):
        with open(os.path.join(SCHEMA_DIR, "verdict_schema.json"), "rb") as f:
            doc = json.loads(f.read().decode("utf-8"))
        self.assertEqual(doc["properties"]["rating"]["enum"],
                         ["strong_buy", "buy", "hold", "sell", "monitor"])

    def test_floors_data_parses_and_names_the_ruled_subjects(self):
        with open(os.path.join(ROOT, "council", "floors", "floors.json"), "rb") as f:
            floors = json.loads(f.read().decode("utf-8"))
        self.assertIn("single_stock", floors["classes"])
        self.assertIn("bitcoin", floors["classes"])
        self.assertIn("etf", floors["classes"])
        self.assertIn("basket", floors["classes"])
        self.assertIn("theme", floors["classes"])
        self.assertIn("AAPL", floors["names"])
        self.assertIn("GLXY", floors["names"])
        aapl_ids = [e.get("id") for e in floors["names"]["AAPL"]["floors"]]
        for ruled in ["operating_cash_flow_q", "net_income_q",
                      "cash_and_investments_mrq_end", "total_debt_mrq_end",
                      "buyback_spend_q", "diluted_shares_q",
                      "buyback_authorisation_remaining", "revenue_greater_china_q"]:
            self.assertIn(ruled, aapl_ids)
        # The W2.5 vehicle floor: the five ruled vehicle facts plus the
        # holdings picture as three specific required ids - the largest
        # holding named, its share of the fund, the top-ten
        # concentration (audit finding THEMES-A r2-1: the picture is
        # named facts, never a count of ids sharing a prefix).
        etf_floors = floors["classes"]["etf"]["floors"]
        etf_required = {e.get("id"): e for e in etf_floors
                        if e.get("level") == "required" and "id" in e}
        for ruled in ["price_last", "nav_per_share", "premium_discount",
                      "expense_ratio", "bid_ask_spread_30d_median",
                      "holding_largest_name", "holding_largest_share",
                      "holding_top10_share"]:
            self.assertIn(ruled, etf_required)


class TestLanguageRule(unittest.TestCase):
    """REBUILD-SPEC section 2: the council's vocabulary, schema, capture and
    prompts never contain the owner's-inventory words. Scans every tracked
    file under council/ except this suite (which must name the words to ban
    them) and run archives (which may quote the owner verbatim)."""

    BANNED = ("held", "unheld", "position", "sleeve", "weight",
              "account", "nlv", "net liquidation")

    def test_no_inventory_vocabulary_anywhere_in_the_tree(self):
        pattern = re.compile(
            r"\b(" + "|".join(re.escape(w) for w in self.BANNED) + r")s?\b",
            re.IGNORECASE)
        offenders = []
        council_dir = os.path.join(ROOT, "council")
        for base, dirs, files in os.walk(council_dir):
            dirs[:] = [d for d in dirs
                       if d not in ("runs", "__pycache__")]
            for name in files:
                if not name.endswith((".py", ".json", ".md")):
                    continue
                path = os.path.join(base, name)
                if os.path.abspath(path) == os.path.abspath(__file__):
                    continue
                with open(path, "rb") as handle:
                    text = handle.read().decode("utf-8", errors="replace")
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    offenders.append("%s:%d uses %r" % (
                        os.path.relpath(path, ROOT), line, match.group(0)))
        self.assertEqual(offenders, [],
                         "the split bans these words from the council tree:\n"
                         + "\n".join(offenders))


PROSE_FIX = os.path.join(ROOT, "council", "tests", "fixtures", "prose")


def _chair_rationales_present():
    return os.path.exists(os.path.join(PROSE_FIX, "chair_rationales.txt"))


class TestProseMeasure(unittest.TestCase):
    """The deterministic prose measure (spec U6.2/U6.3, owner ruling AC6).
    The two fixtures are the chairman's own rationale copied verbatim out of
    the runs on record - the runs themselves are never edited."""

    @classmethod
    def setUpClass(cls):
        from council.lib import prose
        cls.prose = prose
        cls.rules = prose.load_rules()

    def _fixture(self, which):
        # The two chair rationales, copied verbatim out of the runs on record
        # into one fixture file under named headers; the runs are never edited.
        path = os.path.join(PROSE_FIX, "chair_rationales.txt")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        blocks = {}
        current = None
        for line in text.splitlines():
            if line.startswith("===== ") and " chair " in line:
                current = "lulu" if line.split()[1] == "LULU" else "goog"
                blocks[current] = []
            elif current is not None:
                blocks[current].append(line)
        return "\n".join(blocks[which]).strip()

    @unittest.skipUnless(_chair_rationales_present(),
                         "the chair rationales fixture is not published "
                         "in the public copy")
    def test_the_lulu_rationale_is_red(self):
        score = self.prose.measure(self._fixture("lulu"), self.rules)
        self.assertEqual(score["words"], 815)
        self.assertEqual(score["dashes"], 11)
        self.assertEqual(score["antithesis"], 1)
        self.assertGreater(score["long_sentence_share"], 0.20)
        self.assertTrue(self.prose.failures(score, self.rules, score["words"]))

    @unittest.skipUnless(_chair_rationales_present(),
                         "the chair rationales fixture is not published "
                         "in the public copy")
    def test_the_goog_rationale_is_green_on_dashes_red_on_length(self):
        score = self.prose.measure(self._fixture("goog"), self.rules)
        self.assertEqual(score["dashes"], 0)
        self.assertEqual(score["dashes_per_1000_words"], 0.0)
        self.assertEqual(score["antithesis"], 0)
        self.assertGreater(score["long_sentence_share"], 0.20)

    def test_empty_text_scores_zero_and_fails_nothing(self):
        score = self.prose.measure("", self.rules)
        self.assertEqual(score["words"], 0)
        self.assertTrue(score["empty"])
        self.assertIsNone(score["grounded_share"])
        self.assertEqual(self.prose.failures(score, self.rules, 0), [])

    def test_the_measure_never_raises_on_odd_text(self):
        for text in (None, 12345, "?!.", "no terminator here",
                     "— — — dashes only"):
            self.prose.measure(text, self.rules)

    def test_the_three_number_style_patterns_fire(self):
        for text, want in (
                ("it held 2,619,191 thousand dollars at quarter end",
                 "thousand_dollars"),
                ("revenue rose 12 percent over the year", "percent_in_words"),
                ("as of 2026-06-30 the cash stood high", "iso_date")):
            ids = [hit["id"]
                   for hit in self.prose.measure(text, self.rules)["banned"]]
            self.assertIn(want, ids)

    def test_a_clean_analyst_line_passes_the_chair_thresholds(self):
        text = ("Revenue rose to $108M in the June 2026 quarter, from $92M a "
                "year earlier. The balance sheet carries $2.62B of cash as of "
                "30 Jun 2026. Guidance holds at 15% margins. The thesis is "
                "intact at this price.")
        score = self.prose.measure(text, self.rules)
        self.assertEqual(self.prose.failures(score, self.rules, score["words"]),
                         [])

    def test_describe_names_rhetorical_questions(self):
        # Audit finding r1-5: a chair warned ONLY for rhetorical questions must
        # be able to show that in the score the front warning and the appendix
        # display. describe() had omitted the count, so a warned score could
        # read as all-passing and never explain its own warning.
        score = self.prose.measure("Is this cheap? I think not.", self.rules)
        self.assertGreaterEqual(score["rhetorical_questions"], 1)
        self.assertIn("rhetorical question", self.prose.describe(score))

    def test_a_source_cue_matches_only_as_a_whole_word(self):
        # Audit finding r1-4 (P-U6-4), architect ruled IN: source cues are
        # matched as whole words, as month names already are, so "sec" no
        # longer counts inside "sector". A cue found as a substring over-counts
        # the grounded share and shows a wrong score. The cue list stays data.
        crowded = self.prose.measure(
            "The sector looks crowded to me now.", self.rules)
        self.assertEqual(crowded["grounded_sentences"], 0)
        # A real cue, whole word, still grounds the sentence.
        cited = self.prose.measure(
            "The SEC was clear on the point.", self.rules)
        self.assertEqual(cited["grounded_sentences"], 1)


class TestBriefsCarryTheVoice(unittest.TestCase):
    """Owner ruling AC6 and spec U6.5: the mannered-prose block rides in EVERY
    brief, so the council's voice does not depend on whose machine runs it."""

    @classmethod
    def setUpClass(cls):
        from council.engine import briefs
        cls.briefs = briefs

    def _subject(self):
        return {"kind": "single_stock", "asset_class": "equity",
                "name": "Acme Corp", "ticker": "ACME"}

    def test_the_manner_block_is_in_both_writing_rule_forms(self):
        self.assertIn(self.briefs.MANNER_BLOCK, self.briefs.WRITING_RULES)
        self.assertIn(self.briefs.MANNER_BLOCK, self.briefs.WRITING_RULES_SHORT)

    def test_percentages_take_one_decimal_always(self):
        # Owner ruling AC16(4) overrides the design audit's two-decimal draft:
        # one decimal always, no two-decimal exception for yields or coupons.
        for form in (self.briefs.WRITING_RULES, self.briefs.WRITING_RULES_SHORT):
            self.assertIn("one decimal", form)
            self.assertIn("always", form)
            self.assertNotIn("two for yields", form)
            self.assertNotIn("3.91%", form)
        self.assertIn("3.9%", self.briefs.WRITING_RULES)

    def test_every_seat_brief_carries_the_full_manner_block(self):
        briefs = self.briefs
        subject = self._subject()
        answer_path = "/tmp/answer.json"
        advisor_answers = {seat: "An answer citing $10M of cash."
                           for seat in briefs.ADVISOR_SEATS}
        ladders = {seat: None for seat in briefs.ADVISOR_SEATS}
        mapping = dict(zip(briefs.BLIND_LETTERS, briefs.ADVISOR_SEATS))
        built = {
            "frame": briefs.build_brief(
                "frame", "run", answer_path,
                question_verbatim="Is Acme a buy at $50?"),
            "advisor_bear": briefs.build_brief(
                "advisor_bear", "run", answer_path, casefile="CASE",
                subject=subject),
            "reviewer": briefs.build_brief(
                "reviewer", "run", answer_path, casefile="CASE",
                advisor_answers=advisor_answers, blind_mapping=mapping,
                subject=subject, advisor_ladders=ladders),
            "chair_draft": briefs.build_brief(
                "chair_draft", "run", answer_path, casefile="CASE",
                advisor_answers=advisor_answers,
                reviewer_answer={"markdown": "Review.", "synopsis": "Synopsis."},
                subject=subject, advisor_ladders=ladders),
            "chair_resolve": briefs.build_brief(
                "chair_resolve", "run", answer_path, casefile="CASE",
                draft_verdict={"rating": "hold"}, findings=[],
                endorsement=None, challenger_model="gpt-5.6-sol",
                subject=subject),
        }
        for kind, text in built.items():
            self.assertIn(briefs.MANNER_BLOCK, text,
                          "the %s brief does not carry the manner block" % kind)


if __name__ == "__main__":
    unittest.main(verbosity=1)
