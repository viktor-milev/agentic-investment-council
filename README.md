# The agentic investment council

A decision gate for investment questions, built as a pipeline of independent AI seats over one
frozen set of evidence.

You ask it one question about one investment. It works out what facts that question needs,
gathers them, freezes them, and refuses to spend anything on deliberation until it can prove the
frozen evidence can actually answer the question. Then five advisors with different lenses
analyse the same frozen pack in isolation, one blind reviewer cross-examines them, a chairman
writes a verdict, and a **different model from a different family** audits that verdict before
anything is published. The chairman's final document publishes with an appendix showing exactly
what changed after the audit.

It is deliberately **book-blind**: it never sees who holds what. It opines on a thesis in
isolation and hands portfolio work — position sizing, the actual instruction — to a separate
system through a machine-readable envelope. The words *held*, *position*, *sleeve*, *weight*,
*account* and *net liquidation value* are not in its vocabulary, and a test scans the whole tree
to keep it that way.

This repository is a **snapshot for outside review**, extracted from a private working repository.
It is not the live system and carries no history. See *What is deliberately absent* below.

---

## What changed since the last snapshot

This snapshot adds several stages and rules to the pipeline. In plain terms:

- **Every seat's model is now a setting.** The council suggests a model and effort for each seat in
  one file and the operator may override any of them; the outside challenger's default is now
  GPT-6 Sol. See *Seating the council* below.
- **The business comes before the numbers.** Every pack now opens with a short description of what
  the business is and the handful of metrics the decision actually turns on, so a seat reasons
  about a company, not a column of figures.
- **The evidence itself is challenged, not just the verdict.** The outside model now also reviews
  the frozen facts before the council sits. If a correction changes what the seats would reason
  from, the run is held until the evidence is re-checked and re-approved.
- **A one-page brief and a full evidence document, with an approval step.** The gathered evidence
  is written up twice — a one-page summary and a complete document — and the run cannot proceed
  until the corrected evidence is explicitly approved.
- **Untraced numbers are marked, never silently dropped.** A figure in the plain-English business
  description that cannot be traced to a sourced fact is flagged as untraced rather than refusing
  the whole capture.
- **The rating bar depends on the kind of business.** Different business archetypes are measured
  against different standards, so a fragile turnaround and a cash compounder are not judged the
  same way.
- **A house rule against mannered writing.** The chairman's rationale is measured for over-styled
  prose — showy dashes, rhetorical questions, artificial contrasts — and is given one measured
  chance to rewrite before it stands.
- **A verdict ledger scored against outcomes.** Each verdict is recorded as a row and later scored
  against what actually happened to the price and to its own named falsifiers, so the council's
  hit rate can be measured over time.
- **A redesigned report.** The published page was rebuilt as an executive-summary-first document:
  the rating, the decisive numbers and the chairman's rationale in full sit at the top, with the
  ladders, the calendar and the evidence folding beneath.

---

## The pipeline

Each stage writes files the next stage reads. Every stage is a script you can run and inspect.

