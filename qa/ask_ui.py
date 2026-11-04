import os
from playwright.sync_api import sync_playwright
B=os.environ.get("FINN_URL", "http://localhost:3000"); OUT=os.environ.get("FINN_QA_OUT", "/tmp/finn-qa"); errs=[]; ok=[]
os.makedirs(OUT, exist_ok=True)
def check(n,c): ok.append(c); print(("PASS " if c else "FAIL ")+n)
with sync_playwright() as p:
    b=p.chromium.launch()
    for name, vp in [("phone", dict(width=390, height=844)), ("desk", dict(width=1440, height=900))]:
        ctx=b.new_context(viewport=vp, device_scale_factor=2); pg=ctx.new_page()
        pg.on("console", lambda m: m.type=="error" and errs.append(m.text)); pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(f"{B}/research/KAVERI"); pg.wait_for_selector("text=Ask FINN about KAVERI")
        pg.evaluate("sessionStorage.clear()"); pg.reload(); pg.wait_for_selector("text=Ask FINN about KAVERI")
        chips = pg.get_by_role("list", name="Suggested questions").get_by_role("button")
        check(f"{name}: suggestions from the report", chips.count() >= 4)
        chips.filter(has_text="Why did margins decline").click()
        pg.wait_for_selector("text=Answered from the documents"); pg.wait_for_timeout(300)
        pg.locator("#ask").scroll_into_view_if_needed(); pg.screenshot(path=f"{OUT}/ask-{name}-margins.png")
        check(f"{name}: cost-line fact shown", pg.locator("#ask").get_by_text("other expenses").count() >= 1)
        # passage citation -> source viewer with page navigation
        pg.locator("#ask figcaption button").first.click(); pg.wait_for_selector("text=cited")
        dlg = pg.get_by_role("dialog")
        check(f"{name}: source viewer opens at the cited passage", dlg.get_by_text("Realisations came under pressure").count() >= 1)
        pg.screenshot(path=f"{OUT}/ask-{name}-source.png")
        before = dlg.locator("select").input_value()
        dlg.get_by_role("button", name=lambda: True) if False else None
        dlg.locator("button", has_text="Page").last.click(); pg.wait_for_timeout(300)
        check(f"{name}: next page navigates", dlg.locator("select").input_value() != before)
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        # fact citation -> evidence sheet -> read page in document
        pg.locator("#ask button[aria-label^='Source']").first.click(); pg.wait_for_timeout(300)
        ev = pg.get_by_role("dialog")
        check(f"{name}: figure opens its formula", ev.get_by_text("Formula").count() == 1)
        ev.locator("ul button", has_text="Revenue from operations").first.click(); pg.wait_for_timeout(200)
        ev.get_by_role("button", name="Read page").click(); pg.wait_for_selector("text=Consolidated", timeout=5000)
        check(f"{name}: figure leads to its statement page", pg.get_by_role("dialog").get_by_text("Revenue from operations").count() >= 1)
        pg.screenshot(path=f"{OUT}/ask-{name}-table-page.png")
        pg.keyboard.press("Escape"); pg.wait_for_timeout(200)
        box = pg.get_by_label("Question about KAVERI")
        for q, expect in [("What did management promise regarding capacity expansion?", "Answered from the documents"),
                          ("What is the CEO's salary?", "Not enough evidence"), ("Should I buy this stock?", "Outside what FINN answers")]:
            box.fill(q); box.press("Enter"); pg.wait_for_selector(f"article:has-text(\"{q}\")", timeout=10000); pg.wait_for_timeout(300)
            check(f"{name}: {q} -> {expect}", pg.locator("article").first.get_by_text(expect).count() == 1)
        pg.locator("article").nth(2).scroll_into_view_if_needed(); pg.screenshot(path=f"{OUT}/ask-{name}-capacity.png")
        print(name, "overflow", pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"))
        ctx.close()
    b.close()
print("errors", errs); print(sum(ok), "/", len(ok))
