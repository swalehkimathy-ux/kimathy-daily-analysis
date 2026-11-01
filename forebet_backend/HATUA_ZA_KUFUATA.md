# K96 PICKS — HATUA ZA KUFUATA (v2.8.6)

## Sasa hivi (v2.8 · smart-engine v1.0 · vitufe 2)
1. **Supabase (mara moja):** SQL Editor → endesha kwa mpangilio `schema.sql`, `schema_v2.sql`, `schema_v3_security.sql`, kisha `schema_v4_reliability.sql`.
2. **Keys za PC:** source zip → tengeneza `forebet_backend/.env.local` kutoka `.env.example`; Electron installer → weka `.env.local` ndani ya `resources/backend/`. Usiweke GitHub/zip/chat. Ikiwa keys halisi ziliwahi kuwa GitHub, zizungushe (rotate) kwanza.
3. **Sakinisha PC:** `INSTALL_K96.bat` → kisha `TEST_CONNECTION.bat` (sasa hukagua anon deny na analysis_runs pia).
4. **Kila siku:** double-click `K96_START.bat` (browser inafunguka yenyewe) →
   **⬇ 1) Run Scraper** (leo + jana/matokeo) → **🔍 2) Run Engine** (picks + slips) → **🏁 Results**.
5. **Kila siku (manual):** chagua tarehe, bonyeza Run Scraper, hakikisha imethibitishwa Supabase, kisha bonyeza Run Engine.
6. **CLI mbadala:** `python worker.py scrape --date YYYY-MM-DD` kisha `python worker.py run --date YYYY-MM-DD`.
7. **Desktop build (hiari):** `K96_BUILD.bat` (inahitaji Node.js + Python).

Scraper hubadilisha `scrape_status` na kuthibitisha rows za Supabase. Engine huweka kila run kivyake; run iliyofeli haifuti picks/slips za mwisho zilizofanikiwa.

## Kinachofuata
- [ ] Settled ≥300 → `calibration.json` inaanza kutumika kikamilifu.
- [ ] Backtest ya wiki — linganisha buckets za uwezekano dhidi ya matokeo halisi.
- [ ] Closing-line value: `odds_snapshots` zikiongezeka, pima kama picks zinashinda line.
