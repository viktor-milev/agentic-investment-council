# ANCHORLESS-ASSETS SPEC — scenario-earned ratings, per-class sufficiency, the decision front

**Status: FULLY FROZEN (Architect v4, 2026-09-01).** The class anchor lists ¶A/¶B/¶C were
confirmed by the owner the same day with one enhancement — the PBoC-in-isolation addition to
gold's central-bank anchor (ruling AB15) — incorporated in ¶B.2. Nothing in this document is
open. Everything else is
final. This spec EXTENDS `docs/REBUILD-SPEC.md` (+ §17) and `docs/THEMES-BASKETS-SPEC.md`, both
in force in full; where this document is silent, they govern. The builder decides mechanism
everywhere and meaning nowhere; anything unclear → §10 escalation.

## 0. What is being built, in one paragraph

The council learns to rate assets that have no earnings — Bitcoin AND gold now, plus the
commodity-class template with copper as its first registry entry — instead of being structurally frozen at Hold on them (the commissioned Bitcoin
cold read's central finding, accepted by the owner as rulings AB13). For an anchorless subject
the seats build a scenario ladder with probabilities, the chairman aggregates it into an
expected result, and the rating follows from whether that result clears a risk-adjusted bar;
sufficiency is judged against the asset class's own anchors, not the equity checklist; and every
report — all subjects, not just anchorless ones — gains a two-page decision front. Two small
chartered riders land with it (§7). Equity subjects' rating basis is untouched.

## 1. Authorities

OWNER-RULINGS **AB13** (the five rulings, his answers verbatim, including the long-horizon
amendment), **AB14** (the sealed-words extension; the metric-identity rule), **AB12/§AB** as
before. Grounding reference: the Bitcoin cold read (`council/runs/council-btc-2026-08-31` +
the commissioned review) — the builder should read it as the failure this unit exists to fix.

## 2. The asset-class registry and the anchorless flag

`subject` gains an `asset_class` (`equity` | `crypto` | `gold` | `commodity`; the registry is
data under `council/floors/` so later classes are additions, not code). A class is ANCHORED
(equity — the four canonical tests, unchanged) or ANCHORLESS (crypto, gold, commodity). A
`commodity` subject additionally names its PRODUCT (copper is the first registry entry), per
the owner's ruled product-conditional rule (W2.7). Class determines: the sufficiency
anchor set (§4), the rating basis (§3), and nothing else — seats, challenge, budgets, book-
blindness all unchanged. A thematic vehicle WRAPPING an anchorless theme (a Bitcoin ETF) takes
the vehicle floor (AB12) PLUS the anchorless basis through the vehicle.

## 3. The scenario-earned rating (AB13.1–.3)

- **The ladder:** every advisor's answer for an anchorless subject includes a scenario ladder —
  named scenarios (at least a bull, a base, a bear; more where the thesis demands), each with a
  price outcome, a probability, and a one-sentence rationale. Probabilities are the seat's OWN
  DISCIPLINED JUDGMENT, always labeled the council's judgment and never verified evidence
  (AB13.3); the reviewer cross-examines them; the challenger audits them.
- **The aggregation:** the chairman owns the published ladder — aggregating the seats' ladders
  is his judgment (mechanism free), but the published verdict carries HIS final ladder, the
  expected result computed from it with the arithmetic in words, and each seat's headline
  probabilities preserved in the record so divergence is visible.
- **The bar (AB13.2):** the expected annualized result must clear CASH (the question's ruled
  risk-free convention) PLUS a premium scaled to the asset's own realized volatility measured
  over the PAST ~5 YEARS (the owner's amendment — a long horizon, never last month's window).
  The scaling rule is the builder's to fix in data (one named constant in the floors registry,
  stated in the verdict); the SENSITIVITY IS ALWAYS PRINTED — the verdict and the report show
  how the rating moves as the bar and the probabilities move (at minimum: the probability at
  which the rating flips, the bar at ±  one scaling step).
- **The mapping:** monotone and published — clears the bar decisively → `buy`/`strong_buy`
  (the builder fixes the band arithmetic in data, printed in the verdict); clears marginally →
  `hold`; expected result negative against cash → `sell`; a ladder the chairman judges too
  uncertain to aggregate → `monitor` with the reason. No rating without its arithmetic on the
  page. The five-year-volatility figure and its source are pack facts, never seat inventions.
- **Equity subjects are untouched** — the anchor basis stands; a chairman MAY add a scenario
  ladder as supporting context, never as the rating basis.

## 4. Per-class sufficiency (AB13.4)

Sufficiency derives per question as always, PLUS the class anchor set:

