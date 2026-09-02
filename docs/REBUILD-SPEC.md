# REBUILD SPEC — the split-mode council in Python

**Status: FROZEN (Architect v4, 2026-08-30, under owner ruling AB8).** This document is the
builder's whole authority for scope. Nothing may be added to it, reinterpreted, or "improved"
during the build. Anything unclear, anything that seems to need a decision, anything this spec
does not cover: STOP that part, message the architect session (`Agentic Council Architect v4`
via SendMessage), and continue on other parts. The builder decides mechanism everywhere
(F4.2); the builder decides meaning nowhere.

## 0. What is being built, in one paragraph

A clean Python implementation of the investment council in its ruled post-demolition shape: a
book-blind opinion engine that takes one investment question, gathers and freezes the evidence
that THIS question needs, checks the evidence is sufficient BEFORE any money is spent on
deliberation, convenes five parallel advisors and one blind reviewer over the one frozen pack,
synthesizes a chairman's verdict on the owner's five-word scale, has it audited once by a
cross-model challenger, and publishes the chairman's final document with every post-audit
change labeled — a verdict with a priced view, tripwires, and a machine-readable hand-off
envelope for Atlas. It must run end to end in at most 1.5 hours and 1.8 million Anthropic
tokens. It replaces the PowerShell stack, which is frozen, not deleted.

## 1. Authorities, in order

1. `docs/OWNER-RULINGS.md` — §AB governs this build; §X (Python), §Y (report design), §Z
   (writing rules) bind directly. Where an older ruling conflicts with §AB, §AB wins.
2. This spec.
3. `CLAUDE.md` — the communication contract, the checkpoint format, the audit operating block.
The old stack's other contract documents (ARCHITECTURE.md, CONTROLLER-REQUIREMENTS.md) are
REFERENCE ONLY — consult them for how a proven mechanism worked, never as obligations.

## 2. Product definition — the split (AB1, AB3)

- The council knows NOTHING about the owner's holdings. The words held/unheld, position,
  sleeve, weight, account, net liquidation value do not exist in its vocabulary, its capture,
  its schema, or its prompts. The broker is a MARKET-DATA source only: no positions call, no
  account-summary call, ever.
- One action vocabulary, the owner's scale: `strong_buy` / `buy` / `hold` / `sell` /
  `monitor`. `monitor` means a watch-state — "no view yet; watch these named triggers" — not a
  fifth opinion.
- The seam rule, applied at FRAME: a sentence writable without knowing what the owner holds
  belongs to the council; a sentence referencing his inventory belongs to Atlas. If the
  owner's question mixes thesis and position strategy, the FRAME stage extracts the thesis
  half for the council and records the position half verbatim in a clearly labeled
  `for_atlas` note that travels to no seat and appears in the verdict's Atlas envelope
  untouched.

## 3. Repository layout and runtime

- Everything new lives under a new top-level directory **`council/`** in this repository.
  NOTHING outside `council/` may be created or modified except: the BUILD-LOG entry, the one
  allowlist addition in `.audit/audit.yaml` (§14), and the send-off's own branch bookkeeping.
  The old stack (schemas/, control/, workflow/, bridge/, hooks/, tools/) is untouched — its
  eleven checks must still be green at the build's close, proven by execution.
- Python 3.14, **standard library only** for everything that runs a council (the renderer
  precedent). The codex CLI is invoked via subprocess. No pip dependencies, no Node, no
  PowerShell (§X — absolute here; there is no legacy-file exception in a greenfield tree).
- OS-agnostic from the first line: no Windows-only paths, shell=True tricks, or CRLF
  assumptions. This IS the cross-platform rewrite (AB8); it must be plausible on macOS even
  though it is verified on Windows.
- Live research (the evidence stage) is SESSION work done with the session's tools (broker
  MCP market-data calls, web reads), writing artifacts that `council/` scripts then validate,
  freeze, and gate. Scripts never fetch the web themselves.

## 4. The pipeline

