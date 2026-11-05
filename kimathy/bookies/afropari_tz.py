"""bookies/afropari_tz.py — Afropari (HAIJATEKELEZWA — kwa makusudi).

KWA NINI HAIJATEKELEZWA (ukweli, si kisingizio):
  1. Nimejaribu kufikia `afropari.co.tz` — jina la kikoa HALIPATIKANI (DNS fail).
  2. `afropari.com` inapatikana (185.174.42.1) lakini muunganisho wa HTTPS
     umeshindwa kutoka mazingira yangu ya majaribio (http=000).
  3. Sijui njia halisi za API zake, muundo wa masoko, wala vichwa vinavyohitajika.

Kubuni adapter bila kuthibitisha njia halisi = kubuni data. Master prompt inakataza
hilo waziwazi ("Usidhani tovuti ina API ya umma. Usibuni API endpoints").

ILI KUIONGEZA BAADAYE (hatua 3):
  1. Kwenye PC yako, fungua DevTools → Network kwenye ukurasa wa michezo wa Afropari,
     nakili URL ya ombi linalorudisha orodha ya matukio na linalorudisha masoko ya tukio.
  2. Jaza `DAY_INDEX_URL` na `EVENT_MARKETS_URL` hapa chini + vichwa vinavyohitajika.
  3. Andika `day_index()` na `snapshot_event()` zifuatazo muundo ule ule wa betpawa_tz.py,
     kisha weka `afropari.enabled = true` kwenye config.json.
"""
from __future__ import annotations

from .base import BookieDay, Offer

NAME = "afropari"
IMPLEMENTED = False
DAY_INDEX_URL = ""          # ← jaza: URL ya orodha ya matukio ya siku
EVENT_MARKETS_URL = ""      # ← jaza: URL ya masoko ya tukio (na {event_id})
HDRS: dict[str, str] = {}   # ← jaza: vichwa vinavyohitajika (mf. brand / apikey)


class NotImplementedAdapter(RuntimeError):
    pass


def day_index(day_iso: str, sports: list[str], log=print, timeout: int = 25) -> BookieDay:
    raise NotImplementedError(
        "Afropari haijatekelezwa: njia halisi za API hazijathibitishwa. "
        "Angalia maelezo juu ya faili hili.")


def snapshot_event(event_id, timeout: int = 25) -> list[Offer]:
    raise NotImplementedError(
        "Afropari haijatekelezwa: njia halisi za API hazijathibitishwa.")
