import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import requests
from backend.collector import collect_matches
from backend.database import MatchupDatabase
from backend.matchup import extract_top_matchup
from backend.riot_api import RiotAPIError, RiotClient


def fixture(match_id="NA1_1"):
    players = [dict(teamId=team, championName=name, win=win, teamPosition="TOP",
                    kills=5, deaths=2, assists=3, totalMinionsKilled=150,
                    neutralMinionsKilled=10, goldEarned=10000,
                    perks={"styles": [{"selections": [{"perk": 8010}]}]},
                    item0=1054, item6=3340)
               for team, name, win in ((100, "Garen", True), (200, "Darius", False))]
    return {"metadata": {"matchId": match_id}, "info": {"queueId": 420,
            "gameVersion": "16.20.123.456", "gameDuration": 1800, "participants": players}}


class ExtractionTests(unittest.TestCase):
    def test_fields_and_orientation(self):
        match = fixture()
        result = extract_top_matchup(match)
        for key, expected in {"champion": "Garen", "opponent": "Darius", "winner": "Garen",
                "champion_kda": [5, 2, 3], "champion_cs": 160, "opponent_gold": 10000,
                "champion_items": [1054, 3340], "opponent_runes": [8010],
                "patch_major_minor": "16.20"}.items():
            self.assertEqual(result[key], expected)
        match["info"]["participants"].reverse()
        self.assertEqual(extract_top_matchup(match), result)

    def test_reject_invalid_matches(self):
        mutations = [lambda m: m["info"].update(queueId=440),
                     lambda m: m["info"]["participants"].pop(),
                     lambda m: m["info"]["participants"][1].update(teamId=100),
                     lambda m: m["info"]["participants"][1].update(win=True),
                     lambda m: m["info"]["participants"][0].pop("win"),
                     lambda m: m["metadata"].clear(),
                     lambda m: m["info"]["participants"][0].update(teamPosition="")]
        for mutate in mutations:
            match = fixture()
            mutate(match)
            self.assertIsNone(extract_top_matchup(match))
        for bad in (None, {}, {"info": None}):
            self.assertIsNone(extract_top_matchup(bad))

    def test_optional_missing_data(self):
        match = fixture()
        for key in ("kills", "totalMinionsKilled", "goldEarned", "perks", "item0", "item6"):
            match["info"]["participants"][0].pop(key)
        result = extract_top_matchup(match)
        self.assertEqual(result["champion_kda"], [None, 2, 3])
        self.assertIsNone(result["champion_cs"])
        self.assertIsNone(result["champion_gold"])
        self.assertEqual(result["champion_runes"], [])
        self.assertEqual(result["champion_items"], [])


class DatabaseTests(unittest.TestCase):
    def test_list_groups_orientations_and_filters(self):
        with MatchupDatabase(":memory:") as db:
            self.assertEqual(db.list_matchups(), [])
            for match_id, blue, red, version in (
                    ("1", "Garen", "Darius", "16.20.1"),
                    ("2", "Darius", "Garen", "16.20.2"),
                    ("3", "Garen", "Teemo", "16.19.1")):
                match = fixture(match_id)
                match["info"]["gameVersion"] = version
                match["info"]["participants"][0]["championName"] = blue
                match["info"]["participants"][1]["championName"] = red
                db.save_matchup(extract_top_matchup(match))
            pairs = db.list_matchups()
            self.assertEqual(len(pairs), 2)
            self.assertEqual((pairs[0]["champion"], pairs[0]["opponent"],
                              pairs[0]["matches"], pairs[0]["win_rate"]), ("Darius", "Garen", 2, 50))
            self.assertEqual(len(db.list_matchups(min_games=2)), 1)
            self.assertEqual(len(db.list_matchups(limit=1)), 1)
            self.assertEqual(len(db.list_matchups(patch="16.19")), 1)
            self.assertEqual(db.list_matchups(champion="garen")[0]["champion"], "Garen")
            self.assertEqual(db.list_matchups(champion="Teemo")[0]["win_rate"], 0)
            self.assertEqual(db.list_matchups(champion="missing"), [])
            self.assertEqual(db.list_matchups(champion="' OR 1=1 --"), [])
            for kwargs in ({"limit": 0}, {"min_games": 0}):
                with self.assertRaises(ValueError):
                    db.list_matchups(**kwargs)

    def test_list_mirror_sample_size(self):
        match = fixture()
        match["info"]["participants"][1]["championName"] = "Garen"
        with MatchupDatabase(":memory:") as db:
            db.save_matchup(extract_top_matchup(match))
            result = db.list_matchups()[0]
            self.assertEqual((result["matches"], result["sample_size"], result["win_rate"]), (1, 2, 50))

    def test_persistence_duplicates_and_queries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            first = extract_top_matchup(fixture())
            with MatchupDatabase(path) as db:
                self.assertTrue(db.save_matchup(first))
                self.assertFalse(db.save_matchup(dict(first, champion_win=False)))
                self.assertEqual(db.get_matchup("NA1_1"), first)
                second = fixture("NA1_2")
                second["info"]["participants"][0]["championName"] = "Darius"
                second["info"]["participants"][1]["championName"] = "Garen"
                db.save_matchup(extract_top_matchup(second))
                self.assertEqual(db.win_rate("garen", "darius")["win_rate"], 50)
                self.assertEqual(db.win_rate("Darius", "Garen")["sample_size"], 2)
                self.assertEqual(db.win_rate("Garen", "Darius", "16.20")["wins"], 1)
                self.assertIsNone(db.win_rate("Garen", "Darius", "16.19")["win_rate"])
                self.assertIsNone(db.win_rate("' OR 1=1 --", "Darius")["win_rate"])
            with MatchupDatabase(path) as db:
                self.assertTrue(db.contains("NA1_1"))
                self.assertEqual(db.get_matchup("NA1_1"), first)
                self.assertIsNone(db.get_matchup("missing"))

    def test_mirror(self):
        match = fixture()
        match["info"]["participants"][1]["championName"] = "Garen"
        with MatchupDatabase(":memory:") as db:
            db.save_matchup(extract_top_matchup(match))
            result = db.win_rate("Garen", "Garen")
            self.assertEqual((result["matches"], result["sample_size"], result["win_rate"]), (1, 2, 50))