```
EVIDENCE (session research → capture)          — §5
  → GATE (provenance validation, script)       — §5
  → FREEZE (twice, byte-identical, script)     — §5
  → SUFFICIENCY (script; refuses cheaply)      — §5
  → FRAME (question + seam split)              — §2, §6
  → ADVISORS ×5 (parallel, tool-less)          — §6
  → REVIEW ×1 (blind, includes synopsis)       — §6
  → CHAIR SYNTHESIS                            — §6
  → CHALLENGE ×1 (gpt-5.6-sol, full case file) — §7
  → CHAIR RESOLVE (every finding by name)      — §7
  → PUBLISH (final doc + change appendix)      — §7, §8
  → READ-BACK (hash + finished-state proof)    — §10
  → REPORT (HTML)                              — §9
```

A host script under `council/` drives this as a file-exchange protocol with the hosting
session (the proven rpc pattern: the host writes one request + one prompt file per seat, the
session answers each by spawning one isolated subagent that Reads its one prompt and Writes
its one answer, no other tools). The five advisor requests are written AT ONCE and may be
answered in any order — parallel dispatch is what makes the 1.5h cap reachable. Per-seat
retry on malformed answers (bounded, one re-ask with the reason).

## 5. The evidence stage (AB2) — the rebuilt supply line

**Mandate.** For each question, the evidence session derives what facts THIS question needs —
starting from the four canonical valuation tests for a priced asset (profit growth · free
cash flow · rating against the subject's own history or peers · earnings/cash yield against
the risk-free rate) plus whatever the owner's stated thesis turns on — and gathers them live:
filings WITH their prior-year comparatives, management guidance, the dated events calendar,
the risk-free rate, market data from the broker, short interest where the class has it,
volatility. The ruled per-name and per-class cores in Appendix A are FLOORS: always present
for those subjects, never the ceiling.

**Provenance (unchanged discipline — this is what the cold audit called the best-sourced
evidence it had seen).** Every Tier-1 fact carries: stable id, value, unit, as-of date, named
source, the arithmetic written out when derived, and a freshness rule. Every Tier-2 passage
states its figures literally in its text and names its source. Two freshness-family
obligations from the diagnostic: (DIAG-1) a prior-period comparative is dated by the CURRENT
filing that republishes it, not by the period it describes — a current filing's year-ago
column is fresh evidence; (DIAG-2) market-shut captures are legal and disclosed — the pack
states the price's age and why, and the disclosure reaches the seats.

**Gate and freeze.** A `council/` script validates the capture (complete provenance, ids,
units, dates, freshness rules, figures-literal-in-text) and refuses with plain reasons. The
accepted capture is frozen into a pack; built twice into separate directories; the two builds
must be byte-identical and the hash is recorded.

**The sufficiency gate — the stage that makes the AAPL failure structurally impossible.** The
evidence stage writes a sufficiency checklist INTO the pack: each derived requirement (the
four tests + thesis-specific facts) mapped to the pack facts that answer it. A script then
verifies every checklist item resolves to present, in-rule facts. **Failure refuses the run
BEFORE any seat is paid**, with a plain-English list of what is missing and where it likely
lives — that refusal message is itself a product (cost: the capture, ~half an hour; never
three hours of seats). A genuinely unavailable fact class may be declared as a gap only with
a stated reason and the named test it weakens.

## 6. The seats (AB5) — five advisors, one reviewer, one chair

- **Isolation is kept deliberately** (both audits: keep the one-frozen-baseline property, fix
  the food). Every seat is tool-less: one Read of its own prompt file, one Write of its own
  answer file, nothing else. Tool counts per seat are recorded; the two source vocabularies
  that would mark a reach outside the pack must read zero.
- **Five advisors** with the established orthogonal lenses (bear, bull, base-rate skeptic,
  market-structure, risk — risk here means the ASSET's risk: drawdown shape, volatility
  regime, gap behavior, liquidity; never portfolio risk). Dispatched in parallel.
- **One blind reviewer** replaces the five (AB5): reads all five advisor answers under an
  anonymized mapping (the blind draw is kept and recorded; a seat that self-identifies or
  identifies another is re-run — the proven seal check stays), and produces in ONE answer:
  the cross-examination (strongest falsifiable claim, blind spots, what all five missed) and
  the synopsis (≤180 words). The reviewer also polices ruling Z's writing rules by name.
- **The chairman** synthesizes over the pack, the advisors, the review, and the owner's
  verbatim question; drafts the full verdict (§8). After the challenge he resolves every
  finding by name (addressed / adjudicated / overruled) and issues his FINAL document.
