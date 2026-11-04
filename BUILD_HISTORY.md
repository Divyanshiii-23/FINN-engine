# AI build history

**Authoritative record:** the Claude Code session in which FINN was built, <https://claude.ai/code/session_01BSDCbLwzQYPwCqEmhCKEsE>. That session contains every prompt, response, command and tool output.

This file is a short index written by Claude (the assistant) at release time, from its own context. It is **not** a transcript, and where it and the session differ, the session is right. The session ran long enough that earlier parts were summarised automatically, so this index is coarser for the early phases.

| Phase | What was asked (paraphrased) | What it left in this repository |
|---|---|---|
| Push intelligence | Turn exchange filings and EOD prices for a portfolio into a ranked, explained brief and alerts. Rules given: never invent filings, never present synthetic data as real, keep timestamps and source references, make materiality inspectable, let code (not an LLM) compute metrics, no decorative controls. | `engine/finn_engine/` (sources, dedupe, classify, materiality, market, explain, export), `apps/web` brief, alerts, event and move screens, `engine/README.md` |
| Pull research | Research any valid NSE ticker from primary sources only, in eight sections. Prioritise Narrative vs Numbers. Make every material claim traceable. Distinguish explicit guidance from commentary, and never manufacture targets. Test across sectors. | `engine/finn_engine/research/` (pipeline, statements, claims, ledger, sections), synthetic fixture companies, `engine/RESEARCH.md` |
| Management credibility tracker | An evidence-based historical tracker with no arbitrary trust scores. Explore contradiction detection. | `research/credibility.py`, credibility screens |
| Ask FINN | A question-answering pipeline grounded in retrieved documents, with per-claim citations, stated insufficiency and source navigation, and no general model knowledge. | `research/ask.py`, Ask FINN panel and source viewer |
| Code review | An independent senior-engineer review of the whole codebase: prioritise issues, fix the highest-priority ones, hide nothing. | `REVIEW.md`; security, grounding, financial-logic and mobile fixes; `engine/tests/test_review_fixes.py` |
| Evaluation | A QA and AI-evaluation suite against the running application, recording real failures, fixing critical ones and re-running. | `EVAL.md`, `eval/` (gold sets, harness, results JSON), `engine/tests/test_eval_regressions.py` |
| Release | Prepare for submission: fix critical bugs, verify integration and configuration, deploy, test, document. | `Dockerfile`, `deploy/start.sh`, `.env.example`, `/api/health`, `static-demo/`, this documentation set, the fixture ticker collision fix (a fixture had used a real NSE symbol) |

**How the work was checked:**
- Each phase ended with tests run in the session. The failures and their fixes are recorded in REVIEW.md and EVAL.md, including mistakes in the evaluation harness itself.
- The git history of this repository starts at release time. It was created from the working directory, which wasn't under version control while FINN was built. So the session, not git, is the development history.
