"""The ledger row: one append-only record per published verdict (U7.1).

The publisher calls `build_row` on the verdict it just assembled and
`append_row` to write it, then records the row's hash in the run record;
read-back proves the two agree. The same `build_row` reads a verdict of
ANY schema version on record (1.0.0 through the current one), so the
back-fill of past sittings runs through the identical code.

Where the ledger file lives: `COUNCIL_LEDGER_PATH` if it is set, else
`council/ledger/ledger.jsonl` beside the run archive. The append creates
the directory if it is missing.

Book-blind: a row carries the subject's public identity only - never a
size, never a holding.
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")))

from council.lib import canonical, validate  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCHEMA_PATH = os.path.join(ROOT, "council", "schemas", "ledger_row.json")
RULES_PATH = os.path.join(ROOT, "council", "floors", "scoring-rules.json")
LEDGER_ENV = "COUNCIL_LEDGER_PATH"

LEDGER_ROW_VERSION = "1.0.0"


def default_path():
    """The ledger file: the environment override, else the repo default."""
    override = os.environ.get(LEDGER_ENV)
    if override:
        return override
    return os.path.join(ROOT, "council", "ledger", "ledger.jsonl")


RUNS_ENV = "COUNCIL_RUNS_PATH"
# A report render appends its own event to a run record (a READING of the
# run, not a step of it); the run's real last step is what settles whether
# it finished. Matches council.engine.readback.RENDER_EVENT.
RENDER_EVENT = "report_rendered"


def runs_root():
    """Where run archives live: the environment override, else the repo
    default beside the ledger."""
    override = os.environ.get(RUNS_ENV)
    if override:
        return override
    return os.path.join(ROOT, "council", "runs")


def _run_finished(run_id, root):
    """Whether the run that wrote a row finished. A row whose run archive is
    ABSENT is treated as finished (the invented fixtures, and any reader
    without the run store); a row whose archive is present is finished only
    when its record's last real step is run_finished/DONE - the SAME test
    read-back applies, so the gate can never disagree with read-back about a
    real published verdict. Anything else is a run discarded mid-publication
    (owner rulings M5, O1) whose append-only row must not be counted."""
    record = os.path.join(root, run_id or "", "runrecord.jsonl")
    if not os.path.exists(record):
        return True
    try:
        events = canonical.read_jsonl(record)
    except (ValueError, OSError):
        # A present record we cannot read is a crash mid-write (owner rulings
        # M5, O1), not a finished run: it fails closed so the orphan row is
        # not counted as a published verdict (operating envelope item 6).
        return False
    steps = [event for event in events
             if event.get("event") != RENDER_EVENT] or events
    if not steps:
        return True
    last = steps[-1]
    return last.get("event") == "run_finished" and last.get("state") == "DONE"


def confirmed_rows(rows, root=None):
    """The ledger rows whose owning run finished. Drops an orphan row left
    by a run that crashed after its append but before it published and was
    then discarded - so a verdict the council never published is never
    scored or shown as one (U7.1: one row PER PUBLISHED verdict)."""
    root = runs_root() if root is None else root
    return [row for row in rows if _run_finished(row.get("run_id"), root)]


def load_rules():
    return canonical.read_json(RULES_PATH)


def _schema():
    return canonical.read_json(SCHEMA_PATH)


def _as_str(value):
    """A figure carried into the row as text, exactly as it reads."""
    if value is None or isinstance(value, str):
        return value
    return repr(value) if isinstance(value, float) else str(value)


def _parse_ts(text):
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def verdict_date(verdict):
    """The date the ruling was published, YYYY-MM-DD."""
    published = ((verdict.get("provenance") or {}).get("timestamps") or {}
                 ).get("published")
    if isinstance(published, str) and len(published) >= 10:
        return published[:10]
    return None


def _published_at(verdict):
    """The full publication timestamp string, or ''. The back-fill orders on
    this, not on verdict_date's day alone, so two sittings of one subject on
    the same day keep their true sequence and the re-sit chain is not reversed
    (U7.5). ISO-8601 UTC timestamps sort chronologically as text, the same way
    verdict_date's day does."""
    published = ((verdict.get("provenance") or {}).get("timestamps") or {}
                 ).get("published")
    return published if isinstance(published, str) else ""


