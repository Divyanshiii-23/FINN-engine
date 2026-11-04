# Engineering decisions and trade-offs

Each entry gives what was chosen, what it costs, and when it should be revisited.

**1. Code does the arithmetic; language never produces a figure.**
Every number on screen is a fact in a registry: reported (document, page, row, column) or computed (formula and inputs). Text can only cite facts. A model, if one is enabled, may reword sentences but cannot add a number, cause, judgement or name; its output is checked and dropped otherwise.
*Cost:* the wording is plainer than an LLM's, and some insight a model could offer is left out. *Revisit:* never for figures; for wording, once a model's output can be evaluated against the same checks at scale.

**2. Rules over a model for classification, claims and Ask FINN.**
Rules are reproducible, testable against labelled sets, and fail visibly: unmatched filings show as "needs review", and unmatched questions get an explicit gap.
*Cost:* phrasing nobody wrote a rule for is missed. On a held-out announcement set written after the first round of fixes, category accuracy was 83% and tier agreement 77% before that set was used to tune further. See EVAL.md. *Revisit:* a model could propose classifications as candidates while the same rules and floors decide, with held-out sets as the gate.

**3. Never manufacture a target from vague guidance.**
"High single digit" and "double-digit" are kept as words or literal floors. Guidance that names no period is kept as commentary, not scored against the current year.
*Cost:* recall. Four of seventeen explicit sentences in an evaluation set went unscored for want of a stated period. *Why:* scoring a target against the wrong year is worse than not scoring it.

**4. Materiality is a sum of named components, with hard floors.**
Users see exactly why something interrupts them. Floors (rating downgrade, auditor resignation, pledge invocation, insolvency, payment default, death of a director) always surface.
*Cost:* the weights are judgement, not fitted to market reactions. *Revisit:* calibrate against historical price reactions once live data is available.

**5. Credibility without a trust score.**
The tracker shows delivery, revisions and capex execution with their observations. A rate is given only with at least four closed observations over two years.
*Cost:* there's no single number to rank companies by. *Why:* a score over two observations would look precise and mean nothing.

**6. BM25, not embeddings.**
Every retrieved passage can be explained by its matching words. It needs no model or API key and runs inside the engine.
*Cost:* weaker paraphrase recall. A small synonym map covers the common cases; one of 22 paraphrased queries still misses its top three. *Revisit:* add embeddings as a second retriever behind the same citation validator.

**7. JSON files between engine and web, SQLite inside the engine.**
The web app needs no database and can run read-only from built files, which is also what makes the static demo possible. The SQL is plain enough to move, but only SQLite is implemented.
*Cost:* there are no concurrent writers across machines, and the feed is rebuilt rather than queried. *Revisit:* for multi-user, live operation (a server database and a scheduled push run).

**8. One container, engine on localhost.**
Two processes, one image, and the engine never public. The web app proxies it and adds an optional shared token. Research runs are capped at two at once and bodies at 4 KB.
*Cost:* it doesn't scale the engine independently. *Revisit:* split the services if research load grows.

**9. Synthetic, labelled data rather than nothing.**
The build sandbox had no route to NSE, BSE or company websites. Instead of mock UI, FINN generates fictional companies whose documents follow SEBI layouts, with planted scenarios whose correct verdicts were fixed before the code. Symbols that collide with real NSE tickers are forbidden by a test.
*Cost:* passing fixtures proves consistency, not robustness to real filings (the biggest open risk). *Revisit:* first thing when a network route exists. Save real payloads as regression fixtures.

**10. A static demo built from the same components.**
The challenge asks for a deployed URL, and the only host reachable from the build environment serves static pages. Rather than build a separate mock site, `static-demo/` bundles the real screens with a hash router and a data layer that returns exactly what the real API returns without an engine.
*Cost:* Ask FINN and on-demand research are off in that deployment, and it says so. *Revisit:* deploy the container to a server host.

**11. Honest degradation everywhere.**
An unreachable source is reported with what was tried. A missing call is a stated gap. An arbitrary live ticker ends in `SOURCES_UNAVAILABLE` naming the company, its ISIN and each failed fetch. No fallback fills in data from elsewhere.

**12. Mobile first.**
The screens are designed at 390 px and checked at 320 px. Section navigation sits under the phone top bar, and tap targets meet WCAG 2.5.8. Desktop gets a sidebar and two columns from the same components.