- **Prompt economics are a design obligation, not an afterthought:** the measured killer was
  the same case file duplicated per seat (reviewer briefs alone were 37% of all prompt bytes
  on the diagnostic). Briefs share one canonically rendered case file; a seat receives only
  what its role needs; total prompt bytes per run is recorded in the run record. Budgets in
  §11 are the binding test.
- **Ruling Z's writing rules** (case terms explained once, uncommon acronyms spelled out,
  CIO-suitable language, ~25-word sentences, the CLAUDE.md tone) are a compact block in every
  seat brief — reuse the ruled wording from the old briefs, adapted only where the seat
  structure changed.
- Models: seats and chair inherit the hosting session's model and it is recorded per seat in
  the run record. The challenger model is requested explicitly and recorded.

## 7. The challenge round (AB4) — one cycle, transparency instead of freeze

- **One paid challenge cycle by default.** The full unredacted case file goes to
  `gpt-5.6-sol` through a Python codex-CLI bridge (proven flag surface: `exec --model -c
  --sandbox read-only --skip-git-repo-check --ephemeral --ignore-user-config -C
  --output-schema --json -o`; prompts >32KB via stdin; one unpaid smoke test precedes every
  paid call; structured findings against a JSON schema).
- **The challenger's brief is aimed at investment reasoning:** is the thesis judged right AT
  THIS PRICE — unsupported claims, unearned or under-rated conviction, blind spots, what
  would change the answer. It is explicitly told it is NOT a compliance auditor and NOT to
  audit the machinery. The endorsement channel stays: it may issue a typed endorsement naming
  the highest rating it would support.
- **Publication is the chairman's FINAL document.** A `council/` publisher diffs the final
  document against the challenged draft, field by field, and writes a **change appendix** —
  machine-readable in the verdict, human-readable in the report — listing every changed field
  with before and after. Special labels: a rating RAISED beyond the challenged draft without
  a challenger endorsement publishes with a prominent warning in both verdict and report
  ("the outside auditor did not see this rating"); an endorsed raise is labeled as endorsed.
  There is no refusal path on content and no second paid cycle; the only publication refusals
  are mechanical (schema-invalid, hash mismatch, unfinished run).
- Challenge failure (bridge error, no answer) publishes nothing stronger than `hold` and the
  report says loudly that the outside audit did not run (the spirit of the old degradation
  rules, one sentence, no cap machinery).

## 8. The verdict contract

One JSON schema, fresh versioning starting at 1.0.0, under `council/schemas/`. Contents:

- subject (instrument identity), the owner's question VERBATIM, the frame (thesis half /
  `for_atlas` half), classification of what was asked.
- **rating** (the five-word scale) + the chairman's conviction rationale.
- **mispricing read** (cheap / fair / rich / no-view, with magnitude and the arithmetic in
  words — the diagnostic's "roughly 258 against the 320.13 asked" is the standard to meet).
- **tripwires**: invalidation level(s), reopening triggers (price and event), and at least
  one falsifier scoreable against a named published figure on a named date.
- **stock-level sizing inputs** for Atlas: realized volatility, liquidity, event dates,
  drawdown shape — facts about the ASSET that a sizing engine needs (never a size).
- evidence dependencies: the pack facts the ruling rests on, by id.
- the challenge record: findings, dispositions by name, the endorsement if any, and the
  post-audit **change appendix** (§7).
- the Atlas envelope: the machine hand-off (rating, key numbers, tripwires, sizing inputs,
  `for_atlas` note, pack hash, verdict hash) — the founding seam, now filled.
- provenance: models per seat, pack hash, run id, schema version, timestamps.
- **Banned everywhere in the schema:** account figures, sleeve targets, holdings, weights.

## 9. The report

- Reuse and adapt the existing Python renderer into `council/report/` (same Slate & Ember
  design language, ruling Y: one self-contained file, dark default with light toggle, pinned
  nav icon with hover dropdown, sections opening/folding per the ruled inventory, clean
  number formatting — one precision per unit). The old renderer file stays where it is,
  serving the old runs.
- New sections required: the rating with the five-word scale in plain words; the mispricing
  read; the tripwires; the post-audit change appendix; the challenger's full response
  (collapsed); the Atlas envelope rendered as "what the portfolio system receives".
- Ruling Z binds every rendered word the page itself authors.

## 10. Integrity obligations — the spine, kept

1. Evidence provenance per §5 (source + date + arithmetic on every fact).
2. Deterministic freeze: two builds, byte-identical, hash recorded.
3. Sufficiency before spend (§5).
4. Seat isolation, measured; blind review with the seal check (§6).
5. One frozen baseline for every seat; a seat that reaches outside publishes nothing.
6. The cross-model challenge with the full unredacted case file (§7).
7. Post-audit transparency: the change appendix, always present (empty = "nothing changed").
8. Publication integrity: verdict hash recorded in an append-only run record; a read-back
   entry point (separate from the writer) proves the published file hashes to the recorded
   value AND the run reached its finished state; a dead run publishes nothing and is
   discarded whole, never resumed (M5 stands).
9. The whole run directory is the archive: every seat brief and answer, the pack, the
   challenge exchange, the run record — committed as the permanent record. `runs/` under
   `council/` follows the same never-edit rule as today.
10. Token accounting: per-seat usage recorded by the hosting session into the run record;
    totals in the verdict provenance.

## 11. Budgets (AB6) — acceptance criteria, not aspirations

Measured on the acceptance sitting (§15):
- **Wall clock ≤ 1.5 hours** end to end (capture through rendered report).
- **Anthropic tokens ≤ 1.8M** for the whole run (aim 1.5M). The diagnostic measured the
  reviewer bench at 1.31M and the second cycle at 0.64M — both already removed by ruling;
  the design must not spend the savings.
- **Challenger cost ≤ 50%** of the run's Anthropic token cost (measured 6.7% — headroom, not
  license).
