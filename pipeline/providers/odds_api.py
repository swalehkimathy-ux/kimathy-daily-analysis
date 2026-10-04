"""The Odds API v4 adapter.

This module fetches current event odds only. It deliberately does not infer
form, rankings, injuries, or win probabilities from market prices. Records with
no independent evidence remain ineligible in ``engine.prepare_fixture``.

The API key is read from the runner environment and is never logged. The Odds
API requires its key as a query parameter, so all request/error logging here is
sanitized to avoid printing request URLs.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from statistics import median
from typing import Any, Iterable
from urllib.parse import quote

import requests

try:  # Works both when run_daily.py is executed directly and as a package.
    from engine import ODDS_BANDS
except ImportError:  # pragma: no cover - exercised by package-style imports.
    from pipeline.engine import ODDS_BANDS

BASE_URL = "https://api.the-odds-api.com/v4"
VALID_REGIONS = {"us", "us2", "uk", "eu", "au"}
DEFAULT_REGION = "eu"
DEFAULT_MAX_ODDS_AGE_MINUTES = 360
MAX_SPORT_KEYS_PER_RUN = 8
CATEGORY_LIMITS = {"soccer": 4, "basketball": 2, "tennis": 2}
MARKETS_BY_CATEGORY = {
    "soccer": ("h2h", "totals"),
    "basketball": ("h2h",),
    "tennis": ("h2h",),
}

SOCCER_PRIORITY = (
    "soccer_epl",
    "soccer_uefa_champs_league",
    "soccer_spain_la_liga",
    "soccer_germany_bundesliga",
    "soccer_italy_serie_a",
    "soccer_france_ligue_one",
    "soccer_england_efl_champ",
    "soccer_uefa_europa_league",
    "soccer_netherlands_eredivisie",
    "soccer_portugal_primeira_liga",
    "soccer_brazil_campeonato",
    "soccer_usa_mls",
)
BASKETBALL_PRIORITY = (
    "basketball_nba",
    "basketball_euroleague",
    "basketball_wnba",
    "basketball_ncaab",
    "basketball_wncaab",
    "basketball_nbl",
)


class OddsAPIError(RuntimeError):
    """Sanitized provider error; never contains the API key or request URL."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Quote:
    market_key: str
    market_name: str
    selection_name: str
    price: Decimal
    bookmaker_key: str
    bookmaker_name: str
    updated_at: datetime


@dataclass
class OddsAPIFeed:
    """A normalized event/odds batch and safe usage metadata."""

    fixtures: list[dict[str, Any]] = field(default_factory=list)
    sport_keys: list[str] = field(default_factory=list)
    event_count: int = 0
    requests_used: int | None = None
    requests_remaining: int | None = None
    warnings: list[str] = field(default_factory=list)


def _category(sport_key: str) -> str | None:
    key = str(sport_key or "").lower()
    for prefix in ("soccer_", "basketball_", "tennis_"):
        if key.startswith(prefix):
            return prefix[:-1]
    return None


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def _ordered_by_priority(keys: Iterable[str], priority: Iterable[str]) -> list[str]:
    keys = list(dict.fromkeys(keys))
    rank = {key: index for index, key in enumerate(priority)}
    return sorted(keys, key=lambda key: (rank.get(key, len(rank)), key))


