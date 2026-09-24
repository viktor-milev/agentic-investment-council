# council/CHECKS.md — the new battery (REBUILD-SPEC §13)

Run every command from the repository root. The exit code is the authority
(F4.1): 0 is green, anything else is red. `PYTHONIOENCODING=utf-8` on every
invocation (the console codepage otherwise mangles output on Windows).
`python` means YOUR Python 3 interpreter: on Windows it is `python`; on macOS use `python3.13`
(no bare `python` exists there — MAC-3). The seven suites below are the whole battery, on either
platform.

## The seven suites

```
python council/tests/test_foundations.py
python council/tests/test_evidence.py
python council/tests/test_engine.py
python council/tests/test_bridge.py
python council/tests/test_report.py
python council/tests/test_e2e_rehearsal.py
python council/tests/test_ledger.py
```

- **foundations** — canonical bytes and hashing, the schema validator, the
  contract schemas, the ruled floors data (including the asset-class anchor
  registry and the anchorless rating's own constants), and the split's
  language rule scanned over every file in the council tree.
- **evidence** — the provenance gate (declared arithmetic recomputed
  exactly, plus kind consistency and referential integrity for basket,
  theme and vehicle subjects), the byte-identical two-directory freeze,
  and the sufficiency gate's pass and refusal paths per kind — the
  per-constituent essential core, the ruled vehicle floor, and the
  empty-theme refuse-with-shopping-list — over invented fixture packs.
  Since UPGRADE-2 Phase A it also covers the BUSINESS FRAME and the
  outside auditor's reading of the evidence: a pack for a priced
  business must say what it is, how it earns, what is changing, and the
  three to five numbers that decide the question, each answered by a
  fact in the pack or declared an honest gap; a figure written into the
  frame's prose must be one the record carries, written exactly as the
  record writes it; a headline figure that has fallen must be read as
  by design, deterioration or mixed. Sufficiency refuses a sitting
  whose evidence no outside model checked, whose auditor's points went
  unanswered, whose audit record carries neither the one-time token
  that call was issued nor the hash of the evidence it was sent, and
  whose evidence moved after that call with nothing on record saying
  what moved. The one-page evidence brief is covered here too: every
  section present, every figure the exact string the capture recorded,
  and the page kept to one page without cutting through a number.
  Since ANCHORLESS it also covers sufficiency judged PER ASSET CLASS: the
  shape and the class must agree, a commodity names its product, and the
  crypto, gold and copper anchor sets pass on their own fixtures and refuse
  BY NAME when an anchor is pulled — including the cycle history, where the
  four families must cover the same cycles or the recovery durations go
  silently missing. Since UPGRADE-2 U3d it also covers the correction loop
  (a fact patched in place, its derived chain re-struck, the pack re-run at
  zero model cost, and a rebuilding correction refused until re-audited),
  the optional plain-English fact label, the period basis that keeps an
  average from being published as an annual figure, the peer comparability
  statement, and the full evidence document a reviewed sitting approves.
  Since UPGRADE-2 U4(a) it also covers the optional daily price series and
  its benchmark: a series refuses, in plain words, when its dates do not
  strictly increase, when a hole runs longer than five calendar days beyond
  the exchange holidays the floors declare, when its last bar is more than
  three exchange days old, when a close is zero, when it is too short with
  no declared gap, or when the benchmark is not the ruled one or does not
  span the subject's window; and every committed capture fixture is checked
  at the current contract. Since UPGRADE-2 U4(a2) it also covers the tape:
  the 25 figures computed from the series to the exact string (since
  U4(b), the three average prices among them), the freeze
  that appends them byte-identically twice, the gate that recomputes every
  one and refuses a tampered figure by name, and every series-less pack on
  record re-freezing to its own bytes.
- **engine** — the stepped host's state machine end to end: seat retries,
  the blind seal re-run, the reach scan, the chair's mechanical checks
  (kind-aware: one note per named constituent, one falsifier row per
  declared theme falsifier with its prior period quoted exactly), the
  kind-rendering briefs, the publisher's change appendix with the
  unendorsed-raise warning, the failed-audit degradation and the
  envelope's copied subject shape, token accounting, and the read-back
  verifier against a tampered file. Since ANCHORLESS it also covers the
  scenario-earned rating: the four bands and the horizon computed on frozen
  facts, the bar and its printed sensitivity, every way a ladder can fail to
  produce a rating honestly, the host's refusal of a chairman whose stated
  rating his own ladder does not earn, the five seats' distinct evidence
  emphases, the sealed words on the owner's own possession, and MAC-1 — the
  answer contract provably precedes the case file in every rendered brief.
  Since ENVELOPE-ATLAS it also covers the hand-off package standing alone
  (owner ruling AB23): its identity and audit state on both copies, the
  bound tag resolved from the frozen pack onto each key number and sizing
  row, the three newly required fields, the pinned sizing-input units with
  the one checked percent-to-fraction restatement, and read-back still
  CLEAN over every sitting on record after the version bump. Since
  UPGRADE-2 Phase A it also covers what every seat is told before the
  numbers: the business frame ahead of the fact table, what the outside
  auditor asked for and what the record answered, and what changed
  after it read the evidence — every word either model wrote travelling
  inside the quote fence, never in the case file's own voice. The
  host's side of the evidence stage is here as well: the mode chosen at
  the very start of a sitting, the approval a reviewed sitting cannot
  open without, and the capture stage's own minutes and tokens —
  including what the outside auditor cost, measured as the sum of every
  call the bridge recorded. Since UPGRADE-2 U3d it also covers the full
  evidence document a reviewed sitting cannot open without, the estimate
  flag on the capture stage's own figures, and the seat-cost measure —
  tokens per tool turn and brief bytes per seat — computed into the
  published record.
- **bridge** — the challenger command's exact flag surface, the stdin
  prompt, the isolated schema-only directory, every failure status, and a
  real tree-kill on timeout. Every test runs against a fake launcher: the
  suite makes NO paid calls. Since UPGRADE-2 Phase A it also covers the
  SECOND paid call — the audit of the evidence, made before any seat is
  paid — under the same discipline: the brief the auditor reads, the
  five kinds of finding it may return and nothing else, the one-time
  token and the hash of the evidence that call was given, one attempt
  logged per call so a re-dispatched audit can be added up, and the
  merge that writes the auditor's own words into the capture together
  with what the capture session answered and what moved afterwards.
  Since UPGRADE-2 U3d it also covers the per-pass archive — every audit
  pass kept whole so a re-dispatch never loses the first pass's
  dispositions — and the delta re-audit of a correction: a narrower
  brief carrying only the changed facts and the prior findings staged.
- **report** — the rendered page's sections, folding, warnings band, change
  appendix, number formatting (under AC16(1) the number DISPLAY inside seat and
  chairman prose may be respelt to the market form - value unchanged, every
  substitution logged), self-containedness, the dark default, and the kind sections:
  the constituent table, the theme falsifier block with its prior period
  and metric-identity line, the vehicle identity block, and the
  envelope's kind fields under the ruled emphasis label. Since ANCHORLESS it
  also covers the two-page decision front that now opens every report: its
  order before every appendix, the numbers the ruling turns on, the scenario
  ladder with its arithmetic quoted word for word, the bar and the printed
  sensitivity, the downside ladder, the dated calendar, what changes the
  rating, and the two-page budget measured on the rendered text. Since
  UPGRADE-2 Phase A it also covers the evidence stage on the page: what
  the outside auditor asked for, open on the front when it called
  anything blocking; what changed after it read the evidence, open when
  a change touches a number the decision turns on; whether a person
  reviewed the evidence before the council sat or the sitting ran
  unattended; and the sitting's clock, read from the moment the FIRST
  rendering recorded — so the same run reprints as the same page, today
  and in a year. Since UPGRADE-2 U3d it also covers the word "estimated"
  printed beside a capture figure that is one, and the seat-cost appendix
  — tokens per tool turn and brief bytes per seat, the input and output
  columns empty with the note that says the harness cannot fill them.
- **e2e rehearsal** — invented captures through the REAL chain: gate →
  freeze → sufficiency → host → nine canned seats → a canned challenge
  result in the bridge's own shape → publish → read-back → rendered report
  — the single name, a canned basket, a canned theme, an ANCHORLESS subject
  whose published rating is BUY rather than hold, the same subject with the
  chairman's rating raised one band above what his own ladder earns (refused,
  and nothing publishes), and the empty-theme refusal with its shopping-list
  note. Zero model calls.
- **ledger** (UPGRADE-2 U7) — the track record. The row built from a verdict
  of every schema version on record and validated; the horizons' due dates
  counted in trading days; the anchorless price read from the scenario
  reference. A real publish appends one append-only row whose hash the run
  record carries, and read-back verifies it, refuses a row altered after the
  fact, and refuses a missing ledger file. The scoring rules read from data
  (owner ruling AC7): right and wrong per rating word at 252 trading days,
  excess return against the benchmark or the subject's own return where the
  class has none, the mispricing read scored by direction, falsifiers tallied
  for and against, tripwires and triggers as fired or not — with a moved
  threshold flipping an outcome to prove the rules are data. The scorecard
  renders offline and refuses the tokens-against-return correlation below
  twenty scored rows, showing it with its caveat at twenty. Zero model calls;
  the scoring script never fetches; invented fixtures only.

## The old stack's eleven checks — RETIRED (AB24) and DELETED (AB25(3), 2026-09-06)

Historical note only: the frozen PowerShell stack and its eleven checks were retired when Atlas
integrated the council (the AB1 trigger), then deleted from the working tree in one audited commit.
Nothing above depends on them; git history keeps the code and the commands.
