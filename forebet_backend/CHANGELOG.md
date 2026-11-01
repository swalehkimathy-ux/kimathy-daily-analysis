# K96 PICKS — CHANGELOG (per Implementation-Spec phases)

## Phase 8.I — v2.8.5 (2026-11-01) ✅ SMART ENGINE COVERAGE + LOW-ODDS SLIP TARGET
- Football total-goals markets now fall back from `goalsavg` to predicted score, then team season-scoring rates; team Over/Under 0.5 and 1.5 markets are modeled too.
- Goal expectations use modest team scoring/form/home-field signals; form, standings and H2H flags are directional and subtract confidence only.
- Missing exact bookmaker lines no longer erase model candidates. Provider-priced markets are preferred when available; worker still verifies market and odds before slips.
- Removed the artificial 1.15 inferred-odds floor for model-only picks; never treat inverse model probability as a real price. Confidence display is capped at 95%.
- Adaptive threshold logging now reports the last threshold actually tried even if the day still has fewer than three picks.
- Default slip odds target changed to 1.50–1.80. Basketball projected scores above 15 are no longer rejected by football's score bound.
- Offline suites passed: engine, validation, bookie guard, picks, matching, odds, slips, settlement, worker flow.

## Phase 8.H — v2.8.4 (2026-11-01) ✅ UHAKIKI WA SUPABASE + RUN HISTORY SALAMA
- Scraper sasa huhesabu rows za Forebet na kuzihakiki Supabase kabla ya kusema imefanikiwa; status ya cache huonyesha succeeded/partial/failed/empty.
- `scraped_at` husasishwa baada ya scrape, `match_count` ya zamani haifutwi kabla ya mafanikio, na cache isiyothibitishwa haitumiki na Engine/daemon.
- Kila Engine run huhifadhiwa kwa `analysis_runs` na `run_id`; picks/slips za awali hazifutwi. Run iliyofeli haifichi run ya mwisho iliyofanikiwa; slips sifuri zinaonekana kama sifuri, si stale.
- Settlement ya slip sasa hutumia `pick_id` sahihi; rerun nyingi za siku hazijumuishwi mara nyingi kwenye stats za latest-run.
- UI/backend/daemon hutumia EAT; daemon inakagua cache iliyothibitishwa kabla ya catch-up.
- RLS ya anon imefungwa kwa data ya picks/slips; GUI server inafungwa kwa loopback; `test_supabase.py` hukagua anon deny. Distribution ZIP haijumuishi `.env.local`; `.env.local` haifuatiliwi na Git.
- SQL migration mpya: `schema_v4_reliability.sql` (endesha baada ya schema v1–v3).

## Phase 8.G — v2.8.3 (2026-11-01) ✅ RUN ENGINE HAIKWAMI BOOKIE ZIKIWA DOWN
**Tatizo:** devig ya bookie inaitwa kwa KILA mechi (~1353). Betway/betPawa zikiwa hazifikiki,
kila mechi ilijaribu upya `day_index` (timeout 25s × 2) → Run Engine ingeweza kuchukua MASAA.
- `betway.day_index` + `bookie.day_index`: kosa linakumbukwa (`_DOWN`) → bookie iliyokufa inajaribiwa MARA MOJA tu kwa siku.
- `bookie.make_provider`: breaker `FAIL_BREAK=5` (makosa 5 mfululizo → bookie inaachwa kwa run hii),
  budget `PROVIDER_BUDGET_S=480` (dk 8, kisha model-only), progress log kila mechi 100.
- `worker` uthibitisho wa picks: `VERIFY_BUDGET_S=300` (dk 5 max) + kosa la pick moja haliangushi run.
- Test mpya `_tests/test_bookie_guard.py` (down-memo, breaker, budget, verify api_down) → suites 9/9 GREEN.
- E2E (mechi 1353, bookie zote down, kila ombi 2s): Run Engine **13.7s**, maombi ya mtandao **2** (badala ya ~5400).
- Honesty: bookie zikiwa down hakuna slip ya kubuni (slip inahitaji odds halisi za bookie).

## Phase 8.F — v2.8.2 (2026-11-01) ✅ SCRAPER YA HARAKA + KUHIFADHI PAPO HAPO
- 🐛 **Scraper ilichukua saa 1.5+**: ilifungua ukurasa wa H2H wa KILA mechi (1033 × ~5s) kabla ya kuhifadhi chochote;
  GUI ilikata tamaa baada ya dk 30 (rc=-2) → Supabase tupu. Sasa:
  - **Run Scraper** = mechi zote BILA H2H (dakika chache) na **kila sport inahifadhiwa Supabase papo hapo**.
  - **Run Engine** = engine pre-pass → wateule ≤40 → H2H kwa hao tu (~3 dk) → picks + slips.
- 🐛 **Supabase inarudisha mistari 1000 tu** → engine ingeona mechi 1000 kati ya 1353. Mpya: `sb_all()` (kurasa).
- 🛡 Hakuna kikomo cha dk 30 kwenye GUI; kazi mbili haziwezi kuanza pamoja (kubonyeza tena = kuunganishwa na ile ile);
  ukirefresh GUI, inaonyesha maendeleo ya kazi inayoendelea. `taskkill /T` inazima pia worker wa server ya zamani.
- 🔐 `schema_v3_security.sql`: inaondoa maonyo ya Supabase Security Advisor (views security_invoker + search_path).
- 🧪 E2E kubwa dhidi ya Supabase halisi: 1353 mechi (1033/120/200) → scrape 0 H2H, DB 1353/1353 →
  engine H2H 37 tu → picks 10 + slip 1 → cleanup 0.

## Phase 8.E — v2.8.1 (2026-11-01) ✅ TAREHE + LOG ZA MOJA KWA MOJA + SERVER YA ZAMANI
- 🐛 **Tarehe ilikwama**: `CFG.day` ilihifadhiwa localStorage → GUI ilibaki siku ya kwanza ulipoifungua.
  Sasa HAIHIFADHIWI; inatumia **EAT (UTC+3)** (JS + Python `today_eat()`), inajisasisha saa 6 usiku,
  na Picks ina kichagua tarehe + kitufe **Leo**.
- 🐛 **Run Scraper "haifanyi kitu" / Activity Log tupu**: worker iliendeshwa bila `-u` → Python ilishikilia
  output hadi mwisho; `pollJob` ilifuta mstari wa kwanza. Sasa `-u` + `PYTHONUNBUFFERED`, log inaonekana ndani ya
  sekunde 1 kwenye skrini ya Picks (mistari 6 ya mwisho + saa), na console inaonyesha kila hatua kwa saa.
