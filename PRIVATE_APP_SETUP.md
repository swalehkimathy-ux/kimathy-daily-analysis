# Hatua za kuweka Kimathy Daily Analysis (kwa matumizi binafsi)

Mabadiliko ya app yameandaliwa. Hatua zinazobadilisha akaunti lazima uzifanye ndani ya Supabase/GitHub yako. **Usitume API key, password, GitHub token, au service-role key hapa kwenye chat.** Tutafanya hatua moja kwa wakati.

## Kazi ya mara moja: Supabase

1. Fungua project yako ya Supabase → **SQL Editor → New query**. Kama `migration_private_dashboard.sql` haikuendeshwa bado, iendeshe kwanza. Kama ilishaendeshwa, endelea na guard mpya iliyoelezwa hapa chini.
2. Fungua faili `supabase/migration_manual_run_guard.sql` kutoka kifurushi kipya, nakili SQL yote na uiendeshe baada ya migration ya private dashboard. Hii huweka/hu-update kikomo cha seva: ombi moja kwa tarehe ya Tanzania (EAT), kikifunguka upya saa 00:00. Kwa hiyo run kabla na baada ya usiku wa manane inaweza kuwa chini ya saa 24 tofauti na kutumia hadi credits 44 kwa jumla katika run hizo mbili (kikomo cha credits 22 kwa kila run kinabaki).
3. Hakikisha una Supabase Auth user wa kuingia kwenye app na umeidhinisha email yake kwa SQL ya allowlist. Usajili wa umma uzimwe.

## Kubadilisha files za repo kwa kifurushi kipya

Tumia `kimathy-daily-analysis-full-repo.zip`. Ina code yote ya repo pamoja na `.github/workflows/daily-analysis.yml`, lakini haina `node_modules`, build files, `.git`, wala siri/API keys.

1. Pakua na extract ZIP kwenye folder tofauti.
2. Fungua GitHub Desktop, clone repo ya sasa `swalehkimathy-ux/kimathy-daily-analysis` (au tumia clone uliopo), kisha chagua **Show in Explorer**.
3. Fanya backup ya folder la clone. Ndani ya clone, onyesha hidden files kisha futa files/folders za zamani **isipokuwa `.git`**. Usifute repository yenyewe wala kubadili Private/settings.
4. Nakili yaliyomo ndani ya folder ulilo-extract kwenda kwenye clone. Hakikisha `.github/workflows/daily-analysis.yml` imenakiliwa pia. ZIP haina token au provider keys; GitHub Actions secrets zilizohifadhiwa kwenye settings ya repo zitabaki kwa sababu repo haijafutwa.
5. GitHub Desktop: kagua mabadiliko, commit kwa `main`, kisha **Push origin**. Repo ibaki **Private**.

## Kuwezesha kitufe cha app

Baada ya code kusukumwa GitHub:

1. Supabase project → **Edge Functions → Deploy a new function → Via Editor**. Taja `trigger-analysis`, kisha fungua `supabase/functions/trigger-analysis/index.ts` kwenye ZIP na unakili code yote kwenye editor. Acha **Verify JWT** imewashwa, kisha **Deploy function**.
2. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens**. Tengeneza token inayoruhusiwa kwa repository moja tu: `swalehkimathy-ux/kimathy-daily-analysis`. Ruhusa inayohitajika ni **Repository permissions → Actions → Read and write**. Weka muda mfupi wa expiry unaokufaa.
3. Nakili token hiyo mara moja na uiweke Supabase → **Edge Functions → Secrets** kwa jina `KIMATHY_GITHUB_TOKEN`. Thamani hiyo hubaki Supabase server-side; usiiweke kwenye `config.js`, faili la app, GitHub Actions secrets, au chat. Baada ya kuihifadhi, usiitumie tena kwenye ujumbe.

Kumbuka: token kuonekana **active** kunamaanisha haija-expire/kufutwa tu; hakuthibitishi ruhusa. Lazima iwe na access ya repository hiyo na **Actions: Read and write**, na workflow `daily-analysis.yml` iwe enabled kwenye `main` ikiwa na `workflow_dispatch`. Ujumbe wa app sasa utaonyesha namba ya HTTP pekee (bila response body/token) ili tujue kama ni 401, 403, 404 au 422. Usinitumie token yenyewe.

Kitufe cha **Run analysis now** kitaonekana baada ya kuingia. Kufungua app au kubonyeza refresh ya data husoma tu Supabase; havianzishi The Odds API/API-Sports. Kubonyeza kitufe na kuthibitisha ndipo huomba GitHub Actions ianze run. Kikomo cha ombi moja kwa tarehe ya Tanzania kinawekwa Supabase, si JavaScript ya browser, na pipeline hukagua tena kabla ya kuita data providers. Run inaweza kutumia hadi takriban 22 market credits za The Odds API (header za provider ndizo za mwisho); API-Sports inaweza kutumia quota yake tofauti. Vigezo vya ushahidi havipunguzwi na app haitalazimisha pick.

## Hosting na uthibitisho

App inahitaji static HTTPS host ili ifunguke kwenye simu/kompyuta nje ya local machine. Baada ya Push origin, host yako inaweza kuchukua `index.html`/`config.js` mpya. Ingia kwa Supabase email/password. Kitufe kitabaki kimezimwa ikiwa SQL guard, Edge Function, au daily-limit status haijasanidiwa kikamilifu—hiyo ni salama.

Ukiwa unataka kujaribu, tumia **Run analysis now** ndani ya app na uangalie GitHub → **Actions** kwa workflow `Kimathy manual analysis`. Run za moja kwa moja kutoka GitHub pia hukaguliwa na guard ya siku ya kalenda (EAT). Chagua `confirm_requests=true` tu pale unapoanzisha mwenyewe; default yake inabaki `false`.

## Usalama

- API-Sports na The Odds API keys hubaki kwenye GitHub Actions Secrets zilizopo: `API_SPORTS_KEY` na `THE_ODDS_API_KEY`.
- `SUPABASE_URL` na `SUPABASE_SERVICE_ROLE_KEY` hubaki GitHub Actions server-side; Supabase pia huweka key ya admin kwa Edge Function server-side. Usiiweke kwenye browser.
- GitHub fine-grained token huwekwa Edge Function Secrets tu kama `KIMATHY_GITHUB_TOKEN`.
- Usishiriki screenshot yenye key/token, password, au data ya binafsi. Ukihitaji msaada, tuma screenshot isiyo na siri.
