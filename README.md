# KIMATHY SMART BETTING ENGINE

Programu ya **kujitegemea (standalone)** ya kukusanya data za michezo na kuchambua kamari.
Hakuna Supabase · Hakuna GUI · Hakuna hifadhidata ya cloud.
Matokeo: **faili moja la Excel `.xlsx`** kwenye folda ya **Downloads** ya PC yako.

> ⚠️ **Hiki ni chombo cha uchambuzi na kusaidia maamuzi — SI dhamana ya ushindi.**
> Kamari ina hatari ya kupoteza pesa. Beti kwa uwajibikaji.

---

## 1. Inafanya nini (kila uendeshaji)

1. Inasoma saa ya **Africa/Dar_es_Salaam** na kuchukua mechi za **leo tu**.
2. Inaondoa mechi zilizoanza / kwisha / kuahirishwa / kufutwa, na zile zinazoanza
   **ndani ya dakika 60**.
3. Inakusanya data kutoka **Forebet** (chanzo muhimu) + tovuti za utabiri
   (maoni tu) + **bei halisi za masoko kutoka bookmaker**.
4. Inagundua **masoko yote** yanayotolewa kweli kwa kila mechi, kisha inachambua
   **tu yale yenye data mahususi** (kona inahitaji takwimu za kona, sio wastani wa magoli).
5. Inachagua **mgombea mmoja bora tu kwa kila mechi**.
6. Kiboreshaji kinatafuta mchanganyiko wenye combined odds **1.80–2.00** (mipaka inahesabiwa).
7. Inahakiki tena kila kitu mara moja kabla ya kuandika Excel.
8. Inatoa `QUALIFIED ACCUMULATOR` **au** `NO QUALIFIED ACCUMULATOR` yenye sababu.
   **Hakuna dau linalolazimishwa.**

---

## 2. Usakinishaji (PC ya Windows, mara moja)

1. Sakinisha **Python 3.10+** kutoka <https://www.python.org/downloads/> —
   weka alama ya **"Add Python to PATH"**.
2. Pakua mradi huu (Code → Download ZIP) na ufungue ZIP popote, mf. `C:\KIMATHY`.
3. Bonyeza mara mbili **`INSTALL.bat`** (inasakinisha vyanzo + browser ya Playwright).
4. Bonyeza **`DIAGNOSE.bat`** — itakuambia ni chanzo gani kinafikika kutoka PC yako.
5. Bonyeza **`RUN_KIMATHY.bat`** — Excel itaonekana kwenye **Downloads**.

Kila siku: bonyeza `RUN_KIMATHY.bat` tu.

### Njia ya mkono (command line)
```
pip install -r requirements.txt
python -m playwright install chromium
python -m kimathy.diagnose
python -m kimathy.run
```

---

## 3. Mipangilio

Hariri **`config.json`** — hakuna haja ya kugusa code.

| Kipengele | Chaguo-msingi | Maana |
|---|---|---|
| `min_minutes_before_kickoff` | `60` | Muda wa chini kabla ya kuanza mechi |
| `accumulator.combined_odds_min/max` | `1.80` / `2.00` | Safu ya combined odds (mipaka inahesabiwa) |
| `accumulator.force_legs` | `null` | Weka nambari ili kulazimisha idadi ya miguu |
| `leg_filters.leg_odds_min/max` | `1.05` / `3.50` | Mipaka ya odds ya mguu mmoja |
| `leg_filters.min_probability` | `0.75` | Uwezekano wa chini wa mgombea |
| `probability.calibration_enabled` | `false` | **Usiiwashe** — hakuna historia ya ndani bado |
| `output.folder` | `"DOWNLOADS"` | `"DOWNLOADS"` au njia kamili ya folda |
| `bookmakers.*` | betway + betpawa | Washa/zima bookmaker |
| `sources.tipsters.*` | 5 tovuti | Washa/zima tovuti za utabiri |

---

## 4. Vyanzo vya data

### Forebet — chanzo muhimu
Njia halisi zinazotumika (zilizorithiwa kutoka scraper iliyokuwa ikifanya kazi):
* Mpira wa miguu: `https://www.forebet.com/scripts/getrs.php?ln=en&tp=1x2&in=<tarehe>`
* Kikapu: `https://www.forebet.com/en/basketball/predictions-today`
* Tenisi: `https://www.forebet.com/en/tennis/predictions-today`

Muda wa `DATE_BAH` wa Forebet uko **UTC+2**; injini inaongeza saa 1 kufikia **EAT (UTC+3)**.