A run that misses a cap is a FAILED acceptance; the builder is not done.

## 12. Deliberately NOT built (as much a part of this spec as what is)

- No book-awareness of any kind (AB1). No held/unheld vocabulary, no weight math, no account
  privacy machinery — the problem class is deleted, not handled.
- No per-name recipe adjudication machinery; floors live in Appendix A as data.
- No multi-cycle challenge loop, no strengthening freeze-gate, no cap-ceilings table, no
  conviction-cap causes: the honesty surface is the change appendix, the sufficiency gate,
  and loud degradation sentences.
- No typed-claims conflict checker. The reviewer and the challenger police consistency; the
  float-noise defect class dies with the machinery.
- No content-addressed store, no crash-resume, no dual-implementation differential harness
  (one Python implementation, tested directly).
- No PowerShell, no Node, no bridges to the old stack (§X escape hatch: if one seems needed,
  that is an escalation, never a build).
- No blind A/B harness, no theme/basket machinery in v1 (single names and Bitcoin-class
  subjects; the schema leaves room, the code does not implement them).

## 13. Tests and checks — the new battery

- Per-module Python suites under `council/`, runnable each as one command, exit code
  authoritative: schema validation; pipeline state transitions (including seat retry, seal
  re-run, challenge-failure degradation, the publisher's diff/appendix, the unendorsed-raise
  warning); evidence gate + freeze determinism + sufficiency refusals (fixture packs both
  passing and failing); bridge contract (codex invoked with the exact flag surface, stdin
  path, schema-validated response — mocked subprocess, no paid calls in tests); read-back;
  report (assertions against rendered fixtures, the Y/Z obligations, number formatting).
- One END-TO-END rehearsal in the suite: a canned fixture pack and canned seat answers driven
  through host → publish → read-back → render with zero model calls.
- The battery's command list goes in `council/CHECKS.md`; every command green at the build's
  close, exit codes read (F4.1). The OLD eleven checks are also run at close and must be
  green untouched.

## 14. Build process (AB8)

- One branch `unit-rebuild` from current `main`. The shared-checkout rule binds: `git branch
  --show-current` before every write; if the tree is on another branch, stop and re-checkout.
- Build with Fable subagents per part to protect context; the builder session remains the
  single owner of state and the single author of record.
- **Outside review at the close, as the audit plugin prescribes for large changes: three
  sub-charges in series** — (1) the evidence engine (capture contract, gate, freeze,
  sufficiency), (2) the council engine (host, seats, chair, publisher, schemas), (3) the
  bridge + report + read-back. Add `council/` to the audit allowlist in `.audit/audit.yaml`
  (one prefix line; every existing deny stays). Known plugin sharp edge: set
  `PYTHONIOENCODING=utf-8` on audit invocations (cp1252 console crash).
