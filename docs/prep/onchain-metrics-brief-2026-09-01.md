# Bitcoin On-Chain Evidence: What a Council Should Require

**Prepared 1 September 2026. Every figure and every source below was read live from the named provider on 31 August / 1 September 2026.**

---

## 1. The judgment that governs everything else

Blockchain analytics were built to answer one question: *what are the people who own this actually doing?* For twelve years that worked, because owning Bitcoin and holding a Bitcoin wallet were the same thing. They are no longer the same thing. Roughly 1.3 million coins now sit inside exchange-traded funds, custodied overwhelmingly by a single firm. When an investor buys a Bitcoin ETF nothing distinctive happens on the blockchain — and when the fund later shuffles coins between its own wallets, the chain records something that *looks* like a dramatic investor action but is bookkeeping. Glassnode's own public research on 26 August 2026 put it plainly: the custodial wallet group grew by 31,500 coins in a week, matching that week's fund creations "in scale, not traced coin for coin." They could not prove the two were the same coins. Nobody can.

So the honest position is this: **on-chain data has lost much of its power to tell you who is buying and selling, and kept nearly all of its power to tell you what the market paid.** There are three tiers now, and they should not be treated alike:

- **Arithmetic over the whole chain** — what every coin last changed hands at. Unbroken; it requires no guess about who owns anything.
- **Coin-age measures** — how long coins have sat still. Partly broken: a move into fund custody resets a coin's age to zero, so migration reads as fresh buying. But that is one weak assumption, not a chain of them.
- **Wallet-identity measures** — exchange balances, whale watching. Badly broken: they depend on analysts guessing which wallets belong to which businesses, and those guesses now fail in a systematic direction.

My recommendations follow that ranking. **Require the arithmetic, require the best of the age measures, demote the identity guesswork.**

---

## 2. The metrics, by the question they answer

### Question: what did the market pay, and is price above or below it?

**Realized price and realized capitalisation** — the average price at which every coin last changed hands; in effect the market's aggregate purchase price. On 1 September 2026 it stood at **$53,049** against a spot price of **$79,061**.

*Why it decides things.* It is the closest thing Bitcoin has to book value: where the average holder breaks even, and the zone price has historically fallen to in genuine bear markets. It gives a downside ladder a bottom rung that is not a guess. Its 30-day change also shows whether real capital is arriving through *all* channels, not only the fund flows the council already tracks.

*Where it misleads.* Three to four million coins are lost forever and are still counted at their 2010–2013 purchase price, dragging the average down. More importantly today: when a fund takes delivery, those coins re-price at today's market price, so realized cap rises as though new money arrived even when it may be the same owner changing wrapper. Providers also disagree slightly — Coin Metrics implies $53,077 and checkonchain publishes $53,049, but bitcoin-data.com publishes $52,672, about 0.7% lower. A council must name its provider and stay with it.

*Sources.* Coin Metrics Community API — free, no signup, no key, daily bars finalised 02:00–04:00 UTC. Realized cap sits behind their paywall but is exactly recoverable as market cap divided by MVRV, both free. Cross-check: checkonchain's chart data files, free, with the complete daily history. **Verdict: REQUIRED ANCHOR.**

**MVRV and the MVRV-Z score** — how far above its purchase price the market is trading, with the Z-score expressing that as distance from the historical norm. On 31 August 2026: MVRV **1.48**, Z-score **0.85**.

*Why it decides things.* The best single answer to "where are we in the cycle." Historically, Z-scores above roughly 7 marked tops and below zero marked bottoms. At 0.85 the market sits nearer its long-run average than either extreme — a fact that should show up in both the rating and the scenario probabilities.

*Where it misleads.* Badly, if read as a fixed threshold. Peaks have fallen every cycle — above 8 in 2011, around 7.5 in 2017, lower since — and the Z-score's yardstick is computed across Bitcoin's entire history including the wild 2010–2013 period, which makes present readings look tamer than they are. Waiting for a "9" to sell would have meant never selling. **Read direction and rate of change, never the level against a fixed line.**

*Sources.* Coin Metrics Community (`CapMVRVCur`, free daily) for the ratio; `bitcoin-data.com/v1/mvrv-zscore/last` returns the standardised score as dated JSON without a key. **Verdict: REQUIRED ANCHOR.**

