"""Static demo: the published files (static-demo/dist), served locally, in Chromium.

    python3 -m http.server -d static-demo/dist 4000 &   FINN_STATIC_URL=http://127.0.0.1:4000 python qa/static_demo.py

This checks the files, not the hosted page: the claude.ai viewer wraps them in its own frame,
which this test does not reproduce.
"""
import os
import re

from playwright.sync_api import sync_playwright

B = os.environ.get("FINN_STATIC_URL", "http://127.0.0.1:4000")
res, errs = [], []


def ok(name, cond, detail=""):
    res.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  | {detail}"))


OVERFLOW = "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"

with sync_playwright() as p:
    br = p.chromium.launch()
    for w, h in ((390, 844), (320, 640), (1440, 900)):
        pg = br.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        for hsh, expect in (("#brief", r"SYNTHETIC|fixture|synthetic"), ("#portfolio", r"holdings"), ("#alerts", r"Alerts"), ("#alerts-rules", r"Price move in a day"),
                            ("#research", r"NSE ticker"), ("#research-HALCYON", r"Narrative vs Numbers"), ("#credibility-KAVERI", r"redibility"), ("#move-SARANG", r"SARANG")):
            pg.goto(f"{B}/{hsh}")
            pg.wait_for_timeout(900)
            t = pg.locator("body").inner_text()
            ok(f"{w}px {hsh} renders", re.search(expect, t, re.I) and "Application error" not in t, t[:120].replace("\n", " "))
            ok(f"{w}px {hsh} no horizontal overflow", pg.evaluate(OVERFLOW))
        pg.close()
    pg = br.new_page(viewport={"width": 390, "height": 844})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"{B}/#research")
    box = pg.get_by_role("combobox")
    for q, want in (("reliance", "RELIANCE"), ("M&M", "M&M"), ("kaveri", "KAVERI")):
        box.fill(q)
        pg.wait_for_timeout(500)
        opts = [o.split()[0] for o in pg.locator("[role=listbox] [role=option]").all_inner_texts() if o.split() and not o.startswith("Try ")]
        ok(f"search '{q}' finds {want}", want in opts, str(opts[:5]))
    box.fill("kaveri")
    pg.wait_for_timeout(400)
    pg.locator("[role=option]", has_text="KAVERI").first.dispatch_event("mousedown")
    pg.wait_for_timeout(1200)
    ok("selecting a result opens the report", "#research-KAVERI" in pg.url and pg.locator("nav[aria-label=Sections]").count() == 1, pg.url)
    pg.locator("button.num.underline").first.click()
    pg.wait_for_timeout(600)
    ok("a figure opens its evidence sheet", pg.locator("[role=dialog]").count() == 1)
    rd = pg.get_by_role("button", name=re.compile("Read page"))
    if rd.count():
        rd.first.click()
        pg.wait_for_timeout(800)
        ok("evidence opens the source page viewer", "Page" in pg.locator("[role=dialog]").last.inner_text())
    pg.keyboard.press("Escape")
    pg.keyboard.press("Escape")
    pg.goto(f"{B}/#research-KAVERI")
    pg.wait_for_selector("#ask textarea")
    ok("Ask FINN is disabled with a reason (no engine in the static demo)", pg.locator("#ask textarea").is_disabled() and re.search(r"engine", pg.locator("#ask").inner_text(), re.I))
    pg.goto(f"{B}/#research-POLYCAB")
    pg.wait_for_timeout(1200)
    ok("an unbuilt ticker explains that research needs the engine", re.search(r"engine", pg.locator("main").inner_text(), re.I), pg.locator("main").inner_text()[:160])
    pg.goto(f"{B}/#brief")
    pg.wait_for_timeout(800)
    pg.locator("a[href*='event-'], a[href^='#event-']").first.click()
    pg.wait_for_timeout(900)
    ok("brief -> event detail", "#event-" in pg.url and "Materiality" in pg.locator("main").inner_text(), pg.url)
    ok("no page errors", not errs, str(errs[:3]))
    br.close()
print(f"{sum(res)} / {len(res)}")
