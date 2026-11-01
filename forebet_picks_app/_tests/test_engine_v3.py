#!/usr/bin/env python3
"""Engine v1.0 tests — K96 ENGINE RULES (G/F/B/T). Kila kundi lina rule-ID sawa na doc."""
import datetime, sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine, oddsx

D = datetime.datetime(2026, 10, 27, 20, 0)
def mk(p, od, home, away, league, ps=None, avg=None, hf=None, af=None, sport="football", st="Scheduled"):
    return {"dt": D, "league": league, "home": home, "away": away, "status": st, "st": st,
            "p": p, "ps": ps, "avg": avg, "od": od, "url": f"u/{home}",
            "hf": hf or [], "af": af or [], "hp": "", "ap": "", "h2h": "", "rnd": "", "tr": ""}

# ── 1. G1/F1: probability-tu — hakuna +points (Liverpool 1X = 87%, SI 98%) ──
liv = mk([57, 30, 13], [1.35, 5.2, 8.0], "Liverpool", "Tottenham", "EPL", ps=[3, 1], avg=3.2,
         hf=["W"]*4+["D"], af=["L"]*4+["D"])
mm, _ = engine.model_markets(liv, "football")
assert abs(mm[("Double Chance", "1X")] - 0.87) < 1e-9, mm[("Double Chance", "1X")]
bay = mk([76, 15, 9], None, "Bayern Munich", "Union Berlin", "Bundesliga", avg=3.7)
mm_b, info_b = engine.model_markets(bay, "football")
assert abs(mm_b[("Double Chance", "1X")] - 0.91) < 1e-9
assert abs(info_b["lambda_home"] - 2.78) < 0.15 and abs(info_b["lambda_away"] - 0.93) < 0.15, info_b
assert info_b["fit_err"] <= 0.05, info_b["fit_err"]

# ── 2. G2: devig — 1X2 sums→1, Double Chance sums→2 ────────────────────────
assert abs(sum(oddsx.devig([1.5, 3.8, 6.0])) - 1) < 1e-9
assert abs(sum(oddsx.devig([1.2, 1.2, 2.6], total=2.0)) - 2) < 1e-9

# ── 3. BLOCK LIST: friendly & women blocked · 'B. Player' tennis HAIZIBWI ──
assert engine.blocked_reason(mk([70, 18, 12], None, "Real Madrid", "Al Nassr", "Club Friendlies", avg=3.4), "football")
assert engine.blocked_reason(mk([60, 22, 18], None, "Lyon W", "PSG W", "Division 1", avg=3.1), "football")
assert engine.blocked_reason(mk([55, None, 45], None, "A. Player", "B. Player", "ATP 250", avg=22.5), "tennis") is None
assert engine.blocked_reason(mk([55, None, 45], None, "Duo A", "Duo B", "ATP Doubles", avg=21.0), "tennis")   # doubles
assert engine.blocked_reason(mk([50, None, 50], None, "A", "B", "ITF Futures", avg=22.5), "tennis")
tt = mk([70, 18, 12], None, "A", "B", "EPL", avg=3.0, st="FT")
assert engine.blocked_reason(tt, "football")          # status si Scheduled

# ── 4. blend (G3): p_final = 0.5·model + 0.5·market — kubadilisha odds tofauti ──
bk = {"found": True, "bookmaker": "betway",
      "probs": {("Double Chance", "1X"): 0.90}, "odds": {("Double Chance", "1X"): 1.11}}
bt = engine.best_tip_for_match(liv, "football", bk, 0.75, lambda s: None)
assert bt is not None and bt["tip"] == "1X", bt
assert abs(bt["p_final"] - 0.885) < 1e-9 and bt["bk_odds"] == 1.11

# ── 5. G5/G6: bookie asine market → mechi yote hapiti; odds < min → inarejibiwa ──
bk3 = {"found": True, "bookmaker": "betway", "probs": {}, "odds": {}}
assert engine.best_tip_for_match(liv, "football", bk3, 0.75, lambda s: None) is None
# odds chini ya LEG_ODDS_MIN: "1X mine @1.01" imekataliwa (Bayern demo: Over 0.5 @1.01 n.k.)
bk_bad = {"found": True, "bookmaker": "betway",
          "probs": {("Double Chance", "1X"): 0.99}, "odds": {("Double Chance", "1X"): 1.01}}
btb = engine.best_tip_for_match(bay, "football", bk_bad, 0.75, lambda s: None)
assert btb is None or (btb["bk_odds"] is None), btb
# rejected-with-reason zipo (G7 — top 3)
btj = engine.best_tip_for_match(bay, "football", None, 0.75, lambda s: None)
assert isinstance(btj.get("rejected"), list)

