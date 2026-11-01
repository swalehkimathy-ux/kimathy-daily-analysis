# K96 PICKS (v2.8 / smart-engine v1.0) — MAELEZO KAMILI (Full Description)
*by Kimathy96 · smart-engine v0.2 · Forebet = data source PEKEE*

---

## 1. APP INAFANYA NINI (muonekano wa juu)

K96 PICKS inapata **picks zenye confidence ya juu (≥80%)** kila siku, kwa michezo 3
(mpira wa miguu ⚽, kikapu 🏀, tenisi 🎾), bila kubahati.

Mtiririko wa siku nzima:

```
  00:00 EAT ─► [SCRAPER]  chotesa Forebet → hifadhi SUPABASE  (mara moja/siku tu)
  wakati wowote ─► [ENGINE]  chambua → toa picks 3–10 za kuaminika → SUPABASE
  24/7 ─► [GUI]  mtumiaji afungue ara pose → aone picks (hai-gusi Forebet)
  01:00 EAT ─► [SETTLE]  rudia kurasa za jana → matokeo → win/loss → engine inajifunza
```

---

## 2. VIPANDE VIKUU 4 — kila kimoja na kazi yake

### A. SCRAPER (`forebet_picks_app/scraper.py`)

Chufua data kutoka **Forebet pekee**:

| Param | Maana |
|---|---|
| **Football** | feed JSON `getrs.php` — probabilities 1/X/2 (%), predicted score, avg magoli, best-odds 1/X/2, Kelly, form (W/D/L zilizopita), nafasi za ligi (positions), trend-text, weather, wakati EAT |
| **Basketball/Tennis** | kurasa za DOM (bs4) — prob P1/P2, avg points/games, odds |
| **Enrich (hiari)** | detail-page ya mechi → H2H summary + wastani wa kufunga (GF/GP) kwa kila timu |
| **CF-ukinga** | curl_cffi (Chrome impersonation) → ikigongwa: browser ya Playwright halisi — kisha `CloudflareBlocked` |

### B. SMART ENGINE (`forebet_picks_app/engine.py`) — moyo wetu

**Hatua 0 — USALAMA:** ligi/timu za watoto (U21/U19/youth/academy/reserves) na wanawake
zinaondolewa kabisa — takwimu zao ni tete.

**Hatua 1 — GATE:** mechi inaangaliwa tu Forebet ikionyesha favorite (prob ≥ 50%).
Lakini mechi ngumu (hakuna favorite) **HAIBIWI** — inachunguzwa kwa masoko mengine.

**Hatua 2 — UHAKIKI (rules 10, +/− pointi kwa confidence):**

| # | Rule | Pointi |
|---|---|---|
| 1 | H2H imara kwa favorite / inapinga | +6 / −8 |
| 2 | Form ya hivi karibuni (W=3,D=1,L=0 · tofauti ≥4) | +5 / −6 |
| 3 | Favorite hajapoteza michezo 5 | +2 |
| 4 | Ukubwa (nafasi za ligi, tofauti ≥8) | +4 / −8 |
| 5 | Home advantage (favorite ugenini −2) | +2 |
| 6 | Motisha: playoff/final +2 · **friendly −8** | ± |
| 7 | Ligi kuu (takwimu za kuaminika) | +2 |
| 8 | Odds band **1.11–1.57** = favorite halisi · ≤1.90 kawaida · >1.90 inapinga | +6 / +2 / −6 |
| 9 | PS inamuunga favorite + margin ≥2 | +2 / +2 |
| 10 | Kelly ya Forebet (value) | +3 / −2 |

**Hatua 3 — UCHAGUZI WA SOKO (kwa vipaumbele):**

```
DIRECT 1X2      ← tu Forebet ≥90% na rules zinathibitishia (conf ≥ min)
DOUBLE CHANCE   ← 1X=57+30=87 k.m. (BACKUP: salama kuliko direct!)
DRAW NO BET     ← prob ya favorite IKING'O draw: 57/(57+13)=81%
TOTAL GOALS     ← Poisson λ = Avg ya Forebet: Over/Under 1.5, 2.5, 3.5
BTTS            ← Poisson mbili (λ_home, λ_away) — timu zote zifunge au la
HANDICAP +2     ← European Handicap (v0.2: ≈ DC+6 — backoff halisi)
Basketball/Tennis → WINNER pekee (salama: hazina DC wala lines halisi)
```

**Hatua 4 — SIKU (adaptive):** lengo 3–10 picks; ikikawa chache, min 80→75→70;
ikikawa nyingi, top-10 kwa confidence.

### C. WORKER + SUPABASE (`forebet_backend/`)

