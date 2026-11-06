"""flair.accordion — occluding compositor: paint one deck at given card
positions, topmost card wins per column. Paints only lit card pixels, so
the section background shows through everywhere else."""

from collections.abc import Callable, Sequence

from led_ticker_flair.flair.accordion_cards import Deck


def compose(
    deck: Deck,
    positions: Sequence[float],
    W: int,
    set_px: Callable[[int, int, int, int, int], None],
    *,
    mirror: bool,
) -> None:
    xs = [round(p) for p in positions]
    owner = [-1] * W
    for i, card in enumerate(deck.cards):
        lo = max(xs[i], 0)
        hi = min(xs[i] + card.width, W)
        for x in range(lo, hi):
            owner[x] = i
    for i, card in enumerate(deck.cards):
        xi = xs[i]
        for dx, y, (r, g, b) in card.pixels:
            x = xi + dx
            if 0 <= x < W and owner[x] == i:
                set_px(W - 1 - x if mirror else x, y, r, g, b)