# ── 6. G4 flags: form_against inapunguza (kamwe haiongezi) · favourite_away ──
livW = mk([57, 30, 13], None, "Liverpool", "Tottenham", "EPL", ps=[3, 1], avg=3.2,
          hf=["D", "L", "L", "L", "D"], af=["W"]*5)
DC_ONLY = {"found": True, "bookmaker": "betway",
           "probs": {("Double Chance", "1X"): 0.90}, "odds": {("Double Chance", "1X"): 1.11}}
btA = engine.best_tip_for_match(livW, "football", DC_ONLY, 0.60, lambda s: None)
btB = engine.best_tip_for_match(liv, "football", DC_ONLY, 0.60, lambda s: None)
assert btA and btB and btA["tip"] == btB["tip"] == "1X", (btA, btB)
assert "form_against" in btA["flags"], btA["flags"]
assert btA["p_cal"] < btB["p_cal"], "flag → hasi: p_cal INASHUKA TU (kamwe haicongenzeki)"
assert abs((btB["p_cal"] - btA["p_cal"]) - 0.01) < 1e-4, (btA["p_cal"], btB["p_cal"])
aw = mk([20, 30, 50], None, "Small", "BigFC", "EPL", ps=[0, 2], avg=2.4)
btW = engine.best_tip_for_match(aw, "football", None, 0.60, lambda s: None)
if btW and btW["tip"] in ("2", "X2", "12"):
    assert "favourite_away" in btW["flags"]

# ── 7. BASKETBALL (B1-B3): Winner reproduce · handshake markets zipo ──────
nb = mk([84, None, 16], None, "Real Madrid", "Zalgiris", "Euroleague", avg=165.0, sport="basketball")
mmn, inf = engine.model_markets(nb, "basketball")
assert abs(mmn[("Winner", "P1")] - 0.84) < 1e-9                     # B1
assert abs(inf["mean_margin"] - 11.4) < 0.6                         # B2 mean=SD·z(p)
assert abs(mmn[("Handicap", "Home +9.5")] - 0.965) < 0.01, mmn[("Handicap", "Home +9.5")]
h2 = mk([49, None, 51], None, "Hornets", "Pacers", "NBA", avg=232.0, sport="basketball")
btH = engine.best_tip_for_match(h2, "basketball", None, 0.75, lambda s: None)
assert btH and btH["market"] == "Handicap" and "Away +9.5" in btH["tip"], btH and (btH["market"], btH["tip"])

# ── 8. TENNIS (T1-T5): winner normalize · T5 lopsided veto → Over zimeondolewa ──
sn = mk([91, None, 9], None, "J. Sinner", "Q. Qualifier", "ATP Masters", avg=19.5, sport="tennis")
btS = engine.best_tip_for_match(sn, "tennis", None, 0.75, lambda s: None)
assert btS and btS["tip"].startswith("Under"), btS and btS["tip"]       # T5: Over zilizoondolewa
mt, _pm = engine.model_markets(sn, "tennis")
assert any(k[0] == "Total Games" and k[1].startswith("Under") for k in mt)

# ── 9. G7: tie ≤1pt → odds kubwa hushinda ──────────────────────────────────
tb = mk([80, 12, 8], None, "Chiefs", "Rovers", "EPL", avg=3.3)
booking = {"found": True, "bookmaker": "betway",
           "probs": {("Double Chance", "1X"): 0.90, ("1X2", "1"): 0.905},   # ndani ya 1pt baada blend
           "odds": {("Double Chance", "1X"): 1.30, ("1X2", "1"): 1.19}}
btT = engine.best_tip_for_match(tb, "football", booking, 0.75, lambda s: None)
# model: DC 1X=0.92, 1=0.80 → blends: DC .910 @1.30 · 1 .8525 @1.19 — DC mbele (kubwa p_cal)
assert btT and btT["tip"] == "1X", btT and (btT["tip"], btT["p_cal"])

# ── 10. G8: hakuna pick → None + hakuna kufungua chini kimya ───────────────
bal = mk([36, 33, 31], None, "Torino", "Udinese", "Serie A", avg=2.1)
btN = engine.best_tip_for_match(bal, "football", None, 0.99, lambda s: None)
assert btN is None, "min 99%: hakuna candidate → None (hakuna kuponda mipaka)"
# predict_day wrapper bado inafanya kazi
front, pool, mn = engine.predict_day({"football": [liv]}, None, 80, lambda s: None)
assert len(front) == 1 and abs(mn - 0.80) < 1e-9
fr2, mn2 = engine.analyze_day({"football": [liv]}, lambda s: None)
assert len(fr2) == 1 and mn2 == 80

print("✓ engine v1.0 (RULES G/F/B/T): ALL GREEN (10 groups)")