def select_active_sport_keys(
    sports: list[dict[str, Any]],
    explicit_keys: str | Iterable[str] | None = None,
    max_keys: int = MAX_SPORT_KEYS_PER_RUN,
) -> tuple[list[str], list[str]]:
    """Select a small, predictable multi-sport set from the active catalog.

    By default this chooses at most four soccer competitions, two basketball
    competitions, and one active ATP plus one active WTA tennis competition.
    An explicit comma-separated allowlist can be supplied, but inactive or
    unknown keys are ignored and the eight-key free-tier guard still applies.
    """
    active: set[str] = set()
    for item in sports:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        if not key or not _category(key):
            continue
        if not _truthy(item.get("active"), default=True):
            continue
        if _truthy(item.get("has_outrights"), default=False):
            continue
        active.add(key)

    warnings: list[str] = []
    if isinstance(explicit_keys, str):
        requested = [part.strip() for part in explicit_keys.split(",") if part.strip()]
    elif explicit_keys is None:
        requested = []
    else:
        requested = [str(part).strip() for part in explicit_keys if str(part).strip()]

    if requested:
        selected: list[str] = []
        category_counts = {category: 0 for category in CATEGORY_LIMITS}
        for key in requested:
            if key not in active:
                warnings.append(f"Configured sport key is not active or not supported: {key}")
                continue
            if key in selected:
                continue
            category = _category(key)
            if category is None or category_counts[category] >= CATEGORY_LIMITS[category]:
                warnings.append(
                    f"Configured sport key {key} was skipped to keep the per-sport free-tier cap."
                )
                continue
            selected.append(key)
            category_counts[category] += 1
        if len(selected) > max_keys:
            warnings.append(
                f"Sport-key list was limited to {max_keys} per run to protect the free-tier quota."
            )
            selected = selected[:max_keys]
        return selected, warnings

    soccer = _ordered_by_priority(
        (key for key in active if _category(key) == "soccer"), SOCCER_PRIORITY
    )[:CATEGORY_LIMITS["soccer"]]
    basketball = _ordered_by_priority(
        (key for key in active if _category(key) == "basketball"), BASKETBALL_PRIORITY
    )[:CATEGORY_LIMITS["basketball"]]

    tennis_keys = sorted(key for key in active if _category(key) == "tennis")
    atp_keys = [key for key in tennis_keys if "atp" in key.lower()]
    wta_keys = [key for key in tennis_keys if "wta" in key.lower()]
    tennis: list[str] = []
    if atp_keys:
        tennis.append(atp_keys[0])
    if wta_keys and len(tennis) < CATEGORY_LIMITS["tennis"]:
        tennis.append(wta_keys[0])
    for key in tennis_keys:
        if len(tennis) >= CATEGORY_LIMITS["tennis"]:
            break
        if key not in tennis:
            tennis.append(key)

    selected = soccer + basketball + tennis
    if len(selected) > max_keys:
        selected = selected[:max_keys]
    return selected, warnings


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= Decimal("1.00"):
        return None
    return number


def _name_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def _market_timestamp(market: dict[str, Any], bookmaker: dict[str, Any]) -> datetime | None:
    return _parse_utc(market.get("last_update")) or _parse_utc(bookmaker.get("last_update"))


def _fresh_update(
    market: dict[str, Any], bookmaker: dict[str, Any], now_utc: datetime, max_age: timedelta
) -> datetime | None:
    updated = _market_timestamp(market, bookmaker)
    if updated is None or updated > now_utc + timedelta(minutes=5):
        return None
    if now_utc - updated > max_age:
        return None
    return updated


def _within_band(sport: str, price: Decimal) -> bool:
    band = ODDS_BANDS.get(sport)
    return bool(band and band[0] <= price <= band[1])


def _make_candidate(
    sport: str,
    event: dict[str, Any],
    quote: Quote,
    sport_key: str,
) -> dict[str, Any]:
    home = str(event.get("home_team", "")).strip()
    away = str(event.get("away_team", "")).strip()
    competition = str(event.get("sport_title", sport_key)).strip()
    updated = quote.updated_at.isoformat().replace("+00:00", "Z")
    return {
        "sport_type": sport,
        "match_name": f"{home} vs {away}",
        "home_team": home,
        "away_team": away,
        "match_time": str(event.get("commence_time", "")),
        "market_name": quote.market_name,
        "market_key": quote.market_key,
        "picked_odds": str(quote.price),
        "features": {},
        "analysis_note": (
            f"Current decimal quote from {quote.bookmaker_name} ({competition}); "
            f"bookmaker update {updated}. The odds feed does not include the form/ranking "
            "evidence required for a recommendation."
        ),
        "source": "the-odds-api",
        "event_id": str(event.get("id", "")),
        "sport_key": sport_key,
        "competition": competition,
        "selection_name": quote.selection_name,
        "bookmaker_key": quote.bookmaker_key,
        "odds_updated_at": updated,
    }