### Question: where is the floor, and what breaks on the way down?

**Short-term and long-term holder cost basis** — what recent buyers paid, versus what patient holders paid. On 28 August 2026: recent buyers **$69,980**, long-term holders **$48,918**.

*Why it decides things.* This *is* the downside ladder, in dollars rather than chart lines. The recent-buyer average is where the marginal, weakest holder goes underwater and selling historically accelerates; it has acted as support in uptrends and resistance in downtrends. The long-term holder average is the deeper rung. Anchor a downside scenario on these, not on round figures.

*Where it misleads.* The 155-day cutoff between "recent" and "patient" is arbitrary, and a coin moving into fund custody resets to day one — inflating the recent-buyer pool and dragging its average toward today's price. In a heavy creation week this partly measures fund plumbing.

*Sources.* checkonchain (free, complete daily series) as primary; `bitcoin-data.com/v1/sth-realized-price/last` and `/lth-realized-price/last` as a keyless cross-check, roughly three days behind. Worth noting: that free source's $69,980 matches Glassnode's independently published $70.0K for the same week — two unrelated providers agreeing is the strongest validation in this brief. **Verdict: REQUIRED ANCHOR** (both numbers, as one item).

### Question: are patient holders adding or distributing?

**Long-term holder supply and its 30-day net change** — how many coins have sat untouched for more than five months, and whether that pile is growing or shrinking.

*Why it decides things.* Nothing else in the required set answers who is supplying the market. Sustained shrinkage in this pile while price rises is the classic distribution pattern that preceded every prior cycle top; sustained growth through weakness is accumulation. For a verdict that must assign scenario probabilities, this is the behavioural input.

*Where it misleads.* It shares the age-reset defect — heavy fund creations mechanically shrink the long-term pile without a single genuine holder selling, so it must always be read next to the fund flow figures the council already requires. It also moves slowly; judge it in months, not weeks.

*Sources.* checkonchain publishes both the supply split and the 30-day net position change free, as complete daily series back to 2009. I verified the supply file directly: it carries long-term and short-term holder totals plus their profit/loss splits. **Verdict: REQUIRED ANCHOR.**

### Question: is the asset's production system healthy, and what does it cost to make?

**Hash rate and difficulty** — how much computing power secures the network, and how hard the network has made itself in response. On 31 August 2026 hash rate was **951 exahashes per second**, down more than 25% from its October 2025 peak; the next difficulty adjustment is estimated at **+1.7%** after a **-1.3%** move.

*Why it decides things.* This is the only on-chain family custody cannot corrupt — electricity and silicon, not wallet labels. It answers whether the network's security budget is intact and where the marginal cost of production sits. Analysts put average miner production cost near $78,000, with price below it for five consecutive months and roughly one miner in five losing money; listed miners sold over 32,000 coins in the first quarter of 2026, a single-quarter record. That is real, forced supply a downside scenario must account for.

*Where it misleads.* Daily hash rate is a statistical estimate and jumps around — it fell from 1,019 to 951 exahashes in one day. **Use a seven-day average.** Production cost is a soft floor: miners with cheap power keep running far below the average.

*Sources.* Coin Metrics Community (`HashRate`, free daily); mempool.space and blockchain.com both expose free keyless JSON for hash rate and difficulty. **Verdict: REQUIRED ANCHOR.**

---

## 3. What I am deliberately demoting, and why

**Exchange balances and net flows — ADVISORY.** Free and trivially captured (Coin Metrics publishes 2,704,339 coins on exchanges as of 31 August, 13.5% of supply). But this is the metric the new regime broke most thoroughly. Whether a custodian counts as an "exchange" is a provider's editorial choice, and providers disagree by hundreds of thousands of coins. A fund creation can register as a huge inflow, a routine wallet reshuffle as a huge outflow. The old reading — "coins leaving exchanges means conviction" — is no longer safe. Gather it; never let it carry a verdict alone.

**Dormancy, coin-days-destroyed, HODL waves — ADVISORY.** The same age-reset defect as long-term holder supply, without its clarity. Custodial migrations, government seizures, bankruptcy distributions and trust unwinds have all produced enormous "ancient coins waking up" spikes with no market meaning.

