import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from backend.app import create_app
from backend.catalog import Catalog
from backend.coaching import CoachingError, generate_coaching
from backend.database import MatchupDatabase
from backend.jobs import JobManager
from backend.matchup import extract_top_matchup
from backend.reports import build_report
from backend.timeline import collect_timelines, extract_timeline
from backend.tests.test_backend import fixture


def timeline_fixture(match_id="NA1_1", end=900000):
    frames = []
    for stamp in (0, 540000, 593000, 620000, 899000, end):
        if stamp > end:
            continue
        frames.append({"timestamp": stamp, "participantFrames": {
            "1": {"totalGold": 4000, "minionsKilled": 100, "jungleMinionsKilled": 2, "level": 9},
            "6": {"totalGold": 3500, "minionsKilled": 90, "jungleMinionsKilled": 0, "level": 8}},
            "events": [{"type": "ITEM_PURCHASED", "timestamp": stamp, "participantId": 1, "itemId": 1054}]})
    return {"metadata": {"matchId": match_id}, "info": {"frames": frames}}


def record_fixture(match_id="NA1_1", reverse=False):
    match = fixture(match_id)
    match["info"]["participants"][0]["participantId"] = 1
    match["info"]["participants"][1]["participantId"] = 6
    if reverse:
        match["info"]["participants"][0]["championName"] = "Darius"
        match["info"]["participants"][1]["championName"] = "Garen"
    return extract_top_matchup(match)


class TimelineTests(unittest.TestCase):
    def test_irregular_timestamps(self):
        timeline = extract_timeline(timeline_fixture(), record_fixture())
        self.assertEqual(timeline["snapshots"]["10"]["timestamp"], 593000)
        self.assertEqual(timeline["snapshots"]["15"]["timestamp"], 900000)
        self.assertEqual(timeline["snapshots"]["10"]["champion_cs"], 102)
        self.assertEqual(timeline["events"][0]["itemId"], 1054)

    def test_missing_ids_mismatched_game_and_short_game(self):
        self.assertIsNone(extract_timeline(timeline_fixture(), extract_top_matchup(fixture())))
        self.assertIsNone(extract_timeline(timeline_fixture("wrong"), record_fixture()))
        timeline = extract_timeline(timeline_fixture(end=550000), record_fixture())
        self.assertIsNone(timeline["snapshots"]["10"])
        self.assertIsNone(timeline["snapshots"]["15"])
        self.assertIsNone(extract_timeline({}, record_fixture()))

    def test_missing_numeric_frame_does_not_become_zero(self):
        timeline = timeline_fixture()
        for frame in timeline["info"]["frames"]:
            frame["participantFrames"]["1"].pop("jungleMinionsKilled")
        result = extract_timeline(timeline, record_fixture())
        self.assertIsNone(result["snapshots"]["10"]["champion_cs"])

    def test_legacy_records_are_enriched_and_cached(self):
        client = Mock()
        full = fixture()
        full["info"]["participants"][0]["participantId"] = 1
        full["info"]["participants"][1]["participantId"] = 6
        client.get.side_effect = [full, timeline_fixture()]
        with MatchupDatabase(":memory:") as db:
            old = extract_top_matchup(fixture())
            db.save_matchup(old)
            self.assertEqual(collect_timelines(client, db, [old])["inserted"], 1)
            self.assertEqual(collect_timelines(client, db, [old])["duplicates"], 1)
            self.assertEqual(client.get.call_count, 2)


class ReportTests(unittest.TestCase):
    def test_orientation_denominators_and_patch_filter(self):
        with MatchupDatabase(":memory:") as db:
            first = record_fixture()
            second = record_fixture("NA1_2", reverse=True)
            second["champion_gold"] = None
            second["opponent_gold"] = 9000
            db.save_matchup(first)
            db.save_matchup(second)
            db.save_timeline("NA1_2", extract_timeline(timeline_fixture("NA1_2"), second))
            report = build_report(db, "Garen", "Darius")
            self.assertEqual(report["summary"]["win_rate"], 50)
            self.assertEqual(report["champion_stats"]["gold"], {"value": 9500, "samples": 2})
            self.assertEqual(report["opponent_stats"]["gold"]["samples"], 1)
            self.assertEqual(report["timeline"]["10"]["gold_difference"], {"value": -500, "samples": 1})
            self.assertEqual(report["timeline"]["10"]["cs_difference"]["value"], -12)
            self.assertEqual(report["matches"][0]["champion"], "Garen")
            self.assertEqual(report["champion_stats"]["items"][0]["games"], 2)
            self.assertEqual(build_report(db, "Garen", "Darius", "16.19")["summary"]["matches"], 0)

    def test_empty_report(self):
        with MatchupDatabase(":memory:") as db:
            report = build_report(db, "Garen", "Darius")
            self.assertIsNone(report["champion_stats"]["cs"]["value"])
            self.assertEqual(report["matches"], [])
            self.assertIn("No recorded games", report["observations"][0])


class CoachingTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret", "OPENAI_MODEL": "gpt-4.1-mini"})
    def test_response_and_no_player_data(self):
        session = Mock()
        session.post.return_value = Mock(status_code=200, json=lambda: {
            "status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Practice plan"}]}]})
        result = generate_coaching({"summary": {"matches": 2}, "matches": [{"puuid": "private-player"}]}, "Help", session=session)
        self.assertEqual(result["text"], "Practice plan")
        payload = session.post.call_args.kwargs["json"]
        self.assertFalse(payload["store"])
        self.assertNotIn("private-player", payload["input"])
        self.assertNotIn("test-secret", json.dumps(result))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-secret"})
    def test_errors_do_not_expose_provider_bodies(self):
        session = Mock()
        for status in (401, 403, 429, 500):
            session.post.return_value = Mock(status_code=status, text="test-secret")
            with self.assertRaises(CoachingError) as error:
                generate_coaching({}, "Help", session=session)
            self.assertNotIn("test-secret", str(error.exception))
        session.post.side_effect = requests.Timeout("test-secret")
        with self.assertRaises(CoachingError) as error:
            generate_coaching({}, "Help", session=session)
        self.assertNotIn("test-secret", str(error.exception))

    @patch.dict(os.environ, {"OPENAI_API_KEY": ""})
    def test_missing_key(self):
        with self.assertRaises(CoachingError):
            generate_coaching({}, "Help")


