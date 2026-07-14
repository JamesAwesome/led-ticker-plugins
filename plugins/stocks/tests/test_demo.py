from led_ticker_stocks.demo import DemoFeed, seed_quotes


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
