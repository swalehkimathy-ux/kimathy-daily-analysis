# Kubadilisha files za repo kwa kifurushi kipya

Kifurushi kamili ni `kimathy-daily-analysis-full-repo.zip`. Yaliyomo yako moja kwa moja kwenye root ya ZIP (hakuna folder la ziada la kuingia kwanza). Kimejumuisha `.github/workflows/daily-analysis.yml`, pipeline, Supabase files, dashboard, na Android Studio project. Hakina token/API-key values, `.git`, `node_modules`, `www/`, au build output.

## Kabla ya kuanza

- Usifute repository yenyewe kupitia **Settings → Delete repository**. Badilisha files tu; ukifuta repo nzima unaweza kupoteza Actions secrets/settings.
- Hakikisha repository inaendelea kuwa **Private**.
- Hifadhi nakala ya folder lako la clone la sasa kabla ya kubadilisha files.

## Hatua (GitHub Desktop, Windows)

1. Pakua ZIP hii na **Extract All** kwenye folder tofauti.
2. GitHub Desktop: chagua repo `swalehkimathy-ux/kimathy-daily-analysis` kisha **Repository → Show in Explorer**.
3. Katika Explorer, washa **View → Show → Hidden items**. Ndani ya folder la repo, futa files/folders za zamani lakini **acha `.git` folder**. Usifute folder la repo.
4. Nakili yaliyomo yote kutoka kwenye folder ulilo-extract kwenda kwenye folder la repo. Jibu **Replace files** inapoulizwa. Hakikisha `.github/workflows/daily-analysis.yml` imenakiliwa.
5. GitHub Desktop itaonyesha additions/changes/deletions. Kagua kwamba `.gitignore`, `pipeline/`, `supabase/`, `.github/workflows/`, `index.html`, `config.js`, na `android/` zipo. Commit kwa branch `main`, kisha bonyeza **Push origin**.

## Baada ya push

1. Supabase SQL Editor: endesha `supabase/migration_manual_run_guard.sql` iliyosasishwa (inaweza kuendeshwa tena; inabadilisha guard kuwa mara moja kwa tarehe ya Tanzania/EAT).
2. Kisha endesha `supabase/migration_analysis_runs_fixture_board.sql` ili kuunda run history na full fixture board yenye RLS ya owner pekee. Usibonyeze **Run analysis now** kabla migration hii haijaisha.
3. Supabase **Edge Functions**: redeploy `supabase/functions/trigger-analysis/index.ts` na **Verify JWT** ikiwa imewashwa; hii inapeleka muda wa request kutoka server hadi workflow.
4. Hakikisha GitHub Actions workflow mpya ipo kwenye `main`; app mpya itaonyesha coverage board baada ya run inayofuata. Kama unatumia Android app, tumia `BUILD-ANDROID.bat`, jenga debug APK ndani ya Android Studio, kisha sakinisha build mpya. Static site itajisasisha kupitia hosting yake baada ya push ikiwa host imeunganishwa na branch `main`.

Usitume GitHub token, Supabase service-role key, API key, au password hapa. Workflow ina marejeo ya GitHub Actions secrets tu; haihifadhi thamani zake.
