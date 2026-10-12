"""Local LaneCoach HTTP app. Start with python -m backend.app."""
import argparse
import csv
import io
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, send_file, Response
from werkzeug.exceptions import HTTPException

from .catalog import Catalog
from .coaching import generate_coaching
from .collector import collect_matches
from .database import DEFAULT_DB, MatchupDatabase
from .jobs import JobManager
from .reports import build_report, match_detail, orient
from .riot_api import RiotClient
from .timeline import collect_timelines

ROOT = Path(__file__).resolve().parent.parent
REGIONS = {"NA1": "americas", "BR1": "americas", "LA1": "americas", "LA2": "americas",
           "EUW1": "europe", "EUN1": "europe", "TR1": "europe", "RU": "europe",
           "KR": "asia", "JP1": "asia", "OC1": "sea", "PH2": "sea", "SG2": "sea",
           "TH2": "sea", "TW2": "sea", "VN2": "sea", "ME1": "europe"}


def create_app(db_path=DEFAULT_DB, testing=False):
    load_dotenv(Path(__file__).with_name(".env"))
    app = Flask(__name__, static_folder=str(ROOT / "frontend"), static_url_path="/static")
    app.config.update(TESTING=testing, MAX_CONTENT_LENGTH=16384,
                      TRUSTED_HOSTS=["localhost", "127.0.0.1", "[::1]"])
    catalog = Catalog()
    manager = JobManager(db_path)
    app.extensions["jobs"] = manager
    app.extensions["catalog"] = catalog
    token = secrets.token_urlsafe(32)
    riot_clients = {}

    def riot_client(region):
        if region not in riot_clients:
            riot_clients[region] = RiotClient(region)
        return riot_clients[region]

    @app.before_request
    def same_origin():
        if request.method == "POST":
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                return jsonify(error="Cross-origin requests are not allowed."), 403
            if not secrets.compare_digest(request.headers.get("X-LaneCoach-Token", ""), token):
                return jsonify(error="Refresh the app before starting a job."), 403

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https://ddragon.leagueoflegends.com data:; "
            "script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
        if request.path.startswith("/api/") and not request.path.startswith("/api/assets/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        return jsonify(error="The request failed. Check configuration or try again."), 500

    def integer(value, name, minimum=0, maximum=1000):
        try:
            if isinstance(value, bool):
                raise ValueError()
            number = int(value)
            if str(number) != str(value) or not minimum <= number <= maximum:
                raise ValueError()
            return number
        except (ValueError, TypeError):
            raise ValueError(f"{name} must be an integer between {minimum} and {maximum}.") from None

    def text(value, name, required=True, max_length=100):
        if not isinstance(value, str) or len(value) > max_length or (required and not value.strip()):
            raise ValueError(f"Provide a valid {name} (up to {max_length} characters).")
        return value.strip()

    def body():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object.")
        return data

    def pair(data):
        champion = catalog.resolve(text(data.get("champion"), "champion"))
        opponent = catalog.resolve(text(data.get("opponent"), "opponent"))
        patch = data.get("patch") or None
        if patch:
            patch = text(patch, "patch", max_length=20)
        return champion, opponent, patch

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "index.html")

    @app.get("/api/status")
    def status():
        with MatchupDatabase(db_path) as db:
            overview = db.overview()
            jobs = db.jobs()
        return jsonify(**overview, jobs=jobs, token=token,
                       riot_configured=bool(os.getenv("RIOT_API_KEY")),
                       ai_configured=bool(os.getenv("OPENAI_API_KEY")),
                       model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
                       catalog_version=catalog.data.get("version"))

    @app.get("/api/catalog")
    def get_catalog():
        return jsonify(catalog.data)

    @app.get("/api/assets/<kind>/<identifier>")
    def asset(kind, identifier):
        try:
            path = catalog.asset(kind, identifier)
        except (requests.RequestException, OSError, KeyError, TypeError):
            path = None
        if path is None:
            return Response(status=404)
        return send_file(path, mimetype="image/png", max_age=86400)

    @app.get("/api/matchups")
    def matchups():
        champion = request.args.get("champion") or None
        if champion:
            champion = catalog.resolve(text(champion, "champion"))
        minimum = integer(request.args.get("min_games", "1"), "min_games", 1, 100000)
        limit = integer(request.args.get("limit", "100"), "limit", 1, 1000)
        with MatchupDatabase(db_path) as db:
            rows = db.list_matchups(champion, request.args.get("patch") or None, minimum, limit)
        return jsonify(matchups=rows)

    @app.get("/api/report")
    def report():
        champion, opponent, patch = pair(request.args)
        with MatchupDatabase(db_path) as db:
            return jsonify(build_report(db, champion, opponent, patch))

    @app.get("/api/matches/<match_id>")
    def detail(match_id):
        with MatchupDatabase(db_path) as db:
            result = match_detail(db, match_id)
        return (jsonify(result), 200) if result else (jsonify(error="Match not found."), 404)

    @app.get("/api/export")
    def export():
        champion, opponent, patch = pair(request.args)
        with MatchupDatabase(db_path) as db:
            records = [orient(r, champion) for r in db.matchup_records(champion, opponent, patch)]
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["match_id", "patch", "champion", "opponent", "champion_win", "champion_cs", "opponent_cs", "champion_gold", "opponent_gold"])
        for match in records:
            def safe(value):
                # Prevent spreadsheet formulas in untrusted string fields.
                return "'" + value if isinstance(value, str) and value.startswith(("=", "+", "-", "@")) else value
            writer.writerow([safe(match.get(key)) for key in ("match_id", "patch", "champion", "opponent", "champion_win", "champion_cs", "opponent_cs", "champion_gold", "opponent_gold")])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=lanecoach-matches.csv"})

    @app.post("/api/collect")
    def collect():
        data = body()
        name, tag = text(data.get("game_name"), "game name"), text(data.get("tag_line"), "tag")
        region = data.get("region", "americas")
        if region not in {"americas", "europe", "asia", "sea"}:
            raise ValueError("Choose a valid Riot routing region.")
        count = integer(data.get("count", 100), "count", 1, 1000)
        start = integer(data.get("start", 0), "start", 0, 100000)
        if not os.getenv("RIOT_API_KEY"):
            raise ValueError("Add RIOT_API_KEY to backend/.env and restart LaneCoach.")
        def work(update):
            with MatchupDatabase(db_path) as db:
                return collect_matches(riot_client(region), db, name, tag, count, start, progress=update)
        return jsonify(manager.submit("collection", {"game_name": name, "tag_line": tag, "region": region, "count": count, "start": start}, work)), 202

    @app.post("/api/timelines")
    def timelines():
        data = body()
        champion, opponent, patch = pair(data)
        limit = integer(data.get("limit", 20), "limit", 1, 100)
        if not os.getenv("RIOT_API_KEY"):
            raise ValueError("Add RIOT_API_KEY to backend/.env and restart LaneCoach.")
        def work(update):
            with MatchupDatabase(db_path) as db:
                records = [r for r in db.matchup_records(champion, opponent, patch) if not db.get_timeline(r["match_id"])][:limit]
                grouped = {}
                for record in records:
                    region = REGIONS.get(record["match_id"].split("_", 1)[0])
                    if not region:
                        raise ValueError("Unknown region for a stored match.")
                    grouped.setdefault(region, []).append(record)
                total = {"inserted": 0, "duplicates": 0, "failed": 0, "skipped": 0}
                done = 0
                for region, group in grouped.items():
                    def progress(completed, _, summary):
                        update({"completed": done + completed, "total": len(records), **summary})
                    result = collect_timelines(riot_client(region), db, group, progress)
                    done += len(group)
                    for key in total:
                        total[key] += result[key]
                return total
        return jsonify(manager.submit("timelines", {"champion": champion, "opponent": opponent, "patch": patch}, work)), 202

    @app.post("/api/catalog/refresh")
    def refresh_catalog():
        return jsonify(manager.submit("catalog", {}, lambda update: catalog.refresh())), 202

    @app.post("/api/coach")
    def coach():
        data = body()
        champion, opponent, patch = pair(data)
        question = text(data.get("question", "How should I prepare for this top-lane matchup?"), "question", max_length=2000)
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Add OPENAI_API_KEY to backend/.env and restart LaneCoach to enable AI coaching.")
        def work(update):
            with MatchupDatabase(db_path) as db:
                report = build_report(db, champion, opponent, patch)
            abilities = []
            for name in (champion, opponent):
                try:
                    ability = catalog.abilities(name, patch)
                    if ability:
                        abilities.append(ability)
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    pass
            update({"stage": "Generating coaching from your report"})
            return generate_coaching(report, question, abilities)
        return jsonify(manager.submit("coaching", {"champion": champion, "opponent": opponent, "patch": patch}, work)), 202

    return app


def main():
    from waitress import serve
    parser = argparse.ArgumentParser(description="Run the local LaneCoach app")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    app = create_app(args.db)
    print(f"LaneCoach is ready at http://127.0.0.1:{args.port}", flush=True)
    try:
        serve(app, host="127.0.0.1", port=args.port, threads=8)
    except KeyboardInterrupt:
        pass
    finally:
        app.extensions["jobs"].close()


if __name__ == "__main__":
    main()