- 🐛 `fetch` ikishindwa (server imezima) → kitufe kilibaki kimya. Sasa ujumbe wazi + dot nyekundu; JS error
  yoyote → bango jekundu juu (hakuna skrini tupu kimya).
- 🛡 **Server ya zamani** iliyobaki kwenye port 8777 (ingeonyesha GUI ya zamani isiyo na /api/scrape):
  `K96_START.bat` inaizima kwanza; Electron inaangalia `/api/version` na kuizima; gui_server inakataa
  kuendelea na toleo la zamani kwa ujumbe wazi.
- 🪟 GUI inafunguka kama **dirisha la app** (Edge/Chrome `--app`) — Electron haihitajiki tena.
  `INSTALL_K96.bat` inaweka icon **"K96 PICKS"** kwenye Desktop → K96_START.bat (inafunika icon ya zamani).
- 🗂 Kila job inaandika log kwenye `forebet_backend/logs/` (tuma faili hilo kama kuna tatizo).
- 🔇 BrokenPipe noise kwenye console imezimwa; ukaguzi wa Supabase unafanyika nyuma (haichelewesha kuwaka).

## Phase 8.D — v2.8 BLACK-SCREEN FIX (2026-10-31) ✅
- 🐛 **gui_server.py**: double-click ilionyesha console nyeusi tu — browser ilifunguka ndani ya .exe pekee.
  Sasa browser inafunguka yenyewe kila mara (isipokuwa `K96_NO_BROWSER=1`), banner wazi "USIFUNGE dirisha hili",
  na ukiifungua mara ya pili (port 8777 inatumika) inafungua tu browser badala ya kuanguka.
- 🆕 **K96_START.bat**: kizinduzi cha kubofya mara moja (py/python auto) — kikianguka kinaonyesha error + `pause`.
- 🐛 **Electron**: faili za Python zilikuwa ndani ya `app.asar` (Python haiwezi kuzisoma) → server haikuwaka →
  BLACK SCREEN. Sasa `extraResources` → `resources/backend` + `resources/forebet_picks_app` (+ `.env.local`).
  main.js: skrini ya "inapakia" papo hapo, inajaribu `py -3` → `python` → `python3`, ukurasa wa error wenye
  log ya Python + suluhisho + kitufe "Jaribu tena", `did-fail-load` → error page. Majaribio 6 (mock electron) ✓.

## Phase 8.C — v2.8 FINAL CROSSCHECK (2026-10-31) ✅
- 🐛 **gui_server**: `/api/slips` + `/api/calibration` (GET & POST) zilitumia `sb` isiyokuwepo → Slips/Analytics
  zilikuwa tupu kimya kimya. Sasa zinatumia `worker.sb` ✓.
- 🐛 **worker cmd_run**: `.status_code` juu ya JSON (picks/slips/snapshots/odds-refresh) → Run Engine ingeanguka
  wakati wa kuhifadhi slips. Mpya: `sb_resp()` (status_code/json/text, hairushi) ✓.
- 🐛 **snapshots path** `/rest/v1/` mara mbili → sasa `odds_snapshots` ✓.
- 🐛 **rec_to_row**: status ilisomwa `status` badala ya `st` (scraper) → mechi zote zilihifadhiwa "Scheduled".
  Sasa status halisi + `final_home/final_away` kwa mechi zilizoisha ✓ (row_to_rec inarudisha `st`/`sc`).
- 🐛 **settle**: safu `fh/fa` hazipo → `final_home/final_away`; majina ya timu sasa URL-encoded (`&`, nafasi) ✓.
- 🐛 **cmd_scrape**: `DELETE day_cache` ya jana ilizuiwa na trigger ya history (HTTP 400) → imeondolewa (upsert inatosha).
- 🛡 **Uaminifu**: scrape ya mechi 0 → `✗✗ SCRAPE IMESHINDWA` + suluhisho, rc=2, GUI inaonyesha onyo jekundu.
- 🧰 `INSTALL_K96.bat` / `K96_BUILD.bat`: ASCII safi + CRLF; kurekebisha `if ( echo (...) )` iliyokuwa ikivunja cmd.
- 🧪 Test mpya `_tests/test_worker_flow.py`; **E2E LIVE dhidi ya Supabase**: Scraper→Engine(cache, collect=0)→
  Scraper kesho→settle (win/win/push/win, slip=win)→/api/results ✓ → cleanup rows 0.

## Phase 8.B — v2.8 (2026-10-29) ✅ 2-BUTTON FLOW: Scraper → Engine
- **"⬇ Run Scraper (leo+jana)"**: scrape Forebet kwa siku husika (cache-aware) **+ JANA
  fresh** (hataki cache: results zina-update), upsert matches → Supabase, kisha **settle
  picks/slips za jana AUTOMATIC** (moja kwa moja, hakuna action nyingine).
- **"🔍 Run Engine (picks/slips)"**: inasoma data za cache (bila rescrape — haraka sana)
  baada ya scraper → engine v1.0 → bookie verification → Slips.
- worker.py: mode mpya `scrape` (python worker.py scrape [--date 2026-10-29]) +
  `_scrape_day` helper (run+scrape wameshare), `_settle_day_from_finals` in-line.
- GUI: **☰ Hamburger menu** — desktop: kunja/fungua sidebar (inakumbukwa); simu/skrini ndogo: drawer inayoteleza + backdrop, Esc kufunga.
- GUI: Picks tab ina radio-flow 1→2; Results page auto-refresh baada ya scrape.

