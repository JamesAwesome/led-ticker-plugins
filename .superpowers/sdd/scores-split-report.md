# scores.py split — completion report

## Status: COMPLETE

## File line counts

| File | Lines |
|------|-------|
| `_models.py` (NEW) | 116 |
| `_scoreboard.py` (NEW) | 449 |
| `_two_row.py` (NEW) | 493 |
| `scores.py` (RETAINED) | 675 |
| **Total** | **1733** |

Original `scores.py` was 1609 lines; the new total across 4 files is 1733 (increase is
module docstrings + import headers + `__all__` + re-export import lines).

## Re-exports in scores.py `__all__`

From `_models`:
- `GameInfo`, `SeriesInfo`
- `_ordinal`, `_format_inning`, `_format_game_time`, `_classify_postponement`,
  `_parse_team_abbr`, `_fit_team_name`

From `_scoreboard`:
- `MLBScoreboardMessage`
- `_build_series_title`, `_build_game_message`, `_build_scoreboard_message`

From `_two_row`:
- `MLBTwoRowMessage`
- `_build_two_row_message`, `_build_two_row_series_title`
- `_compute_preview_two_row`, `_compute_final_two_row`, `_compute_live_two_row`,
  `_compute_postponed_two_row`
- `_pip_segments`, `_expand_matchup_if_fits`

From `led_ticker.plugin` (re-exported for test_scoreboard.py):
- `SegmentMessage`

Kept in `scores.py`:
- `MLBScoreMonitor`, `_MLBStoryT`, `_MLB_VALID_LAYOUTS`, `_TWO_ROW_ONLY`

## Test result

476 passed, 0 failed, 1.71s

- `test_scores.py` — PASS (all imports from `led_ticker_baseball.scores` work via re-exports)
- `test_scoreboard.py` — PASS (all imports from `led_ticker_baseball.scores` work via re-exports)
- `test_import_purity.py` — PASS (all new modules import only from `led_ticker.plugin`)

## Coverage

95.57% total (required: 90%)

## Notes

- No test files were modified.
- No `from __future__ import annotations` used.
- No import cycles: `_models` has no intra-package deps; `_scoreboard` and `_two_row`
  import from `_models`; `scores` imports from all three.
- Class definitions in `_scoreboard.py` and `_two_row.py` were placed BEFORE their
  builder functions to avoid forward references (no string annotations needed).
- `__init__.py` unchanged: still imports `MLBScoreMonitor` from `.scores`.
