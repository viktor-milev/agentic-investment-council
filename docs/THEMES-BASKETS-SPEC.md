# THEMES & BASKETS SPEC — the council's two new subject kinds

**Status: FULLY FROZEN (Architect v4, 2026-08-31).** ¶Q was ruled by the owner the same day
("refuse-with-shopping-list is accepted") and the thematic-vehicle clarification (owner, same
sitting; OWNER-RULINGS AB12) is incorporated in §2/§4/§6/§9. Nothing in this document is open. The builder decides
mechanism everywhere and meaning nowhere; anything unclear → §12 escalation. This spec EXTENDS
`docs/REBUILD-SPEC.md` (+ its §17 clarifications), which remains in force in full; where this
document is silent, that one governs.

## 0. What is being built, in one paragraph

The live council (`council/`) learns two new subject kinds beside the single name: a **BASKET** —
one investment thesis expressed through several NAMED instruments judged together — and a
**THEME** — a thesis whose instruments may not all be named yet. Same pipeline, same seats, same
book-blindness, same budgets: one rating on the owner's five-word scale for the subject as a
whole, priced where the record supports it, with tripwires and a filled Atlas envelope. This
capability precedes and feeds the Atlas integration.

## 1. Authorities — the ruled meanings that survive into the split world

- OWNER-RULINGS §AB (the split, the scale, the budgets) — unchanged and binding.
- **W2.9 / W7.1 (the owner's own phrase: "theme with no names attached, unlifted"):** a theme
  with no investable expression must never earn conviction on zero verifiable facts. Its
  split-world expression is ¶Q below.
- **W8.2:** where a theme's falsifying fact is a LEVEL, the prior period must be visible — a
  falsifier that cannot fire is not a falsifier. Event- and date-shaped falsifiers are untouched.
- **W8.6 / REG-18 (deferred BY THE OWNER to the first real theme sitting):** nothing yet
  guarantees a theme's prior-period comparison measures the SAME metric, only the same unit.
  This spec does NOT settle it — it OBLIGES the first live theme sitting to surface the concrete
  case and the wording question to the owner (§6). A ruled deferral, not an option.
- **T5's surviving halves:** a basket needs NAMES; an ETF is a SINGLE (never a basket of its
  holdings). T5's "themes publish sized" is dead with sizes (AB1/AB3).

## 2. The subject contract

`subject.kind` ∈ `single | basket | theme` (singles unchanged).

- **BASKET:** 2–8 named constituents, each independently resolvable (ticker/venue identity as
  singles have). Optional `thesis_proportions` — the IDEA's internal emphasis, a statement about
  the thesis and never about anyone's account; clearly labeled as such wherever rendered. More
  than 8 constituents: refuse at intake with the reason — raising the bound is an owner ruling.
- **THEME:** the thesis, PLUS — required to be sittable (¶Q) — an investable expression: a
  provisional universe of 2–8 named instruments OR one named implementation vehicle; PLUS at
  least one measurable falsifying fact, with its prior period where the falsifier is a level
  (W8.2). The universe/vehicle is the owner's or the evidence session's naming; the council
  judges candidates, it never invents them silently (§9).
- **SINGLE THAT IS A COLLECTIVE VEHICLE (an ETF or similar):** stays `kind: single` with ONE
  rating — T5's identity ruling ("an ETF is a single") is intact — but the owner's AB12
  clarification governs its treatment: a THEMATIC vehicle technically one name is really a
  basket wearing one ticker, and the council's capability encompasses it. Its evidence carries
  the vehicle floor (§4) and, where the vehicle is thematic, the theme obligations (falsifier
  with prior period). The 2–8 constituent bound does NOT apply to a vehicle's own holdings:
  the fund's published disclosure is the universe, and the pack carries the HOLDINGS PICTURE
  (top holdings, weights, concentration) — never a per-holding analysis of every name.

## 3. ¶Q — RULED BY THE OWNER, 2026-08-31: refuse-with-shopping-list