class TransportTests(unittest.TestCase):
    def client(self, responses, retries=3):
        session, sleep = Mock(), Mock()
        session.get.side_effect = responses
        return RiotClient(api_key="test-placeholder", session=session, sleep=sleep, retries=retries), session, sleep

    def test_429(self):
        client, session, sleep = self.client([Mock(status_code=429, headers={"Retry-After": "12"}),
                                            Mock(status_code=200, json=lambda: {})])
        self.assertEqual(client.get("/test"), {})
        self.assertAlmostEqual(sleep.call_args.args[0], 12, delta=0.1)
        self.assertEqual(session.get.call_count, 2)

    def test_network_and_server(self):
        client, _, sleep = self.client([requests.Timeout("secret"), Mock(status_code=503),
                                       Mock(status_code=200, json=lambda: [])])
        self.assertEqual(client.get("/test"), [])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    def test_bounded_sanitized_errors(self):
        for status in (401, 403, 404):
            client, session, _ = self.client([Mock(status_code=status)])
            with self.assertRaises(RiotAPIError) as error:
                client.get("/test")
            self.assertEqual(error.exception.status, status)
            self.assertEqual(session.get.call_count, 1)
        client, _, _ = self.client([requests.Timeout("secret")] * 4)
        with self.assertRaises(RiotAPIError) as error:
            client.get("/test")
        self.assertNotIn("secret", str(error.exception))

    def test_invalid_json(self):
        client, _, _ = self.client([Mock(status_code=200, json=Mock(side_effect=ValueError("secret")))])
        with self.assertRaises(RiotAPIError):
            client.get("/test")

    def test_exhausted_429_cooldown(self):
        client, _, sleep = self.client([Mock(status_code=429, headers={"Retry-After": "10"}),
                                       Mock(status_code=200, json=lambda: {})], retries=0)
        with self.assertRaises(RiotAPIError):
            client.get("/test")
        client.get("/next")
        self.assertAlmostEqual(sleep.call_args.args[0], 10, delta=0.1)


class CollectorTests(unittest.TestCase):
    def test_pagination_duplicates_and_encoding(self):
        client = Mock()
        ids = [f"NA1_{i}" for i in range(101)]
        def response(path, params=None):
            if "accounts/" in path:
                return {"puuid": "player"}
            if path.endswith("/ids"):
                self.assertEqual(params["queue"], 420)
                return ids[params["start"]:params["start"] + params["count"]]
            return fixture(path.rsplit("/", 1)[1])
        client.get.side_effect = response
        with MatchupDatabase(":memory:") as db:
            self.assertEqual(collect_matches(client, db, "Name /", "NA1", count=101)["inserted"], 101)
            self.assertEqual(collect_matches(client, db, "Name /", "NA1", count=101)["duplicates"], 101)
        self.assertIn("Name%20%2F", client.get.call_args_list[0].args[0])

    def test_failed_and_ineligible(self):
        client = Mock()
        client.get.side_effect = [{"puuid": "p"}, ["NA1_1", "NA1_2", "NA1_3"],
                                  RiotAPIError("HTTP 404", 404), {}, fixture("NA1_3")]
        with MatchupDatabase(":memory:") as db:
            result = collect_matches(client, db, "Name", "NA1")
        self.assertEqual((result["failed"], result["skipped"], result["inserted"]), (1, 1, 1))

    def test_abort_auth_or_rate_limit(self):
        for status in (401, 403, 429):
            client = Mock()
            client.get.side_effect = [{"puuid": "p"}, ["NA1_1"], RiotAPIError("failure", status)]
            with MatchupDatabase(":memory:") as db, self.assertRaises(RiotAPIError):
                collect_matches(client, db, "Name", "NA1")

    def test_invalid_responses(self):
        for responses in ([{}], [{"puuid": "p"}, {}]):
            client = Mock()
            client.get.side_effect = responses
            with MatchupDatabase(":memory:") as db, self.assertRaises(RiotAPIError):
                collect_matches(client, db, "Name", "NA1")


if __name__ == "__main__":
    unittest.main()