## Phase 8 — v2.7 (2026-10-29) ✅ ENGINE v1.0 = K96 ENGINE RULES
- **Rewrite kamili**: engine v0.2-points → v1.0-probability-rules (K96_ENGINE_RULES.md):
  · G1 hakuna +points · G2 devig (Double Chance inanormalize hadi **tu-2** — bug ya sum-2
    imerekebishwa pande zote betway & betPawa) · G3 blend 0.5·model + 0.5·market + calibration
  · G4 flags −1pt ea (model_vs_market · bookies_disagree · favourite_away · h2h_against ·
    form_against · ps_contradicts · model_fit_poor) max −3
  · F2 λ-fit: grid ya home-share ±avg (Bayern → λ 2.78/0.93, fit_err tracking)
  · F3 avg haipo → goal markets zimezimwa · F4 p-sum ±3 → block
  · **BASKETBALL (B1–B3)**: margin Normal SD=11.5 z-fit → Handicap ±5.5/±9.5 + Totals
    (Σ: "Away +9.5" kwa mechi 50/50 — sio Winner)
  · **TENNIS (T1–T5)**: games diff SD=4.5/6.0 → P1 ±3.5 + Total games · **T5 lopsided veto**
    (favourite ≥85% → Over games zimetolewa)
  · Block list nzima: friendly/exhibition/youth/women/reserve/doubles/ITF/esports/virtual/
    status≠Scheduled + suffix W/II/B **mwisho wa jina tu, SIO tennis** ("B. Player" trap)
  · G7 tie-break ≤1pt → odds → EV · **rejected top-3 kwa sababu** katika kila pick
- test_engine_v3.py: 10 makundi mapya kwa rules; zote suites (7) GREEN; E2E offline demo ✓.

## Phase 7.C — v2.6 (2026-10-28) ✅ SCRAPER IMETEGEMEA-LOUDLY
- fetch_text: requests/curl_cffi/Playwright KILA-moja — mwisho ikifeli: **FetchError (raise)**
  hakuna "cache tupu / log tupu" tena. Activity Log ineleza cause + 4 remedies aRef.
- fetch_day_feed: diagnosis safi (Mtandao / VPN / INSTALL_K96.bat).
- **INSTALL_K96.bat** — one-click: pip deps + Playwright Chromium ha-download.
- Engine: smart-engine v0.3 — ALL 7 test suites remain GREEN.

## Phase 8.F — v2.8.2 (2026-11-01) ✅ SCRAPER YA HARAKA + KUHIFADHI PAPO HAPO
- 🐛 **Scraper ilichukua saa 1.5+**: ilifungua ukurasa wa H2H wa KILA mechi (1033 × ~5s) kabla ya kuhifadhi chochote;
  GUI ilikata tamaa baada ya dk 30 (rc=-2) → Supabase tupu. Sasa:
  - **Run Scraper** = mechi zote BILA H2H (dakika chache) na **kila sport inahifadhiwa Supabase papo hapo**.
  - **Run Engine** = engine pre-pass → wateule ≤40 → H2H kwa hao tu (~3 dk) → picks + slips.
- 🐛 **Supabase inarudisha mistari 1000 tu** → engine ingeona mechi 1000 kati ya 1353. Mpya: `sb_all()` (kurasa).
- 🛡 Hakuna kikomo cha dk 30 kwenye GUI; kazi mbili haziwezi kuanza pamoja (kubonyeza tena = kuunganishwa na ile ile);
  ukirefresh GUI, inaonyesha maendeleo ya kazi inayoendelea. `taskkill /T` inazima pia worker wa server ya zamani.
- 🔐 `schema_v3_security.sql`: inaondoa maonyo ya Supabase Security Advisor (views security_invoker + search_path).
- 🧪 E2E kubwa dhidi ya Supabase halisi: 1353 mechi (1033/120/200) → scrape 0 H2H, DB 1353/1353 →
  engine H2H 37 tu → picks 10 + slip 1 → cleanup 0.

## Phase 8.E — v2.8.1 (2026-11-01) ✅ TAREHE + LOG ZA MOJA KWA MOJA + SERVER YA ZAMANI
- 🐛 **Tarehe ilikwama**: `CFG.day` ilihifadhiwa localStorage → GUI ilibaki siku ya kwanza ulipoifungua.
  Sasa HAIHIFADHIWI; inatumia **EAT (UTC+3)** (JS + Python `today_eat()`), inajisasisha saa 6 usiku,
  na Picks ina kichagua tarehe + kitufe **Leo**.
- 🐛 **Run Scraper "haifanyi kitu" / Activity Log tupu**: worker iliendeshwa bila `-u` → Python ilishikilia
  output hadi mwisho; `pollJob` ilifuta mstari wa kwanza. Sasa `-u` + `PYTHONUNBUFFERED`, log inaonekana ndani ya
  sekunde 1 kwenye skrini ya Picks (mistari 6 ya mwisho + saa), na console inaonyesha kila hatua kwa saa.
- 🐛 `fetch` ikishindwa (server imezima) → kitufe kilibaki kimya. Sasa ujumbe wazi + dot nyekundu; JS error
  yoyote → bango jekundu juu (hakuna skrini tupu kimya).
- 🛡 **Server ya zamani** iliyobaki kwenye port 8777 (ingeonyesha GUI ya zamani isiyo na /api/scrape):
  `K96_START.bat` inaizima kwanza; Electron inaangalia `/api/version` na kuizima; gui_server inakataa
  kuendelea na toleo la zamani kwa ujumbe wazi.
- 🪟 GUI inafunguka kama **dirisha la app** (Edge/Chrome `--app`) — Electron haihitajiki tena.
  `INSTALL_K96.bat` inaweka icon **"K96 PICKS"** kwenye Desktop → K96_START.bat (inafunika icon ya zamani).
- 🗂 Kila job inaandika log kwenye `forebet_backend/logs/` (tuma faili hilo kama kuna tatizo).
- 🔇 BrokenPipe noise kwenye console imezimwa; ukaguzi wa Supabase unafanyika nyuma (haichelewesha kuwaka).

## Phase 8.D — v2.8 BLACK-SCREEN FIX (2026-10-31) ✅
- 🐛 **gui_server.py**: double-click ilionyesha console nyeusi tu — browser ilifunguka ndani ya .exe pekee.
  Sasa browser inafunguka yenyewe kila mara (isipokuwa `K96_NO_BROWSER=1`), banner wazi "USIFUNGE dirisha hili",
  na ukiifungua mara ya pili (port 8777 inatumika) inafungua tu browser badala ya kuanguka.
- 🆕 **K96_START.bat**: kizinduzi cha kubofya mara moja (py/python auto) — kikianguka kinaonyesha error + `pause`.
- 🐛 **Electron**: faili za Python zilikuwa ndani ya `app.asar` (Python haiwezi kuzisoma) → server haikuwaka →
  BLACK SCREEN. Sasa `extraResources` → `resources/backend` + `resources/forebet_picks_app` (+ `.env.local`).
  main.js: skrini ya "inapakia" papo hapo, inajaribu `py -3` → `python` → `python3`, ukurasa wa error wenye
  log ya Python + suluhisho + kitufe "Jaribu tena", `did-fail-load` → error page. Majaribio 6 (mock electron) ✓.