- **equity:** the four canonical tests, ids unchanged.
- **¶A — crypto (the owner confirms this list at freeze):**
  1. price from the ruled aggregators (W6.1) with the 1-day freshness rule;
  2. circulating supply (Coin Metrics or equivalent dated source);
  3. daily US spot-ETF flows from a PRIMARY source, with the cumulative series;
  4. derivatives positioning — futures basis or funding rate and open interest, dated;
  5. THE ON-CHAIN FAMILY (per the commissioned on-chain brief, 2026-09-01, every source
     verified by live request — `scratchpad` brief preserved in the BUILD-LOG at this unit's
     close): (a) realized price and its 30-day change — the market's average purchase price,
     the deep downside rung; (b) the MVRV-Z score — cycle position, read as direction and rate
     of change against its own history, never against a fixed threshold; (c) short-term AND
     long-term holder cost basis — the two operative rungs of the downside ladder; (d)
     long-term holder supply and its 30-day net change — distribution vs accumulation, read in
     months and always beside the fund flows; (e) hash rate (7-day average) and difficulty —
     the one on-chain family custody cannot distort, and the source of forced miner supply.
     Primary sources as verified: Coin Metrics Community API, checkonchain series files
     (capture takes the last non-empty value), mempool.space / blockchain.com JSON;
     bitcoin-data.com as keyless cross-check only. STANDING READING RULE, rendered with the
     evidence: cohort figures are interpreted beside the fund flows — in a heavy-creation
     period they partly measure custody plumbing, and the record says so rather than silently
     trusting them. ADVISORY (gathered when available, never refuses a sitting): exchange
     balances/netflows, short-term-holder SOPR, dormancy/coin-days-destroyed, HODL waves,
     miner reserves/Puell/hashprice, percent-of-supply-in-profit. OMITTED with reasons on the
     record: NUPL (a rearrangement of MVRV — one fact must not vote twice), whale/address
     cohorts (broken by post-ETF custody concentration), thermocap/stock-to-flow/Pi-cycle
     (no mechanism), active-addresses/NVT (off-chain activity blinds them);
  6. cycle history WITH DURATIONS — each prior cycle's peak, trough, depth AND trough-to-
     recovery time (the cold read: "the single most decision-relevant gap");
  7. the event calendar as dated facts (Fed meeting dates from the published calendar,
     protocol events, named legislative dates in play);
  8. long-horizon (~5y) realized volatility — the bar's input (§3);
  9. the halving schedule (date + block height, W8.3).
- **¶B — gold (the owner confirms at freeze; per the commissioned gold/commodity brief,
  2026-09-01, every required source retrieved live that day):** gold is a MONETARY asset, not a
  commodity — its anchors answer "who is buying, why, and what would make them stop":
  1. inflation-protected government bond yields, 5y and 10y (FRED, daily) — the safe
     alternative's pay; the ladder must say whether the bull case needs them to fall, and if
     not, name the buyer;
  2. official-sector (central-bank) buying, latest published quarter WITH ITS AS-OF DATE
     STAMPED — a slow series by nature, so its freshness rule is written for a slow series and
     the staleness is rendered, never hidden — AND, WITHIN IT, THE PBOC IN ISOLATION (owner
     enhancement, AB15): the People's Bank of China's OFFICIAL reported purchases AND a dated
     market ESTIMATE of its true buying, both carried side by side with the divergence visible,
     because the one central bank with a special appetite for gold reports figures that differ
     from what the market estimates it actually buys — and that gap is itself information the
     council must see, never an average that hides it;
  3. gold fund (ETF) holdings and flows, the monthly primary file — the Western investor;
  4. speculative futures positioning, weekly (CFTC) — the crowding read;
  5. the BROAD dollar index (never the euro-heavy popular index) — how much of the move is the
     denominator;
  6. the inflation-adjusted price against its own long history — gold's only valuation check,
     disciplining the debate rather than settling it.
  ADVISORY: jewellery/investment split; physical-market stress dislocations; mining costs only
  when miners are the subject. OMITTED with reasons on the record: the mining cost "floor"
  (costs run ~39% of the price — a floor that constrains nothing); lease/forward rates (no
  public benchmark since 2015); ratio-of-anchor metrics (never anchor on the division of two
  anchors).
