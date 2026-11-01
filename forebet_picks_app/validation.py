# validation.py — K96 (Phase 1): ukaguzi wa data iliyoscrape-kwa kabla ya engine
# Rekodi inayoshindwa UCHUNGUZI huondolewa (ihepeshwe) na kuhesabiwa — HAIJABADILISHWI kimya.
from __future__ import annotations
import re, datetime as dt

HTML_RE = re.compile(r"<|&nbsp;|&amp;")

KNOWN_STATUS = {"Scheduled", "Timed", "In Play", "HT", "FT", "AET", "AP",
                "Postp.", "Aband.", "Cancl.", "Delayed", "Interrupted", "Started"}
NOT_PRE_MATCH_PREFIX = ("FT", "AET", "AP", "In Play", "HT", "Started", "Interrupted")

BASKET_AVG = (120.0, 300.0)
TENNIS_AVG = (12.0, 60.0)
FOOTBALL_AVG = (0.0, 8.0)


def _bad_team_name(n):
    if not n or not isinstance(n, str):
        return "team_tupu"
    n2 = n.strip()
    if not (2 <= len(n2) <= 60):
        return "team_mrefu_uzito"
    if HTML_RE.search(n2):
        return "team_ina_html"
    return None


def validate_record(rec: dict, sport: str = "football") -> tuple[bool, list[str]]:
    """Rudi (ok, problems). ok=False → dondoo kwenye stats, usitumie engine."""
    probs: list[str] = []

    h = _bad_team_name(rec.get("home"))
    if h: probs.append(f"home:{h}")
    a = _bad_team_name(rec.get("away"))
    if a: probs.append(f"away:{a}")
    if rec.get("home") and rec.get("away") and str(rec["home"]).strip() == str(rec["away"]).strip():
        probs.append("home==away")

    p = rec.get("probs") or rec.get("p")
    if sport == "football":
        if p is None or len(p) < 3:
            probs.append("probs_hazipo")
        else:
            try:
                ints = [int(x) for x in p[:3]]
                if not all(0 <= x <= 100 for x in ints):
                    probs.append("probs_nje_0_100")
                if abs(sum(ints) - 100) > 3:
                    probs.append(f"probs_sum_{sum(ints)}")
            except Exception:
                probs.append("probs_si_int")
    else:
        if p is None or len(p) < 2:
            probs.append("probs_hazipo")

    od = rec.get("odds") or rec.get("od")
    if od:
        try:
            vals = [float(x) for x in od if x is not None]
            if vals and (min(vals) < 1.01 or max(vals) > 200):
                probs.append("odds_nje_1.01_200")
            if p and sport == "football" and len(p) >= 3 and len(od) >= 3 and all(od):
                # ulinganisho wa mpangili: favorite ya probs iko na odds ndogo zaidi?
                fb_side = int(max(range(3), key=lambda i: p[i])) if max(p) == max(p) else 0
                best_prob_side = int(max(range(3), key=lambda i: p[i]))
                best_odd_side = int(min(range(3), key=lambda i: float(od[i])))
                if best_prob_side != best_odd_side:
                    probs.append("odds_conflict")          # low-trust: rekodi hubaki, lakini huonyeshwa
        except Exception:
            probs.append("odds_hazifungui")

    ps = rec.get("ps")
    if ps is not None:
        try:
            # Predicted-score scale differs by sport: football goals are small,
            # while basketball forecasts routinely exceed 100 points.
            ps_max = {"football": 15, "basketball": 300, "tennis": 60}.get(sport, 300)
            if isinstance(ps, (list, tuple)):
                if any(x is None or not isinstance(x, int) or not 0 <= x <= ps_max for x in ps):
                    probs.append("ps_mbaya")
            else:
                probs.append("ps_si_pair")
        except Exception:
            probs.append("ps_mbaya")

    avg = rec.get("avg")
    if avg is not None:
        lo, hi = {"football": FOOTBALL_AVG, "basketball": BASKET_AVG, "tennis": TENNIS_AVG}.get(sport, FOOTBALL_AVG)
        try:
            v = float(avg)
            if not (lo <= v <= hi):
                probs.append(f"avg_nje_{v}")
        except Exception:
            probs.append("avg_mbaya")

    d = rec.get("dt")
    if d is not None:
        # NB: pipeline ya sasa hutumia datetime naive (EAT) — Phase ya baadaye: tz-aware kamili.
        if isinstance(d, dt.datetime):
            pass
        elif isinstance(d, str):
            if not d:
                probs.append("dt_tupu")
        else:
            probs.append("dt_aina_mbaya")

    st = (rec.get("status") or "").strip()
    if st:
        if any(st.startswith(x) for x in NOT_PRE_MATCH_PREFIX) or st.startswith("Pen."):
            probs.append(f"not_pre_match:{st}")
        elif st not in KNOWN_STATUS:
            probs.append(f"status_mpya:{st[:12]}")
    if not (rec.get("league") or "").strip():
        probs.append("league_tupu")

    return (len(probs) == 0, probs)


class ValidationStats:
    """Hesabu kamili za ukaguzi wa siku moja."""
    def __init__(self):
        self.total = 0
        self.valid = 0
        self.by_reason: dict[str, int] = {}

    def add(self, ok: bool, probs: list[str]):
        self.total += 1
        if ok:
            self.valid += 1
        for q in probs:
            r = q.split(":", 1)[0]
            r = re.sub(r"_\d+.*$", "", r)          # "probs_sum_120" → "probs_sum"
            self.by_reason[r] = self.by_reason.get(r, 0) + 1

    def line(self) -> str:
        parts = ", ".join(f"{k}={v}" for k, v in sorted(self.by_reason.items(), key=lambda x: -x[1])) or "-"
        return f"[VALIDATION] {self.valid}/{self.total} sawa · sheni: {parts}"