def add_trading_days(start, count):
    """`count` trading days after `start` (a date), counting Monday to
    Friday only. This is a business-day approximation: it does not know
    the exchange's holiday calendar, which no offline script can carry, so
    a real due date can fall a few days later. The observation session
    reads the close on the traded day at or after the printed date."""
    day = start
    added = 0
    while added < count:
        day += datetime.timedelta(days=1)
        if day.weekday() < 5:
            added += 1
    return day


def _horizons(vd_text, rules):
    start = datetime.date.fromisoformat(vd_text)
    rows = []
    for days in rules["horizons_trading_days"]:
        due = add_trading_days(start, days)
        rows.append({"trading_days": days, "due_date": due.isoformat()})
    return rows


def _price_at_verdict(verdict, rules):
    key_numbers = (verdict.get("atlas_envelope") or {}).get("key_numbers") or []
    scenario = verdict.get("scenario_rating") or {}
    ref = scenario.get("reference_price")
    if ref is not None:
        # The anchorless scenario reference price IS the value of
        # reference_price_fact_id (engine/ladder reads it from that pack fact),
        # so its unit is that fact's unit. Carry the unit so a unit-mismatched
        # observed close is caught as incomplete, not scored as a spurious
        # return; an absent or unit-less fact keeps unit None, as tolerant as
        # the field was before.
        ref_fact = scenario.get("reference_price_fact_id")
        unit = None
        for row in key_numbers:
            if ref_fact and row.get("pack_fact_id") == ref_fact:
                unit = row.get("unit")
                break
        return {"value": _as_str(ref), "unit": unit, "fact_id": ref_fact}
    for fact_id in rules.get("price_fact_ids", []):
        for row in key_numbers:
            if row.get("pack_fact_id") == fact_id:
                return {"value": _as_str(row.get("value")),
                        "unit": row.get("unit"), "fact_id": fact_id}
    return None


def _benchmark(verdict, rules):
    asset_class = (verdict.get("subject") or {}).get("asset_class")
    config = (rules.get("benchmarks") or {}).get(asset_class) if asset_class \
        else None
    if not config:
        return None
    key_numbers = (verdict.get("atlas_envelope") or {}).get("key_numbers") or []
    level, unit, fact_id = None, None, None
    for candidate in config.get("level_fact_ids", []):
        for row in key_numbers:
            if row.get("pack_fact_id") == candidate:
                level = _as_str(row.get("value"))
                unit = row.get("unit")
                fact_id = candidate
                break
        if level is not None:
            break
    return {"name": config["name"], "ticker": config.get("ticker"),
            "level_at_verdict": level, "unit": unit, "fact_id": fact_id}


def _int_or_none(value):
    return value if isinstance(value, int) and not isinstance(value, bool) \
        else None


def _tokens_by_stage(verdict):
    provenance = verdict.get("provenance") or {}
    tokens = provenance.get("tokens") or {}
    capture = (provenance.get("evidence") or {}).get("capture") or {}
    seats = {}
    for seat, value in (tokens.get("per_seat") or {}).items():
        seats[seat] = _int_or_none(value)
    return {
        "capture": _int_or_none(capture.get("tokens")),
        "evidence_challenge": _int_or_none(
            capture.get("evidence_challenge_tokens")),
        "seats": seats,
        "verdict_challenge": _int_or_none(tokens.get("challenger")),
    }


def _wall_clock_minutes(verdict):
    provenance = verdict.get("provenance") or {}
    timestamps = provenance.get("timestamps") or {}
    published = _parse_ts(timestamps.get("published"))
    started = _parse_ts((provenance.get("evidence") or {}).get(
        "clock_started") or timestamps.get("run_started"))
    if published is None or started is None:
        return None
    return round((published - started).total_seconds() / 60.0, 1)


def _models(verdict):
    provenance = verdict.get("provenance") or {}
    seats = {}
    for seat, value in (provenance.get("models_per_seat") or {}).items():
        seats[seat] = value if isinstance(value, str) else None
    challenger = provenance.get("challenger_model_requested")
    return {"seats": seats,
            "challenger": challenger if isinstance(challenger, str) else None}


