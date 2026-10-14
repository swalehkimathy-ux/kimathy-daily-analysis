from __future__ import annotations

import unittest
from datetime import datetime, timezone

from engine import prepare_fixture
from providers.opinions_rss import RSSFeed, _sentiment_tone, enrich_with_rss_opinions


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers or {}, "timeout": timeout})
        return self.response


def fixture():
    return {
        "sport_type": "football",
        "home_team": "Home Lions FC",
        "away_team": "Away Eagles FC",
        "match_name": "Home Lions FC vs Away Eagles FC",
        "match_time": "2026-10-04T12:00:00Z",
        "market_name": "Over 1.5 Goals",
        "market_key": "over_1_5_goals",
        "picked_odds": "1.50",
        "features": {},
        "analysis_note": "Odds quote received.",
        "source": "the-odds-api",
    }


def rss_item(title, link, date="Sun, 04 Oct 2026 06:00:00 GMT", description=""):
    return (
        "<item>"
        f"<title>{title}</title><link>{link}</link><pubDate>{date}</pubDate>"
        f"<description><![CDATA[{description}]]></description>"
        "</item>"
    )


class RSSOpinionTests(unittest.TestCase):
    NOW = datetime(2026, 10, 4, 7, 0, tzinfo=timezone.utc)
    FEED = RSSFeed("Test Sports Desk", "https://news.example/rss.xml", "football")

    def test_rss_context_is_attributed_and_does_not_pass_evidence_gate(self):
        xml = (
            "<?xml version='1.0'?><rss version='2.0'><channel>"
            + rss_item(
                "Preview: Home Lions FC v Away Eagles FC",
                "https://news.example/match-preview",
                description=(
                    "The preview expects Home Lions FC to win and describes them as confident. "
                    "Away Eagles FC have injury doubts before kickoff. Full article details are not saved."
                ),
            )
            + "</channel></rss>"
        ).encode()
        session = FakeSession(FakeResponse(xml))
        result = enrich_with_rss_opinions(
            [fixture()], feeds=[self.FEED], now=self.NOW, session=session
        )

        self.assertEqual(result.feeds_checked, 1)
        self.assertEqual(result.feed_items_read, 1)
        self.assertEqual(result.matched_fixtures, 1)
        self.assertEqual(result.matched_articles, 1)
        row = result.fixtures[0]
        self.assertIn("Test Sports Desk", row["analysis_note"])
        self.assertIn("Preview: Home Lions FC v Away Eagles FC", row["analysis_note"])
        self.assertIn("https://news.example/match-preview", row["analysis_note"])
        self.assertIn("team news", row["analysis_note"])
        self.assertIn("This is context only, not a win probability", row["analysis_note"])
        self.assertNotIn("Full article details are not saved", row["analysis_note"])
        self.assertIn("rss-news", row["source"])
        self.assertIsNone(prepare_fixture(row), "RSS must not pass the market-specific evidence gate")
        self.assertEqual(len(session.calls), 1)
        self.assertIn("User-Agent", session.calls[0]["headers"])

    def test_requires_both_teams_and_recent_pre_kickoff_article(self):
        xml = (
            "<rss><channel>"
            + rss_item("Only Home Lions FC are mentioned", "https://news.example/one")
            + rss_item(
                "Both teams Home Lions FC and Away Eagles FC",
                "https://news.example/old",
                date="Wed, 30 Sep 2026 06:00:00 GMT",
            )
            + rss_item(
                "Both teams Home Lions FC and Away Eagles FC",
                "https://news.example/after-kickoff",
                date="Sun, 04 Oct 2026 12:30:00 GMT",
            )
            + "</channel></rss>"
        ).encode()
        result = enrich_with_rss_opinions(
            [fixture()], feeds=[self.FEED], now=self.NOW, session=FakeSession(FakeResponse(xml))
        )

        self.assertEqual(result.matched_fixtures, 0)
        self.assertEqual(result.matched_articles, 0)
        self.assertEqual(result.fixtures[0]["analysis_note"], "Odds quote received.")
        self.assertNotIn("rss-news", result.fixtures[0]["source"])

    def test_atom_feed_parses_and_deduplicates_same_article_link(self):
        xml = b"""<?xml version='1.0'?>
        <feed xmlns='http://www.w3.org/2005/Atom'>
          <entry>
            <title>Home Lions FC preview against Away Eagles FC</title>
            <link rel='alternate' href='https://news.example/atom-preview'/>
            <published>2026-10-04T05:00:00Z</published>
            <summary>Prediction discussion from the team news desk.</summary>
          </entry>
          <entry>
            <title>Duplicate item Home Lions FC versus Away Eagles FC</title>
            <link rel='alternate' href='https://news.example/atom-preview'/>
            <updated>2026-10-04T05:30:00Z</updated>
            <summary>Another syndicated entry.</summary>
          </entry>
        </feed>"""
        result = enrich_with_rss_opinions(
            [fixture()], feeds=[self.FEED], now=self.NOW, session=FakeSession(FakeResponse(xml))
        )

        self.assertEqual(result.feed_items_read, 2)
        self.assertEqual(result.matched_fixtures, 1)
        self.assertEqual(result.matched_articles, 1)
        self.assertEqual(result.fixtures[0]["analysis_note"].count("https://news.example/atom-preview"), 1)

    def test_a_403_is_respected_without_retry_or_bypass(self):
        session = FakeSession(FakeResponse(b"", status_code=403))
        result = enrich_with_rss_opinions(
            [fixture()], feeds=[self.FEED], now=self.NOW, session=session
        )
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(result.feed_items_read, 0)
        self.assertEqual(result.matched_fixtures, 0)
        self.assertTrue(any("HTTP 403" in warning for warning in result.warnings))
        self.assertEqual(result.fixtures[0]["analysis_note"], "Odds quote received.")

    def test_sport_specific_feed_is_not_attached_to_other_sport(self):
        basketball = fixture()
        basketball["sport_type"] = "basketball"
        xml = (
            "<rss><channel>"
            + rss_item("Home Lions FC versus Away Eagles FC preview", "https://news.example/game")
            + "</channel></rss>"
        ).encode()
        result = enrich_with_rss_opinions(
            [basketball], feeds=[self.FEED], now=self.NOW, session=FakeSession(FakeResponse(xml))
        )
        self.assertEqual(result.matched_fixtures, 0)
        self.assertNotIn("rss-news", result.fixtures[0]["source"])

    def test_duplicate_headlines_from_different_links_are_counted_once(self):
        headline = "Home Lions FC vs Away Eagles FC preview"
        xml = (
            "<rss><channel>"
            + rss_item(headline, "https://news.example/story-a")
            + rss_item(headline, "https://news.example/story-b")
            + "</channel></rss>"
        ).encode()
        result = enrich_with_rss_opinions(
            [fixture()], feeds=[self.FEED], now=self.NOW, session=FakeSession(FakeResponse(xml))
        )
        self.assertEqual(result.matched_articles, 1)
        self.assertEqual(result.fixtures[0]["analysis_note"].count("preview (https://news.example/"), 1)

    def test_common_team_aliases_are_supported_conservatively(self):
        alias_fixture = fixture()
        alias_fixture["home_team"] = "Manchester United FC"
        alias_fixture["away_team"] = "Tottenham Hotspur"
        xml = (
            "<rss><channel>"
            + rss_item("Man Utd preview ahead of Spurs clash", "https://news.example/aliases")
            + "</channel></rss>"
        ).encode()
        result = enrich_with_rss_opinions(
            [alias_fixture], feeds=[self.FEED], now=self.NOW, session=FakeSession(FakeResponse(xml))
        )
        self.assertEqual(result.matched_fixtures, 1)
        self.assertIn("https://news.example/aliases", result.fixtures[0]["analysis_note"])

    def test_keyword_tags_use_word_boundaries(self):
        tone, positive, caution, topics = _sentiment_tone(["An outlet opened a window of opportunity."])
        self.assertEqual(tone, "neutral/no-clear-opinion")
        self.assertEqual(positive, 0)
        self.assertEqual(caution, 0)
        self.assertEqual(topics, [])


if __name__ == "__main__":
    unittest.main()
