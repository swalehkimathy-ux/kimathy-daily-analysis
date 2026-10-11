# Kimathy Daily Analysis

Private, on-demand sports analysis dashboard and accumulator pipeline, with a server-enforced limit of one manual request per rolling 24 hours. The goal is to **aim for at least 20 winning accumulators in a month**, not merely to issue 20 tickets. That win count cannot be guaranteed. The system may publish no ticket when fixtures, usable odds or market-specific evidence are insufficient. Each ticket targets combined decimal odds of 1.50 to below 1.90.

## Current build

- Responsive private web dashboard with Supabase email/password sign-in; no public sign-up or demo-pick fallback is built into the app.
- GitHub Actions is manual-only (`workflow_dispatch`); no schedule is configured. The private app's **Run analysis now** button sends the explicit request to GitHub Actions. Opening the app or refreshing its saved dashboard data does not call the sports-data providers.
- The app, Edge Function, and pipeline share a durable Supabase cooldown. One request is accepted per rolling 24 hours; direct GitHub manual runs are also stopped before provider calls if the cooldown is active.
- The Odds API supplies odds. API-Sports supplies football/basketball statistics and can settle past fixtures from final scores.
- A read-only RSS layer checks recent football/basketball news and previews from BBC Sport and ESPN. It adds attributed headlines/links and cautious keyword tags to the fixture note only; it never passes an evidence gate, changes ranking, or fetches article pages.
- Football markets: exact-line totals (0.5, 1.5, 2.5), BTTS Yes/No, directly quoted home-or-draw double chance, and direct 1X2 home win/draw/away win when the selected result is supported by H2H.
- Basketball markets: home moneyline, exact-line totals, and home/away handicap.
- Tennis odds are paused until a permitted rankings/surface/form source is integrated. Corners, cards, cricket, and unsupported markets are not selected.
- At most one selection from a given game can enter a ticket, avoiding stacked correlated markets from the same event.
- Analysis scores are ranking heuristics, **not win probabilities**. The system does not place bets or guarantee returns.

## One-time Supabase setup for an existing project

The browser tables were previously public read-only. This build changes them to **allowlisted-user-only** access. The GitHub Actions service-role key remains server-side and continues to write through the workflow.

1. In Supabase **SQL Editor**, run `supabase/migration_private_dashboard.sql`.
2. In **Authentication → Users**, create your app login account. This is separate from signing in to the Supabase admin dashboard.
3. In Supabase Auth settings, turn off public sign-ups. The allowlist is the main database protection; disabling sign-ups is extra protection.
4. Open `supabase/authorize-owner-template.sql`, replace the sample email with the exact app-login email, and run it in SQL Editor. It should report one authorized owner.
5. Run `supabase/migration_manual_run_guard.sql` in SQL Editor after `migration_private_dashboard.sql`. It creates the private, atomic rolling 24-hour request limit.
6. In Supabase **Edge Functions → Deploy a new function → Via Editor**, create `trigger-analysis`, paste the contents of `supabase/functions/trigger-analysis/index.ts`, and deploy with JWT verification enabled. This server-side function checks the signed-in allowlisted user and dispatches the manual GitHub workflow.
7. Create a GitHub fine-grained personal access token limited to `swalehkimathy-ux/kimathy-daily-analysis` with **Actions: Read and write**. Save it only in Supabase **Edge Function Secrets** as `KIMATHY_GITHUB_TOKEN`; never put it in the web app, GitHub repository, or chat.
8. Open the hosted app and sign in. The button stays disabled until the cooldown status is available. Clicking it explicitly requests a run; a confirmation explains the possible API usage.

The SQL migrations remove anonymous reads and any older broad policies. Until the owner is allowlisted, the browser receives no analysis rows. Do not place API keys or the Supabase service-role key in `config.js` or in the HTML. The `sb_publishable_...` browser key identifies the project; Row Level Security protects the data. The Edge Function's GitHub token and Supabase admin key stay server-side.

For a brand-new Supabase project, run `supabase/schema.sql` instead of `migration_private_dashboard.sql`, then run the manual-run guard migration and create/authorize the app login as above. For non-developer GitHub/Desktop and hosting steps, see `PRIVATE_APP_SETUP.md`.

## GitHub Actions secrets

The GitHub Actions workflow keeps using the existing server-side secrets:

- `THE_ODDS_API_KEY`
- `API_SPORTS_KEY` (or the existing product-specific Football/Basketball secret names)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The app button also needs a repository-limited GitHub fine-grained token stored only in Supabase Edge Function Secrets under `KIMATHY_GITHUB_TOKEN` (Actions: Read and write). It is not an API provider key and does not belong in GitHub repository files, `config.js`, or chat. Never paste any key value into chat. Keep the repository private and do not expose private personal information in the analysis tables.

