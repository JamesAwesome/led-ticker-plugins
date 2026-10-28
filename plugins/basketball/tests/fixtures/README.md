Fixtures are produced by `uv run python tools/capture_fixtures.py --out tests/fixtures` (run from `plugins/basketball/`).
The scoreboard and PHI schedule payloads are trimmed to a few events; raw payloads land in the gitignored `raw/`.
`event_live.json` is hand-written from a captured `post` event (flagged `"_handwritten": true`) when no game was live.
