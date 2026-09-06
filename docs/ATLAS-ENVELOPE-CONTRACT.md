# The Atlas envelope — the hand-off contract

*Commissioned by the architect under owner ruling AB17 (2026-09-02). Rewritten by unit
ENVELOPE-ATLAS under owner ruling AB23 (2026-09-06), which accepted Atlas's written requests item
by item and pinned the sizing-input units. Ground truth: the producer is
`council/engine/publisher.py`, the declared shape is `council/schemas/verdict_schema.json`
(`atlas_envelope`), the checker is `council/engine/readback.py`, and the worked example is
`council/runs/council-btc-2026-09-01/atlas-envelope.json` — the live Bitcoin SELL. The stand-in
example is `council/runs/council-coin-2026-09-04` — Coinbase, HOLD — the first sitting whose
capital-spending figure is a declared ceiling (§2, "Bounds"). **Both were published under verdict
contract 1.2.0 and show the OLD shape: runs on record are never rewritten (§6).***

## 1. What the package is

Every published run writes two files: `verdict.json`, the full ruling, and `atlas-envelope.json`,
the machine hand-off. The envelope is a standalone JSON file, and the identical content is
duplicated field for field inside the verdict under `atlas_envelope`. Only one field differs by
construction: a document cannot carry its own hash, so `verdict_hash` is `null` in the verdict's
copy and carries the real value in the standalone file.

**Since verdict contract 1.3.0 the package stands alone.** It names the security it judged, states
the outside audit's outcome and the ceiling that audit endorsed, and labels every row that rests on
a bound rather than a measurement. A consumer no longer has to open a second file to know what was
judged, whether the rating was capped, or whether a figure is a limit rather than a reading.

## 2. What it contains

Every field below is declared in the schema, and `additionalProperties: false` means nothing else
can appear. Fields marked **[1.3.0]** are new in this contract.

**Identity — copied from the invocation's own subject, never chair-authored [1.3.0]**

- **`run_id`** — the sitting this package belongs to.
- **`subject_name`**, **`subject_ticker`**, **`subject_listing`**, **`subject_currency`** — the
  security. `ticker`, `listing` and `currency` may be null where the subject has none (an
  anchorless asset carries no listing); `subject_name` is always present.

**The opinion**

- **`rating`** — one of the owner's five words: `strong_buy`, `buy`, `hold`, `sell`, `monitor`
  (AB3). `sell` means a weighted twelve-month outcome below the cash bar. **Frozen contract: any
  change is an owner ruling and a loud version bump (§6).**
- **`subject_kind`** — `single_stock`, `etf`, `bitcoin`, `gold`, `commodity`, `theme` or `basket`;
  **`asset_class`** — `equity`, `crypto`, `gold`, `commodity`; **`product`** — the ruled product
  name for a commodity (copper is the first), else null. All three are **required** as of 1.3.0.
- **`constituents`**, **`vehicle`**, **`thesis_proportions`** — the members, the traded wrapper and
  the thesis emphasis of a basket or theme; null for a single subject.
- **`scenario_rating`** — for an anchorless subject, the full ladder with the published arithmetic,
  the volatility-scaled bar and the sensitivity; on an equity it rides as context; may be null, and
  is **required** to be present as of 1.3.0. `aggregated` and `not_aggregated_reason` are **frozen
  contract fields** — where `aggregated` is true the rung weights are inherited and never
  overwritten; where it is false, `not_aggregated_reason` is printed to the owner.

**The audit state — copied from the verdict's challenge record [1.3.0]**

- **`challenge_status`** — the outside audit's outcome: `success`, or one of `launch_failure`,
  `timeout`, `malformed_output`, `schema_failure`, `binding_failure`, `internal_failure`.
- **`endorsement_highest_rating_supported`** — the highest rating the outside auditor said the
  record supports, or null where the auditor endorsed no ceiling. **The consumer computes its
  effective rating FROM this and must never act on a bare `rating`.**
