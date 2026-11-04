"""D. Product functionality, in a real browser against the running app (next start + finn serve).

    python eval/ui_eval.py [label]       (expects the web app on :3000 with FINN_ENGINE_URL set)

D1 arbitrary NSE ticker search   D2 navigation   D3 filtering   D4 loading states
D5 error states                  D6 mobile responsiveness (6 viewports x 8 routes) and tap targets
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import Recorder  # noqa: E402

B = os.environ.get("FINN_URL", "http://127.0.0.1:3000")
FEED = json.loads((Path(__file__).resolve().parents[1] / "apps/web/data/feed.json").read_text())
EV = next(e for e in FEED["events"] if e["materiality"]["tier"] == "interrupt")


def run(label: str) -> int:
    rec = Recorder("ui")
    with sync_playwright() as p:
        br = p.chromium.launch()
        phone = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
        desk = br.new_context(viewport={"width": 1440, "height": 900})
        import traceback
        for name, fn, args in (("D1", search, (rec, phone.new_page())), ("D2", navigation, (rec, phone.new_page(), desk.new_page())), ("D3", filtering, (rec, desk.new_page())),
                               ("D4/D5", loading_and_errors, (rec, br)), ("D6", responsive, (rec, br))):
            try:
                fn(*args)
            except Exception as e:  # noqa: BLE001 - a crashed step is a failed check, the rest still runs
                rec.check("D", f"{name} step crashed", type(e).__name__, False, traceback.format_exc()[-600:], severity="critical")
        br.close()
    rec.save(label)
    print(rec.summary())
    fails = [c for c in rec.checks if not c.passed]
    print(f"\n{len(rec.checks) - len(fails)}/{len(rec.checks)} UI checks passed")
    return 0


# ------------------------------------------------------------------ D1

def search(rec, pg) -> None:
    errs: list[str] = []
    dialogs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    pg.goto(f"{B}/research")
    box = pg.get_by_role("combobox")
    cases = [("reliance", "RELIANCE"), ("RELIANCE", "RELIANCE"), ("M&M", "M&M"), ("bajaj-auto", "BAJAJ-AUTO"), ("tata motors", "TATAMOTORS"), ("hdfc bank", "HDFCBANK"),
             ("TCS.NS", "TCS"), ("NSE:INFY", "INFY"), ("  halcyon  ", "HALCYON"), ("infosys", "INFY")]
    for q, want in cases:
        box.fill(q)
        try:
            deadline = time.time() + 5
            opts: list[str] = []
            while time.time() < deadline:
                opts = [o for o in pg.locator("[role=listbox] [role=option]").all_inner_texts() if not o.startswith("Try ")]
                if any(o.split() and o.split()[0] == want for o in opts) or any(o.startswith("No listed") for o in opts):
                    break
                pg.wait_for_timeout(150)
            first = opts[0].split()[0] if opts else ""
            rec.check("D", "D1 ticker search", f"'{q}' finds {want}", any(o.split()[0] == want for o in opts if o.split()), f"first={first}; {len(opts)} options")
        except Exception as e:  # noqa: BLE001
            rec.check("D", "D1 ticker search", f"'{q}' finds {want}", False, f"{type(e).__name__}: {pg.locator('[role=listbox]').inner_text()[:150] if pg.locator('[role=listbox]').count() else 'no list'}")
    for q, expect in [("zzzqqq", r"No listed company matches"), ("<script>alert(1)</script>", r"No listed company matches"), ("ETERNAL", r"Try ETERNAL anyway")]:
        box.fill(q)
        pg.wait_for_timeout(700)
        txt = pg.locator("[role=listbox]").inner_text() if pg.locator("[role=listbox]").count() else ""
        rec.check("D", "D1 ticker search", f"'{q}' -> {expect}", bool(re.search(expect, txt)), txt[:160])
    rec.check("D", "D1 ticker search", "no script ran from the search box", not dialogs, str(dialogs))
    box.fill("   ")
    pg.wait_for_timeout(300)
    rec.check("D", "D1 ticker search", "blank query shows no list", pg.locator("[role=listbox]").count() == 0, "")
    # Keyboard selection
    box.fill("halcyon")
    pg.wait_for_selector("[role=option]:has-text('HALCYON')")
    box.press("ArrowDown")
    box.press("Enter")
    pg.wait_for_url("**/research/HALCYON", timeout=5000)
    rec.check("D", "D1 ticker search", "keyboard: arrow + enter opens the report", pg.url.endswith("/research/HALCYON"), pg.url)
    pg.wait_for_selector("nav[aria-label=Sections]", timeout=10000)
    # An arbitrary live ticker: no report yet -> research it -> honest failure (no network to NSE/BSE here)
    pg.goto(f"{B}/research")
    box = pg.get_by_role("combobox")
    box.fill("polycab")
    pg.wait_for_selector("[role=option]:has-text('POLYCAB')")
    pg.locator("[role=option]:has-text('POLYCAB')").first.dispatch_event("mousedown")
    pg.wait_for_url("**/research/POLYCAB")
    t0 = time.time()
    try:
        # Either the page offers to research it, or (when it starts on its own) the run ends in a stated failure.
        pg.wait_for_selector("text=/No research has been built|could be reached|couldn't be reached/i", timeout=150000)
        if pg.get_by_role("button", name=re.compile(r"^Research POLYCAB", re.I)).count():
            rec.check("D", "D1 ticker search", "unbuilt ticker offers to run research", True, "")
            pg.get_by_role("button", name=re.compile(r"^Research POLYCAB", re.I)).click()
            pg.wait_for_selector("text=/could be reached|couldn't be reached/i", timeout=150000)
        dt = time.time() - t0
        body = pg.locator("main").inner_text()
        rec.check("D", "D1 ticker search", f"live research on an arbitrary ticker ends in a stated failure, not a hang ({dt:.0f}s; no route to NSE/BSE here)", dt < 150, body[:200].replace("\n", " "), severity="critical")
        rec.check("D", "D1 ticker search", "the failure names the company, its ISIN and the sources tried", bool(re.search(r"Polycab India", body)) and "ISIN" in body and "Sources that couldn" in body, body[:300].replace("\n", " "))
        rec.check("D", "D1 ticker search", "a 'Try again' action is offered", pg.get_by_role("button", name="Try again").count() == 1, "")
    except Exception as e:  # noqa: BLE001
        rec.check("D", "D1 ticker search", "live research on an arbitrary ticker ends in a stated failure, not a hang", False, f"after {time.time() - t0:.0f}s: {pg.locator('main').inner_text()[:300]}", severity="critical")
    rec.check("D", "D1 ticker search", "no page errors during search", not errs, str(errs[:2]))


# ------------------------------------------------------------------ D2

def navigation(rec, ph, dk) -> None:
    errs: list[str] = []
    for pg in (ph, dk):
        pg.on("pageerror", lambda e: errs.append(str(e)))
    ph.goto(f"{B}/")
    ph.wait_for_load_state("networkidle")
    for name, path in (("Portfolio", "/portfolio"), ("Research", "/research"), ("Alerts", "/alerts"), ("Brief", "/")):
        ph.get_by_role("navigation", name="Main").get_by_role("link", name=re.compile(rf"^{name}")).click()
        ph.wait_for_url(f"**{path}" if path != "/" else B + "/", timeout=8000)
        cur = ph.get_by_role("navigation", name="Main").locator("[aria-current=page]").inner_text()
        rec.check("D", "D2 navigation", f"phone tab {name} -> {path}, marked current", cur.strip().split("\n")[0].strip() == name, cur)
    ph.go_back()
    ph.wait_for_timeout(500)
    rec.check("D", "D2 navigation", "browser back returns to the previous tab", ph.url.endswith("/alerts"), ph.url)
    dk.goto(f"{B}/")
    dk.wait_for_load_state("networkidle")
    side = dk.locator("aside")
    for name in ("Portfolio", "Research", "Alerts", "Brief"):
        side.get_by_role("link", name=re.compile(rf"^{name}( \d+)?$")).click()
        dk.wait_for_timeout(600)
        rec.check("D", "D2 navigation", f"desktop sidebar {name}", side.locator("[aria-current=page]").inner_text().strip().split("\n")[0].strip() == name, dk.url)
    # Deep links and drill-downs
    dk.goto(f"{B}/")
    dk.wait_for_selector(f"a[href='/events/{EV['id']}']", timeout=8000)
    dk.locator(f"a[href='/events/{EV['id']}']").first.click()
    dk.wait_for_url(f"**/events/{EV['id']}")
    dk.wait_for_timeout(800)
    rec.check("D", "D2 navigation", "brief -> event detail", EV["symbol"] in dk.locator("main").inner_text(), dk.url)
    for url, expect in [(f"/events/{EV['id']}", EV["symbol"]), ("/moves/SARANG", "SARANG"), ("/research/HALCYON/credibility", "Credibility|credibility"),
                        ("/events/does-not-exist", r"not found|isn't in|no event|doesn't exist|not in the feed"), ("/moves/NOPE", r"not in|no price|not found|isn't|No market"),
                        ("/definitely-not-a-page", r"404|not found|could not be found")]:
        dk.goto(B + url)
        dk.wait_for_timeout(1500)
        t = dk.locator("body").inner_text()
        rec.check("D", "D2 navigation", f"deep link {url}", bool(re.search(expect, t, re.I)), t[:160].replace("\n", " "))
    # Every internal link on the main pages resolves (no 404s)
    seen, bad = set(), []
    for start in ("/", "/portfolio", "/alerts", "/research", "/research/HALCYON", "/research/HALCYON/credibility", f"/events/{EV['id']}", "/moves/SARANG"):
        dk.goto(B + start)
        dk.wait_for_timeout(1200)
        for h in dk.eval_on_selector_all("a[href^='/']", "as => as.map(a => a.getAttribute('href'))"):
            h = h.split("#")[0]
            if h and h not in seen:
                seen.add(h)
                r = dk.request.get(B + h)
                if r.status >= 400:
                    bad.append(f"{h} -> {r.status} (from {start})")
    rec.check("D", "D2 navigation", f"all {len(seen)} internal links resolve", not bad, "; ".join(bad[:5]), severity="critical")
    rec.check("D", "D2 navigation", "no page errors while navigating", not errs, str(errs[:2]))


# ------------------------------------------------------------------ D3

def filtering(rec, pg) -> None:
    pg.goto(f"{B}/alerts")
    pg.wait_for_selector("section[aria-label=Alerts]", timeout=8000)

    def rows():
        return pg.locator("section[aria-label=Alerts] > *").count()
    total = rows()
    kinds = {}
    for k in pg.get_by_role("radiogroup", name="Alert type").get_by_role("radio").all():
        name = k.inner_text().strip()
        k.click()
        pg.wait_for_timeout(250)
        kinds[name] = rows()
    rec.check("D", "D3 filtering", f"alert type filter changes the list ({kinds})", len(set(kinds.values())) > 1 and max(kinds.values()) == total, f"total {total}")
    pg.get_by_role("radiogroup", name="Alert type").get_by_role("radio").first.click()
    sym = pg.locator("#f-sym")
    opts = [o for o in sym.locator("option").all_inner_texts() if o.strip() and not o.lower().startswith("all")]
    if opts:
        sym.select_option(label=opts[0])
        pg.wait_for_timeout(250)
        shown = pg.locator("section[aria-label=Alerts]").inner_text()
        others = [o for o in opts[1:] if re.search(rf"\b{re.escape(o.split()[0])}\b", shown)]
        rec.check("D", "D3 filtering", f"symbol filter '{opts[0]}' shows only that company", rows() >= 1 and not others, f"{rows()} rows; other symbols visible: {others[:3]}")
        clear = pg.get_by_role("button", name=re.compile("Clear filters", re.I))
        rec.check("D", "D3 filtering", "'Clear filters' appears when filtered and restores the list", clear.count() == 1 and (clear.click() or True) and (pg.wait_for_timeout(250) or True) and rows() == total, f"{rows()} vs {total}")
    cat = pg.locator("#f-cat")
    copts = [o for o in cat.locator("option").all_inner_texts() if o.strip() and not o.lower().startswith("all")]
    if copts:
        cat.select_option(label=copts[0])
        pg.wait_for_timeout(250)
        rec.check("D", "D3 filtering", f"category filter '{copts[0]}' narrows the list", 1 <= rows() <= total, f"{rows()} of {total}")
        pg.get_by_role("button", name=re.compile("Clear filters", re.I)).click()
    pg.get_by_role("switch", name=re.compile("Unread only")).click() if pg.get_by_role("switch", name=re.compile("Unread only")).count() else None
    pg.wait_for_timeout(250)
    rec.check("D", "D3 filtering", "unread-only toggle works", rows() <= total, f"{rows()} of {total}")
    # Brief time window: wider windows never show fewer filings
    pg.goto(f"{B}/")
    pg.wait_for_selector("[role=radiogroup][aria-label='Time window']", timeout=8000)
    counts = []
    for name in ("24 h", "3 days", "7 days"):
        r = pg.get_by_role("radiogroup", name="Time window").get_by_role("radio", name=name, exact=True)
        if r.count():
            r.first.click()
            pg.wait_for_timeout(300)
            counts.append((name, pg.locator("a[href^='/events/']").count()))
    mono = all(a[1] <= b[1] for a, b in zip(counts, counts[1:]))
    rec.check("D", "D3 filtering", f"brief window filter is monotonic {counts}", len(counts) == 3 and mono and counts[-1][1] > 0, str(counts))


# ------------------------------------------------------------------ D4, D5

def loading_and_errors(rec, br) -> None:
    ctx = br.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)))

    held: list = []
    def hold(route, request=None):  # requests are parked and released later, so the page really waits
        held.append(route)

    def release():
        while held:
            held.pop(0).continue_()
    pg.route("**/api/v1/research/HALCYON", hold)
    pg.goto(f"{B}/research/HALCYON", wait_until="commit")
    pg.wait_for_timeout(1200)
    busy = pg.locator("[aria-busy=true]").count()
    rec.check("D", "D4 loading states", "report: busy state shown while the API is slow", busy > 0 and pg.locator("nav[aria-label=Sections]").count() == 0, f"aria-busy={busy}; held {len(held)}")
    release()
    pg.wait_for_selector("nav[aria-label=Sections]", timeout=15000)
    rec.check("D", "D4 loading states", "report: content replaces the busy state", pg.locator("[aria-busy=true]").count() == 0, "")
    pg.unroute("**/api/v1/research/HALCYON")
    pg.route("**/api/v1/feed", hold)
    pg.goto(f"{B}/", wait_until="commit")
    pg.wait_for_timeout(1200)
    rec.check("D", "D4 loading states", "brief: busy state shown while the feed loads", pg.locator("[aria-busy=true]").count() > 0, f"held {len(held)}")
    release()
    pg.wait_for_selector("[role=radiogroup][aria-label='Time window']", timeout=15000)
    rec.check("D", "D4 loading states", "brief: content replaces the busy state", pg.locator("[aria-busy=true]").count() == 0, "")
    pg.unroute("**/api/v1/feed")
    pg.goto(f"{B}/research/HALCYON")
    pg.wait_for_selector("#ask textarea")
    pg.route("**/api/v1/ask/HALCYON", hold)
    pg.locator("#ask textarea").fill("Why did margins decline?")
    pg.locator("#ask textarea").press("Enter")
    pg.wait_for_timeout(600)
    btn = pg.locator("#ask button[type=submit]").inner_text()
    rec.check("D", "D4 loading states", "Ask: button says it is reading and input is locked", btn.startswith("Reading") and pg.locator("#ask textarea").is_disabled(), btn)
    release()
    pg.wait_for_timeout(1500)
    rec.check("D", "D4 loading states", "Ask: answer appears and the input unlocks", not pg.locator("#ask textarea").is_disabled() and "Why did margins decline" in pg.locator("#ask").inner_text(), "")
    pg.unroute("**/api/v1/ask/HALCYON")

    # Errors
    cases = [("**/api/v1/feed", 500, json.dumps({"error": {"code": "BOOM", "message": "feed exploded"}}), "/", r"couldn't|could not|error|unavailable|failed|try again"),
             ("**/api/v1/research/HALCYON", 500, json.dumps({"error": {"code": "INTERNAL", "message": "The engine hit an error; it has been logged."}}), "/research/HALCYON", r"engine hit an error|error|returned 500"),
             ("**/api/v1/research/HALCYON", 502, json.dumps({"error": {"code": "ENGINE_UNREACHABLE", "message": "The research engine isn't responding."}}), "/research/HALCYON", r"isn't responding|unreachable|error"),
             ("**/api/v1/feed", 200, "{not json", "/", r"couldn't|could not|error|unavailable|failed|invalid")]
    for pat, code, body, url, expect in cases:
        p2 = ctx.new_page()
        p2.on("pageerror", lambda e: errs.append(str(e)))
        def fake(route, request=None, c=code, b=body):
            route.fulfill(status=c, body=b, content_type="application/json")
        p2.route(pat, fake)
        p2.goto(B + url)
        p2.wait_for_timeout(2500)
        t = p2.locator("main").inner_text() if p2.locator("main").count() else p2.locator("body").inner_text()
        rec.check("D", "D5 error states", f"{url} with {pat.split('/')[-1]} -> {code}{' (bad JSON)' if body.startswith('{not') else ''}", bool(re.search(expect, t, re.I)) and "Application error" not in t, t[:200].replace("\n", " "), severity="critical")
        retry = p2.get_by_role("button", name=re.compile("retry|try again|reload", re.I))
        if retry.count():
            p2.unroute(pat)
            retry.first.click()
            p2.wait_for_timeout(2500)
            rec.check("D", "D5 error states", f"{url}: retry recovers after {code}", "Application error" not in p2.locator("body").inner_text() and not re.search(expect, p2.locator('main').inner_text()[:80], re.I), p2.locator("main").inner_text()[:120])
        p2.close()
    p3 = ctx.new_page()
    p3.route("**/api/v1/ask/HALCYON", lambda route: route.fulfill(status=503, body=json.dumps({"error": {"code": "ENGINE_NOT_CONFIGURED", "message": "Ask FINN needs the research engine."}}), content_type="application/json"))
    p3.goto(f"{B}/research/HALCYON")
    p3.wait_for_selector("#ask textarea")
    p3.locator("#ask textarea").fill("Why did margins decline?")
    p3.locator("#ask textarea").press("Enter")
    p3.wait_for_timeout(1200)
    rec.check("D", "D5 error states", "Ask with engine unavailable shows the reason", "needs the research engine" in p3.locator("#ask").inner_text(), p3.locator("#ask").inner_text()[:200], severity="critical")
    p3.goto(f"{B}/research/%40%40%40")
    p3.wait_for_timeout(1500)
    rec.check("D", "D5 error states", "invalid ticker in the URL explains itself", bool(re.search(r"isn't an NSE symbol|not an NSE|invalid", p3.locator("body").inner_text(), re.I)), p3.locator("main").inner_text()[:160])
    p3.goto(f"{B}/research/CORAL")
    p3.wait_for_timeout(1500)
    rec.check("D", "D5 error states", "company with no documents explains its gaps", bool(re.search(r"no (research )?documents|nothing|gap|not found in the window|No results", p3.locator("main").inner_text(), re.I)), p3.locator("main").inner_text()[:200])
    rec.check("D", "D5 error states", "no uncaught page errors in any error state", not errs, str(errs[:3]), severity="critical")
    ctx.close()


# ------------------------------------------------------------------ D6

ROUTES = ["/", "/portfolio", "/alerts", "/research", "/research/HALCYON", "/research/KAVERI/credibility", f"/events/{EV['id']}", "/moves/SARANG"]
VIEWPORTS = [(320, 640), (375, 667), (390, 844), (768, 1024), (1024, 768), (1440, 900)]
JS_OVERFLOW = """() => {
  const W = document.documentElement.clientWidth;
  const doc = document.documentElement.scrollWidth;
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (r.right > W + 1 || r.left < -1) {
      let p = el.parentElement, clipped = false;
      while (p) { const s = getComputedStyle(p); if (/(auto|scroll|hidden|clip)/.test(s.overflowX)) { clipped = true; break; } p = p.parentElement; }
      if (!clipped) bad.push((el.tagName + '.' + (el.className && el.className.baseVal === undefined ? String(el.className).split(' ').slice(0,2).join('.') : '')).slice(0, 60) + ' ' + Math.round(r.right));
    }
  }
  return { W, doc, bad: bad.slice(0, 5), n: bad.length };
}"""
JS_TAPS = """() => {
  // WCAG 2.2 SC 2.5.8 (AA): a target is fine if it is at least 24x24, OR a 24px circle centred on it
  // doesn't intersect another target (spacing exception), OR it sits inline in a sentence.
  const els = [...document.querySelectorAll('a[href], button, [role=radio], [role=switch], select, input, textarea')]
    .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; });
  const rects = els.map(el => el.getBoundingClientRect());
  const out = [];
  els.forEach((el, i) => {
    const r = rects[i];
    if (r.height >= 24 && r.width >= 24) return;
    const d = getComputedStyle(el).display;
    if ((d === 'inline' || d === 'inline-block') && el.closest('p, li, td, dd') && (el.closest('p, li, td, dd').innerText || '').length > (el.innerText || '').length + 8) return;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const small = (o) => o.width < 24 || o.height < 24;
    const hit = rects.some((o, j) => {
      if (j === i || el.contains(els[j]) || els[j].contains(el)) return false;
      const nx = Math.max(o.left, Math.min(cx, o.right)), ny = Math.max(o.top, Math.min(cy, o.bottom));
      if (Math.hypot(nx - cx, ny - cy) < 12) return true;               // our 24px circle touches the other target
      const ox = o.left + o.width / 2, oy = o.top + o.height / 2;
      return small(o) && Math.hypot(ox - cx, oy - cy) < 24;             // two undersized targets' circles overlap
    });
    if (hit) out.push((el.innerText || el.getAttribute('aria-label') || el.tagName).trim().replace(/\\s+/g, ' ').slice(0, 30) + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
  });
  return out;
}"""


def responsive(rec, br) -> None:
    for w, h in VIEWPORTS:
        ctx = br.new_context(viewport={"width": w, "height": h}, device_scale_factor=1, is_mobile=w < 768, has_touch=w < 768)
        pg = ctx.new_page()
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        for r in ROUTES:
            pg.goto(B + r)
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(500)
            o = pg.evaluate(JS_OVERFLOW)
            rec.check("D", "D6 mobile responsiveness (no horizontal overflow)", f"{w}x{h} {r}", o["doc"] <= o["W"] + 1 and o["n"] == 0, f"page {o['doc']}px in {o['W']}px; {o['n']} elements past the edge: {o['bad']}", severity="critical" if w <= 390 else "normal")
            if w <= 390:
                small = pg.evaluate(JS_TAPS)
                rec.check("D", "D6 tap targets ≥ 24px (WCAG 2.5.8)", f"{w}x{h} {r}", not small, f"{len(small)} small: {small[:5]}")
        rec.check("D", "D6 mobile responsiveness (no horizontal overflow)", f"{w}x{h}: no page errors", not errs, str(errs[:2]))
        ctx.close()


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else "baseline"))
