"""RSS feed monitor widget."""

import asyncio
import itertools
import logging
import re
from html.parser import HTMLParser
from typing import Any, Self

import aiohttp
import attrs
import feedparser
from led_ticker.plugin import (
    FONT_DEFAULT,
    Color,
    Font,
    TickerMessage,
    run_monitor_loop,
    spawn_tracked,
)
from led_ticker.plugin import (
    colors as _colors,
)

logger: logging.Logger = logging.getLogger(__name__)

_DESCRIPTION_MODES: frozenset[str] = frozenset({"off", "append"})
_DESCRIPTION_SEPARATOR = " · "
# Tags that end one paragraph and start the next when flattening the
# description's HTML. Everything else (b/i/a/span/img/...) is inline.
_BLOCK_TAGS: frozenset[str] = frozenset(
    {"p", "br", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}
)


class _ParagraphSplitter(HTMLParser):
    """Flatten an HTML fragment into a list of plain-text paragraphs.

    Block tags split paragraphs; inline tags are dropped but their text is
    kept; `<img>` contributes nothing (alt text is usually empty on feeds).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._buf: list[str] = []

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if text:
            self.paragraphs.append(text)

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        self._buf.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def _normalize(text: str) -> str:
    """Lowercase alphanumerics only — for "is this paragraph already in the
    title?" so a leading emoji / punctuation drift doesn't defeat the check."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def fold_description(
    title: str,
    description_html: str | None,
    *,
    skip_patterns: list[str] | None = None,
) -> str:
    """Append an item's description paragraphs to its ``title``.

    The description is flattened to plain-text paragraphs; a paragraph is
    dropped when it is blank, when its alphanumeric content already appears
    in the title (feeds that restate the headline's date/subject in the
    body), or when any ``skip_patterns`` regex matches it (case-insensitive
    ``re.search``). Survivors are joined onto the title with ``" · "``. No
    survivors → the title is returned unchanged.
    """
    if not description_html:
        return title
    splitter = _ParagraphSplitter()
    splitter.feed(description_html)
    splitter.close()
    title_norm = _normalize(title)
    skips = [re.compile(pat, re.IGNORECASE) for pat in (skip_patterns or [])]
    kept: list[str] = []
    for para in splitter.paragraphs:
        norm = _normalize(para)
        if not norm:
            continue
        if norm in title_norm:
            continue
        if any(rx.search(para) for rx in skips):
            continue
        kept.append(para)
    if not kept:
        return title
    return _DESCRIPTION_SEPARATOR.join([title, *kept])


@attrs.define
class RSSFeedMonitor:
    """Fetches and displays headlines from an RSS feed."""

    session: aiohttp.ClientSession
    feed_url: str
    padding: int = 6
    colors: itertools.cycle[Color] = attrs.Factory(
        lambda: itertools.cycle([_colors.DEFAULT_COLOR, _colors.RED, _colors.GREEN])
    )
    max_stories: int = 5
    # When set, every story TickerMessage gets this color/provider
    # (e.g. `font_color = "rainbow"` paints all stories rainbow).
    # When unset (None), fall back to the legacy 3-color rotation
    # (DEFAULT_COLOR / RED / GREEN) so existing configs keep working.
    font_color: Any = attrs.field(default=None, kw_only=True)
    bg_color: Color | None = attrs.field(default=None, kw_only=True)
    font: Font = attrs.field(default=attrs.Factory(lambda: FONT_DEFAULT), kw_only=True)
    # "off" (default): each story is the item's title. "append": the item's
    # description is flattened to text paragraphs and folded onto the title
    # (see `fold_description`) — how a feed's free-text notes/comments reach
    # the panel. `description_skip` regexes drop paragraphs you don't want.
    description: str = attrs.field(default="off", kw_only=True)
    description_skip: list[str] = attrs.field(factory=list, kw_only=True)
    feed_title: TickerMessage | None = attrs.field(init=False, default=None)
    feed_stories: list[TickerMessage] = attrs.field(init=False, factory=list)

    def _story_color(self) -> Any:
        """Per-story color: `font_color` if set, else next from the
        legacy cycle. Called once per story in `update()`."""
        if self.font_color is not None:
            return self.font_color
        return next(self.colors)

    @classmethod
    def validate_config(cls, cfg: dict[str, Any]) -> list[str]:
        """Pre-coercion config check, run by the engine via validate_widget_cfg.

        Returns message strings (does NOT raise); the engine turns any
        returned messages into a pre-flight ValueError.
        """
        msgs: list[str] = []
        mode = cfg.get("description", "off")
        if mode not in _DESCRIPTION_MODES:
            msgs.append(
                f"rss.feed description={mode!r} must be one of "
                f'{sorted(_DESCRIPTION_MODES)} ("append" folds each item\'s '
                "description paragraphs onto its headline)."
            )
        skip = cfg.get("description_skip")
        if skip is not None:
            if not isinstance(skip, list) or not all(isinstance(p, str) for p in skip):
                msgs.append(
                    f"rss.feed description_skip={skip!r} must be a list of "
                    "regex strings."
                )
            else:
                for pat in skip:
                    try:
                        re.compile(pat)
                    except re.error as e:
                        msgs.append(
                            f"rss.feed description_skip pattern {pat!r} "
                            f"is not a valid regex: {e}"
                        )
                if mode == "off":
                    msgs.append(
                        "rss.feed description_skip has no effect without "
                        'description = "append".'
                    )
        return msgs

    def _story_text(self, item: Any) -> str:
        title: str = item.get("title", "")
        if self.description == "append":
            return fold_description(
                title, item.get("summary"), skip_patterns=self.description_skip
            )
        return title

    @classmethod
    async def start(
        cls,
        session: aiohttp.ClientSession,
        feed_url: str,
        update_interval: int = 1800,
        **kwargs: Any,
    ) -> Self:
        widget = cls(session=session, feed_url=feed_url, **kwargs)
        await widget.update()
        spawn_tracked(run_monitor_loop(widget, update_interval))
        return widget

    async def update(self) -> None:
        logger.info("Updating RSS Feed from: %s", self.feed_url)
        async with self.session.get(self.feed_url) as response:
            feed_data = await response.text()
            feed = await asyncio.to_thread(feedparser.parse, feed_data)
            self.feed_title = TickerMessage(
                feed["channel"]["title"],  # type: ignore[index]
                font=self.font,
                font_color=self._story_color(),
                bg_color=self.bg_color,
            )
            self.feed_stories = [
                TickerMessage(
                    self._story_text(item),
                    font=self.font,
                    font_color=self._story_color(),
                    bg_color=self.bg_color,
                )
                for item in itertools.islice(feed["items"], self.max_stories)  # type: ignore[index]
            ]
        logger.info(
            "RSS %s updated: %d stories",
            self.feed_url,
            len(self.feed_stories),
        )
