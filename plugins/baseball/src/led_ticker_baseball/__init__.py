"""led-ticker-baseball: MLB scores/standings widgets, baseball emoji, and
baseball transitions, contributed via the ``led_ticker.plugins`` entry point.

The entry-point name ``baseball`` is the plugin namespace, so widgets are
``type = "baseball.scores"`` / ``"baseball.standings"``, transitions are
``baseball.roll`` / ``baseball.roll_reverse`` / ``baseball.roll_alternating``,
and the emoji is ``:baseball.ball:``.
"""


def register(api):
    # Real registrations (widgets, emoji, transitions) are wired in Phase 2.
    pass