- **¶C — the commodity TEMPLATE, copper as the first product (the owner confirms at freeze;
  same brief):** built on the ruled W2.7 core, concrete:
  1. the executable contract price with VENUE AND CONTRACT MONTH NAMED;
  2. the cross-venue gap wherever more than one benchmark exists (the tariff-era lesson: never
     assume a single price — how much is metal, how much is policy);
  3. the carry over the intended holding period, read OFF THE CURVE (storage and financing are
     observed in the curve, not computed);
  4. exchange inventories SPLIT BY VENUE, where a series exists for the product (the ruled
     product-conditional item — a product with no exchange stocks declares the reasoned gap);
  5. the tradable horizon and roll requirement — a three-year intent in a one-year-liquid
     contract makes the carry a forecast, and the record says so.
  ADVISORY: physical premiums (paid sources); marginal cost / incentive price (promote only
  for 5y+ horizons or supply-response cases); positioning where the venue is undistorted;
  named disruption risks carried as a scenario-ladder allowance, not data. OMITTED with
  reasons: demand narratives (inventories and the curve already price them — requiring the
  story double-counts it); separate storage-cost inputs (the curve did the arithmetic).
  CAPTURE-FRAGILITY NOTE, recorded: the only free London metals price/inventory feed is a
  scraped third-party mirror — a single point of failure under a required anchor; the builder
  records it as a stated confidence-note source per the rule below, and a fallback path is
  registered, not built.
  A missing anchor without a declared, reasoned gap refuses the sitting with the shopping list
  (the themes precedent). Sources follow the primary-or-discounted rule: a blocked site is
  fetched another way, or the figure carries a stated confidence note.

## 5. The two-page decision front (AB13.5 — ALL subjects)

