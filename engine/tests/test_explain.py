from finn_engine.explain import grounded, llm_explain, template
from finn_engine.models import Classification, Company, Explanation, Facts
from finn_engine.materiality import score


def _base():
    c = Classification(category="press_release", subtype="order_win", routine=False)
    f = Facts(amounts_cr=[410])
    m = score(Company(symbol="Q", name="Q", revenue_ttm_cr=2150), c, f, None, None, False)
    return template(c, f, None, m, "Press Release - Order Win", "Bags an order worth Rs. 410 crore", False), f


def test_template_uses_computed_figures():
    e, _ = _base()
    assert e.generator == "template" and e.grounded
    assert "19.1%" in e.why and "410" in e.why


def test_grounding_rejects_invented_numbers():
    src = "Order received worth 410 crore, equal to 19.1% of revenue of 2150 crore"
    ok, _ = grounded("Order worth 410 crore, 19.1% of revenue", src)
    bad, reason = grounded("Order worth 410 crore lifts margins by 300 bps", src)
    assert ok and not bad and "300" in reason


def test_grounding_rejects_added_causes_judgements_and_names():
    src = "EBIT margin was 20.2% in Q2 FY27 against 20.6% in Q2 FY26, a fall of 0.4 pp."
    assert grounded("The EBIT margin fell to 20.2% in Q2 FY27 from 20.6% in Q2 FY26, down 0.4 pp.", src)[0]
    for text, why in [("EBIT margin fell to 20.2% from 20.6% due to pricing pressure.", "causal"),
                      ("A strong quarter: EBIT margin was 20.2%.", "judgement"),
                      ("EBIT margin was 20.2% as Infosys gained share.", "names"),
                      ("Margin fell to 20.2% as management cut prices to win orders.", "trace")]:
        ok, reason = grounded(text, src)
        assert not ok and why in reason, (text, reason)


def test_llm_output_with_stray_number_falls_back_to_template():
    base, f = _base()
    out = llm_explain(base, {"facts": f.model_dump()}, lambda p: '{"what": "Won a 410 crore order", "why": "Could add 12% to earnings"}', "fake-model")
    assert out.generator == "template" and "12" in out.rejected_llm_reason


def test_grounded_llm_output_is_accepted_and_labelled():
    base, f = _base()
    out = llm_explain(base, {"facts": f.model_dump()}, lambda p: '{"what": "Won an order worth 410 crore.", "why": "It equals 19.1% of trailing revenue."}', "fake-model")
    assert out.generator == "llm:fake-model" and out.grounded


def test_unparseable_llm_output_falls_back():
    base, f = _base()
    out = llm_explain(base, {}, lambda p: "sure! here is a summary", "fake-model")
    assert out.generator == "template" and "unparseable" in out.rejected_llm_reason
