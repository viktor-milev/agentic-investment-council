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

    def test_verdict_schema_is_version_1_3_0(self):
        # Bumped by unit ENVELOPE-ATLAS (owner ruling AB23): the
        # hand-off gained identity, audit state, bound tags and
        # pinned sizing units. Runs already published keep the
        # version they were written under and are never rewritten.
        with open(os.path.join(SCHEMA_DIR, "verdict_schema.json"), "rb") as f:
            doc = json.loads(f.read().decode("utf-8"))
        self.assertEqual(doc["properties"]["schema_version"]["const"], "1.3.0")

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