- **`worker.py`** — modes:
  - `run` — itachota au **tumia cache** (day_cache → haita-gusi Forebet tena siku hiyohiyo);
    picks zinafutwa/na-andikwa upya kila mrun
  - `settle` — irudie kurasa za siku zilizopita → final scores → `win/loss/push` kwa kila
    soko (1X2, DC, DNB, Totals, BTTS, EH+2, Winner) → + matches.final
  - `daemon` — auto: **00:00 scrape/run**, **01:00 settle**, catch-up PC iwaka baadaye
- **`schema.sql`** — vidonge 4:
  - `day_cache` (siku/index ya kumbukumbu: metadata + idadi)
  - `matches` (mechi zote + final scores + raw jsonb)
  - `picks` (tips + result + why/decision + engine_version)
  - `engine_stats` (view: hit-% kwa market+sport — ndiyo "learning data")
  - **RLS (v2.8.4):** anon haina access ya picks/slips; worker hutumia service_role server-side kwenye PC tu

### D. GUI (`index.html` + `gui_server.py`)

- Hamburger ☰ → **5 tabs**: ✅ ELIGIBLE PICKS · 📈 RESULTS · 📊 ENGINE STATS · 📋 LOG · ⚙️ SETTINGS
- **ELIGIBLE PICKS**: spinner ya kijani (hakuna vitezi), pick-cards zenye
  market-chip rangi, confidence bar, FB%, odds, PS, na "Kwa nini?" (sababu za engine).
- **RESULTS**: date selector → tip vs matokeo halisi kwa siku, WIN/LOSS chips,
  hit-rate per day + per market — engine's school report.
- **ENGINE STATS**: hit-rate per soko all-time + siku za cache.
- **SETTINGS**: tarehe, min-conf%, H2H enrich — zinahazibi localStorage (hazipotei).
- **Testing (demo)**: 💾 DEMO→DB (seed halisi Supabase, K96 TEST) · 🧪 Finals bandia · 🧹 cleanup.

---

## 3. JINSI YA KULETA MATOKEO (kiurahisi)

1. Scraper inaleta prob/odds/form/trends — *hii ni hoja ya Forebet* (mathematical Poisson model yao).
2. Engine **haachili hoja yenyewe hivyo** — inaihakiki kwa rules 10 (superiority, form,
   H2H ya karibuni, home/away, motisha, ligi, odds-band, Kelly, PS-coherence).
3. Ikiwa direct imethibitishwa (@90%+), inachukuliwa. La — engine inatafuta **soko salama zaidi**
   (DC/DNB/Goals/BTTS/EH) lixende conf ≥80%.
4. Kila pick inaandika **sababu zake** kwenye DB — transparency kamili.
5. **Settle** inalinganishia na matokeo halisi → hit-rate inayojiongeza → engine inajifunza
   (calibration itakuja Phase 5).

---

## 4. MILIPUKO ILIYOPIMIKA (imbesha!)

- ✅ `settle_pick` — 9/9 masoko ya bets (win/loss/push sahihi)
- ✅ Engine E2E (Liverpool 1X @98, Man City Over 1.5 @85, women blocked, friendly flagged)
- ✅ Pipeline halisi → Supabase: seed 7 mechi/picks → settle 6W/1L → results 85.7% hit
- ✅ RLS (v2.8.4): anon haisomi wala kuandika; worker service_role pekee hufikia DB upande wa PC
- ✅ Day-cache: mara 2+ inatumia data hiyo-hiyo (Forebet haiguswi)
- ✅ GUI: spinner, tabs 5, settings persisted, results day-filter — zote GREEN

## 5. MAPUNGUFU YA KWELI (sinaoni tunajuwe njoo)

- **Sandbox hii haichui Forebet** (CF 403 — datacenter IP): scrape halisi inafanyika **PC yako** tu.
- **EH+2** ni estimation (DC+6) — baada ya backtest tutahesabu halisi.
- **BTTS** inachukulia boli za timu ni independent — takriban-u sahihi.
- **"conf"** ni score yetu, si probability calibrari — Phase 5 (backtest) itafix.
- **Basketball/Tennis results** hazipewi forebet feed — football tu inasettle vizuri kwa sasa.

---

## 6. HATUA ZINAZOFUATA (Phase map)

```
✅ Phase 1 — Smart Engine v0.2 (rules 10 + markets 7)
✅ Phase 2 — Supabase (schema + RLS + stats)
✅ Phase 3 — PC Worker (cache + settle + daemon autos)
✅ Phase 4 — GUI (tabs + spinner + demo tools) ← TUNAHISHI HAPA SASA
⏳ Phase 5 — Production PC zip + .bat setup ya moja-kwa-moja
⏳ Phase 6 — Backtesting 30-60 siku za zamani → calibration halisi
```
