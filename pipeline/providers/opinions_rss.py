"""Private, read-only RSS news/opinion context for fixture candidates.

Only public RSS/Atom feed documents are requested; article pages are not fetched.
The module never creates a pick, changes the stats eligibility gate, or derives
win probabilities. It stores a short classification plus attribution/link only.
"""
from __future__ import annotations

import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Iterable

import requests

DEFAULT_RSS_WINDOW_HOURS = 72
MAX_FEED_BYTES = 2_000_000
MAX_ITEMS_PER_FEED = 200
MAX_NOTE_ITEMS = 2


@dataclass(frozen=True)
class RSSFeed:
    name: str
    url: str
    sport_type: str | None = None


DEFAULT_RSS_FEEDS = (
    RSSFeed("BBC Sport Football", "https://feeds.bbci.co.uk/sport/football/rss.xml", "football"),
    RSSFeed("BBC Sport Basketball", "https://feeds.bbci.co.uk/sport/basketball/rss.xml", "basketball"),
    RSSFeed("ESPN Soccer", "https://www.espn.com/espn/rss/soccer/news", "football"),
    RSSFeed("ESPN NBA", "https://www.espn.com/espn/rss/nba/news", "basketball"),
)

POSITIVE_TERMS = {
    "back", "backing", "confident", "expect", "expected", "favourite", "favorite",
    "in form", "likely", "strong", "unbeaten", "win", "wins",
}
CAUTION_TERMS = {
    "absent", "doubt", "doubts", "injured", "injury", "illness", "missing", "out",
    "poor form", "ruled out", "struggle", "struggling", "suspended", "suspension",
}
TOPIC_TERMS = {
    "prediction": ("prediction", "predicts", "tip", "preview", "expects", "expect"),
    "team news": ("injury", "injured", "doubt", "suspended", "suspension", "unavailable", "ruled out", "line-up", "lineup"),
    "form": ("in form", "unbeaten", "winless", "struggling", "poor form", "winning run", "losing run"),
    "rumour/speculation": ("rumour", "rumor", "linked with", "speculation", "reportedly", "could sign", "transfer talk"),
}


@dataclass
class OpinionRSSResult:
    fixtures: list[dict[str, Any]]
    feeds_checked: int = 0
    feed_items_read: int = 0
    matched_fixtures: int = 0
    matched_articles: int = 0
    warnings: list[str] = field(default_factory=list)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)


def _plain_text(value: Any, limit: int = 2400) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(str(value or ""))
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        text = str(value or "")
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text[:limit]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def _child_text(element: ET.Element, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for child in list(element):
        if _local_name(child.tag) in wanted:
            text = "".join(child.itertext()).strip()
            if text:
                return text
    return ""


def _entry_link(element: ET.Element) -> str:
    for child in list(element):
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "")).strip()
        if href:
            return href
        text = "".join(child.itertext()).strip()
        if text:
            return text
    return ""


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        result = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        result = None
    if result is None:
        try:
            iso = text[:-1] + "+00:00" if text.endswith("Z") else text
            result = datetime.fromisoformat(iso)
        except (TypeError, ValueError, OverflowError):
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _parse_feed(content: bytes, feed: RSSFeed) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    items: list[dict[str, Any]] = []
    for element in root.iter():
        local = _local_name(element.tag)
        if local not in {"item", "entry"}:
            continue
        title = _plain_text(_child_text(element, "title"), 300)
        link = _entry_link(element) or _child_text(element, "link")
        published = _parse_time(_child_text(element, "pubdate", "published", "updated", "date"))
        summary = _plain_text(_child_text(element, "description", "summary", "content"), 2400)
        if not title or not link.startswith("https://") or not published:
            continue
        items.append({
            "source_name": feed.name,
            "source_url": feed.url,
            "title": title,
            "link": link,
            "published_at": published,
            "summary": summary,
        })
        if len(items) >= MAX_ITEMS_PER_FEED:
            break
    return items


def _tokens(value: Any) -> list[str]:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    ignored = {"fc", "cf", "sc", "afc", "club", "the"}
    return [token for token in text.split() if token not in ignored]


TEAM_ALIASES = {
    "manchester united": ("man utd", "manchester utd"),
    "manchester city": ("man city",),
    "tottenham hotspur": ("tottenham", "spurs"),
    "newcastle united": ("newcastle",),
    "west ham united": ("west ham",),
}


def _team_mentioned(team: Any, text: str) -> bool:
    name = str(team or "").strip()
    alias_key = re.sub(r"\b(fc|afc|cf|sc)\b", "", name.lower())
    alias_key = re.sub(r"\s+", " ", alias_key).strip()
    variants = (name, *TEAM_ALIASES.get(alias_key, ()))
    text_tokens = _tokens(text)
    normalized_text = " " + " ".join(text_tokens) + " "
    for variant in variants:
        team_tokens = _tokens(variant)
        if not team_tokens:
            continue
        phrase = " " + " ".join(team_tokens) + " "
        if phrase in normalized_text:
            return True
        if len(team_tokens) >= 3 and set(team_tokens).issubset(set(text_tokens)):
            return True
    return False


def _title_dedupe_key(title: str) -> str:
    text = unicodedata.normalize("NFKD", title)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _has_keyword(text: str, term: str) -> bool:
    words = r"\s+".join(re.escape(part) for part in term.split())
    return re.search(rf"(?<![a-z0-9]){words}(?![a-z0-9])", text) is not None


