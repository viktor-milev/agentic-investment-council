# Anchor sets for GOLD and STANDALONE COMMODITIES (copper as the worked example)

Prepared 1 September 2026. Every source below was tested by live request the same day; results are stated.
Three anchors already apply to every anchorless asset and are **not** repeated here: five-year realized
volatility, the dated event calendar, and the price with its freshness rule.

---

## 1. What these two assets actually are

**Gold is not a commodity for our purposes.** It is not consumed — essentially every ounce ever mined
still exists, and annual mine supply is about 1.5% of that stock. Nothing on the supply side can move the
price. Gold is priced entirely by *who wants to hold the existing pile and at what price*, and by what the
alternative store of value pays. The evidence must answer one question: **who is buying, why, and what
would make them stop?** Three buyers matter (governments, investors via funds, speculators via futures)
and two competing prices of money (inflation-protected bond yields, and the dollar) — plus one check on
whether today's price is historically extreme.

**Copper is the opposite.** It is dug up, consumed, and stored, so it genuinely runs short and long, and
the market says so through inventories and the shape of the forward price curve. It also cannot be held
without cost or contract — as the owner ruled, the council analyses it through the instrument it would
actually buy. The evidence must answer: **is the market tight or loose, what does it cost (or pay) to hold
the position for the intended holding period, and can the position be held that long at all?**

---

## 2. GOLD — metric by metric

| Metric | Source & live result (1 Sep 2026) | Verdict |
|---|---|---|
| Inflation-protected government bond yield, 5y and 10y | US Federal Reserve's FRED, free CSV, no key. Ten-year **2.42%**, five-year **2.18%**, both dated 28 Aug 2026. Next-day. | **REQUIRED** |
| Government (central bank) gold buying | World Gold Council, drawn from IMF statistics. Free file, but the dashboard read "as of March 2026" on a page updated 4 August. Two to five months late. | **REQUIRED**, with the as-of date stamped |
| Gold fund (ETF) holdings and flows | World Gold Council monthly file, free, no account needed — latest data July 2026, published 24 August. The fund sponsor's own daily file (SPDR) redirected to a web page today, not data. | **REQUIRED** (monthly file, not the daily) |
| Futures positioning | US CFTC weekly report, free JSON. Retrieved: speculative funds net long **144,747 gold contracts**, dated 25 August. | **REQUIRED** |
| Dollar strength | FRED broad dollar index, **118.75** on 28 Aug 2026, free and daily. | **REQUIRED** |
| Price today versus its own inflation-adjusted history | London benchmark price, free JSON — **USD 4,562.75/oz** on 28 Aug 2026 — deflated by FRED consumer prices (July 2026). | **REQUIRED** |
| Mining all-in sustaining cost as a "floor" | World Gold Council/Metals Focus, quarterly, free summary: **USD 1,785/oz** in Q1 2026 against a quarterly average gold price of **USD 4,873/oz**. | **OMIT** |
| Gold lease and forward rates | No free public benchmark exists. The London forward rate was discontinued in January 2015 and rates are now private dealer quotes. | **OMIT** |
| Gold futures curve / carry | Derivable from the price and the overnight financing rate (**SOFR 3.68%**, 31 Aug 2026, free). Adds nothing on its own. | **ADVISORY** (stress flag only) |
| Jewellery vs investment demand split | WGC quarterly, lagged. | **ADVISORY** |
| Gold-to-equities and gold-to-inflation ratios | Not sourced — arithmetic on numbers already in evidence. | **OMIT** |

**The critical calls, and why.**

*The cost floor is a fiction for gold.* Miners' costs are running at roughly **39% of the gold price**.
A "floor" 60% below the market is not a floor; it is a statement about mining profits, not about gold.
Requiring it would import a comfortable-sounding number that constrains nothing. It becomes relevant only
if the sitting is about a *mining company*, which is a different asset class.

*Real yields no longer predict — but they still discipline.* The textbook relationship (gold falls when
inflation-protected bonds pay more) has broken down badly since 2022: today those bonds pay a healthy
2.42% and gold is nonetheless near record levels. That is an argument for keeping the anchor, not
dropping it. It forces the council to say out loud whether its bullish case needs yields to fall — and if
not, to name the buyer who is paying up regardless. That is precisely the discipline a scenario ladder
needs.

*Two ratios are omitted on principle.* Gold-to-equity and gold-to-inflation are quotients of figures the
council already holds. Never anchor on the division of two anchors — it creates a way for a sitting to be
refused over arithmetic.