**SOPR variants — ADVISORY.** The short-term-holder version adds a genuine short-horizon capitulation read. Aggregate SOPR mostly restates what MVRV already says, and in bear markets it sits below its line for months, so brief dips signal nothing.

**Miner reserves, Puell multiple, hashprice — ADVISORY.** Informative right now (Puell at 0.74 is a historically stressed zone), but miner balances are muddied by loan collateral and hosting arrangements, and Puell is scaled by newly-issued coins, a small and shrinking part of the picture. Colour, not a gate.

**NUPL — OMIT.** Net unrealised profit/loss is not independent information: it is exactly `1 − 1/MVRV`, a rearrangement of a metric already required. Requiring both lets one fact vote twice.

**Whale and address cohorts — OMIT.** An address is not a person. Fund custody compresses millions of individual holders into a handful of very large addresses, so "whales are accumulating" now frequently means "a fund had a creation." The most corrupted family post-ETF, and the most likely to produce a confident wrong answer.

**Thermocap, Delta cap, stock-to-flow, Pi Cycle, rainbow charts — OMIT.** Thermocap divides by cumulative miner revenue, which only ever grows, making it slow, monotonic, never actionable at a decision horizon, and largely redundant with MVRV-Z. Stock-to-flow was falsified in public. Pi Cycle and rainbow charts are curve-fits to three prior cycles with no mechanism behind them.

**Active addresses and the NVT ratio — OMIT.** Both assume on-chain transaction activity proxies economic activity. Most Bitcoin trading is now off-chain or inside fund wrappers, so it no longer does.

---

## 4. Recommended REQUIRED set (five items)

1. **Realized price** — the market's average purchase price. Read as the deep downside rung; read its 30-day change as whether real capital is entering or leaving through all channels.
2. **MVRV-Z score** — cycle position. Read as direction and rate of change against its own history; never against a fixed "top" threshold, which has fallen every cycle.
3. **Short-term and long-term holder cost basis** — the two operative rungs of the downside ladder. Read the recent-buyer level as the line where forced selling accelerates.
4. **Long-term holder supply and its 30-day change** — distribution versus accumulation. Read in months, not weeks, and always beside fund flows.
5. **Hash rate (7-day average) and difficulty** — network integrity and production cost. Read as the one measure custody cannot distort, and as the source of forced miner supply.

**Standing reading rule for all five:** every cohort figure must be interpreted alongside the fund holdings the council already requires. If fund creations were heavy in the period, cohort figures are partly measuring plumbing, and the council should say so rather than silently trust them.

## 5. Advisory set (gathered when available, never refuses a sitting)

Exchange balances and net flows; short-term-holder SOPR; dormancy and coin-days-destroyed; HODL waves; miner reserves, Puell multiple and hashprice; percentage of supply in profit; Glassnode's free weekly research as a qualitative cross-check.

## 6. What money would and would not buy

Every one of the five required anchors is available free, keyless and dated. No subscription is needed to run this evidence standard.

The one gap money could narrow is **entity-adjusted data** — analytics that try to separate fund plumbing from genuine investor behaviour. Glassnode sells it and has no free programmatic tier in 2026. It would improve the advisory set and would *not* change any of the five anchors, which were chosen precisely to avoid depending on entity guesswork. I would not spend on it yet.

## 7. Capture notes

**Reliable.** Coin Metrics Community API — free, unauthenticated, daily, the most contract-grade source here. mempool.space and blockchain.com chart APIs — free, keyless, single-request JSON. checkonchain — free, no login, complete daily series embedded in its chart files; note the files run 2–23 MB each and the date axis extends past the last real data point, so a capture must take the last non-empty value, not the last date.

**Not reliable.** bitbo.io blocks automated readers with a challenge page on every chart. LookIntoBitcoin (into which Bitcoin Magazine Pro has now folded back) and newhedge render everything after page load, so nothing dated appears in the raw page; both need a full browser, and LookIntoBitcoin's data export sits behind a $99/month tier. Glassnode has no free programmatic access — its free weekly research is genuinely useful, but as prose for a human, not as a feed. bitcoin-data.com answers without a key today, but its own documentation says a key is expected; treat it as a secondary cross-check that may require registration later.

---

*This brief covers metric selection and data sourcing for an evidence standard. It is not investment advice and takes no view on whether Bitcoin should be bought or sold.*