| Stage | What happens | Why it exists |
|---|---|---|
| **Evidence** | A hosting session researches the question live and writes one capture file. Every figure carries a stable id, the exact string observed, a unit, an as-of date, a named source, and the arithmetic written out where the figure is derived. The capture also states, in plain words, what the business is and the metrics the decision turns on. | Bad answers were traced to a starved supply line, not to bad reasoning. |
| **Gate** | A script validates the capture and refuses with plain reasons: incomplete provenance, arithmetic that does not recompute, a figure a passage never actually states, a stale fact, a source that reads the owner's book. A number in the business description that no sourced fact backs is marked *untraced* rather than refused. | Nothing unverified reaches a seat; the business story stays honest about what it can and cannot prove. |
| **Evidence challenge** | The frozen facts go to a model from another family, which challenges the evidence itself. A correction that changes what the seats would reason from forces a re-check and a fresh approval before the run may continue. | The supply line is audited by a different mind before a verdict is ever written. |
| **Brief & approval** | The accepted evidence is written up as a one-page brief and as a full document. The run cannot proceed until the corrected evidence is explicitly approved. | A human sees the exact evidence the council will use, and signs off on it. |
| **Freeze** | The accepted capture is built into a pack **twice, into two separate directories**. The two builds must be byte-identical, and the hash is recorded. | Anyone can later prove the pack the council saw is the pack on disk. |
| **Sufficiency** | A script checks that every derived requirement resolves to a present, in-rule fact. Failure **refuses the run before any seat is paid**, listing what is missing and where it likely lives. | A refusal costs one capture. Discovering the same gap after deliberation costs the whole sitting. |
| **Frame** | The question is split: the thesis half goes to the council, any sentence referencing the asker's own holdings is routed verbatim to a note no seat ever sees. | The book-blindness seam, enforced mechanically and by judgment. |
| **Advisors ×5** | Five tool-less seats — bear, bull, base-rate skeptic, market-structure, risk — dispatched in parallel over the one frozen pack. Each reads one brief and writes one answer. Nothing else. | One frozen baseline; measurable isolation. |
| **Review ×1** | One blind reviewer reads all five under an anonymised mapping and produces the cross-examination and a synopsis. A seat that identifies itself or another is re-run. | Peer review without knowing whose work it is. |
| **Chair** | The chairman synthesises a verdict on a five-word scale — `strong_buy`, `buy`, `hold`, `sell`, `monitor` — with a priced mispricing read, invalidation levels, reopening triggers, and at least one falsifier scoreable against a named figure on a named date. The rating bar is set by the business archetype, and the rationale is measured for mannered prose, with one chance to rewrite. | A verdict you can be proven wrong about, judged against a standard fit to the business, in plain writing. |
| **Challenge ×1** | The full unredacted case file goes to a model from another family (via the `codex` CLI), briefed as an investment critic, not a compliance auditor. It may endorse the highest rating it would support. | The audit is not the same mind marking its own homework. |
| **Publish** | The chairman answers every finding by name, then publishes. A publisher diffs the final document against the challenged draft field by field and writes a **change appendix**. A rating raised beyond what the auditor saw publishes with a prominent warning. | Transparency instead of a gate: the reader sees what the audit moved. |
| **Read-back** | A separate entry point re-verifies: publication was authorised, the verdict still hashes to the recorded value, the hand-off envelope names the same hashes, and the run actually finished. | A verdict nobody can quietly rewrite afterwards. |
| **Ledger** | The verdict is recorded as one row — rating, price, benchmark, horizons, falsifiers, tripwires — and later scored against what the price and the named falsifiers actually did. | The council's calls can be measured against outcomes, not just admired at the time. |
| **Report** | One self-contained HTML page, opening as an executive summary: the rating, the numbers it turns on, and the chairman's rationale in full, with the scenario and downside ladders, the dated calendar, the tripwires and the evidence folding beneath. | The reader gets the decision first and dives deeper by scrolling. |

**Assets with no earnings** (Bitcoin, gold, commodities) are rated differently: the seats and the
chairman build a scenario ladder with their own stated probabilities, the expected result is
computed against a bar of cash plus a premium scaled to the asset's own five-year volatility, and
the arithmetic and its sensitivity are printed on the page. Probabilities are labelled the
council's judgment, never evidence. A commodity product nobody has ruled on refuses rather than
sitting quietly on a generic template.

**A filer with no capital-spending line** does not stop the sitting. A wider published line may
stand in for it, but only if it declares itself: the evidence file tags the figure as a *ceiling*
(it can only overstate the spending) and names the published line it was taken from, and the case
file every seat reads says so in generated words the capture cannot contradict. Any cash flow
computed on top of a ceiling is itself only a *floor* — the true figure can only be higher — and
is labelled that way. Both years must use the same treatment, so a stand-in cannot quietly create
a trend. Nothing here asserts the substitute line is the narrowest one available; that judgment is
a human's, and the file says so. A product nobody has ruled on still refuses.

