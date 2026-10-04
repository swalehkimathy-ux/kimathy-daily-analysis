# Chanzo cha data kinachofaa kwa Kimathy

**Imekaguliwa: 4 Oktoba 2026.** Lengo ni kusasisha mara moja kwa siku (08:30 EAT) kwa football, basketball na tennis. Kiunganishi cha The Odds API v4 na enrichment ya API-Sports kwa football/basketball vimeongezwa kwenye pipeline. Hakuna live request iliyofanywa: API keys hazijawekwa kwenye runner. Tennis bado haina chanzo cha ranking/surface kilichounganishwa.

## Vyanzo vya kuanzia

| Chanzo | Kinafaa kwa | Masharti / mipaka | Mapendekezo |
|---|---|---|---|
| [The Odds API](https://the-odds-api.com/) | Fixtures, muda wa kuanza na bookmaker odds za sports mbalimbali kupitia API rasmi | Starter plan ina credits 500 kwa mwezi. Tennis coverage yake ni hasa Grand Slams, ATP/WTA 1000 na 500; hasa odds za match-winner. Regions zilizoandikwa ni US, UK, EU na Australia; user amekubali international odds ikiwa confidence inatosha, na connector default ni EU. Masharti yanaruhusu kutumia data ndani ya app/dashboard, lakini si kuiuza tena kama raw data feed. Haina kwa yenyewe taarifa za kina za form, rankings au surface. | **Kiunganishi kimeandikwa** kwa `/v4/sports` na `/v4/sports/{sport}/odds`; hutumia one-region requests, huchagua active keys kwa caps za 4 soccer / 2 basketball / 2 tennis, na huangalia quota headers. Max ya kawaida ni hadi takriban credits 12/run (hadi 360 kwa siku 30; manual runs huongeza). Odds-only records hazipati pick mpaka stat/form evidence itolewe. [Pricing](https://the-odds-api.com/) · [API docs](https://the-odds-api.com/liveapi/guides/v4/) · [Tennis coverage](https://the-odds-api.com/sports/tennis-odds.html) · [Terms](https://the-odds-api.com/terms-and-conditions.html) |
| [TheSportsDB](https://www.thesportsdb.com/) | Ratiba, event/team/player metadata na baadhi ya results kwenye sports mbalimbali | Masharti yake yanaruhusu kutumia data inayorudishwa na **API yake rasmi**, lakini yanasema usiscrape website yenyewe. Free plan ina queries/returns chache na haina bookmaker odds. | **Supplement ya fixtures/metadata tu**; si chanzo cha odds. [API guide](https://www.thesportsdb.com/docs_api_guide) · [Terms](https://www.thesportsdb.com/docs_terms_of_use.php) |
| [API-SPORTS](https://api-sports.io/) | Football fixtures, standings na head-to-head; basketball schedule na team game history | Free plan ina requests 100 kwa siku kwa kila API; upatikanaji hutofautiana kwa competition. Orodha yao ya APIs iliyochapishwa haionyeshi tennis. Terms zinakataza resale na zinaonya kuwa baadhi ya matumizi/uchapishaji yanaweza kuhitaji ruhusa za ziada. | **Connector imeandikwa** kwa API-Football v3 na API-Basketball v1, inaangalia status/quota, inaweka cap ya requests na inaacha ushahidi ukikosekana. [Football docs](https://api-sports.io/documentation/football/v3) · [Basketball docs](https://api-sports.io/documentation/basketball/v1) · [Coverage](https://api-sports.io/sports/football) · [Basketball coverage](https://api-sports.io/sports/basketball) · [Terms](https://api-sports.io/terms) |
| [football-data.org](https://www.football-data.org/documentation/api) | Football fixtures, results na competition data | Football pekee; free plan inahitaji account/token na app inapaswa kuweka attribution inayoonekana. | Chanzo cha ziada cha football, si odds feed ya sports zote. [API limits](https://www.football-data.org/documentation/api) · [Attribution FAQ](https://www.football-data.org/documentation/faq) |

## Sources ulizotaja

- [Flashscore terms](https://www.livesport.eu/terms/flashscore_ae/) zinasema kunakili/kutumia maudhui kunahitaji ruhusa ya maandishi. Sitaiunganisha kama scraper bila ruhusa hiyo.
- [Forebet terms](https://www.forebet.com/en/terms-of-use) zinalinda predictions na content yake na zinakataza kunakili au kuitumia bila ruhusa.
- [Statarea terms](https://www.statarea.com/help/terms) zinaweka mipaka ya matumizi/kueneza tena taarifa, hasa zilizolipiwa. Tunahitaji uthibitisho wa ruhusa kabla ya automated collection.
- Football Whispers huchapisha tips/predictions; tip si sawa na bookmaker odds. Sitaiunganisha kama scraper bila masharti/ruhusa ya automated use yaliyo wazi.
- Kwa tennis, masharti ya ATP yanakataza systematic collection ya scores, stats na rankings kwa ajili ya database bila ruhusa ya maandishi; pia yanazuia matumizi ya gambling bila ruhusa hiyo. Kwa hiyo hatutascrape ranking page moja kwa moja. [ATP Terms](https://www.atptour.com/en/terms-and-conditions)

**Muhimu:** kuendesha scraper mara moja kwa siku kunapunguza maombi, lakini hakubadilishi masharti ya matumizi ya chanzo. Hatutatumia login, CAPTCHA/proxy bypass, private endpoints, au kuendelea kupiga requests baada ya 403/429.

## Mpango wa engine na mipaka ya ushahidi

1. The Odds API ndiyo odds feed ya msingi; default bookmaker region ni `eu`, market requests ni limited, na quota huangaliwa kila run.
2. API-Sports v3/v1 inatafutwa kwa fixtures za siku husika. Football standings hutumika tu ikiwa mechi imeunganishwa kwa team IDs, timu zote zimecheza angalau mechi 5, na table ina angalau timu 10. Flag ya high-goal hutumia head-to-head 5 za mwisho, inahitaji 4/5 kuwa na mabao 3+.
3. Basketball home win rate hutumia hadi mechi 10 za nyumbani zilizokamilika hivi karibuni (angalau 5); losing streak ya away hutumia mechi zilizokamilika na inahitaji sample ya away ya angalau 5. Tofauti za majina, ratiba zisizolingana, coverage isiyopo, au quota ndogo husababisha enrichment/pick kurukwa.
4. Tennis bado haina chanzo cha ranking/surface kinachofaa. Hakuna tennis pick inayotengenezwa na Odds API peke yake.
5. Tenganisha **odds halisi** na **predictions**. Kila record ihifadhi source na muda ilipopatikana; usisambaze raw provider data hadharani bila ruhusa.
6. Ratiba ya kila siku ni 05:30 UTC (08:30 EAT). Ikiwa source haina data ya kutosha au odds zimepitwa na wakati, engine isitengeneze pick.
