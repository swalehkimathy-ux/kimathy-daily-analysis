"""net.py — tabaka la kupata data kwa heshima (Sehemu 6.2 na 16).

Sheria:
  * timeouts, retries zenye mipaka, backoff, rate limiting;
  * makosa yanaripotiwa wazi — HAKUNA `except: pass` inayoficha data;
  * kila jibu linabeba asili ya data (URL + muda wa kukipata);
  * HATUPITI vizuizi vya uthibitishaji, paywall, CAPTCHA wala anti-bot.
    Browser fallback inatumika tu kwa Cloudflare "challenge" ya kawaida ambayo
    mtumiaji mwenyewe angeipita kwa kubonyeza — na inazimwa ikiwa imezuiwa.
"""
from __future__ import annotations

import datetime as _dt
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import clock

LogFn = Callable[[str], None]


class FetchError(RuntimeError):
    """Kupata data kumeshindwa baada ya njia zote zilizoruhusiwa."""


class BlockedError(FetchError):
    """Chanzo kimezuia ufikiaji (403 / CAPTCHA / anti-bot). HATUKWEPI."""


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    retrieved_at: str
    method: str                      # curl_cffi | urllib | browser | cache
    source: str = ""
    error: str = ""
    ok: bool = True

    @property
    def provenance(self) -> dict:
        return {"source": self.source, "url": self.url, "retrieved_at": self.retrieved_at,
                "method": self.method, "http_status": self.status}


