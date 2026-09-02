"""The deterministic freeze (REBUILD-SPEC section 5).

build_pack turns an accepted capture into the pack every seat will
read. NOTHING is rounded, reformatted or re-encoded here
(PRECISION-REG-1): the old stack proved that rounding at the freeze
makes a pack contradict its own declared arithmetic, so every value
stays the exact string the capture recorded. The equation sentence for
a derived fact is GENERATED from the frozen operand strings - never
written beside them by hand - so the prose next to a value can never
disagree with it (the section-6f lesson).

CLI:
    python -m council.evidence.freeze <capture.json> <out_dir_a> <out_dir_b>
Refuses (exit 3) unless the gate accepts the capture; builds pack.json
into BOTH directories, byte-compares the two files, and writes
<out_dir_a>/freeze-record.json. Exit codes: 0 byte-identical, 3 gate
refused, 1 mismatch or crash.
"""

import os
import sys
from datetime import date

from council.evidence import gate
from council.lib import canonical

PACK_VERSION = "1.0.0"

_OPERATOR_TEXT = {"add": " + ", "sum": " + ", "subtract": " - ",
                  "multiply": " * ", "divide": " / "}


def _generated_note(fact):
    """The equation sentence, generated from the frozen operand strings
    and the fact's own value string. ASCII operators only."""
    derived = fact["derived"]
    equation = _OPERATOR_TEXT[derived["operation"]].join(
        operand["value"] for operand in derived["operands"])
    return ("Deterministic transform inside the pack: %s = %s. "
            "Not an independent observation." % (equation, fact["value"]))


def build_pack(capture):
    """The pack, exactly as frozen: the capture untouched, the
    freshness arithmetic per tier1 fact, and the generated equation
    notes for every derived fact."""
    captured_on = date.fromisoformat(capture["captured_at"][:10])
    freshness = {}
    generated_notes = {}
    for fact in capture["tier1"]:
        age_days = (captured_on
                    - date.fromisoformat(fact["as_of"][:10])).days
        rule_days = fact["freshness_rule_days"]
        freshness[fact["id"]] = {
            "age_days": age_days,
            "rule_days": rule_days,
            "status": "within_rule" if age_days <= rule_days else "stale",
        }
        if fact["derived"]:
            generated_notes[fact["id"]] = _generated_note(fact)
    return {"pack_version": PACK_VERSION,
            "capture": capture,
            "freshness": freshness,
            "generated_notes": generated_notes}


_USAGE = ("usage: python -m council.evidence.freeze "
          "<capture.json> <out_dir_a> <out_dir_b>")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) != 3:
            print(_USAGE)
            return 1
        capture_path, dir_a, dir_b = args
        capture = canonical.read_json(capture_path)
        checked = gate.validate_capture(capture, gate.load_capture_schema())
        if checked["result"] != "accepted":
            print("freeze: refused - the gate does not accept this "
                  "capture, so nothing freezes")
            for reason in checked["reasons"]:
                print("  - " + reason)
            return 3
        pack = build_pack(capture)
        path_a = os.path.join(dir_a, "pack.json")
        path_b = os.path.join(dir_b, "pack.json")
        sha_a = canonical.write_canonical_json(path_a, pack)
        sha_b = canonical.write_canonical_json(path_b, pack)
        with open(path_a, "rb") as handle:
            bytes_a = handle.read()
        with open(path_b, "rb") as handle:
            bytes_b = handle.read()
        identical = bytes_a == bytes_b and sha_a == sha_b
        stale_count = sum(1 for entry in pack["freshness"].values()
                          if entry["status"] == "stale")
        record = {"pack_sha256": sha_a,
                  "byte_identical": identical,
                  "tier1_count": len(capture["tier1"]),
                  "tier2_count": len(capture["tier2"]),
                  "stale_count": stale_count}
        canonical.write_canonical_json(
            os.path.join(dir_a, "freeze-record.json"), record)
        if identical:
            print("freeze: built twice, byte-identical - sha256 %s" % sha_a)
            print("  tier1 facts: %d, tier2 passages: %d, stale: %d"
                  % (record["tier1_count"], record["tier2_count"],
                     stale_count))
            return 0
        print("freeze: MISMATCH - the two builds are not byte-identical "
              "(%s vs %s); nothing about this pack can be trusted"
              % (sha_a, sha_b))
        return 1
    except Exception as exc:
        print("freeze crashed: %r" % (exc,))
        return 1


if __name__ == "__main__":
    sys.exit(main())
