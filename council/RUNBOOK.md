# council/RUNBOOK.md — hosting a sitting on the Python council

The whole pipeline (REBUILD-SPEC §4), operated from one interactive session
on this machine. Everything below runs from the repository root with
`PYTHONIOENCODING=utf-8`. The budgets are acceptance criteria (AB6): wall
clock at most 1.5 hours capture through rendered report, at most 1.8M
Anthropic tokens (aim 1.5M), challenger at most 50% of the Anthropic cost.

## 1. Evidence (session work — the scripts never fetch anything)

Derive what THIS question needs: the four valuation tests for a priced
asset (profit growth · free cash flow · rating against own history or
peers · earnings/cash yield against the risk-free rate) plus whatever the
owner's thesis turns on, on top of the ruled floors in
`council/floors/floors.json`. Gather live: filings WITH their prior-year
comparatives, guidance, the dated events calendar, the risk-free rate,
market data from the broker, short interest where the class has it.

Write one capture JSON per `council/schemas/capture_schema.json`. The
rules that matter most in practice:

- The broker is a MARKET-DATA source only. Never call the two calls that
  read the owner's book; the gate refuses sources naming them.
- Every figure is the exact string observed — never round, never reformat.
- A derived figure declares `derived.operation` + `operands`; the gate
  recomputes it exactly and the freeze generates its equation sentence.
- A prior-period comparative is dated by the CURRENT filing that
  republishes it (its own fact family, longer freshness rule).
- A shut market is legal and disclosed: `market_state.state = "closed"`
  plus a plain `disclosure` sentence — it reaches the seats.
- Every Tier-2 passage states its figures literally in its own text. The
  `figures` list is a HAND-WRITTEN, curated assertion of the figures that matter, written in the
  same format as the passage prose (grouped thousands included) — never a mechanical dump of every
  numeral in the text (MAC-5).
- Write the sufficiency checklist INTO the capture: every requirement
  (the four tests + thesis-specific) mapped to the fact ids that answer it. The four
  canonical tests carry EXACTLY these ids — `profit_growth`, `free_cash_flow`,
  `rating_vs_history_or_peers`, `yield_vs_risk_free` — the gate refuses any other spelling (MAC-2).
- **A filer that does not report capital spending at all (rulings AB19 and
  AB20).** Some companies never publish capital spending as a line of its own
  — Coinbase is the first the council met. The sitting does NOT refuse.
  Capture `capital_expenditure_q` and its prior-year pair as a DERIVED ceiling
  built from the NARROWEST published line that contains capital spending,
  struck identically in both years out of the SAME line, and **tag each of the
  four figures** — the two ceilings and the two free-cash-flow figures built
  on them:

  ```json
  "capital_expenditure_q": ... "bound": {"kind": "ceiling",
                                         "published_line": "Other investing activities, net"}
  "free_cash_flow_q":      ... "bound": {"kind": "floor", "published_line": null}
  ```

  The `published_line` is the line's name **as the filer prints it**, written
  identically on both years — case and spacing are ignored, anything else is
  a different line and the gate refuses. Declare the gap `absent_by_design`
  alongside; its `fact_class` must read exactly **`a separately reported
  capital-expenditure line`** — that phrase is what arms the check. Tag
  without the gap row, or declare the gap without the tags, and the sitting
  refuses either way: the two travel together.

  The tag is what the case file renders for every seat, in a sentence the
  machine generates from it — you no longer have to work the words into the
  source sentence yourself, and a differently-worded source is no longer
  refused. Where no published line contains the item, refuse as before. This
  licenses no substitute against any other must-have.

  **Which line is the NARROWEST published one containing capital spending is
  not something the machine can see, and the tag does not change that.**
  Naming a line is a claim about the filer's statements, never a check of one;
  the gate can only compare your two claims to each other. That judgement
  stays yours.

  Worked example: `council/runs/council-coin-2026-09-04/evidence/capture.json`
  — copy its arithmetic and its source sentences, but note that it was
  written to the previous contract (`capture_version` 1.2.0) and carries no
  tags, because runs on record are never rewritten. Your capture is 1.3.0 and
  needs them. The migration is set out in
  `council/tests/test_evidence.py::to_contract_1_3_0`.