## Phase 8.C — v2.8 FINAL CROSSCHECK (2026-10-31) ✅
- 🐛 **gui_server**: `/api/slips` + `/api/calibration` (GET & POST) zilitumia `sb` isiyokuwepo → Slips/Analytics
  zilikuwa tupu kimya kimya. Sasa zinatumia `worker.sb` ✓.
- 🐛 **worker cmd_run**: `.status_code` juu ya JSON (picks/slips/snapshots/odds-refresh) → Run Engine ingeanguka
  wakati wa kuhifadhi slips. Mpya: `sb_resp()` (status_code/json/text, hairushi) ✓.
- 🐛 **snapshots path** `/rest/v1/` mara mbili → sasa `odds_snapshots` ✓.
- 🐛 **rec_to_row**: status ilisomwa `status` badala ya `st` (scraper) → mechi zote zilihifadhiwa "Scheduled".
  Sasa status halisi + `final_home/final_away` kwa mechi zilizoisha ✓ (row_to_rec inarudisha `st`/`sc`).
- 🐛 **settle**: safu `fh/fa` hazipo → `final_home/final_away`; majina ya timu sasa URL-encoded (`&`, nafasi) ✓.
- 🐛 **cmd_scrape**: `DELETE day_cache` ya jana ilizuiwa na trigger ya history (HTTP 400) → imeondolewa (upsert inatosha).
- 🛡 **Uaminifu**: scrape ya mechi 0 → `✗✗ SCRAPE IMESHINDWA` + suluhisho, rc=2, GUI inaonyesha onyo jekundu.
- 🧰 `INSTALL_K96.bat` / `K96_BUILD.bat`: ASCII safi + CRLF; kurekebisha `if ( echo (...) )` iliyokuwa ikivunja cmd.
- 🧪 Test mpya `_tests/test_worker_flow.py`; **E2E LIVE dhidi ya Supabase**: Scraper→Engine(cache, collect=0)→
  Scraper kesho→settle (win/win/push/win, slip=win)→/api/results ✓ → cleanup rows 0.

## Phase 8.B — v2.8 (2026-10-29) ✅ 2-BUTTON FLOW: Scraper → Engine
- **"⬇ Run Scraper (leo+jana)"**: scrape Forebet kwa siku husika (cache-aware) **+ JANA
  fresh** (hataki cache: results zina-update), upsert matches → Supabase, kisha **settle
  picks/slips za jana AUTOMATIC** (moja kwa moja, hakuna action nyingine).
- **"🔍 Run Engine (picks/slips)"**: inasoma data za cache (bila rescrape — haraka sana)
  baada ya scraper → engine v1.0 → bookie verification → Slips.
- worker.py: mode mpya `scrape` (python worker.py scrape [--date 2026-10-29]) +
  `_scrape_day` helper (run+scrape wameshare), `_settle_day_from_finals` in-line.
- GUI: Picks tab ina radio-flow 1→2; Results page auto-refresh baada ya scrape.

## Phase 8 — v2.7 (2026-10-29) ✅ ENGINE v1.0 = K96 ENGINE RULES
- **Rewrite kamili**: engine v0.2-points → v1.0-probability-rules (K96_ENGINE_RULES.md):
  · G1 hakuna +points · G2 devig (Double Chance inanormalize hadi **tu-2** — bug ya sum-2
    imerekebishwa pande zote betway & betPawa) · G3 blend 0.5·model + 0.5·market + calibration
  · G4 flags −1pt ea (model_vs_market · bookies_disagree · favourite_away · h2h_against ·
    form_against · ps_contradicts · model_fit_poor) max −3
  · F2 λ-fit: grid ya home-share ±avg (Bayern → λ 2.78/0.93, fit_err tracking)
  · F3 avg haipo → goal markets zimezimwa · F4 p-sum ±3 → block
  · **BASKETBALL (B1–B3)**: margin Normal SD=11.5 z-fit → Handicap ±5.5/±9.5 + Totals
    (Σ: "Away +9.5" kwa mechi 50/50 — sio Winner)
  · **TENNIS (T1–T5)**: games diff SD=4.5/6.0 → P1 ±3.5 + Total games · **T5 lopsided veto**
    (favourite ≥85% → Over games zimetolewa)
  · Block list nzima: friendly/exhibition/youth/women/reserve/doubles/ITF/esports/virtual/
    status≠Scheduled + suffix W/II/B **mwisho wa jina tu, SIO tennis** ("B. Player" trap)
  · G7 tie-break ≤1pt → odds → EV · **rejected top-3 kwa sababu** katika kila pick
- test_engine_v3.py: 10 makundi mapya kwa rules; zote suites (7) GREEN; E2E offline demo ✓.

## Phase 7.C — v2.6 (2026-10-28) ✅ SCRAPER IMETEGEMEA-LOUDLY
- fetch_text: requests/curl_cffi/Playwright KILA-moja — mwisho ikifeli: **FetchError (raise)** —
  hakuna "cache tupu / log tupu" tena. Activity Log inaishamiza cause + 4 remedies.
- fetch_day_feed v9-diagnosis: "CHanzo zote 3 zimeshindwa — Mtandao wako / VPN" + exact INSTALL_K96.bat.
- **INSTALL_K96.bat** — ONE-easy double-click: pip deps + Playwright Chromium ha-download
  kama is ifunge (free-of-mimi ship siri): end user HATOHITAJI kuiicha setup.
- Engine: smart-engine v0.3 (state-of-art blend) — ALL 7 test suites remain GREEN.

## Phase 8.F — v2.8.2 (2026-11-01) ✅ SCRAPER YA HARAKA + KUHIFADHI PAPO HAPO
- 🐛 **Scraper ilichukua saa 1.5+**: ilifungua ukurasa wa H2H wa KILA mechi (1033 × ~5s) kabla ya kuhifadhi chochote;
  GUI ilikata tamaa baada ya dk 30 (rc=-2) → Supabase tupu. Sasa:
  - **Run Scraper** = mechi zote BILA H2H (dakika chache) na **kila sport inahifadhiwa Supabase papo hapo**.
  - **Run Engine** = engine pre-pass → wateule ≤40 → H2H kwa hao tu (~3 dk) → picks + slips.
