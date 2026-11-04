"""Pull research: on-demand, primary-source research for any NSE equity.

Two paths that never share text meet only at a deterministic join:

* the numbers path reads results filings (and, where present, the statement
  of assets and liabilities and the cash flow statement filed with them);
* the narrative path reads call transcripts, investor presentations and the
  annual report, and turns management statements into typed claims.

No broker reports, news or model knowledge are read. Every item in the
output carries an info_class and evidence pointing at a document and page.
"""

RESEARCH_VERSION = "research-v1"
CLAIMS_VERSION = "claims-rules-v1"