### Bookmakers — **Betway TZ + betPawa TZ**
| Bookmaker | Kazi | Sababu |
|---|---|---|
| **Betway TZ** | uthibitishaji wa bei + orodha ya matukio | njia zake za API zilizothibitishwa kufanya kazi; endpoint ya masoko ya tukio inarudisha masoko yote |
| **betPawa TZ** | **ugunduzi mpana wa masoko** + bei | `/events/{id}` inarudisha masoko **YOTE** ya tukio — ndiyo inayowezesha "gundua masoko kwa upana" |
| Afropari | **HAIJATEKELEZWA** | jina la kikoa `afropari.co.tz` halipatikani (DNS); `afropari.com` inapatikana lakini njia zake za API hazijathibitishwa. Kubuni adapter bila kuthibitisha = kubuni data, na hiyo imekataliwa. |

Kichwa cha lazima cha betPawa: `X-Pawa-Brand: betpawa-tanzania`
(bila hicho API inarudisha `BRAND_HEADER_IS_MISSING`).

### Tovuti za utabiri (maoni tu)
`footballwhispers`, `statarea`, `sportskeeda`, `windrawwin`, `predictz`.

**Msimamo wa uaminifu:** hizi hutoa **maoni, si takwimu**. Kila rekodi inabeba
`trust = opinion_only` na `probability = None`. **Hazigeuzwi kuwa uwezekano** na
**hazitumiki** katika hesabu za injini. HTML ghafi huhifadhiwa kwenye
`Downloads/kimathy_captures/` ili ukaguzi uwezekane. Ikiwa tovuti imezuiwa,
inarekodiwa wazi — hakuna utabiri unaobuniwa.

---

## 5. Masoko: yanayochambuliwa na yasiyochambuliwa

**Sheria:** soko bila data mahususi **halichambuliwi**. Linaondolewa na sababu inaandikwa.

| Mchezo | YANAYOchambuliwa | HAYACHAMBULIWI (data inakosekana) |
|---|---|---|
| Mpira wa miguu | 1X2, Double Chance, Draw No Bet, Total Goals 0.5–4.5, BTTS, Team Goals 0.5/1.5, Asian Handicap, European Handicap +2, First to Score, Correct Score*, Winning Margin* | **Kona, Kadi, Madhambi (fouls), Magoli ya kichwa, Player props (shots/goals/assists), Half-Time** |
| Kikapu | Match Winner (incl. OT), Point Spread, Total Points | **Team Points, Quarter/Half markets, Player props** |
| Tenisi | Match Winner, Games Handicap ±3.5, Total Games | **Set Winner, Set Score, Player to Win a Set** |

\* variance kubwa — inaruhusiwa tu kama bookmaker inatoa na odds zinastahili.

Orodha kamili na sababu zake iko `kimathy/markets.py`.

---

## 6. Majaribio

```
python tests/run_all.py          # majaribio 8 — yote offline
python tests/live_smoke.py       # jaribio la DATA HAI (linahitaji mtandao)
```

Majaribio 8 ya kawaida ni **offline** (hakuna mtandao). Yanatekeleza code halisi ya
injini, si nakala yake — ikiwemo mtiririko mzima kutoka rekodi hadi faili la `.xlsx`.

### Matokeo ya uthibitishaji (2026-11-05)

| Kipimo | Matokeo |
|---|---|
| Majaribio 8 (offline) | **8/8 GREEN** |
| CLI halisi `python -m kimathy.run` | **imefanya kazi**, `.xlsx` imetengenezwa |
| betPawa TZ — orodha ya matukio | **IMEFIKIKA** · matukio 97 ya mpira (leo) |
| betPawa TZ — masoko ya tukio moja | **IMEFIKIKA** · offers 1165 · **aina 117 za masoko** |
| Jaribio la data hai (njia kamili) | **QUALIFIED ACCUMULATOR** · miguu 3 · odds 1.811 · joint 45.8% · **EV −0.170** |
| Betway TZ | **HTTP 403** kutoka IP ya datacenter (inatarajiwa kufanya kazi kwenye PC yako) |
| Forebet | **HTTP 403** kutoka IP ya datacenter (inatarajiwa kufanya kazi kwenye PC yako) |
| windrawwin / predictz | **HTTP 200** (zinafikika) |
| sportskeeda | HTTP 403 |
| footballwhispers / statarea | hazikufikika wakati wa kipimo |

> Kumbuka: jaribio la data hai **halikutumia Forebet** (haikufikika). `probs` zilikokotolewa
> kutoka bei za 1X2 za betPawa yenyewe. Kwa hiyo ni uthibitisho wa **msimbo**, si uchambuzi halisi.

### Muundo halisi wa API ya betPawa (umethibitishwa)

```
markets[i]["marketType"]["id"]        → "5000"
markets[i]["marketType"]["name"]      → "Total Score Over/Under - FT"
markets[i]["marketType"]["displayName"] → "Over/Under | Full Time"
markets[i]["row"][j]["specifier"]     → {"total": "2.5"} | {"hcp": "-1.5"} | {"number": "1"}
markets[i]["row"][j]["prices"][k]     → {"name","odds","suspended","probability":{"win":..}}
```

