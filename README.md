# Kimathy Daily Analysis

A responsive multi-sport accumulator analysis dashboard based on the attached brief. It includes a working demo UI, a Supabase schema, a Python eligibility/optimizer engine, and a GitHub Actions schedule template. See `DATA_SOURCES.md` for the current source/permission shortlist before connecting a real feed.

## Open the app

The frontend is a standalone HTML/CSS/JS app with no build step or external libraries:

```bash
cd kimathy-daily-analysis
python3 -m http.server 4173 --bind 0.0.0.0
```

Open the served page. By default it uses **synthetic demo fixtures** and labels them as demo data. The sample teams, fixtures, odds and analysis scores are illustrative, not a real slate or live prices.

## Supabase connection

1. Run `supabase/schema.sql` in the Supabase SQL editor.
2. In `config.js`, set `supabaseUrl` and either `supabasePublishableKey` (new `sb_publishable_...` key) or `supabaseAnonKey` (legacy anon/public JWT key). The app only reads `daily_fixtures` through Supabase REST.
3. The schema grants public read-only access for these analysis tables. Do not expose private information in them. The browser must never contain a service-role key.
4. Click the refresh icon, or reload, to fetch pending fixtures for today's `Africa/Dar_es_Salaam` date.

### Temporary interface check

Run `supabase/interface-test-fixtures.sql` in the SQL editor to insert four clearly marked **fictional test rows**. Refresh the app: it should display four `TEST ONLY` fixtures and build odds close to **1.60**. After checking, run `supabase/cleanup-interface-test-fixtures.sql` to remove only those test rows.

## Daily pipeline

`pipeline/engine.py` applies the odds bands, checks evidence fields for each sport, computes a transparent 0–100 heuristic score if the feed does not supply one, then builds a score-ranked accumulator. The greedy selector stops as soon as combined decimal odds reach 1.50 and remain strictly below 1.90. It will not publish an incomplete ticket as `ready`.

### The Odds API connector

`pipeline/providers/odds_api.py` connects to The Odds API v4. It discovers in-season competitions, then by default requests at most four soccer competitions, two basketball competitions, and one active ATP plus one WTA tennis competition. It uses one bookmaker region (`eu`) and decimal prices. The conservative maximum is about 12 credits per daily run (up to 360 across 30 days); manual runs also use quota. The connector reads the provider's usage headers and skips requests when the reported remaining credits are below the expected request cost. The `/sports` catalog call itself is quota-free. See the provider's [v4 documentation](https://the-odds-api.com/liveapi/guides/v4/) for endpoint and usage details.

The adapter only normalizes markets supported by the existing strategies: football **Over 0.5 Goals** when that exact line is supplied, basketball **home moneyline**, and tennis **match winner**. It does not rename a football 1X2 price as double chance, or another totals line as Over 0.5. It also rejects started matches and bookmaker quotes older than six hours by default.

### API-Sports form/statistics connector

`pipeline/providers/api_sports.py` enriches same-day football and basketball odds candidates only when API-Sports independently matches both teams and the event time. It calls the provider's daily schedule, then requests only the relevant standings, head-to-head history, or team game history. Coverage differs by league, and an unmatched or incomplete record remains ineligible rather than being guessed.

- **Football:** current league standings are attached only when both teams have played at least five matches and the standings table has at least ten teams. The separate high-goal evidence flag requires five completed head-to-head games, with at least four having three or more goals.
- **Basketball:** home win rate is calculated from the latest up to ten completed home games (at least five are required); the opposing side's away losing streak is counted from completed away games, and is attached only when at least five such games are available.
- Requests are checked against each product's API-Sports account status. The connector caps billable requests at 60 per product per run (below the published 100/day free allowance), reserves a request for safety, and stops when the account's remaining daily quota is too low. Actual calls depend on the day's matches.
- API-Sports does not provide the tennis ranking/surface evidence this strategy requires, so tennis remains unsupported for picks. Odds alone are never enough to recommend a selection.

The connector has been validated offline with mocked API responses only. No API-Sports key has been added to the project or used for a live request yet; the first GitHub Actions run after you add the secret will verify your account's live coverage.

The API key is read only from the runner environment and is not printed. API-Sports coverage and terms vary; its terms warn that some data may require third-party permissions and restrict resale/publication. Keep this personal, do not redistribute raw provider data, and verify that your intended use is permitted. The existing `SPORTS_FEED_URL` path remains as a fallback for a complete, permitted normalized feed.

For GitHub Actions, add these repository secrets:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY` (server-side secret only)
- `THE_ODDS_API_KEY` (keep private; do not put it in `config.js`, HTML, or the repository)
- `API_SPORTS_KEY` if the dashboard uses one key for both APIs; if it gives separate product keys, use `API_FOOTBALL_KEY` and/or `API_BASKETBALL_KEY` instead (product-specific keys take precedence)
- `SPORTS_FEED_URL` and `SPORTS_FEED_TOKEN` only if using the normalized-feed fallback

**Simple setup for your API-Sports key:** in your GitHub repository open **Settings → Secrets and variables → Actions → New repository secret**. Enter `API_SPORTS_KEY` as the name and paste your key as the value, then save. If the API-Sports dashboard gave you separate product keys, create `API_FOOTBALL_KEY` and/or `API_BASKETBALL_KEY` instead. Do not paste any key into a source file or chat. After saving, open **Actions → Kimathy daily analysis → Run workflow** to test once; the logs show request counts and safe warnings, never the key.

Optional repository variable `ODDS_API_SPORT_KEYS` can be a comma-separated list of active sport keys; otherwise the connector chooses a capped default set. `ODDS_API_REGION` defaults to `eu`. A private repository is appropriate for a personal project, but keys must still be stored as Actions secrets, not committed to a file. The Supabase schema currently grants public read-only access to the analysis tables; keep private information out of them unless you later add authentication and tighter row-level security.

The workflow is scheduled with cron `30 5 * * *` (05:30 UTC / 08:30 EAT) and can also be run manually. GitHub-hosted scheduled runners can start late during busy periods, so cron is not an exact-time guarantee.

## Test the optimizer

```bash
python3 -m unittest discover -s pipeline -p 'test_*.py'
```

## Important limitations

- Analysis scores are ranking heuristics, **not calibrated probabilities**.
- This application does not place bets, verify event outcomes, or guarantee returns.
- Demo content is synthetic. Connect a provider and validate its data, freshness, market mappings and legal terms before relying on it.
- The stake calculator is illustrative only and displays a gross return estimate before fees or other deductions.
