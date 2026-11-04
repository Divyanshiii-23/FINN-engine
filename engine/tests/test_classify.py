import pytest

from finn_engine.classify import classify
from finn_engine.taxonomy import CATEGORIES, RULES

from .conftest import ann

CASES = [
    # (subject, headline, category, subtype, routine)
    ("Financial Results for the Quarter Ended 30 September 2026", "Unaudited financial results", "results", "financial_results", False),
    ("Board Meeting Intimation for Consideration of Financial Results", None, "results", "board_meeting_intimation", True),
    ("Newspaper Publication", "Copy of newspaper publication of financial results", "results", "newspaper_publication", True),
    ("Investor Presentation", "Investor presentation for Q2 FY27", "results", "investor_presentation", False),
    ("Acquisition", "Agreement to acquire 100% stake in a diagnostics chain", "mna", "acquisition_or_divestment", False),
    ("Scheme of Amalgamation", None, "mna", "scheme", False),
    ("Outcome of Board Meeting - Fund Raising", "Board approved raising up to Rs. 600 crore through a QIP", "fund_raise", "qip", False),
    ("Buyback of equity shares", None, "fund_raise", "buyback", False),
    ("Resignation of Chief Financial Officer", "Mr. S. Kulkarni has resigned", "management_change", "resignation", False),
    ("Appointment of Independent Director", None, "management_change", "appointment", False),
    ("Resignation of Statutory Auditor", None, "management_change", "auditor_resignation", False),
    ("Disclosure under Regulation 30 - Receipt of Warning Letter", None, "litigation", "regulatory_warning", False),
    ("Disclosure of Tax Demand Order", "GST demand order of Rs. 38 crore", "litigation", "tax_demand", False),
    ("Admission of application under IBC by NCLT", "Corporate insolvency resolution process initiated", "litigation", "insolvency", False),
    ("Disclosure under SEBI (Prohibition of Insider Trading) Regulations, 2015", None, "insider_trading", "disclosure", False),
    ("Intimation of Earnings Call", None, "earnings_call", "notice", False),
    ("Transcript of Earnings Call", None, "earnings_call", "transcript", False),
    ("Audio Recording of Earnings Call", None, "earnings_call", "recording", True),
    ("Schedule of Analyst / Institutional Investor Meetings", None, "investor_meetings", "meeting_schedule", True),
    ("Credit Rating", "revised the long-term rating from AA- to A+, a downgrade", "credit_rating", "downgrade", False),
    ("Credit Rating", "rating reaffirmed at AA", "credit_rating", "reaffirm", True),
    ("Corporate Action - Declaration of Interim Dividend", None, "dividend", "dividend", False),
    ("Bonus Issue of Equity Shares", None, "bonus_split", "bonus", False),
    ("Sub-division of equity shares", None, "bonus_split", "split", False),
    ("Outcome of Board Meeting - Capacity Expansion", "Board approved capex of Rs. 1,150 crore", "capex", "expansion", False),
    ("Press Release - Order Win", "The Company bags an order worth Rs. 410 crore", "press_release", "order_win", False),
    ("Clarification on news item", None, "press_release", "clarification", False),
    ("Postal Ballot Notice", None, "postal_ballot", "postal_ballot", True),
    ("Proceedings of Annual General Meeting", None, "agm_egm", "general_meeting", True),
    ("Disclosure under SEBI SAST - Encumbrance of Shares", "Promoter has created a pledge", "pledging", "creation", False),
    ("Invocation of pledge on promoter shares", None, "pledging", "invocation", False),
    ("Closure of Trading Window", None, "unclassified", "trading_window", True),
    ("Compliance Certificate under Regulation 74(5)", None, "unclassified", "compliance_certificate", True),
    ("Allotment of Equity Shares under ESOP Scheme", None, "unclassified", "esop_allotment", True),
    ("Intimation of Loss of Share Certificate", None, "unclassified", "share_certificates", True),
]


@pytest.mark.parametrize("subject,headline,cat,sub,routine", CASES)
def test_rules(subject, headline, cat, sub, routine):
    c = classify(ann(subject, headline))
    assert (c.category, c.subtype, c.routine) == (cat, sub, routine), c


def test_every_reference_category_is_reachable():
    assert {r.category for r in RULES} == set(CATEGORIES)
    assert {c[2] for c in CASES} == set(CATEGORIES)


def test_bse_company_prefix_is_ignored():
    # "COMPANY - 990102 - " must not influence the rule match
    c = classify(ann("ORDER WIN TRADERS LTD - 990102 - Closure of Trading Window"))
    assert c.category == "unclassified" and c.subtype == "trading_window"


def test_unknown_filing_is_surfaced_not_buried():
    c = classify(ann("Intimation regarding a matter of a general nature"))
    assert c.method == "fallback" and c.category == "unclassified" and c.routine is False and c.confidence == "low"


def test_esop_allotment_is_not_a_fund_raise():
    assert classify(ann("Allotment of equity shares under ESOP 2019")).category == "unclassified"


def test_website_change_is_routine_paperwork():
    c = classify(ann("Intimation regarding change in website address"))
    assert c.category == "unclassified" and c.subtype == "contact_change" and c.routine


@pytest.mark.parametrize("subject,headline,category,subtype", [
    ("Open Offer - Detailed Public Statement", "Detailed public statement for the open offer by the acquirer", "mna", "open_offer"),
    ("Proposal for Voluntary Delisting of Equity Shares", "Delisting proposal from the promoter", "mna", "delisting"),
    ("Default in payment of interest on Non-Convertible Debentures", "Delay in payment of interest due on listed NCDs", "litigation", "payment_default"),
    ("Search operations by Income Tax Department", "Income tax officials conducted search operations", "litigation", "search_or_investigation"),
    ("Order of SEBI", "SEBI has passed an order restraining the promoters from accessing the securities market", "litigation", "regulator_order"),
    ("Disruption of operations due to fire", "A fire broke out at Unit 3; operations are suspended", "press_release", "disruption"),
    ("NCLT sanctions Scheme of Amalgamation", "The NCLT has sanctioned the scheme of amalgamation", "mna", "scheme"),
    ("Clarification on news item appearing in media", "Clarification on a news report", "press_release", "clarification"),
    ("Intimation of demise of Chairman", "Sad demise of the Chairman", "management_change", "demise"),
    ("Announcement under Regulation 30 (LODR)-Updates", "Plant shutdown for 25 days for scheduled maintenance", "press_release", "general"),
])
def test_review_eval_rules(subject, headline, category, subtype):
    a = ann(subject)
    a.headline = headline
    c = classify(a)
    assert (c.category, c.subtype) == (category, subtype)
