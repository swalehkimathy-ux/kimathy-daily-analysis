# Maelekezo ya kusasisha Kimathy Daily Analysis

Hii ZIP ni **source code kamili** ya repository, si APK wala deployment iliyokamilika. Yaliyomo yako moja kwa moja kwenye root ya ZIP (hakuna folder la ziada la kuingia kwanza). Imejumuisha dashboard, pipeline, tests, Supabase files, GitHub Actions workflow na Android Studio project. Haijumuishi `.git`, `node_modules`, `www/`, build output, API keys, Supabase service-role key au GitHub token.

## A. Sasisha repository kupitia GitHub Desktop (Windows)

1. Pakua `kimathy-daily-analysis-full-repo.zip` kutoka hapa, kisha **Extract All** kwenye folder la muda.
2. Fanya backup ya repository yako iliyopo. Hakikisha una repo `swalehkimathy-ux/kimathy-daily-analysis` na branch `main` iliyochaguliwa kwenye GitHub Desktop.
3. GitHub Desktop: chagua **Repository → Show in Explorer**. Usifute repository yenyewe.
4. Kwenye File Explorer, washa **View → Show → Hidden items**. Ndani ya folder la repo, futa files/folders za zamani lakini **acha `.git` folder**. Usifute `.git` wala `.github` ya ZIP mpya.
5. Nakili **yaliyomo yote** ya folder ulilo-extract moja kwa moja ndani ya folder la repo. Jibu **Replace files** ikitokea. Hakikisha `.github/workflows/daily-analysis.yml`, `pipeline/`, `supabase/`, `index.html`, `config.js`, `package.json`, `android/` na `UPLOAD-TO-GITHUB.md` zipo.
6. Kwenye project root, fungua Command Prompt/Terminal na endesha offline tests:

   ```bash
   python -m unittest discover -s pipeline -p 'test_*.py'
   ```

   Vipimo hivi havitumii API keys wala kuita providers. Vikipita, rudi GitHub Desktop.

7. Kagua **Changes**: usikubali kufutwa kwa `.github/workflows/daily-analysis.yml`, `config.js`, au Android project. Weka commit message mfano `Add independent football evidence routes`, chagua **Commit to main**, kisha **Push origin**.
8. GitHub Actions secrets huhifadhiwa kwenye GitHub, si ndani ya ZIP; replacement ya files haiifuti. Kagua `THE_ODDS_API_KEY`, `API_SPORTS_KEY` (au majina ya API-Sports ya product maalum), `SUPABASE_URL`, na `SUPABASE_SERVICE_ROLE_KEY`. Usitume thamani za secrets kwenye chat au repository.

## B. Supabase na tovuti

- Kwa marekebisho haya **hakuna migration mpya**: evidence route na snapshot zinahifadhiwa kwenye JSONB iliyopo `analysis_fixtures.market_options`, na note ya prediction kwenye `daily_fixtures.analysis_note`.
- Ikiwa `migration_analysis_runs_fixture_board.sql` haijawahi kutumika kwenye project yako, iendeshe mara moja kabla ya run ili kuwe na run ledger na fixture board.
- Huhitaji ku-redeploy Edge Function wala kubadilisha daily-run guard kwa marekebisho haya ikiwa manual trigger na guard vinafanya kazi tayari. Hizi code files hazijabadilishwa.
- Ikiwa static host imeunganishwa na branch `main`, itajenga tovuti baada ya **Push origin**. Subiri deployment ikamilike kisha fungua app na ingia kwa akaunti iliyoidhinishwa.

## C. Android (hiari)

1. Baada ya kusasisha clone, double-click `BUILD-ANDROID.bat`.
2. Script itasakinisha dependencies, itajenga `www/`, itasawazisha web app kwenye Android project na kufungua Android Studio.
3. Android Studio ikimaliza Gradle Sync: chagua **Build → Build Bundle(s) / APK(s) → Build APK(s)**. APK ya majaribio iko `android/app/build/outputs/apk/debug/app-debug.apk`.

## D. Kukagua run ya kwanza

1. Tumia **Run analysis now** ndani ya app; usijaribu kupita daily guard. Guard huruhusu ombi kulingana na tarehe ya Tanzania (Africa/Dar_es_Salaam).
2. Kwenye **Fixture board**, fungua football fixture yenye quote. Kila market itaonyesha route iliyopita au sababu/threshold iliyokosekana, sample count, freshness ya odds na tarehe ya mechi za mwisho za stats.
3. Hakikisha schedule fixtures zinaonekana hata bila quote; usichukulie sifuri za picks kama mafanikio—soma coverage, join diagnostics na sababu za gate.
4. Hakuna live provider run iliyofanywa wakati wa kutengeneza mabadiliko haya. Unit tests ni offline; routes mpya hazina historical Odds API snapshots za kutosha kwa backtest ya kweli. Tathmini matokeo kwa mpangilio wa muda baada ya predictions kupata verified results. Alama ni heuristic, si probability iliyocalibrate wala ahadi ya ushindi.

## Usalama

Usifute repository kupitia **Settings → Delete repository**; unaweza kupoteza Actions secrets na settings. Repo ibaki **Private**. Usiweke API keys, Supabase service-role key, GitHub token, passwords au `.env` kwenye ZIP/repository/chat. `KIMATHY_GITHUB_TOKEN` ni secret ya Supabase Edge Function, si API key ya provider.
