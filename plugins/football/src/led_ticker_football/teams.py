"""The 32 NFL clubs: ESPN abbreviations and ids, names and LED-visible colours.

Colours start from ESPN's `color` / `alternateColor` and are LIFTED so no
team is invisible on a black panel: every primary and secondary has a
channel >= 90. Where ESPN's primary is black or near-black (`LV`, `PIT`,
`HOU`, `CHI`, `DEN`) the lifted other colour is the chip's main colour.
"""

from dataclasses import dataclass

Color = tuple[int, int, int]
_NEUTRAL: Color = (200, 200, 200)
_SILVER: Color = (190, 190, 190)


@dataclass(frozen=True)
class TeamInfo:
    abbrev: str
    espn_id: str
    city: str
    nickname: str
    primary: Color
    secondary: Color


NFL_TEAMS: dict[str, TeamInfo] = {
    t.abbrev: t
    for t in (
        TeamInfo("ARI", "22", "Arizona", "Cardinals", (200, 30, 60), (255, 255, 255)),
        TeamInfo("ATL", "1", "Atlanta", "Falcons", (200, 30, 50), _SILVER),
        TeamInfo("BAL", "33", "Baltimore", "Ravens", (90, 50, 200), (200, 170, 60)),
        TeamInfo("BUF", "2", "Buffalo", "Bills", (30, 80, 220), (220, 30, 60)),
        TeamInfo("CAR", "29", "Carolina", "Panthers", (0, 140, 220), _SILVER),
        TeamInfo("CHI", "3", "Chicago", "Bears", (230, 70, 0), (40, 80, 180)),
        TeamInfo("CIN", "4", "Cincinnati", "Bengals", (250, 80, 20), _SILVER),
        TeamInfo("CLE", "5", "Cleveland", "Browns", (150, 90, 30), (255, 60, 0)),
        TeamInfo("DAL", "6", "Dallas", "Cowboys", (30, 80, 200), (176, 183, 188)),
        TeamInfo("DEN", "7", "Denver", "Broncos", (250, 76, 2), (40, 80, 180)),
        TeamInfo("DET", "8", "Detroit", "Lions", (0, 118, 182), (187, 187, 187)),
        TeamInfo("GB", "9", "Green Bay", "Packers", (40, 130, 60), (255, 182, 18)),
        TeamInfo("HOU", "34", "Houston", "Texans", (235, 0, 40), (40, 80, 160)),
        TeamInfo("IND", "11", "Indianapolis", "Colts", (30, 90, 200), (255, 255, 255)),
        TeamInfo("JAX", "30", "Jacksonville", "Jaguars", (0, 130, 150), (215, 162, 42)),
        TeamInfo("KC", "12", "Kansas City", "Chiefs", (227, 24, 55), (255, 182, 18)),
        TeamInfo("LV", "13", "Las Vegas", "Raiders", _SILVER, (120, 120, 120)),
        TeamInfo("LAC", "24", "Los Angeles", "Chargers", (0, 128, 198), (255, 194, 14)),
        TeamInfo("LAR", "14", "Los Angeles", "Rams", (30, 70, 200), (255, 209, 0)),
        TeamInfo("MIA", "15", "Miami", "Dolphins", (0, 160, 170), (252, 76, 2)),
        TeamInfo("MIN", "16", "Minnesota", "Vikings", (110, 50, 190), (255, 198, 47)),
        TeamInfo("NE", "17", "New England", "Patriots", (30, 80, 200), (198, 12, 48)),
        TeamInfo("NO", "18", "New Orleans", "Saints", (211, 188, 141), _SILVER),
        TeamInfo("NYG", "19", "New York", "Giants", (40, 90, 220), (230, 40, 60)),
        TeamInfo("NYJ", "20", "New York", "Jets", (30, 130, 80), (255, 255, 255)),
        TeamInfo("PHI", "21", "Philadelphia", "Eagles", (0, 150, 130), _SILVER),
        TeamInfo("PIT", "23", "Pittsburgh", "Steelers", (255, 182, 18), _SILVER),
        TeamInfo("SF", "25", "San Francisco", "49ers", (200, 20, 20), (179, 153, 93)),
        TeamInfo("SEA", "26", "Seattle", "Seahawks", (30, 80, 200), (105, 190, 40)),
        TeamInfo("TB", "27", "Tampa Bay", "Buccaneers", (189, 28, 54), _SILVER),
        TeamInfo("TEN", "10", "Tennessee", "Titans", (68, 149, 210), (40, 70, 160)),
        TeamInfo(
            "WSH", "28", "Washington", "Commanders", (150, 30, 30), (255, 182, 18)
        ),
    )
}

_BY_ID: dict[str, str] = {t.espn_id: t.abbrev for t in NFL_TEAMS.values()}


def team(abbrev: str) -> TeamInfo:
    """Look up a club by abbreviation; unknown codes get a neutral entry."""
    code = abbrev.upper()
    found = NFL_TEAMS.get(code)
    if found is not None:
        return found
    return TeamInfo(abbrev, "", "", abbrev, _NEUTRAL, _NEUTRAL)


def normalize_team(code: str) -> str | None:
    """Upper-cased code if it is a known NFL abbreviation, else None."""
    up = code.strip().upper()
    return up if up in NFL_TEAMS else None


def team_by_id(espn_id: str) -> str | None:
    """Abbreviation for an ESPN team id (how `situation.possession` names a team)."""
    return _BY_ID.get(str(espn_id))
