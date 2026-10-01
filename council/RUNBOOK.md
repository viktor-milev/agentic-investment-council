# council/RUNBOOK.md — hosting a sitting on the Python council

The whole pipeline (REBUILD-SPEC §4), operated from one interactive session
on this machine. Everything below runs from the repository root with
`PYTHONIOENCODING=utf-8`. Where a command below says `python`, it means your
Python 3 interpreter, as in `council/CHECKS.md`: `python3.13` on the Mac (no bare
`python` exists there), `python` on Windows. The budgets are acceptance criteria
(AB6/AC8): wall clock at most 1.5 hours from the go to the rendered report — the
wait for a human to read the evidence brief is outside it — at most 2.2M
Anthropic tokens (AC8), challenger at most 50% of the Anthropic cost. For a given
sitting the owner may set the token figure as a target, not a cap: the sitting
reports where it comes out; AC8's 2.2M stands for every other subject until
measured.

## 0. Ask the one question, and write the answer down (owner ruling AC3)

**Before you open a single filing.** In standalone use, ask the user this and
nothing else:

> Do you want to read and approve the one-page evidence brief before the
> council sits, or run unattended (auto-mode)?

Write the answer immediately, into the sitting's own evidence folder — the
folder that will also hold the capture, the outside audit and its resolution:

```
<run>/evidence/mode.json
{"mode": "reviewed", "chosen_by": "<the person who answered>", "at": "<iso now>"}
```

`mode` is `reviewed` or `unattended`, and nothing else. The choice is made
ONCE, here, and never revisited: `host init` refuses a mode dated after the
capture, because a choice made after the evidence exists is a choice made
knowing what the evidence says.

**A sitting invoked by Atlas is unattended by construction.** Write
`{"mode": "unattended", "chosen_by": "atlas", "at": "<iso now>"}` and ask
nobody: Atlas runs autonomously, and the seam
(`docs/ATLAS-ENVELOPE-CONTRACT.md`) is where any future human step belongs —
never the council.

## 1. Evidence (session work — the scripts never fetch anything)

### 1.0 Frame the business BEFORE you gather (owner ruling AC1)

**Write this first, before you open a single filing.** In your own words, and
without looking anything up beyond what the question already tells you:

1. **What it does** — what is sold, to whom, and the vanish test: what does the
   customer lose if this company disappears tomorrow? At most 120 words.
2. **What is changing** — one of `none`, `mix_shift`, `model_transition`,
   `turnaround`, `cyclical_trough`, `cyclical_peak`, `rollup`, and at most 150
   words saying it.
3. **The three to five numbers that decide THIS question** — candidates, with
   one line each on why each decides it.

Then gather to ANSWER those questions, rather than gathering first and writing
the frame from whatever arrived. The order is the point: a pack built the other
way round carries whatever the sources made easy, and the number that actually
decides the case is the one nobody demanded. That is exactly how a company
converting to a new business model gets read as a company in decline.

The questions above come from two places and nothing is imported from either:
the **equity-research initiating-coverage checklist** (business description,
revenue lines, competitive standing, management record) and the
**business-decoder memo spine** (what is sold · to whom · the vanish test ·
who else could do it). Quarry them for questions; wire nothing in.

Then write the frame into the capture as `business_frame`, keyed by ticker —
the subject's own for a single listed name, one key per constituent for a
basket or a theme universe. A fund and an asset with no earnings may carry one
and are never refused for its absence. Each frame carries: `what_it_does`,
`how_it_earns` (the revenue lines with their share of the latest period, each
pointing at its `segment_revenue_*` facts), `what_is_changing`,
`headline_decline_read`, three to five `decisive_metrics`, `peers`,
`management`, `competitive_position`, and — for a single listed name (owner
ruling AC15, unit U3e) — `archetype` with `archetype_because`, and
`cycle_dependence` with `cycle_dependence_because`. These rules bite in
practice:

- **A falling headline figure must be READ.** If revenue, net income or
  operating cash flow is below its prior-year pair, the frame says whether the
  fall is `by_design`, `deterioration` or `mixed`, with the facts it rests on.
  `unknown` is allowed and is a declared gap: add a `gaps` row whose
  `fact_class` reads exactly `headline_decline_read`.
- **A transition is judged on the new business.** Where `what_is_changing.kind`
  is `model_transition` or `turnaround`, at least one decisive metric is of kind
  `capacity_or_backlog` or `unit_economics` — the contracted megawatts and the
  rent per megawatt of the TeraWulf case (`docs/C2-CAPTURE-RUNBOOK.md:66`).
- **Two to six peers, or an honest gap.** Each peer carries at least two
  comparable figures as tier-1 facts named `peer_<metric>__<ticker>`. Where no
  honest peer set exists, name none and add a `gaps` row with `fact_class`
  exactly `peer_` — three true peers beat six doubtful ones, and one comparison
  is an anecdote. The same row lifts the ruled peer floor.
- **Guided beside delivered.** For each of the last four reported quarters that
  had guidance, capture `guided_<metric>_<q>` and `delivered_<metric>_<q>`.
  Where the company publishes no guidance, name no quarter and add a `gaps` row
  with `fact_class` exactly `guided_`.
- **A guidance row's period is not a caption (owner ruling AC12.1).** The
  `period` you display binds to the ids beneath it: lower-case the label,
  turn every run of anything that is not a letter or a digit into one
  underscore, and every `guided`/`delivered` id in that row must END with
  `_<that slug>` (plus the member suffix inside an expression). `Q1 FY2026`
  binds to `guided_revenue_q1_fy2026`. And the table is COMPLETE both ways:
  every guided figure in a row has its own `delivered_` partner in the pack,
  and every `guided_` fact the pack carries appears in some row **while the
  table has room** — a quarter management missed may not be left out while its
  figures sit in the fact table below. The table holds four quarters, so a pack
  carrying five is legal and the four you show are your own recorded choice; a
  table with room left owes every quarter the pack holds.
  **One row per period, never one row per metric:** every metric guided for that period
  goes in the row's `guided` list, and each is scored against its own `delivered_` partner,
  which the seats' case file prints beside it; `delivered` names the row's headline metric.
  Two rows for the same period refuse (a label that fits two quarters).
- **This year so far (owner ruling AC45(9)).** Guidance for a period the
  company has not reported yet - the year it is in - goes in the ruled
  families like any other: its own row headed by that period (`FY<year>`),
  the first guides in `guided`, each revision in `revisions`, and
  `"delivered": null`. The gate lets a row wait for its outcome only where its
  period falls after the one `latest_required_report_period` (the member's
  own, inside an expression) leads with, so write that fact's value period
  first, in the rows' own labelling (`Q<n> FY<year>, quarter ended ...`); a
  value that is a bare date places no period, and every row then names its
  delivered figure. A year's row cannot share the table with that year's
  quarter rows (their ids end with the year's slug too). The pages print the
  open cell as "not reported yet". Once the period is reported, the row names
  its `delivered_` figure like any other.
- **Every figure you write in the frame's prose is declared (owner ruling
  AC12.2).** `what_it_does_figures` beside `what_it_does`; a `figures` list
  inside `what_is_changing`, on each revenue line, and on each decisive-metric
  row. Each declared figure must stand in that block's own text word for word,
  in the same format you wrote it — exactly the rule a tier-2 passage's
  `figures` already meets, checked by the same code. Prose with no figure in it
  declares an empty list. The two single-name rationale fields answer to that
  same rule (owner ruling AC13.1): a figure written into `archetype_because` or
  `cycle_dependence_because` is declared in its optional sibling list
  (`archetype_because_figures`, `cycle_dependence_because_figures`), stands in
  that field's own text word for word, and equals the value of a fact the frame
  carries — each list absent or empty where the rationale carries no figure.
- **An UNDECLARED number in the prose is marked, never refused (owner ruling
  AC19).** Separately from the declared-figures rule above, the council reads
  every number written into the frame's prose and traces it to a recorded fact,
  allowing for rounding and for a change of scale or unit wording. A number that
  matches nothing stays in the text and is marked `[not traced to a recorded
  fact]` — in every seat's case file, the one-page brief, the full evidence
  document you approve, and the outside auditor's evidence brief (which is told
  to look at the marked numbers first) — and one summary line per frame says how
  many numbers traced and how many did not. Nothing is refused on this ground;
  it costs a mark, not a rejection. So a correct quarterly figure that is one
  fourth of a recorded annual one comes out marked (the council does no
  arithmetic between facts) while the pack still passes. Years, dates, ordinals,
  period labels and plain counts are exempt. The tolerances and the exemption
  list are DATA, in `council/floors/floors.json` under `prose_figure_marks`; the
  marks are computed when the documents are rendered, so nothing you gather or
  freeze changes, and the pack hash does not move.
- **The share of the period is a figure the pack carries (owner ruling
  AC12.2).** `share_of_period` is not free text: it must equal, character for
  character, the value of one of that line's own facts, or of a fact struck
  ONLY from them. The natural shape is a derived fact — the segment's revenue
  divided by every revenue line of the quarter — whose arithmetic the freeze
  prints; the worked example
  (`council/tests/fixtures/evidence/exmp-pass.json`) shows it. With real
  figures that division almost never comes out even, so record the share
  rounded once, half-up, to at least four significant digits (owner ruling
  AC41(2)): the gate recomputes the rounding at the figure's own decimal
  places and names the right figure if yours is off, and the freeze's note
  says the figure is rounded. The rule, whole: a quotient may be recorded
  rounded only when its id is in a share or yield family the floors name
  (`rounded_quotient_families`: ids starting `segment_revenue_share_` or
  containing `share_of_period` or `yield`) AND its `derived` block declares
  `rounded_places` equal to the places the value is written to — on every
  path, a quotient that comes out even included, and a correction re-strikes
  the figure at the declared places; every other derived figure stays exact. A business with one revenue line
  strikes its share the same way (its revenue divided by itself). Never write
  a line's own revenue in the share's place. The owner's documents print a
  recorded share at reading precision, a percentage to one decimal (owner
  ruling AC16(4)); a share written as a plain fraction prints as a
  percentage to one decimal (0.62 prints 62.0%), the exact figure kept in
  the fact's own entry; the change on a year ago is struck at reading
  precision from the recorded figures (unit READ-B1).
