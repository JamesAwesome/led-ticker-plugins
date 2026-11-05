"""flair.accordion — pure motion math: phase progress ``k`` in [0, 1] to a
per-card x position. No canvas, no painting.

Every ``*_decks`` function positions ALL of a plan's decks from ONE shared
anchor / hand trajectory, derived from the union of the decks' extents, so
two-row decks move in lockstep (spec §Two-row: "the same anchor"). Each
deck keeps its own slots and peek. For a single deck the union is that
deck, so the single-deck wrappers (``sweep_out`` ...) are the same math.
"""

from collections.abc import Sequence

from led_ticker_flair.flair.accordion_cards import Deck


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _max_right_edge(deck: Deck) -> float:
    """max_i(i*P + w_i): the stacked deck's right edge relative to its anchor."""
    return max(i * deck.peek + c.width for i, c in enumerate(deck.cards))


def _live(decks: Sequence[Deck]) -> list[Deck]:
    return [d for d in decks if d.cards]


def _sweep_start(deck: Deck, W: int) -> float:
    """The hand position at which no card of ``deck`` is scooped yet."""
    p = deck.peek
    n = len(deck.cards)
    return max(W - (n - 1) * p, max(c.slot - i * p for i, c in enumerate(deck.cards)))


def sweep_out_decks(decks: Sequence[Deck], W: int, k: float) -> list[list[float]]:
    live = _live(decks)
    if not live:
        return [[] for _ in decks]
    # One shared hand: it starts where no deck has a scooped card (k=0 is
    # every deck's slots) and ends past every deck's off-panel point.
    g0 = max(_sweep_start(d, W) for d in live)
    g1 = min(-_max_right_edge(d) - 1 for d in live)
    g = _lerp(g0, g1, k)
    return [
        [min(float(c.slot), g + i * d.peek) for i, c in enumerate(d.cards)]
        for d in decks
    ]


def sweep_in_decks(decks: Sequence[Deck], W: int, k: float) -> list[list[float]]:
    live = _live(decks)
    if not live:
        return [[] for _ in decks]
    h1 = min(min(c.slot - i * d.peek for i, c in enumerate(d.cards)) for d in live)
    h = _lerp(float(W), h1, k)
    return [
        [max(float(c.slot), h + i * d.peek) for i, c in enumerate(d.cards)]
        for d in decks
    ]


def _stretch(deck: Deck, a: float, s: float) -> list[float]:
    cards = deck.cards
    s0 = cards[0].slot
    p = deck.peek
    return [a + _lerp(i * p, c.slot - s0, s) for i, c in enumerate(cards)]


def _stretch_decks(
    decks: Sequence[Deck], a: float, u0: float, s: float
) -> list[list[float]]:
    """Each deck's anchor is the shared anchor ``a`` plus that deck's fixed
    offset from the union's first slot ``u0``: one common translation."""
    return [
        _stretch(d, a + (d.cards[0].slot - u0), s) if d.cards else [] for d in decks
    ]


def stretch_out_decks(decks: Sequence[Deck], W: int, k: float) -> list[list[float]]:
    live = _live(decks)
    if not live:
        return [[] for _ in decks]
    u0 = float(min(d.cards[0].slot for d in live))
    # End anchor: every deck, stacked at its own offset, is fully off-panel.
    a1 = min(-_max_right_edge(d) - 1 - (d.cards[0].slot - u0) for d in live)
    return _stretch_decks(decks, _lerp(u0, a1, k), u0, 1 - k)


def stretch_in_decks(decks: Sequence[Deck], W: int, k: float) -> list[list[float]]:
    live = _live(decks)
    if not live:
        return [[] for _ in decks]
    u0 = float(min(d.cards[0].slot for d in live))
    return _stretch_decks(decks, _lerp(float(W), u0, k), u0, k)


# --- single-deck forms (the union of one deck is that deck) ----------------


def sweep_out(deck: Deck, W: int, k: float) -> list[float]:
    return sweep_out_decks([deck], W, k)[0]


def sweep_in(deck: Deck, W: int, k: float) -> list[float]:
    return sweep_in_decks([deck], W, k)[0]


def stretch_out(deck: Deck, W: int, k: float) -> list[float]:
    return stretch_out_decks([deck], W, k)[0]


def stretch_in(deck: Deck, W: int, k: float) -> list[float]:
    return stretch_in_decks([deck], W, k)[0]