- The builder makes NO paid challenger calls except the standing smoke test plus at most one
  small structured-output proof of the bridge (bounded, recorded).
- Close: BUILD-LOG entry (full technical record + the ≤350-word owner checkpoint in the
  CLAUDE.md format), branch pushed, STOP DEAD. No merge, no acceptance sitting — those are
  the architect's.

## 15. Acceptance (the architect's, stated so the builder can build toward it)

1. Every `council/CHECKS.md` command green by the architect's own execution; the old eleven
   checks green untouched.
2. The three audit sub-charges closed under the plugin's stopping rule, ledger complete.
3. ONE live acceptance sitting (subject: AAPL unless the owner directs otherwise), hosted by
   the architect's dispatch, measured against §11. It must produce a decision-grade verdict:
   a rating, a priced mispricing read, tripwires, a filled Atlas envelope, a rendered report.
4. Seat isolation, freeze determinism, and read-back verified on that sitting's artifacts.

## 16. Escalation

Unclear meaning, missing ruling, tempting scope, a needed bridge, a schema question the spec
does not answer: SendMessage to `Agentic Council Architect v4`, mark that part blocked,
continue elsewhere. If the architect session is unreachable, write the question into the
BUILD-LOG entry under "ESCALATED, NOT DECIDED" and leave the part unbuilt. Building past an
ambiguity is the one unforgivable move.

---

## Appendix A — Evidence floors (by reference; content is data under `council/floors/`)

- Generic single stock (W1/W2.1): last price · 52-week low and high · market value · proof
  the latest required report is in hand · at least one earnings-power measure and one
  financial-resilience measure chosen for the business (default set: revenue, net income,
  cash, total debt) · short interest where a dated series exists (W2.2) · the results-date
  check (W2.3: confirmed date or verified "none announced") · plus, from AB2's mandate, the
  prior-year comparatives, capital spending, guidance where published, the events calendar,
  and the risk-free rate named by the question's convention.
- AAPL (W4): operating cash flow AND net income; cash-and-investments AND total debt as two
  facts; the three capital-return facts; Greater China revenue.
- GLXY (W5, business facts only — the book items are dead): the mark-to-market-hybrid
  reading; NET digital-asset exposure on the W8.1 meaning; liquidity and equity after
  collateral pledged away; both operating segments (AUM proper, contracted data-centre MW).
- Bitcoin (W6/W8.3): price from the owner-named aggregators (CoinGecko / CoinMarketCap,
  public endpoint proven) · circulating supply (Coin Metrics) · daily US spot-ETF flows
  (Farside) · halving date + block height · futures basis stays advisory (W6.4; CME refused
  automation) · the equity fact families declared absent-by-design.

## Appendix B — Environment facts the builder will hit

- Windows 11 host, Python 3.14 on PATH, `codex` CLI on PATH (0.149.1). The broker MCP
  connector (market data) is available in interactive/dispatched sessions on this machine;
  never assume it in tests.
- PowerShell 5.1 mangles UTF-8 on append — the builder writes files via its own tools or
  Python, never `Add-Content`.
- The Read tool refuses files >256KB in one call — big briefs are paged; design brief sizes
  with this in mind.
- `sec.gov`'s document archive 403s automated fetches; `data.sec.gov` and issuer
  investor-relations copies answer (runbook-proven).
- Seats may not be given tool-less agent TYPES from a running session — the prohibition is
  instructional, enforced by measurement (tool counts recorded), as every council to date.
- Background-launched hosts get killed by harness timeouts — long-running host processes are
  launched detached (the diagnostic lost 1.05M tokens to exactly this).

## 17. Architect clarifications during the build (§16 rulings, appended as made)

**17.1 (2026-08-31, escalated by the builder at the SC2 audit).** The verdict's challenge record
(§8) ALSO carries the challenger's one-paragraph overall summary, as a nullable field — null on a
failed challenge, never fabricated, rendered verbatim and attributed in the report's challenge
section. Grounds: §8's purpose is a complete challenge record, and AB4's transparency is defeated
if a paid auditor's overall view is withheld from the published document (the outside reviewer's
scenario: a zero-finding success with a damning summary would publish reading cleaner than the
audit). Schema stays 1.0.0; nothing else in §8 moves. The companion mechanism — the summary
reaching the chair's resolve brief verbatim — is the builder's, endorsed.