## Odds quota and coverage

To broaden daily fixture coverage, the Odds API connector uses one bookmaker region (`eu`) and selects up to **10 competitions: eight soccer and two basketball**. Two soccer market families rotate across each league/day so the slate covers totals, BTTS, double chance and direct 1X2 over the rotation; basketball requests moneyline, totals and spreads. A hard runtime cap limits requested market credits to **22 per run** (16 soccer + 6 basketball under the full plan). At a 500-credit monthly allowance, that is about 20–22 full runs before any provider-specific differences; no daily run is scheduled automatically. The connector also respects the provider's live remaining-credit header, which is authoritative. Broader coverage does not relax the existing evidence thresholds and does not guarantee a ticket or win.

API-Sports enrichment checks account quota and fixture identity before attaching statistics. Logs now report football/basketball candidate counts and whether a shared or product-specific API-Sports key variable is set (never its value), plus provider schedule rows, matched fixtures, name/time mismatches and out-of-scope candidates. This makes an empty football enrichment result easier to diagnose. Matching remains conservative: the code does not loosen team/time rules or attach stats when the mapping is ambiguous.

## RSS news/opinion context (supporting only)

The daily run checks the official BBC Sport football and basketball RSS feeds and ESPN soccer and NBA RSS feeds. It reads the feed's own headlines/short summaries—not article webpages—and considers recent items from the previous 72 hours that are published before kickoff. An item is attached only when both fixture team names match in its title/summary. The dashboard note stores attribution, the original headline, and source link; it does not save the summaries or full article text.

This is a lightweight context signal, not an AI sentiment model or a prediction. Simple keyword topic/tone tags can misread wording, so they are explicitly excluded from market eligibility, confidence ranking, and accumulator construction. They cannot turn an odds-only candidate into a pick. If a feed is unavailable or declines access, that source is skipped without retrying or bypassing the restriction.

BBC Sport requests attribution and prohibits use of its logos/trademarks; its feed use is subject to its [RSS guidance and terms](https://www.bbc.com/sport/articles/cqllxj2n4kyo). ESPN's [RSS terms](https://www.espn.com/espn/news/story?id=3437834) require the supplied source link and attribution, prohibit modifying the feed headline/summary/URL, and disallow advertising within ESPN RSS content; the dashboard has no ads and preserves the original headline/link. The Guardian feed is intentionally excluded from automation because its [terms](https://www.theguardian.com/help/terms-of-service) restrict automated reading and content analysis/data mining absent express authorization. Coverage is not guaranteed for every league or fixture. These feeds add no API keys or setup steps.

## Evidence thresholds

- **Football direct 1X2:** among the last five completed head-to-heads, at least four must have the same outcome (home win, draw, or away win) as the quoted selection. The decimal quote must also be within the configured 1.05–1.80 leg range.
- **Football double chance 1X:** a complete 10+ team standings table, both teams with at least five league matches, home team top three, away team bottom five.
- **Football totals:** five completed head-to-head games; at least four of five must match the exact Over/Under line (0.5, 1.5 or 2.5).
- **Football BTTS:** five completed head-to-head games; at least four of five must match Yes or No.
- **Basketball home moneyline:** at least five recent home games, home win rate at least 80%, and at least five recent away games with a current away losing streak of five or more.
- **Basketball totals:** at least five relevant home and away games; each team's observed hit rate at the selected line must be at least 70% in the selected direction.
- **Basketball handicap:** at least five relevant games per side; the selected-side cover rate must be at least 70% and the opposing-side cover rate at most 30% at the quoted line.

Odds alone never pass the eligibility engine. Only one market from the same game can enter an accumulator.

## Automatic result tracking

On each run, API-Sports checks supported football/basketball fixtures from up to seven prior days, within a capped request budget. It records `win`, `loss`, or `void` only when the fixture matches and a final score is available. Unmatched, incomplete, postponed, or unsupported results remain pending; they are not guessed. Accumulator history reports a **paper** win rate and one-unit ROI based on stored odds, not actual staking or profit. API-Sports coverage varies by competition and must still be checked in a live run.

## Tests

Run offline tests from the project root:

```bash
python -m unittest discover -s pipeline -p 'test_*.py'
```

These tests mock provider/Supabase responses. They do not use your live API credentials, place bets, or verify live account coverage.

To preview the static app locally, serve the project over HTTP rather than opening the HTML with `file://`:

```bash
python3 -m http.server 4173 --bind 0.0.0.0
```

A deployed static host is still required to access the web app outside the local machine. A hosting provider can make the login page reachable, but only an allowlisted authenticated account can read the analysis tables.