---

## Seating the council: defaults and how to override them

Every seat in the council runs on a model and effort you choose. The council only suggests
defaults, in `council/floors/seats.json`: the five advisors, the peer reviewer and the business-frame
writer on Claude Opus 5.5 at high effort, the chairman on Claude Opus 5.5 at extra-high effort, and
the outside challenger on GPT-6 Sol at high effort. These are recommendations, not requirements —
make your own settings. The Claude seats are launched by the session hosting the sitting, so you
change them by telling that session which model and effort to give each seat (see
`council/RUNBOOK.md`, "Seating the council"). The challenger is changed by setting
`COUNCIL_CHALLENGER_MODEL` and `COUNCIL_CHALLENGER_EFFORT` in the environment, or by editing the
file. Whatever you choose, the published verdict records the model each seat was actually asked to
run on, so every decision carries its own record of who made it.

---

## Running it

Python 3.14, **standard library only** — no dependencies, no package install, nothing to build.
(Verified: the only non-`council` imports in the tree are stdlib modules.)

Run from the repository root. **The exit code is the authority: 0 is green.**

The seven suites, what each covers, and the command to run it:

| Suite | Tests | Covers | Run |
|---|---|---|---|
| `test_foundations` | 32 | canonical bytes and hashing, the schema validator, the ruled evidence floors, the book-blind language rule scanned over every file, the deterministic mannered-prose measure | `PYTHONIOENCODING=utf-8 python council/tests/test_foundations.py` |
| `test_evidence` | 676 | the provenance gate, the evidence challenge and re-audit, the byte-identical freeze, the one-page and full briefs, sufficiency pass and refusal paths per subject kind and per asset class | `PYTHONIOENCODING=utf-8 python council/tests/test_evidence.py` |
| `test_engine` | 468 | the state machine end to end, seat retries, the blind seal, the chairman's mechanical checks, the archetype rating bar, the scenario-earned rating, the mannered-prose re-ask, the publisher's change appendix | `PYTHONIOENCODING=utf-8 python council/tests/test_engine.py` |
| `test_bridge` | 101 | the challenger command's exact flag surface, every failure status, timeout tree-kill — against a fake launcher, so **no paid calls** | `PYTHONIOENCODING=utf-8 python council/tests/test_bridge.py` |
| `test_report` | 297 | the rendered page: sections, folding, warnings, number formatting, self-containedness, the executive-summary front | `PYTHONIOENCODING=utf-8 python council/tests/test_report.py` |
| `test_e2e_rehearsal` | 7 | invented captures driven through the **real** chain — gate → freeze → sufficiency → host → canned seats → canned challenge → publish → read-back → ledger → rendered report, with **zero model calls** | `PYTHONIOENCODING=utf-8 python council/tests/test_e2e_rehearsal.py` |
| `test_ledger` | 61 | building a verdict row, back-filling rows from real verdicts, and scoring a row against the recorded outcome | `PYTHONIOENCODING=utf-8 python council/tests/test_ledger.py` |

1642 tests at this snapshot. **All seven suites are green standalone in this tree (exit code 0).**

**Clean skips.** Nineteen tests skip here and only here, each with its reason printed, because they
read material this copy does not publish. Seventeen read *live run records*: `test_evidence` skips
fourteen (the live-capture and archetype-acceptance classes re-run the gate over real captures),
`test_engine` skips two (`TestEveryPublishedRunStillReadsBack` re-verifies every published sitting
against its record), and `test_ledger` skips one (scoring rows built from real verdicts). The
other two are in `test_foundations`: they check the mannered-prose measure against the chairman's
own rationales from two real sittings, a fixture withheld here (see *What is deliberately absent*).
Each skip fires only when the material is absent — a checkout holding it runs the test — so an
omission stays visible rather than papered over, and the prose measure itself is fully exercised by
the rest of its suite.

**`test_e2e_rehearsal.py` is the demonstration to run first.** It exercises the entire pipeline
with real artifacts and no model, no network, and no API key — the fastest honest way to see what
the system actually does.

