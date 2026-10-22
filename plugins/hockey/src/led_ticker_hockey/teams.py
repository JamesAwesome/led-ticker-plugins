"""The 32 NHL clubs: abbreviations, names and LED-visible brand colors.

Colors are lifted so no team is invisible on a black panel: every primary and
secondary has a channel >= 90.
"""

from dataclasses import dataclass

Color = tuple[int, int, int]
_NEUTRAL: Color = (200, 200, 200)


@dataclass(frozen=True)
class TeamInfo:
    abbrev: str
    city: str
    nickname: str
    primary: Color
    secondary: Color


NHL_TEAMS: dict[str, TeamInfo] = {
    t.abbrev: t
    for t in (
        TeamInfo("ANA", "Anaheim", "Ducks", (255, 110, 40), (200, 170, 100)),
        TeamInfo("BOS", "Boston", "Bruins", (255, 184, 28), (255, 255, 255)),
        TeamInfo("BUF", "Buffalo", "Sabres", (40, 100, 255), (255, 184, 28)),
        TeamInfo("CGY", "Calgary", "Flames", (230, 40, 50), (255, 184, 28)),
        TeamInfo("CAR", "Carolina", "Hurricanes", (230, 30, 50), (255, 255, 255)),
        TeamInfo("CHI", "Chicago", "Blackhawks", (230, 30, 50), (255, 255, 255)),
        TeamInfo("COL", "Colorado", "Avalanche", (200, 60, 100), (70, 140, 220)),
        TeamInfo("CBJ", "Columbus", "Blue Jackets", (30, 100, 230), (230, 40, 50)),
        TeamInfo("DAL", "Dallas", "Stars", (0, 170, 100), (190, 190, 190)),
        TeamInfo("DET", "Detroit", "Red Wings", (230, 30, 50), (255, 255, 255)),
        TeamInfo("EDM", "Edmonton", "Oilers", (255, 100, 30), (40, 100, 255)),
        TeamInfo("FLA", "Florida", "Panthers", (230, 30, 50), (255, 200, 60)),
        TeamInfo("LAK", "Los Angeles", "Kings", (190, 190, 190), (255, 255, 255)),
        TeamInfo("MIN", "Minnesota", "Wild", (30, 140, 80), (230, 60, 60)),
        TeamInfo("MTL", "Montreal", "Canadiens", (230, 30, 50), (40, 100, 255)),
        TeamInfo("NSH", "Nashville", "Predators", (255, 184, 28), (40, 100, 255)),
        TeamInfo("NJD", "New Jersey", "Devils", (230, 30, 50), (255, 255, 255)),
        TeamInfo("NYI", "New York", "Islanders", (40, 110, 255), (255, 130, 40)),
        TeamInfo("NYR", "New York", "Rangers", (40, 110, 255), (230, 30, 50)),
        TeamInfo("OTT", "Ottawa", "Senators", (230, 30, 50), (200, 170, 100)),
        TeamInfo("PHI", "Philadelphia", "Flyers", (255, 90, 0), (255, 90, 0)),
        TeamInfo("PIT", "Pittsburgh", "Penguins", (255, 200, 60), (255, 255, 255)),
        TeamInfo("SJS", "San Jose", "Sharks", (0, 150, 170), (255, 130, 40)),
        TeamInfo("SEA", "Seattle", "Kraken", (100, 200, 220), (230, 60, 80)),
        TeamInfo("STL", "St. Louis", "Blues", (40, 100, 255), (255, 200, 60)),
        TeamInfo("TBL", "Tampa Bay", "Lightning", (40, 100, 255), (255, 255, 255)),
        TeamInfo("TOR", "Toronto", "Maple Leafs", (40, 100, 255), (255, 255, 255)),
        TeamInfo("UTA", "Utah", "Mammoth", (110, 200, 255), (255, 255, 255)),
        TeamInfo("VAN", "Vancouver", "Canucks", (40, 130, 230), (0, 150, 90)),
        TeamInfo("VGK", "Vegas", "Golden Knights", (200, 170, 100), (190, 190, 190)),
        TeamInfo("WSH", "Washington", "Capitals", (230, 30, 50), (40, 100, 255)),
        TeamInfo("WPG", "Winnipeg", "Jets", (60, 110, 200), (190, 190, 190)),
    )
}


def team(abbrev: str) -> TeamInfo:
    """Look up a club by abbreviation; unknown codes get a neutral entry."""
    code = abbrev.upper()
    found = NHL_TEAMS.get(code)
    if found is not None:
        return found
    return TeamInfo(abbrev, "", abbrev, _NEUTRAL, _NEUTRAL)


def normalize_team(code: str) -> str | None:
    """Upper-cased code if it is a known NHL abbreviation, else None."""
    up = code.strip().upper()
    return up if up in NHL_TEAMS else None