*Government buying is late, and required anyway.* It is the most important driver of this market since
2022, and the series always exists, so it cannot refuse a sitting for plumbing reasons. But it is months
stale: write the freshness rule for a slow series, and put the as-of date on the face of the evidence.

### Gold — the REQUIRED set (six)

1. **Inflation-protected bond yield, five- and ten-year.** The return on the safe alternative. Read as: what
   must this yield do for the bull case to work — and if the answer is "nothing", name the buyer instead.
2. **Government gold buying, latest published quarter, date stamped.** The buyer who does not care about
   price. Read as: is the official-sector bid still there, and how old is this news?
3. **Gold fund holdings and flows, monthly.** The Western investor. Read as: is private money joining the
   move or selling into it?
4. **Speculative futures positioning, weekly.** The fast money. Read as: how crowded is this, and how much
   of the recent move is borrowed conviction that can reverse in a week?
5. **Broad dollar index.** The currency the price is quoted in. Read as: how much of the move is gold rising
   versus the dollar falling? Use the *broad* index — the popular "dollar index" is over half euro and
   misleads.
6. **Inflation-adjusted price against its own long history.** The only valuation check gold has. Read as: is
   today extreme by the standards of the last fifty years — accepting that there are only about three
   independent episodes to compare against, so this disciplines the debate rather than settling it.

**Gold advisory:** jewellery/investment demand split; physical market stress signals (London–New York
price dislocations); mining costs when miners are the subject; gold's relationship to equities and to
inflation as commentary, computed at the table.

---

## 3. COPPER — metric by metric

| Metric | Source & live result (1 Sep 2026) | Verdict |
|---|---|---|
| Executable contract price, venue named | London cash **USD 14,535.00/t** and three-month **USD 14,370.00/t**, 28 Aug 2026, retrieved free from a third-party mirror. New York futures at record levels near **USD 6.71/lb** (≈ USD 14,800/t). | **REQUIRED** |
| The gap between the two venues | The same metal at two prices, because of US import tariff policy. | **REQUIRED** |
| Carry over the holding period | Read directly off the curve: cash **above** three-month by **USD 165/t** — a shortage signal, and a position that *pays* about 4.6% a year to roll. Financing rate 3.68%, free. | **REQUIRED** |
| Exchange inventories | London **234,275 t** free and dated; New York inventories reported swelling toward 650,000 t during the tariff scramble; Shanghai exchange site reachable. | **REQUIRED**, with the venue split |
| Can the position be held for the horizon? | Open interest free from the CFTC file (**283,299 New York copper contracts**). Liquidity thins sharply beyond roughly a year. | **REQUIRED** |
| Physical premiums (e.g. Yangshan) | Subscription only (SMM, Fastmarkets). Blocked today. | **ADVISORY** |
| Marginal cost / incentive price | Good data is paid (Wood Mackenzie, CRU). Free annual fallback: USGS commodity summary, **retrieved successfully**. | **ADVISORY** |
| Speculative positioning | Free and dated (net long **76,271 contracts**, 25 Aug) — but covers only the New York venue, which is the *distorted* one. | **ADVISORY** |
| China grid / property / electric-vehicle demand | Annual plans, slow-moving, or forecasts dressed as measurements. | **OMIT** |
| Supply pipeline and mine disruptions | No free, dated, structured series exists. It is news. | **ADVISORY** |
| IMF monthly copper price (FRED) | Free but monthly and late — latest is **July 2026**. | **OMIT as the price anchor** |

**The critical calls, and why.**

*The 2024–26 tariff episode taught one lesson: never assume a single price.* Copper today trades at
materially different prices in London and New York because US tariff policy made location matter more
than metal. A council that anchors on "the copper price" without naming the venue and the contract month
can build an entire case on a price it could not transact at. Hence the venue gap is its own required
item, not a footnote.

*Inventories must be required as a split, not a total.* During the tariff scramble, metal moved from
London warehouses to New York ones. Total world inventory barely changed; each venue's number swung
violently. A council reading one venue would have called relocation a shortage. Requiring the split makes
that error impossible to make silently. The honest caveat: exchange inventories are the visible tip —
metal held privately is invisible, and warehouse figures have historically been gamed.

