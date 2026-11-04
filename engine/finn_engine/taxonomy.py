"""Announcement taxonomy (ENAM reference, section 1) and classification rules.

Categories follow the reference document exactly. Subtypes carry most of the
materiality signal: a rating *downgrade* and a rating *reaffirmation* share a
category but not an importance.

Rules are ordered; the first match wins. Each rule matches against the filing
subject, headline and the exchange's own sub-category text (lower-cased).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CATEGORIES: dict[str, str] = {
    "results": "Quarterly/annual results, the board meeting approving them, results decks, shareholder letters and results ads",
    "mna": "Acquisition, merger, demerger, joint venture, investment in or sale of a stake",
    "fund_raise": "Rights issues, QIPs, preferential allotments, buybacks, debt such as commercial paper",
    "management_change": "A CEO, CFO, MD or director joining, resigning or retiring",
    "litigation": "Lawsuits, regulatory orders, fines, warnings, insolvency/restructuring",
    "insider_trading": "A promoter or insider buying or selling their own shareholding",
    "earnings_call": "Investor conference call notice, transcript or recording",
    "investor_meetings": "Meetings with specific investors or funds, investor conferences",
    "credit_rating": "Rating assigned, upgraded, downgraded or reaffirmed",
    "dividend": "Cash dividend declared, with record date",
    "bonus_split": "Bonus issue or stock split",
    "capex": "Spend on a new plant, facility or capacity expansion",
    "press_release": "Order wins, products, partnerships, rumour clarifications not covered elsewhere",
    "postal_ballot": "Postal ballot notice and result",
    "agm_egm": "Annual or extraordinary general meeting notice and result",
    "pledging": "Promoter pledge created, released or invoked",
    "unclassified": "Routine, low-relevance paperwork that doesn't move the stock",
}


@dataclass(frozen=True)
class Rule:
    id: str
    category: str
    pattern: str
    subtype: str | None = None
    exclude: str | None = None

    def match(self, text: str) -> re.Match[str] | None:
        if self.exclude and re.search(self.exclude, text):
            return None
        return re.search(self.pattern, text)


# Ordered: routine compliance first (so "ESOP allotment" never becomes a fund
# raise), then the most specific material types, then broad catch-alls.
RULES: list[Rule] = [
    # --- routine compliance paperwork -> unclassified
    Rule("u-share-cert", "unclassified", r"loss of (share )?certificate|duplicate (share )?certificate|reg(ulation|\.)\s*39\s*\(3\)|issue of duplicate", "share_certificates"),
    Rule("u-74-5", "unclassified", r"reg(ulation|\.)\s*74\s*\(5\)|depositories and participants", "compliance_certificate"),
    Rule("u-40-9", "unclassified", r"reg(ulation|\.)\s*40\s*\(9\)|reg(ulation|\.)\s*7\s*\(3\)|compliance certificate", "compliance_certificate"),
    Rule("u-trading-window", "unclassified", r"trading window", "trading_window"),
    Rule("u-esop", "unclassified", r"\besop\b|\besos\b|employee stock option|stock option scheme|allotment of equity shares under .*(esop|employee)", "esop_allotment"),
    Rule("u-shareholding", "unclassified", r"shareholding pattern|investor complaints|statement of investor", "statutory_statement"),
    Rule("u-deviation", "unclassified", r"statement of deviation|monitoring agency", "use_of_proceeds_statement"),
    Rule("u-rpt", "unclassified", r"related party transaction", "related_party_disclosure"),
    Rule("u-esg", "unclassified", r"\besg\b|business responsibility|brsr|sustainability report", "esg_report"),
    Rule("u-registrar", "unclassified", r"registrar (and|&) (share )?transfer agent|\brta\b", "registrar_change"),
    Rule("u-iepf", "unclassified", r"\biepf\b|unclaimed dividend|investor education and protection", "iepf"),
    Rule("u-recon", "unclassified", r"reconciliation of share capital|share capital audit", "statutory_statement"),
    Rule("u-31-4", "unclassified", r"reg(ulation|\.)\s*31\s*\(4\)|no encumbrance (has been )?created|yearly declaration", "annual_declaration"),
    Rule("u-integrated-gov", "unclassified", r"integrated filing.{0,20}governance", "integrated_governance_filing"),
    Rule("u-website", "unclassified", r"change in (the )?(website|e-?mail|registered office|address)|website address|corporate identity number", "contact_change"),
    # --- takeovers and delisting before SAST/insider rules: an open offer is filed under SAST but is an M&A event
    Rule("m-open-offer", "mna", r"open offer|detailed public statement|letter of offer|draft letter of offer", "open_offer"),
    Rule("m-delist", "mna", r"delist", "delisting"),
    # --- pledging before insider trading (pledges are SAST disclosures too)
    Rule("p-invoke", "pledging", r"invocation of pledge|pledge.*invoked|invoked.*pledge", "invocation"),
    Rule("p-release", "pledging", r"release of (pledge|encumbrance)|revocation of (pledge|encumbrance)", "release"),
    Rule("p-create", "pledging", r"pledge|encumbrance", "creation"),
    # --- credit rating
    Rule("cr-downgrade", "credit_rating", r"(credit )?rating.*(downgrad|revised downward|lowered)|downgrad.*rating", "downgrade"),
    Rule("cr-upgrade", "credit_rating", r"(credit )?rating.*(upgrad|revised upward)|upgrad.*rating", "upgrade"),
    Rule("cr-reaffirm", "credit_rating", r"(credit )?rating.*(reaffirm|re-affirm|retain)", "reaffirm"),
    Rule("cr-withdrawn", "credit_rating", r"(credit )?rating.*withdraw", "withdrawn"),
    Rule("cr-generic", "credit_rating", r"credit rating|rating (agency|action)|\b(crisil|icra|care ratings|india ratings)\b", "rating_update"),
    # --- insider trading
    Rule("it-promoter-sale", "insider_trading", r"promoter.{0,40}\b(sold|sale|sell|sells|offload|divest)|(sold|sale of).{0,60}by (the |a |an )?promoter|block deal|bulk deal", "promoter_sale"),
    Rule("it-substantial", "insider_trading", r"reg(ulation|\.)\s*29\s*\(1\)|acqui(red|sition) of [\d.]+\s?%", "substantial_acquisition"),
    Rule("it-pit", "insider_trading", r"insider trading|\bpit\b|prohibition of insider|reg(ulation|\.)\s*7\s*\(2\)|\bsast\b|reg(ulation|\.)\s*29\s*\(", "disclosure"),
    # --- earnings call
    Rule("ec-transcript", "earnings_call", r"transcript", "transcript"),
    Rule("ec-recording", "earnings_call", r"audio recording|video recording|recording of .*call", "recording"),
    Rule("ec-notice", "earnings_call", r"earnings call|conference call|con-?call|analyst call|investor call", "notice"),
    # --- investor meetings
    Rule("im-meet", "investor_meetings", r"analyst.{0,30}meet|investor.{0,30}meet|institutional investor|investor conference|investor day|schedule of (analyst|investor)", "meeting_schedule"),
    # --- postal ballot / general meetings
    Rule("pb", "postal_ballot", r"postal ballot|e-?voting result", "postal_ballot"),
    Rule("agm", "agm_egm", r"annual general meeting|\bagm\b|extra-?ordinary general meeting|\begm\b|book closure", "general_meeting"),
    Rule("pr-clar-early", "press_release", r"\bclarification\b|news (item|report)|media report|rumou?r", "clarification"),
    # --- results family
    Rule("r-intimation", "results", r"(intimation|notice) of board meeting|board meeting (intimation|to be held)|prior intimation", "board_meeting_intimation"),
    Rule("r-newspaper", "results", r"newspaper (publication|advertisement)|publication of (financial )?results|copy of newspaper", "newspaper_publication"),
    Rule("r-presentation", "results", r"investor presentation|earnings presentation|results presentation|analyst presentation", "investor_presentation"),
    Rule("r-financials", "results", r"financial results|unaudited.{0,40}results|audited.{0,40}results|results for the (quarter|half|year|period)|integrated filing.{0,20}financial", "financial_results"),
    # --- corporate actions
    Rule("bs-bonus", "bonus_split", r"\bbonus\b", "bonus"),
    Rule("bs-split", "bonus_split", r"sub-?division|stock split|split of (equity )?shares", "split"),
    Rule("d-special", "dividend", r"special dividend", "special"),
    Rule("d-dividend", "dividend", r"dividend", "dividend"),
    Rule("l-default", "litigation", r"\bdefault(ed|s)?\b.{0,40}(payment|interest|principal|repayment|dues|obligation)|delay(ed)? in (the )?(payment|servicing|repayment)|non-?payment of (interest|principal)", "payment_default"),
    Rule("fr-buyback", "fund_raise", r"buy-?back", "buyback"),
    Rule("fr-qip", "fund_raise", r"\bqip\b|qualified institution", "qip"),
    Rule("fr-rights", "fund_raise", r"rights issue|rights entitlement", "rights"),
    Rule("fr-pref", "fund_raise", r"preferential (issue|allotment)", "preferential"),
    Rule("fr-debt", "fund_raise", r"non-?convertible debenture|\bncds?\b|commercial paper|bonds?\b.*(issue|allot)|fund rais", "debt"),
    # --- management change (auditor first: different materiality)
    Rule("mc-auditor-resign", "management_change", r"(resignation|cessation).{0,60}auditor|auditor.{0,60}(resign|cessation)", "auditor_resignation"),
    Rule("mc-auditor", "management_change", r"appointment of .{0,30}auditor|auditor.{0,30}appoint", "auditor_appointment"),
    Rule("mc-demise", "management_change", r"demise|passed away|death of", "demise"),
    Rule("mc-resign-concerns", "management_change", r"resign.{0,160}\b(concerns?|governance|differences|disagree|not satisf|unable to function|pressure)\b", "resignation_with_concerns"),
    Rule("mc-resign", "management_change", r"resignation|cessation|steps down|stepping down|retire", "resignation"),
    Rule("mc-appoint", "management_change", r"appointment|appointed|re-?appointment|change in (directorate|management|kmp|key managerial)|designated as", "appointment"),
    # --- litigation and regulatory
    Rule("l-search", "litigation", r"search (operations?|and seizure|&\s*seizure)|survey (operations?|by|under)|section 133a|income.?tax (search|survey|authorities conducted)|\braid\b|enforcement directorate|\bcbi\b", "search_or_investigation"),
    Rule("l-regulator-order", "litigation", r"sebi.{0,40}\b(order|restrain|debar|prohibit)|interim order|restrain(ed|ing)?\b.{0,40}(securities market|accessing)|debarred", "regulator_order"),
    Rule("l-insolvency", "litigation", r"insolvency|\bnclt\b|\bcirp\b|winding up|resolution professional", "insolvency", exclude=r"scheme|amalgamation|merger|demerger|arrangement"),
    Rule("l-eir", "litigation", r"establishment inspection report|\beir\b.{0,40}(usfda|fda)|classif\w+ .{0,30}\b(vai|nai)\b", "inspection_closed"),
    Rule("l-warning", "litigation", r"warning letter|import alert|form 483|observations? from (the )?(us ?fda|regulator)", "regulatory_warning"),
    Rule("l-tax", "litigation", r"(tax|gst|income.?tax).{0,30}(demand|order|notice|assessment)|demand order", "tax_demand"),
    Rule("l-penalty", "litigation", r"penalt|\bfine[ds]?\b|show cause|adjudication|sebi order|regulatory action|order (passed|received) .{0,40}(authority|tribunal|court|commission)", "penalty_or_order"),
    Rule("l-litigation", "litigation", r"litigation|lawsuit|court|tribunal|arbitration|search (and|&) seizure|\braid\b", "litigation"),
    # --- operational disruptions: not in the ENAM category list, filed as press releases but scored as events
    Rule("pr-disruption", "press_release", r"\bfire\b|explosion|gas leak|accident at|disruption of operations|operations (at .{0,30})?(are |were |have been )?(suspended|halted|disrupted)|production (is |has been )?(affected|halted|stopped)|cyber.?(security )?(incident|attack)|ransomware|\bflood|\bstrike\b|lock-?out", "disruption",
         exclude=r"scheduled|planned|maintenance"),
    # --- M&A
    Rule("m-demerger", "mna", r"demerger|de-merger|spin-?off|hive-?off", "demerger"),
    Rule("m-scheme", "mna", r"amalgamation|merger|scheme of arrangement", "scheme"),
    Rule("m-jv", "mna", r"joint venture|\bjv\b", "joint_venture"),
    Rule("m-acq", "mna", r"acqui(re|sition)|investment in .{0,40}(subsidiary|company|shares)|stake (in|sale)|divest|disinvest|sale of .{0,30}(stake|subsidiary|business|undertaking)", "acquisition_or_divestment"),
    # --- capex
    Rule("cx", "capex", r"capacity expansion|capex|capital expenditure|new (plant|facility|unit)|greenfield|brownfield|commission(ing|ed) of|commercial production|commencement of (commercial )?operations", "expansion"),
    # --- a board outcome that matched nothing more specific above
    Rule("r-outcome", "results", r"outcome of (the )?board meeting", "board_meeting_outcome"),
    # --- press releases
    Rule("pr-order", "press_release", r"\border\b.{0,40}(win|won|receiv|bag|secur|award)|(bag|secur|receiv|win)(s|ging|ing)? (of )?.{0,30}order|letter of (award|intent)|\bloa\b|\bloi\b|work order|purchase order", "order_win"),
    Rule("pr-clar", "press_release", r"clarification|rumou?r|news (item|report)|media report", "clarification"),
    Rule("pr-launch", "press_release", r"launch|partnership|collaborat|agreement|mou\b|tie-?up", "business_update"),
    Rule("pr-operating", "press_release", r"business update|operational update|monthly (sales|business)|sales (volumes?|numbers) for|quarterly update", "operating_update"),
    Rule("pr-generic", "press_release", r"press release|media release|update", "general"),
]

# Base importance for (category, subtype); subtype-less falls back to category.
PRIORS: dict[tuple[str, str | None], int] = {
    ("results", "financial_results"): 55,
    ("results", "board_meeting_outcome"): 45,
    ("results", "investor_presentation"): 25,
    ("results", "board_meeting_intimation"): 12,
    ("results", "newspaper_publication"): 5,
    ("mna", None): 50,
    ("mna", "open_offer"): 65,
    ("mna", "delisting"): 70,
    ("mna", "demerger"): 65,
    ("fund_raise", "qip"): 45,
    ("fund_raise", "rights"): 45,
    ("fund_raise", "preferential"): 40,
    ("fund_raise", "buyback"): 45,
    ("fund_raise", "debt"): 25,
    ("management_change", "auditor_resignation"): 60,
    ("management_change", "auditor_appointment"): 8,
    ("management_change", "resignation"): 40,
    ("management_change", "resignation_with_concerns"): 65,
    ("management_change", "demise"): 65,
    ("management_change", "appointment"): 30,
    ("litigation", "insolvency"): 60,
    ("litigation", "regulatory_warning"): 65,
    ("litigation", "payment_default"): 75,
    ("litigation", "inspection_closed"): 30,
    ("litigation", "search_or_investigation"): 65,
    ("litigation", "regulator_order"): 65,
    ("litigation", "tax_demand"): 30,
    ("litigation", "penalty_or_order"): 35,
    ("litigation", "litigation"): 30,
    ("insider_trading", None): 30,
    ("insider_trading", "promoter_sale"): 50,
    ("insider_trading", "substantial_acquisition"): 40,
    ("earnings_call", "notice"): 20,
    ("earnings_call", "transcript"): 12,
    ("earnings_call", "recording"): 5,
    ("investor_meetings", None): 5,
    ("credit_rating", "downgrade"): 60,
    ("credit_rating", "upgrade"): 40,
    ("credit_rating", "withdrawn"): 30,
    ("credit_rating", "reaffirm"): 10,
    ("credit_rating", "rating_update"): 25,
    ("dividend", None): 25,
    ("dividend", "special"): 40,
    ("bonus_split", None): 40,
    ("capex", None): 40,
    ("press_release", "order_win"): 35,
    ("press_release", "clarification"): 30,
    ("press_release", "business_update"): 25,
    ("press_release", "general"): 15,
    ("press_release", "operating_update"): 40,
    ("press_release", "disruption"): 65,
    ("postal_ballot", None): 5,
    ("agm_egm", None): 5,
    ("pledging", "invocation"): 65,
    ("pledging", "creation"): 40,
    ("pledging", "release"): 20,
    ("unclassified", "needs_review"): 36,  # unknown: surface in the brief, don't bury
    ("unclassified", None): 2,
}

# Subtypes that are routine paperwork whatever their category.
ROUTINE: set[tuple[str, str | None]] = {
    ("results", "newspaper_publication"),
    ("results", "board_meeting_intimation"),
    ("earnings_call", "recording"),
    ("management_change", "auditor_appointment"),
    ("credit_rating", "reaffirm"),
}
ROUTINE_CATEGORIES = {"unclassified", "investor_meetings", "postal_ballot", "agm_egm"}

# Hard floors: always interrupt (architecture doc, module 4).
FLOORS: dict[tuple[str, str], str] = {
    ("credit_rating", "downgrade"): "Rating downgrades always surface",
    ("management_change", "auditor_resignation"): "Auditor resignations always surface",
    ("pledging", "invocation"): "Pledge invocations always surface",
    ("litigation", "insolvency"): "Insolvency proceedings always surface",
    ("litigation", "payment_default"): "Defaults on debt payments always surface",
    ("management_change", "demise"): "The death of a director or executive always surfaces",
}


def prior(category: str, subtype: str | None) -> int:
    return PRIORS.get((category, subtype), PRIORS.get((category, None), 15))


def is_routine(category: str, subtype: str | None) -> bool:
    if (category, subtype) == ("unclassified", "needs_review"):
        return False
    return category in ROUTINE_CATEGORIES or (category, subtype) in ROUTINE
