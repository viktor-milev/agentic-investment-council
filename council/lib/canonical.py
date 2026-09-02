"""Canonical bytes, hashing, and durable file writes.

The freeze obligation (REBUILD-SPEC section 5): the same accepted capture must
build into byte-identical pack files every time, on any OS. Canonical form is
JSON with sorted keys, single separators, ASCII escapes, one trailing LF,
UTF-8. Figures are carried as the exact strings the capture recorded;
canonicalization never touches a value (PRECISION-REG-1: rounding at the
freeze was proven to contradict a pack's own declared arithmetic).
"""

import hashlib
import json
import os
import tempfile


def canonical_bytes(obj):
    """The one canonical byte form of a JSON-shaped object."""
    text = json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)
    return text.encode("utf-8") + b"\n"


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_bytes_atomic(path, data):
    """Write bytes so a crash leaves either the old file or the new, never a
    torn one: temp file in the target directory, fsync, then rename."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def write_canonical_json(path, obj):
    """Write an object in canonical form; returns the sha256 of the bytes."""
    data = canonical_bytes(obj)
    write_bytes_atomic(path, data)
    return sha256_bytes(data)


def read_json(path):
    with open(path, "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def append_jsonl(path, obj):
    """Append one record to an append-only JSONL file, durably."""
    line = json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False)
    with open(path, "ab") as handle:
        handle.write(line.encode("utf-8") + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_jsonl(path):
    records = []
    with open(path, "rb") as handle:
        for raw in handle.read().decode("utf-8").splitlines():
            if raw.strip():
                records.append(json.loads(raw))
    return records
