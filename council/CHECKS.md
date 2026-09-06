# council/CHECKS.md — the new battery (REBUILD-SPEC §13)

Run every command from the repository root. The exit code is the authority
(F4.1): 0 is green, anything else is red. `PYTHONIOENCODING=utf-8` on every
invocation (the console codepage otherwise mangles output on Windows).
`python` means YOUR Python 3 interpreter: on Windows it is `python`; on macOS use `python3.13`
(no bare `python` exists there — MAC-3). The old stack's eleven checks are Windows-only by design
(seven are PowerShell); on macOS they are absent along with the frozen stack they test, and the
PowerShell invocation-pin hook registered in `.claude/settings.json` is likewise inert there —
inert AND guarding nothing, since the frozen stack cannot run on macOS at all (MAC-4, adjudicated:
documented rather than ported; the pin dies with the frozen stack at its AB1 retirement).

## The six suites

```
python council/tests/test_foundations.py
python council/tests/test_evidence.py
python council/tests/test_engine.py
python council/tests/test_bridge.py
python council/tests/test_report.py
python council/tests/test_e2e_rehearsal.py
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
  Since ANCHORLESS it also covers sufficiency judged PER ASSET CLASS: the
  shape and the class must agree, a commodity names its product, and the
  crypto, gold and copper anchor sets pass on their own fixtures and refuse
  BY NAME when an anchor is pulled — including the cycle history, where the
  four families must cover the same cycles or the recovery durations go
  silently missing.
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
  CLEAN over every sitting on record after the version bump.
- **bridge** — the challenger command's exact flag surface, the stdin
  prompt, the isolated schema-only directory, every failure status, and a
  real tree-kill on timeout. Every test runs against a fake launcher: the
  suite makes NO paid calls.
- **report** — the rendered page's sections, folding, warnings band, change
  appendix, number formatting (reading precision only - seat prose is never
  edited), self-containedness, the dark default, and the kind sections:
  the constituent table, the theme falsifier block with its prior period
  and metric-identity line, the vehicle identity block, and the
  envelope's kind fields under the ruled emphasis label. Since ANCHORLESS it
  also covers the two-page decision front that now opens every report: its
  order before every appendix, the numbers the ruling turns on, the scenario
  ladder with its arithmetic quoted word for word, the bar and the printed
  sensitivity, the downside ladder, the dated calendar, what changes the
  rating, and the two-page budget measured on the rendered text.
- **e2e rehearsal** — invented captures through the REAL chain: gate →
  freeze → sufficiency → host → nine canned seats → a canned challenge
  result in the bridge's own shape → publish → read-back → rendered report
  — the single name, a canned basket, a canned theme, an ANCHORLESS subject
  whose published rating is BUY rather than hold, the same subject with the
  chairman's rating raised one band above what his own ladder earns (refused,
  and nothing publishes), and the empty-theme refusal with its shopping-list
  note. Zero model calls.

## The old stack's eleven checks — RETIRED (ruling AB24, 2026-09-06)

The frozen PowerShell stack is retired: Atlas integrated the council and the AB1 trigger fired.
These eleven are no longer run at any gate and no longer need to be green; they are listed only
so the record stays legible until the owner rules on deleting the stack from the tree.

```
python schemas/verdict-schema.Tests.py
powershell -ExecutionPolicy Bypass -File control/control-flow.Tests.ps1
powershell -ExecutionPolicy Bypass -File bridge/bridge.Tests.ps1
powershell -ExecutionPolicy Bypass -File control/diff/differential.Tests.ps1
powershell -ExecutionPolicy Bypass -File control/store/run-store.Tests.ps1
powershell -ExecutionPolicy Bypass -File control/store/run-store-ingress.Tests.ps1
powershell -ExecutionPolicy Bypass -File tools/steward/steward.Tests.ps1
powershell -ExecutionPolicy Bypass -File hooks/hooks.Tests.ps1
powershell -ExecutionPolicy Bypass -File workflow/controller.Tests.ps1
powershell -ExecutionPolicy Bypass -File workflow/build-controller.ps1 -Check
python tools/report/report.Tests.py
```
