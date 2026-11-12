"""RSS feed monitor widget."""

import asyncio
import itertools
import logging
import re
from html.parser import HTMLParser
from typing import Any, ClassVar, Self

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
DEFAULT_DESCRIPTION_MAX_CHARS = 200
# Dedup is TOKEN-based: a paragraph restates the title (and is dropped) when
# its words, in order, are a contiguous run of the title's words AND it has at
# least this many words (or equals the whole title). Two short words ("Nov
# 11", "9:17 PM") are a restatement; one word echoing a title word ("Hunting")
# is a note and survives.
_DEDUP_MIN_TOKENS = 2
_TOKEN_RE = re.compile(r"[^\W_]+")
# Tags that end one paragraph and start the next when flattening the
# description's HTML. Everything else (b/i/a/span/img/...) is inline.
_BLOCK_TAGS: frozenset[str] = frozenset(
    {"p", "br", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}
)
# Elements whose character data is code/markup, never prose.
_SKIP_CONTENT_TAGS: frozenset[str] = frozenset({"script", "style", "textarea"})


class _ParagraphSplitter(HTMLParser):
    """Flatten an HTML fragment into a list of plain-text paragraphs.

    Block tags split paragraphs; inline tags are dropped but their text is
    kept; `<img>` has no text node so contributes nothing; the contents of
    `<script>`/`<style>`/`<textarea>` are discarded; a literal `<![CDATA[..]]>`
    (a feed that double-wrapped) is kept as text.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragraphs: list[str] = []
        self._buf: list[str] = []
        self._skip_depth = 0

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if text:
            self.paragraphs.append(text)

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in _SKIP_CONTENT_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_CONTENT_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._buf.append(data)

    def unknown_decl(self, data: str) -> None:
        # A literal `<![CDATA[..]]>` (feed double-wrapped its HTML) is text.
        # (Inside <script>/<style> the stdlib treats it as raw text and never
        # routes it here, so no skip-depth check is needed.)
        if data.startswith("CDATA["):
            self._buf.append(data[len("CDATA[") :])

    def close(self) -> None:
        super().close()
        self._flush()


def _tokens(text: str) -> list[str]:
    """Lowercased alphanumeric words — the unit title-dedup compares on, so a
    leading emoji / punctuation drift ("📅", "—", ":") doesn't defeat it."""
    return _TOKEN_RE.findall(text.lower())


def _is_contiguous_run(needle: list[str], hay: list[str]) -> bool:
    n = len(needle)
    return any(hay[i : i + n] == needle for i in range(len(hay) - n + 1))


def _restates_title(para: str, title_tokens: list[str]) -> bool:
    toks = _tokens(para)
    if not toks or not title_tokens:
        return False
    if toks == title_tokens:
        return True
    return len(toks) >= _DEDUP_MIN_TOKENS and _is_contiguous_run(toks, title_tokens)


