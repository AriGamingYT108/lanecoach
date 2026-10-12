"""Compatibility helpers for fetching and printing matchups."""
if __package__:
    from .matchup import extract_top_matchup, get_items, get_runes
    from .riot_api import RiotClient
else:
    from matchup import extract_top_matchup, get_items, get_runes
    from riot_api import RiotClient


def get_match(match_id):
    from urllib.parse import quote
    return RiotClient().get(f"/lol/match/v5/matches/{quote(match_id, safe='')}")


def print_matchup(matchup):
    print("\n==============================")
    print("       TOP LANE MATCHUP")
    print("==============================")

    print(
        f"{matchup['champion']} "
        f"vs "
        f"{matchup['opponent']}"
    )

    print(f"Patch: {matchup['patch']}")

    print(
        f"\n{matchup['champion']} KDA:",
        "/".join(map(str, matchup["champion_kda"]))
    )

    print(
        f"{matchup['opponent']} KDA:",
        "/".join(map(str, matchup["opponent_kda"]))
    )

    print(
        f"\nCS: "
        f"{matchup['champion_cs']} vs "
        f"{matchup['opponent_cs']}"
    )

    print(
        f"Gold: "
        f"{matchup['champion_gold']} vs "
        f"{matchup['opponent_gold']}"
    )

    winner = (
        matchup["champion"]
        if matchup["champion_win"]
        else matchup["opponent"]
    )

    print(f"\nWinner: {winner}")

    print(
        f"\n{matchup['champion']} runes:",
        matchup["champion_runes"]
    )

    print(
        f"{matchup['champion']} items:",
        matchup["champion_items"]
    )