# Five-minute demo

Use a phone-sized window (390 px wide) or a phone.

- **Steps 1–5** work on the hosted static demo (<https://claude.ai/artifact/L9dgVoqU59h9e4vsqhg1n1>, once shared).
- **Step 6 (Ask FINN)** needs the full app: `./deploy/start.sh`, then <http://localhost:3000>.

Say once, at the start: *"Everything you'll see is synthetic, labelled data. FINN couldn't reach the exchanges from where it was built, so it runs on fictional companies whose filings follow real SEBI layouts. The banner on every screen says so."*

---

**0:00 – 0:40 · The brief: what changed since you last looked**
- Open **Brief**. Under *Needs you*, SARANG's **credit rating downgrade (AA- → A+)** is at the top, followed by the order win, the acquisition and the warning letter.
- Tap SARANG. The event page shows **why it ranked**: a sum of named components (filing type, size against the company, market reaction), plus the hard floor that makes rating downgrades always surface. Each one gives its inputs.
- *Point:* no black-box score; every point is explained.

**0:40 – 1:20 · Duplicates, clustering, the market**
- Back to the brief and open **KESTREL's Q2 results**. The outcome, the results PDF, the press release, the deck and a corrigendum form **one event**. The second copy of the PDF is marked a duplicate, and the corrigendum is linked, not dropped.
- Open **Alerts → Market moves**. **SARANG −4.2% on 2.6× volume** is explained by the downgrade, while **MERIDIAN +6.8% on 3.4×** shows *no filing explains this move*.
- *Point:* FINN says when it doesn't know why something moved.

**1:20 – 1:50 · The user's own thresholds**
- Tap **Change** (or Alerts → Rules). Move *Price move in a day* from 5% to 3%: QUANTA (+3.9%) now alerts. Set a category to *Hide* and its alerts go, except hard floors.

**1:50 – 3:10 · Pull research: Narrative vs Numbers**
- **Research**: type `tata motors` or `RELIANCE.NS` to show search across the NSE list. A company without a report says what's needed to build one.
- Open **KAVERI** (cement).
  - The section bar sticks under the top bar.
  - **Narrative vs Numbers**: on the Q2 FY27 call, management described demand positively while revenue fell 2.1% year on year; margins likewise; FY26 capex missed its first-stated plan.
  - Tap any figure: the evidence sheet shows the **document, page and the row it came from**. *Read page N* opens the page text.
- **Management guidance**: "high single digit" revenue growth is kept **as words, not turned into a number**.
- *Point:* every claim traces to a page; vague guidance is never scored as a target.

**3:10 – 3:50 · Credibility tracker and conflicting sources**
- From KAVERI, open **the tracker**: *kept 4 of 6 explicit targets whose period has closed*, and closed targets tended to land on the unfavourable side of the range. Each indicator lists its observations. There is no trust score.
- Open **VEDIKA**: the Q4 FY26 deck said 24.5–25.5% EBITDA margin and the call said 24–25%. FINN flags that **the documents disagree** rather than picking one.

**3:50 – 4:40 · Ask FINN (full app only)**
- On KAVERI, ask *"Why did margins decline in Q2 FY27?"*: the answer cites the margin facts and the cost lines that moved, then quotes management. Interpretation is labelled as such.
- Ask *"Why did EBITDA margin improve by 5 percentage points?"*: FINN corrects the premise from the filings.
- Ask *"Should I buy this stock?"*: refused; FINN shows what the filings say instead.
- On CORAL, ask anything: *not enough evidence*, with what was searched.
- *Point:* answers come only from the company's own documents, and numbers that aren't in the cited evidence are dropped.

**4:40 – 5:00 · Close**
- *"Arithmetic is code, language never invents a figure, and gaps are stated rather than filled. The evaluation report has the failures as well as the passes."* Point to **EVAL.md** and **LIMITATIONS.md**.

---

**If something goes wrong:**
- Ask FINN says it needs the engine: you're on the static demo or the engine isn't running. Run `./deploy/start.sh`.
- An empty brief: check `/api/health` (it should show `feed.events: 29`).
- On-demand research for a real ticker ends in "None of the filing sources … could be reached" when the network blocks NSE and BSE. That is the honest result, not a crash.
