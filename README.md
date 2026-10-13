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

This snapshot adds four new kinds of subject the council can rate, and a stop on the hand-off to
the portfolio side. In plain terms:

- **Tokens whose protocol earns fees.** A second kind of crypto subject: a token whose network or
  application earns fees and passes some of them to holders. Four tokens are admitted, as data in
  the evidence floors; every other token waits for a ruling. Price and supply are read from
  CoinGecko and the price cross-checked the same day against Coin Metrics. Users' fees, the
  protocol's revenue and holders' fees over thirty and ninety days are read from DefiLlama, split by
  the route they reach holders, and each split must add up exactly. The release schedule of locked
  tokens is recorded for at least the next twelve months. The token is compared with others of its
  family on market value against holders' fees, and with its own history. Each sitting names a past
  *derate* — a recorded case of a token whose price fell as new supply came out — kept as reviewed
  reference data in the floors. A claim of the form "this token reaches a given value by a date"
  may be tested, and the chairman gives its probability. These sittings always stop for a person
  to review the method before any advisor is paid; they never run unattended.
- **Insurers that compound their float.** An insurer whose share portfolio and wholly owned
  businesses outside insurance make up more than a third of its assets, or which reports those
  businesses as its own segments, is rated as its own kind of financial institution: price to book
  value against ten years of growth in book value per share. The underwriting result and the
  investment gains are shown year by year, signed and never smoothed. The rule reads the evidence,
  never a company's name.
- **Uranium, sat through a physical holder.** Uranium is rated as one commodity through the listed
  vehicle that holds the metal. The daily price is the holder's own uranium value over its pounds,
  cross-checked against the New York futures settlement; month-end spot and term prices sit beside
  it. The holder's own net asset value is used, never rebuilt by the council. The reactor fleet,
  the two largest producers' output guidance and US power companies' uncontracted needs are
  recorded; secondary supply and state stockpiles are background only. The scenario ladder runs
  three years and must name three downside cases: a supply response, the holders turning sellers,
  and power companies delaying contracts. Uranium producers are rated on the producer rules, their
  reserves counted in pounds by one fixed published factor.
- **Treasury companies and their listed preferred shares.** A company that raises money to buy
  more of one coin, with its coins more than half of its assets, is a holding company of its own
  sub-type, rated over twelve months: its coins at today's price, less its net debt, against its
  market value. Every convertible bond, loan and preferred share is recorded; whether each
  preferred share counts as debt is chosen, with a reason, before any evidence is gathered. The
  history since the company began buying, every money raise and every coin sale of the last four
  quarters are recorded. The coin's largest listed spot fund is shown beside it as the plain
  alternative, never as a peer. For every coin scenario the ladder names a case where the premium
  falls and one where it turns to a discount. A listed preferred share of such a company is a
  subject of its own kind.
- **The hand-off to the portfolio side can be withheld.** A verdict on a product the portfolio
  side has not confirmed it can read is published and recorded, but its envelope is withheld: a
  file stating the reason stands in its place, the read-back checks it, and the report says so.
- **Pages and records.** For captures from 11 October 2026, yields and revenue shares print as
  percentages and the chairman's worked-out figures trace to their written operands. Floors
  1.47.0, capture contract 1.17.0, verdict contract 1.11.0, seat-answer contracts 1.8.0; every test
  fixture re-versioned; RUNBOOK sections 1.0f to 1.0j.

---

## The pipeline

Each stage writes files the next stage reads. Every stage is a script you can run and inspect.

