import os
from playwright.sync_api import sync_playwright
B=os.environ.get("FINN_URL", "http://localhost:3000"); OUT=os.environ.get("FINN_QA_OUT", "/tmp/finn-qa"); errs=[]
os.makedirs(OUT, exist_ok=True)
with sync_playwright() as p:
    b=p.chromium.launch()
    for name, vp in [("phone", dict(width=390, height=844)), ("desk", dict(width=1440, height=900))]:
        ctx=b.new_context(viewport=vp, device_scale_factor=2); pg=ctx.new_page()
        pg.on("console", lambda m: m.type=="error" and errs.append(m.text)); pg.on("pageerror", lambda e: errs.append(str(e)))
        for sym in ["KAVERI","SARANG","VEDIKA","HALCYON"]:
            pg.goto(f"{B}/research/{sym}/credibility"); pg.wait_for_selector("text=Track record"); pg.wait_for_timeout(500)
            pg.screenshot(path=f"{OUT}/cred-{name}-{sym}-top.png")
            print(name, sym, "overflow", pg.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"))
            if sym=="KAVERI":
                pg.locator("#timeline").scroll_into_view_if_needed(); pg.wait_for_timeout(300)
                pg.screenshot(path=f"{OUT}/cred-{name}-{sym}-lanes.png")
                pg.locator("article").first.get_by_role("button", name="Show the observations").click(); pg.wait_for_timeout(200)
                pg.locator("article").first.scroll_into_view_if_needed(); pg.screenshot(path=f"{OUT}/cred-{name}-{sym}-delivery.png")
        pg.goto(f"{B}/research/KAVERI"); pg.wait_for_selector("text=Management credibility"); pg.wait_for_timeout(300)
        pg.get_by_text("Management credibility").first.scroll_into_view_if_needed(); pg.screenshot(path=f"{OUT}/cred-{name}-card.png")
        ctx.close()
    b.close()
print("errors", errs)