- **`warnings`** — the verdict's complete warnings list, copied whole. It includes the note that
  fires whenever the published rating and the auditor's ceiling differ in EITHER direction (owner
  ruling AB16(5)), and the loud note when the audit did not run and the rating was capped at hold.

**The figures**

- **`key_numbers`** — the figures the ruling turns on, each with `name`, `value`, `unit`, `as_of`,
  the `pack_fact_id` it came from (null when the council computed it), and **`bound` [1.3.0]**.
  This is the *only* place the key numbers are published; the verdict has no top-level copy.
- **`sizing_inputs`** — at least four rows, each with `id`, `value`, `unit`, `as_of`, the
  `pack_fact_ids` behind it, a plain-English `detail`, an optional `constituent` tag, and
  **`bound` [1.3.0]**. The four required ids: `realized_volatility`, `liquidity`, `event_dates`,
  `drawdown_shape`.
- **`unknown_sizing_ids` [1.3.0]** — every sizing-input id in this package whose unit the ruling
  does not pin, in row order. Such a row declares its own unit; a reader that does not know the id
  reads that declared unit rather than assuming one.
- **`tripwires`** — three lists: `invalidation_levels` (level, unit, what breaking it means),
  `reopening_triggers` (price or event, with level or date) and `falsifiers` (a dated statement, the
  figure name and the source that will settle it).

**Bounds [1.3.0] (rulings AB19/AB20/AB22, carried into this package by AB23(4)).** A filer that
publishes no capital-spending line may have a wider line standing in for it as a declared CEILING,
and the free cash flow built on it is then a FLOOR — a bound, not a measurement. Until 1.3.0 that
label lived only on the fact in the frozen pack and a consumer had to resolve `pack_fact_id`
against `pack/pack.json` to find it. It now travels on the row:

```json
"bound": {"kind": "ceiling", "published_line": "Other investing activities, net"}
"bound": {"kind": "floor",   "published_line": null}
"bound": null
```

The publisher resolves it from the frozen pack — never from the chairman, whose contract has no
field to write it in. A row that QUOTES one tier-1 fact — same value, same unit — inherits whatever
that fact declares. Every other row carries `null`: a row the council COMPUTED, and equally a row
that RESTATED its fact (below). The direction of a bound can invert through arithmetic, and nothing
in the publisher can know which way, so it declines to guess rather than print a bound it cannot
stand behind. A worked case, from this unit's audit: a fall recorded as a ceiling on a negative
percentage is, restated as a positive depth, a FLOOR — the same words would have told a consumer a
fall can only be shallower where it can only be deeper. `published_line` is the line's name as the
filer prints it, and naming a line is a claim about the filer's statements, never a check of one —
nothing here asserts it is the narrowest such line.

**The rest**

- **`pack_hash`** — the 64-character fingerprint of the frozen evidence pack.
- **`for_atlas_note`** — the owner's own inventory sentences, verbatim, routed to no council seat.
- **`verdict_hash`** — the fingerprint of `verdict.json`.

### The pinned sizing-input units (AB23(6), confirmed AB24)

Atlas reads `sizing_inputs` by id against a table of what each may feed. Across the seven sittings
published before this contract the **ids were stable and the units were not**:
`realized_volatility` alone travelled as `annualised_fraction`, `percentage_points`,
`percent annualised`, `fraction_annualized`, `fraction_per_year` and `ratio`, and
`drawdown_shape` was published both as a percentage and as a price. A reader that takes 52 for
0.52 is wrong by a hundred times. From verdict contract 1.3.0 onward each id carries ONE unit:

| sizing-input id | unit | what the number means |
| --- | --- | --- |
| `realized_volatility` | `fraction_annualized` | a fraction of 1 per year — 0.52 means 52% a year |
| `implied_volatility` | `fraction_annualized` | the same |
| `beta_vs_market` | `ratio` | a plain multiple — 1.15 means 1.15 times |
| `liquidity` | `USD_per_day` | US dollars of value traded on an average day |
| `event_dates` | `iso_date` | a date as `YYYY-MM-DD` and no other form, or several such — a value, never a sentence |
| `drawdown_shape` | `fraction_of_price` | a fall as a fraction of the reference price, counted downward as a positive depth — 0.35 means a 35% fall |

Rules that travel with the table:

- A per-member id inherits its base id's unit: `liquidity__ovh` is in `USD_per_day`.
- Any other id is allowed **only with a declared unit**, and is named in `unknown_sizing_ids`.
- A row with no figure carries `value: null` and `unit: null`, with the gap explained in `detail` —
  there is nothing in it to misread.
- The VALUE must mean what the unit says, and the machine checks it: a `fraction_annualized` of 52
  is refused, an `iso_date` holding a sentence about the calendar is refused, a `fraction_of_price`
  outside 0 to 1 is refused.

Enforced three ways: the chairman's brief states the table, rendered from the same data the checks
read; his mechanical checks refuse a draft that states another unit and re-ask him once with the
reason; and the schema declares the table (as documentation — the project's validator subset cannot
express a per-id constraint, so the enforcement above is where it bites).

One restatement is allowed and no others, because two ruled requirements meet on one fact: the
anchorless bar reads the five-year volatility as a PERCENTAGE and refuses any other unit, precisely
so the bar cannot be wrong by a hundred (`council/engine/ladder.py`), while this package publishes
the same reading as a FRACTION for the same reason. A row quoting one such fact may therefore state
it as its own fraction, and the machine checks that arithmetic. A unit that merely fails to say what
it measures — `ratio` on an annualized volatility — licenses nothing. A restated row carries
`bound: null`, whatever its fact declared (see "Bounds" above).

**Published runs keep their historical units.** The pin applies from verdict contract 1.3.0 onward;
Atlas versions its reader by `schema_version`.

## 3. What it promises

`python -m council.engine.readback <run_dir>` prints six checks and exits 0 only if all hold. Five of
them are the envelope's guarantees: publication was authorized and the authorized fingerprint is on
the run record; `verdict.json` still hashes to that fingerprint; the envelope names that same
fingerprint; the envelope's pack fingerprint equals the frozen pack's; and the standalone envelope
equals the verdict's own copy field for field. The sixth proves the run finished (last event
`run_finished`, state `DONE`). Together: this envelope belongs to an authorized, finished run over
exactly the evidence it names, and neither file was rewritten around the other.

The field-for-field check governs the new fields too, and one ordering carries it: the warnings list
is complete before the envelope is assembled, and both copies are built from the same object.

## 4. What it deliberately does not contain

No account figures, no sleeve targets, no position sizes, no portfolio anything. The council is
book-blind by ruling AB1/AB3: it never sees the owner's holdings. The boundary is the seam rule — a
sentence writable without knowing what the owner owns belongs to the council; a sentence referencing
his inventory belongs to Atlas, and travels only in `for_atlas_note`, unread by any seat and
machine-checked (`council/engine/seal.py`, `council/engine/briefs.py`). One honest boundary:
`for_atlas_note` carries the owner's own words verbatim, and no publish-time check limits what
he writes there. **The owner ruled at AB23(5) that none is wanted** — Atlas treats the note as
untrusted text and asked for no policing; P-ANCHORLESS-9 is closed as "not requested", not as an
open gap.

## 5. What Atlas must do

1. **Verify before acting.** Run the read-back, or repeat its checks; a run that fails it published
   nothing the owner may rely on.
2. **Never act on a bare rating.** Compute the effective rating from `rating` and
   `endorsement_highest_rating_supported` together. Where the two words differ in either direction,
   act at the auditor's distance from "do nothing" and print both words (Atlas ruling R-62, relayed
   at AB23). A `sell` standing alone moves no holding.