- 🐛 **Supabase inarudisha mistari 1000 tu** → engine ingeona mechi 1000 kati ya 1353. Mpya: `sb_all()` (kurasa).
- 🛡 Hakuna kikomo cha dk 30 kwenye GUI; kazi mbili haziwezi kuanza pamoja (kubonyeza tena = kuunganishwa na ile ile);
  ukirefresh GUI, inaonyesha maendeleo ya kazi inayoendelea. `taskkill /T` inazima pia worker wa server ya zamani.
- 🔐 `schema_v3_security.sql`: inaondoa maonyo ya Supabase Security Advisor (views security_invoker + search_path).
- 🧪 E2E kubwa dhidi ya Supabase halisi: 1353 mechi (1033/120/200) → scrape 0 H2H, DB 1353/1353 →
  engine H2H 37 tu → picks 10 + slip 1 → cleanup 0.

## Phase 8.E — v2.8.1 (2026-11-01) ✅ TAREHE + LOG ZA MOJA KWA MOJA + SERVER YA ZAMANI
- 🐛 **Tarehe ilikwama**: `CFG.day` ilihifadhiwa localStorage → GUI ilibaki siku ya kwanza ulipoifungua.
  Sasa HAIHIFADHIWI; inatumia **EAT (UTC+3)** (JS + Python `today_eat()`), inajisasisha saa 6 usiku,
  na Picks ina kichagua tarehe + kitufe **Leo**.
- 🐛 **Run Scraper "haifanyi kitu" / Activity Log tupu**: worker iliendeshwa bila `-u` → Python ilishikilia
  output hadi mwisho; `pollJob` ilifuta mstari wa kwanza. Sasa `-u` + `PYTHONUNBUFFERED`, log inaonekana ndani ya
  sekunde 1 kwenye skrini ya Picks (mistari 6 ya mwisho + saa), na console inaonyesha kila hatua kwa saa.
- 🐛 `fetch` ikishindwa (server imezima) → kitufe kilibaki kimya. Sasa ujumbe wazi + dot nyekundu; JS error
  yoyote → bango jekundu juu (hakuna skrini tupu kimya).
- 🛡 **Server ya zamani** iliyobaki kwenye port 8777 (ingeonyesha GUI ya zamani isiyo na /api/scrape):
  `K96_START.bat` inaizima kwanza; Electron inaangalia `/api/version` na kuizima; gui_server inakataa
  kuendelea na toleo la zamani kwa ujumbe wazi.
- 🪟 GUI inafunguka kama **dirisha la app** (Edge/Chrome `--app`) — Electron haihitajiki tena.
  `INSTALL_K96.bat` inaweka icon **"K96 PICKS"** kwenye Desktop → K96_START.bat (inafunika icon ya zamani).
- 🗂 Kila job inaandika log kwenye `forebet_backend/logs/` (tuma faili hilo kama kuna tatizo).
- 🔇 BrokenPipe noise kwenye console imezimwa; ukaguzi wa Supabase unafanyika nyuma (haichelewesha kuwaka).

## Phase 8.D — v2.8 BLACK-SCREEN FIX (2026-10-31) ✅
- 🐛 **gui_server.py**: double-click ilionyesha console nyeusi tu — browser ilifunguka ndani ya .exe pekee.
  Sasa browser inafunguka yenyewe kila mara (isipokuwa `K96_NO_BROWSER=1`), banner wazi "USIFUNGE dirisha hili",
  na ukiifungua mara ya pili (port 8777 inatumika) inafungua tu browser badala ya kuanguka.
- 🆕 **K96_START.bat**: kizinduzi cha kubofya mara moja (py/python auto) — kikianguka kinaonyesha error + `pause`.
- 🐛 **Electron**: faili za Python zilikuwa ndani ya `app.asar` (Python haiwezi kuzisoma) → server haikuwaka →
  BLACK SCREEN. Sasa `extraResources` → `resources/backend` + `resources/forebet_picks_app` (+ `.env.local`).
  main.js: skrini ya "inapakia" papo hapo, inajaribu `py -3` → `python` → `python3`, ukurasa wa error wenye
  log ya Python + suluhisho + kitufe "Jaribu tena", `did-fail-load` → error page. Majaribio 6 (mock electron) ✓.

## Phase 8.C — v2.8 FINAL CROSSCHECK (2026-10-31) ✅
- 🐛 **gui_server**: `/api/slips` + `/api/calibration` (GET & POST) zilitumia `sb` isiyokuwepo → Slips/Analytics
  zilikuwa tupu kimya kimya. Sasa zinatumia `worker.sb` ✓.
- 🐛 **worker cmd_run**: `.status_code` juu ya JSON (picks/slips/snapshots/odds-refresh) → Run Engine ingeanguka
  wakati wa kuhifadhi slips. Mpya: `sb_resp()` (status_code/json/text, hairushi) ✓.
- 🐛 **snapshots path** `/rest/v1/` mara mbili → sasa `odds_snapshots` ✓.
- 🐛 **rec_to_row**: status ilisomwa `status` badala ya `st` (scraper) → mechi zote zilihifadhiwa "Scheduled".
  Sasa status halisi + `final_home/final_away` kwa mechi zilizoisha ✓ (row_to_rec inarudisha `st`/`sc`).
- 🐛 **settle**: safu `fh/fa` hazipo → `final_home/final_away`; majina ya timu sasa URL-encoded (`&`, nafasi) ✓.
- 🐛 **cmd_scrape**: `DELETE day_cache` ya jana ilizuiwa na trigger ya history (HTTP 400) → imeondolewa (upsert inatosha).
- 🛡 **Uaminifu**: scrape ya mechi 0 → `✗✗ SCRAPE IMESHINDWA` + suluhisho, rc=2, GUI inaonyesha onyo jekundu.
- 🧰 `INSTALL_K96.bat` / `K96_BUILD.bat`: ASCII safi + CRLF; kurekebisha `if ( echo (...) )` iliyokuwa ikivunja cmd.
- 🧪 Test mpya `_tests/test_worker_flow.py`; **E2E LIVE dhidi ya Supabase**: Scraper→Engine(cache, collect=0)→
  Scraper kesho→settle (win/win/push/win, slip=win)→/api/results ✓ → cleanup rows 0.

## Phase 8.B — v2.8 (2026-10-29) ✅ 2-BUTTON FLOW: Scraper → Engine
- **"⬇ Run Scraper (leo+jana)"**: scrape Forebet kwa siku husika (cache-aware) **+ JANA
  fresh** (hataki cache: results zina-update), upsert matches → Supabase, kisha **settle
  picks/slips za jana AUTOMATIC** (moja kwa moja, hakuna action nyingine).