def normalize_event(
    event: dict[str, Any],
    sport_key: str,
    now: datetime | None = None,
    max_age_minutes: int = DEFAULT_MAX_ODDS_AGE_MINUTES,
) -> list[dict[str, Any]]:
    """Convert one v4 event into supported, fresh decimal-odds candidates.

    Only markets that match the existing engine's explicit strategies are
    emitted: football over 0.5 goals, basketball home moneyline, and tennis
    match winner. A three-way football moneyline is not mislabeled as double
    chance, and a different totals line is never mislabeled as over 0.5 goals.
    """
    category = _category(sport_key)
    if category is None or not isinstance(event, dict):
        return []
    sport = "football" if category == "soccer" else category
    now_utc = _as_utc(now)
    max_age = timedelta(minutes=max(1, int(max_age_minutes)))
    commence = _parse_utc(event.get("commence_time"))
    home = str(event.get("home_team", "")).strip()
    away = str(event.get("away_team", "")).strip()
    if not commence or commence <= now_utc or not home or not away:
        return []

    home_key, away_key = _name_key(home), _name_key(away)
    if not home_key or not away_key:
        return []

    quote_groups: dict[str, list[Quote]] = {
        "over_0_5_goals": [],
        "home_moneyline": [],
    }
    tennis_votes: dict[str, int] = {}
    tennis_names: dict[str, str] = {}
    tennis_quotes: dict[str, list[Quote]] = {}

    bookmakers = event.get("bookmakers", [])
    if not isinstance(bookmakers, list):
        return []
    for bookmaker in bookmakers:
        if not isinstance(bookmaker, dict):
            continue
        bookmaker_key = str(bookmaker.get("key", "")).strip()
        bookmaker_name = str(bookmaker.get("title") or bookmaker_key).strip()
        markets = bookmaker.get("markets", [])
        if not bookmaker_key or not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            market_key = str(market.get("key", "")).strip().lower()
            updated = _fresh_update(market, bookmaker, now_utc, max_age)
            if updated is None:
                continue
            outcomes = market.get("outcomes", [])
            if not isinstance(outcomes, list):
                continue

            if sport == "football" and market_key == "totals":
                for outcome in outcomes:
                    if not isinstance(outcome, dict) or _name_key(outcome.get("name")) != "over":
                        continue
                    point = _decimal(outcome.get("point"))
                    price = _decimal(outcome.get("price"))
                    # _decimal rejects values <= 1, so parse the 0.5 line separately.
                    if point is None:
                        try:
                            point = Decimal(str(outcome.get("point")))
                        except (InvalidOperation, TypeError, ValueError):
                            point = None
                    if point == Decimal("0.5") and price is not None:
                        quote_groups["over_0_5_goals"].append(
                            Quote(
                                "over_0_5_goals",
                                "Over 0.5 Goals",
                                "Over 0.5",
                                price,
                                bookmaker_key,
                                bookmaker_name,
                                updated,
                            )
                        )

            if sport == "basketball" and market_key == "h2h":
                for outcome in outcomes:
                    if not isinstance(outcome, dict) or _name_key(outcome.get("name")) != home_key:
                        continue
                    price = _decimal(outcome.get("price"))
                    if price is not None:
                        quote_groups["home_moneyline"].append(
                            Quote(
                                "home_moneyline",
                                f"Moneyline · Home Win ({home})",
                                home,
                                price,
                                bookmaker_key,
                                bookmaker_name,
                                updated,
                            )
                        )

            if sport == "tennis" and market_key == "h2h":
                participant_outcomes: list[tuple[dict[str, Any], Decimal]] = []
                for outcome in outcomes:
                    if not isinstance(outcome, dict):
                        continue
                    participant_key = _name_key(outcome.get("name"))
                    if participant_key not in {home_key, away_key}:
                        continue
                    price = _decimal(outcome.get("price"))
                    if price is not None:
                        participant_outcomes.append((outcome, price))
                if len(participant_outcomes) < 2:
                    continue
                participant_outcomes.sort(key=lambda row: row[1])
                if participant_outcomes[0][1] == participant_outcomes[1][1]:
                    continue
                favorite, price = participant_outcomes[0]
                favorite_name = str(favorite.get("name", "")).strip()
                favorite_key = _name_key(favorite_name)
                if not favorite_key:
                    continue
                tennis_votes[favorite_key] = tennis_votes.get(favorite_key, 0) + 1
                tennis_names[favorite_key] = favorite_name
                tennis_quotes.setdefault(favorite_key, []).append(
                    Quote(
                        "match_winner",
                        f"Match Winner · {favorite_name}",
                        favorite_name,
                        price,
                        bookmaker_key,
                        bookmaker_name,
                        updated,
                    )
                )

    candidates: list[dict[str, Any]] = []
    if sport == "football":
        best = _best_in_band(quote_groups["over_0_5_goals"], sport)
        if best:
            candidates.append(_make_candidate(sport, event, best, sport_key))
    elif sport == "basketball":
        best = _best_in_band(quote_groups["home_moneyline"], sport)
        if best:
            candidates.append(_make_candidate(sport, event, best, sport_key))
    elif sport == "tennis" and tennis_votes:
        # Require bookmaker consensus on the favorite; break ties by the lower
        # median quoted price, then stable participant name.
        favored_key = sorted(
            tennis_votes,
            key=lambda key: (
                -tennis_votes[key],
                median([quote.price for quote in tennis_quotes[key]]),
                key,
            ),
        )[0]
        best = _best_in_band(tennis_quotes[favored_key], sport)
        if best:
            candidates.append(_make_candidate(sport, event, best, sport_key))
    return candidates


