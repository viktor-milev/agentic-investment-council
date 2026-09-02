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

## The pipeline

Each stage writes files the next stage reads. Every stage is a script you can run and inspect.

| Stage | What happens | Why it exists |
|---|---|---|
| **Evidence** | A hosting session researches the question live and writes one capture file. Every figure carries a stable id, the exact string observed, a unit, an as-of date, a named source, and the arithmetic written out where the figure is derived. | Bad answers were traced to a starved supply line, not to bad reasoning. |
| **Gate** | A script validates the capture and refuses with plain reasons: incomplete provenance, arithmetic that does not recompute, a figure a passage never actually states, a stale fact, a source that reads the owner's book. | Nothing unverified reaches a seat. |
| **Freeze** | The accepted capture is built into a pack **twice, into two separate directories**. The two builds must be byte-identical, and the hash is recorded. | Anyone can later prove the pack the council saw is the pack on disk. |
| **Sufficiency** | A script checks that every derived requirement resolves to a present, in-rule fact. Failure **refuses the run before any seat is paid**, listing what is missing and where it likely lives. | A refusal costs one capture. Discovering the same gap after deliberation costs the whole sitting. |
| **Frame** | The question is split: the thesis half goes to the council, any sentence referencing the asker's own holdings is routed verbatim to a note no seat ever sees. | The book-blindness seam, enforced mechanically and by judgment. |
| **Advisors ×5** | Five tool-less seats — bear, bull, base-rate skeptic, market-structure, risk — dispatched in parallel over the one frozen pack. Each reads one brief and writes one answer. Nothing else. | One frozen baseline; measurable isolation. |
| **Review ×1** | One blind reviewer reads all five under an anonymised mapping and produces the cross-examination and a synopsis. A seat that identifies itself or another is re-run. | Peer review without knowing whose work it is. |
| **Chair** | The chairman synthesises a verdict on a five-word scale — `strong_buy`, `buy`, `hold`, `sell`, `monitor` — with a priced mispricing read, invalidation levels, reopening triggers, and at least one falsifier scoreable against a named figure on a named date. | A verdict you can be proven wrong about. |
| **Challenge ×1** | The full unredacted case file goes to a model from another family (via the `codex` CLI), briefed as an investment critic, not a compliance auditor. It may endorse the highest rating it would support. | The audit is not the same mind marking its own homework. |
| **Publish** | The chairman answers every finding by name, then publishes. A publisher diffs the final document against the challenged draft field by field and writes a **change appendix**. A rating raised beyond what the auditor saw publishes with a prominent warning. | Transparency instead of a gate: the reader sees what the audit moved. |
| **Read-back** | A separate entry point re-verifies: publication was authorised, the verdict still hashes to the recorded value, the hand-off envelope names the same hashes, and the run actually finished. | A verdict nobody can quietly rewrite afterwards. |
| **Report** | One self-contained HTML page, opening with a two-page decision front: the rating, the numbers it turns on, the downside ladder, the dated calendar, the tripwires, and what would change the rating. | Everything else folds behind it as appendices. |

**Assets with no earnings** (Bitcoin, gold, commodities) are rated differently: the seats and the
chairman build a scenario ladder with their own stated probabilities, the expected result is
computed against a bar of cash plus a premium scaled to the asset's own five-year volatility, and
the arithmetic and its sensitivity are printed on the page. Probabilities are labelled the
council's judgment, never evidence. A commodity product nobody has ruled on refuses rather than
sitting quietly on a generic template.

---

## Running it

Python 3.14, **standard library only** — no dependencies, no package install, nothing to build.
(Verified: the only non-`council` imports in the tree are stdlib modules.)

Run from the repository root. **The exit code is the authority: 0 is green.**

```bash
PYTHONIOENCODING=utf-8 python council/tests/test_foundations.py
```

The six suites, and what each covers:

| Suite | Tests | Covers |
|---|---|---|
| `council/tests/test_foundations.py` | 19 | canonical bytes and hashing, the schema validator, the ruled evidence floors, the book-blind language rule scanned over every file |
| `council/tests/test_evidence.py` | 173 | the provenance gate, the byte-identical freeze, sufficiency pass and refusal paths per subject kind and per asset class |
| `council/tests/test_engine.py` | 241 | the state machine end to end, seat retries, the blind seal, the chairman's mechanical checks, the scenario-earned rating, the publisher's change appendix |
| `council/tests/test_bridge.py` | 29 | the challenger command's exact flag surface, every failure status, timeout tree-kill — against a fake launcher, so **no paid calls** |
| `council/tests/test_report.py` | 150 | the rendered page: sections, folding, warnings, number formatting, self-containedness, the decision front |
| `council/tests/test_e2e_rehearsal.py` | 6 | invented captures driven through the **real** chain — gate → freeze → sufficiency → host → nine canned seats → canned challenge → publish → read-back → rendered report, with **zero model calls** |

618 tests at this snapshot; all six were green, standalone in this tree, when it was cut.

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
  question and dated personal records. Nothing from a real sitting travels. The invented fixtures
  under `council/tests/fixtures/` replace them for every test and for the rehearsal.
- **The owner's rulings ledger** (`docs/OWNER-RULINGS.md`). It is a private decision log that
  quotes him throughout. The specs here cite its ruling ids (`AB13`, `W2.5`, `§X` and so on) and
  those citations are left intact, so the reasoning stays traceable even though the source is not
  published.
- **The build log and the whole audit trail** (build history, adversarial review transcripts,
  finding dispositions). They quote run material and internal review at length.
- **The superseded PowerShell implementation** (`schemas/`, `control/`, `workflow/`, `bridge/`,
  `hooks/`, `tools/`) and its captures. It is the first build of this system, frozen rather than
  deleted, and its captures are the owner's. Consequence: the "old stack's eleven checks" section
  at the end of `council/CHECKS.md` names commands that are not in this copy. The six Python
  suites above are the whole battery here.
- **Local session configuration** (`.claude/`). Machine-specific, of no use to a reader.
- **One example sentence, altered.** `docs/ANCHORLESS-SPEC.md` §11 and the matching regression
  test constant in `council/tests/test_engine.py` originally quoted the owner's own sentence
  naming a real holding of his. `ExampleCo` stands in for it, marked in place in both files. The
  mechanism and the ruling are unchanged.

Because the run records are absent, a few documents point at paths that do not exist here —
`docs/ATLAS-ENVELOPE-CONTRACT.md` cites a live Bitcoin run as its worked example, and
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