- **"🔍 Run Engine (picks/slips)"**: inasoma data za cache (bila rescrape — haraka sana)
  baada ya scraper → engine v1.0 → bookie verification → Slips.
- worker.py: mode mpya `scrape` (python worker.py scrape [--date 2026-10-29]) +
  `_scrape_day` helper (run+scrape wameshare), `_settle_day_from_finals` in-line.
- GUI: Picks tab ina radio-flow 1→2; Results page auto-refresh baada ya scrape.

## Phase 8 — v2.7 (2026-10-29) ✅ ENGINE v1.0 = K96 ENGINE RULES
- **Rewrite kamili**: engine v0.2-points → v1.0-probability-rules (K96_ENGINE_RULES.md):
  · G1 hakuna +points · G2 devig (Double Chance inanormalize hadi **tu-2** — bug ya sum-2
    imerekebishwa pande zote betway & betPawa) · G3 blend 0.5·model + 0.5·market + calibration
  · G4 flags −1pt ea (model_vs_market · bookies_disagree · favourite_away · h2h_against ·
    form_against · ps_contradicts · model_fit_poor) max −3
  · F2 λ-fit: grid ya home-share ±avg (Bayern → λ 2.78/0.93, fit_err tracking)
  · F3 avg haipo → goal markets zimezimwa · F4 p-sum ±3 → block
  · **BASKETBALL (B1–B3)**: margin Normal SD=11.5 z-fit → Handicap ±5.5/±9.5 + Totals
    (Σ: "Away +9.5" kwa mechi 50/50 — sio Winner)
  · **TENNIS (T1–T5)**: games diff SD=4.5/6.0 → P1 ±3.5 + Total games · **T5 lopsided veto**
    (favourite ≥85% → Over games zimetolewa)
  · Block list nzima: friendly/exhibition/youth/women/reserve/doubles/ITF/esports/virtual/
    status≠Scheduled + suffix W/II/B **mwisho wa jina tu, SIO tennis** ("B. Player" trap)
  · G7 tie-break ≤1pt → odds → EV · **rejected top-3 kwa sababu** katika kila pick
- test_engine_v3.py: 10 makundi mapya kwa rules; zote suites (7) GREEN; E2E offline demo ✓.

## Phase 7.C — v2.6 (2026-10-28) ✅ SCRAPER IMETEGEMEA-LOUDLY
- fetch_text: requests/curl_cffi/Playwright KILA-moja — mwisho ikifeli: **FetchError (raise)**
  hakuna "cache tupu / log tupu" tena. Activity Log ineleza cause + 4 remedies aRef.
- fetch_day_feed: diagnosis safi (Mtandao / VPN / INSTALL_K96.bat).
- **INSTALL_K96.bat** — one-click: pip deps + Playwright Chromium ha-download.
- Engine: smart-engine v0.3 — ALL 7 test suites remain GREEN.

## Phase 8.F — v2.8.2 (2026-11-01) ✅ SCRAPER YA HARAKA + KUHIFADHI PAPO HAPO
- 🐛 **Scraper ilichukua saa 1.5+**: ilifungua ukurasa wa H2H wa KILA mechi (1033 × ~5s) kabla ya kuhifadhi chochote;
  GUI ilikata tamaa baada ya dk 30 (rc=-2) → Supabase tupu. Sasa:
  - **Run Scraper** = mechi zote BILA H2H (dakika chache) na **kila sport inahifadhiwa Supabase papo hapo**.
  - **Run Engine** = engine pre-pass → wateule ≤40 → H2H kwa hao tu (~3 dk) → picks + slips.
- 🐛 **Supabase inarudisha mistari 1000 tu** → engine ingeona mechi 1000 kati ya 1353. Mpya: `sb_all()` (kurasa).
- 🛡 Hakuna kikomo cha dk 30 kwenye GUI; kazi mbili haziwezi kuanza pamoja (kubonyeza tena = kuunganishwa na ile ile);
  ukirefresh GUI, inaonyesha maendeleo ya kazi inayoendelea. `taskkill /T` inazima pia worker wa server ya zamani.
- 🔐 `schema_v3_security.sql`: inaondoa maonyo ya Supabase Security Advisor (views security_invoker + search_path).
- 🧪 E2E kubwa dhidi ya Supabase halisi: 1353 mechi (1033/120/200) → scrape 0 H2H, DB 1353/1353 →
  engine H2H 37 tu → picks 10 + slip 1 → cleanup 0.

## Phase 8.E — v2.8.1 (2026-11-01) ✅ TAREHE + LOG ZA MOJA KWA MOJA + SERVER YA ZAMANI
- 🐛 **Tarehe ilikwama**: `CFG.day` ilihifadhiwa localStorage → GUI ilibaki siku ya kwanza ulipoifungua.
  Sasa HAIHIFADHIWI; inatumia **EAT (UTC+3)** (JS + Python `today_eat()`), inajisasisha saa 6 usiku,
  na Picks ina kichagua tarehe + kitufe **Leo**.
- 🐛 **Run Scraper "haifanyi kitu" / Activity Log tupu**: worker iliendeshwa bila `-u` → Python ilishikilia
  output hadi mwisho; `pollJob` ilifuta mstari wa kwanza. Sasa `-u` + `PYTHONUNBUFFERED`, log inaonekana ndani ya
  sekunde 1 kwenye skrini ya Picks (mistari 6 ya mwisho + saa), na console inaonyesha kila hatua kwa saa.
- 🐛 `fetch` ikishindwa (server imezima) → kitufe kilibaki kimya. Sasa ujumbe wazi + dot nyekundu; JS error
  yoyote → bango jekundu juu (hakuna skrini tupu kimya).
- 🛡 **Server ya zamani** iliyobaki kwenye port 8777 (ingeonyesha GUI ya zamani isiyo na /api/scrape):
  `K96_START.bat` inaizima kwanza; Electron inaangalia `/api/version` na kuizima; gui_server inakataa
  kuendelea na toleo la zamani kwa ujumbe wazi.
- 🪟 GUI inafunguka kama **dirisha la app** (Edge/Chrome `--app`) — Electron haihitajiki tena.
  `INSTALL_K96.bat` inaweka icon **"K96 PICKS"** kwenye Desktop → K96_START.bat (inafunika icon ya zamani).
