"""flair.accordion — pure motion math: phase progress ``k`` in [0, 1] to a
per-card x position. No canvas, no painting."""

from led_ticker_flair.flair.accordion_cards import Deck


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _max_right_edge(deck: Deck) -> float:
    """max_i(i*P + w_i): the stacked deck's right edge relative to its anchor."""
    return max(i * deck.peek + c.width for i, c in enumerate(deck.cards))


def sweep_out(deck: Deck, W: int, k: float) -> list[float]:
    cards = deck.cards
    if not cards:
        return []
    p = deck.peek
    n = len(cards)
    g0 = max(W - (n - 1) * p, max(c.slot - i * p for i, c in enumerate(cards)))
    g1 = -_max_right_edge(deck) - 1
    g = _lerp(g0, g1, k)
    return [min(float(c.slot), g + i * p) for i, c in enumerate(cards)]


def sweep_in(deck: Deck, W: int, k: float) -> list[float]:
    cards = deck.cards
    if not cards:
        return []
    p = deck.peek
    h1 = min(c.slot - i * p for i, c in enumerate(cards))
    h = _lerp(float(W), h1, k)
    return [max(float(c.slot), h + i * p) for i, c in enumerate(cards)]


def _stretch(deck: Deck, a: float, s: float) -> list[float]:
    cards = deck.cards
    s0 = cards[0].slot
    p = deck.peek
    return [a + _lerp(i * p, c.slot - s0, s) for i, c in enumerate(cards)]


def stretch_out(deck: Deck, W: int, k: float) -> list[float]:
    if not deck.cards:
        return []
    a1 = -_max_right_edge(deck) - 1
    a = _lerp(float(deck.cards[0].slot), a1, k)
    return _stretch(deck, a, 1 - k)


def stretch_in(deck: Deck, W: int, k: float) -> list[float]:
    if not deck.cards:
        return []
    a = _lerp(float(W), float(deck.cards[0].slot), k)
    return _stretch(deck, a, k)