- **A revenue line points at revenue and nothing else (owner ruling
  AC12.3).** The ids under `how_it_earns[].facts` must be `revenue_q`,
  `revenue_prior_year_q`, anything starting `segment_revenue_`, or a fact
  struck from those (however many steps down), each with its member suffix
  inside an expression. The families are DATA, in
  `council/floors/floors.json` under `revenue_families`; widening them is an
  owner ruling, not a code change.
- **The rating measure follows the archetype (owner ruling AC15, P2 — a
  single listed name).** Declare the subject's `archetype`: a
  `profitable_operator` (rated on earnings against its own history and
  peers), a `ramping_infrastructure_builder` (rated on enterprise value per
  unit of contracted capacity and contracted revenue per unit — the TeraWulf
  case), a `stabilised_lessor` (rated on enterprise value to operating
  income), or a `no_earnings_asset` (which keeps the anchorless ladder and is
  legal only for an anchorless subject). Say why in `archetype_because`, at
  most 40 words, citing facts. Then put the `measure` that archetype calls
  for on the `rating_vs_history_or_peers` row: the table archetype→measure is
  DATA in `council/floors/floors.json` under `archetype_measures`. The
  measure's own numerator must be a fact the pack carries, and its
  denominator(s) too: name the subject's own tier-1 denominator fact ids in
  `subject_denominator_facts` — as many as the measure's `denominators_required`
  in the table — each a fresh number like the numerator. And the rating
  must be computable for every peer — the shared numerator
  (`peer_enterprise_value__<ticker>` or `peer_market_cap__<ticker>`) AND each
  denominator the row names in `peer_denominator_metrics`
  (`peer_<metric>__<ticker>`, exactly `denominators_required` — the earnings
  comparator such as `pe_ratio` for a profitable operator, contracted capacity
  and rent per unit for a ramping builder) — or the peer half is the declared
  `peer_` gap. A ratio is not computable from its numerator alone, on either
  side (architect ruling 2026-09-20).
  **Never rate a `model_transition` on the trailing revenue of the business
  it is exiting** — `revenue_q`, its prior-year pair, or an EV-to-revenue
  fact of the exited business on the rating row is refused.
- **A single name carries the cycle it depends on (owner ruling AC15, P4).**
  Set `cycle_dependence` to `identified` or `none`, with a
  `cycle_dependence_because` of at most 25 words. Where it is `identified`,
  carry a top-level `cycle` block: the cycle in one line (`name`, ≤25 words),
  why it matters (`why_it_matters`, ≤40 words), then either three to five
  dated `series` (hard cap five — each `id`, `source`, `as_of`, `unit`,
  at least eight `points` of `date`/`value` in strictly increasing dates, and
  a `refetch_url_or_source_line`) or a `gap` with its `reason`. It is
  EVIDENCE, never analysis: no computed indicator, no reading. A series is
  judged fresh against the class's price-freshness rule times ten. Where it is
  `none`, carry no `cycle` block.

Every id the frame names must exist in the pack: fact ids in tier-1, and the
two passages (`t2_capital_allocation`, and the market-structure passage the
`competitive_position` field names) in tier-2. Per member of a basket or a
theme, suffix the passage ids the way the facts are suffixed
(`t2_capital_allocation__achp`). The word limits are counted by the gate and a
breach names the count.

### 1.0a A financial institution (owner rulings AC28, AC30)

**Which firms qualify (AC30(2)).** A firm is a financial institution when a
prudential regulator sets the capital it must hold (a bank, a card lender, a
broker that owns a bank, an insurer, a reinsurer), when its product is managing
other people's money for a fee, or when it is a holding company whose assets are
mostly such firms. Card networks, exchanges, rating agencies, market-data vendors
and payments or fintech software firms are NOT: they stay `profitable_operator`.
The worked list and the custody-bank and card-lender cases are in
`docs/FI-ARCHETYPE-BRIEF-2026-09-23.md` §B0.