- 🗂 Kila job inaandika log kwenye `forebet_backend/logs/` (tuma faili hilo kama kuna tatizo).
- 🔇 BrokenPipe noise kwenye console imezimwa; ukaguzi wa Supabase unafanyika nyuma (haichelewesha kuwaka).

## Phase 8.D — v2.8 BLACK-SCREEN FIX (2026-10-31) ✅
- 🐛 **gui_server.py**: double-click ilionyesha console nyeusi tu — browser ilifunguka ndani ya .exe pekee.
  Sasa browser inafunguka yenyewe kila mara (isipokuwa `K96_NO_BROWSER=1`), banner wazi "USIFUNGE dirisha hili",
  na ukiifungua mara ya pili (port 8777 inatumika) inafungua tu browser badala ya kuanguka.
- 🆕 **K96_START.bat**: kizinduzi cha kubofya mara moja (py/python auto) — kikianguka kinaonyesha error + `pause`.
- 🐛 **Electron**: faili za Python zilikuwa ndani ya `app.asar` (Python haiwezi kuzisoma) → server haikuwaka →
  BLACK SCREEN. Sasa `extraResources` → `resources/backend` + `resources/forebet_picks_app` (+ `.env.local`).
  main.js: skrini ya "inapakia" papo hapo, inajaribu `py -3` → `python` → `python3`, ukurasa wa error wenye
  log ya Python + suluhisho + kitufe "Jaribu tena", `did-fail-load` → error page. Majaribio 6 (mock electron) ✓.

## Phase 8.C — v2.8 FINAL CROSSCHECK (2026-10-31) ✅
- 🐛 **gui_server**: `/api/slips` + `/api/calibration` (GET & POST) zilitumia `sb` isiyokuwepo → Slips/Analytics
  zilikuwa tupu kimya kimya. Sasa zinatumia `worker.sb` ✓.
- 🐛 **worker cmd_run**: `.status_code` juu ya JSON (picks/slips/snapshots/odds-refresh) → Run Engine ingeanguka
  wakati wa kuhifadhi slips. Mpya: `sb_resp()` (status_code/json/text, hairushi) ✓.
- 🐛 **snapshots path** `/rest/v1/` mara mbili → sasa `odds_snapshots` ✓.
- 🐛 **rec_to_row**: status ilisomwa `status` badala ya `st` (scraper) → mechi zote zilihifadhiwa "Scheduled".
  Sasa status halisi + `final_home/final_away` kwa mechi zilizoisha ✓ (row_to_rec inarudisha `st`/`sc`).
- 🐛 **settle**: safu `fh/fa` hazipo → `final_home/final_away`; majina ya timu sasa URL-encoded (`&`, nafasi) ✓.
- 🐛 **cmd_scrape**: `DELETE day_cache` ya jana ilizuiwa na trigger ya history (HTTP 400) → imeondolewa (upsert inatosha).
- 🛡 **Uaminifu**: scrape ya mechi 0 → `✗✗ SCRAPE IMESHINDWA` + suluhisho, rc=2, GUI inaonyesha onyo jekundu.
- 🧰 `INSTALL_K96.bat` / `K96_BUILD.bat`: ASCII safi + CRLF; kurekebisha `if ( echo (...) )` iliyokuwa ikivunja cmd.
- 🧪 Test mpya `_tests/test_worker_flow.py`; **E2E LIVE dhidi ya Supabase**: Scraper→Engine(cache, collect=0)→
  Scraper kesho→settle (win/win/push/win, slip=win)→/api/results ✓ → cleanup rows 0.

## Phase 8.B — v2.8 (2026-10-29) ✅ 2-BUTTON FLOW: Scraper → Engine
- **"⬇ Run Scraper (leo+jana)"**: scrape Forebet kwa siku husika (cache-aware) **+ JANA
  fresh** (hataki cache: results zina-update), upsert matches → Supabase, kisha **settle
  picks/slips za jana AUTOMATIC** (moja kwa moja, hakuna action nyingine).
- **"🔍 Run Engine (picks/slips)"**: inasoma data za cache (bila rescrape — haraka sana)
  baada ya scraper → engine v1.0 → bookie verification → Slips.
- worker.py: mode mpya `scrape` (python worker.py scrape [--date 2026-10-29]) +
  `_scrape_day` helper (run+scrape wameshare), `_settle_day_from_finals` in-line.
- GUI: Picks tab ina radio-flow 1→2; Results page auto-refresh baada ya scrape.

## Phase 8 — v2.7 (2026-10-29) ✅ ENGINE v1.0 = K96 ENGINE RULES
- **Rewrite kamili**: engine v0.2-points → v1.0-probability-rules (K96_ENGINE_RULES.md):
  · G1 hakuna +points · G2 devig (Double Chance inanormalize hadi **tu-2** — bug ya sum-2
    imerekebishwa pande zote betway & betPawa) · G3 blend 0.5·model + 0.5·market + calibration
  · G4 flags −1pt ea (model_vs_market · bookies_disagree · favourite_away · h2h_against ·
    form_against · ps_contradicts · model_fit_poor) max −3
  · F2 λ-fit: grid ya home-share ±avg (Bayern → λ 2.78/0.93, fit_err tracking)
  · F3 avg haipo → goal markets zimezimwa · F4 p-sum ±3 → block
  · **BASKETBALL (B1–B3)**: margin Normal SD=11.5 z-fit → Handicap ±5.5/±9.5 + Totals
    (Σ: "Away +9.5" kwa mechi 50/50 — sio Winner)
  · **TENNIS (T1–T5)**: games diff SD=4.5/6.0 → P1 ±3.5 + Total games · **T5 lopsided veto**
    (favourite ≥85% → Over games zimetolewa)
  · Block list nzima: friendly/exhibition/youth/women/reserve/doubles/ITF/esports/virtual/
    status≠Scheduled + suffix W/II/B **mwisho wa jina tu, SIO tennis** ("B. Player" trap)
  · G7 tie-break ≤1pt → odds → EV · **rejected top-3 kwa sababu** katika kila pick
- test_engine_v3.py: 10 makundi mapya kwa rules; zote suites (7) GREEN; E2E offline demo ✓.

## Phase 7.B — v2.5 (2026-10-28) ✅ AUTO-HEAL ya cache-tupu
- Ikiwa scraping ya kwanza ilishindika (Forebet blocked/mtandao) → cache iliwasobadirigikwa TUPU:
  sasa worker hu-bonyeza cache stop gereza na rescrape FRESH (bgija na aix).
