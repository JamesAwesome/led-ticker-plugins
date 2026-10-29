Fixtures are produced by `uv run python tools/capture_fixtures.py --out tests/fixtures` (run from `plugins/basketball/`).
The scoreboard and PHI schedule payloads are trimmed to a few events; raw payloads land in the gitignored `raw/`.
`event_live.json` is hand-written from a captured `post` event (flagged `"_handwritten": true`) when no game was live.
`event_final_ot.json` (SA @ UTAH, one OT) and `event_final_phi.json` (PHI @ IND) are real 2026-10-28 finals, trimmed with `_trim_event` from the `--date 20261028` raw scoreboard.
