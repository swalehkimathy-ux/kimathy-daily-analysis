# 🟢 K96 PICKS — Smart Pick Engine (v2.8.6 / smart-engine v1.0)

**K96 PICKS** ni desktop programu ya uchambuzi wa kubeti: Forebet forecasts × Betway/betPawa real odds → Smart Engine → verified picks and slips.

- 🏦 **Bookmaker verification**: tip lazima i-EXIST kwenye Betway TZ au betPawa TZ — kublinga kwenye site = HAIONYESHWI kabisa
- 🧠 **Probability halisi**: `0.5 × model (Poisson fit)` + `0.5 × bookie devig` — kamwe HAKUKUJIWA confidence
- 🎫 **Slip builder**: DP huchagua subset yenye joint-prob ya juu ndani ya target ya total odds 1.50–2.50
- 📊 **Ukweli juu yake**: Phase 6 → backtest + calibration live kwenye Analytics tab

---

## 🚀 HATUA ZA KWANZA (PC mpya, ~10 min)

0. **Ondoa K96 ya zamani**: Settings → Apps → "K96 PICKS" → Uninstall (kama uliwahi kusakinisha installer ya zamani), na futa folda za zamani.
1. **Tumia source iliyosasishwa** kwenye branch hii, au jenga installer mpya kwa `K96_BUILD.bat` (installer haijatengenezwa kwenye mabadiliko haya).
2. Kwa source zip, tengeneza `forebet_backend/.env.local` kwa kunakili `.env.example`, kisha jaza URL na keys kwenye PC yako tu. Kwa Electron installer, weka faili hiyo ndani ya `resources/backend/`. Usiiweke GitHub, zip au chat.
3. **Supabase SQL Editor** (mara moja tu, kama bado): endesha kwa mpangilio `schema.sql` → `schema_v2.sql` → `schema_v3_security.sql` → `schema_v4_reliability.sql`.
4. **Sakinisha**: double-click `forebet_backend\INSTALL_K96.bat` (pip deps + Playwright Chromium).
5. **Jaribu**: `forebet_backend\TEST_CONNECTION.bat` → lazima **7/7 PASS ✓**.
6. **Anzisha**: icon **"K96 PICKS"** ya Desktop (au double-click **`K96_START.bat`**) → browser inafunguka yenyewe (http://127.0.0.1:8777).
   Dirisha jeusi la console linalofunguka ndilo server — **liache wazi** (ukilifunga, app inazimika).

## 🔁 MATUMIZI YA KILA SIKU (vitufe 2)

| Hatua | Kitufe | Kinachofanyika |
|---|---|---|
| 1 | **⬇ 1) Run Scraper (leo+jana)** | Inachota mechi zote za Forebet (bila H2H — dakika chache) ya siku uliyochagua **+ jana (matokeo)** → Supabase **kila sport papo hapo**, kisha inasettle picks/slips za jana automatic. Browser ikifunguka, iache ipite Cloudflare. |
| 2 | **🔍 2) Run Engine (picks/slips)** | Inasoma data za hatua 1 (bila kuscrape tena) → H2H kwa wateule ≤40 tu (~3 dk) → engine v1.0 → uhakiki wa bookie → **Picks + Slips**. |
| 3 | **🏁 Results** tab | Matokeo ya siku iliyochaguliwa (default: jana) — win/loss/push + hit rate. |

> UI hutambua tarehe mpya ya EAT kila dakika, lakini kubadilika kwa tarehe **hakuanzi scrape/engine yenyewe**. Scraper na Engine zinaanzishwa kwa mikono kupitia vitufe vya desktop; hakuna scheduler inayohitajika.
> Scraper ikipata mechi **0**, au Supabase verification ikishindwa, GUI inaonyesha kosa kwenye Activity Log — **usibonyeze Run Engine** hadi scrape ithibitishwe.
> CLI: `python worker.py scrape --date 2026-10-31` · `python worker.py run --date 2026-10-31`

## 🖥️ Workflow ya manual (hakuna automation)

1. Mara ya kwanza tu, tengeneza `forebet_backend/.env.local` kutoka `.env.example` na ujaze credentials zako locally.
2. Kila siku, chagua tarehe kwenye UI → bonyeza **Run Scraper** na subiri Supabase verification ifanikiwe.
3. Kisha bonyeza **Run Engine** kwa tarehe hiyo; Engine hutumia data iliyohifadhiwa na kuunda picks/slips kutoka odds halisi zilizothibitishwa.
4. CLI mbadala: `python worker.py scrape --date YYYY-MM-DD` kisha `python worker.py run --date YYYY-MM-DD`.

Hakuna GitHub schedule au custom Android APK iliyojumuishwa. `.env.local` haipo kwenye ZIP kwa usalama; tengeneza locally kutoka `.env.example`. GitHub Android app haihitajiki kwa workflow hii.

## 🎫 Slips (jicho kuu)

| Label | Maana |
|---|---|
| **SAFEST** | joint WIN% ya juu zaidi (kawaida legs haba) |
| **BALANCED** | joint vs. odds urarini |
| **HIGHER_ODDS** | odds ya juu zaidi kufikia lengo |

ℹ **Kila leg inapunguza joint probability:** 10 legs @90% → joint ≈ **35%** tu. Kwa hiyo **SAFEST inapenda legs chache** — ndilo design salama.

## ⚙️ Settings ya slip (GUI → Settings → Slip builder)
odds ya leg (1.01–3.50), slip target (1.50–2.50), MAX legs (12), FORCE N (au acha auto), min leg prob (0.75), friendly block.

## 🛡️ Usalama (CRITICAL)
- `.env.local` HAIZIKI GitHub/zip/exe kamwe — tengeneza locally kutoka `.env.example`; `.gitignore` inailinda.
- Baada ya `schema_v4_reliability.sql`, anon haina ruhusa ya kusoma picks/slips; GUI server hufungwa kwa `127.0.0.1` na worker hutumia service_role upande wa PC pekee.
- Keys zikivuja au zimewahi kuingia Git: **Supabase → Settings → API → Rotate** → update `.env.local`.
- `test_supabase.py` hukagua service-role access, anon deny, tables muhimu na round-trip ya test.

## 📚 Files muhimu
```
forebet_backend/
  worker.py          worker/settle/daemon (Supabase client)
  gui_server.py      GUI backend
  index.html         GUI (English, 6 tabs ikijumuisha 🎫 Slips)
  test_supabase.py   7-point connection probe
  backtest.py        walk-forward honesty
  calibration.py     isotonic refit (≥300 settled)
  schema*.sql        Supabase migrations (RUN mwisho: SQL Editor)
forebet_picks_app/
  scraper.py · engine.py (v0.3) · slip.py · bookie.py · betway.py · matching.py · validation.py · oddsx.py
  _tests/            7 test suites (44+ asserts — zote offline)
```

## ⚠️ KNOWN LIMITS (kuwa honest)
- FOREBET + Betway TZ + betPawa TZ NDIO data tu — hakuna injuries/lineups/market-movement
- Calibration inahitaji **≥300 settled picks** (time inabol — engine inajifunza polepole)
- Betting ina hatari ya kupoteza pesa — weka bankroll limits na bet responsibly
- Backtest (historically) ni model-only bila devig (snapshot accumulation inaendelea)

## 📞 Version
`v2.8.6 · manual workflow + balanced multi-sport engine · 2026-11-01 · By Kimathy96`
