import os
"""Behaviour checks for the push-intelligence UI against the fixture feed."""
import re
from playwright.sync_api import sync_playwright

BASE = os.environ.get("FINN_URL", "http://localhost:3000")
results, errors = [], []


def check(name, cond):
    results.append(("PASS" if cond else "FAIL", name))


def needs(pg):
    loc = pg.locator("section[aria-labelledby=needs-you]")
    return loc.inner_text() if loc.count() else ""


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    pg.goto(BASE + "/", wait_until="networkidle")
    check("fixture label visible", "Test fixtures" in pg.locator("header").first.inner_text())
    check("since-last-look shows rating downgrade", "downgrade" in needs(pg))
    pg.get_by_role("radio", name="24 h").click()
    check("24h window adds the QUANTA order", "QUANTA" in needs(pg))
    pg.get_by_role("radio", name="7 days").click()
    check("7-day window includes HELIX acquisition", "HELIX" in needs(pg))

    # Snooze and restore
    n0 = pg.locator("section[aria-labelledby=needs-you] article").count()
    pg.locator("section[aria-labelledby=needs-you] article").first.get_by_role("button", name="Snooze").click()
    check("snooze removes from Needs you", pg.locator("section[aria-labelledby=needs-you] article").count() == n0 - 1)
    pg.get_by_role("button", name="Show", exact=True).click()
    pg.get_by_role("button", name="Restore", exact=True).click()
    check("restore brings it back", pg.locator("section[aria-labelledby=needs-you] article").count() == n0)

    # Category rules: results -> Alert, credit rating -> Hide (floor keeps it)
    pg.goto(BASE + "/alerts?tab=rules", wait_until="networkidle")
    pg.locator("li").filter(has_text="Results").filter(has_text="in 7 days").first.get_by_role("radio", name="Alert").click()
    pg.locator("li").filter(has_text="Credit rating").first.get_by_role("radio", name="Hide").click()
    for _ in range(5):
        pg.get_by_role("button", name="Decrease Volume against 20-day average").click()
    check("lower volume threshold flags QUANTA", "QUANTA" in pg.get_by_text("these thresholds flag").inner_text())
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.get_by_role("radio", name="24 h").click()
    t = needs(pg)
    check("results rule promotes Kestrel results", "Q2 FY27 results" in t and "Placed here by your rule" in t)
    check("floor overrides Hide for downgrade", "downgrade" in t and "Shown despite your category setting" in t)

    # Inbox filters
    pg.goto(BASE + "/alerts", wait_until="networkidle")
    pg.get_by_role("radio", name="Unexplained moves").click()
    arts = pg.locator("section[aria-label=Alerts] article")
    check("unexplained filter shows only MERIDIAN", arts.count() == 1 and "MERIDIAN" in arts.first.inner_text())
    pg.get_by_role("button", name="Clear filters").click()
    pg.select_option("#f-sym", "SARANG")
    check("company filter", all("SARANG" in arts.nth(i).inner_text() for i in range(arts.count())) and arts.count() >= 2)
    pg.get_by_role("button", name="Clear filters").click()

    # Investigate marks read and navigates; badge decrements
    badge = lambda: int(pg.locator("nav[aria-label=Main] >> text=/^\\d+$/").first.inner_text())
    before = badge()
    pg.locator("section[aria-label=Alerts] article").filter(has_text="MERIDIAN").get_by_role("link", name="Investigate").click()
    pg.wait_for_url("**/moves/MERIDIAN")
    check("investigate opens the move page", "No filing explains this move" in pg.content())
    check("investigating marks the alert read", badge() == before - 1)

    # Event page: inputs expand; results checks visible
    pg.goto(BASE + "/events/f95a6bbe09207fd4", wait_until="networkidle")
    pg.get_by_role("button", name="Inputs").first.click()
    check("materiality inputs expand", "r-financials" in pg.locator("section[aria-labelledby=mat]").inner_text())
    check("identity checks shown", "PBT - tax = PAT (current)" in pg.content())
    check("duplicates explained", "same filing on NSE and BSE" in pg.content() and "same attachment posted again" in pg.content())
    check("no exchange link on fixtures", pg.locator("a[href*='bseindia.com'], a[href*='nseindia.com']").count() == 0)

    # Lotus: unavailable attachment stated, nothing inferred
    pg.goto(BASE + "/events/e12c0b6713acb781", wait_until="networkidle")
    check("unavailable attachment stated", "Attachment unavailable" in pg.content() and "Nothing was inferred" in pg.content())

    # Mark all as seen -> quiet state
    pg.goto(BASE + "/alerts?tab=rules", wait_until="networkidle")
    pg.get_by_role("button", name="Reset rules to defaults").click()
    pg.goto(BASE + "/", wait_until="networkidle")
    pg.get_by_role("button", name="Mark all as seen").click()
    check("quiet state after mark all seen", pg.get_by_text("Nothing needs you").is_visible())

    # Feed unavailable state
    pg2 = ctx.new_page()
    pg2.route("**/api/v1/feed", lambda r: r.fulfill(status=404, content_type="application/json", body='{"error":{"code":"NO_FEED","message":"No feed has been generated yet. Run the engine."}}'))
    pg2.goto(BASE + "/alerts", wait_until="networkidle")
    check("no-feed state is explained", pg2.get_by_text("No feed yet").is_visible())
    b.close()

for r in results:
    print(*r)
print("errors:", [e for e in errors if "404" not in e] or "none")