**A theme without an investable expression, or without one measurable falsifier, is REFUSED at
the sufficiency gate before any seat is paid** — the refusal note is the product: it states
exactly what would make the question sittable (names or a vehicle; a falsifiable fact; the prior
period where the fact is a level), in plain words, at capture cost. The old machinery instead
let such a theme SIT and capped its conviction; the rebuild has no cap machinery, and paying
three seats' wages to discover an unanswerable question contradicts ruling AB2. The owner's W2.9
intent — never conviction on zero verifiable facts — is preserved in the stronger form.
*(Ruled: the owner accepted this reading verbatim — "refuse-with-shopping-list is accepted.
Good call." The sit-and-ceiling alternative is closed.)*

## 4. Evidence — floors and sufficiency per kind

- **BASKET:** thesis-level facts (what the one idea turns on, AB2-derived) + a per-constituent
  ESSENTIAL core: identity, last price, market value, and the one or two metrics the thesis
  load-bears on for THAT constituent. The full four-test single-name battery is NOT required per
  constituent; the four tests apply at the thesis level where the question is a priced one.
  Sufficiency derives per question as AB2 prescribes, plus: every named constituent present with
  its essential core, and the thesis facts answerable.
- **THEME:** the falsifying fact(s) with prior period(s) (W8.2), the universe/vehicle facts
  (identity, price, market value per named expression), and the thesis facts. Sufficiency
  additionally enforces ¶Q.
- **COLLECTIVE VEHICLE (thematic or not):** the ruled ETF core survives from W2.5 as the
  vehicle floor — price · NAV per share · premium/discount (derived) · the holdings picture ·
  expense ratio · the 30-day median bid-ask spread · leverage/reset terms where the fund is
  leveraged or inverse; fund flows advisory unless a tested dated source exists for that fund
  family (the Bitcoin-ETF carve-out stands). A THEMATIC vehicle additionally carries at least
  one measurable falsifying fact for its theme, with the prior period where it is a level
  (W8.2) — the seats judge the theme THROUGH the vehicle.
- All REBUILD-SPEC §5 provenance rules unchanged (exact strings, declared arithmetic,
  comparative dating, market-state disclosure, figures literal in passages).

## 5. Seats and briefs

The bench is unchanged: five advisors, one blind reviewer with synopsis, chair, one challenge
cycle. Briefs render the kind and its constituents/expression; every seat is told the subject's
kind and what it obliges (the reviewer explicitly polices per-constituent blind spots — the
advisor who judged the basket on its largest name alone). Brief bytes must scale SUBLINEARLY in
constituent count — the shared case file carries the constituent table once; the 2–8 bound
(§2) is part of the budget design, and AB6/AB11 govern every sitting unchanged.

## 6. The verdict and the envelope

- **ONE rating for the subject as a whole** on the owner's five-word scale. Per-constituent
  RATINGS are explicitly not built (§9); per-constituent NOTES are — short typed notes (the
  constituent's role in the thesis, its load-bearing metric, any constituent-level tripwire).
- Mispricing read where the subject supports one (a basket of priced names can; many themes
  answer "no-view" honestly — the schema's existing no-view is the right word).
- Tripwires: subject-level plus constituent-bound where a trigger belongs to one name. For a
  THEME the falsifier is first-class: it appears in tripwires with its prior period and the
  named figure and date it is scored against — and the same block applies to a THEMATIC
  VEHICLE'S theme (§2), so a thematic ETF is never rated without a falsifier for the theme it
  wraps.
- The Atlas envelope carries: kind, the constituent list (or vehicle), per-constituent sizing
  inputs where available (realized volatility, liquidity, event dates), the thesis
  proportions if stated, and the standard hashes. The `for_atlas` seam rule is unchanged.
- **The REG-18 obligation:** the FIRST live theme sitting's record must present the owner, in
  plain words with the sitting's own concrete case, the metric-identity question his W8.6
  deferral parked — and the verdict's theme falsifier block must name the metric identity it
  assumed, so the question is answerable from the page.

## 7. The report

Kind-appropriate rendering: a constituent table (identity, price, market value, load-bearing
metric, note) for baskets and themed universes; the theme falsifier block with its prior period;
the thesis-proportions labeled as the idea's emphasis, never as a portfolio. Ruling Z binds; the
formatting rules (one precision per unit, exact-decimal) are already the renderer's.

## 8. Tests

Extend the existing six suites in place (no seventh suite): schema kinds and bounds; gate and
sufficiency per kind including the ¶Q refusal WITH its shopping-list note and the
level-needs-prior-period rule; engine briefs for both kinds; publisher notes and
constituent-bound tripwires; report rendering both kinds; and the e2e rehearsal gains one canned
BASKET fixture and one canned THEME fixture plus one empty-theme refusal path — all zero-model.
`council/CHECKS.md` updated with the new counts.

## 9. Deliberately NOT built

Per-constituent ratings (one subject, one rating). Sleeves, sizes, account anything (AB1 —
unchanged). Theme universe auto-discovery — the council judges NAMED candidates; inventing an
investable universe is research the owner or evidence session does openly, never a silent seat
behavior. Per-holding decomposition of a collective vehicle — the holdings picture is evidence, never
dozens of sub-analyses (T5: an ETF is a single; AB12 gives it the thematic treatment, not a
seat per holding). Old-stack changes of any kind.
More than 8 constituents.

## 10. Build discipline

Branch `unit-themes` from the main commit the architect names at green light. Changes confined
to `council/` + `docs/` (+ `council/CHECKS.md`); the frozen PowerShell stack untouched; the six
suites and the old eleven green at the close by the builder's own execution. The audit runs
through the plugin exclusively; if the diff exceeds the caps, split per the plugin's own rule
(likely two: contract+evidence / engine+report), each closed under the stopping rule.
BUILD-LOG entry + the ≤350-word owner checkpoint; push; STOP DEAD.

## 11. Acceptance (the architect's)

1. The extended suites green by the architect's own execution; the old eleven untouched-green.
2. The audit charges closed under the stopping rule, ledger complete.
3. ONE live acceptance sitting on an owner-supplied basket OR theme, measured against AB6/AB11
   (discards count). If the subject is a theme, the sitting must also discharge the §6 REG-18
   surfacing obligation. A decision-grade verdict: the rating, the notes, the tripwires, the
   filled envelope, the rendered page.

## 12. Escalation

As REBUILD-SPEC §16, with the addressing lesson learned: BEFORE building anything, the builder
messages the architect session (find it via ListAgents — the interactive session on this repo
whose reply confirms it is the architect) and waits for the green light naming the base commit.
Unclear meaning, a tempting scope, a schema question this spec and REBUILD-SPEC do not answer:
message the architect, mark the part blocked, build elsewhere. Building past an ambiguity is
the one unforgivable move.
