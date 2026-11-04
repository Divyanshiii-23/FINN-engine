# FINN code review

Reviewed 2026-11-04. Scope: the whole repository, covering the push pipeline, the Pull research engine,
Ask FINN, the credibility tracker, the research service and the Next.js app.

I reproduced every finding below against the running code before listing it.
Findings marked **Fixed** have a regression test or a UI check (named in each finding).
Findings marked **Open** are not fixed and are listed as they are.

**Environment limit.** This sandbox can't reach NSE, BSE or company websites. So the live
source paths, and the parsers against *real* filings, are still unverified (see O-5).

Severity measures harm to an investor relying on the output, or to the server running it:

| Severity | Meaning |
|---|---|
| **High** | Wrong or unsupported figures shown as fact; a security hole; a core feature unusable on its main surface |
| **Medium** | Degrades correctness or coverage in common cases, or is exploitable only under conditions |
| **Low** | Polish, robustness or maintainability |

## Summary

| ID | Severity | Area | Finding | Status |
|---|---|---|---|---|
| R-01 | High | Security | Exchange-supplied attachment refs could read local files and fetch any URL (SSRF) | Fixed |
| R-03 | High | Security / API | Engine API: no auth, unbounded body, unbounded live crawls, traceback leak | Fixed (auth opt-in) |
| R-04 | High | Hallucination | Model rewording was checked for numbers only; causes, judgements and names passed | Fixed |
| R-05 | High | Hallucination | Ask validator counted the user's question as evidence | Fixed |
| R-06 | High | Retrieval | "Why did margins decline in FY26?" was answered with Q2 FY27, without saying so | Fixed |
| R-11 | High | Financials | Bank (Banking Regulation Act) statement format not recognised | Fixed (synthetic page only) |
| R-12 | High | Financials | Lender detection relied only on BSE; if BSE was down, a bank got EBITDA | Fixed |
| R-19 | High | Mobile | Section nav hidden under the phone top bar; anchors landed under it | Fixed |
| R-02 | Medium | Security | Links from exchange data rendered with any URL scheme | Fixed |
| R-07 | Medium | Retrieval | "predict" or "recommend" anywhere caused a refusal ("What did management predict for capex?") | Fixed |
| R-09 | Medium | Financials | Dash/"Nil" cells read as missing, so EBITDA was absent for debt-free companies | Fixed |
| R-10 | Medium | Financials | EBITDA fell back to PBT including exceptional items, labelled "before exceptional" | Fixed |
| R-13 | Medium | Financials | Capex "on track" had an undocumented 20% leniency | Fixed (verdict change) |
| R-14 | Medium | Pipeline | index.json race; same-symbol temp-file collision crashed writes | Fixed |
| R-15 | Medium | Pipeline | No stale fallback for the BSE scrip list: one outage disabled BSE for every ticker | Fixed |
| R-16 | Medium | Pipeline | BSE pagination cap silently dropped older filings | Fixed (now reported) |
| R-17 | Medium | Pipeline | Service used the wall clock as "today" for fixture companies | Fixed |
| R-20 | Medium | Frontend | Ask history survived a report refresh, so citations could point at the wrong version | Fixed |
| R-08 | Low | Hallucination | A rule template wrote an unsupported number; the validator dropped the whole finding | Fixed |
| R-18 | Low | Performance | Every request re-parsed the multi-MB report; Ask rebuilt the BM25 index per question | Fixed |
| R-21 | Low | Frontend | Engine error shape didn't match the UI; users saw "returned 429" instead of the reason | Fixed |
| R-22 | Low | Accessibility | Modal sheet had no focus trap | Fixed |
| R-23 | Low | Frontend | Ask textarea didn't grow with the question | Fixed |
| O-1…O-12 | — | — | See [Open issues](#open-issues) | Open |

Checked and found sound:
- **Dead buttons.** Every `<button>` has a handler or is a form submit (grep plus the interaction suites).
- **Navigation.** All section anchors resolve (checked on a phone viewport).
- **Ticker handling.** `M&M` and `BAJAJ-AUTO` pass validation and URL encoding end to end; `.NS` and `NSE:` prefixes are stripped.
- **Engine binding.** The engine binds to 127.0.0.1 by default.

---

## High

### R-01: SSRF and local file read through exchange data
- **Where.** `engine/finn_engine/research/sources.py` (`LiveInputs.download`, `FileInputs.download`), `engine/finn_engine/pipeline.py` (`LiveInputs.attachment`), `engine/finn_engine/sources/http.py`.
- **Root cause.** `download(ref)` read any path on disk (`file://` or an existing path) and fetched any `http(s)` URL. The `ref` comes straight from BSE/NSE announcement JSON. Redirects were followed to any host. The push pipeline fetched non-BSE attachment URLs unchecked.
- **Impact.** A malformed or malicious announcement record could make the server:
  - read local files into a "document", whose text then shows up in passages and Ask answers;
  - request internal addresses, such as cloud metadata or the engine itself.
- **Fix.**
  - `host_allowed()` permits only `https` on `bseindia.com` and `nseindia.com` (and their subdomains).
  - `HttpClient.get(..., hosts=)` follows redirects manually and checks each hop.
  - Local paths are read only for operator-supplied documents (`trusted=True`, set for IR documents passed on the command line).
  - Fixture refs resolve only inside the fixture's `attachments/` directory.
- **Tests.** `test_review_fixes.py::test_exchange_hosts_only`, `::test_untrusted_refs_cannot_read_files_or_reach_other_hosts`, `::test_fixture_refs_stay_inside_the_fixture_directory`.

### R-03: Engine HTTP surface
- **Where.** `engine/finn_engine/research/service.py`; `apps/web/lib/server/research.ts`.
- **Root cause.**
  - No authentication.
  - `rfile.read(Content-Length)` had no limit.
  - Every POST for a new symbol started a thread that crawls the exchanges, with no cap.
  - Unexpected exceptions returned `traceback.format_exc()` to the client.
  - Malformed requests (bad JSON, a non-integer Content-Length) dropped the connection with no response.
  - The Next routes relay POSTs publicly, so anyone who could reach the web app could trigger crawls.
- **Impact.**
  - Memory exhaustion from oversized bodies.
  - Unbounded outbound crawling, which can get the server IP blocked by NSE and BSE.
  - Server paths and code disclosed to clients.
- **Fix.**
  - Optional `FINN_ENGINE_TOKEN`: the engine requires `Authorization: Bearer`, compared in constant time. The web app adds the header server-side only. `/health` stays open.
  - At most 2 concurrent runs (`429 BUSY`); finished jobs are pruned at 200.
  - Bodies capped at 4 KB (`413`); `400 BAD_JSON` for bad bodies.
  - Generic `500 INTERNAL` responses, with the traceback written to stderr only.
- **Tests.** `::test_body_limit_and_bad_json`, `::test_token_required_when_configured`, `::test_concurrent_jobs_are_capped`, `::test_internal_errors_do_not_leak_a_traceback`.
- **Manual check.** Engine and web app run with and without a matching token: 401 direct, 200 through the web app.
- **Still open.** The token is opt-in, and there is no per-client rate limit (O-4, O-11).

### R-04: Model output checked for numbers only
- **Where.** `engine/finn_engine/explain.py::grounded`, used by `llm_explain` (push) and `research/credibility.py::model_rephraser`.
- **Root cause.** A rewording was accepted if every number in it appeared in the inputs. "Margins fell to 20.2% due to pricing pressure" passed.
- **Impact.** With `--llm` enabled, a model could add causes, judgements ("a strong quarter") or company names to text labelled as grounded. That breaks the rule that nothing unsupported is shown.
- **Fix.** `grounded()` now also rejects:
  - causal connectives absent from the inputs;
  - evaluative or forecast words absent from the inputs;
  - capitalised names absent from the inputs;
  - rewordings where fewer than 60% of content words trace to the inputs (a small list of neutral movement words is exempt).

  The credibility rephraser checks against the facts plus FINN's own sentence.
- **Tests.** `test_explain.py::test_grounding_rejects_added_causes_judgements_and_names`; `test_research_credibility.py::test_model_rewrite_is_rejected_when_it_adds_a_number` (extended).
- **Trade-off.** Synonym-heavy paraphrases are now rejected, and FINN's own wording is kept instead. That is the safe direction.

### R-05: The question counted as evidence
- **Where.** `engine/finn_engine/research/ask.py::validate`.
- **Root cause.** `ev = evidence + " " + question`.
- **Impact.** In model mode, asking "Will EBIT margin reach 31.5%?" let a block claiming "EBIT margin will reach 31.5%" pass validation, because the number came from the user.
- **Fix.**
  - The question is excluded from the evidence.
  - Strict (model) validation also rejects a stated cause that the cited evidence doesn't contain.
- **Tests.** `::test_question_text_is_not_evidence`, `::test_strict_validation_rejects_an_added_cause`.

### R-06: Named period silently replaced
- **Where.** `ask.py::Asker._period_for`.
- **Root cause.** A period that wasn't a quarter in the trajectory (FY26, H1 FY27, FY22) fell back to the latest quarter.
- **Impact.** "Why did margins decline in FY26?" returned a Q2 FY27 analysis with status *answered*: a confident answer to a different question.
- **Fix.**
  - A named year or half is answered through its latest quarter, with an explicit note ("You asked about FY26 … this answers for Q4 FY26").
  - The full-year margin pair is added when both years are available.
  - A period outside the filings read returns *insufficient* with the range that was covered.
- **Tests.** `::test_named_year_is_not_silently_swapped_for_the_latest_quarter`. UI check: `qa/review_ui.py` ("FY26 question answered with the period note").

### R-11: Bank statement format
- **Where.** `engine/finn_engine/research/statements.py` (`PNL_FIELDS`, `BS_FIELDS`, `SECTIONS`, balance-sheet page test).
- **Root cause.** The patterns covered Ind AS corporates and NBFCs only. Banks file in the Third Schedule format:
  - P&L: "Interest expended", "Provisions (other than tax) and contingencies";
  - balance sheet: "Capital and liabilities" / "Assets", "Advances", "Cash and balances with RBI", and a bare "Total" on each side.

  The balance-sheet page also had to contain "total assets", so a bank's balance sheet was never picked.
- **Impact.** For HDFCBANK (in the demo portfolio) and every listed bank:
  - net interest income, credit cost and loan growth were missing;
  - the balance sheet was missing;
  - Narrative vs Numbers checks on loans and asset quality showed as unverifiable.
- **Fix.** The patterns and bank sections above are added. Deposits and borrowings are summed as lender funding. The total check uses each side's "Total".
- **Tests.** `test_research_statements.py::test_bank_format_is_read`.
- **Limit.** Tested only on a page FINN built, never on a real bank filing.

### R-12: Bank analysed as a manufacturer when BSE is down
- **Where.** `research/pipeline.py::resolve`.
- **Root cause.** `is_financial` came only from BSE's `INDUSTRY` field, and only BSE supplies it.
- **Impact.** If BSE was unreachable, a bank got EBITDA, an EBITDA margin and working-capital days computed on interest income. Those are wrong metrics presented as computed facts.
- **Fix.**
  - When the industry is unknown, a name match (bank, finance, finserv, fincorp, housing finance, NBFC) marks the company as a lender, with a note saying so.
  - R-15 also makes the industry field far more often available.
- **Tests.** `::test_lender_is_detected_from_the_name_when_industry_is_unknown`.

### R-19: Phone section nav hidden
- **Where.** `apps/web/components/research/CompanyScreen.tsx`, `AskFinn.tsx`, `shell/AppShell.tsx`, `app/globals.css`.
- **Root cause.**
  - The section nav was `sticky top-0 z-10`. The phone top bar is also `sticky top-0`, at `z-30`, and 94 px tall, so the nav slid under it.
  - `scroll-mt-16` (64 px) left section headings under the bar.
- **Impact.** On phones, the main surface for this challenge, the eight-section navigation was invisible once you scrolled, and tapping a section hid its heading.
- **Fix.**
  - AppShell measures the top bar with a `ResizeObserver` and publishes `--topbar`. (The bar's height varies because its data notice wraps.)
  - The nav sticks at `top: var(--topbar)`.
  - Sections use `scroll-margin: var(--topbar) + 3.5rem`. Desktop is unchanged.
- **Tests.** `qa/review_ui.py`: the nav sits at y = 94, and all 11 anchors land below nav plus bar (measured at 390×844).

## Medium

### R-02: Unvalidated link schemes
- **Where.** `components/research/ReportSections.tsx` (document table), `lib/research.ts::docHref` (EvidenceSheet, SourceViewer), `components/push/FeedGate.tsx`.
- **Root cause.** `href={d.url}` and `href={source.attachment_url}` came straight from exchange-derived JSON.
- **Impact.** React 19 already neutralises `javascript:` hrefs, so this was not directly exploitable. Other schemes (`data:`, `vbscript:`, app schemes) were still rendered as links on trusted UI.
- **Fix.** `lib/safe-url.ts::safeUrl` allows only `http:` and `https:`, and is applied at every external link sink.
- **Tests.** `qa/review_ui.py`: "no links with a non-http scheme on the page".

### R-07: False refusals
- **Where.** `ask.py::OUT_OF_SCOPE`, `intent_of`.
- **Root cause.** Bare `predict` and `recommend` matched anywhere in the question.
- **Impact.** "What did management predict for capex?" and "What did the auditor recommend?" were refused as investment advice.
- **Fix.**
  - Refuse only advice addressed to FINN ("would you recommend", "recommend buying", "predict the share price").
  - `predict`, `forecast` and `outlook` now route to the promises analysis.
- **Tests.** `::test_out_of_scope_is_about_advice_not_vocabulary` (6 cases).

### R-09: Dash cells treated as missing
- **Where.** `engine/finn_engine/extract/results.py::rows_from_page`. This is shared by push and research.
- **Root cause.** `-`, `–`, `—` and `Nil` became `None`, which downstream means "not reported".
- **Impact.** A debt-free company prints finance costs as "-", so EBITDA (which needs finance cost and other income) wasn't computed. Exceptional items printed as "-" looked unknown.
- **Fix.** A dash in a figure column is zero, per Indian results convention.
- **Tests.** `test_research_statements.py::test_dash_and_nil_cells_are_zero`, plus the bank test ("Exceptional items" all dashes).

### R-10: EBITDA silently included exceptional items
- **Where.** `research/financials.py::Numbers.ebitda`.
- **Root cause.** `pbt_pre_exc or pbt`, while the formula text always said "PBT before exceptional items".
- **Impact.** In a quarter with an exceptional item and no pre-exceptional line, EBITDA moved by the exceptional amount. The formula shown described a different calculation.
- **Fix.**
  - Use PBT only when exceptional items are absent or zero, and label it so.
  - Otherwise, compute no EBITDA. The sign convention of that row varies, so FINN won't back it out.
- **Tests.** `test_research_statements.py::test_ebitda_never_includes_exceptional_items` (pre-exceptional line used; non-zero exceptional item with no pre-exceptional line refused; dash exceptional item allowed and labelled).

### R-13: Capex "on track" leniency
- **Where.** `research/ledger.py::_pending`.
- **Root cause.** `a.value >= lo * share * 0.8`: an undisclosed 20% allowance below straight-line.
- **Impact.** Spending 41% of a plan at the half-year showed as "on track".
- **Fix.**
  - Straight-line, with the metric's own tolerance (5% for capex).
  - The ledger detail now says "Judged pro rata to the 2 of 4 quarters elapsed", alongside the existing "rest of the year needs ₹X" line.
- **Behaviour change.** KAVERI FY27 capex (₹610 cr of ~₹1,500 cr at H1) moves from "not repeated" to "not repeated; behind". The test expectation was updated with the reason.

### R-14: Index race and temp-file collision
- **Where.** `research/pipeline.py::write`.
- **Root cause.**
  - The read-modify-write of `index.json` had no lock.
  - Fixed temp names (`SYM.tmp`) meant two writers of the same symbol renamed each other's files. The new test caught this as a `FileNotFoundError`.
- **Impact.** Concurrent jobs (service plus CLI) could drop companies from the index or crash a run after all the work was done.
- **Fix.** A thread lock plus a `flock` on `.index.lock`; unique `mkstemp` temp files with atomic `os.replace` for the report, passages and index.
- **Tests.** `::test_index_survives_concurrent_writes` (8 concurrent writers).

### R-15: No stale fallback for the BSE scrip list
- **Where.** `research/sources.py::LiveInputs.bse_scrips`.
- **Impact.** Every BSE outage meant:
  - no BSE code, so BSE filings weren't searched;
  - no industry, so lenders weren't detected (R-12);
  - no market cap.
- **Fix.** Use the last cached copy and say how old it is in the fetch log.
- **Tests.** `::test_bse_scrip_list_falls_back_to_an_older_copy`.

### R-16: Pagination truncation was silent
- **Where.** `engine/finn_engine/sources/bse.py::fetch`.
- **Impact.** A heavy filer with more than 25 pages of announcements in the 1,000-day window lost its oldest filings, such as the earliest guidance calls, with no trace.
- **Fix.** A failed fetch-log entry ("stopped after 25 pages (1250 of N)") now appears in the report's source log. The cap itself is unchanged.
- **Tests.** `::test_bse_pagination_cap_is_reported`.

### R-17: Fixture "today" drifted
- **Where.** `research/service.py::Service.__init__`.
- **Root cause.** `serve` passed `as_of=None`, so fixture runs used the wall clock.
- **Impact.** The fixture date happens to be today. From tomorrow, the window and the open or closed status of guidance would drift away from the documents.
- **Fix.** Fixture-backed services pin `fixtures.AS_OF`.
- **Tests.** `::test_fixture_service_pins_the_fixture_date`.

### R-20: Ask history across report versions
- **Where.** `components/research/AskFinn.tsx`.
- **Root cause.** The sessionStorage key was `finn.ask.SYM`.
- **Impact.** After "Refresh research", earlier answers cited fact ids that could now resolve to different figures, or to nothing.
- **Fix.** The key includes the report's `generated_at`, and keys from older versions are removed on load.
- **Tests.** `qa/review_ui.py`: a stale-version key is dropped, and the current version survives a reload.

## Low

- **R-08.** "No single cost line moved by more than 0.25 pp": the 0.25 is FINN's threshold, not evidence, so the validator correctly dropped the block and the finding vanished. The template now says it in words (`ask.py`).
- **R-18.** `Service._load` caches parsed JSON by file mtime. `Service.ask` keeps one `Asker` (BM25 index) per report version. Test: `::test_reports_are_cached_until_the_file_changes`.
- **R-21.** The engine returns `{"error": "BUSY", "message": …}` but the UI reads `error.message`. `lib/server/research.ts::relay` normalises the shape for the research and Ask routes, and the report GET does too. Verified with curl through the web app.
- **R-22.** `components/ui/Sheet.tsx` is `aria-modal` but Tab escaped it. Tab and Shift+Tab now cycle inside it. Checked in `qa/review_ui.py` (25 tabs).
- **R-23.** The Ask textarea grows to about five lines and resets after sending. Checked in `qa/review_ui.py`.

---

## Open issues

| ID | Severity | Where | Issue | Proposed fix |
|---|---|---|---|---|
| O-5 | High (risk) | parsers, `research/sources.py` | **Never run on a real filing or live endpoint.** The sandbox has no route to NSE or BSE. The fixtures were written by the same author as the parsers, so passing them proves consistency, not coverage. NSE announcement, NSE annual-report and BSE scrip-list field mappings are unconfirmed. | Run `finn research` on 10–15 tickers across sectors (including a bank, an NBFC and a calendar-year reporter) from a network that can reach the exchanges. Save the payloads as `FileInputs` regression fixtures. |
| O-1 | Medium | `research/seed/nse_equity_list_2023-11-05.csv` | When NSE is unreachable, ticker validation uses a 2023 list. Listings since then give `UNVERIFIED_SYMBOL`; renamed or delisted symbols are accepted. | Refresh EQUITY_L.csv daily when reachable; show the list date beside the result (the identity note already states it). |
| O-2 | Medium | `research/periods.py` | Calendar-year reporters and half-yearly SME filers are unsupported: periods assume April–March quarters. | Detect the fiscal year from the results header dates; label periods by end date when it isn't April–March. |
| O-4 | Medium | `apps/web/app/api/v1/*` | No per-client rate limit. Ask is cheap now (R-18), but one client can keep both research slots busy. | Token-bucket per IP in a Next middleware, or put the engine behind a gateway. |
| O-11 | Medium | deployment | `FINN_ENGINE_TOKEN` is off by default. If the engine is exposed beyond localhost without it, anyone can start crawls. | Refuse to bind a non-loopback host without a token. |
| O-3 | Low–Medium | `extract/results.py` vs `research/statements.py` | Two results parsers share the row reader but not field maps, so bank and dash fixes must be kept in step by hand. | Make push use `research.statements` for P&L fields. |
| O-8 | Low–Medium | `research/pipeline.py` | BSE `Mktcap` is assumed to be ₹ crore; unverified live. It feeds P/E. | Confirm against a live payload; keep P/E hidden until confirmed. |
| O-6 | Low | `ask.py::toks` | Crude suffix stemming ("pricing" vs "price" can miss). | Porter stemmer or a small lemma map. |
| O-7 | Low | `pipeline.py::FIN_INDUSTRY` | "credit" in the industry regex could mark a credit-rating agency as a lender. | Match BSE's lender industry names exactly. |
| O-9 | Low | `pipeline.py::FIN_NAME` | Name fallback can mark an insurance holding company ("…Finserv") as a lender; it is flagged in identity notes. | Combine with a statement test (presence of "Interest earned" or "Deposits"). |
| O-10 | Low | `financials.py::growth` | Dead `base == "qoq"` branch (unreachable). | Delete. |
| O-12 | Low | `apps/web` | ESLint isn't configured (`next lint` prompts), so there is no lint gate. | Add `eslint.config.mjs` with `next/core-web-vitals`. |

## Verification run

| Check | Result |
|---|---|
| Engine `pytest tests` | **226 passed**: 200 before the review, plus 26 new (`test_review_fixes.py` 22, `test_research_statements.py` 3, `test_explain.py` 1) |
| `qa/research_interact.py` | 15 / 15 |
| `qa/ask_ui.py` | 18 / 18 |
| `qa/push_interact.py` | all pass, no console errors |
| `qa/cred_shots.py` | no overflow, no errors |
| `qa/review_ui.py` (new) | 22 / 22 (phone 390×844) |
| `tsc --noEmit` | clean |
| Token passthrough (manual) | engine 401 without token; web app with token 200; web app without token shows the normalised UNAUTHORIZED message |
