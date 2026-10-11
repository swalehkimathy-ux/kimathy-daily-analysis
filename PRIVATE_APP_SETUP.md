# Hatua za kuweka Kimathy Daily Analysis (kwa matumizi binafsi)

Mabadiliko ya app yameandaliwa. Hatua zinazobadilisha akaunti lazima uzifanye ndani ya Supabase/GitHub yako. **Usitume API key, password, GitHub token, au service-role key hapa kwenye chat.** Tutafanya hatua moja kwa wakati.

## Kazi ya mara moja: Supabase

1. Fungua project yako ya Supabase → **SQL Editor → New query**. Kama `migration_private_dashboard.sql` haikuendeshwa bado, iendeshe kwanza. Kama ilishaendeshwa, usiirudie bila sababu.
2. Fungua faili `supabase/migration_manual_run_guard.sql` kutoka kifurushi kipya, nakili SQL yote na uiendeshe baada ya migration ya private dashboard. Hii huweka kikomo cha seva: ombi moja kwa kila saa 24 zinazozunguka.
3. Hakikisha una Supabase Auth user wa kuingia kwenye app na umeidhinisha email yake kwa SQL ya allowlist. Usajili wa umma uzimwe.

## Kuweka app/pipeline code GitHub bila terminal

1. Pakua na fungua `kimathy-daily-analysis.zip` kwenye kompyuta.
2. Fungua GitHub Desktop, clone repository yako iliyopo `swalehkimathy-ux/kimathy-daily-analysis` (ikiwa tayari ume-clone, tumia folder hilo).
3. Nakili files/folders zilizo ndani ya ZIP na uzibandike kwenye folder la repo; ruhusu kubadilisha files za zamani. ZIP haijumuishi `.github`, kwa makusudi—**usiifute wala ku-upload tena `.github` iliyopo**.
4. GitHub Desktop: kagua mabadiliko, andika ujumbe mfupi kama `Add manual app trigger`, bonyeza **Commit to main**, kisha **Push origin**. Workflow iliyopo `daily-analysis.yml` ibaki kama ilivyo; ni manual-only.

## Kuwezesha kitufe cha app

Baada ya code kusukumwa GitHub:

1. Supabase project → **Edge Functions → Deploy a new function → Via Editor**. Taja `trigger-analysis`, kisha fungua `supabase/functions/trigger-analysis/index.ts` kwenye ZIP na unakili code yote kwenye editor. Acha **Verify JWT** imewashwa, kisha **Deploy function**.
2. GitHub → **Settings → Developer settings → Personal access tokens → Fine-grained tokens**. Tengeneza token inayoruhusiwa kwa repository moja tu: `swalehkimathy-ux/kimathy-daily-analysis`. Ruhusa inayohitajika ni **Repository permissions → Actions → Read and write**. Weka muda mfupi wa expiry unaokufaa.
3. Nakili token hiyo mara moja na uiweke Supabase → **Edge Functions → Secrets** kwa jina `KIMATHY_GITHUB_TOKEN`. Thamani hiyo hubaki Supabase server-side; usiiweke kwenye `config.js`, faili la app, GitHub Actions secrets, au chat. Baada ya kuihifadhi, usiitumie tena kwenye ujumbe.

Kitufe cha **Run analysis now** kitaonekana baada ya kuingia. Kufungua app au kubonyeza refresh ya data husoma tu Supabase; havianzishi The Odds API/API-Sports. Kubonyeza kitufe na kuthibitisha ndipo huomba GitHub Actions ianze run. Kikomo cha saa 24 kinawekwa Supabase, si JavaScript ya browser, na pipeline hukagua tena kabla ya kuita data providers. Run inaweza kutumia hadi takriban 22 market credits za The Odds API (header za provider ndizo za mwisho); API-Sports inaweza kutumia quota yake tofauti. Vigezo vya ushahidi havipunguzwi na app haitalazimisha pick.

## Hosting na uthibitisho

App inahitaji static HTTPS host ili ifunguke kwenye simu/kompyuta nje ya local machine. Baada ya Push origin, host yako inaweza kuchukua `index.html`/`config.js` mpya. Ingia kwa Supabase email/password. Kitufe kitabaki kimezimwa ikiwa SQL guard, Edge Function, au cooldown status haijasanidiwa kikamilifu—hiyo ni salama.

Ukiwa unataka kujaribu, tumia **Run analysis now** ndani ya app na uangalie GitHub → **Actions** kwa workflow `Kimathy manual analysis`. Run za moja kwa moja kutoka GitHub pia hukaguliwa na cooldown ya server. Chagua `confirm_requests=true` tu pale unapoanzisha mwenyewe; default yake inabaki `false`.

## Usalama

- API-Sports na The Odds API keys hubaki kwenye GitHub Actions Secrets zilizopo: `API_SPORTS_KEY` na `THE_ODDS_API_KEY`.
- `SUPABASE_URL` na `SUPABASE_SERVICE_ROLE_KEY` hubaki GitHub Actions server-side; Supabase pia huweka key ya admin kwa Edge Function server-side. Usiiweke kwenye browser.
- GitHub fine-grained token huwekwa Edge Function Secrets tu kama `KIMATHY_GITHUB_TOKEN`.
- Usishiriki screenshot yenye key/token, password, au data ya binafsi. Ukihitaji msaada, tuma screenshot isiyo na siri.