**The sub-type, and a hybrid's other engine.** Set `archetype:
financial_institution` and `fi_subtype` to one of `bank`, `insurer`,
`reinsurer`, `traditional_asset_manager`, `alternative_asset_manager`,
`financial_holding`; the ground goes in `archetype_because`. The sub-type is
where the binding capital requirement sits; for a capital-light firm, the engine
its own segment reporting shows as the largest. Declare the other engine in
`fi_secondary_subtype` with the segment facts that carry its share in
`fi_secondary_share_facts`.

**The measure and its facts.** The sub-type's row in `council/floors/floors.json`
(`archetype_measures.table.financial_institution`) names the `measure` to put on
the `rating_vs_history_or_peers` row, and `denominator_ids` names the fact ids
each role may use. Write `subject_denominator_facts` in the ORDER the rule reads
them: the capital (or, for a manager, the client assets) FIRST, the earnings
SECOND - a bank `tangible_common_equity` then `net_income_to_common_ttm`; an
insurer `equity_for_operating_roe` then `operating_earnings_ttm`; a reinsurer
`equity_for_roe` then `net_income_ttm`; a traditional manager `aum_period_end`
then `adjusted_net_income_ttm`; an alternative manager
`fee_earning_aum_period_end` then `fre_ttm`; a holding its one denominator,
`nav_total`. The peers carry the same metrics as `peer_<metric>__<ticker>`, or
the `peer_` gap is declared. The numerator is the market value of ALL the common
equity; where there is more than one participating class or exchangeable units,
carry `participating_share_count`, and declare it absent by design otherwise.

**Trailing four quarters.** A `_ttm` figure is a derived fact with its
arithmetic declared: the four quarterly columns of the latest supplement's trend
table (`sum`), or the full year plus the year to date less the prior year to date.

**Capital beside its requirement.** `fi_capital` names `ratio_facts` and
`requirement_facts` in their families (`cet1_ratio_` beside `cet1_requirement_`,
`solvency_ratio_` beside `solvency_requirement_`, and so on - each ratio beside
the requirement FOR THAT RATIO, same suffix), the `regime` (at most twelve
words), the `binding_constraint` (at most twenty-five) and, where carried,
`target_fact`. Some decisive metric must rest on a capital ratio (kind
`balance_sheet`). A capital `gap` with its reason is legal only for the two
managers, and for a holding whose regulated subsidiary is declared absent by
design. Write a ratio in the prose as a percentage ("15.2%" for a percent fact),
or it is marked as not traced to a recorded fact.

**The risk-cost line.** `fi_risk_cost`: `kind` `credit` for a bank,
`underwriting` for an insurer or reinsurer, any of the three - `none_by_design`
included - for a manager or a holding; its `facts` in the risk-cost families
(`provision_for_credit_losses_q`, `credit_cost_`, `combined_ratio_`,
`large_loss_actual_`, `reserve_development_`), and `because` in at most
twenty-five words.

**The earnings split.** Every `how_it_earns` line carries a `nature`: `spread`,
`fee`, `underwriting`, `investment`, `trading`, `performance` or `other`. The
lines still point only at revenue facts.

**A holding's net asset value (AC30(3)).** `nav_bridge`: each component with its
`name`, `value_fact` and `method` (`listed_at_market`, `company_reported_value`,
`carrying_value`), the `holdco_net_debt_fact`, the derived `nav_total_fact`,
where published the `published_nav_fact`, and the derived `discount_fact`. The
owned companies are not rated in the same sitting and every page says so.
Sufficiency checks the bridge as a chain of captured facts (AC28, AC30 G3): the
rating's one denominator is the bridge's `nav_total_fact`; that total is
derived, never typed in; every component's `value_fact` and the
`holdco_net_debt_fact` sit inside its arithmetic, directly or through a
subtotal; and the chain ends in recorded readings, not numbers written into the
capture. The discount's own history is the `nav_published_hist_`/`price_hist_`
floor: eight quarter-end pairs, or the gap declared absent by design. What no
machine can check is that the bridge lists EVERY holding the company owns - the
outside auditor and the owner carry that.

**The free-cash test (AC30(1)).** For a bank, insurer, reinsurer or holding the
second canonical test is answered by capital the firm can pay out and still stay
above its regulator's minimum: a `distributable_capital_` fact on the
`free_cash_flow` row, its arithmetic declared where derived. Carry NO operating
cash flow or capital spending for a bank - the capital-spending floor is lifted
for these four. A manager keeps the ordinary test.

**A model transition (AC30(4)).** Where `what_is_changing.kind` is
`model_transition`, the earnings and client-asset denominators are the
CONTINUING business's: the same id ending `_continuing`. The capital and
net-asset-value denominators are exempt.

**The regulator's own bad year (AC30(5)).** A bank inside a published
supervisory stress test carries its `stress_` facts (the stress capital buffer,
the minimum projected capital ratio, the projected loss rate); a bank outside one
declares `stress_` absent by design with the reason. They are evidence; nothing
reads them.

**Guidance (AC30(6)).** On every guidance row `guided` is the FIRST guidance for
that period; each later revision stands in `revisions`, oldest first, each with
its `date` and its `guidance_revised_<metric>_<period>` fact - a metric the row
guides, the row's own period, dated no later than the capture. A metric revised
more than once keeps that id for its first revision and adds `_r2`, `_r3` and on
for each later one, none dated before the one it follows. An empty list says
the guidance was never revised. Delivery is judged against the first.

**Decisive-metric kinds** (brief §D, a mapping, not a rule): capital ratio
`balance_sheet`; return on tangible equity or on equity `unit_economics`;
combined ratio `margin`; fee rate `pricing`; flows and organic growth `growth`;
credit cost `other`.

**The cycle.** Every sub-type has an identifiable cycle, so `cycle_dependence`
is `identified`. The per-sub-type series in brief §C are SUGGESTIONS, never a
rule. A quarterly series read at the sitting passes the freshness check though
its latest point is months old, so every page prints the last point's date
beside the date the series was read.

**The one-line question (AC32) - every capture, not only a financial
institution.** `question_line` is the owner's question as he asked it, on one
line, at most sixty words, uncut; the report's masthead prints it.

**Units and the question line (AC37 and its amendment, floors 1.10.0).** Every fact's `unit`
and every cycle series' `unit` must be on the floors' `allowed_units` list,
written exactly as listed (`USD_million` and `USD_millions` are both there;
`USD millions` is not). Any other unit refuses: "fact '<id>' has the unit
'<unit>', which is not on the floors' list of allowed units (allowed_units,
owner ruling AC37) ...". When a capture needs a unit that is not on the list,
stop and ask the architect: he adds a plain measure of the asset (a physical
quantity, a currency per such quantity or per share, a count, a rate, a
period) without asking the owner and records it in the floors' authority
note; any other unit goes to the owner. The `question_line` is checked for
contradiction, not vocabulary. The subject's name and ticker are first
taken out of both the line and `question_verbatim`, never cut from inside a
word: the name as typed, each of its words whole, in that order, in any
case, with nothing but spaces between them and an optional possessive `'s`
after it, touching no letter, digit or figure sign (a currency, percent or
comparison sign) on either side; only the name and its possessive come out,
and any other mark beside it stays and is read as usual (so `(Buy Corp)`,
`Buy Corp's` and `Best Buy—a retailer` are the name, but `buy, Corp`,
`xBuy Corp` and `$Buy Corp` are not);
the ticker only as a whole word written exactly as the subject block writes
it, capitals and all (a ticker `BUY` leaves the owner's own "buy" alone). So
the name stands in the line but a word of it standing alone allows nothing,
and a figure joined to the ticker (`EXMP-1`) is still checked whole as a
figure. The line then passes when every figure in it (whole, with its signs, so `$50` does not match `$50.5` nor
`<$50` match `>$50`), every ticker in it and
every decision word or negation in it - buy, sell, hold, long, short, add,
trim, exit, not, no, never, in any form (`buying` answers `buy`; every word
ending in `n't`, such as `don't`, answers `not`; words joined by a mark, as in `buy/sell`, are read apart) - is
in `question_verbatim`. Ordinary words are free. So
paraphrase freely, but add no figure, ticker or action the owner never
wrote; one that he never wrote refuses by name. Beware ordinary uses of the
decision words ("no debt", "the long history"): reword them if the owner's
question never uses that word.

Sources: brief §B (the per-sub-type facts and where to find them), §E (the floors)
and §F (the JPMorgan list). Do not copy their tables here.

### 1.0b A growth company that does not yet make a profit (owner ruling AC49)

**The four-quarters rule (AC49(1), AC50(1)-(3)).** A company is rated on its
earnings only when each of its four latest reported quarters shows an operating
profit under standard accounting - after stock pay and after one-off charges, no
"adjusted" figure. A company that reports only every six months needs its two
latest halves profitable. Anything less puts it on the growth path:
`archetype: reinvesting_grower`. The rule works both ways - a company with four
profitable quarters is rated on its earnings however fast it grows, and a grower
with four refuses as graduated. It governs `profitable_operator` and
`stabilised_lessor`, turnarounds and cyclicals included; the contract-based
infrastructure builder, the financial institution and an asset with no earnings
are untouched. The machine chooses from the quarters you record, never you; the
data is `archetype_measures.profitability_rule` in the floors, in force for a
capture made from 2026-09-27. No sales at all, or a loss on every sale
(negative gross profit), is refused openly (AC50(4)).

**The sub-type.** `grower_subtype`: `recurring_revenue` for subscription and
usage software; `transaction_platform` for a marketplace, a payments business
or consumer internet earning a cut of the volume that passes through it. Pick
by what the company's own segment reporting says most of its gross profit comes
from; the ground goes in `archetype_because`. The two share one measure and
differ in the evidence they carry.

**The quarters and their ids.** One member per quarter, the id ending in the
quarter's period: `revenue_quarter_<q>_fy<yyyy>`, `gross_profit_quarter_...`
and `operating_income_quarter_...` (for example `_q2_fy2026`), at least the
four latest, the newest being the latest report's quarter. A half-year reporter
writes its halves under the same prefixes (`_h1_fy2026`). Never mix quarters and
halves, and never two members for one period.

**The trailing sums, derived.** `revenue_ttm`, `gross_profit_ttm`,
`operating_cash_flow_ttm` and `capital_expenditure_ttm` are derived facts with
their arithmetic declared: the four quarters summed (`sum`), or the full year
plus this year to date less last year to date. `capital_expenditure_ttm` is a
spend, recorded as a positive amount; the machine refuses it below zero. Record
every figure the months of cash left are counted from in ONE unit.

**The yardstick (AC50(5)).** The `rating_vs_history_or_peers` row carries
`measure: ev_to_gross_profit_against_revenue_growth`,
`subject_denominator_facts: [gross_profit_ttm, revenue_ttm]` in that order, and
`answered_by` naming `enterprise_value`. Sales growth is the `revenue_q` /
`revenue_prior_year_q` pair. Record the yardstick's two halves, `enterprise_value`
and the gross profit, in ONE unit - sufficiency refuses a mixed pair by name.
A forward figure appears only where the company
itself guides it (`guidance_breakeven_` and the like); it is shown beside and
never rated on.

**The months of cash left (AC50(7), AC50(8)).** The frame's `growth_runway`
block: `cash_facts` (`cash_and_investments_mrq_end` - cash plus short-term
investments at the latest quarter end), `operating_cash_flow_fact`
(`operating_cash_flow_ttm`), `capital_expenditure_fact`
(`capital_expenditure_ttm`), optional `undrawn_facility_facts` (shown on every
page, never counted), `funding_because` (how it funds itself, at most
twenty-five words) and `funding_because_figures`. The machine works out the
months - never write them as a fact. Under the line in the floors
(`growth_runway.threshold_months`) the council may rate the company at most
hold, sell still open, and every page says so in one sentence. A company
generating cash is not burning it and passes. The cash, the burn and the growth
pair must each sit in some decisive metric's `answered_by`.

**Stock pay and the share count (AC50(6)).** `stock_based_compensation_q` and
`diluted_shares_q`, each with its `_prior_year_q` pair from the same filing's
comparative column. Stock pay is NOT subtracted from gross profit; the pages
print it beside the yardstick as a share of sales, with the share-count growth.

**The three standard tests (AC50(9) as amended).** `revenue_growth` (a new row
of kind `canonical_test`) answered by the growth pair and, where the company
reports it, an `arr_` fact; `profit_growth` answered by a `gross_profit_` fact;
`free_cash_flow` answered by the three runway facts. **Naming rule:** an id
starting `gross_profit_` carries an amount of gross profit and nothing else - a
margin or any other ratio goes under `gross_margin_`, never under
`gross_profit_`.

**By sub-type (AC50(11)).** Recurring revenue: `net_revenue_retention_`, `rpo_`
(remaining performance obligations) - each present or declared absent by design
- and `arr_` where reported. Platform: `gross_volume_q` with its prior-year pair,
or declared absent by design. Every grower: `convertible_notes_` (or absent by
design), and the yardstick's own history, `ev_hist_` beside
`gross_profit_ttm_hist_`, eight quarter ends, or the gap declared where the
company has been listed under two years.

**Peers (AC50(10)).** Growth companies of the same kind - subscription with
subscription, platform with platform - each carrying `enterprise_value`,
`gross_profit_ttm` and `revenue_ttm` as `peer_<metric>__<ticker>`, with its
`comparable_because`. A mature profitable leader appears only with
`not_comparable_on` saying why.

**A model transition.** Where `what_is_changing.kind` is `model_transition`, the
gross-profit and revenue denominators are the continuing business's, the same
id ending `_continuing`, and the rule reads the continuing business's quarterly
operating income (`operating_income_quarter_<period>_continuing`).

**Every revenue line carries a `nature`:** `subscription`, `usage`,
`transaction` or `product`.

**Traps, one line each.** An "adjusted" margin or "Rule of 40" before stock pay
is not standard accounting - record the reported figure. Recurring revenue and
retention are the company's own definitions - quote the definition in the
source. Billings are not revenue. A negative enterprise value (net cash above
the market value) is recorded as it is, never floored. Convertible notes are
dilution the enterprise value hides - record each issue's principal and
conversion price.

**The cycle.** Often identified (the long-dated discount rate drives these
valuations). The series in brief §2.1 - the ten-year real yield, the Nasdaq
Composite, a software sector fund - are SUGGESTIONS, never a rule.

Sources: `docs/ARCHETYPE-GAPS-BRIEF-2026-09-24.md` §2.1 (the facts and where
to find them). Do not copy its tables here.

### 1.0c An oil, gas or mining producer (owner rulings AC51-AC56)

**Who is a producer (AC51 R1, R2; AC52 R8).** A company whose sales come mostly
from oil, gas or metal it extracts under a reserve standard, or from royalties
and streams on others' output: `archetype: resource_producer`. Service firms,
refiners and pipelines are not producers; a company with nothing produced yet is
refused openly. **The three kinds**, in `producer_subtype`:
`oil_and_gas_producer`, `miner` (gold, silver, copper), `royalty_and_streaming`
(finances mines and wells for a share of the output). The ground goes in
`archetype_because`.

**The products (AC51 R3, AC56(1)).** The main commodity is one of the floors'
`resource_products`: `crude_oil`, `natural_gas`, `gold`, `silver`, `copper`.
Anything else as the MAIN product refuses with a shopping list. A by-product off
the list (zinc, lead, molybdenum) is named in `by_products` and shown apart.

**The rule both ways (AC51 R4).** A company that reports reserves (any tier-1
id starting `reserves_`) is rated as a producer - never as a profit-maker on
peak earnings, never as a grower in a loss year. The one exception is an
integrated oil major declared a profit-maker with its `integrated_major` block
(AC52(1) as amended; §1.1 names the arms' ids); its pages show its reserves and
today's `reference_price_` fact beside the profit yardstick.

**The `resource_base` block.** `product`, optional `by_products`,
`reserves_standard`, `reserve_report_date_fact`, `reserve_facts`,
`reserve_price_facts`, `production_facts`, `realized_price_facts`,
`reference_price_fact`, `unit_cost_facts`, and exactly one of `hedge_facts` and
`hedge_none_by_design: true`. Each field names ids of its own family (below).

**Reserves (AC52 R7).** The company's own share only; "resources" never
counted (`resources_` is shown, advisory). Oil and gas: `reserves_proved_boe`
(rated), `reserves_probable_boe` where published; miner and royalty company:
`reserves_pp_attributable` (proven plus probable). An id starting `reserves_`
carries a reserve amount and nothing else - a price goes under
`reserve_price_<product>`, a past year-end under `reserves_hist_`. Name the
category (`proved`, `probable`, `pp`) and, for a figure of one commodity, the
commodity in the id: the pages read both from it.

**Oil and gas shown apart (AC52 R6).** Beside the barrel-of-oil-equivalent total,
record `reserves_proved_crude_oil_bbl` and `reserves_proved_natural_gas_mcf`
(and each commodity's `reserve_price_` and `reference_price_` where carried):
every page prints them on rows of their own. A by-product's reserve and output
name it (`reserves_pp_zinc`, `production_zinc_ttm`) in the one unit the company
reports.

**The report date, the standard, the price deck (AC53 R9, R12).**
`reserve_report_date`: the latest annual reserve report's effective date,
`YYYY-MM-DD`, at most 456 days before the capture, else the sitting is refused.
`reserves_standard`: `sec_oil_and_gas`, `sec_s_k_1300`, `ni_43_101`, `jorc` or
`prms`. `reserve_price_<product>`: each price the reserves were counted at, in
the product's price unit. The council takes reserves as reported.

**Units (AC52 R6; the gas trap, F4).** Crude oil in `bbl`, priced `USD per
barrel`; gas in `mcf`, priced `USD per MMBtu`; gold and silver in `oz`, `USD per
ounce`; copper in `lb`, `USD per pound`. An oil and gas producer's rated
reserves and output are in `boe` (six thousand cubic feet to a barrel), its unit
cost in `USD per boe` or per barrel. The council converts nothing: gas counted in
cubic feet is never set against a price per million British thermal units, and a
pair in two units reads "not comparable in one unit". Record `enterprise_value`,
`operating_cash_flow_ttm` and every peer's in ONE unit - plain `USD` where the
reserves are counted in single barrels or ounces, or the value per unit of
reserves reads in millions per barrel.

**Today's price (B4).** `reference_price_<product>` from the benchmark the
product list names, dated at the sitting (freshness no looser than 3 days).

**Output and the price received.** `production_quarter_<period>` and
`realized_price_quarter_<period>`, one member per quarter (`_q2_fy2026`), the
four latest; `production_q` with `production_prior_year_q` and
`realized_price_q` with `realized_price_prior_year_q`, each pair from one
report.

**Cost per unit (AC54 R14, R16).** `unit_cost_<product>` in the words the fact
carries as its label: all-in sustaining cost (the World Gold Council definition)
for gold, operating cost per barrel for oil and gas. A royalty or streaming
company: one `stream_payment_` fact per stream, every one cited in
`unit_cost_facts` and named by `profit_growth`; `operator_concentration_` for
the share of income from its largest mine or operator.

**Hedges (AC53 R11).** `hedge_` facts - the share of next year's output under
contracts that lock in a price, and the average locked-in price - cited in
`hedge_facts`; or `hedge_none_by_design: true` with the `hedge_` gap declared
absent by design. Shown beside today's price, never netted.

**Derived, and the balance sheet.** `production_ttm`, `operating_cash_flow_ttm`,
`capital_expenditure_ttm` (a positive spend) are derived facts, arithmetic
declared. `total_debt_mrq_end`, `cash_and_investments_mrq_end`,
`asset_retirement_obligation` (oil and gas, miner); `standardized_measure` for a
US SEC filer in oil and gas (shown beside, never the denominator). The machine
works out reserve life and value per unit - never write them as facts.

**The yardstick and the tests (AC52 R5, AC54 R13-R14).** The
`rating_vs_history_or_peers` row: `measure:
ev_to_reserves_against_cash_flow_at_the_recorded_price`,
`subject_denominator_facts: [<the rated reserves id>, operating_cash_flow_ttm]`,
`answered_by` naming `enterprise_value`. `profit_growth`: `production_q`,
`production_prior_year_q`, `realized_price_q` and a `unit_cost_` fact (royalty:
every `stream_payment_`). `free_cash_flow`: `operating_cash_flow_ttm` and
`capital_expenditure_ttm` - all capital spending. A negative cash flow passes and
prints "negative, not a multiple".

**Peers and own history (AC54 R15).** Producers of the same main commodity and
kind, each with `peer_enterprise_value__<t>`, `peer_<reserves id>__<t>` and
`peer_operating_cash_flow_ttm__<t>` in the subject's units; an outsider only with
`not_comparable_on`. History: `ev_hist_` beside `reserves_hist_`, five year
ends, or the gap declared.

**Also.** A sale of a field or mine: `what_is_changing.kind: model_transition`,
the denominators ending `_continuing`. Every revenue line carries `nature`:
`commodity_sales`, `royalty` or `stream`, together more than half of revenue.
`cycle_dependence: identified`.

**Traps, one line each.** The standardized measure uses the SEC's twelve-month
average price, not today's. Hedges move the price received away from the
benchmark. All-in cost definitions differ (by-product credits) - quote the
company's. Write-downs of reserves and impairments. Country risk
(`jurisdiction_`, advisory). A stream's fixed payment per unit is not a mining
cost. An integrated major's refining and chemicals arms are not production.

**The cycle.** Always identified. The series in brief §2.2 - the product's own
price, crude stocks, the rig count, the broad dollar, and for precious metals the
ten-year real yield - are SUGGESTIONS, never a rule.

Sources: `docs/ARCHETYPE-GAPS-BRIEF-2026-09-24.md` §2.2. Do not copy its tables
here.

### 1.0d A holding company that owns other businesses (owner rulings AC59-AC62, AC65)

A listed company whose value is mostly investments in businesses it does not run
day to day, and which publishes the value of what it owns, declares
`investment_holding`. A conglomerate running its businesses stays a profit-maker.
Where banks, insurers and money managers make up more than half that value, use
the financial institution's `financial_holding` sub-type instead. Both are rated
on price against net asset value; the owned businesses are not rated here (H1-H2).

One listed holding above half is still a holding company. The front names it as
not rated in this sitting (H3). The rule works both ways: a holding company is
always rated as one; reported profits are shown and never decisive. A loss from
falling investment prices never makes it a growth company (H4).

Build `nav_bridge`: every listed investment at today's price; each private
investment at the company's own latest published value; subtract only the
holding company's own net debt. Print the company's own published net asset
value beside the council's (H5). For every private component name
`valuation_basis` and a value fact with its own `as_of`. The bases are listed
company comparisons, the latest funding round, forecast cash, a fund manager's
statement, cost, or another stated method. The council never re-values private
businesses. A value older than fifteen months refuses with a shopping list.
Book value is used only where nothing better is published, and labelled (H6).

The pack is recorded in ONE currency, the holding company's own reporting currency; a foreign-reporting holding is captured in its own currency.
A conversion is exactly one foreign figure times one dated `fx_rate_` fact, with the same scale and its result in the pack's currency (AC62 H16, AC65).
Every fact a floor names by id — the 52-week range, price, market value, holding-company net
debt, costs, cash flows and capital returns — is recorded in the pack's currency; a native
source figure takes an id of its own.

The market value, every bridge component, the net debt and the net asset value
use one unit string, including its scale. Count every share class in
`market_cap`, including both A and B shares (H16). Conversion arithmetic and
its dated exchange-rate fact stay visible; never convert out of the pack's
currency or out and back (AC65).

Record each of the last five financial year-end pairs as
`nav_published_hist_fyYYYY` and `price_hist_fyYYYY`, the company's published
value per share and the price that day, in one unit. A quarter-end does not
count. A younger listing declares its gap and shows what it has (H9). In the
weeks before the new annual report, an oldest member beyond the five-year
freshness ceiling is declared a gap; the ceiling is not widened.
The generated brief shows today's discount at today's prices and on the latest
published value, the annual discounts, their average and the ruled range phrase
(H10-H11). Do not describe a discount as cheap or dear in the evidence.

Capture the holding company's net debt and `holdco_costs_ttm`, plus the
`holdco_cash_flow_` facts for dividends received, costs, interest and dividends
paid. Capture dividends and buybacks too. The first standard test is net asset
value per share growth, dividends beside it and never added in; the second is
dividend cover; the third is the discount against its history and peers (H8, H13).
Peers are other holding companies on their own published value; a financial
holding needs a stated reason. Only this sitting's company is re-priced (H14).
Record every investment in the company's value table, largest first with its
share. The smallest are grouped as "other" when together under a tenth;
completeness stays with the outside evidence check and the owner (H15).
The private share, debt share and yearly costs share are calculated, never
rating caps; above half private, the front carries the ruled warning (H7-H8).

Watch these traps when gathering:

- Consolidated results and investment-entity reporting describe different things; use the published investment value table.
- Private marks can be stale, especially venture investments; preserve each date and method.
- Cross-holdings are shown as reported, never netted.
- A discount inside another discount stays visible in the underlying investment.
- A structural discount is evidence for the advisors to judge, never a claim it will close.
- Currency conversions need their own native figure, dated rate and pack-currency result.

Sources: `docs/ARCHETYPE-GAPS-BRIEF-2026-09-24.md` §2.5. Do not copy its tables here.
The first sitting's seed adds any exchange calendar or `SEK`
unit the listing needs; this page unit makes no such data change (charter F7).

### 1.1 Gather, then write the capture

**Listings outside the US.** The listing name as the broker writes it binds
the price series to the exchange calendar in the floors. Figures may be
recorded in the listing's currency; the one-currency-per-pack rule with dated
conversions is not yet ruled. Name the primary listing's broad-index ETF
benchmark per sitting (owner ruling AC4, unchanged); the floors provide no
non-US default.

Derive what THIS question needs: the four valuation tests for a priced
asset (profit growth · free cash flow · rating against own history or
peers · earnings/cash yield against the risk-free rate) plus whatever the
owner's thesis turns on, on top of the ruled floors in
`council/floors/floors.json` (floors 1.19.0). A producer's by-product off the
floors' product list (zinc, lead, molybdenum) is shown apart: its reserve and
output figures name it and sit in one unit of quantity (`by_product_units`), never converted
or counted in the rating (owner ruling AC56(1)). A royalty or streaming
company's first standard test names every `stream_payment_` fact its resource
block cites, one per stream (owner ruling AC56(2)). An integrated oil major declared a
profit-maker names each arm's share of capital employed by the fact id's
prefix: `capital_share_upstream`, `capital_share_refining_and_marketing`, and
`capital_share_midstream` where the company reports midstream on its own.
Gather live: filings WITH their
prior-year comparatives, guidance, the dated events calendar, the risk-free
rate, market data from the broker, short interest where the class has it, and
— new at floors 1.3.0, all conditional, so present or declared absent with a
reason — segment revenue (`segment_revenue_*`), the guided figure beside the
delivered one (`guided_*` / `delivered_*`), the peer set (`peer_*`), and what
management owns (`insider_ownership_pct`). Two more are advisory and never
block: `ceo_tenure_years` and the published consensus
(`analyst_consensus_*`). New at floors 1.7.0 (owner ruling AC4), for a single
stock and also conditional: insiders' dealings over the last twelve months
(`insider_flow_*`, a US name's Form 4 filings) and the company's own buying of
its shares (`buyback_*`) — each present, or declared absent-by-design with the
gap's `fact_class` exactly `insider_flow_` or `buyback_`; a gap with any other
reason reads as a gathering failure and refuses, and what management owns
(`insider_ownership_pct`) does not answer the insider-dealing floor. Made real
at floors 1.8.0 (owner ruling AC35(2)): the buyback floor reads only
`buyback_spend_<period>` — the amount actually spent on repurchased shares in
that period, dated at the period end (`buyback_spend_q`); an authorisation
(`buyback_authorisation_remaining`) or a yield alone does not answer it, and a
share count may ride beside it as `buyback_shares_<period>`. The insider floor
reads only dealings, one set of three facts per Form 4 dealing sharing a suffix
`<n>`: `insider_flow_direction_<n>` (`buy` or `sell`, unit `direction`),
`insider_flow_date_<n>` (the trade date `YYYY-MM-DD`, unit `date`) and
`insider_flow_size_<n>` (the shares traded, unit `shares`); a dealing missing
any part refuses by name, and a summary such as `insider_flow_net_shares_12m`
may ride beside but answers nothing. The two gap classes are now exactly
`buyback_spend_` (no repurchase programme) and `insider_flow_direction_` (no
published dealings, or none in the window); the old `buyback_` and
`insider_flow_` gap classes no longer lift anything. The gate checks every
fact under either prefix for its shape and its unit, and anything else refuses
by name. A fact id carries its period or its number after the prefix (a bare
`buyback_spend_` or `insider_flow_direction_` refuses), and every value is read
exactly as stored, so a stray space or line break refuses too. A spend is a positive amount dated not after the capture, in a currency
unit (`USD`, `USD_million`, `USD_millions`, `USD_m`, `USD_thousand`,
`USD_billion`, `USD_billions`, `US$m`, `EUR` or `EUR_b`); the one exception is a
spend of exactly zero, which may ride beside a spend that counts and is not
itself counted. Every dealing's direction reads exactly `buy` or `sell` (unit
`direction`), its date falls within the twelve months before the capture (366
days, unit `date`), and its size is positive in `shares`, `thousand_shares`,
`thousands_of_shares` or `million_shares`; a dealing with any part wrong is not
counted at all.

**The holder-structure test comes first (floors 1.12.0, owner rulings AC41(1)
as amended of record and AC47).** Before gathering any dealing, record what
the officers and directors together own, from the proxy's security-ownership
table: `insider_ownership_pct` in `%` (where the proxy prints only a "less
than" line, record that figure with a `ceiling` bound naming the published
line), or the group row's shares as `insider_group_shares` beside the shares
in issue (`common_shares_outstanding`, `shares_outstanding`,
`shares_outstanding_mrq_end` or `shares_common_outstanding`) in the SAME
unit; where two shares-in-issue figures disagree the smaller decides, and a
group figure published as "more than" or "less than" carries its bound and
decides only the way it points. The group row counts as it stands: shares the officers and directors
control through trusts and holding companies count, a family holding outside
that row does not. Then the depth, against the threshold the floors carry
(`depth.threshold_pct` on the insider floor):
- **Under the threshold:** the three summary facts, each dated at the capture
  and each source naming the method - the Form 4 filings in the twelve months
  before the capture, which rows were counted, how the value was summed:
  `insider_flow_summary_count` (the number of dealings, unit `count`, a whole
  number above zero), `insider_flow_summary_direction` (`buy`, `sell` or
  `even` by net shares, unit `direction`) and `insider_flow_summary_value`
  (the total value of the dealings, bought plus sold, in a currency unit the
  buyback floor names). Beside them, every dealing by the company's own chief
  executive (both, where the company has two co-chief executives; a division
  head with a chief executive title does not count), its finance chief and
  its chair, each as the three dealing facts with the role in the id ending:
  `ceo_<n>`, `cfo_<n>`, `chair_<n>`. One person in two roles is recorded once,
  under the first of `ceo`, `cfo`, `chair` that applies. A window with no
  dealing is declared (the `insider_flow_direction_` gap, absent-by-design),
  never summarised as nothing.
- **At or over the threshold:** every dealing, as above. Carrying every
  dealing meets the floor at either depth - more is never less - and a
  summary alone refuses at this ownership, naming the holding it found.
- **The ownership cannot be established** (no percentage is published and no
  share counts pair): declare the `insider_ownership_pct` gap absent-by-design
  and gather NO `insider_flow_` fact. The floor does not apply, the council
  rules without the insider evidence, and the approval document, the report
  and the seats' case file say once that insider information was not
  available and was not considered. A pack that carries an insider fact beside
  an unknown ownership refuses.

The gate checks each summary part's shape, unit and date (the capture's own
day) wherever a summary is carried, not its truth, and never
that the three officers' dealings are complete - both are the gatherer's
duty, stated here.

**The financial-year end (floors 1.12.0, owner ruling AC46(2)).** Every
single-stock capture records `fiscal_year_end`: the month and day the
company's financial year ends, written `MM-DD`, unit `month_day`, from the
cover of the latest annual report. The gate asks it of every capture made on
or after the floor's `applies_from` date; a capture made earlier - every
capture on record - is never asked.

**The third canonical test keeps its id `rating_vs_history_or_peers` and its
meaning — but peers are now EXPECTED wherever a peer set exists, and it now
carries the `measure` its archetype calls for (owner ruling AC15, P2, above).**
The subject's own history alone cannot say whether the whole industry
re-rated; answer the test against both where you honestly can, on the measure
the business archetype demands.

Write one capture JSON per `council/schemas/capture_schema.json`. The
rules that matter most in practice:

- The broker is a MARKET-DATA source only. Never call the two calls that
  read the owner's book; the gate refuses sources naming them.
- **The daily price series reaches the capture through the helper, never through your own
  reading.** A gatherer seat makes the broker's price-history call — for the subject and, where
  one is ruled, the benchmark — so the long reply lands in that seat's transcript, not in yours.
  Then run, once per series, on that seat's own transcript
  (`subagents/agent-<id>.jsonl` beside your session's):

  ```
  python -m council.evidence.series <agent-transcript.jsonl> --contract <id> --ticker <T> \
      --calendar <C> --as-of <D> --source "<where it was read>" \
      --last-date <the last finished session> --out <file>
  ```

  and paste the object it writes as `price_series` or `benchmark_series`. It takes the last
  reply for that contract, copies every close and volume exactly as the broker wrote it, and
  drops any bar after `--last-date` (a day still trading). Never retype a bar.
- Every figure is the exact string observed — never round, never reformat. One exception is
  the broker's float noise: a figure that comes back as the full digits of a single-precision
  number (a price with a long tail of digits where the quote shows two places) is refused at the
  gate — as a fact's own value or as a figure written inline in a derived fact's arithmetic —
  and the gate names the short figure to write; write that and quote the broker's digits in the
  source.
- The previous close is the price series' last bar, never a snapshot field: the broker's
  snapshot has returned an empty previous close.
- Give every tier-1 fact a plain `label` of at most eight words: its plain name, never its id,
  on one line (owner ruling AC15, P5). The gate refuses a longer label, so write them short
  the first time.
- A derived figure declares `derived.operation` + `operands`; the gate
  recomputes it exactly and the freeze generates its equation sentence.
- A prior-period comparative is dated by the CURRENT filing that
  republishes it (its own fact family, longer freshness rule).
- **A dated record of a finished period is current for five years (owner ruling AC41(3)).**
  A first guide or a revision for a period now reported, a delivered figure, a filed report for
  a finished quarter or year, a past year-end balance: date it by the document you read it
  from, and give it the floors' `freshness_ceiling` → `closed_period_record_rule_days` (five
  years, 1,826 days) as its `freshness_rule_days`. Everything else keeps a rule matching how often it is
  republished. The gate refuses any rule longer than 1,826 days, so a record older than that is
  too old to carry. That is five calendar years as the floors count them; across a century year
  that is not a leap year the span is one day shorter, so a record could count as current one
  day past its fifth anniversary, first reachable by a sitting in 2101 (the floors' own note,
  accepted).
- A shut market is legal and disclosed: `market_state.state = "closed"`
  plus a plain `disclosure` sentence — it reaches the seats.
- Every Tier-2 passage states its figures literally in its own text. The
  `figures` list is a HAND-WRITTEN, curated assertion of the figures that matter, written in the
  same format as the passage prose (grouped thousands included) — never a mechanical dump of every
  numeral in the text (MAC-5).
- Tag each Tier-2 passage's `category` from `business`, `peers`, `price`, `positioning`,
  `calendar`, `cycle`, `general` — `general` where none fits (capture contract 1.9.0). Each
  advisor's case file places the passages its lens reads first at the top; every seat still
  reads every passage, and the reviewer, the chairman and both outside calls read capture order.
  Every seat, the outside challenger and the evidence auditor read the facts' sources through a
  numbered index before the fact table: text that several facts' sources repeat is printed once in
  an entry, and each fact's line carries the rest of its source verbatim - usually its page, line
  or column, sometimes also its address or saved file; one document can take several entries, and
  a source no other fact repeats stays in full. The owner's one-page brief, full document and
  report page keep full citations.
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
  written to an older contract (`capture_version` 1.2.0) and carries neither
  the tags nor a business frame, because runs on record are never rewritten.
  Your capture is 1.12.0 and needs both. The migrations are set out in
  `council/tests/test_evidence.py`, `to_contract_1_4_1` through
  `to_contract_1_12_0`, and the same file prints
  exactly which frame rows the two single-name sittings on record would have
  needed.
- **The four sizing facts, in the units the hand-off is pinned to (ruling
  AB23(6)).** Atlas reads the sizing rows by id and cannot ask what a number
  meant, so each id now carries ONE unit and the chairman is refused if he
  states another: `realized_volatility` and `implied_volatility` in
  `fraction_annualized` (0.52 means 52% a year), `beta_vs_market` in `ratio`,
  `liquidity` in `USD_per_day` (the value traded on an average day),
  `event_dates` in `iso_date` (a date, or several — never a sentence about
  the calendar), `drawdown_shape` in `fraction_of_price` (0.35 means a 35%
  fall). The chairman quotes a single cited fact EXACTLY, so **capture the
  facts these rows will quote in those units** and the sitting is easy.

  Two escapes exist and no others. A reading computed from several facts is
  stated in the pinned unit by the chairman, citing every operand. And a
  fact carried in PERCENT may be published as its own fraction — the one
  restatement the contract allows, because the anchorless bar insists on
  reading its volatility fact as a percentage (`council/engine/ladder.py`)
  while the hand-off publishes the same reading as a fraction; the machine
  checks that arithmetic and nothing else is taken on trust. A unit that
  merely fails to say what it measures — `ratio` on an annualized
  volatility, `US$m` on a turnover — buys nothing: the row is refused, and
  the chairman's only honest move is to set the value null and explain the
  gap. Capture it right instead.
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

### 1a. The outside auditor reads the evidence — before any seat is paid (owner ruling AC2)

**One paid call, and it happens here.** A model outside this council's own
family reads the whole record and says what is missing, what looks wrong and
what is misread. It audits: it never gathers, and it never writes the frame.
You answer every point it raises, on the record, before the sufficiency gate
will let a council sit.

`<run>` below is the sitting's own working folder, and it is **not**
`<runs_root>/<run_id>`: `host init` (section 3) creates the run directory
itself and refuses outright if one already exists, so anything written under
that path before the host starts stops the sitting dead. Stage the evidence
work anywhere else and move it in beside the run afterwards, the way every
sitting on record did.

**Where to stage, and how many sessions (owner ruling AC15(5)(d), and the
debrief's own lesson):** stage under a folder in the repository's ignored
`scratch/` directory, or under `$HOME` — **never `/tmp`**. `/tmp` was cleared
during the WULF sitting's five-day pause and took the builder's scripts with
it; the `$HOME` staging survived. And **one session, one working tree**: a
second session on this repository works in its own `git worktree`, never in the
same checkout — two sessions in one tree corrupt each other's work (the debrief
found the tree checked out on `main` underneath a running sitting).

Run the cheap gate first — there is no sense paying to audit a capture that
contradicts itself:

```
python -m council.evidence.gate <capture.json>
python -m council.bridge.codex_bridge evidence <capture.json> <run>/evidence/challenge
```

The command builds the brief, sends it on stdin, and writes what came back into
`<run>/evidence/challenge/`: `brief.md` (exactly what the auditor read),
`request.json`, `response.json`, `events.jsonl`, `probe.json` and `result.json`. Where the
capture carries a daily price series, the brief also shows the auditor the price table the freeze
will compute from it, figure by figure, so a missing moving average is never raised as a gap. It runs the
standing smoke test first and refuses the paid call if that fails or lists a forbidden tool
(see "The challenger's tool posture", §3 step 5). **One audit
per sitting:** a `result.json` that already stands refuses a second call, the
same rule the verdict challenge lives under. Deliberately re-dispatching means
deleting that file first.

The auditor may raise only five kinds of point, and each carries a severity:

| Kind | What it means |
|---|---|
| `missing_decisive_fact` | a fact this business and this question turn on that the pack does not carry |
| `suspect_figure` | a value inconsistent with another, stale, mis-united, or implausible for this filer |
| `framing_error` | the frame reads the business wrongly |
| `missing_checklist_row` | a requirement the checklist should carry and does not |
| `source_doubt` | it read the source itself and that page prints a different figure |

`blocking` means the council cannot honestly sit until the point is answered;
`material` means the answer could change; `minor` is worth recording.

**Then answer every point.** Write `<run>/evidence/challenge-resolution.json`,
one entry per finding id:

```json
{"resolutions": {
  "E1": {"disposition": "captured", "fact_ids": ["rent_per_megawatt_q"]},
  "E2": {"disposition": "gap_declared", "reason": "the filer publishes it annually only",
         "weakened_test": "profit_growth"},
  "E3": {"disposition": "overruled", "reason": "at least twenty-five words saying why this
          particular objection does not hold on this particular record"}
}}
```

- `captured` — you went and got it. Name the ids you added **or changed**; the
  gate refuses a `captured` answer that names a fact nobody can read, and
  `evidence-record` refuses one that names only figures the pack already carried
  unchanged — that is not gathering, it is pointing. Where you went, looked and
  the auditor was simply wrong, the honest answer is `overruled`.
- `gap_declared` — you could not get it. Name BOTH the reason and the test the
  absence weakens; sufficiency refuses a declared gap missing either, because an
  absence nobody explains answers nothing. Add the ordinary `gaps` row too where
  the class has one; either way the declared-gaps section says how many points
  you conceded and sends the reader up to the audit, where each is named with
  its reason and the test it weakens, so nothing can say "None declared" while
  a gap stands, and no absence is counted twice.
- `overruled` — you disagree. A point of ANY severity set aside in fewer than 25
  words refuses at sufficiency: 25 words is what it takes to say why a specific
  objection is wrong, and "disagree" is not an answer.

A figure the auditor quotes from a source is a DOUBT, never a fact. Capture it
yourself, with its own source and date, before it enters the record.

**Then record it into the capture**, so the freeze's hash covers what the
auditor said and what you answered:

```
python -m council.bridge.codex_bridge evidence-record <capture.json> <run>/evidence/challenge
```

(`--resolution <path>` if your answers are not at
`<run>/evidence/challenge-resolution.json`.) This writes the `evidence_challenge`
block into the capture — never copy the auditor's words in by hand. Re-run the
gate afterwards, then carry on to section 2.

**It lists everything that moved after the auditor read the evidence** (owner
ruling AC13.2). Gathering what a finding asked for is expected; so is a figure
re-read at the source, a passage corrected, a fact dropped. The command holds
both readings of the evidence — the one it sent and the one on disk now — so it
writes the list itself: every fact or passage that changed, was added or was
removed, with what the auditor saw and what you are asking the council to sit
on. That list goes into the pack's audit block, into every seat's case file and
onto the owner's report, open on the front page when a change touches a decisive
metric or one of the three headline pairs. Nothing here refuses you; what
refuses, at sufficiency, is a pack whose evidence moved with an empty list
beside it — which is what happens if you edit the capture AFTER recording. So
record LAST: gather, correct, then run this command.

Two bindings do still refuse, and both are about recording an answer into the
wrong pack: the file path the audit was made against, and the subject and the
question inside it. Facts may move between the audit and this command; the pack
may not become a different pack.

**Re-dispatching the auditor is allowed, and both calls are counted.** To call
it again, delete `challenge/result.json` and run the command again; the log of
attempts beside it is not deleted, so the new result carries every call this
sitting has made. `evidence_challenge_tokens` in `capture-usage.json` is then
the SUM of them — `host init` adds up what the bridge recorded and refuses a
sidecar that names only the last one (register item P-U3-14).

**Every pass is kept whole (owner ruling AC15, the per-pass archive).** A
re-dispatched audit no longer overwrites the first: the bridge keeps each pass
in `challenge/result.pass<N>.json`, and `evidence-record` keeps each answer in
`challenge/resolution.pass<N>.json` and writes the archive into the capture's
`evidence_challenge` block — `prior_passes` holds every earlier pass whole
(its findings AND its dispositions), with the current one marked `current_pass`.
The debrief's own two-pass sitting lost pass 1's dispositions to an overwrite;
that can no longer happen.

**A correction goes back to the auditor as a DELTA, never the whole pack again
(owner ruling AC15, P8).** After you correct the pack (section 2b) with a
correction the command calls *rebuilding*, re-audit only the change:

```
python -m council.bridge.codex_bridge evidence --delta <capture.json> <run>/evidence/challenge
python -m council.bridge.codex_bridge evidence-record <capture.json> <run>/evidence/challenge
```

`--delta` shows the auditor only the changed facts, the figures struck from
them, and the frame passages that cite them, with the prior pass's findings
staged — not the whole record. Delete `challenge/result.json` first, exactly as
for a full re-dispatch. `evidence-record` marks the correction re-audited, and
the sufficiency gate then lets the pack sit. A *narrowing* correction needs no
delta re-audit and the command says so.

**The record also carries the call's own token** (owner ruling AC13.3). The
bridge mints a one-time token for every evidence call and knows the hash of the
evidence it sent; both go into `result.json` and this command copies them into
the block. Sufficiency refuses a block that carries neither — it raises the cost
of typing an audit that never happened. It does not make one impossible: this
session writes every file in that folder, and no check on this disk can prove a
paid call was made.

**If the call fails** — no `codex` on PATH, a smoke failure, a timeout, an
answer outside its schema — record it anyway. The block says `failed` with the
status word AND the bridge's own reason, which the owner's page prints (the
seats read only the one sentence: the reason can carry the outside model's own
words, and no seat prompt takes those unfenced), sufficiency passes, every seat is told in one sentence that nothing here
was checked by a second model, and the report's front page says so too. The
sitting is not stopped by a failed audit; it is stopped by an unanswered one.

**Skipping this step is not one of the choices.** Sufficiency refuses a pack
that carries no audit at all: a call nobody made is neither a success nor a
recorded failure, and the whole point of ruling AC2 is that no seat is paid
until a second model has read the evidence or has demonstrably failed to. A
machine with no `codex` records the failure above and sits.

**A basket or a theme gets ONE audit over the whole pack**, not one per member.

### 1b. Write down what the gathering cost (owner ruling AC3)

The seats have always been charged for; the stage that gathers the evidence
was the one nobody counted. When the capture is done — including the outside
audit above and any re-gathering its findings caused — write:

```
<run>/evidence/capture-usage.json
{"tokens": 412000, "minutes": 38.5, "model": "<the model that captured>",
 "estimated": false, "evidence_challenge_tokens": 74000}
```

`tokens` and `minutes` are the capture session's own accounting and are
required — `host init` refuses a sitting without them, in either mode.
`estimated` is required too (owner ruling AC15): `true` where the token or
minute figures are an ESTIMATE rather than a count — a session token counter
that was reset means the true figure cannot be known, so the honest flag is
`true` — and `false` where they are counted. The report prints "estimated"
beside the figures where it is true, so an estimate is never read as a count.
The WULF sitting's ~700,000-token capture cost was an estimate that nothing on
record marked as one; this flag closes that.
`evidence_challenge_tokens` is what the outside auditor cost, from
`<run>/evidence/challenge/result.json` — the `usage_tokens` of a single call,
or the SUM over that file's `attempts` list where the auditor was re-dispatched.
Copy that number exactly, because `host init` adds the attempts up itself and
refuses the sitting when the two disagree, naming both and how many calls it
counted. How many bytes of prompt that call was actually given is the
bridge's own count in the same file (`prompt_bytes_sent`); the host publishes
that and never measures the page on disk, which proves nothing about what
reached the other side. These figures are reported BESIDE the sitting's
1.5-hour clock, never inside it.

## 2. Gate, freeze, sufficiency (cheap, before any seat is paid)

```
python -m council.evidence.gate <capture.json>
python -m council.evidence.freeze <capture.json> <out_a> <out_b>
python -m council.evidence.sufficiency <out_a>/pack.json --out <out_a>/sufficiency-result.json
```

Freeze builds twice and must report byte-identical with one hash (recorded
in `<out_a>/freeze-record.json`).

**The tape is computed here, at the freeze (spec U4.3, owner ruling AC4).**
When the capture carries the subject's daily closes (`price_series`, and the
ruled benchmark's `benchmark_series` beside it), the freeze turns them into
25 tape figures and appends them to the pack's tier1, each a derived fact
(`series_stat`) with its window in trading days, its arithmetic printed as
its note, and a plain-English label the owner's evidence document prints:
the price against its 50-, 100- and 200-day averages; the 200-day average's
slope over 60 days; the place in the 52-week range; the fall from the
52-week closing high; the price return over 21, 63, 126 and 252 trading
days, and the same four against the benchmark; realized volatility over 21,
63 and 252 trading days; recent volume against its usual level; the largest
one-day fall, the highest and the lowest close in 52 weeks; the days
closing above the 200-day average; and the 50-, 100- and 200-day average
prices themselves, so a seat can name the level (the report page's tape table
keeps its fifteen rows; its chart draws each average as a line). A figure the history is too short for
(or, on an absolute sitting, a figure against a benchmark) becomes a
declared gap. Never write a tape figure by hand: the gate recomputes every
one from the series and refuses any that differs. The broker's price-history
call is a MARKET-DATA call and is allowed for the series; the two calls that
read the owner's book stay forbidden. Each tape figure takes its unit from
the `price_last` fact, which a capture with a series must carry, and its
freshness rule from the series: fresh for as long as the gate accepts the
series itself. A capture without a series freezes exactly as before. A sufficiency refusal (exit 3) is itself
the product: what is missing, why, where it likely lives — fix the capture
and repeat. No seat is paid before it passes.

## 2a. The one-page brief, the FULL document, and the go (owner ruling AC3, AC15)

```
python -m council.evidence.brief <out_a>/pack.json --out <run>/evidence/brief.md
python -m council.evidence.brief <out_a>/pack.json --out <run>/evidence/EVIDENCE-FULL.md --full
```

The one-page brief is deterministic text out of the frozen pack — no model call,
nothing on the page that is not already in the pack. Every figure reads in the
report's market form ($84.20, 6.8%, 18 Nov 2026); the full document prints the
exact recorded value beside it in each fact's own entry, and the pack itself stays
exact. It is one page: the question, what the business is, the numbers that decide
it (one small table), what the outside model asked for in the evidence check and
what happened to every point, what the record admits it does not carry, the price
against its 200-day average and its 52-week range, the dated events by name, and
what the gathering cost. The command reads `capture-usage.json` from
the folder it writes into, so §1b comes first.

**The full document is what a person actually approves (owner ruling AC15,
P6).** `--full` renders the WHOLE evidence for a reader — the one-page brief as
its summary at the top, then the business frame, every fact (by its plain-English
label where the capture wrote one, never the machine key), every passage, every
gap, every auditor finding and its resolution, and the checklist, nothing
trimmed. The one-page brief was never fit to approve: it is bounded to one page
and cuts mid-figure. The full document is the one the reviewer reads and says go
on.

**The same `--full` command writes the page he reads it on (owner ruling
AC40(2b)).** Beside `EVIDENCE-FULL.md` it writes `EVIDENCE-FULL.html`: the same
text, rendered from the Markdown's own bytes, in the report's look, one file that
opens from disk and fetches nothing. The owner cannot open Markdown — give him
the PAGE, and open it for him on the Mac:

```
open <run>/evidence/EVIDENCE-FULL.html
```

Do not send files through the app's file card: they do not save on his machine
(recorded 2026-09-24). The command refuses, and writes neither file, when some
other file already stands at the page's path. Never render a page by hand.

**Generate both in BOTH modes.** In auto-mode nobody reads them and the council
sits; both are still part of the record. `host init` now refuses an
**unattended** sitting whose full document is missing too (owner ruling
AC18(2)): no person approves it, but it must exist as the record of what the
council sat on — and it must BE the rendering of the pack the council was
handed, not a stale document from another pack. Missing, and init names the file
to produce; from a different pack, and init refuses and names the command to
regenerate it — no run is created either way.

**In `reviewed` mode the sitting now stops.** Give the FULL document — its
page, opened as above — to the person who chose that mode. Nothing is paid until he writes, in the same folder:

```
<run>/evidence/approval.json
{"by": "<his name>", "at": "<iso now>", "note": "<what he checked or changed>",
 "document_sha256": "<sha256 of the EVIDENCE-FULL.md he approved>",
 "pack_sha256": "<the pack's sha256, printed at the head of EVIDENCE-FULL.md>"}
```

The note may not be blank — an approval that says nothing records nothing. Both
hashes are required and both are checked, because the go is taken ON this
evidence (owner ruling AC3): a go that cannot be tied to the exact document and
pack the council sits on is not that go. Record the `document_sha256` of the full
document he approved (`shasum -a 256` on the file) and the `pack_sha256` of the
pack it summarizes — it is printed at the head of EVIDENCE-FULL.md, so he copies
the one he actually read. The `document_sha256` stays the MARKDOWN's hash, never
the page's; the page prints that same hash at its foot. `host init` refuses a reviewed sitting whose full
document is missing, whose approval omits either hash, whose `document_sha256` no
longer matches the document on disk (it was rewritten after he read it), or whose
`pack_sha256` is not the pack the council was handed (the go was taken on a
different pack) — so nobody can approve one document, or one pack, and sit on
another. It also re-renders the full document from the pack it was handed and
refuses unless the bytes match the one approved, so a document whose head line
names this pack while its body was rendered from a different one is caught too.
**Approve and sit on the same code:** because init re-renders with the code it
runs, a document approved before a change to how the document reads (a merge such
as READ-B2) is refused after it — re-run the `--full` command and take a fresh go
on the new document.
In the reviewed mode it refuses, too, a missing `EVIDENCE-FULL.html` or one that
is not the rendering of the approved Markdown — so the page he read is provably
the document he approved — and it copies the page into the run beside it.
In the unattended mode a missing page is allowed, but a page that is there must
be the rendering of the full document too, or init refuses: the run never files
a page of some other document.
The 1.5-hour clock starts at the approval moment, so the wait costs the
sitting nothing. An `approval.json` beside an `unattended` mode is refused rather
than guessed at: one of the two would be a lie about who saw the evidence.

## 2b. Correcting a fact WITHOUT rebuilding the pack (owner ruling AC15, P7)

**A correction never rebuilds the pack in full — that is the owner's absolute
rule.** When a figure is wrong, patch it in place and re-run only the cheap
deterministic chain:

```
python -m council.evidence.correct <capture.json> --set <fact_id>=<value> [--source <text>] [--reason <text>] [--by <name>] --out <out_a>
```

It sets ONE fact's value in place, re-strikes every derived figure that rests
on it (so a stale figure is never left behind), records the correction on the
capture's `corrections` list, and re-runs gate → freeze → sufficiency → brief
with **no model call**. Source documents are not re-read and nothing is
re-gathered; the command prints which facts' readings the change made stale, for
you to re-gather by hand if the change is not itself a re-reading (give
`--source` when it is). Correct a fact the seats reason from — one the business
frame's reading rests on, or a headline figure — and the command calls the
correction *rebuilding* and refuses to let the pack sit until you run the delta
re-audit of section 1a. Correct a peripheral figure and it *narrows*: no
re-audit, and the chain re-runs green at once.

A correction also removes, from the capture's folder, the approval, the one-page
brief, the full document AND its page (`EVIDENCE-FULL.html`): no stale page
survives a changed fact. Run the `--full` command again for a fresh document and
page, and take a fresh go on it.

You never `--set` a derived figure directly; correct the fact it is struck from
and it is re-struck for you. A correction whose re-strike would turn a division
into a non-terminating decimal is refused whole — correct that figure with its
own source instead.

## 3. The council (the stepped host + your dispatches)

```
python -m council.engine.host init --runs-root <dir> --run-id <id> --pack <pack.json> --pack-sha256 <hash> --sufficiency <sufficiency-result.json> --question-file <question.txt> --subject-json <subject.json> --evidence-dir <run>/evidence
python -m council.engine.host step <run_dir>
python -m council.engine.host status <run_dir>
```

`--evidence-dir` is the folder §0, §1b and §2a wrote into. `init` refuses
without it, copies `mode.json`, `capture-usage.json` and any `approval.json`
into the run beside the pack, and records all three in the run record — so the
run says on its own what was decided and spent before it existed. None of them
is inside the pack's hash: the pack is the evidence, and who chose and who
approved is provenance. The report's front page prints either "Reviewed by
&lt;name&gt; before the council sat." or, in the warning style, "Auto-mode: no
human reviewed the evidence before the council sat."

### Seating the council (owner ruling AC24)

Which model and effort each seat runs on is a setting, not a rule. The
suggested defaults live in `council/floors/seats.json`: the five advisors,
the reviewer and the frame writer on `claude-opus-5-5` at `high`, the
chairman (draft and resolve) at `xhigh`, the outside challenger `gpt-6-sol`
at `high`. Nothing a seat DOES changes with its model.

- **Claude seats.** You launch them, so you seat them: dispatch each on the
  file's model and effort unless the sitting's dispatch says otherwise. An
  override (a different effort, a higher model tier) is stated in the
  dispatch, seat by seat, and each seat's usage sidecar records the model it
  actually ran on (step 3 below) — that is what the verdict's
  `models_per_seat` shows.
- **The challenger.** The council writes the file's choice into both outside
  requests. To override it for a sitting, set `COUNCIL_CHALLENGER_MODEL`
  and/or `COUNCIL_CHALLENGER_EFFORT` in the environment of every `host step`
  and `codex_bridge` command. The model the request named is what the
  verdict records as `challenger_model_requested`.

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

   **The chairman's document is also measured for the council's writing rules**
   (owner ruling AC6, spec U6.4). Over a threshold, or over the rationale's word
   cap, the host re-asks the chair ONCE with the hit list — "rewrite these
   sentences, change no number and no rating"; a second miss PUBLISHES with the
   writing score shown on the front, never a freeze. The advisors and the
   reviewer are scored for the record only, never re-asked. The council's voice
   is carried by its own briefs and this measure (`council/lib/prose.py`, with
   its thresholds and word lists in `council/floors/prose-rules.json`), never by
   the host machine's own CLAUDE.md — a sitting must not rely on that file.

   **The chairman's four fields** (UPGRADE-2 U5(b) and READ-C1, owner rulings AC5, AC35(3)
   and AC44(1)): first the one-line answer (`answer_line` — one line answering the owner's
   question, printed above everything else on the page and never carried into the Atlas
   hand-off; a figure in it that traces to no recorded fact or key number is marked where the
   line is printed), then what decided it (`decisive_argument` — the advisor whose argument decided the rating, and
   why), the business in his own words (`business_read`, at most 120 words) and one row per
   decisive metric (`decisive_metrics_read`). At publish each row's value is traced to the
   facts its metric is answered by (and the figures a passage answering it states), by the
   same rule that marks business-frame prose; a row
   whose figure traces to none is marked "not traced to a recorded fact" on the row, once in
   the verdict's warnings and beside the row on the page — never refused, never re-asked. The host checks them on each chair document
   BEFORE the writing measure; a field missing or not in the form asked is asked for ONCE, as
   its own request (`chair_draft_fields` / `chair_resolve_fields`) — dispatch it like any seat.
   Its answer is spliced onto the accepted document; after it the field stands as written, or
   publishes empty — never a refusal. A `price` trigger's unit must be its price fact's unit
   exactly (refused otherwise, like any wrong figure); a price level counts as supported where
   it is one the market-structure advisor named, or sits at or within 1% of a turning point the price
   history carries — the year's lowest or highest close, a moving average (owner ruling
   AC44(4)); where no price trigger is supported, the verdict carries one plain warning line
   saying which level is the chairman's own judgement and naming the nearest turning point.