| Stage | What happens | Why it exists |
|---|---|---|
| **Evidence** | A hosting session researches the question live and writes one capture file. Every figure carries a stable id, the exact string observed, a unit, an as-of date, a named source, and the arithmetic written out where the figure is derived. The capture also states, in plain words, what the business is and the metrics the decision turns on, and may carry the daily price history of the subject and its benchmark. | Bad answers were traced to a starved supply line, not to bad reasoning. |
| **Gate** | A script validates the capture and refuses with plain reasons: incomplete provenance, arithmetic that does not recompute, a figure a passage never actually states, a stale fact, a source that reads the owner's book, a price history with impossible dates, holes or the wrong instrument. A number in the business description that no sourced fact backs is marked *untraced* rather than refused. | Nothing unverified reaches a seat; the business story stays honest about what it can and cannot prove. |
| **Evidence challenge** | The frozen facts go to a model from another family, which challenges the evidence itself. A correction that changes what the seats would reason from forces a re-check and a fresh approval before the run may continue. | The supply line is audited by a different mind before a verdict is ever written. |
| **Brief & approval** | The accepted evidence is written up as a one-page brief and as a full document, and the full document also as a self-contained web page. The run cannot proceed until the corrected evidence is explicitly approved, and the page must be the exact rendering of the document approved. | A human sees the exact evidence the council will use, and signs off on it. |
| **Freeze** | The accepted capture is built into a pack **twice, into two separate directories**. The two builds must be byte-identical, and the hash is recorded. Where a price history is carried, the freeze adds the tape: 25 price figures (average prices, returns, distance from the highs and lows, volatility), each recomputed by the gate. | Anyone can later prove the pack the council saw is the pack on disk. |
| **Sufficiency** | A script checks that every derived requirement resolves to a present, in-rule fact. Failure **refuses the run before any seat is paid**, listing what is missing and where it likely lives. | A refusal costs one capture. Discovering the same gap after deliberation costs the whole sitting. |
| **Frame** | The question is split: the thesis half goes to the council, any sentence referencing the asker's own holdings is routed verbatim to a note no seat ever sees. | The book-blindness seam, enforced mechanically and by judgment. |
| **Advisors ×5** | Five tool-less seats — bear, bull, base-rate skeptic, market-structure, risk — dispatched in parallel over the one frozen pack, its sources cited once each in a numbered index. Each reads one brief, argues from its seat's stated method (the market-structure and risk seats read the tape), and writes one answer under three required headings. Nothing else. | One frozen baseline; measurable isolation. |
| **Review ×1** | One blind reviewer reads all five under an anonymised mapping and produces the cross-examination and a synopsis. A seat that identifies itself or another is re-run. | Peer review without knowing whose work it is. |
| **Chair** | The chairman synthesises a verdict on a five-word scale — `strong_buy`, `buy`, `hold`, `sell`, `monitor` — with a one-line answer to the question, the argument that decided it, the business in his own words, every decisive number with what it implies, a priced mispricing read, invalidation levels, reopening triggers, and at least one falsifier scoreable against a named figure on a named date. The rating bar is set by the business archetype, and the rationale is measured for mannered prose, with one chance to rewrite. | A verdict you can be proven wrong about, judged against a standard fit to the business, in plain writing. |
| **Challenge ×1** | The full unredacted case file goes to a model from another family (via the `codex` CLI), briefed as an investment critic, not a compliance auditor. It may endorse the highest rating it would support. Its web search and connected apps are switched off; a free test call lists its tools before the paid one, and every tool it uses is recorded — any use beyond reading the case file publishes the verdict as unaudited. | The audit is not the same mind marking its own homework. |
| **Publish** | The chairman answers every finding by name, then publishes. A publisher diffs the final document against the challenged draft field by field and writes a **change appendix**. A rating raised beyond what the auditor saw publishes with a prominent warning. | Transparency instead of a gate: the reader sees what the audit moved. |
| **Read-back** | A separate entry point re-verifies: publication was authorised, the verdict still hashes to the recorded value, the hand-off envelope names the same hashes, and the run actually finished. | A verdict nobody can quietly rewrite afterwards. |
| **Ledger** | The verdict is recorded as one row — rating, price, benchmark, horizons, falsifiers, tripwires — and later scored against what the price and the named falsifiers actually did. | The council's calls can be measured against outcomes, not just admired at the time. |
| **Report** | One self-contained HTML page in numbered sections, opening with the chairman's one-line answer and the rating: a price chart with the tape beside it, the numbers the rating turns on, the advisors, and the chairman's rationale in full, with the scenario and downside ladders, the dated calendar, the tripwires and the evidence folding beneath. Every technical term carries a plain explanation. | The reader gets the decision first and dives deeper by scrolling. |

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

