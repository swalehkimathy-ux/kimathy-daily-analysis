"""Majaribio: mtiririko mzima (offline) — kutoka Forebet-fixture hadi faili la Excel.

Hii inatekeleza `kimathy.run.run()` HALISI, si nakala yake. Bookmaker ni fixture;
kila kitu kingine (uthibitishaji, uchujaji wa muda, uchambuzi, kiboreshaji,
uhakiki wa mwisho, Excel) ni code halisi ya injini.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import clock, run as runmod
from kimathy.bookies.base import Offer
from kimathy.config import Config
from tests._fixtures import FixtureProvider, football_offers, rec


def _cfg(tmp: str) -> Config:
    return Config({
        "min_minutes_before_kickoff": 60,
        "sports": ["football"],
        "accumulator": {"combined_odds_min": 1.80, "combined_odds_max": 2.00,
                        "max_legs": 12, "force_legs": None, "correlation_haircut": 0.98},
        "leg_filters": {"leg_odds_min": 1.05, "leg_odds_max": 3.50, "min_probability": 0.60,
                        "block_friendlies": True, "block_youth_and_women": True,
                        "max_flags_before_drop": 6},
        "probability": {"weight_model": 0.5, "uncalibrated_cap": 0.95,
                        "calibration_enabled": False},
        "output": {"folder": tmp, "filename_prefix": "KIMATHY_TEST",
                   "save_raw_captures": False},
        "run": {"reverify_before_export": True},
    })


def _make_provider(records) -> FixtureProvider:
    offers = {f"{r['home']}|{r['away']}": football_offers(f"ev{i}")
              for i, r in enumerate(records)}
    return FixtureProvider(offers, records=records)


def main():
    tmp = tempfile.mkdtemp(prefix="kimathy_test_")

    # Rekodi: 4 zinazostahili + 1 ya kirafiki + 1 inayoanza baada ya dk 20 + 1 iliyokwisha
    records = [
        rec("Team Alpha", "Team Beta", 57, 30, 13, avg=3.0, league="Ligi A", hours=3),
        rec("Team Gamma", "Team Delta", 36, 33, 31, avg=2.1, league="Ligi B", hours=4),
        rec("Team Echo", "Team Foxtrot", 62, 22, 16, avg=2.7, league="Ligi C", hours=5),
        rec("Team Golf", "Team Hotel", 48, 28, 24, avg=2.9, league="Ligi D", hours=6),
        rec("Real Madrid", "Al Nassr", 70, 20, 10, avg=3.0, league="Club Friendlies", hours=3),
        rec("Team India", "Team Juliet", 60, 25, 15, avg=2.5, league="Ligi E", hours=0, minutes=20),
        rec("Team Kilo", "Team Lima", 55, 25, 20, avg=2.4, league="Ligi F", hours=8, status="FT"),
    ]
    prov = _make_provider(records)
    cfg = _cfg(tmp)
    logs: list[str] = []

    res = runmod.run(cfg=cfg, log=lambda m="": logs.append(str(m)), offline=True,
                     fixtures_provider=prov)
    text = "\n".join(logs)

    # 1. faili la Excel limetengenezwa na ni .xlsx halali
    p = Path(res["excel"])
    assert p.exists() and p.suffix == ".xlsx", p
    from openpyxl import load_workbook
    wb = load_workbook(p)
    assert "ACCUMULATOR" in wb.sheetnames and "TAHADHARI" in wb.sheetnames
    ws = wb["ACCUMULATOR"]
    body = "\n".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)

    # 2. hali ya uendeshaji ipo wazi
    assert res["status"] in ("QUALIFIED ACCUMULATOR", "NO QUALIFIED ACCUMULATOR"), res["status"]
    assert res["status"] in body

    # 3. mechi ya kirafiki, ile ya dakika 20, na ile ya FT — zote HAZIKUINGIA
    assert "Real Madrid" not in body
    assert "Team India" not in body
    assert "Team Kilo" not in body

    # 4. kama kuna accumulator: odds iko ndani ya 1.80–2.00 na hakuna mechi iliyorudiwa
    if res["status"] == "QUALIFIED ACCUMULATOR":
        acc = res["accumulator"]
        assert 1.80 <= acc.total_odds <= 2.00, acc.total_odds
        keys = [(l["home"], l["away"]) for l in acc.legs]
        assert len(keys) == len(set(keys))
        assert "COMBINED DECIMAL ODDS" in body
        assert str(acc.total_odds) in body
    else:
        assert "Hakuna accumulator inayostahili" in body
        assert "hakuna dau lililotolewa" in body.lower()

    # 5. tahadhari za uaminifu zipo — hakuna dhamana ya ushindi
    assert "estimated" in body.lower()
    warn = "\n".join(str(c.value) for row in wb["TAHADHARI"].iter_rows() for c in row if c.value)
    assert "SI dhamana ya ushindi" in warn

    # 6. faili la awali HALIFUTWI — uendeshaji wa pili unatengeneza faili jipya
    res2 = runmod.run(cfg=cfg, log=lambda m="": None, offline=True, fixtures_provider=prov)
    assert res2["excel"] != res["excel"], "faili la awali limeandikwa upya!"
    assert Path(res["excel"]).exists() and Path(res2["excel"]).exists()

    # 7. hakuna UTEGEMEZI wa Supabase (import / URL / funguo) popote
    marks = ("import supabase", "from supabase", "supabase.co", "supabase_url",
             "supabase_service_role", "supabase_anon_key", "rest/v1/")
    src = Path(__file__).resolve().parent.parent / "kimathy"
    hits = []
    for f in src.rglob("*.py"):
        low = f.read_text(encoding="utf-8").lower()
        hits += [f"{f.name}: {m}" for m in marks if m in low]
    assert not hits, hits

    # 8. muhtasari wa uendeshaji umeandikwa kwenye Excel
    assert "eligible_matches" in body or "mechi zinazostahili" in text

    print(f"✓ end_to_end: ALL GREEN (8 makundi) · status={res['status']} · "
          f"faili={p.name}")
    print(f"  (folda ya majaribio: {tmp})")


if __name__ == "__main__":
    main()
