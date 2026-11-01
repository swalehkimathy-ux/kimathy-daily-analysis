#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FOREBET DATA SCRAPER v5.0 - data GHAFI kutoka forebet.com (HAKUNA engine/predictions/slips).
Output: Excel sheet kwa kila sport + forebet_data_<day>.json + @DATA JSON line kwa UI.
"""
import os
import sys
import argparse
import datetime as _dt
import json
import re
import time
import unicodedata
from pathlib import Path

TZ_SHIFT_HOURS = 1
ENRICH_MAX_FOOTBALL = 25
ENRICH_MAX_OTHER = 8
HEADED_BROWSER_WAIT_S = 90
OUT_DIR = Path(__file__).resolve().parent
CACHE_DIR = OUT_DIR / "cache"

SPORTS = {
    "football":  {"url": "https://www.forebet.com/en/football-tips-and-predictions-for-today",
                  "sheet": "Football",  "avg": "Avg Goals (Total)",   "enrich": ENRICH_MAX_FOOTBALL, "dom": False},
    "basketball": {"url": "https://www.forebet.com/en/basketball/predictions-today",
                   "sheet": "Basketball", "avg": "Avg Points (Total)", "enrich": ENRICH_MAX_OTHER, "dom": True},
    "tennis":    {"url": "https://www.forebet.com/en/tennis/predictions-today",
                   "sheet": "Tennis",     "avg": "Avg Games (Total)",   "enrich": ENRICH_MAX_OTHER, "dom": True},
}
SPORT_ORDER = ["football", "basketball", "tennis"]   # v7: FOREBET pekee, sports 3 (cricket OUT)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower().replace("&", "and")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def getrs_url(day: str) -> str:
    return ("https://www.forebet.com/scripts/getrs.php?ln=en&tp=1x2"
            f"&in={day}&ord=0&tz=0&tzs=&tze=&output=1")

def match_url(sport: str, home: str, away: str, mid: str, league_name: str = "") -> str:
    if sport == "football":
        return f"https://www.forebet.com/en/football/matches/{slug(home)}-{slug(away)}-{mid}"
    lg = slug(league_name)
    if lg:
        return f"https://www.forebet.com/en/{sport}/matches/{lg}/{slug(home)}-{slug(away)}/{mid}"
    return f"https://www.forebet.com/en/{sport}/predictions-today"


# ------------------------------- FETCH LAYER --------------------------------

class CloudflareBlocked(Exception):
    pass


ERRS: dict = {}          # Phase 1: hesabu ya silent-parse-fails (si sirri-hadhi ya log)

class FetchError(RuntimeError):
    """Kila njia za kupata data zimeshindwa — kwa kuwa habari halisi, AIERR."""
    pass
def _err(key: str) -> None:
    ERRS[key] = ERRS.get(key, 0) + 1

def _looks_blocked(text: str) -> bool:
    head = (text or "")[:400].lower()
    return "just a moment" in head or "<title>attention required" in head

def fetch_curl(url: str, timeout: int = 45) -> str:
    from curl_cffi import requests as creq
    r = creq.get(url, impersonate="chrome", timeout=timeout)
    if r.status_code == 403:
        raise CloudflareBlocked(f"HTTP 403 (Cloudflare) for {url}")
    r.raise_for_status()
    if _looks_blocked(r.text):
        raise CloudflareBlocked("Cloudflare interstitial page returned")
    return r.text

def fetch_browser(url: str, timeout_s: int = 90) -> str:
    from playwright.sync_api import sync_playwright
    deadline = time.time() + timeout_s
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            while time.time() < deadline:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    time.sleep(4)
                    body = page.inner_text("body")
                    if body and "just a moment" not in body.lower():
                        return page.content()      # RAW html (parse_match_page inahitaji tags)
                    page.reload(wait_until="domcontentloaded", timeout=30000)
                    time.sleep(6)
                except Exception:
                    _err("browser_retry")
                    time.sleep(5)
        finally:
            browser.close()
        raise CloudflareBlocked("Playwright could not pass Cloudflare")

def fetch_text(url: str, log=print, allow_browser: bool = True, label: str = "") -> str:
    try:
        txt = fetch_curl(url)
        if label:
            log(f"  -> OK {label} (curl_cffi)")
        return txt
    except Exception as e:  # noqa: BLE001
        log(f"  -> blocked/failed {url}: {e}")
        if not allow_browser:
            raise
        log("  -> opening real browser to pass Cloudflare (subiri)...")
        try:
            return fetch_browser(url, HEADED_BROWSER_WAIT_S)
        except Exception as e2:  # noqa: BLE001
            log(f"  -> browser fallback haiwezi: {e2}")
            log("     ❚ HB: CONFIG-MUST: 'playwright install chromium'  → INSTALL_K96.bat")
            raise

def fetch_day_feed(day: str, log=print):
    cache_file = CACHE_DIR / f"getrs_{day}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        log(f"  -> cached feed ({len(data[0])} rows)")
        return data[0], data[1]
    log("Fetching football feed (getrs.php)...")
    txt = fetch_text(getrs_url(day), log)
    txt = re.sub(r"<[^>]+>", "", txt).strip()
    if not txt:
        log("  ✗✗ IMESHINDIKANA KUPATA DATA KUTOKA FOREBET ✗✗")
        log("     CHanzo zote 3 zimeshindwa: requests → curl_cffi → Playwright-browser halisi.")
        log("     Yanaonekana kama Cloudflare / Mtandao wako NDIO block.")
        log("     REMEDY:")
        log("       1) Hakikisha kompyuta ina 4G/WiFI iliyowekeza")
        log("       2) Run: INSTALL_K96.bat   (inaweka python-deps + Playwright chromium)")
        log("       3) Kama VPN ipo — UIERTE (CF hupiga VPN-IPs vibuko)")
        log("       4) Retry Run Engine — scraper ina-stealth mpema itajar mechi ya leo-tomorrow")
        raise FetchError("forebet fetch ALL-FAILED (see log juu)")
    data = json.loads(txt)
    rows, leagues = data[0], data[1]
    if rows:
        CACHE_DIR.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps([rows, leagues], ensure_ascii=False), encoding="utf-8")
    log(f"  -> {len(rows)} matches, {len(leagues)} leagues.")
    return rows, leagues


# ------------------------------ TRANSFORM (football feed) -------------------
def status_of(r):
    st = r.get("comment") or "Scheduled"
    if r.get("extra_time_score"):
        st = f"AET (ET {r['extra_time_score']})"
    if r.get("penalty_score"):
        st = f"Pen. ({r['penalty_score']})"
    return st

def status_of(r):
    st = r.get("comment") or "Scheduled"
    if r.get("extra_time_score"):
        st = f"AET (ET {r['extra_time_score']})"
    if r.get("penalty_score"):
        st = f"Pen. ({r['penalty_score']})"
    return st

def league_name(leagues: dict, lid) -> str:
    try:
        e = leagues.get(str(lid)) or leagues.get(lid)
        if isinstance(e, list):
            return f"{e[0]} {e[1]}".strip()
    except Exception:  # noqa: BLE001
        pass
    return f"league {lid}"

def num(v):
    try:
        return float(v) if v is not None and v != "" else None
    except Exception:  # noqa: BLE001
        return None

def iv(v):
    n = num(v)
    return int(n) if n is not None else None

def parse_bah(bah: str):
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?", bah or "")
    if not m:
        return None
    d = _dt.datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6] or 0))
    return d + _dt.timedelta(hours=TZ_SHIFT_HOURS)

def empty_rec(**kw):
    base = dict(id="", league="", rnd="", dt=None, home="", away="", sc=None, ht=None,
                st="Scheduled", p=[None, None, None], pick=None, ps=[None, None], avg=None,
                od=None, kelly=None, hf=[], af=[], hp="", ap="", tr="", stad="", w=None,
                preview=None, pick_day="0", h2h="", avg_h=None, avg_a=None, url="",
                score_txt="")
    base.update(kw)
    return base

def build_records_feed(rows, leagues, day: str):
    recs = []
    for r in rows:
        bah = r.get("DATE_BAH") or r.get("DATE") or ""
        if not bah:
                continue
        dt = parse_bah(bah)
        if not dt or dt.strftime("%Y-%m-%d") != day:
            continue
        sc = None
        if r.get("Host_SC") is not None and r.get("Guest_SC") is not None:
            sc = [int(r["Host_SC"]), int(r["Guest_SC"])]
        ht = None
        if r.get("Host_SC_HT") is not None and r.get("Guest_SC_HT") is not None:
            ht = [int(r["Host_SC_HT"]), int(r["Guest_SC_HT"])]
        odds = None
        o1, ox, o2 = num(r.get("best_odd_1")), num(r.get("best_odd_X")), num(r.get("best_odd_2"))
        if o1 and ox and o2:
            odds = [o1, ox, o2]
        weather = None
        if r.get("weather_low") not in (None, ""):
            weather = [iv(r.get("weather_low")), iv(r.get("weather_code"))]
        recs.append(empty_rec(
            id=str(r.get("id")), league=league_name(leagues, r.get("league_id")),
            rnd=str(r.get("Round") or ""), dt=dt,
            home=r.get("HOST_NAME") or "", away=r.get("GUEST_NAME") or "",
            sc=sc, ht=ht, st=status_of(r),
            p=[iv(r.get("Pred_1")), iv(r.get("Pred_X")), iv(r.get("Pred_2"))],
            ps=[iv(r.get("host_sc_pr")), iv(r.get("guest_sc_pr"))],
            avg=num(r.get("goalsavg")), od=odds, kelly=num(r.get("kelly")),
            hf=r.get("host_form") or [], af=r.get("guest_form") or [],
            hp=r.get("host_pos") or "", ap=r.get("guest_pos") or "",
            tr=(r.get("trend") or {}).get("en") or "",
            stad=r.get("match_stadium") or r.get("host_stadium") or "",
            w=weather, preview=r.get("match_preview"),
            pick_day=str(r.get("pick_day") or "0"),
            url=match_url("football", r.get("HOST_NAME") or "", r.get("GUEST_NAME") or "",
                          str(r.get("id"))),
        ))
    recs.sort(key=lambda x: (x["dt"], x["league"], x["id"]))
    return recs


# --------------- TRANSFORM (basketball/cricket/tennis pages) ----------------
def _txt(el):
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()

def _txt(el):
    if el is None:
        return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()

def parse_dom_date(s: str):
    s = s or ""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})", s)
    if m:
        d = _dt.datetime(int(m[3]), int(m[2]), int(m[1]), int(m[4]), int(m[5]))
        return d + _dt.timedelta(hours=TZ_SHIFT_HOURS)
    m = re.search(r"(\d{1,2})/(\d{1,2})\s*-\s*\d{1,2}/\d{1,2}/(\d{4})", s)  # multi-day (Tests)
    if m:
        d = _dt.datetime(int(m[3]), int(m[2]), int(m[1]))
        return d + _dt.timedelta(hours=TZ_SHIFT_HOURS)
    return None

def parse_sport_dom(html: str, sport: str) -> list:
    """Extract every match row (.rcnt) of `sport` from a predictions page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for row in soup.select(".rcnt"):
        a = row.select_one(f'a[href*="/en/{sport}/matches/"]')
        if not a:
            continue
        href = a.get("href", "")
        m = re.search(r"(\d+)(?:[?#].*)?$", href)
        if not m:
            continue
        mid = m.group(1)

        league = ""
        sib, hops = row.find_previous_sibling(), 0
        while sib is not None and hops < 80:
            if "heading" in (sib.get("class") or []):
                league = _txt(sib)
                break
            sib, hops = sib.find_previous_sibling(), hops + 1
        if not league:
            sib = row.find_previous("div", class_="heading")
            if sib:
                league = _txt(sib)
        if not league:
            league = _txt(row.select_one(".shortTag")) or sport

        home = _txt(row.select_one(".homeTeam"))
        away = _txt(row.select_one(".awayTeam"))
        dt = parse_dom_date(_txt(row.select_one(".date_bah")))

        pv = []
        for sp in row.select(".fprc span"):
            try:
                pv.append(int(_txt(sp)))
            except ValueError:
                _err("pv_invalid")
        p1 = pX = p2 = None
        if len(pv) >= 3:
            p1, pX, p2 = pv[0], pv[1], pv[2]
        elif len(pv) >= 2:
            p1, p2 = pv[0], pv[1]

        pick = _txt(row.select_one(".forepr"))
        if pick not in ("1", "X", "2"):
            pick = "2" if (p2 or 0) > (p1 or 0) else ("X" if (pX or 0) > (p1 or 0) else "1")

        ps = [None, None]
        ex = row.select_one(".ex_sc")
        if ex is not None:
            html_ex = str(ex)
            html_ex = re.sub(r"<br\s*/?>", "|", html_ex, flags=re.I)
            plain = re.sub(r"<[^>]+>", "", html_ex)
            parts = [int(x.strip()) for x in plain.split("|") if x.strip().isdigit()]
            if len(parts) >= 2:
                ps = [parts[0], parts[1]]
            else:
                dm = re.search(r"(\d+)\s*[-\u2013]\s*(\d+)", plain)
                if dm:
                    ps = [int(dm[1]), int(dm[2])]

        avg = num(_txt(row.select_one(".avg_sc")))

        od = []
        for sp in row.select(".haodd span")[:3]:
            t = _txt(sp)
            od.append(t if t and t != "-" else "")

        st = _txt(row.select_one(".lmin_td")) or "Scheduled"
        score = _txt(row.select_one(".lscr_td"))
        url = href if href.startswith("http") else "https://www.forebet.com" + href

        out.append(empty_rec(
            id=mid, league=league, dt=dt, home=home, away=away,
            st=st, score_txt=score, p=[p1, pX, p2], pick=pick, ps=ps,
            avg=avg, od=od or None, url=url,
        ))
    return out