5. When the chair's draft is in, `step` writes the challenge request and
   prints the bridge command:

```
python -m council.bridge.codex_bridge challenge <run_dir>
```

   Run it yourself (detached or in the background if you prefer — its
   result lands durably in `challenge/result.json` either way). It smokes
   the model first and refuses the paid call on a failed smoke. Beside the smoke it asks
   `codex --version` once, unpaid, and records the first line as `codex_version` on every result
   it writes (owner ruling AC25(4)); the evidence audit does the same, and the host copies that
   one into the run record at `init`. The verdict's provenance carries both, and the report's
   model stamp prints them — nothing where none was recorded.

   **The challenger's tool posture.** The challenger reads the case file it is
   sent and nothing else: no web search, no reach into the owner's connected
   apps (mail, code, calendar, files). Both commands switch web search, the connected apps, sub-agents and image generation off, and
   the smoke test doubles as a probe: the model replies exactly OK, then NONE or
   one bare tool name per line; any other reply refuses the paid call and quotes the line.
   A tool of a forbidden kind (the list is data, `council/floors/challenger-posture.json`)
   refuses the paid call and names the tool; the reply is kept as
   `challenge/probe.json`. After the call, every tool it used is listed by name
   in `result.json`, and the raw event stream stays beside it as `events.jsonl`
   — the sitting's only session record. A call beyond reading the case file
   marks the result `posture_breach`, handled exactly as an unreadable answer:
   the sitting publishes unaudited, capped at hold. **Operator's check before a
   sitting:** `python -m council.bridge.codex_bridge smoke` must print `ok` and
   a tool list with nothing of a forbidden kind. Measured 2026-09-23 (codex
   0.156.0, before the sub-agent and image switches): no search, browser or app
   tool, but a shell, a patch tool, sub-agent and image tools remained. Measured
   again 2026-09-24 on codex 0.156.0: the sub-agent (`collaboration.*`) and local
   image-viewing tools stay listed whatever is switched off; they run inside the
   same sandbox, and any call to them voids the answer after the fact. The
   operator's check is that the list shows no search, browser, mail, app or
   connector tool. The evidence audit (§1a)
   carries the same switches and probe, but keeps its web reader for the
   `source_doubt` point: the posture file's `evidence_audit_reads_the_web`
   is true by owner ruling AC29 (web reading kept, apps off).
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
Rendering also writes the substitution log beside it, named after the report
(`report.html.number-substitutions.json` beside `report.html`): every number the
renderer respelt inside the council's prose (say, "47,636 thousand dollars"
shown as "$47.6M"), with where it was, so the respelling is on the record
(owner ruling AC16(1)).

