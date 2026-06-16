#!/usr/bin/env python3
"""Fetch FIFA World Cup 2026 group-stage matches and standings from
football-data.org and write a normalized results.json that the frontend
can read directly. Intended to be run from GitHub Actions on a cron."""

import json
import os
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")
if not API_KEY:
    print("ERROR: FOOTBALL_DATA_API_KEY not set", file=sys.stderr)
    sys.exit(1)

BASE = "https://api.football-data.org/v4/competitions/WC"
HEADERS = {"X-Auth-Token": API_KEY}

# Map team display names returned by the API to the 3-letter codes our
# frontend uses. Variations are listed for resilience.
TEAM_CODE = {
    "Saudi Arabia": "ksa", "Brazil": "bra", "Morocco": "mar", "Qatar": "qat",
    "Switzerland": "sui", "Egypt": "egy", "Belgium": "bel", "Uruguay": "uru",
    "Spain": "esp", "Cape Verde": "cpv", "France": "fra", "Senegal": "sen",
    "Iraq": "irq", "Norway": "nor", "Argentina": "arg", "Algeria": "alg",
    "Austria": "aut", "Jordan": "jor", "Portugal": "por", "DR Congo": "cod",
    "Congo DR": "cod", "England": "eng", "Croatia": "cro", "Ghana": "gha",
    "Germany": "ger", "Netherlands": "ned", "Japan": "jpn", "Sweden": "swe",
    "Tunisia": "tun", "Mexico": "mex", "South Korea": "kor",
    "Republic of Korea": "kor", "Korea Republic": "kor", "Canada": "can",
    "Iran": "irn", "IR Iran": "irn", "New Zealand": "nzl", "Colombia": "col",
    "Uzbekistan": "uzb", "Panama": "pan", "South Africa": "rsa",
    "Scotland": "sco", "Haiti": "hai", "Ecuador": "ecu", "Ivory Coast": "civ",
    "Côte d'Ivoire": "civ", "Curacao": "cuw", "Curaçao": "cuw",
    "Bosnia and Herzegovina": "bih", "Bosnia & Herzegovina": "bih",
    "Czechia": "cze", "Czech Republic": "cze", "USA": "usa",
    "United States": "usa", "Paraguay": "par", "Australia": "aus",
    "Turkey": "tur", "Türkiye": "tur", "Turkiye": "tur",
}


# If the dict lookup misses and the fallback (first-3-chars-lowercased) gives
# us something that's still wrong, force the canonical code here.
CODE_FIXUP = {
    "cap": "cpv",   # "Cape Verde" -> we use cpv, not cap
    "bos": "bih",   # "Bosnia ..." -> we use bih, not bos
}


def code(name: str) -> str:
    """Return 3-letter team code, falling back to lowercased first 3 chars."""
    if not name:
        return "tbd"
    raw = TEAM_CODE.get(name.strip(), name.strip().lower()[:3])
    return CODE_FIXUP.get(raw, raw)


def api_get(path: str) -> dict:
    req = Request(BASE + path, headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> None:
    try:
        matches_resp = api_get("/matches")
        standings_resp = api_get("/standings")
    except (HTTPError, URLError) as e:
        print(f"API error, leaving results.json unchanged: {e}", file=sys.stderr)
        sys.exit(0)  # exit 0 so the workflow doesn't fail; just skip update

    # ---- Transform matches ----
    matches: dict[str, dict] = {}
    for m in matches_resp.get("matches", []):
        # Only group-stage matches for now
        stage = (m.get("stage") or "").upper()
        if stage and stage != "GROUP_STAGE":
            continue
        home = code(m.get("homeTeam", {}).get("name"))
        away = code(m.get("awayTeam", {}).get("name"))
        # Key by team pair only — each pair plays once in the group stage,
        # so this avoids UTC vs Saudi-time date mismatches.
        key = f"{home}_{away}"
        ft = m.get("score", {}).get("fullTime", {}) or {}
        matches[key] = {
            "status": m.get("status", "SCHEDULED"),
            "homeScore": ft.get("home"),
            "awayScore": ft.get("away"),
            "minute": m.get("minute"),
        }

    # ---- Transform standings ----
    standings: dict[str, list] = {}
    for grp in standings_resp.get("standings", []):
        if grp.get("type") != "TOTAL":
            continue
        # group field is like "GROUP_A" or "Group A" or just "A" depending on API
        raw = (grp.get("group") or "").upper()
        letter = raw.replace("GROUP_", "").replace("GROUP ", "").strip()
        if len(letter) != 1:
            continue
        rows = []
        for row in grp.get("table", []):
            t = row.get("team", {})
            rows.append({
                "team": code(t.get("name")),
                "played": row.get("playedGames", 0),
                "won": row.get("won", 0),
                "drawn": row.get("draw", 0),
                "lost": row.get("lost", 0),
                "gf": row.get("goalsFor", 0),
                "ga": row.get("goalsAgainst", 0),
                "gd": row.get("goalDifference", 0),
                "pts": row.get("points", 0),
            })
        standings[letter] = rows

    output = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "football-data.org",
        "competition": "FIFA World Cup 2026",
        "matches": matches,
        "standings": standings,
    }

    with open("results.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"Wrote results.json: {len(matches)} matches, {len(standings)} groups")


if __name__ == "__main__":
    main()
