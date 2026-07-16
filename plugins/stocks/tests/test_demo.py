from led_ticker_stocks.demo import DemoFeed, seed_quotes
from led_ticker_stocks.state import MarketState


def test_seed_is_deterministic_and_has_data():
    a = seed_quotes(["AAPL", "MSFT"])
    b = seed_quotes(["AAPL", "MSFT"])
    assert a["AAPL"].price == b["AAPL"].price
    assert a["AAPL"].has_data


def test_step_moves_a_price_and_stamps_flash():
    feed = DemoFeed(["AAPL", "MSFT", "NVDA"])
    before = {s: q.price for s, q in feed.quotes.items()}
    for _ in range(50):
        feed.step()
    after = {s: q.price for s, q in feed.quotes.items()}
    assert any(after[s] != before[s] for s in before)
    assert any(q.flash_t is not None for q in feed.quotes.values())


def test_seeded_demo_quotes_are_open_with_magnitude_decimals():
    q = seed_quotes(["AAPL"])["AAPL"]
    assert q.state is MarketState.OPEN
    assert q.dp_decimals == 2  # _seed_price is 50-500 -> >=10 -> 2