- `sec.gov`'s archive refuses automated fetches; use `data.sec.gov` or the
  issuer's investor-relations copies.

Capturing the two new subject kinds, and the thematic vehicle:

- **A basket** — 2 to 8 constituents, each with its own ticker. Every
  named member's own last price and market value are tier-1 facts with
  the id suffix `__<ticker>` (the ticker lowercased). Write ONE
  `constituent_essential` checklist row per member: the one or two
  metrics the thesis load-bears on for that name, answered by its facts.
  `thesis_proportions` are optional and always the IDEA's emphasis —
  a statement about the thesis, never an instruction to any portfolio.
- **A theme** — the subject's theme block carries the thesis and at
  least one measurable falsifier. A `level` falsifier names its fact AND
  the prior-period fact — a falsifier that cannot fire is not a
  falsifier. The expression is a provisional universe of 2 to 8 named
  instruments OR one implementation vehicle, never both; universe
  members carry the same per-member facts and checklist rows a basket's
  do. An unsittable theme refuses at the sufficiency gate with the
  shopping list — what would make the question sittable — at capture
  cost; that note is the product.
- **A thematic vehicle** — kind `etf` plus the theme block. The fund's
  own published disclosure is the universe: capture the ruled vehicle
  floor (price, NAV per share, premium/discount, the holdings picture —
  the top holdings and each holding's share of the fund — expense
  ratio, the 30-day median bid-ask spread) and the theme's falsifier
  through the vehicle. The holdings picture is facts, never a
  per-holding analysis.

REG-18, deferred BY THE OWNER to the first real theme sitting: that
sitting's record must put to the owner, in plain words with the
sitting's own concrete case, whether a falsifier's prior-period
comparison measures the SAME metric or only the same unit. The
verdict's `metric_identity_assumed` field is where the sitting's
assumption is read from.

Capturing an asset with NO EARNINGS (ANCHORLESS-SPEC, owner rulings
AB13/AB15). The subject declares an `asset_class` beside its kind:
`equity`, `crypto`, `gold` or `commodity`. The class decides which
must-haves the sitting is judged against and nothing else; the kind
still decides the shape. Bullion is kind `gold`, a metal contract is
kind `commodity` and names its `product` (copper is the first ruled
product), a coin is kind `bitcoin`, and a fund holding any of them
stays kind `etf` with the class of what it wraps.

- **The anchor names are in the data, not in anyone's memory.** Read
  `council/floors/floors.json` → `asset_classes` before writing the
  capture: every required fact id is listed there with why it is
  required and where it was last found live. The sufficiency refusal
  prints the same three things for anything missing, so a first pass
  that refuses costs a capture, never a council.
- **Two of those anchors are the RATING's own inputs**, not context: a
  `risk_free_rate*` fact and `realized_volatility_5y`, measured over
  five years. The bar the rating must clear is cash plus a ruled
  multiple of that volatility, so a pack without them can produce no
  rating at all.
- **The dated calendar is required.** Every calendar fact's id begins
  `calendar_`, its VALUE is the event's date, and its SOURCE sentence
  should say plainly what the event is — that sentence is what the
  report's front page prints beside the date.
- **Cycle history carries its DURATIONS.** For each prior cycle, four
  facts sharing one suffix: `cycle_peak_<cycle>`,
  `cycle_trough_<cycle>`, `cycle_drawdown_<cycle>` and
  `cycle_recovery_months_<cycle>`. The gate refuses a family answered
  for some cycles and silent for others — the cold read called the
  trough-to-recovery TIME the single most decision-relevant gap.
- **The seats and the chairman each build a scenario ladder.** Nothing
  in the capture does; the ladder is judgment, and it is the seats'.
  The chairman's ladder names three frozen fact ids — the price it is
  measured against, the five-year volatility and the cash rate — and
  the machine computes the expected result, the bar, the band and the
  printed sensitivity from them. A rating the ladder does not earn is
  refused, so the chairman decides the ladder and the rating follows.