def _best_in_band(quotes: list[Quote], sport: str) -> Quote | None:
    eligible = [quote for quote in quotes if _within_band(sport, quote.price)]
    if not eligible:
        return None
    return max(eligible, key=lambda quote: (quote.price, quote.updated_at, quote.bookmaker_key))


def _header_int(headers: Any, name: str) -> int | None:
    try:
        items = headers.items()
    except AttributeError:
        return None
    wanted = name.lower()
    for key, value in items:
        if str(key).lower() == wanted:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


class TheOddsAPIClient:
    def __init__(
        self,
        api_key: str,
        region: str = DEFAULT_REGION,
        timeout: int = 30,
        session: Any = None,
    ):
        key = str(api_key or "").strip()
        if not key:
            raise OddsAPIError("THE_ODDS_API_KEY is not set in the runner secrets.")
        normalized_region = str(region or DEFAULT_REGION).strip().lower()
        if normalized_region not in VALID_REGIONS:
            raise OddsAPIError(
                "ODDS_API_REGION must be one region: us, us2, uk, eu, or au."
            )
        self._api_key = key
        self.region = normalized_region
        self.timeout = max(1, int(timeout))
        self.session = session or requests

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> tuple[Any, Any]:
        query = dict(params or {})
        query["apiKey"] = self._api_key
        url = f"{BASE_URL}{path}"
        try:
            response = self.session.get(url, params=query, timeout=self.timeout)
        except requests.RequestException:
            # Do not include the original exception: requests can embed the URL,
            # and the provider key is a query parameter.
            raise OddsAPIError(
                "The Odds API could not be reached (network/timeout error); the key was not logged."
            ) from None
        except Exception:
            raise OddsAPIError(
                "The Odds API request failed unexpectedly; request details were suppressed to protect the key."
            ) from None

        status = int(getattr(response, "status_code", 0) or 0)
        if status < 200 or status >= 300:
            if status in {401, 403}:
                message = "The Odds API rejected the key or access (HTTP 401/403); check the provider account privately."
            elif status == 429:
                message = "The Odds API rate/credit limit was reached (HTTP 429); check quota in the provider account."
            else:
                message = f"The Odds API request failed (HTTP {status}); response details and URL were suppressed."
            raise OddsAPIError(message, status_code=status)
        try:
            payload = response.json()
        except Exception:
            raise OddsAPIError(
                "The Odds API returned an unreadable response; response details were suppressed."
            ) from None
        return payload, getattr(response, "headers", {})

    def list_active_sports(self) -> tuple[list[dict[str, Any]], Any]:
        payload, headers = self._get_json("/sports")
        if not isinstance(payload, list):
            raise OddsAPIError("The Odds API returned an unexpected sports catalog.")
        return [row for row in payload if isinstance(row, dict)], headers

    def get_odds(
        self, sport_key: str, markets: tuple[str, ...]
    ) -> tuple[list[dict[str, Any]], Any]:
        safe_key = quote(sport_key, safe="_")
        payload, headers = self._get_json(
            f"/sports/{safe_key}/odds",
            {
                "regions": self.region,
                "markets": ",".join(markets),
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            },
        )
        if not isinstance(payload, list):
            raise OddsAPIError(f"The Odds API returned an unexpected odds payload for {sport_key}.")
        return [row for row in payload if isinstance(row, dict)], headers


