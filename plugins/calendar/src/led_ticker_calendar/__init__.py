"""led-ticker-calendar: calendar (.ics) agenda/next/two_row widget, contributed
via the ``led_ticker.plugins`` entry point.

The entry-point name ``calendar`` is the plugin namespace, so the widget is
``type = "calendar.events"`` in config.toml.
"""

from led_ticker_calendar.calendar import Calendar


def register(api):
    api.widget("events")(Calendar)