**A bank, an insurer, a reinsurer, an asset manager or a holding company of financial firms** is
rated as a financial institution: on the return it earns on the capital it must hold, beside that
capital's legal minimum and the regulator's bad-year stress loss. For these firms the
capital-spending requirement is lifted, and the cash test becomes the capital the firm can pay out
and still stay above its minimum. A holding company is rated on the discount to its net asset
value, and the gate checks that value as a chain of recorded facts: every holding added once, the
company's own net debt taken off once.

**A holding company that owns other businesses** — most of its value in stakes it does not run
day to day — is rated on price against net asset value by the same chain of facts, with every
private stake at the company's own latest dated value and the company's own published value
printed beside the council's. Today's discount is read against its last five financial year-ends;
dividend cover answers the cash test. A holding company is always rated as one, and a loss from
falling investment prices never makes it a growth company.

**A growth company that does not yet make a profit** — one without four profitable quarters
behind it — is rated on the growth path: what the whole business costs against its gross profit,
beside its sales growth, compared with growth companies of the same kind. The months of cash left
are worked out by the machine from the recorded cash and cash burn, never written by hand; below
the floors' line the council may rate it at most *hold*, and every page says so in one sentence.
The rule works both ways: a company with four profitable quarters is rated on its earnings however
fast it grows.

**An oil, gas or mining producer, or a royalty and streaming company,** is rated on what it costs
against its reserves and against its cash flow at the price the reserves were counted at. A
company that reports reserves is always rated this way, never on peak-year earnings — unless it
is an integrated oil major that passes the stated test, when it is rated as a profit-maker with
its reserves and today's price still shown. The council takes reserves as reported, converts no
units (gas counted in cubic feet is never set against a price per million British thermal
units), and shows by-product metals apart.

**A token whose protocol earns fees** is rated on the fees that reach its holders: its market
value against ninety days of holders' fees, beside tokens of the same family and its own history,
with the next twelve months of new supply set against daily trading. A fee that is really newly
created tokens paid to stakers is never counted as a fee. Every sitting names the past derate it is
compared with, and stops for a person to review the method before any advisor is paid.

**An insurer that compounds its float** — a large share portfolio or wholly owned businesses
outside insurance beside its underwriting — is rated on price to book value against ten years of
book value per share growth. The underwriting record and investment gains are shown year by year;
operating return on equity is shown, never rated.

**Uranium** is rated through the listed vehicle that holds the metal, on a three-year scenario
ladder against cash. The holder's own published net asset value stands; the council never builds
one. China's buying and global secondary supply are prose only, labelled unverified, never a
council figure.

**A company that holds a coin as its treasury** is rated on its coins at today's price, less its
net debt, against its market value, over twelve months. Each preferred share's treatment is chosen
before the evidence is gathered and shown with its reason; the largest listed spot fund for the
coin is printed beside it as the plain alternative.

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

Python 3.13 or newer, **standard library only** — no dependencies, no package install, nothing to
build. (Verified: the only non-`council` imports in the tree are stdlib modules.)

Run from the repository root. **The exit code is the authority: 0 is green.**

The seven suites, what each covers, and the command to run it:

