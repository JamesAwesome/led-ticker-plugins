# led-ticker-telnet

A telnet/ANSI terminal rendering backend for [led-ticker](https://github.com/JamesAwesome/led-ticker). Watch your LED sign in a terminal over a TCP connection.

## Status

Alpha — skeleton only (network output lands in a follow-up task).

## Install

```bash
pip install led-ticker-telnet
```

Then select the backend in your `config.toml`:

```toml
[display]
backend = "telnet.telnet"
```

## Development

```bash
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests
```

Python 3.14+ only.
