"""The append-only run record.

Every event the run takes is appended as one JSONL row; nothing ever rewrites
the file. The record is the authority on what has happened: the host derives
its progress from these events on every step, which is what lets a stepped,
never-resident host survive being invoked from scratch each time.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical  # noqa: E402

RECORD_NAME = "runrecord.jsonl"


def _now_utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def record_path(run_dir):
    return os.path.join(run_dir, RECORD_NAME)


def read_events(run_dir):
    """Every event so far, in append order. Missing record = no events."""
    path = record_path(run_dir)
    if not os.path.exists(path):
        return []
    return canonical.read_jsonl(path)


def append_event(run_dir, event, data):
    """Append one event row: {"seq", "ts", "event", **data}. Returns the row."""
    if not isinstance(data, dict):
        raise ValueError("event data must be a dict")
    for reserved in ("seq", "ts", "event"):
        if reserved in data:
            raise ValueError("event data may not carry %r" % reserved)
    row = {"seq": len(read_events(run_dir)) + 1,
           "ts": _now_utc(),
           "event": event}
    row.update(data)
    canonical.append_jsonl(record_path(run_dir), row)
    return row
