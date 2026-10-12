"""Idempotent Account-V1/Match-V5 ETL for all five roles; one-shot or scheduled."""
import argparse
import json
import time
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

from backend.riot_api import RiotClient, RiotAPIError
from .knowledge import seed_knowledge
from .store import Store

ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}


def extract_players(match):
    try:
        info, match_id = match["info"], match["metadata"]["matchId"]
        if info.get("queueId") != 420 or not match_id or not info.get("gameVersion"):
            return []
        result = []
        for p in info["participants"]:
            role, pid = p.get("teamPosition"), p.get("participantId")
            if role not in ROLES or type(pid) is not int or not 1 <= pid <= 10 or not isinstance(p.get("championName"), str) or type(p.get("win")) is not bool or p.get("teamId") not in {100, 200}:
                continue
            opposing = [q for q in info["participants"] if q.get("teamPosition") == role and q.get("teamId") in {100, 200} and q.get("teamId") != p["teamId"]]
            styles = (p.get("perks") or {}).get("styles") or []
            primary = next((s for s in styles if s.get("description") == "primaryStyle"), styles[0] if styles else {})
            selections = primary.get("selections") or []
            cs = [p.get("totalMinionsKilled"), p.get("neutralMinionsKilled")]
            result.append({"match_id": match_id, "participant_id": pid, "role": role,
                "champion": p["championName"], "opponent": opposing[0].get("championName") if len(opposing) == 1 else None,
                "win": p["win"], "keystone": selections[0].get("perk") if selections else None,
                "kills": p.get("kills"), "deaths": p.get("deaths"), "assists": p.get("assists"),
                "cs": sum(cs) if all(type(v) is int for v in cs) else None, "gold": p.get("goldEarned"),
                "payload": {"runes": styles, "items": [p.get(f"item{i}") for i in range(7)],
                            "team_id": p["teamId"]}})
        if len({p["participant_id"] for p in result}) != len(result):
            return []
        return result
    except (KeyError, TypeError, AttributeError):
        return []


def run_etl(store, client, game_name, tag, count=100):
    account = client.get(f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag, safe='')}")
    if not isinstance(account, dict) or not account.get("puuid"):
        raise RiotAPIError("Account response missing PUUID")
    counts = {"inserted": 0, "duplicates": 0, "skipped": 0, "failed": 0}
    for start in range(0, count, 100):
        size = min(100, count - start)
        ids = client.get(f"/lol/match/v5/matches/by-puuid/{quote(account['puuid'], safe='')}/ids", params={"queue": 420, "type": "ranked", "start": start, "count": size})
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
            raise RiotAPIError("Invalid match history response")
        for match_id in ids:
            if store.contains(match_id):
                counts["duplicates"] += 1
                continue
            try:
                match = client.get(f"/lol/match/v5/matches/{quote(match_id, safe='')}")
                extracted = extract_players(match)
                if not extracted or match.get("metadata", {}).get("matchId") != match_id:
                    counts["skipped"] += 1
                elif store.save_match(match, extracted):
                    counts["inserted"] += 1
                else:
                    counts["duplicates"] += 1
            except RiotAPIError as error:
                if error.status in {401, 403, 429}:
                    raise
                counts["failed"] += 1
        if len(ids) < size:
            break
    return counts


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-file", type=Path, required=True, help="JSON list of game_name, tag, region")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--interval", type=int, default=0, help="Repeat interval in seconds; 0 runs once")
    args = parser.parse_args()
    if not 1 <= args.count <= 1000 or args.interval < 0:
        parser.error("count must be 1–1000 and interval nonnegative")
    try:
        seeds = json.loads(args.seed_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        parser.error("Cannot read seed file; provide a valid local JSON list.")
    if not isinstance(seeds, list) or not seeds or any(
        not isinstance(seed, dict) or not isinstance(seed.get("game_name"), str)
        or not seed["game_name"].strip() or not isinstance(seed.get("tag"), str)
        or not seed["tag"].strip() or seed.get("region", "americas") not in {"americas", "europe", "asia", "sea"}
        for seed in seeds
    ):
        parser.error("Seeds must contain nonempty game_name/tag and a supported region.")
    store = Store()
    store.initialize()
    seed_knowledge(store)
    clients = {}
    while True:
        for seed in seeds:
            region = seed.get("region", "americas")
            if region not in clients:
                clients[region] = RiotClient(region)
            try:
                print(json.dumps(run_etl(store, clients[region], seed["game_name"], seed["tag"], args.count)), flush=True)
            except RiotAPIError as error:
                print(str(error), flush=True)
                if not args.interval:
                    raise SystemExit(1) from None
        if not args.interval:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError:
        raise SystemExit("Database operation failed. Check PostgreSQL and DATABASE_URL privately.") from None
    except RiotAPIError as error:
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        print("ETL stopped.")
