import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RIOT_API_KEY")
BASE_URL = "https://americas.api.riotgames.com"

HEADERS = {
    "X-Riot-Token": API_KEY
}


def get_match(match_id):
    url = f"{BASE_URL}/lol/match/v5/matches/{match_id}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=10
    )

    response.raise_for_status()

    return response.json()


def get_runes(player):
    rune_ids = []

    for style in player["perks"]["styles"]:
        for selection in style["selections"]:
            rune_ids.append(selection["perk"])

    return rune_ids


def get_items(player):
    items = []

    for i in range(7):
        item_id = player[f"item{i}"]

        if item_id != 0:
            items.append(item_id)

    return items


def extract_top_matchup(match):
    info = match["info"]

    # Ranked Solo/Duo only
    if info["queueId"] != 420:
        return None

    top_laners = [
        player
        for player in info["participants"]
        if player["teamPosition"] == "TOP"
    ]

    if len(top_laners) != 2:
        return None

    player1 = top_laners[0]
    player2 = top_laners[1]

    return {
        "match_id": match["metadata"]["matchId"],
        "patch": info["gameVersion"],
        "game_duration": info["gameDuration"],

        "champion": player1["championName"],
        "opponent": player2["championName"],
        "champion_win": player1["win"],

        "champion_kda": [
            player1["kills"],
            player1["deaths"],
            player1["assists"]
        ],

        "opponent_kda": [
            player2["kills"],
            player2["deaths"],
            player2["assists"]
        ],

        "champion_cs": (
            player1["totalMinionsKilled"]
            + player1["neutralMinionsKilled"]
        ),

        "opponent_cs": (
            player2["totalMinionsKilled"]
            + player2["neutralMinionsKilled"]
        ),

        "champion_gold": player1["goldEarned"],
        "opponent_gold": player2["goldEarned"],

        "champion_runes": get_runes(player1),
        "opponent_runes": get_runes(player2),

        "champion_items": get_items(player1),
        "opponent_items": get_items(player2)
    }


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