Running a *live* sitting additionally needs a hosting session that can dispatch isolated seats
and a `codex` CLI on PATH for the challenger. `council/RUNBOOK.md` is the operator's procedure;
`council/CHECKS.md` is the check battery and its per-platform notes.

---

## What is deliberately absent from this copy

This is an extraction, not a fork. Each omission below has one reason.

- **All git history.** The private repository's history is saturated with the owner's personal
  financial material. This copy begins at a single initial commit and has no ancestry.
- **`council/runs/**` — every live run record.** Each sitting carries the owner's own verbatim
  question and dated personal records. Nothing from a real sitting travels. Invented fixtures under
  `council/tests/fixtures/` replace them almost everywhere — but not quite: the live-capture and
  read-back tests open real records directly and therefore **skip** in this copy, with the reason
  printed. A skip fires only when no live run exists at all, so the omission stays visible rather
  than papered over.
- **The chairman's own rationales from real sittings**
  (`council/tests/fixtures/prose/chair_rationales.txt`). This fixture is the chairman's verbatim
  writing from two live runs, quoting the owner's own theses. It is withheld, which is why the two
  `test_foundations` prose comparisons noted above skip here.
- **The owner's rulings ledger** (`docs/OWNER-RULINGS.md`). It is a private decision log that
  quotes him throughout. The specs here cite its ruling ids (`AB13`, `AC16`, `§X` and so on) and
  those citations are left intact, so the reasoning stays traceable even though the source is not
  published.
- **The build log and the whole audit trail** (build history, adversarial review transcripts,
  finding dispositions). They quote run material and internal review at length.
- **The superseded PowerShell implementation** and its captures. It was the first build of this
  system, since retired, and its captures are the owner's. The seven Python suites above are the
  whole check battery here.
- **Local session configuration** (`.claude/`). Machine-specific, of no use to a reader.
- **One example sentence, altered.** `docs/ANCHORLESS-SPEC.md` §11 and the matching regression
  test constant in `council/tests/test_engine.py` originally quoted the owner's own sentence
  naming a real holding of his. `ExampleCo` stands in for it, marked in place in both files. The
  mechanism and the ruling are unchanged.

Because the run records are absent, a few documents point at paths that do not exist here —
`docs/ATLAS-ENVELOPE-CONTRACT.md` cites a live run as its worked example, and
`docs/ANCHORLESS-SPEC.md` cites another as the failure it was written to fix. The citations are
left verbatim rather than rewritten; read them as references to material that was not published.

---

## Reading order for a reviewer

1. `docs/REBUILD-SPEC.md` — the whole system's contract: pipeline, seats, verdict, budgets, and a
   long list of what was deliberately *not* built.
2. `council/tests/test_e2e_rehearsal.py` — then run it. The shortest path from claim to evidence.
3. `council/evidence/gate.py` and `council/evidence/sufficiency.py` — the two stages that refuse.
4. `council/engine/host.py` — the state machine everything else hangs off.
5. `docs/ANCHORLESS-SPEC.md` — how an asset with no earnings earns a rating instead of being
   frozen at "hold" forever.
6. `docs/ATLAS-ENVELOPE-CONTRACT.md` — the hand-off to the portfolio side, and the honest note
   about the one boundary the machine does not police.
7. `docs/THEMES-BASKETS-SPEC.md` — multi-instrument subjects, and why a theme with no investable
   expression is refused rather than rated weakly.
8. `docs/prep/` — the two research briefs behind the Bitcoin and gold/commodity evidence
   standards. Useful on their own if you care about what a serious evidence bar looks like.

Critique is the point of publishing this. The design commitments most worth attacking are the
ones this copy cannot prove to you: that isolation actually buys independent reasoning, that one
challenge cycle is enough, and that a frozen pack does not simply freeze an early mistake.

---

## License

MIT. See [`LICENSE`](LICENSE).

Nothing here is investment advice, and no output of this system is investment advice.
