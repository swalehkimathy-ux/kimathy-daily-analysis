"""config.py — mipangilio inayosomeka kutoka config.json (rahisi kuhariri bila code).

Hakuna siri hapa. Hakuna Supabase. Hakuna hifadhidata ya cloud.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("KIMATHY_CONFIG", ROOT / "config.json"))

_DEFAULTS = {
    "timezone": "Africa/Dar_es_Salaam",
    "min_minutes_before_kickoff": 60,
    "sports": ["football", "basketball", "tennis"],
    "accumulator": {
        "combined_odds_min": 1.80,
        "combined_odds_max": 2.00,
        "max_legs": 12,
        "force_legs": None,
        "correlation_haircut": 0.98,
    },
    "leg_filters": {
        "leg_odds_min": 1.05,
        "leg_odds_max": 3.50,
        "min_probability": 0.75,
        "block_friendlies": True,
        "block_youth_and_women": True,
        "max_flags_before_drop": 3,
    },
    "probability": {
        "weight_model": 0.5,
        "flag_penalty": 0.01,
        "max_flag_penalty": 0.03,
        "uncalibrated_cap": 0.95,
        "calibration_enabled": False,
    },
    "sources": {"forebet": {"enabled": True, "is_primary": True}, "tipsters": {}},
    "bookmakers": {},
    "network": {
        "timeout_s": 30,
        "retries": 2,
        "retry_backoff_s": 2.0,
        "min_interval_s": 1.2,
        "allow_browser_fallback": True,
        "browser_wait_s": 90,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0 Safari/537.36",
    },
    "output": {
        "folder": "DOWNLOADS",
        "filename_prefix": "KIMATHY_SMART_BETTING",
        "save_raw_captures": True,
        "captures_subfolder": "kimathy_captures",
    },
    "run": {"reverify_before_export": True, "max_events_per_run": 1500, "shortlist_h2h_max": 40},
}


def _deep_merge(base: dict, extra: dict) -> dict:
    out = dict(base)
    for k, v in (extra or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """Mpangilio uliopakiwa. `cfg.get('accumulator.combined_odds_min')` inafanya kazi."""

    def __init__(self, data: dict, path: Path | None = None):
        self._d = _deep_merge(_DEFAULTS, data or {})
        self.path = path

    @property
    def data(self) -> dict:
        return self._d

    def get(self, dotted: str, default=None):
        cur = self._d
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def section(self, dotted: str) -> dict:
        v = self.get(dotted, {})
        return v if isinstance(v, dict) else {}

    # ---- uthibitishaji wa mipangilio muhimu ----
    def validate(self) -> list[str]:
        probs = []
        lo, hi = self.get("accumulator.combined_odds_min"), self.get("accumulator.combined_odds_max")
        if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float))):
            probs.append("combined_odds_min/max lazima ziwe nambari")
        elif not (1.0 < lo <= hi):
            probs.append(f"safu ya odds {lo}–{hi} si halali (lazima 1.0 < min <= max)")
        mm = self.get("min_minutes_before_kickoff")
        if not (isinstance(mm, int) and mm >= 0):
            probs.append("min_minutes_before_kickoff lazima iwe nambari kamili >= 0")
        mp = self.get("leg_filters.min_probability")
        if not (isinstance(mp, (int, float)) and 0 < mp < 1):
            probs.append("min_probability lazima iwe kati ya 0 na 1")
        if self.get("probability.calibration_enabled"):
            probs.append("ONYO: calibration_enabled=true lakini hakuna historia ya ndani — "
                         "uwezekano unabaki 'estimated'")
        return probs


_CACHE: Config | None = None


def load(path: Path | None = None, force: bool = False) -> Config:
    global _CACHE
    if _CACHE is not None and not force and path is None:
        return _CACHE
    p = path or CONFIG_PATH
    data = {}
    if Path(p).exists():
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"✗ config.json imeharibika ({p}): {e}")
    cfg = Config(data, Path(p))
    if path is None:
        _CACHE = cfg
    return cfg


def resolve_output_folder(cfg: Config) -> Path:
    """'DOWNLOADS' → folda ya Downloads ya PC halisi (Windows/macOS/Linux)."""
    want = str(cfg.get("output.folder", "DOWNLOADS")).strip()
    if want.upper() == "DOWNLOADS":
        home = Path.home()
        for cand in (home / "Downloads", home / "downloads", home / "MafailiYaliyopakuliwa"):
            if cand.is_dir():
                return cand
        home_dl = home / "Downloads"
        home_dl.mkdir(parents=True, exist_ok=True)
        return home_dl
    p = Path(want).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p