def rel_page_for(day: str):
    today = _dt.date.today()
    if day == today.isoformat():
        return "predictions-today"
    if day == (today + _dt.timedelta(days=1)).isoformat():
        return "predictions-tomorrow"
    if day == (today - _dt.timedelta(days=1)).isoformat():
        return "predictions-yesterday"
    return None


# ------------------------------ ENRICHMENT ----------------------------------
def _plain(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    except Exception:  # noqa: BLE001
        return re.sub(r"<[^>]+>", " ", html)

def _norm_team(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", s.lower())

def _same_team(a: str, b: str) -> bool:
    na, nb = _norm_team(a), _norm_team(b)
    if not na or not nb:
        return False
    return na == nb or (min(len(na), len(nb)) >= 4 and (na in nb or nb in na))

def parse_match_page(html: str, home: str, away: str) -> dict:
    """Read the real blocks of a forebet match page:
    - 'Head to head' module  -> div.st_row meetings (date/home/score/away)
    - league standings table  -> GF/GP = real season average scored per team
    """
    from bs4 import BeautifulSoup
    out = {}
    soup = BeautifulSoup(html, "html.parser")

    # --- Head to head module ---
    # NOTE: the site's markup here is invalid (a stray </a> closes rows early),
    # so read it from the RAW html slice of the module, not the repaired DOM tree.
    hat = None
    for mm in re.finditer(r'<div class="mptlt"[^>]*>(.*?)</div>', html, re.I | re.S):
        ttxt = re.sub(r"<[^>]+>", "", mm.group(1)).strip().lower()
        if "head to head" in ttxt:
            hat = mm
            break
    if hat is not None:
        mnext = html.find('<div class="mptlt"', hat.end())
        frag = html[hat.start(): mnext if mnext > 0 else len(html)]
        meetings = []
        pat = re.compile(
            r'class="st_date"[^>]*>\s*<div>([\d/]+)</div>\s*<div>(\d{4})</div>'
            r'.*?class="st_hteam[^"]*"\s*>\s*<a[^>]*>(.*?)</a>'
            r'.*?class="st_res[^"]*">(.*?)</span>'
            r'.*?class="st_ateam[^"]*"\s*>\s*<a[^>]*>(.*?)</a>', re.S)
        for d, y, ht, sc, at in pat.findall(frag):
            sc_t = re.sub(r"<[^>]+>", "", sc)
            m2 = re.match(r"\s*(\d+)\s*-\s*(\d+)", sc_t)
            if m2:
                meetings.append((f"{d} {y}", _plain(re.sub(r"<[^>]+>", "", ht)),
                                 int(m2.group(1)), int(m2.group(2)),
                                 _plain(re.sub(r"<[^>]+>", "", at))))
        if not meetings:
            # PAT2 fallback: tafuta kila kipande ndani ya st_row block peke yake
            pat_d = re.compile(r'class="st_date"[^>]*>\s*<div>\s*([\d/]+)\s*</div>\s*<div>\s*(\d{4})\s*</div>')
            pat_ht = re.compile(r'class="st_hteam[^"]*"\s*>\s*<a[^>]*>(.*?)</a>', re.S)
            pat_at = re.compile(r'class="st_ateam[^"]*"\s*>\s*<a[^>]*>(.*?)</a>', re.S)
            pat_sc = re.compile(r'class="st_res[^"]*">(.*?)</span>', re.S)
            for block in re.split(r'<div class="st_row[^"]*"', frag)[1:]:
                md, mh = pat_d.search(block), pat_ht.search(block)
                ms, ma = pat_sc.search(block), pat_at.search(block)
                if not (md and mh and ms and ma):
                    continue
                sc_t = re.sub(r"<[^>]+>", "", ms.group(1))
                m2 = re.match(r"\s*(\d+)\s*-\s*(\d+)", sc_t)
                if m2:
                    meetings.append((f"{md.group(1)} {md.group(2)}",
                                     _plain(re.sub(r"<[^>]+>", "", mh.group(1))),
                                     int(m2.group(1)), int(m2.group(2)),
                                     _plain(re.sub(r"<[^>]+>", "", ma.group(1)))))
        if not meetings:
            out["h2h"] = "0 previous meetings."
        else:
            W = D = L = 0
            last_bits = []
            for date, ht, hg, ag, at in meetings:  # page is ordered most-recent first
                if _same_team(ht, home):
                    x, y = hg, ag
                elif _same_team(at, home):
                    x, y = ag, hg
                else:
                    continue
                if x > y:
                    W += 1
                elif x == y:
                    D += 1
                else:
                    L += 1
                if len(last_bits) < 3:
                    last_bits.append(f"{date}: {ht} {hg} - {ag} {at}".replace("  ", " "))
            tot = W + D + L
            if tot:
                out["h2h"] = f"{tot} meetings: {home} {W}W - {D}D - {L}L vs {away}."
                if last_bits:
                    out["h2h"] += f" Last: {'; '.join(last_bits)}"

    # --- Per-team season averages from the 'Standings ...' table (GF / GP) ---
    for tr in soup.select("table.standings tr"):
        a = tr.select_one(".standing-second-td a")
        if a is None:
            continue
        cells = [_txt(td) for td in tr.find_all("td")]
        if len(cells) < 9:
            continue
        try:
            gp, gf = int(cells[3]), int(cells[7])
        except (ValueError, IndexError):
            continue
        if gp <= 0:
            continue
        scored = round(gf / gp, 2)
        name = _txt(a)
        if _same_team(name, home) and out.get("avg_h") is None:
            out["avg_h"] = scored
        elif _same_team(name, away) and out.get("avg_a") is None:
            out["avg_a"] = scored
    return out

_HAS_PLAYWRIGHT = None

def _has_playwright():
    global _HAS_PLAYWRIGHT
    if _HAS_PLAYWRIGHT is None:
        try:
            import playwright.sync_api  # noqa: F401
            _HAS_PLAYWRIGHT = True
        except Exception:  # noqa: BLE001
            _HAS_PLAYWRIGHT = False
    return _HAS_PLAYWRIGHT


def enrich(records, sport: str, log=print):
    # v6 requirement: H2H lazima ijazwe kwa KILA mechi yenye detail page (hakuna cap).
    targets = [r for r in records if r.get("url")]
    log(f"  [{sport}] H2H detail scrape: {len(targets)} mechi (detail page kila moja)...")
    if not targets:
        log(f"  [{sport}] hakuna mechi za ku-enrich.")
        return 0
    done = 0
    for r in targets:
        fetched, last_err, used_browser = None, None, False
        for attempt in range(2):                 # mara mbili (CF/transient blips)
            try:
                fetched = fetch_curl(r["url"], timeout=30)
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(1.5 + attempt)
        if fetched is None and _has_playwright():
            try:                                 # browser halisi = fallback (tu kama playwright ipo)
                fetched = fetch_browser(r["url"], timeout_s=45)
                used_browser = True
            except Exception as e:  # noqa: BLE001
                last_err = e
        if fetched is None:
            if sport == "football" and not r["h2h"]:
                r["h2h"] = "\u2014"
            log(f"  x {r['home']} vs {r['away']}: {last_err}")
            continue
        try:
            info = parse_match_page(fetched, r["home"], r["away"])
            r["h2h"] = info.get("h2h") or ("\u2014" if sport == "football" else r["h2h"])
            r["avg_h"] = info.get("avg_h")
            r["avg_a"] = info.get("avg_a")
            done += 1
            mark = "\u2713" if info.get("h2h") and not str(r["h2h"]).startswith("0 previous") else "\u2205"
            log(f"  + {r['home']} vs {r['away']} ({done}/{len(targets)})"
                f" h2h:{mark}" + (" [browser]" if used_browser else ""))
            time.sleep(1.2)
        except Exception as e:  # noqa: BLE001
            if sport == "football" and not r["h2h"]:
                r["h2h"] = "\u2014"
            log(f"  x {r['home']} vs {r['away']}: {e}")
    return done


# ------------------------------- COLLECT ------------------------------------
def collect_sport(sport: str, day: str, do_enrich: bool, log=print) -> list:
    if not SPORTS[sport]["dom"]:
        rows, leagues = fetch_day_feed(day, log)
        recs = build_records_feed(rows, leagues, day)
        log(f"  [{sport}] {len(recs)} mechi za siku {day} (EAT).")
    else:
        rel = rel_page_for(day)
        if rel is None:
            log(f"  [{sport}] tovuti ina leo/kesho/jana tu kwa sport hii ({day} haipatikani).")
            return []
        base = f"https://www.forebet.com/en/{sport}/{rel}"
        log(f"  [{sport}] kusoma {base} ...")
        html1 = fetch_text(base, log, label="upcoming")
        html2 = None
        try:
            html2 = fetch_text(base + "/finished", log, allow_browser=False, label="finished")
        except Exception:
            log(f"  [{sport}] (hakuna/imefeli tab ya finished — no problem)")
        recs_all = parse_sport_dom(html1, sport)
        merged = {r["id"]: r for r in recs_all}
        order = [r["id"] for r in recs_all]
        n2 = 0
        if html2:
            for r in parse_sport_dom(html2, sport):
                if r["id"] not in merged:
                    merged[r["id"]] = r
                    order.append(r["id"])
                    n2 += 1
                elif (not merged[r["id"]]["score_txt"]) and r["score_txt"]:
                    merged[r["id"]] = r
        recs = [merged[i] for i in order]
        log(f"  [{sport}] {len(recs)} mechi kwenye kurasa (+{n2} finished).")
        recs = [r for r in recs if r["dt"] and r["dt"].strftime("%Y-%m-%d") == day]
        log(f"  [{sport}] {len(recs)} mechi za siku {day} (EAT).")
        recs.sort(key=lambda x: (x["dt"], x["league"], x["id"]))
    if do_enrich and recs:
        log(f"  [{sport}] enrichment ya mechi kubwa...")
        n = enrich(recs, sport, log)
        log(f"  [{sport}] enrichment: {n} mechi.")
    return recs


# ------------------------------- EXCEL --------------------------------------
def dc_calc(p):
    p1, px, p2 = p
    c = {"1X": (p1 or 0) + (px or 0), "12": (p1 or 0) + (p2 or 0), "X2": (px or 0) + (p2 or 0)}
    best = max(c, key=c.get)
    return best, c[best], c



SPORT_NAMES = {"football": "Football", "basketball": "Basketball", "cricket": "Cricket", "tennis": "Tennis"}

SCRAPER = "scraper v5.0.1"


def collect(sport: str, day: str, do_enrich: bool, log=print) -> list:
    """Raw data tu kutoka forebet: HAKUNA predictions/slips kabisa."""
    if sport == "football":
        rows, leagues = fetch_day_feed(day, log)
        recs = build_records_feed(rows, leagues, day)
        log(f"  [{sport}] {len(recs)} mechi za siku {day} (EAT).")
    else:
        rel = rel_page_for(day)
        if rel is None:
            log(f"  [{sport}] tovuti ina leo/kesho/jana tu kwa sport hii ({day} haipatikani).")
            return []
        url = SPORTS[sport]["url"].replace("predictions-today", rel)
        log(f"  [{sport}] kusoma {url} ...")
        html = fetch_text(url, log, label=None)
        recs = parse_sport_dom(html, sport)
        recs = [r for r in recs if r["dt"] is None or r["dt"].strftime("%Y-%m-%d") == day]
        log(f"  [{sport}] {len(recs)} mechi za siku {day} (EAT).")
    if do_enrich and recs and sport == "football":
        log(f"  [{sport}] kuongeza H2H + standings kwa mechi kuu (polepole kwa Cloudflare) ...")
        try:
            n = enrich(recs, sport, log)
            log(f"  [{sport}] enrich: {n} mechi zipatikana data za ziada.")
        except Exception as e:  # noqa: BLE001
            log(f"  [{sport}] enrich imekataa: {e}")
    return recs


def dc_of(p):
    p1, px, p2 = (list(p) + [None, None, None])[:3]
    if p1 is None or px is None or p2 is None:
        return "-"
    return f"1X {round(p1 + px)}% / 12 {round(p1 + p2)}% / X2 {round(px + p2)}%"


FOOTBALL_HEADERS = [
    "#", "League", "Round", "Kick-off (EAT)", "Home Team", "Away Team",
    "Status", "FT Score", "Prob 1 %", "Prob X %", "Prob 2 %",
    "Double Chance (1X/12/X2) (forebet)", "Predicted Score (forebet)",
    "Odds 1 (site)", "Odds X (site)", "Odds 2 (site)", "Kelly (forebet)",
    "Form Home (latest->)", "Form Away (latest->)", "Pos Home", "Pos Away",
    "Avg Goals (Total)", "Avg Scored Home", "Avg Scored Away",
    "H2H (last meetings)", "Forebet Trend (EN)", "Stadium", "Weather", "Match URL",
]
FOOTBALL_WIDTHS = [4, 30, 6, 11, 24, 24, 9, 10, 8, 8, 8, 26, 12, 8, 8, 8, 8,
                   16, 16, 8, 8, 9, 9, 9, 44, 52, 26, 12, 60]
WRAP_HEADERS = {"Forebet Trend (EN)", "H2H (last meetings)", "Match URL",
                "Double Chance (1X/12/X2) (forebet)", "League", "Home Team", "Away Team", "Stadium"}


def football_row(r, i):
    p1, px, p2 = (list(r["p"]) + [None, None, None])[:3]
    score = f"{r['sc'][0]} - {r['sc'][1]}" if r["sc"] is not None else (r["score_txt"] or "-")
    ps = f"{r['ps'][0]} - {r['ps'][1]}" if None not in r["ps"] else ""
    od = r["od"] or []
    od = [(float(str(o).replace(",", ".")) if o else None) for o in (list(od) + [None, None, None])[:3]]
    weather = "" if not r["w"] else f"{r['w'][0]}°C, icon {r['w'][1]}"
    return [
        i, r["league"], r["rnd"], r["dt"].strftime("%H:%M") if r["dt"] else "",
        r["home"], r["away"], r["st"], score, p1, px, p2,
        dc_of(r["p"]), ps,
        od[0], od[1], od[2], r["kelly"],
        "".join(x.upper() for x in r["hf"]), "".join(x.upper() for x in r["af"]),
        r["hp"], r["ap"], r["avg"], r["avg_h"], r["avg_a"],
        r["h2h"] or "", r["tr"], r["stad"], weather, r["url"],
    ]


# ---------- sport-sensible columns (win probs + betting-market tips; data-driven tu) ----------
def _fav(p1, p2, name1, name2):
    """Moneyline / match-winner tip kutoka kwa forebet probs (hakuna engine)."""
    if p1 is None and p2 is None:
        return ""
    return name1 if (p1 or 0) >= (p2 or 0) else name2


def _ou_lean(ps_pair, avg):
    """Over/Under lean: predicted total (forebet score) dhidi ya avg ya siku."""
    if None in ps_pair or avg is None:
        return "-"
    tot = ps_pair[0] + ps_pair[1]
    return ("OVER" if tot > avg else "UNDER") + f" ({tot} vs avg {avg})"


def _margin(ps_pair):
    if None in ps_pair:
        return None
    return ps_pair[0] - ps_pair[1]


DOM_COLUMNS = {
    "tennis": {
        "headers": ["#", "League / Tournament", "Date (EAT)", "Player 1 (P1)", "Player 2 (P2)",
                    "Status", "Score (sets)", "Win Prob P1 %", "Win Prob P2 %",
                    "Moneyline Tip (win prob tip)", "Predicted Sets (forebet)",
                    "Straight Sets 2-0 possible?",
                    "Odds P1 (site)", "Odds P2 (site)", "Avg Games (Total)", "Match URL"],
        "widths":  [4, 30, 16, 24, 24, 11, 11, 8, 8, 22, 12, 12, 9, 9, 10, 60],
    },
    "basketball": {
        "headers": ["#", "League", "Date (EAT)", "Home Team", "Away Team", "Status", "Score",
                    "Win Prob Home %", "Win Prob Away %", "Moneyline Tip (win prob tip)",
                    "Predicted Score (forebet)", "Expected Total Points", "Avg Points (Total)",
                    "Over/Under Total Lean", "Handicap Estimate (pts)",
                    "Odds Home (site)", "Odds Away (site)", "Match URL"],
        "widths":  [4, 30, 16, 24, 24, 11, 11, 8, 8, 24, 12, 12, 11, 18, 12, 9, 9, 60],
    },
    "cricket": {
        "headers": ["#", "League", "Date (EAT)", "Home Team", "Away Team", "Status", "Score",
                    "Win Prob Home %", "Draw Prob %", "Win Prob Away %", "Match Winner Tip",
                    "Predicted Score (forebet)", "Expected Total Runs", "Avg Runs (Total)",
                    "Over/Under Total Lean", "Winning Margin (runs)",
                    "Odds Home (site)", "Odds Away (site)", "Match URL"],
        "widths":  [4, 30, 16, 24, 24, 11, 12, 8, 8, 8, 24, 12, 12, 11, 18, 12, 9, 9, 60],
    },
}


def dom_headers(sport: str):
    return DOM_COLUMNS[sport]["headers"]


def dom_widths(sport):
    return DOM_COLUMNS[sport]["widths"]


def dom_row(r, i, sport):
    p1, px, p2 = (list(r["p"]) + [None, None, None])[:3]
    od = r["od"] or []
    od = [str(o) if o else "" for o in (list(od) + ["", ""])[:2]]
    score = r["score_txt"] or (f"{r['sc'][0]} - {r['sc'][1]}" if r["sc"] is not None else "-")
    ps = r["ps"]
    ps_txt = f"{ps[0]} - {ps[1]}" if None not in ps else ""
    dt = r["dt"].strftime("%Y-%m-%d %H:%M") if r["dt"] else ""
    base6 = [i, r["league"], dt, r["home"], r["away"], r["st"], score]
    if sport == "tennis":
        return (base6 + [p1, p2,
                         _fav(p1, p2, r["home"], r["away"]),
                         ps_txt,
                         ("YES" if (None not in ps and ps[1] == 0 and (p1 or 0) >= (p2 or 0)) or
                                    (None not in ps and ps[0] == 0 and (p2 or 0) > (p1 or 0)) else "-"),
                         od[0], od[1], r["avg"], r["url"]])
    if sport == "basketball":
        tot = None if None in ps else ps[0] + ps[1]
        marg = _margin(ps)
        return (base6 + [p1, p2,
                         _fav(p1, p2, r["home"], r["away"]),
                         ps_txt, tot, r["avg"], _ou_lean(ps, r["avg"]),
                         (f"{_fav(p1, p2, r['home'], r['away'])} by {abs(marg)}" if marg else "-"),
                         od[0], od[1], r["url"]])
    # cricket
    tot = None if None in ps else ps[0] + ps[1]
    marg = _margin(ps)
    return (base6 + [p1, px, p2,
                     _fav(p1, p2, r["home"], r["away"]),
                     ps_txt, tot, r["avg"], _ou_lean(ps, r["avg"]),
                     (f"{_fav(p1, p2, r['home'], r['away'])} by {abs(marg)}" if marg else "-"),
                     od[0], od[1], r["url"]])


def build_excel(sport_recs, day, out_path: Path, log=print) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    wb.remove(wb.active)
    hdr_fill = PatternFill("solid", fgColor="1F4E78")
    thin = Side(style="thin", color="B0B0B0")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    band = PatternFill("solid", fgColor="EAF2FB")
    counts = []
    for sport, recs in sport_recs:
        ws = wb.create_sheet(SPORT_NAMES.get(sport, sport.title()))
        is_fb = sport == "football"
        headers = FOOTBALL_HEADERS if is_fb else dom_headers(sport)
        widths = FOOTBALL_WIDTHS if is_fb else dom_widths(sport)
        ws.append(headers)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=c)
            cell.fill = hdr_fill
            cell.font = Font(color="FFFFFF", bold=True, size=10)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        wrap_cols = {c for c in range(1, len(headers) + 1) if headers[c - 1] in WRAP_HEADERS}
        for i, r in enumerate(recs, 1):
            ws.append(football_row(r, i) if is_fb else dom_row(r, i, sport))
            er = ws.max_row
            fill = band if i % 2 == 0 else None
            for c in range(1, len(headers) + 1):
                cell = ws.cell(row=er, column=c)
                cell.border = border
                cell.alignment = Alignment(vertical="center", wrap_text=(c in wrap_cols))
                if fill:
                    cell.fill = fill
                if c == len(headers):
                    cell.hyperlink = r["url"]
                    cell.font = Font(color="0563C1", underline="single")
        for i2, wd in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i2)].width = wd
        ws.freeze_panes = "G2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(ws.max_row, 2)}"
        counts.append((SPORT_NAMES.get(sport, sport.title()), len(recs)))
    wb.save(out_path)
    log("Saved: " + str(out_path) + "  [" + ", ".join(f"{n}:{c}" for n, c in counts) + "]")
    return out_path


