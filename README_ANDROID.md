# Kimathy Daily Analysis — Android Studio build

Hii ni njia ya kufunga dashboard binafsi iliyopo kama Android app kupitia Capacitor. APK huonyesha dashboard ileile; uchambuzi na kuhifadhi matokeo bado hufanywa na Supabase/GitHub Actions server-side. Simu inahitaji intaneti.

## Kile kilichoongezwa

- `package.json` na `package-lock.json`: Capacitor dependencies zilizofungwa kwa matoleo maalum.
- `capacitor.config.json`: jina la app `Kimathy Daily Analysis` na package ID mpya `com.kimathy.dailyanalysis`.
- `scripts/build-web.mjs`: huweka `index.html` na `config.js` tu ndani ya `www/` kwa ajili ya Android.
- `android/`: mradi wa Android Studio uliotengenezwa na Capacitor.
- `BUILD-ANDROID.bat`: huangalia Node.js, huweka dependencies, hujenga bundle, husawazisha Android, kisha hufungua Android Studio.
- `supabase/` na pipeline zipo kwenye kifurushi kama kumbukumbu ya backend. Ili limit mpya ya mara moja kwa tarehe (EAT) ianze kufanya kazi, endesha tena `supabase/migration_manual_run_guard.sql` na deploy Edge Function iliyosasishwa; APK peke yake haiwezi kubadilisha guard ya server.

## Mahitaji kwenye Windows

1. Node.js **22.12 au mpya zaidi** (22 LTS inapendekezwa; Capacitor CLI ya sasa inahitaji Node 22).
2. Android Studio iliyosakinishwa pamoja na Android SDK. Tumia JDK iliyokuja na Android Studio.
3. Intaneti kwa npm na Gradle Sync ya mara ya kwanza.

## Tengeneza debug APK

1. Pakua na **extract** ZIP nzima kwenye folda ya kawaida ya kompyuta (si ndani ya ZIP yenyewe).
2. Double-click `BUILD-ANDROID.bat`.
3. Ikikamilika, subiri **Gradle Sync** ndani ya Android Studio imalize.
4. Android Studio: **Build → Build Bundle(s) / APK(s) → Build APK(s)**.
5. Debug APK itatoka hapa:

   `android\app\build\outputs\apk\debug\app-debug.apk`

6. Hamisha APK hiyo kwenda simu yako na uisakinishe. Android inaweza kukuomba uruhusu kusakinisha app kutoka chanzo hicho.

Debug APK imesainiwa kwa debug key ya kompyuta yako, inafaa kwa majaribio binafsi. Kwa release APK au Play Store, tumia Android Studio kuunda signing key mpya kwa app hii na ihifadhi kwa usalama kwenye kompyuta/backup yako. **Usiweke keystore, password au alias ndani ya ZIP, GitHub, au chat.** Kwa kuwa umechagua app mpya, package ID yake ni mpya; haitafanya upgrade ya app nyingine yenye package ID tofauti.

## Supabase na usalama

- Ingia kwa **Supabase Auth identity ileile iliyo allowlist**; public registration haifunguliwi.
- App hutumia Supabase URL na **publishable key** iliyo `config.js`. Publishable key inaweza kuwepo kwenye app ya mteja; RLS na user allowlist ndizo hulinda data.
- `service_role`/`sb_secret`, API-Sports key, Odds API key na `KIMATHY_GITHUB_TOKEN` **havimo kwenye Android app**. Hubaki kwenye GitHub Actions Secrets au Supabase Edge Function Secrets kama zilivyo sasa.
- Kitufe cha **Run analysis now** bado hutumia Supabase Edge Function na GitHub workflow; kinaheshimu workflow ya manual na kikomo cha ombi moja kwa tarehe ya Tanzania (EAT; hufunguka upya saa 00:00). Hakuna provider request inayotumwa app inapofunguliwa tu.
- Kubonyeza run kunaweza kutumia hadi **22 Odds API market credits**. Usiendeshe ikiwa hutaki kutumia credits kwa sasa; run inaweza pia kuishia bila ticket pale ushahidi hautoshi.

## GitHub workflow

ZIP kamili ya repo **inajumuisha `.github/workflows/daily-analysis.yml`** ili workflow ya manual iende pamoja na code. Workflow ina majina ya secrets tu, si thamani zake. Badilisha files za repo bila kufuta repository/settings; Android app haitahitaji kuhamisha API keys kutoka GitHub/Supabase kwenda simu.

## Msaada wa haraka

- Ikiwa `BUILD-ANDROID.bat` inasema Node haipo au ni ya zamani, sakinisha Node.js 22 LTS kisha fungua terminal/folda upya.
- Ikiwa Android Studio haifunguki, fungua Android Studio mwenyewe na uchague **Open**, kisha chagua folda `android/` ndani ya mradi uli-extract.
- Ikiwa login inaonyesha config warning, hakikisha `config.js` ipo pamoja na `index.html` kwenye root ya mradi na unaunganisha intaneti.
- Tuma tu maandishi ya hitilafu yasiyo na email/private data. Usitume passwords, API keys, tokens, au keystore.