**Render inside the sitting, before you commit the run.** The sitting's clock
ends at the rendered report, so the FIRST rendering of a run appends one
`report_rendered` row to that run's record and every later rendering prints the
moment it recorded — which is what makes a page reprinted months later byte for
byte the page the owner approved. The page and the row go together: the page is
staged, the row is written, and only then does the page appear. If the record
cannot be written the command refuses, prints why, and publishes nothing —
a report nothing has timed is re-timed by the next rendering, which changes the
minutes on the front page and can flip the budget line. Read-back is unaffected:
it reads the run's own last step and ignores that row.

## 5. The record

The run directory is the archive — every brief, answer, the pack, the
challenge exchange, the run record, the verdict, the envelope, the page.
It is committed whole under `council/runs/` and never edited afterward.

## 6. The ledger — the track record (owner ruling AC7)

Publishing writes one line to a shared file, `council/ledger/ledger.jsonl`,
so every verdict can later be judged against what happened. You do nothing
to make this happen: the publisher writes the line as part of §4's publish,
records its fingerprint in the run record, and read-back proves the line on
file is the one this run wrote. The line carries the subject's public name
only — no size and no holding, ever. Later, a session captures what happened
and scores it; the scorecard shows the record.

### 6.1 Capture what happened (an observation file)

