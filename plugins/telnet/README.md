# led-ticker-telnet

Watch your [led-ticker](https://github.com/JamesAwesome/led-ticker) sign live in any ANSI-capable terminal — the same content that drives your LED panels streams over TCP as true-color ANSI escape sequences.

Every client sees the current frame the moment `swap()` fires, at panel cadence. Open two terminals, disconnect one, start another — the sign keeps rendering without interruption.

## Prerequisites

- A working [led-ticker](https://github.com/JamesAwesome/led-ticker) install (core ≥ 2.2).
- An ANSI-capable terminal (any modern terminal on macOS, Linux, or Windows Terminal). True-color support (24-bit) recommended; most terminals released after 2017 support it.
- `telnet` or `nc` on the connecting machine (both are standard on macOS and most Linux distros).

## Install

This plugin auto-registers via the `led_ticker.plugins` entry point — once the package is installed, no `[plugins]` config change is needed.

**Into a containerized led-ticker (recommended):** add the package to your `config/requirements-plugins.txt` and rebuild:

```text
led-ticker-telnet
```

```bash
# in your led-ticker checkout
docker compose up -d --build
```

**Standalone (a venv that already has led-ticker):**

```bash
pip install led-ticker-telnet
```

See the led-ticker [Plugins docs](https://docs.ledticker.dev/plugins/) for the constraint-based install the Docker image uses.

## Select the backend

In your `config/config.toml`, set the `backend` field under `[display]`:

```toml
[display]
backend = "telnet.telnet"
rows = 16
cols = 32
chain_length = 5
brightness = 80
default_scale = 1
```

The backend name is `telnet.telnet` — the first `telnet` is the plugin namespace (from the entry-point registration), and the second names the backend within that namespace.

All other `[display]` fields (`rows`, `cols`, `chain_length`, `default_scale`, etc.) work exactly as they do with the rgbmatrix backend. Your widgets, sections, and transitions config is unchanged.

## Connect

Once led-ticker starts with the telnet backend, connect from any machine on the same network:

```bash
telnet <host> 2300  # default; see Configuration to change
```

```bash
nc <host> 2300  # default; see Configuration to change
```

Replace `<host>` with the hostname or IP of the machine running led-ticker. When connecting locally: `telnet localhost 2300`.

The terminal renders one text row per two canvas rows, using the Unicode UPPER HALF BLOCK character (▀) with the top pixel as the foreground color and the bottom pixel as the background color. This doubles the vertical pixel density in most terminals.

Disconnecting cleanly (Ctrl-C or closing the terminal window) is safe — led-ticker logs the departure and continues running.

## Configuration via environment variables

The telnet backend reads two environment variables at startup:

| Variable | Default | Description |
|----------|---------|-------------|
| `LED_TICKER_TELNET_PORT` | `2300` | TCP port to listen on |
| `LED_TICKER_TELNET_HOST` | `0.0.0.0` | Bind address (all interfaces) |

Set them in your shell or in Docker Compose:

```bash
# shell
export LED_TICKER_TELNET_PORT=3000
```

```yaml
# docker compose (compose.yaml)
environment:
  LED_TICKER_TELNET_PORT: "3000"
  # LED_TICKER_TELNET_HOST: "0.0.0.0"   # bind address; default is all interfaces
```

## Known limitations

**`brightness` is a no-op.** The `[display] brightness` field is required by led-ticker's backend protocol but has no effect on ANSI output — adjust brightness/contrast in your terminal instead.

**`pixel_mapper_config` is accepted but ignored.** The telnet backend accepts the `pixel_mapper_config` argument (required by led-ticker's backend constructor convention) but does not apply any chain-folding or U-mapper remapping — it renders the logical canvas directly to the terminal. Physical-panel layout concerns (serpentine chains, rotation) are a hardware-level concern irrelevant to a terminal preview.

**TOML `[display]` sub-keys are not readable by plugin backends today.** The port and host are therefore environment-only — there is no `port = 2300` or `host = "0.0.0.0"` key in the `[display]` block.

A future led-ticker-core `[display.<backend>]` → `from_config(cls, cfg)` mechanism would close this: plugins could define their own sub-table and receive a typed config object at startup. Port and host would then be first-class TOML knobs alongside `brightness`, `rows`, and the rest. This is the key usability gap to resolve in a follow-up core change.

## Behavior under error conditions

- **Bind failure** (port in use, insufficient permissions): the backend logs a warning and continues without a server. The sign renders normally; clients simply cannot connect until the conflict is resolved and led-ticker restarts.
- **Slow or stalled client**: `swap()` writes to the client without waiting for a drain, so the render loop never blocks. Bytes a client hasn't read accumulate in that connection's in-process write buffer; to keep a stalled client (suspended `nc`, terminal under Ctrl-S flow control, congested link) from growing that buffer without bound, `swap()` checks each client's write-buffer size and **skips the write for any client over a ~4 MiB cap** — that frame is dropped for that client, which recovers automatically once it starts reading again. The render loop and other clients are unaffected.
- **Client disconnect mid-session**: detected on the next `swap()` write; the client is pruned and rendering continues.

## Development

```bash
cd plugins/telnet
uv sync --extra dev      # resolves led-ticker-core from PyPI
uv run pytest -q
uv run ruff check src tests
uv run pyright src
```

The plugin imports only the public `led_ticker.plugin` surface — `tests/test_import_purity.py` enforces it.

## Links

- [led-ticker](https://github.com/JamesAwesome/led-ticker) — the core project
- [Docs site](https://docs.ledticker.dev) · [Plugin system](https://docs.ledticker.dev/plugins/)
- [Plugin authoring guide](https://docs.ledticker.dev/plugins/authoring/)
