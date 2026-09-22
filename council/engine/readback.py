"""The read-back entry point: python -m council.engine.readback <run_dir>.

A separate pair of eyes on the published file, deliberately independent of
the writer (it imports council.lib only, never the publisher). It proves,
against the append-only run record:

  1. verdict.json hashes to the value recorded at publish_authorized;
  2. the record's last event is run_finished with state DONE;
  3. atlas-envelope.json carries that same verdict hash;
  4. the envelope's pack hash equals the invocation's frozen pack hash;
  5. the standalone envelope equals the verdict's own copy of it, field
     for field (with the verdict hash filled in), so neither file can be
     quietly rewritten around the other;
  6. where the run recorded a ledger row (from U7 on), the shared ledger
     carries a row that hashes to the recorded value and the verdict names
     it - so a run cannot claim a track-record entry it did not write.

Exit 0 only when everything holds. A run that cannot pass this check
published nothing the owner may rely on.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical  # noqa: E402


def _ledger_path():
    """Where the shared ledger lives, resolved WITHOUT importing the
    writer - read-back stays a second pair of eyes. The rule matches
    council.ledger.ledger.default_path: the environment override, else the
    repo default beside the run archive."""
    override = os.environ.get("COUNCIL_LEDGER_PATH")
    if override:
        return override
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "council", "ledger", "ledger.jsonl")


# The first rendering of a report appends its own row to the run record
# (register item P-U3-5, architect's mechanism ruling): a READING of the
# run, not a step of it. What must be last is the run's own last step.
RENDER_EVENT = "report_rendered"


def _last_step(events):
    steps = [event for event in events
             if event.get("event") != RENDER_EVENT]
    return (steps or events)[-1]


def check(run_dir):
    """Print plain ok / NOT OK lines; return 0 only when everything holds."""
    failures = 0

    def ok(text):
        print("ok: %s" % text)

    def bad(text):
        nonlocal failures
        failures += 1
        print("NOT OK: %s" % text)

    record_path = os.path.join(run_dir, "runrecord.jsonl")
    if not os.path.exists(record_path):
        bad("no run record at %s" % record_path)
        return 1
    events = canonical.read_jsonl(record_path)
    authorized = [e for e in events if e.get("event") == "publish_authorized"]
    if not authorized:
        bad("the run record carries no publish_authorized event")
        return 1
    recorded_hash = authorized[-1].get("verdict_hash")
    ok("publish_authorized recorded verdict hash %s" % recorded_hash)

    last = _last_step(events)
    if last.get("event") == "run_finished" and last.get("state") == "DONE":
        ok("the record's last event is run_finished with state DONE")
    else:
        bad("the record's last event is %r, not run_finished/DONE - this "
            "run did not finish" % last.get("event"))

    verdict_path = os.path.join(run_dir, "verdict.json")
    if not os.path.exists(verdict_path):
        bad("verdict.json is missing")
    else:
        actual = canonical.sha256_file(verdict_path)
        if actual == recorded_hash:
            ok("verdict.json hashes to the recorded value")
        else:
            bad("verdict.json hashes to %s, not the recorded %s - the "
                "published file is not the file that was authorized"
                % (actual, recorded_hash))

    envelope_path = os.path.join(run_dir, "atlas-envelope.json")
    if not os.path.exists(envelope_path):
        bad("atlas-envelope.json is missing")
    else:
        envelope = canonical.read_json(envelope_path)
        if envelope.get("verdict_hash") == recorded_hash:
            ok("the Atlas envelope carries the same verdict hash")
        else:
            bad("the Atlas envelope's verdict_hash %r does not match the "
                "recorded %s" % (envelope.get("verdict_hash"),
                                 recorded_hash))
        invocation = canonical.read_json(
            os.path.join(run_dir, "invocation.json"))
        if envelope.get("pack_hash") == invocation.get("pack_sha256"):
            ok("the Atlas envelope's pack hash equals the frozen pack hash")
        else:
            bad("the Atlas envelope's pack_hash %r does not equal the "
                "invocation's %r" % (envelope.get("pack_hash"),
                                     invocation.get("pack_sha256")))
        if os.path.exists(verdict_path):
            try:
                verdict_doc = canonical.read_json(verdict_path)
            except ValueError:
                verdict_doc = None
                bad("verdict.json cannot be read to compare its own copy "
                    "of the envelope")
            if verdict_doc is not None:
                inner = dict(verdict_doc.get("atlas_envelope") or {})
                inner["verdict_hash"] = recorded_hash
                if inner == envelope:
                    ok("the standalone envelope equals the verdict's own "
                       "copy, field for field")
                else:
                    for key in sorted(set(inner) | set(envelope)):
                        if inner.get(key) != envelope.get(key):
                            bad("the standalone envelope's %r does not "
                                "equal the verdict's own copy of it" % key)
                            break

    # Check 6: the ledger row (U7). Only runs published from U7 on record
    # one; a run published before it carries no such event and is left
    # exactly as it read before - records are records.
    ledger_events = [e for e in events
                     if e.get("event") == "ledger_row_appended"]
    if ledger_events:
        recorded_row_hash = ledger_events[-1].get("row_hash")
        recorded_row_id = ledger_events[-1].get("ledger_row_id")
        path = _ledger_path()
        if not os.path.exists(path):
            bad("the record says a ledger row was written, but no ledger "
                "file stands at %s" % path)
        else:
            rows = canonical.read_jsonl(path)
            matched = [r for r in rows
                       if canonical.sha256_bytes(canonical.canonical_bytes(r))
                       == recorded_row_hash]
            if not matched:
                bad("no ledger row hashes to the recorded value %s - this "
                    "run's row is missing or was altered" % recorded_row_hash)
            else:
                ok("the ledger carries this run's row at the recorded hash")
                if matched[0].get("ledger_row_id") != recorded_row_id:
                    bad("the ledger row's id %r does not match the recorded "
                        "%r" % (matched[0].get("ledger_row_id"),
                                recorded_row_id))
                elif os.path.exists(verdict_path):
                    verdict_named = (
                        canonical.read_json(verdict_path).get("provenance")
                        or {}).get("ledger_row_id")
                    if verdict_named != recorded_row_id:
                        bad("the verdict names ledger row %r, not the "
                            "recorded %r" % (verdict_named, recorded_row_id))
                    else:
                        ok("the verdict names the ledger row that was written")

    if failures:
        print("READ-BACK FAILED: %d check(s) did not hold" % failures)
        return 1
    print("READ-BACK CLEAN: the published verdict is the authorized "
          "verdict and the run finished")
    return 0


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    return check(argv[0])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