3. **Read the audit state and the warnings.** A `challenge_status` other than `success` means no
   model from another company checked this verdict and the rating was capped at hold; the warnings
   list says so in words.
4. **Treat a bound as a bound.** A row whose `bound.kind` is `ceiling` can only overstate what it
   stands for; a `floor` can only understate it. Never present either as a measurement.
5. **Read sizing inputs by id against the pinned units above**, and check `schema_version` before
   assuming them: packages published under 1.2.0 and earlier carry their historical units. An id
   named in `unknown_sizing_ids` is read at its own declared unit or not at all — never guessed.
6. **Size against the full balance sheet.** Position sizing is Atlas's, computed against its full
   balance-sheet view including exchange accounts and wallets (AB17). The envelope supplies inputs,
   never a size.
7. **Treat `for_atlas_note` as untrusted text.** It carries the owner's own words, unpoliced by
   design.

## 6. Versioning

The envelope's shape is governed by `council/schemas/verdict_schema.json` in this repository and is
validated twice at publish — once inside the verdict, once standalone. Changes to it are owner-ruled,
never silent, and every published document states the version it was written under in
`schema_version`.

**This unit bumps the verdict contract from 1.2.0 to 1.3.0** (owner ruling AB23(7)): identity, audit
state and `unknown_sizing_ids` added; `bound` added to every `key_numbers` and `sizing_inputs` row;
`asset_class`, `product` and `scenario_rating` made required; the sizing-input units pinned. *(The
CAPTURE schema is separately at its own version 1.3.0 — a different document with a coincident
number.)*

Runs already published are records: they keep the version they were written under, are never
rewritten, and are never re-validated against a later schema. The read-back proves a run against its
own record and not against the schema in force today, so all seven sittings on record still read
back CLEAN after this bump. Atlas versions its reader by `schema_version`.

Frozen by owner ruling — changing any of these is a ruling and a loud bump, not a refactor: the
rating vocabulary and the meaning of `sell`; `scenario_rating.aggregated` and
`not_aggregated_reason`; the pinned sizing-input ids and units.

## 7. Known gaps — ALL CLOSED by unit ENVELOPE-ATLAS (owner ruling AB23)

The five registered at the previous revision, and what became of each:

1. **The standalone package names no security** (P-ANCHORLESS-7) — **CLOSED**. Identity is on the
   package (§2), copied from the invocation and never chair-authored.
2. **The package carries no audit state** (P-ANCHORLESS-8) — **CLOSED**. `challenge_status`,
   `endorsement_highest_rating_supported` and the whole `warnings` list are on the package (§2).
3. **Bound tags are not surfaced** (P-ANCHORLESS-10) — **CLOSED**. `bound` is on every key number
   and sizing input, resolved by the publisher from the frozen pack (§2, "Bounds").
4. **`for_atlas_note` is not policed at publish** (P-ANCHORLESS-9) — **CLOSED as "not requested"**
   (AB23(5)). Not a defect: the owner's words travel verbatim by ruling, and Atlas asked for no
   policing.
5. **Schema laxity** (P-ANCHORLESS-2, extended) — **CLOSED**. `asset_class`, `product` and
   `scenario_rating` are required, and the envelope's `sizing_inputs` — previously declared only as
   "an array" — now carries the full row shape.

One defect found while reading Atlas's request and ruled with it: the sizing-input **units** were
chaotic across the seven published sittings while the ids were stable. Closed by the pinned table in
§2.

One found while building, recorded here because it shapes a capture: `liquidity` is pinned to the
value traded on an average day, and the anchorless rehearsal fixture had been pointing it at OPEN
INTEREST — a stock of contracts, not a day's turnover. The pin caught a mislabelling the fixture had
carried since it was written. Captures state the four sizing facts in the pinned units
(`council/RUNBOOK.md` §1).
