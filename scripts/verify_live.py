"""Explicit live integration check; never displays credentials or provider bodies."""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from dotenv import load_dotenv

from backend.app import REGIONS
from backend.catalog import Catalog
from backend.coaching import CoachingError, generate_coaching
from backend.database import MatchupDatabase
from backend.reports import build_report
from backend.riot_api import RiotAPIError, RiotClient
from backend.timeline import collect_timelines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coach", action="store_true", help="Make one paid OpenAI coaching request")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / "backend" / ".env")
    catalog = Catalog()
    try:
        result = catalog.refresh()
        print("Public references verified:", result)
    except (requests.RequestException, ValueError, KeyError, OSError):
        print("Public references unavailable; cached names remain usable.")
        return 1
    with MatchupDatabase() as db:
        pairs = db.list_matchups(limit=1)
        if not pairs:
            print("Collect a game before running the integration check.")
            return 1
        pair = pairs[0]
        records = db.matchup_records(pair["champion"], pair["opponent"])[:2]
        try:
            result = collect_timelines(RiotClient(REGIONS[records[0]["match_id"].split("_")[0]]), db, records)
        except RiotAPIError as error:
            print(str(error))
            return 1
        print("Timeline verification:", result)
        report = build_report(db, pair["champion"], pair["opponent"])
        print("Report verified:", pair["champion"], "vs", pair["opponent"], "with", report["timeline_matches"], "timelines")
    if args.coach:
        try:
            references = [catalog.abilities(name) for name in (pair["champion"], pair["opponent"])]
            result = generate_coaching(report, "Give me three practical goals for this matchup, distinguishing evidence from general advice.", references)
        except (CoachingError, requests.RequestException) as error:
            print(str(error) if isinstance(error, CoachingError) else "Champion reference request failed.")
            return 1
        print("AI coaching verified:", result["model"], "response characters:", len(result["text"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
