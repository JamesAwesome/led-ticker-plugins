"""`description = "append"`: fold an item's free-text description paragraphs
onto its headline (the critter-feed "comments" use case)."""

import unittest.mock as mock

import pytest

from led_ticker_rss.rss import RSSFeedMonitor, fold_description

CRITTER_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Critters</title>
    <description>A log of every critter seen.</description>
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
    <item>
      <description><![CDATA[<p>Untitled note</p>]]></description>
    </item>
  </channel>
</rss>
"""


def _session_for(feed_xml: str) -> mock.MagicMock:
    session = mock.MagicMock()
    response = mock.AsyncMock()
    response.text.return_value = feed_xml
    ctx = mock.AsyncMock()
    ctx.__aenter__.return_value = response
    session.get.return_value = ctx
    return session


@pytest.fixture
def critter_session():
    return _session_for(CRITTER_RSS)


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
        out = fold_description(
            "Saw a Sparrow — November 11, 2026 · 9:06 AM",
            "<p>📅 November 11, 2026 · 9:06 AM</p>",
        )
        assert out == "Saw a Sparrow — November 11, 2026 · 9:06 AM"

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

    def test_short_paragraph_echoing_a_title_word_is_kept(self):
        """Dedup targets a RESTATED title (date line), not any word the note
        shares with it — one-word notes must survive."""
        out = fold_description(
            "Hunting season opens", "<p>Hunting</p><p>ok</p><p>season</p>"
        )
        assert out == "Hunting season opens · Hunting · ok · season"

    def test_paragraph_equal_to_title_is_dropped_even_when_short(self):
        assert fold_description("Hunting", "<p>Hunting</p>") == "Hunting"

    def test_empty_title_uses_description_without_leading_separator(self):
        assert fold_description("", "<p>only desc</p>") == "only desc"
        assert fold_description("", "") == ""

    def test_emoji_only_paragraph_is_kept(self):
        assert fold_description("T", "<p>🦌</p>") == "T · 🦌"

    def test_script_style_textarea_contents_are_dropped(self):
        out = fold_description(
            "T",
            "<script>var x = '<p>';</script><style>p{color:red}</style>"
            "<textarea><p>x</p></textarea><p>visible</p>",
        )
        assert out == "T · visible"

    def test_literal_cdata_is_kept_as_text(self):
        out = fold_description("T", "<p><![CDATA[inside cdata]]> after</p>")
        assert out == "T · inside cdata after"

    def test_max_chars_truncates_at_a_word_boundary_with_ellipsis(self):
        out = fold_description("T", "<p>alpha beta gamma delta</p>", max_chars=12)
        assert out == "T · alpha beta…"

    def test_max_chars_zero_means_no_cap(self):
        long = "word " * 100
        out = fold_description("T", f"<p>{long}</p>", max_chars=0)
        assert out == "T · " + long.strip()

    def test_max_chars_counts_the_folded_part_not_the_title(self):
        out = fold_description("a very long title indeed", "<p>short</p>", max_chars=5)
        assert out == "a very long title indeed · short"

    def test_short_restated_date_is_dropped(self):
        """Dedup is token-based: a run of 2+ title words (in order) is a
        restatement no matter how short — "Nov 11", "9:17 PM", "11/11/26"."""
        assert fold_description("Saw a Deer — Nov 11", "<p>📅 Nov 11</p>") == (
            "Saw a Deer — Nov 11"
        )
        assert fold_description("Saw a Deer — 9:17 PM", "<p>🕘 9:17 PM</p>") == (
            "Saw a Deer — 9:17 PM"
        )
        assert fold_description("Deer — 11/11/26", "<p>📅 11/11/26</p>") == (
            "Deer — 11/11/26"
        )

    def test_dedup_is_consistent_within_one_item(self):
        out = fold_description(
            "New York City Marathon results",
            "<p>New York</p><p>Marathon results</p><p>York City Marathon</p>",
        )
        assert out == "New York City Marathon results"

    def test_title_words_out_of_order_are_not_a_restatement(self):
        out = fold_description("Hunting season opens", "<p>season Hunting</p>")
        assert out == "Hunting season opens · season Hunting"

    def test_truncation_never_leaves_a_dangling_separator(self):
        # max_chars=9: cut = "alpha · " → word boundary → "alpha ·" → the
        # separator must be stripped before the ellipsis.
        for n in (8, 9, 10):
            out = fold_description("T", "<p>alpha</p><p>beta gamma</p>", max_chars=n)
            assert out == "T · alpha…", n

    def test_truncation_does_not_double_an_existing_ellipsis(self):
        out = fold_description(
            "T", "<p>Lorem ipsum dolor sit… Read more at the site</p>", max_chars=24
        )
        assert out == "T · Lorem ipsum dolor sit…"

    def test_truncation_result_never_exceeds_max_chars(self):
        for n in range(1, 30):
            out = fold_description(
                "T", "<p>supercalifragilistic ok then</p>", max_chars=n
            )
            folded = out.removeprefix("T · ")
            assert len(folded) <= n, (n, folded)

    def test_plain_text_summary_bypasses_the_html_parser(self):
        out = fold_description("E", "5 < 6 and <y> z &amp; w", is_html=False)
        assert out == "E · 5 < 6 and <y> z &amp; w"

    def test_text_outside_any_block_tag_is_its_own_paragraph(self):
        assert fold_description("T", "lead<p>para") == "T · lead · para"
        assert fold_description("T", "<p>one</p>tail") == "T · one · tail"

    def test_stray_closing_script_tag_does_not_swallow_following_text(self):
        assert fold_description("T", "</script><p>after</p>") == "T · after"

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
            "Untitled note",
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

    async def test_title_less_item_is_dropped_when_off(self, critter_session):
        """`description = "off"` has nothing to show for an item with no
        <title>: skip it rather than emit an empty story (the old code
        KeyError'd the whole update)."""
        feed = RSSFeedMonitor(session=critter_session, feed_url="https://x/feed")
        await feed.update()
        texts = [s.text for s in feed.feed_stories]
        assert "" not in texts
        assert len(texts) == 4

    async def test_max_chars_caps_the_folded_note(self, critter_session):
        feed = RSSFeedMonitor(
            session=critter_session,
            feed_url="https://x/feed",
            description="append",
            description_max_chars=10,
        )
        await feed.update()
        assert feed.feed_stories[0].text == (
            "Saw a Deer — November 11, 2026 · 9:17 PM · Backyard…"
        )

    async def test_engine_accepts_the_knobs_and_rejects_bad_values(self):
        """Through core's validate_widget_cfg (what `led-ticker validate` and
        config-load run): a TOML array for description_skip is accepted, a
        bad `description` is a pre-flight ValueError."""
        from led_ticker import _plugin_loader as L
        from led_ticker.app.factories import validate_widget_cfg

        L.reset_plugins()
        try:
            L.load_plugins(None, entry_points_enabled=True)
            good = {
                "type": "rss.feed",
                "feed_url": "https://x/feed",
                "description": "append",
                "description_skip": ["^📍"],
                "description_max_chars": 120,
            }
            await validate_widget_cfg(good, session=None)
            with pytest.raises(ValueError, match="description"):
                await validate_widget_cfg(
                    {"type": "rss.feed", "feed_url": "https://x", "description": "yes"},
                    session=None,
                )
        finally:
            L.reset_plugins()

    async def test_max_stories_counts_displayable_stories(self):
        """`max_stories` caps what reaches the panel, so a skipped
        (title-less, `"off"`) item must not eat a slot."""
        feed_xml = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
          <item><description>no title</description></item>
          <item><title>Second</title></item>
          <item><title>Third</title></item>
        </channel></rss>"""
        feed = RSSFeedMonitor(
            session=_session_for(feed_xml), feed_url="https://x/feed", max_stories=1
        )
        await feed.update()
        assert [s.text for s in feed.feed_stories] == ["Second"]

    async def test_atom_plain_text_summary_is_not_html_parsed(self):
        feed_xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>
          <entry><title>E</title>
            <summary type="text">5 &lt; 6 and &lt;y&gt; z</summary></entry>
        </feed>"""
        feed = RSSFeedMonitor(
            session=_session_for(feed_xml),
            feed_url="https://x/feed",
            description="append",
        )
        await feed.update()
        assert feed.feed_stories[0].text == "E · 5 < 6 and <y> z"

    async def test_atom_plain_text_content_fallback_is_not_html_parsed(self):
        """No <summary>: feedparser copies <content> into `summary` but
        leaves `summary_detail` unset — the type must come from `content`."""
        feed_xml = """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom"><title>t</title>
          <entry><title>E</title>
            <content type="text">Use &lt;br&gt; tags; 5 &lt; 6</content></entry>
        </feed>"""
        feed = RSSFeedMonitor(
            session=_session_for(feed_xml),
            feed_url="https://x/feed",
            description="append",
        )
        await feed.update()
        assert feed.feed_stories[0].text == "E · Use <br> tags; 5 < 6"

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

    def test_non_string_description_value_gets_the_friendly_message(self):
        for bad in (["append"], {"style": "append"}, 1):
            msgs = RSSFeedMonitor.validate_config({"description": bad})
            assert len(msgs) == 1, bad
            assert "append" in msgs[0] and "must be one of" in msgs[0], msgs

    def test_description_skip_must_be_list_of_str(self):
        assert RSSFeedMonitor.validate_config({"description_skip": "^a$"})
        assert RSSFeedMonitor.validate_config({"description_skip": ["^a$", 3]})

    def test_description_skip_invalid_regex(self):
        msgs = RSSFeedMonitor.validate_config(
            {"description": "append", "description_skip": ["(unclosed"]}
        )
        assert len(msgs) == 1
        assert "(unclosed" in msgs[0]

    def test_description_skip_without_append_is_not_an_error(self):
        assert RSSFeedMonitor.validate_config({"description_skip": ["^a$"]}) == []

    def test_description_skip_without_append_is_an_advisory_warning(self):
        msgs = RSSFeedMonitor.validate_config_warnings(
            {"description_skip": ["^a$"]}, ctx=None
        )
        assert len(msgs) == 1
        assert 'description = "append"' in msgs[0]
        assert (
            RSSFeedMonitor.validate_config_warnings(
                {"description": "append", "description_skip": ["^a$"]}, ctx=None
            )
            == []
        )

    def test_description_max_chars_must_be_non_negative_int(self):
        assert RSSFeedMonitor.validate_config({"description_max_chars": 0}) == []
        assert RSSFeedMonitor.validate_config({"description_max_chars": -1})
        assert RSSFeedMonitor.validate_config({"description_max_chars": True})
        assert RSSFeedMonitor.validate_config({"description_max_chars": "80"})


class TestListFieldHints:
    def test_new_knobs_have_list_field_hints(self):
        hints = RSSFeedMonitor._LIST_FIELD_HINTS
        for name in ("description", "description_skip", "description_max_chars"):
            assert name in hints, name
            assert len(hints[name]) == 3