def _truncate(text: str, max_chars: int) -> str:
    """Cut ``text`` to at most ``max_chars`` characters INCLUDING the ellipsis
    that marks the cut, at a word boundary when there is one, and never ending
    on a dangling separator. ``max_chars <= 0`` → no cap."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" " + _DESCRIPTION_SEPARATOR.strip()) + "…"


def fold_description(
    title: str,
    description_html: str | None,
    *,
    skip_patterns: list[str] | None = None,
    max_chars: int = DEFAULT_DESCRIPTION_MAX_CHARS,
    is_html: bool = True,
) -> str:
    """Append an item's description paragraphs to its ``title``.

    The description is flattened to plain-text paragraphs (``is_html=False``
    for a feed that declares a plain-text summary: the whole string is one
    paragraph and ``<``/``&`` are literal). A paragraph is dropped when it is
    blank, when it restates the title (see ``_restates_title``: its words are
    a contiguous run of 2+ title words, or all of them — feeds that repeat the
    headline's date/subject in the body), or when any ``skip_patterns`` regex
    matches it (case-insensitive ``re.search``). Survivors are joined with
    ``" · "``, capped at ``max_chars`` characters including the ellipsis
    (word boundary; ``0`` = no cap — the cap applies to the folded part only,
    never the title), then appended to the title. No survivors → the title
    unchanged. An empty title (RSS 2.0 allows description-only items) → the
    folded text alone.
    """
    if not description_html:
        return title
    if is_html:
        splitter = _ParagraphSplitter()
        splitter.feed(description_html)
        splitter.close()
        paragraphs = splitter.paragraphs
    else:
        paragraphs = [" ".join(description_html.split())]
    title_tokens = _tokens(title)
    skips = [re.compile(pat, re.IGNORECASE) for pat in (skip_patterns or [])]
    kept: list[str] = []
    for para in paragraphs:
        if not para:
            continue
        if _restates_title(para, title_tokens):
            continue
        if any(rx.search(para) for rx in skips):
            continue
        kept.append(para)
    if not kept:
        return title
    folded = _truncate(_DESCRIPTION_SEPARATOR.join(kept), max_chars)
    if not title:
        return folded
    return f"{title}{_DESCRIPTION_SEPARATOR}{folded}"


@attrs.define
class RSSFeedMonitor:
    """Fetches and displays headlines from an RSS feed."""

    _LIST_FIELD_HINTS: ClassVar[dict] = {
        "description": (
            '"off" | "append"',
            "append = fold each item's description paragraphs onto its headline",
            '"off"',
        ),
        "description_skip": (
            "list of regex strings",
            "description paragraphs matching any (case-insensitive search) are dropped",
            "[]",
        ),
        "description_max_chars": (
            "int",
            "cap on the folded description text (chars incl. the ellipsis); 0 = no cap",
            str(DEFAULT_DESCRIPTION_MAX_CHARS),
        ),
    }

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
    # Cap on the folded description text (chars; 0 = uncapped). feedparser
    # falls back to `content:encoded` / Atom <content> when an item has no
    # <description>, so without a cap a full article body would scroll.
    description_max_chars: int = attrs.field(
        default=DEFAULT_DESCRIPTION_MAX_CHARS, kw_only=True
    )
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
        max_chars = cfg.get("description_max_chars")
        if max_chars is not None and (
            isinstance(max_chars, bool)
            or not isinstance(max_chars, int)
            or max_chars < 0
        ):
            msgs.append(
                f"rss.feed description_max_chars={max_chars!r} must be a "
                "non-negative integer (0 = no cap)."
            )
        return msgs

    @classmethod
    def validate_config_warnings(cls, cfg: dict[str, Any], ctx: Any) -> list[str]:
        """Advisory sibling of ``validate_config`` (surfaced by
        ``led-ticker validate`` as warnings, never errors)."""
        if cfg.get("description_skip") and cfg.get("description", "off") == "off":
            return [
                "rss.feed description_skip has no effect without "
                'description = "append".'
            ]
        return []

    def _story_text(self, item: Any) -> str:
        """Headline for one feed item; "" when the item has nothing to show
        (caller skips those). feedparser maps RSS <description> / Atom
        <summary> — falling back to content:encoded / <content> — to
        ``summary``; a missing <title> is simply absent."""
        title: str = item.get("title") or ""
        if self.description == "append":
            detail = item.get("summary_detail") or {}
            return fold_description(
                title,
                item.get("summary"),
                skip_patterns=self.description_skip,
                max_chars=self.description_max_chars,
                is_html=detail.get("type") != "text/plain",
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
            # Filter BEFORE capping so a skipped item (nothing to show)
            # doesn't eat one of the `max_stories` panel slots.
            texts = (t for t in map(self._story_text, feed["items"]) if t)  # type: ignore[index]
            self.feed_stories = [
                TickerMessage(
                    text,
                    font=self.font,
                    font_color=self._story_color(),
                    bg_color=self.bg_color,
                )
                for text in itertools.islice(texts, self.max_stories)
            ]
        logger.info(
            "RSS %s updated: %d stories",
            self.feed_url,
            len(self.feed_stories),
        )