def to_jsonable(r):
    d = dict(r)
    d["dt"] = r["dt"].strftime("%Y-%m-%d %H:%M") if r.get("dt") else None
    return d


def run(day: str, sports, do_enrich: bool = True, log=print):
    sport_recs = []
    for sport in sports:
        log(f"=== [{sport.upper()}] ===")
        try:
            recs = collect(sport, day, do_enrich, log)
        except CloudflareBlocked as e:
            log(f"!!! [{sport}] Cloudflare: {e}")
            recs = []
        except Exception as e:  # noqa: BLE001
            log(f"!!! [{sport}] hitilafu: {e}")
            recs = []
        sport_recs.append((sport, recs))
    out = None
    if any(recs for _, recs in sport_recs):
        out = build_excel(sport_recs, day, OUT_DIR / f"Forebet_Data_{day}.xlsx", log)
        (OUT_DIR / f"forebet_data_{day}.json").write_text(
            json.dumps({"day": day, "scraper": SCRAPER,
                        "sports": {s: [to_jsonable(r) for r in recs] for s, recs in sport_recs}},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        log("!!! HAKUNA data iliyopatikana siku hiyo - angalia hapo juu (internet au Cloudflare block).")
    payload = {"day": day, "scraper": SCRAPER, "excel": str(out) if out else None,
               "sports": [{"sport": s, "count": len(recs),
                           "sample": [{"home": r["home"], "away": r["away"], "league": r["league"],
                                       "time": r["dt"].strftime("%H:%M") if r.get("dt") else "",
                                       "status": r["st"],
                                       "score": (f"{r['sc'][0]} - {r['sc'][1]}" if r["sc"] else (r["score_txt"] or None)),
                                       "probs": r["p"], "odds": r["od"], "url": r["url"]}
                                      for r in recs[:8]]}
                          for s, recs in sport_recs]}
    log("@DATA " + json.dumps(payload, ensure_ascii=False))
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Forebet DATA SCRAPER (no engine, no predictions) v5.0")
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default = today)")
    ap.add_argument("--sports", default=None, help="(deprecated — FOOTBALL pekee sasa; ubao huu haujatumika)")
    ap.add_argument("--no-enrich", action="store_true")
    a = ap.parse_args()
    day = a.date or _dt.date.today().isoformat()
    sports = [s2.strip() for s2 in a.sports.split(",") if s2.strip() in SPORTS] if a.sports else SPORT_ORDER
    try:
        run(day, sports, do_enrich=not a.no_enrich)
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print("@DATA " + json.dumps({"day": day, "scraper": "scraper v5.0", "excel": None,
                                     "sports": [], "error": str(e)[:150]}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