def _sentiment_tone(texts: list[str]) -> tuple[str, int, int, list[str]]:
    joined = " ".join(texts).lower()
    positive = sum(1 for term in POSITIVE_TERMS if _has_keyword(joined, term))
    caution = sum(1 for term in CAUTION_TERMS if _has_keyword(joined, term))
    if positive > caution:
        tone = "positive-language"
    elif caution > positive:
        tone = "caution-language"
    elif positive or caution:
        tone = "mixed-language"
    else:
        tone = "neutral/no-clear-opinion"
    topics = [
        label for label, terms in TOPIC_TERMS.items()
        if any(_has_keyword(joined, term) for term in terms)
    ]
    return tone, positive, caution, topics


def _candidate_time(candidate: dict[str, Any]) -> datetime | None:
    value = candidate.get("match_time")
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _append_opinion_note(candidate: dict[str, Any], matched: list[dict[str, Any]]) -> None:
    texts = [f"{item['title']} {item.get('summary', '')}" for item in matched]
    tone, positive, caution, topics = _sentiment_tone(texts)
    sources = ", ".join(sorted({str(item["source_name"]) for item in matched}))
    topic_text = ", ".join(topics) if topics else "general coverage"
    references = " | ".join(
        f"{item['source_name']}: {item['title']} ({item['link']})"
        for item in matched[:MAX_NOTE_ITEMS]
    )
    note = (
        f"RSS news/opinion context (last {DEFAULT_RSS_WINDOW_HOURS}h): "
        f"{len(matched)} matched item(s) from {sources}; {tone} by simple keyword scan "
        f"(positive terms {positive}, caution terms {caution}); topics: {topic_text}. "
        f"Headlines/links: {references}. This is context only, not a win probability."
    )
    existing = str(candidate.get("analysis_note", "")).strip()
    candidate["analysis_note"] = f"{existing} News/opinion: {note}".strip()
    source = str(candidate.get("source", "")).strip()
    if "rss-news" not in source.lower():
        candidate["source"] = f"{source}+rss-news" if source else "rss-news"


def enrich_with_rss_opinions(
    fixtures: list[dict[str, Any]],
    *,
    feeds: Iterable[RSSFeed] = DEFAULT_RSS_FEEDS,
    now: datetime | None = None,
    window_hours: int = DEFAULT_RSS_WINDOW_HOURS,
    session: Any = None,
) -> OpinionRSSResult:
    """Attach short attributed RSS context only when both fixture teams match.

    Feed items must be recent and published before kickoff. Article webpages are
    never fetched; only feed metadata/title/summary are used and only short titles
    and source links are written into the private analysis note.
    """
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    now_utc = now_utc.astimezone(timezone.utc)
    max_age = timedelta(hours=max(1, int(window_hours)))
    result = OpinionRSSResult(fixtures=[dict(row) for row in fixtures if isinstance(row, dict)])
    client = session if session is not None else requests
    parsed_items: list[dict[str, Any]] = []
    feed_list = list(feeds)
    result.feeds_checked = len(feed_list)
    for feed in feed_list:
        try:
            response = client.get(
                feed.url,
                headers={
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
                    "User-Agent": "KimathyPrivateDailyAnalysis/1.0 (RSS reader; personal use)",
                },
                timeout=15,
            )
        except requests.RequestException:
            result.warnings.append(f"{feed.name}: RSS feed could not be reached; skipped.")
            continue
        except Exception:
            result.warnings.append(f"{feed.name}: RSS request failed; skipped.")
            continue
        status = int(getattr(response, "status_code", 0) or 0)
        if status in {403, 429}:
            result.warnings.append(f"{feed.name}: source declined access (HTTP {status}); no retry or bypass attempted.")
            continue
        if status < 200 or status >= 300:
            result.warnings.append(f"{feed.name}: RSS request returned HTTP {status}; skipped.")
            continue
        content = getattr(response, "content", b"")
        if len(content) > MAX_FEED_BYTES:
            result.warnings.append(f"{feed.name}: RSS feed exceeded the size limit; skipped.")
            continue
        parsed_items.extend(_parse_feed(content, feed))

    cutoff = now_utc - max_age
    recent_items = [
        item for item in parsed_items
        if cutoff <= item["published_at"] <= now_utc + timedelta(minutes=5)
    ]
    result.feed_items_read = len(recent_items)
    for candidate in result.fixtures:
        if feed_list:
            sport = str(candidate.get("sport_type", "")).strip().lower()
            applicable = [feed for feed in feed_list if feed.sport_type in (None, sport)]
        else:
            applicable = []
        allowed_sources = {feed.name for feed in applicable}
        match_time = _candidate_time(candidate)
        if not match_time:
            continue
        home, away = candidate.get("home_team"), candidate.get("away_team")
        if not home or not away:
            parts = str(candidate.get("match_name", "")).split(" vs ", 1)
            if len(parts) == 2:
                home, away = parts[0].strip(), parts[1].strip()
        if not home or not away:
            continue
        potential: list[dict[str, Any]] = []
        for item in recent_items:
            if item["source_name"] not in allowed_sources or item["published_at"] > match_time:
                continue
            text = f"{item['title']} {item.get('summary', '')}"
            if _team_mentioned(home, text) and _team_mentioned(away, text):
                potential.append(item)
        potential.sort(key=lambda item: item["published_at"], reverse=True)
        matched: list[dict[str, Any]] = []
        seen_links: set[str] = set()
        seen_titles: set[str] = set()
        for item in potential:
            title_key = _title_dedupe_key(item["title"])
            if item["link"] in seen_links or (title_key and title_key in seen_titles):
                continue
            seen_links.add(item["link"])
            if title_key:
                seen_titles.add(title_key)
            matched.append(item)
        if not matched:
            continue
        _append_opinion_note(candidate, matched)
        result.matched_fixtures += 1
        result.matched_articles += len(matched)
    return result