Months after a sitting, capture the outcome the way you capture evidence —
by hand, from named sources, never guessed. For each due date (three, six
and twelve months out, printed in the ledger line as the horizons' due
dates), write the subject's closing price and, for a single stock, the
benchmark's closing price, each the exact figure with its source and the
date it is as of. Add each falsifier's published figure with its source and
your plain reading of whether it resolved FOR the council, AGAINST it, or is
still unresolved. Note whether any tripwire or any named re-opening trigger
fired, with the date. The shape is `council/schemas/observation_schema.json`:
write one observation per verdict and collect them all into ONE file — the
scorer in §6.2 reads that single combined file for the whole ledger.

### 6.2 Score it, then render the scorecard

```
python -m council.ledger.score council/ledger/ledger.jsonl <observations.json>
python -m council.ledger.report
```

The scoring script NEVER fetches: it reads only the figures you recorded and
applies the rules in `council/floors/scoring-rules.json` (owner ruling AC7 —
the horizons, what counts as right for each rating word, how a falsifier or
a tripwire resolves). The scorecard is one self-contained page,
`council/ledger/scorecard.html`, dark by default. It shows the verdicts and
their outcomes, the hit rate by rating word, the mean excess by horizon, and
the falsifiers for and against. It will NOT correlate tokens against return
below twenty scored verdicts — it prints the count and says so; the number
is whatever it is.

### 6.3 A fired tripwire or a lost falsifier is a reason to re-sit

If a tripwire fires, or a falsifier resolves against the council, that is a
signal to convene the council again on the same subject. A re-sitting is an
ordinary sitting; its ledger line links back to the prior one automatically,
so the record shows the chain.
