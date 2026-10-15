# Kimathy Daily Analysis

Private, on-demand sports analysis dashboard and accumulator pipeline, with a server-enforced limit of one manual request per Tanzania calendar day (Africa/Dar_es_Salaam). There is no promised win count or hit rate. The system may publish no ticket when fixtures, usable odds or market-specific evidence are insufficient. Each ticket targets combined decimal odds of 1.50 to below 1.90, with a flexible number of legs and no padding.

## Current build

- Responsive private web dashboard with Supabase email/password sign-in; no public sign-up or demo-pick fallback is built into the app.
- GitHub Actions is manual-only (`workflow_dispatch`); no schedule is configured. The private app's **Run analysis now** button sends the explicit request to GitHub Actions. Opening the app or refreshing its saved dashboard data does not call the sports-data providers.
- The app, Edge Function, and pipeline share a durable Supabase guard. One request is accepted per Tanzania calendar day (EAT); it resets at local midnight, so runs just before and after midnight can be less than 24 hours apart (up to 44 Odds API credits across those two runs, with the existing 22-credit cap per run). Direct GitHub manual runs are also stopped before provider calls if today's limit is active.
- Each owner request is timestamped server-side in UTC. The runner carries that exact timestamp through GitHub Actions and uses its Africa/Dar_es_Salaam date for schedule discovery, market rotation, ticket construction and persistence (even if the workflow starts just after EAT midnight).
- API-Sports' date-based football/basketball schedule defines the fixture universe independently of Odds API coverage; it is not derived from the Odds API event list. All normalized same-day schedule rows are stored in `analysis_fixtures`, including rows with no quote or insufficient statistics; `analysis_runs` records provider scope, counts, warnings and coverage. The Odds API supplies market quotes only for selected active sport keys/markets, and API-Sports can enrich candidate evidence and settle past fixtures from final scores.
- A read-only RSS layer checks recent football/basketball news and previews from BBC Sport and ESPN. It adds attributed headlines/links and cautious keyword tags to the fixture note only; it never passes an evidence gate, changes ranking, or fetches article pages.
- Football markets: exact-line totals (0.5, 1.5, 2.5), BTTS Yes/No, directly quoted home-or-draw double chance, direct 1X2 home win/draw/away win, and **two-way soccer spreads**. Eligibility uses H2H, recent form, venue splits, and (for 1X) standings through explicit market-specific routes. The connected Odds API market is not a European 3-way handicap, so every spread is explicitly labelled two-way; unsupported/ambiguous line types are skipped.
- Football evidence is market-specific and routes are explicit. H2H can qualify direct 1X2, 1X double chance, and BTTS; totals and spreads retain their existing H2H-plus-form route. Independently, five-game recent form and home/away venue splits can qualify suitable markets without an H2H sample, but only at the stricter thresholds documented below. Form is fetched independently of H2H, and partial/missing samples stay visible; no threshold is relaxed globally and no pick is forced.
- Basketball markets: home moneyline, exact-line totals, and home/away handicap.
- Tennis odds are paused until a permitted rankings/surface/form source is integrated. Corners, cards, cricket, and unsupported markets are not selected.
- At most one selection from a given game can enter a ticket, avoiding stacked correlated markets from the same event.
- Analysis scores are ranking heuristics, **not win probabilities**. The system does not place bets or guarantee returns.
- The private dashboard also has a Capacitor Android Studio wrapper. See `README_ANDROID.md` for Windows setup/build steps; the complete-repository ZIP includes the manual-only `.github/workflows/daily-analysis.yml` workflow and contains no secret values. Keep the repository private.

For a clean replacement of the tracked repository files, use `UPLOAD-TO-GITHUB.md`; that archive includes the workflow but excludes credentials, dependencies, and generated build output.

## One-time Supabase setup for an existing project

The browser tables were previously public read-only. This build changes them to **allowlisted-user-only** access. The GitHub Actions service-role key remains server-side and continues to write through the workflow.