def row_id_for(verdict):
    """A verdict names its own ledger row in provenance from 1.4.0; a
    verdict written before that is keyed by its run id, which is unique per
    sitting and is the ledger's primary key either way."""
    named = (verdict.get("provenance") or {}).get("ledger_row_id")
    if isinstance(named, str) and named:
        return named
    return verdict["run_id"]


def build_row(verdict, rules=None):
    """One ledger row from a verdict of any schema version. Reads the
    verdict only; fields the older contracts do not carry come through as
    null. `prior_ledger_row_id` is resolved at append time against the
    ledger already on disk, and is null here."""
    rules = rules or load_rules()
    subject = verdict.get("subject") or {}
    tripwires = verdict.get("tripwires") or {}
    mispricing = verdict.get("mispricing") or {}
    vd = verdict_date(verdict)
    return {
        "ledger_row_version": LEDGER_ROW_VERSION,
        "ledger_row_id": row_id_for(verdict),
        "run_id": verdict["run_id"],
        "verdict_schema_version": verdict.get("schema_version"),
        "prior_ledger_row_id": None,
        "subject": {
            "kind": subject.get("kind"),
            "name": subject.get("name"),
            "ticker": subject.get("ticker"),
            "listing": subject.get("listing"),
            "currency": subject.get("currency"),
        },
        "asset_class": subject.get("asset_class"),
        "verdict_date": vd,
        "published_at": _published_at(verdict),
        "rating": verdict.get("rating"),
        "mispricing": {"read": mispricing.get("read"),
                       "magnitude": mispricing.get("magnitude")},
        "price_at_verdict": _price_at_verdict(verdict, rules),
        "benchmark": _benchmark(verdict, rules),
        "horizons": _horizons(vd, rules) if vd else [],
        "tripwire_levels": [
            {"level": row.get("level"), "unit": row.get("unit"),
             "meaning": row.get("meaning")}
            for row in tripwires.get("invalidation_levels", [])],
        "reopening_triggers": [
            {"kind": row.get("kind"), "detail": row.get("detail"),
             "level": row.get("level"), "unit": row.get("unit"),
             "date": row.get("date")}
            for row in tripwires.get("reopening_triggers", [])],
        "falsifiers": [
            {"figure_name": row.get("figure_name"), "date": row.get("date"),
             "source": row.get("source")}
            for row in tripwires.get("falsifiers", [])],
        "tokens_by_stage": _tokens_by_stage(verdict),
        "wall_clock_minutes": _wall_clock_minutes(verdict),
        "models": _models(verdict),
    }


def row_hash(row):
    """The one canonical hash of a row, the value read-back checks."""
    return canonical.sha256_bytes(canonical.canonical_bytes(row))


def read_rows(path=None):
    path = path or default_path()
    if not os.path.exists(path):
        return []
    return canonical.read_jsonl(path)


def _same_subject(a, b):
    sa, sb = a.get("subject") or {}, b.get("subject") or {}
    if a.get("asset_class") != b.get("asset_class"):
        return False
    if sa.get("ticker") and sb.get("ticker"):
        if sa.get("ticker") != sb.get("ticker"):
            return False
        # A ticker is unique only within its listing: two different securities
        # can reuse one across exchanges. Where both rows name a listing it
        # must match too, so they are not merged into one re-sit chain (a wrong
        # prior link, or a false out-of-order refusal); a row predating the
        # listing field falls back to the ticker alone.
        if sa.get("listing") and sb.get("listing"):
            return sa.get("listing") == sb.get("listing")
        return True
    return sa.get("name") == sb.get("name")


def find_prior_row_id(existing_rows, row):
    """The most recent existing row for the same subject, so a re-sit's
    row links the sitting it re-sits (U7.5). Identity only - ticker where
    both carry one, else name, within the same asset class. Book-blind."""
    prior = None
    for candidate in existing_rows:
        if candidate.get("ledger_row_id") == row.get("ledger_row_id"):
            continue
        if _same_subject(candidate, row):
            prior = candidate.get("ledger_row_id")
    return prior


