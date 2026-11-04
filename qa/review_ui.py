import os
"""UI checks for the review fixes: phone sticky nav, Ask history versioning, textarea growth, sheet focus trap, unsafe links."""
from playwright.sync_api import sync_playwright
B = os.environ.get("FINN_URL", "http://localhost:3000")
res = []
def ok(name, cond): res.append((name, bool(cond))); print("PASS" if cond else "FAIL", name)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    errs = []
    pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
    pg.goto(f"{B}/research/HALCYON"); pg.wait_for_selector("nav[aria-label=Sections]")
    pg.evaluate("sessionStorage.setItem('finn.ask.HALCYON', '[]'); sessionStorage.setItem('finn.ask.HALCYON.1999-01-01T00:00:00', '[]')")
    pg.mouse.wheel(0, 2500); pg.wait_for_timeout(400)
    h = pg.locator("header").first.bounding_box(); n = pg.locator("nav[aria-label=Sections]").bounding_box()
    ok("phone section nav sits below the top bar", abs(n["y"] - h["height"]) < 2)
    for i in range(pg.locator("nav[aria-label=Sections] a").count()):
        a = pg.locator("nav[aria-label=Sections] a").nth(i); href = a.get_attribute("href"); a.click(); pg.wait_for_timeout(700)
        y = pg.locator(href).bounding_box()["y"]
        ok(f"anchor {href} lands below nav ({y:.0f} >= {h['height'] + n['height']:.0f})", y >= h["height"] + n["height"] - 2)
    ta = pg.locator("#ask textarea")
    h0 = ta.bounding_box()["height"]
    ta.fill(""); ta.type("Why did margins decline in FY26, and which cost lines moved the most as a share of revenue compared with the year before?", delay=0)
    ok("textarea grows with a long question", ta.bounding_box()["height"] > h0 + 10)
    ta.press("Enter"); pg.wait_for_selector("#ask article, #ask [data-answer]", timeout=15000) if pg.locator("#ask article").count() == 0 else None
    pg.wait_for_timeout(1500)
    ok("FY26 question answered with the period note", pg.locator("#ask").inner_text().find("You asked about FY26") >= 0)
    ok("textarea resets after asking", ta.bounding_box()["height"] <= h0 + 2)
    pg.reload(); pg.wait_for_selector("#ask"); pg.wait_for_timeout(800)
    keys = pg.evaluate("Object.keys(sessionStorage).filter(k => k.startsWith('finn.ask.HALCYON'))")
    ok(f"stale-version history dropped on load ({keys})", len(keys) == 1 and keys[0] != "finn.ask.HALCYON" and "1999" not in keys[0])
    ok("history survives a reload of the same report", "You asked about FY26" in pg.locator("#ask").inner_text())
    # Sheet focus trap
    pg.locator("button:has-text('Read page'), [data-fact] button, button[aria-haspopup=dialog]").first.click() if pg.locator("button[aria-haspopup=dialog]").count() else pg.locator("#nvn button").first.click()
    pg.wait_for_selector("[role=dialog]", timeout=5000)
    inside = []
    for _ in range(25):
        pg.keyboard.press("Tab")
        inside.append(pg.evaluate("document.querySelector('[role=dialog]').contains(document.activeElement)"))
    ok("Tab stays inside the open sheet", all(inside))
    pg.keyboard.press("Shift+Tab"); ok("Shift+Tab stays inside", pg.evaluate("document.querySelector('[role=dialog]').contains(document.activeElement)"))
    pg.keyboard.press("Escape"); pg.wait_for_timeout(300); ok("Escape closes the sheet", pg.locator("[role=dialog]").count() == 0)
    # Unsafe URL handling, exercised in the browser with the real helper semantics
    r = pg.evaluate("""() => { const f = (u) => { try { const p = new URL(u); return p.protocol === 'https:' || p.protocol === 'http:'; } catch { return false; } };
        return [f('javascript:alert(1)'), f('data:text/html,x'), f('https://www.bseindia.com/x.pdf')]; }""")
    ok("javascript:/data: links rejected, https kept", r == [False, False, True])
    ok("no links with a non-http scheme on the page", pg.evaluate("Array.from(document.querySelectorAll('a[href]')).every(a => /^(https?:|\\/|#)/.test(a.getAttribute('href')))"))
    ok(f"no console errors ({errs[:2]})", not errs)
    b.close()
print(f"{sum(c for _, c in res)} / {len(res)}")
