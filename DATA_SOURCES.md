# Chanzo cha data kinachofaa kwa Kimathy

**Imesasishwa: 11 Oktoba 2026.** App haina ratiba ya automatic: run huanzishwa kwa kubonyeza kitufe, na ombi moja tu huruhusiwa ndani ya kila rolling saa 24. Lengo ni **angalau accumulators 20 zilizoshinda kwa mwezi**, si tiketi 20 tu zilizotolewa; hili ni lengo tu, si ahadi. Run inaweza kutoa hakuna ticket ikiwa odds au ushahidi wa takwimu hautoshi—hakuna pick inayolazimishwa. Ticket moja inalenga odds jumla **1.50 hadi chini ya 1.90**.

## Chanzo cha odds na stats

| Chanzo | Kinachotumika | Mipaka muhimu | Uamuzi wa sasa |
|---|---|---|---|
| [The Odds API](https://the-odds-api.com/) | Odds za bookmaker kupitia API rasmi; default region ni EU. | Credits hutumika kulingana na markets na regions zilizoombwa. Free allowance inaweza kubadilika; connector husoma headers za quota. Coverage ya market/bookmaker hutofautiana kwa ligi. Soccer `spreads` ya source ni two-way point spread, si European 3-way handicap; haijabadilishwa jina wala kukisia `h2h_3_way`. | Connector inachagua hadi competitions 10 (soccer 8 na basketball 2). Markets mbili za soccer huzunguka kwa ligi/siku kati ya totals, BTTS, double chance, h2h (1X2) na `spreads`; basketball huomba h2h, totals na spreads. Hard cap, ikijumuisha retries, ni **22 market credits/run** kwa region moja (16 soccer + 6 basketball chini ya full plan). |
| [API-Sports / API-Football](https://api-sports.io/) | Football fixtures, standings, head-to-head, recent team scorelines na matokeo ya final. | Free plan iliyoonyeshwa na provider: hadi requests 100/siku kwa kila API; coverage hutegemea ligi/season. Baadhi ya matumizi au uchapishaji vinaweza kuhitaji ruhusa za ziada. | Hutumika kuoanisha mechi; totals/spreads zinahitaji H2H 5 na hutumia pia form ya mechi 5 za hivi karibuni kwa kila timu pale data ipo; standings hutumika kwa double chance. Matokeo ya zamani husettled pale fixture/final score vinapolingana. |
| [API-Sports / API-Basketball](https://api-sports.io/) | Ratiba, game history na score za basketball. | Coverage hutofautiana kwa ligi. Hii ni data ya stats/results, si odds za bookmaker. | Hutumika kwa home moneyline, totals, handicap na settlement pale data ya game ipo. |
| [TheSportsDB](https://www.thesportsdb.com/) | Metadata/ratiba na baadhi ya matokeo kupitia API yake rasmi. | Haina bookmaker odds; free plan/coverage ni chache. Terms zinasema tumia API rasmi, si kuscrape tovuti. | Haijaunganishwa kwa picks; inaweza kutathminiwa kama supplement ya ratiba pekee. |
| [football-data.org](https://www.football-data.org/documentation/api) | Ratiba, results na competition data ya football. | Football pekee; free plan inahitaji account/token na attribution. | Haijaunganishwa kwa sasa. API-Sports ndiyo stats/results source inayotumika. |
| [BBC Sport RSS](https://support.bbc.co.uk/platform/feeds/SportFeeds.htm) | Headlines/previews za football na basketball kupitia RSS rasmi. | Coverage si ya kila ligi/mechi; attribution ya BBC Sport inahitajika na alama/logo za BBC hazitumiki. | Context pekee: headline/link na keyword tags; haibadili eligibility wala ranking. |
| [ESPN RSS](https://www.espn.com/espn/news/story?id=3437834) | Headlines na summaries za soccer na NBA kutoka RSS rasmi. | Lazima ihifadhi headline/URL kama zilivyo na attribution; hakuna matangazo ndani ya ESPN RSS content. | Context pekee, si ushahidi wa takwimu wala utabiri. |

## Maoni/news kupitia RSS (context tu)

Pipeline husoma feeds nne mara moja kila run: BBC Sport Football, BBC Sport Basketball, ESPN Soccer na ESPN NBA. Huchuja items za saa 72 zilizopita, zilizochapishwa kabla ya kickoff, na huambatanisha item tu ikiwa majina ya timu zote mbili yana-match kwenye title/summary. Huhifadhi source, headline ya asili na link; full article text/summary haihifadhiwi. Link/attribution huonekana kwenye `analysis_note` ya fixture. Keyword topic/tone ni annotation ya ndani, si maoni rasmi ya publisher.

Hii si AI sentiment model: keyword tags zinaweza kukosea muktadha. RSS signal haiingii kwenye evidence gate, score/ranking, odds au uamuzi wa accumulator. Candidate isiyo na verified market-specific stats haiwezi kupita kwa sababu ya RSS. Feed ikikataa request au haipatikani, inarukwa bila retry/bypass. BBC feed hutumia attribution kama inavyoelekezwa kwenye [mwongozo wa RSS wa BBC Sport](https://www.bbc.com/sport/articles/cqllxj2n4kyo). ESPN RSS hutumia URL na headline ya feed kama zilivyo na attribution kulingana na [RSS terms za ESPN](https://www.espn.com/espn/news/story?id=3437834), bila matangazo. The Guardian haijaunganishwa kwenye automation: [terms zake](https://www.theguardian.com/help/terms-of-service) pia zinakataza automated reading pamoja na content analysis/data mining bila idhini ya maandishi; hakuna Guardian feed/page inayotumiwa hapa. Coverage ya ligi/mechi zote haijahakikishwa.

## Markets zinazounganishwa sasa

- **Football:** totals Over/Under 0.5, 1.5 au 2.5; BTTS Yes/No; double chance **Home or Draw (1X)**; direct 1X2 (home win, draw, away win); na **two-way soccer spread** yenye upande/line iliyochukuliwa kutoka `spreads`. Market name huiweka wazi kuwa ni two-way; European 3-way handicap haijaunganishwa kwa sababu source iliyopo haijaithibitisha. Quarter-lines hazichukuliwi. Direct 1X2 inahitaji quote ya kweli yenye outcomes zote tatu; odds ziwe 1.05–1.80 na angalau 4 kati ya H2H 5 ziunge mkono outcome iliyochaguliwa.
- **Basketball:** home moneyline, totals Over/Under kwa line halisi, na handicap/spread kwa upande na line halisi.
- **Tennis:** imezimwa kwa muda kwenye odds requests kwa sababu hatuna stats source inayokubalika ya ranking/surface/form. Odds peke yake hazitoshi.
- **Corners, cards na cricket:** hazijaunganishwa. Coverage ya odds pamoja na stats za market hizo haijathibitishwa.

## Vigezo vya ushahidi

1. **Football 1X:** standings ziwe kamili (angalau timu 10), timu zote mbili ziwe na angalau mechi 5 za ligi, nyumbani iwe top 3 na ugenini iwe bottom 5.
2. **Football direct 1X2:** kwenye H2H 5 zilizokamilika, angalau 4 ziwe na outcome ileile ya matokeo yaliyonukuliwa (home win, draw au away win); odds lazima ziwe ndani ya 1.05–1.80.
3. **Football totals:** mechi 5 zilizokamilika za head-to-head; angalau 4 kati ya 5 zilingane na line na direction inayochaguliwa. Pia timu zote mbili zihitaji scorelines 5 za hivi karibuni; direction iliyochaguliwa iwe na wastani wa hit rate angalau 60% kati ya samples mbili na hakuna timu iliyo chini ya 40%.
4. **Football two-way spread:** line kamili ya whole/half-goal, H2H 5 zilizokamilika na angalau 4 covers kwa upande uliochaguliwa. Kila timu ihitaji form ya mechi 5: selected side cover rate angalau 70%, opponent cover rate isizidi 30% kwenye line iliyoakisiwa. Hii si European 3-way handicap.
5. **Football BTTS:** mechi 5 za head-to-head; angalau 4 kati ya 5 zilingane na Yes au No.
6. **Basketball moneyline:** home team iwe na angalau mechi 5 za hivi karibuni nyumbani na win rate angalau 80%; opponent awe na sample ya angalau mechi 5 za ugenini na losing streak ya sasa ya angalau 5.
7. **Basketball totals:** sample ya angalau mechi 5 kwa home team nyumbani na away team ugenini; kila sample iwe na hit rate angalau 70% kwenye line/direction hiyo hiyo.
8. **Basketball handicap:** angalau mechi 5 kwa kila sample inayotumika; selected side iwe na cover rate angalau 70% na upande pinzani usizidi 30% kwenye handicap line hiyo.
9. Ticket haiwezi kuweka markets mbili kutoka mechi moja. Ikiwa stats zimekosekana, majina/muda havilingani au fixture ni ambiguous, pick inakataliwa.

Hizi ni vigezo vya kuchuja, si ushahidi wa uhakika kwamba pick itashinda. Alama 0–100 ni ranking heuristic, si probability iliyocalibrate.

## Matumizi ya credits na requests

- The Odds API huomba region moja (`eu`) na hadi competitions 10: soccer 8 kwa markets 2 kila moja, pamoja na basketball 2 kwa markets 3 kila moja. Hard cap ya credits **22/run** inajumuisha retries; allowance ya 500 inaunga mkono hadi takriban 22 full runs bila retries/gharama nyingine. Connector husoma quota iliyobaki na hupunguza au kusimamisha maombi ikiwa credits hazitoshi.
- API-Sports enrichment ina cap ya hadi requests 60 kwa product kwa run; settlement ya matokeo ina cap tofauti ya hadi requests 20 kwa product. Status/quota hukaguliwa na request moja hubaki akiba. Idadi halisi hutegemea games na past fixtures.
- Spread imeingizwa kwenye mzunguko wa markets mbili za soccer kwa competition; haiongezi idadi ya market slots wala hard cap ya 22. Matokeo yake, frequency ya kila market family inategemea rotation na idadi ya ligi zinazopatikana.

## Result tracking

API-Sports hutafuta final scores za football na basketball kwa fixtures za hadi siku 7 zilizopita. Result huandikwa tu pale timu, muda/fixture na market vinaweza kulinganishwa. Mechi isiyolingana, iliyocheleweshwa, au isiyo na score ya mwisho hubaki **pending**—hakuna matokeo yanayokadiriwa.

Dashboard inaonyesha win rate na “paper ROI” kwa dhana ya stake ya unit moja kwa kila accumulator. Hizo si stakes halisi, profit halisi wala forecast. Void legs hushughulikiwa kama push; tickets zenye leg moja iliyopoteza huhesabiwa loss.

## Matumizi ya tovuti na masharti

- [Flashscore terms](https://www.livesport.eu/terms/flashscore_ae/) zinahitaji ruhusa kwa matumizi/kunakili maudhui; hatuendeshi scraper bila ruhusa hiyo.
- [Forebet terms](https://www.forebet.com/en/terms-of-use) zinalinda predictions na content; hatuzi-copy kama chanzo cha stats/odds.
- [Statarea terms](https://www.statarea.com/help/terms) zinaweka mipaka ya matumizi na usambazaji; hakuna automated collection bila ruhusa iliyothibitishwa.
- Football Whispers tips si bookmaker odds; hakuna scraper iliyounganishwa.
- Hatutumii login/CAPTCHA/proxy bypass, private endpoints, wala kuendelea kupiga requests baada ya 403/429.

**Live-test ya awali (toleo kabla ya upanuzi huu):** The Odds API ilirudisha events 144 na odds candidates 13, ikitumia credits 12 na kuripoti 488 zilizobaki. API-Sports ilifanya schedule call moja ya basketball lakini haiku-match candidate; hakuna candidate iliyokuwa na ushahidi wa stats, hivyo hakuna ticket iliyotengenezwa. Mabadiliko ya matching diagnostics na markets hapo juu bado yanahitaji kuthibitishwa kwenye run yako inayofuata; offline mock tests haziwezi kuthibitisha coverage ya account yako.