1. In Supabase **SQL Editor**, run `supabase/migration_private_dashboard.sql`.
2. In **Authentication → Users**, create your app login account. This is separate from signing in to the Supabase admin dashboard.
3. In Supabase Auth settings, turn off public sign-ups. The allowlist is the main database protection; disabling sign-ups is extra protection.
4. Open `supabase/authorize-owner-template.sql`, replace the sample email with the exact app-login email, and run it in SQL Editor. It should report one authorized owner.
5. Run `supabase/migration_manual_run_guard.sql` in SQL Editor after `migration_private_dashboard.sql`. It creates or updates the private, atomic one-request-per-calendar-day guard using Africa/Dar_es_Salaam. For an existing installation, re-run this updated file to replace the old rolling 24-hour functions.
6. Run `supabase/migration_analysis_runs_fixture_board.sql` in SQL Editor. It adds the request-time run ledger and full fixture board with owner-only read access. Apply this before deploying the updated workflow or HTML; otherwise the runner cannot write the schedule snapshot.
7. In Supabase **Edge Functions → Deploy a new function → Via Editor**, create `trigger-analysis`, paste the contents of `supabase/functions/trigger-analysis/index.ts`, and deploy with JWT verification enabled. This server-side function checks the signed-in allowlisted user, captures the request timestamp and dispatches the manual GitHub workflow.
8. Create a GitHub fine-grained personal access token limited to `swalehkimathy-ux/kimathy-daily-analysis` with **Actions: Read and write**. Save it only in Supabase **Edge Function Secrets** as `KIMATHY_GITHUB_TOKEN`; never put it in the web app, GitHub repository, or chat.
9. Open the hosted app and sign in. The button stays disabled until the secure daily-limit status is available. Clicking it explicitly requests a run; a confirmation explains API usage and the midnight reset.

The SQL migrations remove anonymous reads and any older broad policies. Until the owner is allowlisted, the browser receives no analysis rows. Do not place API keys or the Supabase service-role key in `config.js` or in the HTML. The `sb_publishable_...` browser key identifies the project; Row Level Security protects the data. The Edge Function's GitHub token and Supabase admin key stay server-side.

For a brand-new Supabase project, run `supabase/schema.sql` instead of `migration_private_dashboard.sql`, then run the manual-run guard migration and create/authorize the app login as above. For non-developer GitHub/Desktop and hosting steps, see `PRIVATE_APP_SETUP.md`.

## GitHub Actions secrets

The GitHub Actions workflow keeps using the existing server-side secrets:

- `THE_ODDS_API_KEY`
- `API_SPORTS_KEY` (or the existing product-specific Football/Basketball secret names)
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

The app button also needs a repository-limited GitHub fine-grained token stored only in Supabase Edge Function Secrets under `KIMATHY_GITHUB_TOKEN` (Actions: Read and write). It is not an API provider key and does not belong in GitHub repository files, `config.js`, or chat. Never paste any key value into chat. Keep the repository private and do not expose private personal information in the analysis tables.

### GitHub dispatch troubleshooting

An active GitHub token is not necessarily authorized for this dispatch. Check that the fine-grained token includes the private repository `swalehkimathy-ux/kimathy-daily-analysis`, has repository permission **Actions: Read and write**, and is saved in Supabase Edge Function Secrets as `KIMATHY_GITHUB_TOKEN`. Also verify that `.github/workflows/daily-analysis.yml` is enabled on `main` and includes `workflow_dispatch`. The private app now shows only GitHub's HTTP status code on a rejection; it does not expose the response body or any token. Common clues: 401 authentication, 403 permission/policy, 404 inaccessible or wrong repository/workflow, and 422 invalid workflow/ref/input.

## Odds quota and coverage

To broaden daily fixture coverage, the Odds API connector uses one bookmaker region (`eu`) and selects up to **10 competitions: eight soccer and two basketball**. Two soccer market families rotate across each league/day so the slate covers totals, BTTS, double chance, direct 1X2 and two-way soccer spreads over the rotation; basketball requests moneyline, totals and spreads. A hard runtime cap limits requested market credits, including retries, to **22 per run** (16 soccer + 6 basketball under the full plan). At a 500-credit monthly allowance, that is about 20–22 full runs before provider-specific differences; no daily run is scheduled automatically. The connector also respects the provider's live remaining-credit header, which is authoritative. Broader coverage does not relax the existing evidence thresholds and does not guarantee a ticket or win.

API-Sports enrichment checks account quota and fixture identity before attaching statistics. The runner fetches its date-based schedule before Odds API filtering and persists the broadest same-day fixture list returned by the configured API-Sports product(s). The board shows fixtures with no matching quote or stats rather than deleting them, plus run timestamps, quote freshness, latest available stats timestamps, evidence sample counts, join diagnostics and missing-coverage notes. API-Sports and Odds API caps/coverage remain in force; the workflow does not claim to analyze all 1,248 advertised API-Sports competitions or every global match in depth. Logs report candidate counts, provider schedule rows, matched fixtures, name/time mismatches and out-of-scope candidates. Matching remains conservative: the code does not loosen team/time rules or attach stats when the mapping is ambiguous. For compatibility with the observed API-Sports Free-plan restriction on the `last` parameter, H2H results are filtered to the latest five locally; recent team form uses a bounded one-year `from`/`to` query and is also trimmed locally. The live client paces requests at least 6.2 seconds apart to stay below the Free-plan 10-requests-per-minute limit, including status calls. Existing per-run request and credit caps are retained; the evidence gates now include the explicit market-specific independent routes below.

