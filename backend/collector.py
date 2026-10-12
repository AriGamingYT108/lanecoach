"""Collect a Riot ID's ranked Solo/Duo history into SQLite."""
import argparse
import json
from urllib.parse import quote

if __package__:
    from .database import DEFAULT_DB, MatchupDatabase
    from .matchup import extract_top_matchup
    from .riot_api import RiotAPIError, RiotClient
else:
    from database import DEFAULT_DB, MatchupDatabase
    from matchup import extract_top_matchup
    from riot_api import RiotAPIError, RiotClient


def collect_matches(client, db, game_name, tag_line, count=100, start=0, progress=None):
    if count < 1 or start < 0 or not game_name.strip() or not tag_line.strip():
        raise ValueError("Provide a Riot ID, positive count, and nonnegative start")
    account = client.get(f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag_line, safe='')}")
    if not isinstance(account, dict) or not isinstance(account.get("puuid"), str) or not account["puuid"]:
        raise RiotAPIError("Account response is missing PUUID")
    puuid = quote(account["puuid"], safe="")
    summary = dict(fetched=0, inserted=0, duplicates=0, skipped=0, failed=0)
    offset, remaining = start, count
    while remaining:
        page_size = min(100, remaining)
        ids = client.get(f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
                         params={"queue": 420, "type": "ranked", "start": offset, "count": page_size})
        if not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids):
            raise RiotAPIError("Match history response is invalid")
        for match_id in ids:
            if db.contains(match_id):
                summary["duplicates"] += 1
                if progress:
                    progress(dict(summary))
                continue
            try:
                match = client.get(f"/lol/match/v5/matches/{quote(match_id, safe='')}")
            except RiotAPIError as error:
                if error.status in {401, 403, 429}:
                    raise
                summary["failed"] += 1
                if progress:
                    progress(dict(summary))
                continue
            summary["fetched"] += 1
            matchup = extract_top_matchup(match)
            if matchup is None or matchup["match_id"] != match_id:
                summary["skipped"] += 1
            elif db.save_matchup(matchup):
                summary["inserted"] += 1
            else:
                summary["duplicates"] += 1
            if progress:
                progress(dict(summary))
        if len(ids) < page_size:
            break
        offset += len(ids)
        remaining -= len(ids)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_name")
    parser.add_argument("tag_line", help="Riot ID tag without #")
    parser.add_argument("--region", choices=["americas", "europe", "asia", "sea"], default="americas")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    try:
        client = RiotClient(args.region)
        with MatchupDatabase(args.db) as db:
            print(json.dumps(collect_matches(client, db, args.game_name, args.tag_line, args.count, args.start), indent=2))
    except (RiotAPIError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
