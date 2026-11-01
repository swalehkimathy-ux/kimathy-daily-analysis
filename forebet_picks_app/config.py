# config.py — K96 (Phase 1): ushabu wa mipangilio yote pamoja (env + GUI settings)
# Mipangilio ya slip/odds (Phase 5) inaanza hapa — GUI itasoma na kubadilisha kupitia hapa.
from __future__ import annotations
import json, os
from pathlib import Path

DEFAULTS = {
    # slip target & legs (Phase 5)
    "LEG_ODDS_MIN": 1.01,        # low-odds markets allowed; real odds still required for slips
    "LEG_ODDS_MAX": 3.50,
    "SLIP_ODDS_MIN": 1.50,
    "SLIP_ODDS_MAX": 1.80,
    "MAX_LEGS": 12,
    "FORCE_LEGS": None,          # int N ili kulazimisha legs zingine
    "MIN_LEG_PROB": 0.75,
    "BLOCK_FRIENDLY": True,
    "FLAG_PENALTY": 0.01,
    # engine
    "MIN_CONF": 80,
    "TIMEZONE_OFFSET_EAT": 3,
    # weights
    "W_MODEL": 0.5,              # p_final = w*p_model + (1-w)*p_market
    "W_BETWAY": 0.5,             # mchanganyiko wa p_market (betway/betpawa)
    "MODEL_VERSION": "smart-engine-v0.2",
}

_PATHS = []


def _config_dir() -> Path:
    here = Path(__file__).resolve().parent          # forebet_picks_app/
    return here.parent / "forebet_backend"


def settings_path() -> Path:
    return _config_dir() / "k96_settings.json"


def read_env() -> dict:
    """Soma .env.local kutoka forebet_backend/ — BILA kucheza na sirri."""
    cand = [_config_dir() / ".env.local", Path.cwd() / ".env.local"]
    p = next((x for x in cand if x.exists()), None)
    env = {}
    if p:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get(key: str):
    cfg = DEFAULTS.copy()
    p = settings_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    env = read_env()
    if key in ("MIN_CONF", "TIMEZONE_OFFSET_EAT") and env.get(key) not in (None, ""):
        try:
            return int(env[key]) if "." not in env[key] else float(env[key])
        except Exception:
            pass
    return cfg.get(key)


def set(key: str, value) -> None:
    p = settings_path()
    cfg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    cfg[key] = value
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def all_settings() -> dict:
    cfg = DEFAULTS.copy()
    p = settings_path()
    if p.exists():
        try:
            cfg.update(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    env = read_env()
    for k in ("MIN_CONF", "TIMEZONE_OFFSET_EAT"):
        if env.get(k) not in (None, ""):
            try:
                cfg[k] = int(env[k]) if "." not in str(env[k]) else float(env[k])
            except Exception:
                pass
    return cfg
