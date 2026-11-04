# Five-minute demo

Use a phone-sized window (390 px wide) or a phone.

- **Steps 1–5** work on the hosted static demo (<https://claude.ai/artifact/L9dgVoqU59h9e4vsqhg1n1>, once shared).
- **Step 6 (Ask FINN)** needs the full app: `./deploy/start.sh`, then <http://localhost:3000>.

Say once, at the start: *"Everything you'll see is synthetic, labelled data. FINN couldn't reach the exchanges from where it was built, so it runs on fictional companies whose filings follow real SEBI layouts. The banner on every screen says so."*

---

**0:00 – 0:40 · The brief: what changed since you last looked**
- Open **Brief** (window: *Since last look*). Under *Needs you*, SARANG's **credit rating downgrade (AA- → A+)** is at the top, followed by VEDIKA's USFDA-style warning letter, TIDEMARK's CFO resignation and KAVERI's ₹1,150 cr capex. KESTREL's results and CORAL's pledge are under *Worth a look*; 15 routine filings are collapsed.
- Tap SARANG. The event page shows **why it scored 74**: a sum of named components (filing type 60, market reaction +14 for −4.2% at −5.0 standard deviations on 2.6× volume), each with its inputs. The explanation notes that rating downgrades always surface: a hard floor of 70 would have applied had the score been lower.
- Optional: switch the window to *7 days* to bring in the older order win (QUANTA) and acquisition (HELIX).
- *Point:* no black-box score; every point is explained.

**0:40 – 1:20 · Duplicates, clustering, the market**
- Back to the brief and open **KESTREL's Q2 results** (under *Worth a look*). The outcome, the results PDF, the press release, the deck and a corrigendum form **one event**. The second copy of the PDF is marked a duplicate, and the corrigendum is linked, not dropped.
- Open **Alerts → Market moves**. **SARANG's volume at 2.6×** its 20-day average is *explained by a filing* (the downgrade; the −4.2% fall is below the 5% price threshold), while **MERIDIAN +6.8% on 3.4×** shows *no filing explains this move*.
- *Point:* FINN says when it doesn't know why something moved.

**1:20 – 1:50 · The user's own thresholds**
- Tap **Change** (or Alerts → Rules). Move *Price move in a day* from 5% to 3%: QUANTA (+3.9%) now alerts. Set a category to *Hide* and its alerts go, except hard floors.

**1:50 – 3:10 · Pull research: Narrative vs Numbers**
- **Research**: type `tata motors` or `RELIANCE.NS` to show search across the NSE list. A company without a report says what's needed to build one.
- Open **KAVERI** (cement).
  - The section bar sticks under the top bar.
  - **Narrative vs Numbers**: on the Q2 FY27 call, management described demand positively while revenue fell 2.1% year on year; margins likewise; FY26 capex missed its first-stated plan.
  - Tap a figure in the snapshot (say, revenue ₹1,655.0 cr): the evidence sheet shows the **document, page, column and the row as printed**. *Read page N* opens the page text. (A computed figure shows its formula and inputs instead.)
- **Management guidance**: "high single digit" revenue growth is kept **as words, not turned into a number**.
- *Point:* every claim traces to a page; vague guidance is never scored as a target.

**3:10 – 3:50 · Credibility tracker and conflicting sources**
- From KAVERI, open **the tracker**: *kept 4 of 6 explicit targets whose period has closed*. Each indicator lists its observations, and the page says why there is no trust score.
- Open **VEDIKA**: the Q4 FY26 deck said 24.5–25.5% EBITDA margin and the call said 24–25%. FINN flags that **the documents disagree** rather than picking one.

**3:50 – 4:40 · Ask FINN (full app only)**
- On KAVERI, ask *"Why did margins decline in Q2 FY27?"*: the answer cites the margin facts and the cost lines that moved, then quotes management. Interpretation is labelled as such.
- Ask *"Why did EBITDA margin improve by 5 percentage points?"*: FINN corrects the premise from the filings.
- Ask *"Should I buy this stock?"*: refused; FINN shows what the filings say instead.
- On CORAL (listed, but no documents in the window), ask *"Why did margins decline?"*: *not enough evidence*, because no results filing could be read.
- *Point:* answers come only from the company's own documents, and numbers that aren't in the cited evidence are dropped.

**4:40 – 5:00 · Close**
- *"Arithmetic is code, language never invents a figure, and gaps are stated rather than filled. The evaluation report has the failures as well as the passes."* Point to **EVAL.md** and **LIMITATIONS.md**.

---

**If something goes wrong:**
- Ask FINN says it needs the engine: you're on the static demo or the engine isn't running. Run `./deploy/start.sh`.
- An empty brief: check `/api/health` (it should show `feed.events: 29`).
- On-demand research for a real ticker ends in "None of the filing sources … could be reached" when the network blocks NSE and BSE. That is the honest result, not a crash.