class CatalogTests(unittest.TestCase):
    def test_assets_restrict_urls_and_cache_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(Path(directory) / "catalog.json")
            catalog.data["champions"] = {
                "Garen": {"image": "https://ddragon.leagueoflegends.com/cdn/16.20.1/img/champion/Garen.png"},
                "Unsafe": {"image": "https://other.example/private"}}
            with patch("backend.catalog.requests.get") as get:
                get.return_value = Mock(status_code=200, content=b"\x89PNG\r\n\x1a\nfixture")
                first = catalog.asset("champions", "Garen")
                self.assertTrue(first.exists())
                self.assertEqual(catalog.asset("champions", "Garen"), first)
                self.assertIsNone(catalog.asset("champions", "Unsafe"))
                self.assertIsNone(catalog.asset("unknown", "Garen"))
                self.assertIsNone(catalog.asset("champions", "../../.env"))
                self.assertEqual(get.call_count, 1)

    def test_html_is_not_cached_as_an_image(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Catalog(Path(directory) / "catalog.json")
            catalog.data["items"] = {"1": {"image": "https://ddragon.leagueoflegends.com/img/1.png"}}
            with patch("backend.catalog.requests.get", return_value=Mock(status_code=200, content=b"<html>")):
                self.assertIsNone(catalog.asset("items", "1"))


class AppTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "app.sqlite3"
        self.env = patch.dict(os.environ, {"OPENAI_API_KEY": "", "RIOT_API_KEY": ""})
        self.env.start()
        self.app = create_app(self.path, testing=True)
        self.client = self.app.test_client()
        self.token = self.client.get("/api/status").json["token"]
        self.headers = {"X-LaneCoach-Token": self.token}

    def tearDown(self):
        self.app.extensions["jobs"].close()
        self.env.stop()
        self.directory.cleanup()

    def test_pages_status_and_no_secrets(self):
        for path in ("/", "/static/app.js", "/static/styles.css"):
            with self.client.get(path) as response:
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/status").json["matches"], 0)
        self.assertEqual(self.client.get("/api/matchups").json["matchups"], [])
        self.assertEqual(self.client.get("/api/report?champion=Garen&opponent=Darius").json["summary"]["matches"], 0)
        self.assertEqual(self.client.get("/api/matches/missing").status_code, 404)
        self.assertNotIn("RIOT_API_KEY", self.client.get("/api/status").text)
        self.assertEqual(self.client.get("/static/../backend/.env").status_code, 404)

    def test_csrf_origin_and_input_validation(self):
        self.assertEqual(self.client.post("/api/collect", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/collect", json={}, headers={**self.headers, "Origin": "https://other.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/status", headers={"Host": "evil.example"}).status_code, 400)
        self.assertEqual(self.client.get("/api/report").status_code, 400)
        self.assertEqual(self.client.get("/api/matchups?limit=-1").status_code, 400)
        self.assertEqual(self.client.post("/api/collect", json={}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.post("/api/coach", json={"champion": "Garen", "opponent": "Darius"}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get("/api/assets/unknown/missing").status_code, 404)

    def test_real_report_and_csv(self):
        with MatchupDatabase(self.path) as db:
            db.save_matchup(record_fixture())
        report = self.client.get("/api/report?champion=Darius&opponent=Garen").json
        self.assertEqual(report["summary"]["win_rate"], 0)
        self.assertEqual(self.client.get("/api/status").json["pairs"], 1)
        export = self.client.get("/api/export?champion=Garen&opponent=Darius")
        self.assertEqual(export.status_code, 200)
        self.assertIn("NA1_1", export.text)
        self.assertIn("attachment", export.headers["Content-Disposition"])

    @patch("backend.app.collect_matches")
    @patch("backend.app.RiotClient")
    def test_collection_job(self, client_class, collect):
        collect.return_value = {"inserted": 1}
        with patch.dict(os.environ, {"RIOT_API_KEY": "test-placeholder"}):
            response = self.client.post("/api/collect", json={"game_name": "Player", "tag_line": "NA1", "count": 5}, headers=self.headers)
        self.assertEqual(response.status_code, 202)
        self.app.extensions["jobs"].close()
        jobs = self.client.get("/api/status").json["jobs"]
        self.assertEqual(jobs[0]["status"], "completed")
        self.assertEqual(jobs[0]["result"], {"inserted": 1})

    @patch("backend.app.generate_coaching", return_value={"text": "Synthetic test plan", "model": "test"})
    @patch("backend.catalog.Catalog.abilities", return_value=None)
    def test_coaching_job_result_is_persisted(self, abilities, coaching):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"}):
            response = self.client.post("/api/coach", json={"champion": "Garen", "opponent": "Darius", "question": "Help with farm"}, headers=self.headers)
        self.assertEqual(response.status_code, 202)
        self.app.extensions["jobs"].close()
        job = self.client.get("/api/status").json["jobs"][0]
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["text"], "Synthetic test plan")
        self.assertEqual(coaching.call_args.args[1], "Help with farm")

    @patch("backend.app.collect_timelines", return_value={"inserted": 1, "duplicates": 0, "failed": 0, "skipped": 0})
    @patch("backend.app.RiotClient")
    def test_timeline_job(self, client_class, collect):
        with MatchupDatabase(self.path) as db:
            db.save_matchup(record_fixture())
        with patch.dict(os.environ, {"RIOT_API_KEY": "test-placeholder"}):
            response = self.client.post("/api/timelines", json={"champion": "Garen", "opponent": "Darius"}, headers=self.headers)
        self.assertEqual(response.status_code, 202)
        self.app.extensions["jobs"].close()
        self.assertEqual(self.client.get("/api/status").json["jobs"][0]["result"]["inserted"], 1)
        client_class.assert_called_once_with("americas")


class JobTests(unittest.TestCase):
    def test_concurrency_failure_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "jobs.sqlite3"
            manager = JobManager(path)
            release = threading.Event()
            def work(update):
                release.wait(5)
                return {"inserted": 1}
            manager.submit("collection", {}, work)
            with self.assertRaises(ValueError):
                manager.submit("collection", {}, work)
            release.set()
            manager.close()
            with MatchupDatabase(path) as db:
                self.assertEqual(db.jobs()[0]["status"], "completed")
                db.save_job({"id": "unfinished", "status": "running"})
            manager = JobManager(path)
            with MatchupDatabase(path) as db:
                self.assertEqual(db.jobs()[0]["status"], "interrupted")
            def fail(update):
                raise RuntimeError("secret-in-exception")
            manager.submit("collection", {}, fail)
            manager.close()
            with MatchupDatabase(path) as db:
                self.assertEqual(db.jobs()[0]["status"], "failed")
                self.assertNotIn("secret-in-exception", db.jobs()[0]["error"])


if __name__ == "__main__":
    unittest.main()