The report opens with at most two rendered pages: the rating; the three-to-five numbers the
ruling actually turns on; the scenario ladder with its expected-result arithmetic (anchorless)
or the priced read (anchored); the downside ladder; the dated event calendar; the tripwires;
and "what changes this rating" in plain sentences. Everything else — advisors, the reviewer's
disagreement map (rendered as the front's cross-examination summary, per the cold read), the
challenge round, the audit trail — folds behind it as appendices. Figures ROUNDED in prose per
the reading-precision rules. Ruling Z binds. Tripwires must be actionable INSIDE the horizon:
every event trigger carries a date; long-horizon invalidations get rolling checkpoints.

## 6. Seat differentiation for anchorless subjects

The five advisor lenses stay named as built, but for an anchorless subject each brief assigns
the seat its EVIDENCE EMPHASIS (flows/positioning · on-chain/valuation-floor · cycle history/
durations · macro/calendar · asset-specific risk) so five seats stop producing one essay five
ways (the cold read's finding). Mechanism free; the obligation is that the five briefs are not
identical in their emphasis instruction and the reviewer polices convergence by name.

## 7. Chartered riders (small, land with this unit)

1. **AB14(2):** `hold`, `holds`, `holding` join the sealed-words inventory in the seal module,
   with a regression test that the owner's actual theme question (the word "hold") now trips
   the mechanical net — test FAILS pre-fix.
2. **MAC-1 code half:** every seat brief is REORDERED so the answer contract comes FIRST,
   before the case file — a truncated read fails safe. Regression: the contract section
   provably precedes the evidence in every rendered brief; plus the dispatch-note doc line
   already applied. The theme sitting's paging J3 item closes with this.

## 8. Deliberately NOT built

Further commodity PRODUCTS beyond copper (each product's conditional items return to the owner
when charged; the template ships now).
Any change to equity rating semantics. Portfolio anything (AB1 stands). Autonomous probability
sourcing from prediction markets as the council's own view (a market-implied probability may
enter the PACK as a dated fact; the council's ladder remains its own labeled judgment). No
changes to the frozen PowerShell stack.

## 9. Tests, build, audit, acceptance

Extend the existing suites in place: registry + anchorless flag; ladder schema and the
aggregation arithmetic; the bar computation with the 5-year-volatility input and the printed
sensitivity; the mapping bands; sufficiency pass AND refusal fixtures for crypto, gold, and
copper-as-commodity; the decision
front's rendering (both bases); the two riders' regressions; e2e gains one canned anchorless
rehearsal (zero-model). CHECKS.md counts updated. Branch `unit-anchorless` in a dedicated
worktree from the commit the architect names; council/ + docs/ only; suites and the old eleven
(on Windows) green at close by the builder's execution; the plugin audit split per its caps;
BUILD-LOG + the ≤350-word owner checkpoint; push; STOP DEAD.
**Acceptance (architect's):** suites by own execution; audit ledger complete; ONE live sitting
— **Bitcoin re-run** (the natural benchmark: the cold read's own subject), measured against
AB6/AB11, and judged against the cold read's complaints: a reachable rating with its arithmetic,
the durations answered, the calendar present, the two-page front. The owner's same hard-money
thesis travels verbatim.

## 10. Escalation and the handshake (MANDATORY, the ruled standard)

The builder does NOT hunt for the architect. On dispatch: read the intake via
`git show origin/main:<path>` without touching any checkout, then WAIT. **The ARCHITECT opens
the handshake**, names the base commit and the worktree, and confirms ¶A's status. Only
instructions from that address govern. Unclear meaning → message that address, mark the part
blocked, build elsewhere. Building past an ambiguity is the one unforgivable move.

## 11. Clarification C1 — the AB14(2) sealed words fire on the OWNER'S OWN possession, never on every occurrence of the letters (architect ruling v5, 2026-09-01, builder escalation 1)

> *[Example sentence altered for the public copy; the mechanism and the ruling are unchanged.
> The owner's own sentence had exactly this shape and named a real holding of his; "ExampleCo"
> stands in for it here and in the matching regression test.]*

The builder escalated with a measurement on the EU-sovereignty sitting's verbatim question: the
bare-word reading of `hold`/`holds`/`holding` fires three times — twice on company facts
("OVHcloud … holds France's highest security visa"; "United Internet … HOLDING / Internet
Infrastructure") and once on the question author's own possession ("I would also add ExampleCo
to the list, which I hold."). On the bare-word reading two constituents' evidence would be routed
to the Atlas half where no seat sees it, and the ruling's own originating sitting becomes
unsittable.

**RULED: the first-person possession reading.** The three words join the sealed-words inventory
as the owner's OWN-possession language — the net fires where the question's author speaks of
possessing (I/we/my/our shapes, tolerant of intervening adverbs and ordinary inversions), and
never on a third party's or a company's use of the same letters. Grounds, both already ruled by
the owner: (a) AB14(2)'s stated purpose is verbatim "the first live theme was protected by the
frame's judgment alone when the owner wrote 'hold'; the mechanical net now catches it too" — the
target is the owner's sentence; (b) AB3's seam rule decides the boundary — "a sentence writable
without knowing what the owner holds belongs to the council; a sentence referencing his
inventory belongs to Atlas" — and a company fact is writable without knowing the owner's book.
The exact pattern mechanics are the builder's (mechanism). The frame's judgment remains the
backstop ABOVE the mechanical net, exactly as it operated in the first live theme: a first-person
shape the pattern misses is still caught by the frame, while an over-firing pattern would delete
council evidence with no backstop — so the pattern errs narrow, never wide.

**Regression obligations (as the builder proposed):** refutation-first — the owner's own
sentence "I would also add ExampleCo to the list, which I hold." provably passes the net TODAY
and is caught after the fix; AND the two company rows are provably NOT caught, so the ruling's
own sitting stays sittable.

This clarification interprets an owner ruling and is reported to the owner in plain terms at the
unit checkpoint; he may overrule, and an overrule reopens only this section.

## 12. Clarification C2 — a commodity PRODUCT the owner has never ruled on REFUSES with the shopping list (architect ruling v5, 2026-09-01, builder escalation 2)

The builder escalated (raised twice by the outside reviewer): a `commodity` subject naming a
product with no registry entry beyond the template — aluminium, say — today SITS, with one
pass-path sentence noting that only the template applied. The reviewer called it a fail-open
against §8's own words.

**RULED: option 2 — REFUSE with the shopping list.** An unregistered product does not sit. The
refusal names, in plain words, what would make it sittable: the owner's determination of the
product-conditional pair (does an exchange-stocks series exist for this product and at which
venues, or is the reasoned gap declared; does an undistorted positioning report exist), and the
owner's charge of the product into the registry. Grounds, all already ruled: (a) §8's own text —
"each product's conditional items return to the owner when charged" — and refusal is the
mechanism that forces that return; sitting silently is the mechanism that skips it; (b) AB13.4 —
sufficiency is judged against a RULED anchor set, and for an unregistered product nobody has
ruled which of the product-conditional pair applies; (c) AB12(1), the themes precedent — refuse-
with-shopping-list is the owner-ratified shape for "not yet sittable," and it costs a capture,
never a council; (d) the owner's documented direction: every overrule at a must-have batch went
toward MORE required facts, never fewer. "The template ships now" (§8) is satisfied on this
reading: the template ships USED — copper sits on it — and each later product is a registry-data
addition, not code (§2's own registry rule). Option 1's honesty depended on a reader noticing
one sentence; a refusal cannot be missed. Regression as the builder proposed: aluminium refuses
with the list, copper sits — and the refusal text names the conditional pair, not a bare no.

Reported to the owner at the unit checkpoint; he may overrule, and an overrule reopens only this
section.
