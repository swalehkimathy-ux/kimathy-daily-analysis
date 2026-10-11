# Chanzo cha data kinachofaa kwa Kimathy

**Imesasishwa: 4 Oktoba 2026.** Mfumo unaendeshwa mara moja kwa siku (08:30 EAT) na lengo ni **angalau accumulators 20 zilizoshinda kwa mwezi**, si tiketi 20 tu zilizotolewa. Hili ni lengo tu, si ahadi; matokeo hayawezi kuhakikishwa. App itajaribu kutoa ticket kila siku yenye mechi, odds na ushahidi wa takwimu unaotosha; haitalazimisha pick data inapokosekana. Ticket moja inalenga odds jumla **1.50 hadi chini ya 1.90**.

## Chanzo cha odds na stats

| Chanzo | Kinachotumika | Mipaka muhimu | Uamuzi wa sasa |
|---|---|---|---|
| [The Odds API](https://the-odds-api.com/) | Odds za bookmaker kupitia API rasmi; default region ni EU. | Credits hutumika kulingana na markets na regions zilizoombwa. Free allowance inaweza kubadilika; connector husoma headers za quota. Coverage ya market/bookmaker hutofautiana kwa ligi. | Ili kuongeza siku zenye candidates, connector inachagua hadi competitions 10 (soccer 8 na basketball 2). Kwa kila ligi ya soccer inaomba market moja kati ya totals, BTTS, double chance au h2h ya matokeo ya moja kwa moja (1X2); market hizo huzunguka kwa ligi na siku ili kutumia quota kidogo huku slate ikifunika families zote nne. Kwa basketball inaomba h2h, totals na spreads. Gharama ya juu inayotarajiwa ni 14 credits/run kwa region moja. |
| [API-Sports / API-Football](https://api-sports.io/) | Football fixtures, standings, head-to-head na matokeo ya final. | Free plan iliyoonyeshwa na provider: hadi requests 100/siku kwa kila API; coverage hutegemea ligi/season. Baadhi ya matumizi au uchapishaji vinaweza kuhitaji ruhusa za ziada. | Hutumika kuoanisha mechi, kuleta ushahidi unaohusiana na market, na kusettle matokeo ya mechi zilizopita pale fixture na final score zinapolingana. |
| [API-Sports / API-Basketball](https://api-sports.io/) | Ratiba, game history na score za basketball. | Coverage hutofautiana kwa ligi. Hii ni data ya stats/results, si odds za bookmaker. | Hutumika kwa home moneyline, totals, handicap na settlement pale data ya game ipo. |
| [TheSportsDB](https://www.thesportsdb.com/) | Metadata/ratiba na baadhi ya matokeo kupitia API yake rasmi. | Haina bookmaker odds; free plan/coverage ni chache. Terms zinasema tumia API rasmi, si kuscrape tovuti. | Haijaunganishwa kwa picks; inaweza kutathminiwa kama supplement ya ratiba pekee. |
| [football-data.org](https://www.football-data.org/documentation/api) | Ratiba, results na competition data ya football. | Football pekee; free plan inahitaji account/token na attribution. | Haijaunganishwa kwa sasa. API-Sports ndiyo stats/results source inayotumika. |
| [BBC Sport RSS](https://support.bbc.co.uk/platform/feeds/SportFeeds.htm) | Headlines/previews za football na basketball kupitia RSS rasmi. | Coverage si ya kila ligi/mechi; attribution ya BBC Sport inahitajika na alama/logo za BBC hazitumiki. | Context pekee: headline/link na keyword tags; haibadili eligibility wala ranking. |
| [ESPN RSS](https://www.espn.com/espn/news/story?id=3437834) | Headlines na summaries za soccer na NBA kutoka RSS rasmi. | Lazima ihifadhi headline/URL kama zilivyo na attribution; hakuna matangazo ndani ya ESPN RSS content. | Context pekee, si ushahidi wa takwimu wala utabiri. |

## Maoni/news kupitia RSS (context tu)

Pipeline husoma feeds nne mara moja kila run: BBC Sport Football, BBC Sport Basketball, ESPN Soccer na ESPN NBA. Huchuja items za saa 72 zilizopita, zilizochapishwa kabla ya kickoff, na huambatanisha item tu ikiwa majina ya timu zote mbili yana-match kwenye title/summary. Huhifadhi source, headline ya asili na link; full article text/summary haihifadhiwi. Link/attribution huonekana kwenye `analysis_note` ya fixture. Keyword topic/tone ni annotation ya ndani, si maoni rasmi ya publisher.

Hii si AI sentiment model: keyword tags zinaweza kukosea muktadha. RSS signal haiingii kwenye evidence gate, score/ranking, odds au uamuzi wa accumulator. Candidate isiyo na verified market-specific stats haiwezi kupita kwa sababu ya RSS. Feed ikikataa request au haipatikani, inarukwa bila retry/bypass. BBC feed hutumia attribution kama inavyoelekezwa kwenye [mwongozo wa RSS wa BBC Sport](https://www.bbc.com/sport/articles/cqllxj2n4kyo). ESPN RSS hutumia URL na headline ya feed kama zilivyo na attribution kulingana na [RSS terms za ESPN](https://www.espn.com/espn/news/story?id=3437834), bila matangazo. The Guardian haijaunganishwa kwenye automation: [terms zake](https://www.theguardian.com/help/terms-of-service) pia zinakataza automated reading pamoja na content analysis/data mining bila idhini ya maandishi; hakuna Guardian feed/page inayotumiwa hapa. Coverage ya ligi/mechi zote haijahakikishwa.

## Markets zinazounganishwa sasa

- **Football:** totals Over/Under 0.5, 1.5 au 2.5; BTTS Yes/No; double chance **Home or Draw (1X)**; na matokeo ya moja kwa moja ya 1X2 (home win, draw, away win). Kwa direct winner tunahitaji quote ya 1X2 yenye outcomes zote tatu; odds ziwe 1.05–1.80 na angalau 4 kati ya H2H 5 ziunge mkono outcome iliyochaguliwa. Three-way 1X2 haibadilishwi kimakosa kuwa double chance.
- **Basketball:** home moneyline, totals Over/Under kwa line halisi, na handicap/spread kwa upande na line halisi.
- **Tennis:** imezimwa kwa muda kwenye odds requests kwa sababu hatuna stats source inayokubalika ya ranking/surface/form. Odds peke yake hazitoshi.
- **Corners, cards na cricket:** hazijaunganishwa. Coverage ya odds pamoja na stats za market hizo haijathibitishwa.

## Vigezo vya ushahidi

1. **Football 1X:** standings ziwe kamili (angalau timu 10), timu zote mbili ziwe na angalau mechi 5 za ligi, nyumbani iwe top 3 na ugenini iwe bottom 5.
2. **Football direct 1X2:** kwenye H2H 5 zilizokamilika, angalau 4 ziwe na outcome ileile ya matokeo yaliyonukuliwa (home win, draw au away win); odds lazima ziwe ndani ya 1.05–1.80.
3. **Football totals:** mechi 5 zilizokamilika za head-to-head; angalau 4 kati ya 5 zilingane na line na direction inayochaguliwa.
4. **Football BTTS:** mechi 5 za head-to-head; angalau 4 kati ya 5 zilingane na Yes au No.
5. **Basketball moneyline:** home team iwe na angalau mechi 5 za hivi karibuni nyumbani na win rate angalau 80%; opponent awe na sample ya angalau mechi 5 za ugenini na losing streak ya sasa ya angalau 5.
6. **Basketball totals:** sample ya angalau mechi 5 kwa home team nyumbani na away team ugenini; kila sample iwe na hit rate angalau 70% kwenye line/direction hiyo hiyo.
7. **Basketball handicap:** angalau mechi 5 kwa kila sample inayotumika; selected side iwe na cover rate angalau 70% na upande pinzani usizidi 30% kwenye handicap line hiyo.
8. Ticket haiwezi kuweka markets mbili kutoka mechi moja. Ikiwa stats zimekosekana, majina/muda havilingani au fixture ni ambiguous, pick inakataliwa.

Hizi ni vigezo vya kuchuja, si ushahidi wa uhakika kwamba pick itashinda. Alama 0–100 ni ranking heuristic, si probability iliyocalibrate.

## Matumizi ya credits na requests

- The Odds API huomba region moja (`eu`) na hadi competitions 10: soccer 8 kwa market moja kila moja, pamoja na basketball 2 kwa markets 3 kila moja. Gharama inayotarajiwa ni hadi credits 14/run (karibu 420 kwa runs 30 kwenye allowance ya 500), kabla ya manual reruns. Hii huacha buffer ya credits takriban 80; connector husoma quota iliyobaki na hupunguza au kusimamisha maombi ikiwa credits hazitoshi.
- API-Sports enrichment ina cap ya hadi requests 60 kwa product kwa run; settlement ya matokeo ina cap tofauti ya hadi requests 20 kwa product. Status/quota hukaguliwa na request moja hubaki akiba. Idadi halisi hutegemea games na past fixtures.
- Kuongeza market nyingine kunaweza kuongeza gharama; ndiyo maana markets mpya zimechaguliwa kwa kubadilisha tennis (isiyoweza kuchaguliwa kwa sasa) na kupunguza idadi ya ligi badala ya kuongeza credits bila kikomo.

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