Toleo la zamani la code lilisoma `market["betTypeId"]` na `market["name"]` — **njia hizo
hazipo tena**, na hilo ndilo lilikuwa likifanya majina ya masoko kuwa matupu. Limerekebishwa.

Majina halisi ya masoko yanayolingana na injini:
`1X2 - FT` · `Double Chance - FT` · `Draw No Bet - FT` · `Total Score Over/Under - FT` ·
`Total Score Over/Under - FT - Home Team` · `Total Score Over/Under - FT - Away Team` ·
`Both Teams To Score - FT` · `Asian Handicap - FT` · `Handicap 1X2 - FT` ·
`Correct Score (26 Outcomes)` · `Winning Margin - FT` · `Goal` (timu ya kwanza kufunga).

betPawa **inatoa** masoko ya kona, kadi (bookings) na player shots — lakini injini
**haiyachambui** kwa sababu hakuna chanzo cha takwimu hizo. Hii ni tabia iliyokusudiwa.

---

## 7. MAPUNGUFU YA KWELI (soma hii)

1. **Uwezekano unaonyeshwa ni MAKADIRIO (estimated).** Haujasawazishwa (calibrated)
   kwa historia ya matokeo. Historia ya calibration **imeondolewa** kwa ombi lako;
   kwa hiyo injini haiwezi kudai usahihi wowote wa kihistoria.
2. **Masoko ya kona/kadi/madhambi/player props hayachambuliwi.** Vyanzo vilivyosanidiwa
   havina takwimu hizo. Kuongeza hayo kunahitaji chanzo kipya cha takwimu.
3. **Safu ya 1.80–2.00 ni nyembamba.** Siku nyingi matokeo halisi yatakuwa
   `NO QUALIFIED ACCUMULATOR`. Hii ni tabia sahihi, si kosa.
4. **Uhuru (independence) wa miguu ni dhana.** Uwezekano wa pamoja unakokotolewa
   kama `Πp × 0.98^(jozi za correlation)`. Hairuhusu utegemezi usiojulikana.
5. **Scraping inaweza kuvunjika** Forebet au bookmaker wakibadilisha kurasa/API zao.
   Endesha `DIAGNOSE.bat` kujua sababu.
6. **Forebet na Betway huzuia IP za datacenter/VPN** (HTTP 403). Zima VPN;
   endesha kwenye PC yako yenye mtandao wa kawaida.
7. **EV mara nyingi ni hasi.** Bookmaker ana margin. Mguu wenye uwezekano mkubwa
   si "pesa bure".

---

## 8. Muundo wa faili

```
kimathy_engine/
  RUN_KIMATHY.bat        ← bonyeza hii (uendeshaji wa kila siku)
  DIAGNOSE.bat           ← kipimo cha vyanzo
  INSTALL.bat            ← usakinishaji wa mara moja
  config.json            ← mipangilio (hariri hii)
  requirements.txt
  kimathy/
    clock.py             saa ya Tanzania + sheria za muda (dakika 60)
    config.py            mipangilio + folda ya Downloads
    net.py               kupata data kwa heshima (timeouts, retries, rate limit)
    normalize.py         majina ya timu, aliases, ulinganishaji wa matukio
    validate.py          uthibitishaji wa rekodi (hakuna kurekebisha kimya kimya)
    forebet.py           adapta ya Forebet
    tipsters.py          tovuti za utabiri (maoni tu)
    markets.py           katalogi ya masoko + mahitaji ya data
    analyze.py           modeli ya uwezekano (Poisson / Normal)
    candidates.py        mgombea mmoja bora kwa kila mechi
    optimize.py          kiboreshaji cha accumulator 1.80–2.00
    verify.py            uhakiki wa mwisho kabla ya export
    excel.py             faili la .xlsx
    run.py               mtiririko mzima + CLI
    diagnose.py          kipimo cha vyanzo
    bookies/
      base.py            Offer, devig, overround, circuit breaker
      betway_tz.py       Betway Tanzania
      betpawa_tz.py      betPawa Tanzania
      afropari_tz.py     HAIJATEKELEZWA (stub yenye maelekezo)
      provider.py        ugunduzi wa masoko + uthibitishaji wa bei
    data/aliases.json    majina mbadala ya timu
  tests/                 majaribio 8 (offline)
```

---

## 9. Usalama

* **Hakuna siri kwenye mradi huu.** Hakuna tokens, hakuna funguo, hakuna `.env.local`.
* Hakuna hifadhidata ya cloud — data zote zinabaki kwenye PC yako.
* Ukishiriki mradi, hakikisha huna faili la `.env.local` wala token yoyote ndani yake.
* **Access token ya GitHub na funguo za Supabase zilizowahi kuandikwa wazi
  zinapaswa kuzungushwa (rotate)** — tazama historia ya mazungumzo.

---

`KIMATHY SMART BETTING ENGINE v1.0.0 · standalone · Dar es Salaam`