| Suite | Tests | Covers | Run |
|---|---|---|---|
| `test_foundations` | 40 | canonical bytes and hashing, the schema validator, the ruled evidence floors, the exchange calendars and currency units, the book-blind language rule scanned over every file, the deterministic mannered-prose measure | `PYTHONIOENCODING=utf-8 python3 -m unittest council.tests.test_foundations` |
| `test_evidence` | 2544 | the provenance gate, the unit list and the one-line question check, the price history and the tape, the listings outside the US, the evidence challenge and re-audit, the byte-identical freeze, the one-page and full briefs and the approval page, the financial-institution, float-compounder, growth, resource-producer, uranium, protocol-token, holding-company and treasury-company rules, sufficiency pass and refusal paths per subject kind and per asset class | `PYTHONIOENCODING=utf-8 python3 -m unittest council.tests.test_evidence` |
| `test_engine` | 993 | the state machine end to end, seat retries, the blind seal, the seats' methods and required headings, the citation index, the chairman's mechanical checks and required fields, the archetype rating bar, the scenario-earned rating, the mannered-prose re-ask, the publisher's change appendix, the withheld hand-off | `PYTHONIOENCODING=utf-8 python3 -m unittest council.tests.test_engine` |
| `test_bridge` | 150 | the challenger command's exact flag surface, the tool-list probe and the tool-use record, every failure status, timeout tree-kill — against a fake launcher, so **no paid calls** | `PYTHONIOENCODING=utf-8 python3 -m unittest council.tests.test_bridge` |
| `test_report` | 646 | the rendered page: the numbered sections, the price chart, the business tables, the plain explanations, folding, warnings, number formatting, self-containedness, the approval page, the financial-institution, float-compounder, growth, resource-producer, uranium, protocol-token, holding-company, treasury-company and preferred-share pages | `PYTHONIOENCODING=utf-8 python3 -m unittest council.tests.test_report` |
| `test_e2e_rehearsal` | 9 | invented captures driven through the **real** chain — gate → freeze → sufficiency → host → canned seats → canned challenge → publish → read-back → ledger → rendered report, with **zero model calls** | `PYTHONIOENCODING=utf-8 python3 -m unittest council.tests.test_e2e_rehearsal` |
| `test_ledger` | 61 | building a verdict row, back-filling rows from real verdicts, and scoring a row against the recorded outcome | `PYTHONIOENCODING=utf-8 python3 -m unittest council.tests.test_ledger` |

4443 tests at this snapshot. **All seven suites are green standalone in this tree (exit code 0).**
Where `python3` on your machine is older than 3.13, name the newer interpreter instead (for
example `python3.13`).

**Clean skips.** 148 tests skip here and only here, each with its reason printed, because they
read material this copy does not publish. 146 read *live run records*: `test_evidence` skips 88
(the live-capture, migration and archetype-acceptance classes re-run the gate over real captures,
the record-set classes check that every new rule leaves each real sitting's result unchanged, and
the approval-document and business-row classes render a real sitting's evidence), `test_report`
skips 48 (the readability, look-and-feel, business-table and approval-page classes render a real
sitting, and every real sitting still renders), `test_engine` skips 9 (read-back of every published
sitting, and checks that read one real sitting's case file and verdict), and `test_ledger` skips
one (scoring rows built from real verdicts). The other two are in `test_foundations`: they check the
mannered-prose measure against the chairman's own rationales from two real sittings, a fixture
withheld here (see *What is deliberately absent*). Each skip fires only when the material is
absent — a checkout holding it runs the test — so an omission stays visible rather than papered
over, and every mechanism these tests exercise is also exercised on invented fixtures elsewhere in
its suite.

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
- **The verdict ledger of real sittings** (`council/ledger/ledger.jsonl`). It records every real
  verdict the council has published — subject, rating, price and levels. The code that writes and
  scores it travels, with invented ledger fixtures; publishing a sitting in this copy creates the
  file afresh.
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
- **Example sentences, altered.** `docs/ANCHORLESS-SPEC.md` §11 and the matching regression
  test constant in `council/tests/test_engine.py` originally quoted the owner's own sentence
  naming a real holding of his. `ExampleCo` stands in for it, marked in place in both files. The
  one-line question tests in `council/tests/test_evidence.py` read against an invented example
  question, marked in place, and the figures a few report tests expect from a real sitting's page
  (price levels, a sitting's duration and cost) are invented values of the same shape; those tests
  skip here in any case. The mechanisms and the rulings are unchanged.

Because the run records are absent, a few documents point at paths that do not exist here —
`docs/ATLAS-ENVELOPE-CONTRACT.md` cites a live run as its worked example, and
`docs/ANCHORLESS-SPEC.md` cites another as the failure it was written to fix. The citations are
left verbatim rather than rewritten; read them as references to material that was not published.
Likewise the evidence floors name, for each recorded derate case, the reference record it was read
from under `docs/DERATE-RECORDS-2026-10-08/`; those records are not published, and the figures
the council uses from them are carried in the floors themselves.

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
