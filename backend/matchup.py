"""Pure extraction of one blue-side versus red-side ranked top matchup."""


def get_runes(player):
    return [selection["perk"]
            for style in player.get("perks", {}).get("styles", [])
            for selection in style.get("selections", []) if "perk" in selection]


def get_items(player):
    return [player[f"item{i}"] for i in range(7) if player.get(f"item{i}")]


def extract_top_matchup(match):
    """Return None for ineligible/incomplete data; never guess roles or winners.

    Missing optional stats remain None; absent rune/item collections are empty.
    patch preserves gameVersion for compatibility; patch_major_minor groups builds.
    """
    try:
        info = match["info"]
        if info["queueId"] != 420:
            return None
        tops = [p for p in info["participants"] if p.get("teamPosition") == "TOP"]
        if len(tops) != 2 or {p["teamId"] for p in tops} != {100, 200}:
            return None
        blue, red = sorted(tops, key=lambda p: p["teamId"])
        if any(type(p.get("win")) is not bool or not p.get("championName") for p in tops):
            return None
        if blue["win"] == red["win"]:
            return None
        match_id, version = match["metadata"]["matchId"], info["gameVersion"]
        if not isinstance(match_id, str) or not match_id or not isinstance(version, str) or not version:
            return None
        result = {"match_id": match_id, "patch": version,
                  "patch_major_minor": ".".join(version.split(".")[:2]),
                  "game_duration": info.get("gameDuration"),
                  "game_start": info.get("gameStartTimestamp"),
                  "champion": blue["championName"], "opponent": red["championName"],
                  "champion_win": blue["win"],
                  "winner": blue["championName"] if blue["win"] else red["championName"]}
        for prefix, player in (("champion", blue), ("opponent", red)):
            result[f"{prefix}_participant_id"] = player.get("participantId")
            result[f"{prefix}_summoner_spells"] = [player.get("summoner1Id"), player.get("summoner2Id")]
            result[f"{prefix}_kda"] = [player.get(k) for k in ("kills", "deaths", "assists")]
            cs = [player.get(k) for k in ("totalMinionsKilled", "neutralMinionsKilled")]
            result[f"{prefix}_cs"] = sum(cs) if all(type(n) is int for n in cs) else None
            result[f"{prefix}_gold"] = player.get("goldEarned")
            result[f"{prefix}_runes"] = get_runes(player)
            result[f"{prefix}_items"] = get_items(player)
            result[f"{prefix}_perks"] = player.get("perks", {})
        return result
    except (KeyError, TypeError, AttributeError, ValueError):
        return None