def fetch_odds_api_feed(
    api_key: str,
    region: str = DEFAULT_REGION,
    explicit_sport_keys: str | Iterable[str] | None = None,
    max_age_minutes: int = DEFAULT_MAX_ODDS_AGE_MINUTES,
    now: datetime | None = None,
    session: Any = None,
) -> OddsAPIFeed:
    """Fetch a quota-aware, multi-sport odds batch from The Odds API v4."""
    client = TheOddsAPIClient(api_key, region=region, session=session)
    feed = OddsAPIFeed()
    active_sports, sports_headers = client.list_active_sports()
    feed.requests_used = _header_int(sports_headers, "x-requests-used")
    feed.requests_remaining = _header_int(sports_headers, "x-requests-remaining")
    selected, selection_warnings = select_active_sport_keys(
        active_sports, explicit_keys=explicit_sport_keys
    )
    feed.sport_keys = selected
    feed.warnings.extend(selection_warnings)

    now_utc = _as_utc(now)
    for sport_key in selected:
        category = _category(sport_key)
        if category is None:
            continue
        markets = MARKETS_BY_CATEGORY[category]
        estimated_cost = len(markets)  # one configured bookmaker region
        if (
            feed.requests_remaining is not None
            and feed.requests_remaining < estimated_cost
        ):
            feed.warnings.append(
                f"Skipped {sport_key}: remaining credits are below the conservative cost estimate."
            )
            continue
        try:
            events, headers = client.get_odds(sport_key, markets)
        except OddsAPIError as exc:
            if exc.status_code in {400, 404, 422}:
                feed.warnings.append(f"Skipped {sport_key}: provider rejected this sport/market request.")
                continue
            raise

        header_used = _header_int(headers, "x-requests-used")
        header_remaining = _header_int(headers, "x-requests-remaining")
        if header_used is not None:
            feed.requests_used = header_used
        if header_remaining is not None:
            feed.requests_remaining = header_remaining
        feed.event_count += len(events)
        for event in events:
            feed.fixtures.extend(
                normalize_event(
                    event,
                    sport_key,
                    now=now_utc,
                    max_age_minutes=max_age_minutes,
                )
            )
    return feed
