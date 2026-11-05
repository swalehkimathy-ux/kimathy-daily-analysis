"""diagnose.py — kipimo cha mtandao: ni chanzo gani kinafikika kutoka PC YAKO?

Endesha hii mara moja baada ya usakinishaji. Inakuambia kwa uaminifu:
  * Forebet inafikika? (feed ya getrs.php + kurasa za kikapu/tenisi)
  * Betway TZ / betPawa TZ zinafikika? matukio mangapi ya leo?
  * Tovuti za utabiri (tipsters) zinafikika? HTML ghafi huhifadhiwa kwa ukaguzi.

 python -m kimathy.diagnose
"""
from __future__ import annotations

import sys

from . import clock, forebet, tipsters
from .bookies.provider import Provider
from .config import load
from .net import Fetcher, save_capture


def main() -> int:
    cfg = load()
    day = clock.today_tz().isoformat()
    print("=" * 74)
    print("  KIMATHY — KIPIMO CHA VYANZO (diagnostic)")
    print(f"  Saa ya Tanzania: {clock.fmt_tz(clock.now_tz(), True)} · tarehe {day}")
    print("=" * 74)
    fetcher = Fetcher.from_config(cfg, log=lambda *a: None)

    print("\n[1] FOREBET (chanzo muhimu)")
    url_fb = forebet.FEED_URL.format(day=day)
    r = fetcher.try_fetch(url_fb, source="forebet-football")
    print(f"    getrs.php            : HTTP {r.status} · method={r.method} · "
          f"{'OK' if r.ok else 'IMESHINDWA: ' + r.error}")
    for sport, page in forebet.SPORT_PAGES.items():
        rs = fetcher.try_fetch(page, source=f"forebet-{sport}")
        print(f"    {sport:<20s}: HTTP {rs.status} · {'OK' if rs.ok else 'IMESHINDWA: ' + rs.error}")

    print("\n[2] BOOKMAKERS (bei halisi za masoko)")
    prov = Provider(cfg, log=lambda m: print(f"    {m}"))
    prov.build_index()
    for name in prov.names:
        if name in prov.index:
            print(f"    {name:<12s}: ✓ matukio {len(prov.index[name])} ya leo")
        else:
            print(f"    {name:<12s}: ✗ {prov.down.get(name, 'hakuna matukio')}")
    print(f"    jumla ya snapshots za masoko: {prov.stats['snapshots']}")

    print("\n[3] TOVUTI ZA UTABIRI (maoni tu — HTML ghafi itahifadhiwa)")
    for name, meta in cfg.section("sources.tipsters").items():
        if not meta.get("enabled"):
            print(f"    {name:<18s}: imezimwa kwenye config.json")
            continue
        rt = fetcher.try_fetch(meta.get("url", ""), source=name)
        if rt.ok:
            p = save_capture(cfg, f"diag_{name}", rt.text, log=lambda *a: None)
            print(f"    {name:<18s}: HTTP {rt.status} · OK · HTML imehifadhiwa → {p}")
        else:
            print(f"    {name:<18s}: ✗ {rt.error}")

    print("\n[4] MUHTASARI")
    ok_fb = r.ok
    ok_bk = bool(prov.available())
    print(f"    Forebet inafikika      : {'NDIYO' if ok_fb else 'HAPANA'}")
    print(f"    Bookmaker anafikika    : {', '.join(prov.available()) or 'HAKUNA'}")
    if not ok_fb:
        print("\n    USULUHISHO wa Forebet:")
        print("      1) Hakikisha mtandao unaendesha (jaribu ukurasa wa forebet.com kwenye browser)")
        print("      2) ZIMA VPN — Cloudflare huzuia IP za VPN mara nyingi")
        print("      3) Sakinisha browser ya Playwright:  python -m playwright install chromium")
        print("      4) Jaribu tena baada ya dakika chache")
    if not ok_bk:
        print("\n    USULUHISHO wa bookmaker:")
        print("      1) Thibitisha unatumia tovuti za TZ (betway.co.tz / betpawa.co.tz)")
        print("      2) ZIMA VPN")
        print("      3) Kama bado inashindwa, tuma log hii — njia za API zinaweza kubadilika")
    print("\n    Bila Forebet au bookmaker, injini itatoa NO QUALIFIED ACCUMULATOR.")
    print("    Hii ni tabia sahihi: hatubuni data.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
