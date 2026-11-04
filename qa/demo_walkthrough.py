"""Runs DEMO.md step by step against the full app and checks every claim the presenter will make.

    FINN_URL=http://127.0.0.1:3000 python qa/demo_walkthrough.py
"""
import json
import os
import re
import urllib.request

from playwright.sync_api import sync_playwright

B = os.environ.get("FINN_URL", "http://127.0.0.1:3000")
res, errs = [], []


def ok(step, cond, detail=""):
    res.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + step + ("" if cond else f"  | {str(detail)[:300]}"))


def ask(sym, q):
    r = urllib.request.Request(f"{B}/api/v1/ask/{sym}", data=json.dumps({"question": q}).encode(), method="POST", headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))


with sync_playwright() as p:
    br = p.chromium.launch()
    pg = br.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    # 0:00 brief
    pg.goto(B + "/")
    pg.wait_for_selector("#needs-you", timeout=15000)
    banner = pg.locator("header").first.inner_text()
    ok("0:00 every screen carries the synthetic-data notice", re.search(r"synthetic|fixture", banner, re.I), banner)
    needs = pg.locator("section[aria-labelledby=needs-you]").inner_text()
    first = needs.split("\n")[1:6]
    ok("0:00 SARANG's rating downgrade (AA- -> A+) leads 'Needs you'", "SARANG" in "\n".join(first) and re.search(r"AA-.{0,10}A\+", needs), first)
    for s in ("warning letter", "Chief Financial Officer", "capex of Rs. 1,150 crore"):
        ok(f"0:00 'Needs you' also shows: {s}", re.search(re.escape(s), needs, re.I), needs[:400])
    FEED = json.load(urllib.request.urlopen(B + "/api/v1/feed"))
    ev_id = {e["symbol"] + ":" + e["category"]: e["id"] for e in FEED["events"] if e["materiality"]["tier"] != "routine"}
    pg.locator("section[aria-labelledby=needs-you] a[href^='/events/']", has_text="Credit rating downgrade").first.click()
    pg.wait_for_url("**/events/**")
    pg.wait_for_timeout(800)
    ev = pg.locator("main").inner_text()
    ok("0:20 event page shows named components (filing type 60, market reaction +14 = 74) and 'always surface'",
       re.search(r"Filing type", ev) and re.search(r"Market reaction", ev) and re.search(r"74", ev) and re.search(r"always surface", ev), ev[:300])
    # 0:40 KESTREL cluster
    pg.goto(B + "/")
    pg.wait_for_selector("#needs-you")
    kid = ev_id["KESTREL:results"]
    ok("0:40 KESTREL's results are under 'Worth a look'", pg.locator(f"a[href='/events/{kid}']").count() > 0, "")
    pg.locator(f"a[href='/events/{kid}']").first.click()
    pg.wait_for_url("**/events/**")
    pg.wait_for_timeout(800)
    k = pg.locator("main").inner_text()
    ok("0:40 KESTREL results: one event holding outcome, PDF, press release, deck, corrigendum", all(re.search(x, k, re.I) for x in ("Outcome of Board Meeting", "Press Release", "Investor Presentation", "Corrigendum")), k[:400])
    ok("0:40 the second PDF copy is marked a duplicate and the corrigendum linked", re.search(r"duplicate", k, re.I) and re.search(r"supersede|correct|revis", k, re.I), "")
    # Alerts -> market moves
    pg.goto(B + "/alerts")
    pg.wait_for_selector("section[aria-label=Alerts]")
    pg.get_by_role("radiogroup", name="Alert type").get_by_role("radio", name=re.compile("Market", re.I)).first.click()
    pg.wait_for_timeout(400)
    al = pg.locator("section[aria-label=Alerts]").inner_text()
    ok("1:00 SARANG: volume 2.6x alert, explained by the downgrade", re.search(r"SARANG[\s\S]{0,120}volume 2\.6×[\s\S]{0,120}Explained by a filing: Credit rating downgrade", al), al[:400])
    ok("1:00 MERIDIAN +6.8% on 3.4x: no filing explains it", re.search(r"MERIDIAN[\s\S]{0,200}No filing explains", al) or re.search(r"No filing explains[\s\S]{0,200}MERIDIAN", al), al[:600])
    # 1:20 thresholds
    before = "QUANTA" in al
    pg.goto(B + "/alerts?tab=rules")
    pg.wait_for_selector("text=Price move in a day")
    dec = pg.get_by_role("button", name=re.compile(r"Decrease Price move", re.I))
    for _ in range(4):
        dec.click()
    pg.goto(B + "/alerts")
    pg.wait_for_selector("section[aria-label=Alerts]")
    al3 = pg.locator("section[aria-label=Alerts]").inner_text()
    ok("1:20 at 3% (was 5%), QUANTA +3.9% now alerts", not before and "QUANTA" in al3, f"before={before}")
    pg.evaluate("localStorage.clear()")
    # 1:50 research search
    pg.goto(B + "/research")
    box = pg.get_by_role("combobox")
    for q, want in (("tata motors", "TATAMOTORS"), ("RELIANCE.NS", "RELIANCE")):
        box.fill(q)
        pg.wait_for_timeout(1200)
        opts = [o.split()[0] for o in pg.locator("[role=listbox] [role=option]").all_inner_texts() if o.split() and not o.startswith("Try ")]
        ok(f"1:50 search '{q}' finds {want}", want in opts, opts[:4])
    pg.goto(B + "/research/KAVERI")
    pg.wait_for_selector("nav[aria-label=Sections]", timeout=15000)
    nvn = pg.locator("#nvn").inner_text()
    ok("2:10 KAVERI: demand described positively while revenue fell 2.1% YoY", re.search(r"demand positively[\s\S]{0,120}2\.1%", nvn), nvn[:300])
    ok("2:10 KAVERI: margins likewise; FY26 capex missed", re.search(r"margins positively", nvn) and re.search(r"Capex guidance of ~₹1,200 cr for FY26 was missed", nvn), "")
    pg.locator("#snapshot button.num.underline").first.click()
    pg.wait_for_timeout(600)
    sheet = pg.locator("[role=dialog]").inner_text()
    ok("2:40 tapping a reported figure shows document, page, column and the printed row", re.search(r"Page \d+ · P&L · Column", sheet) and "Row as printed" in sheet, sheet[:300])
    rp = pg.get_by_role("button", name=re.compile("Read page"))
    ok("2:40 'Read page N' opens the page text", rp.count() > 0 and (rp.first.click() or True) and (pg.wait_for_timeout(700) or True) and "SYNTHETIC" in pg.locator("[role=dialog]").last.inner_text().upper(), "")
    pg.keyboard.press("Escape")
    pg.keyboard.press("Escape")
    g = pg.locator("#guidance").inner_text()
    ok("3:00 'high single digit' revenue growth kept as words", re.search(r"high single digit", g, re.I) and re.search(r"word", g, re.I), g[:300])
    # 3:10 credibility
    pg.goto(B + "/research/KAVERI/credibility")
    pg.wait_for_timeout(1500)
    cr = pg.locator("main").inner_text()
    m = re.search(r"kept (\d+) of (\d+)", cr, re.I)
    ok("3:10 tracker: 'kept 4 of 6 explicit targets'", m and m.groups() == ("4", "6"), m and m.group(0))
    ok("3:10 the tracker states it gives no trust score, and shows none", "No trust score" in cr and not re.search(r"(trust|credibility) score\s*[:=]\s*\d", cr, re.I), "")
    pg.goto(B + "/research/VEDIKA")
    pg.wait_for_selector("#nvn")
    v = pg.locator("#nvn").inner_text()
    ok("3:40 VEDIKA: presentation 24.5–25.5% vs transcript 24–25% flagged", re.search(r"24\.5.25\.5%[\s\S]{0,80}24.25%", v), v[:300])
    # 3:50 Ask FINN
    a = ask("KAVERI", "Why did margins decline in Q2 FY27?")
    kinds = {b["kind"] for b in a["blocks"]}
    ok("3:50 'Why did margins decline in Q2 FY27?' answered with cited facts, management quotes, labelled interpretation",
       a["status"] == "answered" and {"fact", "management", "interpretation"} <= kinds and all(b["cites"] for b in a["blocks"] if b["kind"] == "fact"), (a["status"], kinds))
    a = ask("KAVERI", "Why did EBITDA margin improve by 5 percentage points?")
    t = " ".join(b["text"] for b in a["blocks"])
    ok("4:10 false premise corrected from the filings", re.search(r"assumes|but", t) and not re.search(r"\b5(\.0)? ?(pp|percentage)", t), t[:200])
    ok("4:20 'Should I buy this stock?' refused", ask("KAVERI", "Should I buy this stock?")["status"] == "out_of_scope")
    a = ask("CORAL", "Why did margins decline?")
    ok("4:30 CORAL: not enough evidence, and why", a["status"] == "insufficient" and re.search(r"No results filing could be read", " ".join(b["text"] for b in a["blocks"])), a["status"])
    # Ask FINN in the UI, on the phone
    pg.goto(B + "/research/KAVERI")
    pg.wait_for_selector("#ask textarea")
    pg.locator("#ask textarea").fill("Why did margins decline in Q2 FY27?")
    pg.locator("#ask textarea").press("Enter")
    pg.wait_for_timeout(2500)
    ok("3:50 the Ask FINN panel shows the answer and its sources on the phone", "Answered from the documents" in pg.locator("#ask").inner_text() and "Sources" in pg.locator("#ask").inner_text(), pg.locator("#ask").inner_text()[:200])
    h = json.load(urllib.request.urlopen(B + "/api/health"))
    ok("troubleshooting: /api/health shows feed.events 29 and the engine reachable", h["feed"]["events"] == 29 and h["engine"]["reachable"], h)
    ok("no page errors during the walkthrough", not errs, errs[:3])
    br.close()
print(f"{sum(res)} / {len(res)}")
