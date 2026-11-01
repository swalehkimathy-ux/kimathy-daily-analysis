# 🟢 K96 PICKS — Smart Pick Engine (v2.8.3 / smart-engine v1.0)

**K96 PICKS** ni desktop programu ya uchambuzi wa kubeti: Forebet (probabilities) × Betway/betPawa (soko halisi) → **smart-engine v0.3** → Slips salama (odds target yako).

- 🏦 **Bookmaker verification**: tip lazima i-EXIST kwenye Betway TZ au betPawa TZ — kublinga kwenye site = HAIONYESHWI kabisa
- 🧠 **Probability halisi**: `0.5 × model (Poisson fit)` + `0.5 × bookie devig` — kamwe HAKUKUJIWA confidence
- 🎫 **Slip builder**: DP inachagua subset yenye joint-prob ya JUU per total-odds lengo (1.85–2.50 default)
- 📊 **Ukweli juu yake**: Phase 6 → backtest + calibration live kwenye Analytics tab

---

## 🚀 HATUA ZA KWANZA (PC mpya, ~10 min)

0. **Ondoa K96 ya zamani**: Settings → Apps → "K96 PICKS" → Uninstall (kama uliwahi kusakinisha installer ya zamani), na futa folda za zamani.
1. **Unzip** `K96_PICKS_PC_v2.8.3.zip` popote (mf. `C:\K96`).
2. **`.env.local` IMO NDANI** ya `forebet_backend/` tayari (Supabase URL + keys) — hakuna cha kuweka.
3. **Supabase SQL Editor** (mara moja tu, kama bado): RUN `schema.sql` **+ `schema_v2.sql`** **+ `schema_v3_security.sql`** (inaondoa maonyo ya Security Advisor).
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

> Scraper ikipata mechi **0**, GUI inaonyesha onyo jekundu na sababu (Activity Log) — **usibonyeze Run Engine** hadi scrape ifanikiwe.
> CLI: `python worker.py scrape --date 2026-10-31` · `python worker.py run --date 2026-10-31`

> ⏰ **Daemon (auto):** `python worker.py daemon` — PC ikikuwa online 24/7: picks za 00:00, settle 01:00, odds-refresh 06:00/12:00, calibration Jumatatu 04:00.

## 🎫 Slips (jicho kuu)

| Label | Maana |
|---|---|
| **SAFEST** | joint WIN% ya juu zaidi (kawaida legs haba) |
| **BALANCED** | joint vs. odds urarini |
| **HIGHER_ODDS** | odds ya juu zaidi kufikia lengo |

ℹ **Kila leg inapunguza joint probability:** 10 legs @90% → joint ≈ **35%** tu. Kwa hiyo **SAFEST inapenda legs chache** — ndilo design salama.

## ⚙️ Settings ya slip (GUI → Settings → Slip builder)
odds ya leg (1.05–3.50), slip target (1.85–2.50), MAX legs (12), FORCE N (au acha auto), min leg prob (0.75), friendly block.

## 🛡️ Usalama (CRITICAL)
- `.env.local` HAIZIKI kwenye zip/exe kamwe — iwe pembeni ya exe/control. `.gitignore` + `.env.example` tayari.
- Supabase RLS: anon key hujiruhusu kusoma TU; service_role inakalili PC pekee.
- Keys zikivuja: **Supabase → Settings → API → Rotate** → update `.env.local`.
- `test_supabase.py` inathibitisha: anon write → 401 ✓ (RLS inafanya kazi)

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
`v2.8.3 · smart-engine v1.0 (K96 ENGINE RULES) · 2026-11-01 · By Kimathy96`