- Siku ile ile ya siku-0 rows huitday_cache no-longer ni ha-full-ley (delete row).
- `.env.local` iko kwenye zip (mbinafsi) KAMA user ilivyoamua.

## Phase 6 — v2.4 (2026-10-28) ✅ HONESTY PHASE (settle + backtest + calibration)
- settle_pick: basketball (Winner incl OT) + tennis (match winner; walkover/retire → `void`) ✓
- settle_slips(): slip wins ikiwa legs zote-isizo-void zameshinda; push-odds hurembalwa.
- `backtest.py --from ... --to ...`: walk-forward replay ya day_cache → hit-rate per market,
  Brier & log-loss, buckets pred-vs-actual.
- `calibration.py`: isotonic PAVA ikifika ≥300 settled → `data/calibration.json` → auto ya engine.
- daemon: 06:00/12:00 odds-refresh · Jumatatu 04:00 calibration refit.
- GUI Analytics: calibration chart (predicted● vs actual●) + slips history.
- KOOMEA: ODDS_BAND na sentensi zake zimefutwa KINUKERE (grep = 0 hits).

## Phase 5 — v2.3 (2026-10-28) ✅ BETSLIP BUILDER (DP)
- `slip.py`: DP juu ya log-odds buckets (step 0.005) + back-pointers — deterministic 100%.
  Lengo: odds [SLIP_ODDS_MIN..MAX] (default 1.85–2.50), joint-P MAX; FORCE_LEGS=N mode iki-support na warning.
- Top-5 slips: SAFEST / BALANCED / HIGHER_ODDS/edition — joint-P halisi EV & correlation-haircut (league pairs ×0.98).
- "Hakuna slip salama leo" ikasivyokupatikna — kamwe haiforced bad slip ✓
- GUI: 🎫 Slips tab (legs table + joint % + risk % + EV) + Settings → Slip Builder card Save
  (LEG_ODDS · SLIP_ODDS · MAX_LEGS · FORCE_LEGS · MIN_LEG_PROB · BLOCK_FRIENDLY imeitiliali n Supabase/ai).
- Copy/print line: elimu ya odds-historia ya slips (ida: "10 legs × 90% ≈ 35% tu").
- slips + slip_legs rows zinahifadhiwa Supabase (schema_v2 muhimu).

## Phase 4 — v2.2 (2026-10-28) ✅ ENGINE v0.3 (upishano mkubwa)
- `model_probabilities()`: Poisson (λ ime-fit kwenye Forebet 1X2 — fit err ≤ 1 pt on tests) →
  Totals/BTTS/EH probabilities HALISI · DC = p1+px exact · DNB normalized.
- `bookie.make_provider()`: per-match bookmaker markets → devig (betway primary, pawa fallback).
- `p_final = 0.5·model + 0.5·market` baadaye calibration (Phase 6 itajaza isotonic).
- **ODDS_BAND +6/−6 IMEFUTWA KABISA** — odds ni mipaka TU (config LEG_ODDS_MIN/MAX).
- Rules kubwa 10 zimeshubuliwa kuwa FLAGS/veto (__form_against, h2h_against, ps_contra, fav_away_)
  — zinapunguza p_cal kwa −1pt kila moja (cap −3pt), KAMWE hazi-hini probability.
- **FRIENDLY BLOCK ngumu** (E6); junk legs (fair-odds < 1.15 model-only / < LEG_ODDS_MIN online) hu-dropped.
- Live verified: Man City-Brighton EH+2: model 94.6% × devig 94.2% → conf 94 @1.05 (EV −0.9% honest).
- test_msingi UPDATED kwa v0.3 (DC=0.87 exact assert sasa).

## Phase 3 — v2.1 (2026-10-28) ✅
- `oddsx.py`: devig (margin removal) + combine + bookies-disagree flags — 5 asset tests GREEN.
- `betway.snapshot_event()` + `bookie.snapshot_event()`: outcomes ZOTE za event (815/1141 rows!).
- worker: `[COVERAGE]` per-sport betway-vs-pawa counts + kuhifadhi `odds_snapshots` Supabase
  (kipima, closing-value data ya Phase 6).
- `schema_v2.sql`: odds_snapshots · slips · slip_legs · calibration view ·
  trigger inayozuia day_cache kufute settled history (spec D4) — RUN in SQL Editor.

## Phase 2 — v2.0 (2026-10-28) ✅
- `matching.py`: matcher MOJA ya bookie zote — distinguishing tokens (Inter ≠ Inter Miami ✓),
  Jaccard+SequenceMatcher, aliases (48 groups), kickoff **±20 min** (tofauti ya muda → REJECT),
  fixtures ambiguofu/wambegesi → REJECT kamwe usi-guess. Ali-handle "Hanfmann, Yannick"↔"Y. Hanfmann".
- bookie.py + betway.py: duplicates za _norm/_sim zimefutwa (B3) — zote zinatumia matching.py.
- Fake tests: 11 asserts GREEN + live cross-check: Man City ✓ bw 1.66 / pawa 1.84 · time mbaya → REJECT ✓.

## Phase 1 — v1.9 (2026-10-28) ✅
- `validation.py`: ukaguzi wa records nyingi kabla ya engine (12 unit tests, stats zinachapishwa kwa run).
- `config.py`: mipangilio yote mahali moja (LEG_ODDS, SLIP_ODDS, MAX_LEGS, MIN_CONF…) + `k96_settings.json`.
- `worker.load_env()`: halisi validation ya URL/JWT/role/ref/expiry, error ya wazi Kiswahili, exit 2.
- `test_supabase.py`: jaribio la 7 (auth, RLS, tables, round-trip, clock skew) — **7/7 PASS live**.
- scaper: `_plain()` duplicate imeondolewa · silent-except counters (`ERRS`) · iki-burni up doa.
- forebet_scraper/ (dupl kitata lama) — IMEFUTWA.
- `.gitignore` + `.env.example` (zabad hakuna sirri hata).
- **SECURITY**: ZIP ya usambari HAIJA-jumba `.env.local` tena. Owner: rotate keys Supabase.

## v1.8 (2026-10-28) — Betway primary chain + ENGINE AUTO-REPLACE + diversity caps
## v1.7 — Betway TZ module (REST feeds) + GUI chip
## v1.6 — betPawa TZ verification

## KINACHAFUATA (Phase 2): matching.py borda (aliasing · kickoff ±20min · ambiguity-reject)