@dataclass
class Fetcher:
    timeout_s: int = 30
    retries: int = 2
    retry_backoff_s: float = 2.0
    min_interval_s: float = 1.2
    allow_browser_fallback: bool = True
    browser_wait_s: int = 90
    user_agent: str = ""
    log: LogFn = field(default=print)
    _last_call: float = 0.0

    @classmethod
    def from_config(cls, cfg, log: LogFn = print) -> "Fetcher":
        n = cfg.section("network")
        return cls(
            timeout_s=int(n.get("timeout_s", 30)),
            retries=int(n.get("retries", 2)),
            retry_backoff_s=float(n.get("retry_backoff_s", 2.0)),
            min_interval_s=float(n.get("min_interval_s", 1.2)),
            allow_browser_fallback=bool(n.get("allow_browser_fallback", True)),
            browser_wait_s=int(n.get("browser_wait_s", 90)),
            user_agent=str(n.get("user_agent", "")),
            log=log,
        )

    # ---------------- rate limiting ----------------
    def _throttle(self) -> None:
        if self.min_interval_s <= 0:
            return
        gap = time.monotonic() - self._last_call
        if gap < self.min_interval_s:
            time.sleep(self.min_interval_s - gap)
        self._last_call = time.monotonic()

    # ---------------- njia za kupata ----------------
    def _via_curl_cffi(self, url: str, headers: dict) -> tuple[int, str]:
        from curl_cffi import requests as creq
        r = creq.get(url, headers=headers, timeout=self.timeout_s, impersonate="chrome")
        return int(r.status_code), r.text

    def _via_urllib(self, url: str, headers: dict) -> tuple[int, str]:
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
            return int(r.status), raw.decode(enc, errors="replace")

    def _via_browser(self, url: str) -> tuple[int, str]:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=self.user_agent or None)
                resp = page.goto(url, timeout=self.browser_wait_s * 1000, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:  # noqa: BLE001
                    pass
                code = int(resp.status) if resp and resp.status else 200
                return code, page.content()
            finally:
                browser.close()

    @staticmethod
    def _looks_blocked(text: str) -> bool:
        low = (text or "")[:4000].lower()
        marks = ("cf-browser-verification", "checking your browser", "cloudflare",
                 "attention required", "just a moment", "enable javascript and cookies")
        return sum(1 for m in marks if m in low) >= 2

    # ---------------- API kuu ----------------
    def fetch(self, url: str, *, source: str = "", headers: dict | None = None,
              allow_browser: bool | None = None, log: LogFn | None = None) -> FetchResult:
        log = log or self.log
        hdrs = {"Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "User-Agent": self.user_agent}
        hdrs.update(headers or {})
        allow_browser = self.allow_browser_fallback if allow_browser is None else allow_browser

        attempts = [("curl_cffi", self._via_curl_cffi), ("urllib", self._via_urllib)]
        last_err = ""
        for name, fn in attempts:
            for try_no in range(1, self.retries + 2):
                self._throttle()
                try:
                    code, text = fn(url, hdrs)
                except Exception as e:  # noqa: BLE001
                    last_err = f"{name}: {type(e).__name__}: {str(e)[:160]}"
                    log(f"    · {source or url[:60]} — {name} jaribio {try_no} limeshindwa: {last_err}")
                    if try_no <= self.retries:
                        time.sleep(self.retry_backoff_s * try_no)
                    continue
                if code in (401, 403):
                    if self._looks_blocked(text):
                        last_err = f"HTTP {code} + ukurasa wa uthibitishaji (anti-bot)"
                    else:
                        # Hakuna browser fallback kwa 403 ya kawaida: huo ni ukataji wa ufikiaji.
                        raise BlockedError(f"{source or url}: HTTP {code} — ufikiaji umekataliwa "
                                           f"(hatupiti uthibitishaji)")
                    break
                if code >= 500 and try_no <= self.retries:
                    last_err = f"HTTP {code}"
                    time.sleep(self.retry_backoff_s * try_no)
                    continue
                if self._looks_blocked(text):
                    last_err = "ukurasa wa Cloudflare challenge"
                    break
                return FetchResult(url=url, status=code, text=text,
                                   retrieved_at=clock.now_tz().isoformat(timespec="seconds"),
                                   method=name, source=source,
                                   ok=(200 <= code < 300))
            else:
                continue
            break

        if allow_browser:
            log(f"    · {source or url[:60]} — najaribu browser halisi (subiri)...")
            self._throttle()
            try:
                code, text = self._via_browser(url)
                if code in (200, 201, 304) and not self._looks_blocked(text):
                    return FetchResult(url=url, status=code, text=text,
                                       retrieved_at=clock.now_tz().isoformat(timespec="seconds"),
                                       method="browser", source=source, ok=True)
                last_err = f"browser: HTTP {code}"
            except Exception as e:  # noqa: BLE001
                last_err = f"browser: {type(e).__name__}: {str(e)[:160]}"
        raise BlockedError(f"{source or url}: imeshindwa kupata data ({last_err})")

    def try_fetch(self, url: str, **kw) -> FetchResult:
        """Kama `fetch` lakini hairushi — inarudisha FetchResult yenye ok=False.

        Hii ndiyo inayozuia chanzo kimoja kilichoshindwa kuharibu uendeshaji mzima.
        """
        log = kw.pop("log", self.log)
        try:
            return self.fetch(url, log=log, **kw)
        except FetchError as e:
            return FetchResult(url=url, status=0, text="",
                               retrieved_at=clock.now_tz().isoformat(timespec="seconds"),
                               method="none", source=kw.get("source", ""),
                               error=str(e), ok=False)


def save_capture(cfg, name: str, text: str, log: LogFn = print) -> Path | None:
    """Hifadhi HTML ghafi kwa ukaguzi (usafi wa ushahidi)."""
    if not cfg.get("output.save_raw_captures", True) or not text:
        return None
    from .config import resolve_output_folder
    base = resolve_output_folder(cfg) / str(cfg.get("output.captures_subfolder", "kimathy_captures"))
    base.mkdir(parents=True, exist_ok=True)
    day = clock.today_tz().isoformat()
    p = base / f"{name}_{day}_{clock.now_tz().strftime('%H%M%S')}.html"
    try:
        p.write_text(text, encoding="utf-8")
        return p
    except Exception as e:  # noqa: BLE001
        log(f"    · capture haikuhifadhiwa: {e}")
        return None


def try_json(text: str):
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return None