def _out_of_order(prior, row):
    """True when appending `row` after the same-subject `prior` would reverse
    the re-sit chain (U7.5), so the append is refused. Two ways it can:
    `prior` is a strictly LATER sitting (a later day, or the same day at a
    later publication time); or the two share a day and `prior` predates the
    published_at field, so it carries no intra-day time and cannot be proven
    earlier than this timestamped row - an ambiguous order, refused rather
    than written with a possibly-reversed link. Two rows that BOTH predate
    the field keep the accepted day-granularity fallback and are not refused
    here (their order is resolved by file order in `find_prior_row_id`)."""
    new_date = row.get("verdict_date") or ""
    new_pub = row.get("published_at") or ""
    prior_date = prior.get("verdict_date") or ""
    prior_pub = prior.get("published_at") or ""
    if (prior_date, prior_pub) > (new_date, new_pub):
        return True
    return prior_date == new_date and bool(new_pub) and not prior_pub


class DuplicateLedgerRow(ValueError):
    """A row whose ledger_row_id is already on file was appended again. One
    row PER published verdict (U7.1): a retry, a re-run or a back-fill over a
    partly-filled ledger must not write a second copy and double-count it
    (operating envelope item 5, idempotency)."""


class LedgerOutOfOrder(ValueError):
    """A row for an EARLIER sitting was appended while a LATER sitting of the
    same subject is already on file - earlier by verdict day, or by the
    publication time within the same day. Appending it would insert before an
    existing re-sit and reverse the chain the re-sit link records (U7.5), so
    it is REFUSED loudly rather than written wrong. Back-fill oldest first,
    into a ledger that holds no later sitting of the subject."""


def append_row(row, path=None):
    """Resolve the re-sit link against the ledger on disk, validate the
    row, append it, and return (row_hash, row_as_written). The append is
    the last durable step: the caller records the returned hash.

    A row whose ledger_row_id is already on file is REFUSED with
    `DuplicateLedgerRow`, so the same verdict is never appended twice."""
    path = path or default_path()
    existing = read_rows(path)
    row_id = row.get("ledger_row_id")
    if any(prior.get("ledger_row_id") == row_id for prior in existing):
        raise DuplicateLedgerRow(
            "a ledger row for %r is already on file; the same verdict is "
            "never appended twice" % row_id)
    later = [prior.get("ledger_row_id") for prior in existing
             if prior.get("ledger_row_id") != row_id
             and _same_subject(prior, row)
             and _out_of_order(prior, row)]
    if later:
        raise LedgerOutOfOrder(
            "a later sitting of the same subject is already on file (%s); "
            "appending %r for an earlier sitting would reverse the re-sit "
            "chain (U7.5)" % (", ".join(later), row_id))
    written = dict(row)
    written["prior_ledger_row_id"] = find_prior_row_id(existing, written)
    errors = validate.validate(written, _schema())
    if errors:
        raise ValueError("the ledger row does not match its schema:\n  "
                         + "\n  ".join(errors))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    canonical.append_jsonl(path, written)
    return row_hash(written), written


def back_fill(verdicts, path=None, rules=None):
    """Append a batch of past verdicts as rows, one per verdict, through the
    SAME build_row/append_row the publisher uses (so every schema version on
    record reads identically). Verdicts are appended OLDEST first (by verdict
    date), whatever order the caller supplies them in, so each re-sit's row
    links the sitting it re-sits and never the reverse (U7.5). A verdict whose
    row is already on file is SKIPPED and reported, never a batch failure, so
    a back-fill re-run over a partly-filled ledger is safe (operating envelope
    item 5, idempotency). Returns (appended_ids, skipped_ids), oldest first.
    Reads only what it is handed; it never fetches and never touches the run
    store."""
    rules = rules or load_rules()
    path = path or default_path()
    ordered = sorted(verdicts, key=_published_at)
    appended, skipped = [], []
    for verdict in ordered:
        row = build_row(verdict, rules)
        try:
            append_row(row, path)
        except DuplicateLedgerRow:
            skipped.append(row["ledger_row_id"])
            continue
        appended.append(row["ledger_row_id"])
    return appended, skipped