Forebet and Statarea are displayed as owner-verification links only. Their pages are not scraped, copied into the app, or used as prediction inputs.

## RSS news/opinion context (supporting only)

The daily run checks the official BBC Sport football and basketball RSS feeds and ESPN soccer and NBA RSS feeds. It reads the feed's own headlines/short summaries—not article webpages—and considers recent items from the previous 72 hours that are published before kickoff. An item is attached only when both fixture team names match in its title/summary. The dashboard note stores attribution, the original headline, and source link; it does not save the summaries or full article text.

This is a lightweight context signal, not an AI sentiment model or a prediction. Simple keyword topic/tone tags can misread wording, so they are explicitly excluded from market eligibility, confidence ranking, and accumulator construction. They cannot turn an odds-only candidate into a pick. If a feed is unavailable or declines access, that source is skipped without retrying or bypassing the restriction.

BBC Sport requests attribution and prohibits use of its logos/trademarks; its feed use is subject to its [RSS guidance and terms](https://www.bbc.com/sport/articles/cqllxj2n4kyo). ESPN's [RSS terms](https://www.espn.com/espn/news/story?id=3437834) require the supplied source link and attribution, prohibit modifying the feed headline/summary/URL, and disallow advertising within ESPN RSS content; the dashboard has no ads and preserves the original headline/link. The Guardian feed is intentionally excluded from automation because its [terms](https://www.theguardian.com/help/terms-of-service) restrict automated reading and content analysis/data mining absent express authorization. Coverage is not guaranteed for every league or fixture. These feeds add no API keys or setup steps.

## Evidence thresholds

All football routes require a current, valid quote and a market that maps unambiguously to the listed outcome. Samples use the latest five completed pre-kickoff games returned by API-Sports; venue splits use the team's last five matches in the corresponding home/away role. If a required sample is shorter or a field is absent, the route fails and the board states which coverage is missing.

- **Football direct 1X2:** either at least 4/5 matching outcomes in H2H, or an independent venue route: home win requires home side wins >=4/5 at home and opponent losses >=3/5 away; away win mirrors this; draw requires each side draws >=3/5 in its relevant venue split.
- **Football double chance 1X:** any one of: standings route (10+ team table, both teams with >=5 league matches, home top three and away bottom five); H2H home-win-plus-draw >=4/5; or independent venue form (home side unbeaten >=4/5 at home and opponent losses >=3/5 away).
- **Football totals (0.5, 1.5, 2.5):** the legacy route remains H2H >=4/5 at the exact line plus five-game form for each side, with each selected-direction rate >=40% and the two-team mean >=60%. Without sufficient H2H, the independent form route requires five games per team, each selected-direction rate >=60%, and mean >=70%.
- **Football two-way spread:** the legacy route remains exact-line H2H >=4/5 plus five-game selected-side form >=70% and opponent mirrored-line form <=30%. Without sufficient H2H, the independent route requires the exact same quoted whole/half line and five samples with selected cover >=80% and opponent <=20%. Quarter-lines and European 3-way handicaps are not mapped.
- **Football BTTS Yes/No:** either H2H >=4/5 for the selected side, or five recent games for each team with BTTS Yes in >=3/5 for Yes picks, or BTTS No in >=3/5 for No picks.
- **Basketball home moneyline:** at least five recent home games, home win rate at least 80%, and at least five recent away games with a current away losing streak of five or more.
- **Basketball totals:** at least five relevant home and away games; each team's observed hit rate at the selected line must be at least 70% in the selected direction.
- **Basketball handicap:** at least five relevant games per side; the selected-side cover rate must be at least 70% and the opposing-side cover rate at most 30% at the quoted line.

The route shown for an eligible football market is the actual route used; rejected quotes display market-specific sample/threshold diagnostics. Odds alone never pass the eligibility engine. Only one market from the same game can enter an accumulator.

## Automatic result tracking

On each run, API-Sports checks supported football/basketball fixtures from up to seven prior days, within a capped request budget. It records `win`, `loss`, or `void` only when the fixture matches and a final score is available. Unmatched, incomplete, postponed, or unsupported results remain pending; they are not guessed. Accumulator history reports a **paper** win rate and one-unit ROI based on stored odds, not actual staking or profit. The private results view also audits verified pre-match predictions over a chronological 70/30 earlier/later split, deduplicating to one highest-score selection per fixture and showing observed score-band records. It does not random-shuffle, infer probabilities from the score, or auto-retune thresholds; small samples are called out. The newly added independent football routes have no archived historical Odds API quote/feature snapshots for rejected candidates, so this is not a pre-deployment backtest or calibration of those routes. Their performance can only be evaluated prospectively as pre-match predictions accrue verified outcomes. API-Sports coverage varies by competition and must still be checked in a live run.

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