*Demand stories are omitted deliberately.* China's grid spending, property weakness and electric-vehicle
copper intensity are the fashionable items, and they are exactly what to leave out. In a storable
commodity, demand reveals itself in inventories and in the shape of the price curve — which are already
required. Requiring the narrative on top double-counts it, and each of those series would give a sitting a
plumbing reason to fail while adding no measurement the price has not already made.

*Storage costs are not computed; they are observed.* The forward curve already prices storage and
financing. Requiring separate storage inputs is arithmetic the market has done for us, and would be wrong
more often than the curve. Only a council contemplating holding physical metal needs the components.

*Positioning is demoted for copper but required for gold.* The same free source, a different verdict: for
gold, New York futures are where the speculative money actually is; for copper, that venue is the one
tariffs distorted, so its positioning is a partial view of a fractured market.

### Copper — the REQUIRED set (five)

1. **Executable price, with venue and contract month named.** Read as: this is the price we could actually
   transact, not an index.
2. **The cross-venue gap.** Read as: how much of this price is metal and how much is policy?
3. **Carry over the intended holding period, read off the curve.** Read as: does time work for us or against
   us — today, a copper long is paid to wait.
4. **Exchange inventories, split by venue.** Read as: is the world short, or has metal simply moved?
5. **Tradable horizon and roll requirement.** Read as: if we intend to hold three years in a contract that is
   liquid for one, our carry number is a forecast, not an observation — and the plan needs a roll programme.

Note that tariff decision dates and the policy calendar are **already covered** by the class-generic dated
event calendar. Do not duplicate them here.

**Copper advisory:** physical premiums where purchased; marginal cost and incentive price (promote to
required only for horizons beyond five years or where the case rests on supply responding); speculative
positioning; named disruption risks carried as an allowance in the scenario ladder rather than as data.

---

## 4. Capture notes

**Reliable, free, machine-readable, verified today:** FRED (real yields, dollar, financing rate, consumer
prices) — plain CSV, no key, next business day; the London bullion benchmark price as JSON; the CFTC
positioning file as JSON (as-of Tuesday, published Friday); the Federal Reserve meeting calendar; the USGS
annual minerals summary.

**Fragile — expect these to break:** the World Gold Council files (free but the site pushes logins, the
data runs a month or more behind, and pages get restructured); the gold fund's own daily holdings file,
which today returned a web page rather than data; and — most important — **our only free London metals
price and inventory feed is a third-party mirror scraped from a web table.** It worked cleanly today and
is dated 28 August, but it has no service guarantee and will break on a site redesign. That is a single
point of failure sitting under a required copper anchor, and it should be treated as a known risk rather
than assumed.

**Refused us today:** the CME's own price service (connection failed), the London Metal Exchange website
(403 forbidden), Nasdaq Data Link (403), Yahoo's quote service (rate-limited). None of these can sit under
a required anchor.

**What only money buys:** London official prices under licence; physical premiums such as Yangshan
(SMM/Fastmarkets); mine cost curves (Wood Mackenzie, CRU); and gold lease and forward rates, which have
had **no public benchmark since 2015**. Of these, the physical premium is the one genuinely worth paying
for — it is the fastest honest read on tightness. The rest can be lived without.

---

## 5. What is copper-specific and what becomes the commodity template

**Template (applies to any standalone commodity, with the owner's product-conditional rule intact):**
executable contract price with venue and contract month named; the gap between benchmarks wherever more
than one exists; carry over the intended holding period read off the curve; tradable horizon and roll
requirement; exchange inventories **where a series exists for that product**; positioning **where a report
exists for that product**. The last two are the ruled product-conditional pair — required for copper,
absent for products with no exchange stocks (a reasoned gap, declared, not a refusal).

**Copper-specific:** the three-venue inventory split and the relocation trap it guards against; the
Yangshan physical premium; the China grid/property/vehicle demand narrative (omitted here, but the
category is product-specific); and the tariff-driven venue dislocation — though the *pattern* generalises
to any metal a government decides to tax at the border, so the template keeps the cross-venue gap as a
standing item rather than a copper footnote.

**Explicitly does not generalise:** gold's anchors. Real yields, government buying and fund flows belong
to a monetary asset and have no place in the commodity template. Gold should be its own class, and the
temptation to file it under "commodities" is the first mistake to design out.

---

**Proposals recorded, not built** (scope freeze respected): a freshness rule written for slow-moving
series with a visible as-of stamp; a "disruption allowance" as a scenario-ladder obligation rather than an
evidence item; a fallback path for the London price should the free mirror fail.
