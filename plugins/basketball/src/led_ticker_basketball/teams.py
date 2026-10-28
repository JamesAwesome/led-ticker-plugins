"""The 30 NBA clubs: ESPN abbreviations and ids, names and LED-visible colours.

Colours start from ESPN's `color` / `alternateColor` and are LIFTED so no team
is invisible on a black panel: every primary and secondary has a channel >= 90.
Where ESPN's primary is black or near-black (`BKN`, `SA`) the lifted secondary
is the chip's main colour.

The ESPN ids below are verified against the 2026-10-28 payload: pending (the
human capture step confirms each `team.id`; fix any that differ).
"""

from dataclasses import dataclass

Color = tuple[int, int, int]
_NEUTRAL: Color = (200, 200, 200)
_SILVER: Color = (190, 190, 190)
_WHITE: Color = (255, 255, 255)


@dataclass(frozen=True)
class TeamInfo:
    abbrev: str
    espn_id: str
    city: str
    nickname: str
    primary: Color
    secondary: Color


NBA_TEAMS: dict[str, TeamInfo] = {
    t.abbrev: t
    for t in (
        TeamInfo("ATL", "1", "Atlanta", "Hawks", (225, 68, 52), (196, 214, 0)),
        TeamInfo("BOS", "2", "Boston", "Celtics", (0, 150, 80), _WHITE),
        TeamInfo("BKN", "17", "Brooklyn", "Nets", _SILVER, _WHITE),
        TeamInfo("CHA", "30", "Charlotte", "Hornets", (29, 140, 160), (110, 70, 190)),
        TeamInfo("CHI", "4", "Chicago", "Bulls", (206, 17, 65), _WHITE),
        TeamInfo("CLE", "5", "Cleveland", "Cavaliers", (134, 0, 56), (253, 187, 48)),
        TeamInfo("DAL", "6", "Dallas", "Mavericks", (0, 100, 220), (0, 43, 92)),
        TeamInfo("DEN", "7", "Denver", "Nuggets", (60, 110, 190), (255, 198, 39)),
        TeamInfo("DET", "8", "Detroit", "Pistons", (200, 16, 46), (29, 66, 138)),
        TeamInfo("GS", "9", "Golden State", "Warriors", (29, 66, 138), (255, 199, 44)),
        TeamInfo("HOU", "10", "Houston", "Rockets", (206, 17, 65), _SILVER),
        TeamInfo("IND", "11", "Indiana", "Pacers", (253, 187, 48), (0, 45, 98)),
        TeamInfo("LAC", "12", "Los Angeles", "Clippers", (200, 16, 46), (29, 66, 138)),
        TeamInfo("LAL", "13", "Los Angeles", "Lakers", (85, 37, 130), (253, 185, 39)),
        TeamInfo("MEM", "29", "Memphis", "Grizzlies", (93, 118, 169), (70, 90, 190)),
        TeamInfo("MIA", "14", "Miami", "Heat", (152, 0, 46), (249, 160, 27)),
        TeamInfo("MIL", "15", "Milwaukee", "Bucks", (0, 130, 60), (240, 235, 210)),
        TeamInfo(
            "MIN", "16", "Minnesota", "Timberwolves", (60, 110, 190), (120, 190, 32)
        ),
        TeamInfo("NO", "3", "New Orleans", "Pelicans", (30, 80, 190), (225, 58, 62)),
        TeamInfo("NY", "18", "New York", "Knicks", (245, 132, 38), (0, 107, 182)),
        TeamInfo("OKC", "25", "Oklahoma City", "Thunder", (0, 125, 195), (239, 59, 36)),
        TeamInfo("ORL", "19", "Orlando", "Magic", (0, 125, 197), _SILVER),
        TeamInfo("PHI", "20", "Philadelphia", "76ers", (0, 107, 182), (237, 23, 76)),
        TeamInfo("PHX", "21", "Phoenix", "Suns", (229, 95, 32), (29, 17, 96)),
        TeamInfo("POR", "22", "Portland", "Trail Blazers", (224, 58, 62), _SILVER),
        TeamInfo("SA", "24", "San Antonio", "Spurs", _SILVER, (130, 130, 130)),
        TeamInfo("SAC", "23", "Sacramento", "Kings", (115, 64, 160), _SILVER),
        TeamInfo("TOR", "28", "Toronto", "Raptors", (206, 17, 65), _SILVER),
        TeamInfo("UTAH", "26", "Utah", "Jazz", (0, 130, 60), (249, 160, 27)),
        TeamInfo("WSH", "27", "Washington", "Wizards", (0, 43, 92), (227, 24, 55)),
    )
}

_BY_ID: dict[str, str] = {t.espn_id: t.abbrev for t in NBA_TEAMS.values()}


def team(abbrev: str) -> TeamInfo:
    """Look up a club by abbreviation; unknown codes get a neutral entry."""
    found = NBA_TEAMS.get(abbrev.upper())
    if found is not None:
        return found
    return TeamInfo(abbrev, "", "", abbrev, _NEUTRAL, _NEUTRAL)


def normalize_team(code: str) -> str | None:
    """Upper-cased code if it is a known NBA abbreviation, else None."""
    up = code.strip().upper()
    return up if up in NBA_TEAMS else None


def team_by_id(espn_id: str) -> str | None:
    """Abbreviation for an ESPN team id."""
    return _BY_ID.get(str(espn_id))
