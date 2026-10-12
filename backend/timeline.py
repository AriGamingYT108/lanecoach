"""Extract timestamp-based lane evidence without assuming one-minute frame spacing."""
from urllib.parse import quote
import math

from .matchup import extract_top_matchup
from .riot_api import RiotAPIError


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def extract_timeline(timeline, matchup):
    try:
        if timeline["metadata"]["matchId"] != matchup["match_id"]:
            return None
        blue = matchup.get("champion_participant_id")
        red = matchup.get("opponent_participant_id")
        if type(blue) is not int or type(red) is not int or not 1 <= blue <= 10 or not 1 <= red <= 10 or blue == red:
            return None
        frames = timeline["info"]["frames"]
        if not isinstance(frames, list) or not frames:
            return None
        points, events = [], []
        for frame in frames:
            timestamp = frame.get("timestamp")
            if not numeric(timestamp) or timestamp < 0:
                continue
            participants = frame.get("participantFrames", {})
            p1, p2 = participants.get(str(blue)), participants.get(str(red))
            if isinstance(p1, dict) and isinstance(p2, dict):
                def cs(p):
                    values = [p.get("minionsKilled"), p.get("jungleMinionsKilled")]
                    return sum(values) if all(numeric(v) for v in values) else None
                points.append({"timestamp": timestamp,
                    "champion_gold": p1.get("totalGold"), "opponent_gold": p2.get("totalGold"),
                    "champion_cs": cs(p1), "opponent_cs": cs(p2),
                    "champion_level": p1.get("level"), "opponent_level": p2.get("level")})
            for event in frame.get("events", []):
                stamp = event.get("timestamp")
                if not numeric(stamp) or not 0 <= stamp <= 900000:
                    continue
                kind = event.get("type")
                if kind == "CHAMPION_KILL" and ({event.get("killerId"), event.get("victimId")} & {blue, red}
                        or {blue, red} & set(event.get("assistingParticipantIds", []))):
                    events.append({k: event.get(k) for k in ("type", "timestamp", "killerId", "victimId", "assistingParticipantIds")})
                elif kind in {"ITEM_PURCHASED", "ITEM_SOLD", "ITEM_UNDO"} and event.get("participantId") in {blue, red}:
                    events.append({k: event.get(k) for k in ("type", "timestamp", "participantId", "itemId", "beforeId", "afterId")})
        points.sort(key=lambda p: p["timestamp"])
        if not points:
            return None
        snapshots = {}
        for minute in (10, 15):
            target = minute * 60000
            # A late remake or missing frame must not masquerade as a 10-minute sample.
            eligible = [p for p in points if target - 90000 <= p["timestamp"] <= target]
            snapshots[str(minute)] = eligible[-1] if points[-1]["timestamp"] >= target and eligible else None
        return {"match_id": matchup["match_id"], "champion_participant_id": blue,
                "opponent_participant_id": red, "snapshots": snapshots,
                "points": points, "events": sorted(events, key=lambda e: e["timestamp"])}
    except (KeyError, TypeError, AttributeError, ValueError):
        return None


def collect_timelines(client, db, records, progress=None):
    summary = {"inserted": 0, "duplicates": 0, "failed": 0, "skipped": 0}
    for index, record in enumerate(records):
        match_id = record["match_id"]
        if db.get_timeline(match_id):
            summary["duplicates"] += 1
        else:
            try:
                # Older stored matchups may predate participant ID extraction.
                if not record.get("champion_participant_id") or not record.get("opponent_participant_id"):
                    record = extract_top_matchup(client.get(f"/lol/match/v5/matches/{quote(match_id, safe='')}"))
                if not record:
                    summary["skipped"] += 1
                    continue
                raw = client.get(f"/lol/match/v5/matches/{quote(match_id, safe='')}/timeline")
                extracted = extract_timeline(raw, record)
                if extracted:
                    db.save_timeline(match_id, extracted)
                    summary["inserted"] += 1
                else:
                    summary["skipped"] += 1
            except RiotAPIError as error:
                if error.status in {401, 403, 429}:
                    raise
                summary["failed"] += 1
        if progress:
            progress(index + 1, len(records), dict(summary))
    return summary
