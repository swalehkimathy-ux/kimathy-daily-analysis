"""Majaribio: uthibitishaji wa rekodi (Sehemu 9) — hakuna kurekebisha kimya kimya."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kimathy import validate
from tests._fixtures import rec


def main():
    # 1. rekodi nzuri inapita
    r = rec("Simba", "Yanga", 55, 25, 20, avg=2.6)
    ok, probs = validate.validate_record(r, "football")
    assert ok, probs

    # 2. uwezekano usiojumlisha 100 → kushindwa
    ok, probs = validate.validate_record(rec("A", "B", 55, 25, 30, avg=2.6), "football")
    assert not ok and any("uwezekano_haujumlishi_100" in p for p in probs), probs

    # 3. uwezekano uliokosekana
    ok, probs = validate.validate_record(rec("A", "B", None, 25, 20, avg=2.6), "football")
    assert not ok and any("uwezekano_haujakamilika" in p for p in probs), probs

    # 4. jina la timu lisilo halali (HTML)
    r = rec("Simba", "Yanga", 55, 25, 20, avg=2.6)
    r["home"] = "Simba <b>&nbsp;"
    ok, probs = validate.validate_record(r, "football")
    assert not ok and any("jina_la_timu_ya_nyumbani" in p for p in probs), probs

    # 5. timu zinazofanana
    ok, probs = validate.validate_record(rec("Simba", "Simba", 55, 25, 20, avg=2.6), "football")
    assert not ok and any("timu_zinazofanana" in p for p in probs), probs

    # 6. wastani wa magoli usio halali
    ok, probs = validate.validate_record(rec("A", "B", 55, 25, 20, avg=25.0), "football")
    assert not ok and any("wastani_wa_magoli" in p for p in probs), probs

    # 7. mechi iliyokwisha (FT) → not_pre_match
    r = rec("A", "B", 55, 25, 20, avg=2.6, status="FT")
    ok, probs = validate.validate_record(r, "football")
    assert not ok and any("not_pre_match" in p for p in probs), probs

    # 8. ligi haipo
    r = rec("A", "B", 55, 25, 20, avg=2.6)
    r["league"] = ""
    ok, probs = validate.validate_record(r, "football")
    assert not ok and any("ligi_haipo" in p for p in probs), probs

    # 9. chanzo cha URL hakipo (asili ya data ni lazima)
    r = rec("A", "B", 55, 25, 20, avg=2.6)
    r["source_url"] = ""
    ok, probs = validate.validate_record(r, "football")
    assert not ok and any("chanzo_cha_url_hakipo" in p for p in probs), probs

    # 10. takwimu za uendeshaji
    st = validate.ValidationStats()
    st.add(True, [])
    st.add(False, ["uwezekano_haujakamilika"])
    st.add(False, ["uwezekano_haujakamilika", "ligi_haipo"])
    assert st.total == 3 and st.valid == 1 and st.dropped_count == 2
    assert st.dropped["uwezekano_haujakamilika"] == 2
    line = st.line()
    assert "halali 1" in line and "uwezekano_haujakamilika=2" in line, line

    # 11. kikapu: pointi 100–320
    ok, _ = validate.validate_record(rec("Lakers", "Celtics", 55, 0, 45, avg=225,
                                         sport="basketball"), "basketball")
    assert ok
    ok2, probs2 = validate.validate_record(rec("Lakers", "Celtics", 55, 0, 45, avg=2.6,
                                               sport="basketball"), "basketball")
    assert not ok2 and any("wastani_wa_pointi" in p for p in probs2), probs2

    print("✓ validate: ALL GREEN (11 makundi — hakuna kurekebisha kimya kimya)")


if __name__ == "__main__":
    main()
