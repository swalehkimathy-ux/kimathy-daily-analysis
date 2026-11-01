# K96 PICKS — HATUA ZA KUFUATA (v2.8)

## Sasa hivi (v2.8 · smart-engine v1.0 · vitufe 2)
1. **Supabase (mara moja):** SQL Editor → `schema.sql` kisha `schema_v2.sql` (kama bado hujafanya).
2. **Sakinisha PC:** `INSTALL_K96.bat` → kisha `TEST_CONNECTION.bat` (7/7 PASS).
3. **Kila siku:** double-click `K96_START.bat` (browser inafunguka yenyewe) →
   **⬇ 1) Run Scraper** (leo + jana/matokeo) → **🔍 2) Run Engine** (picks + slips) → **🏁 Results**.
4. **Daemon (hiari, PC online 24/7):** `python worker.py daemon` — picks 00:00, settle 01:00,
   odds-refresh 06:00/12:00, calibration Jumatatu 04:00.
5. **Desktop build (hiari):** `K96_BUILD.bat` (inahitaji Node.js + Python).

`.env.local` iko ndani ya zip (matumizi binafsi) — usiishiriki zip hii na mtu mwingine.

## Kinachofuata
- [ ] Settled ≥300 → `calibration.json` inaanza kutumika kikamilifu.
- [ ] Backtest ya wiki — linganisha buckets za uwezekano dhidi ya matokeo halisi.
- [ ] Closing-line value: `odds_snapshots` zikiongezeka, pima kama picks zinashinda line.