Source notes proven at live sittings (data, not rules — check them at the
sitting before relying on them):

- Apple's investor-relations copies of the 10-Q are served from
  `s2.q4cdn.com` (the IR page links there).
- Some IR-hosted PDFs decode with a +29 glyph shift — every extracted
  character sits 29 code points high; shift back before reading figures,
  and verify a known word decodes correctly first.
- Apple newsroom PDFs live under predictable `/newsroom/pdfs/` paths named
  by the release.
- Apple publishes no three-month cash-flow statement: a single quarter is
  always the difference of two cumulative statements — strike both years
  identically and record the operands, so the gate can recompute the
  arithmetic.

## 2. Gate, freeze, sufficiency (cheap, before any seat is paid)

```
python -m council.evidence.gate <capture.json>
python -m council.evidence.freeze <capture.json> <out_a> <out_b>
python -m council.evidence.sufficiency <out_a>/pack.json --out <out_a>/sufficiency-result.json
```

Freeze builds twice and must report byte-identical with one hash (recorded
in `<out_a>/freeze-record.json`). A sufficiency refusal (exit 3) is itself
the product: what is missing, why, where it likely lives — fix the capture
and repeat. No seat is paid before it passes.

## 3. The council (the stepped host + your dispatches)

```
python -m council.engine.host init --runs-root <dir> --run-id <id> --pack <pack.json> --pack-sha256 <hash> --sufficiency <sufficiency-result.json> --question-file <question.txt> --subject-json <subject.json>
python -m council.engine.host step <run_dir>
python -m council.engine.host status <run_dir>
```

The host is never a long-running process: each `step` advances as far as
the files on disk allow, then exits — there is nothing for a timeout to
kill. Loop until DONE:

1. `step`, then `status` — it lists the pending seat requests.
2. For EVERY pending request, dispatch one isolated subagent whose whole
   task is: Read the one brief file, Write the one answer file, use no
   other tool of any kind. Tell each seat ON DISPATCH that its brief may exceed a single Read and
   MUST be paged with offset/limit to the very end — the answer contract sits at the end, and a
   seat that stops early answers against a contract it never read (MAC-1). Paging its OWN brief is
   compliant, and the usage sidecar's tool count records it. Dispatch all five advisors in parallel — that
   is what makes the wall-clock budget reachable. A seat that corrects
   its OWN answer file with a further Write or an Edit before finishing
   is a recorded deviation, not a failure: the usage sidecar's tool
   count keeps it visible and the reach and seal checks still govern
   the content. Any touch of any OTHER file or any other tool
   disqualifies the seat. When a seat must correct itself, prefer
   telling it to rewrite the whole file.
3. After each answer, write the usage sidecar
   `rpc/NNN-usage.json`: `{"tokens": .., "tool_calls": .., "minutes": ..,
   "model": ".."}` from the dispatch's own accounting. This is how
   per-seat isolation and cost are measured into the run record.
4. `step` again. Malformed answers are re-asked once with the reason; a
   second failure fails the run. A failed run publishes nothing and is
   never resumed — start a fresh run id (M5).
5. When the chair's draft is in, `step` writes the challenge request and
   prints the bridge command:

```
python -m council.bridge.codex_bridge challenge <run_dir>
```

   Run it yourself (detached or in the background if you prefer — its
   result lands durably in `challenge/result.json` either way). It smokes
   the model first and refuses the paid call on a failed smoke.
6. Keep stepping: chair resolve, then publish happen on the following
   steps. On a failed challenge the host skips resolve and publishes
   degraded — nothing stronger than hold, with the warning on the page.

## 4. Read-back and the report

```
python -m council.engine.readback <run_dir>
python -m council.report.render_report <run_dir>
```

Read-back must print CLEAN and exit 0: the published verdict hashes to the
recorded value, the run finished, and the Atlas envelope carries the same
hashes. The report is one self-contained file at `<run_dir>/report.html`.

## 5. The record

The run directory is the archive — every brief, answer, the pack, the
challenge exchange, the run record, the verdict, the envelope, the page.
It is committed whole under `council/runs/` and never edited afterward.
