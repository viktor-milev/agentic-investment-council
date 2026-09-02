# The Atlas envelope — the hand-off contract

*Commissioned by the architect under owner ruling AB17 (2026-09-02). Ground truth: the producer is
`council/engine/publisher.py`, the declared shape is `council/schemas/verdict_schema.json`
(`atlas_envelope`), the checker is `council/engine/readback.py`, and the worked example is
`council/runs/council-btc-2026-09-01/atlas-envelope.json` — the live Bitcoin SELL.*

## 1. What the package is

Every published run writes two files: `verdict.json`, the full ruling, and `atlas-envelope.json`,
the machine hand-off. The envelope is a standalone JSON file, and the identical content is
duplicated field for field inside the verdict under `atlas_envelope`. Only one field differs by
construction: a document cannot carry its own hash, so `verdict_hash` is `null` in the verdict's
copy and carries the real value in the standalone file (`publisher.py`, lines 404–447).

## 2. What it contains

Fourteen fields, all of them declared in the schema (`additionalProperties: false` — nothing else
can appear):

- **`rating`** — one of the owner's five words: `strong_buy`, `buy`, `hold`, `sell`, `monitor` (AB3).
- **`subject_kind`** — `single_stock`, `etf`, `bitcoin`, `gold`, `commodity`, `theme` or `basket`;
  **`asset_class`** — `equity`, `crypto`, `gold`, `commodity`; **`product`** — the ruled product name
  for a commodity (copper is the first), else null. Copied from the invocation, never chair-authored.
- **`constituents`**, **`vehicle`**, **`thesis_proportions`** — the members, the traded wrapper and
  the thesis emphasis of a basket or theme; null for a single subject.
- **`key_numbers`** — the figures the ruling turns on, each with `name`, `value`, `unit`, `as_of` and
  the `pack_fact_id` it came from (null when the council computed it). This is the *only* place the
  key numbers are published; the verdict has no top-level copy.
- **`tripwires`** — three lists: `invalidation_levels` (level, unit, what breaking it means),
  `reopening_triggers` (price or event, with level or date) and `falsifiers` (a dated statement, the
  figure name and the source that will settle it).
- **`sizing_inputs`** — at least four rows, each with `id`, `value`, `unit`, `as_of`, the
  `pack_fact_ids` behind it and a plain-English `detail`. The Bitcoin run's four ids:
  `realized_volatility`, `liquidity`, `event_dates`, `drawdown_shape`.
- **`scenario_rating`** — for an anchorless subject, the full ladder with the published arithmetic,
  the volatility-scaled bar and the sensitivity; on an equity it rides as context; may be null.
- **`pack_hash`** — the 64-character fingerprint of the frozen evidence pack.
- **`for_atlas_note`** — the owner's own inventory sentences, verbatim, routed to no council seat.
- **`verdict_hash`** — the fingerprint of `verdict.json`.

## 3. What it promises

`python -m council.engine.readback <run_dir>` prints six checks and exits 0 only if all hold. Five of
them are the envelope's guarantees: publication was authorized and the authorized fingerprint is on
the run record; `verdict.json` still hashes to that fingerprint; the envelope names that same
fingerprint; the envelope's pack fingerprint equals the frozen pack's; and the standalone envelope
equals the verdict's own copy field for field. The sixth proves the run finished (last event
`run_finished`, state `DONE`). Together: this envelope belongs to an authorized, finished run over
exactly the evidence it names, and neither file was rewritten around the other.

## 4. What it deliberately does not contain

No account figures, no sleeve targets, no position sizes, no portfolio anything. The council is
book-blind by ruling AB1/AB3: it never sees the owner's holdings. The boundary is the seam rule — a
sentence writable without knowing what the owner owns belongs to the council; a sentence referencing
his inventory belongs to Atlas, and travels only in `for_atlas_note`, unread by any seat and
machine-checked (`council/engine/seal.py`, `council/engine/briefs.py`). One honest boundary:
`for_atlas_note` carries the owner's own words verbatim, and no publish-time check limits what
he writes there — the machine keeps inventory language away from the council's seats; it does
not police the note itself (registered as P-ANCHORLESS-9, pending the Atlas integration charge).

## 5. What Atlas must do

1. **Verify before acting.** Run the read-back, or repeat its checks; a run that fails it published
   nothing the owner may rely on.
2. **Size against the full balance sheet.** Position sizing is Atlas's, computed against its full
   balance-sheet view including exchange accounts and wallets (AB17). The envelope supplies inputs,
   never a size.
3. **Report the first acceptance.** Atlas's first accepted translation of a live verdict into a
   portfolio instruction is the ruled trigger that retires the frozen PowerShell stack (AB1). It must
   be reported to the owner and the architect when it happens.

## 6. Versioning

The envelope's shape is governed by `council/schemas/verdict_schema.json` in this repository and is
validated twice at publish — once inside the verdict, once standalone. Changes to it are owner-ruled,
never silent.
