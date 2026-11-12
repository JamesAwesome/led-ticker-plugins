"""`description = "append"`: fold an item's free-text description paragraphs
onto its headline (the critter-feed "comments" use case)."""

import unittest.mock as mock

import pytest

from led_ticker_rss.rss import RSSFeedMonitor, fold_description

CRITTER_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Critters</title>
    <item>
      <title>Saw a Deer — November 11, 2026 · 9:17 PM</title>
      <description><![CDATA[<p>Backyard</p>
        <p>📅 November 11, 2026 · 9:17 PM</p>
        <p>Crossing my street! </p>]]></description>
    </item>
    <item>
      <title>Saw a Sparrow — November 11, 2026 · 9:06 AM</title>
      <description><![CDATA[<p>📅 November 11, 2026 · 9:06 AM</p>]]></description>
    </item>
    <item>
      <title>Saw a Hawk — November 10, 2026 · 4:00 PM</title>
      <description><![CDATA[<p>📅 November 10, 2026 · 4:00 PM</p>
        <img src="https://example.com/x.jpg" alt="" /><p>Hunting</p>]]></description>
    </item>
    <item>
      <title>No description</title>
    </item>
  </channel>
</rss>
"""


@pytest.fixture
def critter_session():
    session = mock.MagicMock()
    response = mock.AsyncMock()
    response.text.return_value = CRITTER_RSS
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = response
    session.get.return_value = ctx
    return session


class TestFoldDescription:
    """Pure helper: title + description HTML → one headline string."""

    def test_appends_free_text_paragraph(self):
        out = fold_description(
            "Saw a Deer — November 11, 2026 · 9:17 PM",
            "<p>📅 November 11, 2026 · 9:17 PM</p><p>Crossing my street! </p>",
        )
        assert out == "Saw a Deer — November 11, 2026 · 9:17 PM · Crossing my street!"

    def test_paragraph_already_in_title_is_dropped(self):
        """The date line repeats the title (modulo a leading emoji) → gone."""
        out = fold_description("Saw a Sparrow — Nov 11", "<p>📅 Nov 11</p>")
        assert out == "Saw a Sparrow — Nov 11"

    def test_no_description_returns_title(self):
        assert fold_description("Plain", "") == "Plain"
        assert fold_description("Plain", None) == "Plain"

    def test_images_contribute_nothing(self):
        out = fold_description("T", '<img src="https://example.com/x.jpg" alt="" />')
        assert out == "T"

    def test_skip_patterns_drop_matching_paragraphs(self):
        out = fold_description(
            "T",
            "<p>Backyard</p><p>Crossing my street!</p>",
            skip_patterns=[r"^Backyard$"],
        )
        assert out == "T · Crossing my street!"

    def test_skip_patterns_are_case_insensitive_search(self):
        out = fold_description(
            "T", "<p>Seen while hunting</p><p>ok</p>", skip_patterns=["HUNT"]
        )
        assert out == "T · ok"

    def test_multiple_paragraphs_joined_with_separator(self):
        out = fold_description("T", "<p>one</p><p>two</p>")
        assert out == "T · one · two"

    def test_br_splits_and_entities_unescaped(self):
        out = fold_description("T", "<p>salt &amp; pepper<br/>second</p>")
        assert out == "T · salt & pepper · second"

    def test_whitespace_only_paragraphs_dropped(self):
        out = fold_description("T", "<p>  </p><p>\n</p><p>real</p>")
        assert out == "T · real"


class TestDescriptionKnob:
    async def test_default_is_title_only(self, critter_session):
        """Back-compat: without the knob, stories are exactly the headline."""
        feed = RSSFeedMonitor(session=critter_session, feed_url="https://x/feed")
        await feed.update()
        assert feed.feed_stories[0].text == "Saw a Deer — November 11, 2026 · 9:17 PM"

    async def test_append_folds_note_into_headline(self, critter_session):
        feed = RSSFeedMonitor(
            session=critter_session, feed_url="https://x/feed", description="append"
        )
        await feed.update()
        texts = [s.text for s in feed.feed_stories]
        assert texts == [
            "Saw a Deer — November 11, 2026 · 9:17 PM · Backyard · Crossing my street!",
            "Saw a Sparrow — November 11, 2026 · 9:06 AM",
            "Saw a Hawk — November 10, 2026 · 4:00 PM · Hunting",
            "No description",
        ]

    async def test_description_skip_applies_to_every_story(self, critter_session):
        feed = RSSFeedMonitor(
            session=critter_session,
            feed_url="https://x/feed",
            description="append",
            description_skip=[r"^Backyard$", r"^Hunting$"],
        )
        await feed.update()
        texts = [s.text for s in feed.feed_stories]
        assert (
            texts[0] == "Saw a Deer — November 11, 2026 · 9:17 PM · Crossing my street!"
        )
        assert texts[2] == "Saw a Hawk — November 10, 2026 · 4:00 PM"

    async def test_title_is_never_folded(self, critter_session):
        feed = RSSFeedMonitor(
            session=critter_session, feed_url="https://x/feed", description="append"
        )
        await feed.update()
        assert feed.feed_title.text == "Critters"


class TestValidateConfig:
    def test_clean_config_has_no_messages(self):
        assert RSSFeedMonitor.validate_config({"feed_url": "https://x"}) == []
        assert (
            RSSFeedMonitor.validate_config(
                {
                    "feed_url": "https://x",
                    "description": "append",
                    "description_skip": ["^a$"],
                }
            )
            == []
        )

    def test_bad_description_value(self):
        msgs = RSSFeedMonitor.validate_config({"description": "yes"})
        assert len(msgs) == 1
        assert "description" in msgs[0] and "append" in msgs[0]

    def test_description_skip_must_be_list_of_str(self):
        assert RSSFeedMonitor.validate_config({"description_skip": "^a$"})
        assert RSSFeedMonitor.validate_config({"description_skip": ["^a$", 3]})

    def test_description_skip_invalid_regex(self):
        msgs = RSSFeedMonitor.validate_config(
            {"description": "append", "description_skip": ["(unclosed"]}
        )
        assert len(msgs) == 1
        assert "(unclosed" in msgs[0]

    def test_description_skip_without_append_warns_in_message(self):
        msgs = RSSFeedMonitor.validate_config({"description_skip": ["^a$"]})
        assert len(msgs) == 1
        assert 'description = "append"' in msgs[0]
