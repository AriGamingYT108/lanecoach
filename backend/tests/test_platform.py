import copy
import json
import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from backend.catalog import Catalog
from backend.coaching import CoachingError
from backend.platform.api import create_app
from backend.platform.coach import answer
from backend.platform.etl import extract_players, run_etl
from backend.platform.knowledge import seed_knowledge
from backend.platform.retrieval import retrieve
from backend.platform.store import Store, metadata


def full_fixture(match_id="NA1_fixture"):
    participants = []
    for team in (100, 200):
        for index, role in enumerate(("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")):
            participants.append({"participantId": index + (1 if team == 100 else 6), "teamPosition": role,
                "championName": ["Garen", "LeeSin", "Ahri", "Ashe", "Leona"][index] if team == 100 else ["Darius", "Vi", "Zed", "Jinx", "Nautilus"][index],
                "teamId": team, "win": team == 100, "kills": 2, "deaths": 1, "assists": 3,
                "totalMinionsKilled": 100, "neutralMinionsKilled": 4, "goldEarned": 8000,
                "perks": {"styles": [{"description": "primaryStyle", "selections": [{"perk": 8010}]}]}})
    return {"metadata": {"matchId": match_id}, "info": {"queueId": 420, "gameVersion": "16.20.1", "gameDuration": 1500, "participants": participants}}


class ExtractionTests(unittest.TestCase):
    def test_all_roles_and_opposing_players(self):
        rows = extract_players(full_fixture())
        self.assertEqual(len(rows), 10)
        self.assertEqual({r["role"] for r in rows}, {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"})
        self.assertEqual(rows[1]["opponent"], "Vi")
        self.assertEqual(rows[4]["opponent"], "Nautilus")
        self.assertEqual(rows[0]["cs"], 104)
        self.assertEqual(rows[0]["keystone"], 8010)

    def test_invalid_queue_roles_and_duplicate_ids(self):
        match = full_fixture()
        match["info"]["queueId"] = 440
        self.assertEqual(extract_players(match), [])
        match = full_fixture()
        match["info"]["participants"][0]["participantId"] = 2
        self.assertEqual(extract_players(match), [])
        match = full_fixture()
        match["info"]["participants"][0]["teamPosition"] = ""
        rows = extract_players(match)
        self.assertEqual(len(rows), 9)
        self.assertIsNone(next(r for r in rows if r["champion"] == "Darius")["opponent"])
        self.assertEqual(extract_players({}), [])


class PlatformStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store("sqlite://")
        self.store.initialize()
        seed_knowledge(self.store)

    def tearDown(self):
        self.store.engine.dispose()

    def test_sql_analytics_and_duplicate_prevention(self):
        match = full_fixture()
        self.assertTrue(self.store.save_match(match, extract_players(match)))
        self.assertFalse(self.store.save_match(match, extract_players(match)))
        result = self.store.analytics("LeeSin", "JUNGLE")
        self.assertEqual(result["overall"], {"sample_size": 1, "wins": 1, "win_rate": 100})
        self.assertEqual(result["runes"][0]["keystone"], 8010)
        self.assertEqual(result["opponents"][0]["opponent"], "Vi")
        self.assertEqual(self.store.analytics("Vi", "JUNGLE")["overall"]["win_rate"], 0)
        self.assertEqual(self.store.analytics("LeeSin", "TOP")["overall"]["sample_size"], 0)
        self.assertEqual(self.store.analytics("LeeSin", "JUNGLE", patch="16.19")["overall"]["sample_size"], 0)
        self.assertEqual(self.store.analytics("LeeSin", "JUNGLE", minimum=2)["runes"], [])
        self.assertEqual(self.store.analytics("' OR 1=1 --", "JUNGLE")["overall"]["sample_size"], 0)

    def test_retrieval_role_scope_and_repeatable_ingestion(self):
        seed_knowledge(self.store)
        self.assertEqual(self.store.overview()["documents"], 6)
        sources = retrieve(self.store, "jungle route gank farm", {"role": "JUNGLE"})
        self.assertTrue(any(s["id"] == "practice-jungle" for s in sources))
        self.assertFalse(any(s["role"] == "TOP" for s in sources))

    def test_etl_is_idempotent_and_paginates(self):
        client = Mock()
        client.get.side_effect = [{"puuid": "private-player"}, ["NA1_fixture"], full_fixture()]
        self.assertEqual(run_etl(self.store, client, "A name", "TAG")["inserted"], 1)
        client.get.side_effect = [{"puuid": "private-player"}, ["NA1_fixture"]]
        self.assertEqual(run_etl(self.store, client, "A name", "TAG")["duplicates"], 1)
        self.assertEqual(self.store.overview()["participants"], 10)

    def test_fastapi_conversation_and_follow_up(self):
        coach = Mock(return_value={"text": "Synthetic test reply", "sources": [], "model": "test", "analytics": None})
        app = create_app(self.store, Catalog(), coach)
        headers = {"X-LaneCoach-Client": "browser"}
        with TestClient(app) as client:
            request = {"profile": {"role": "UTILITY", "champion": "Leona"}, "question": "When can I roam?"}
            response = client.post("/api/coach", json=request, headers=headers)
            self.assertEqual(response.status_code, 200)
            session_id = response.json()["session_id"]
            request.update(session_id=session_id, question="What if my carry is behind?")
            self.assertEqual(client.post("/api/coach", json=request, headers=headers).status_code, 200)
            self.assertEqual(len(coach.call_args.args[4]), 2)
            conversation = client.get("/api/sessions/" + session_id).json()
            self.assertEqual(len(conversation["messages"]), 4)
            self.assertEqual(conversation["profile"]["role"], "UTILITY")
            request["profile"]["role"] = "TOP"
            self.assertEqual(client.post("/api/coach", json=request, headers=headers).status_code, 409)
            self.assertEqual(client.post("/api/coach", json=request).status_code, 403)
            self.assertEqual(client.post("/api/coach", json=request, headers={**headers, "Origin": "https://evil.example"}).status_code, 403)
            self.assertTrue(client.get("/api/health").json()["database_ready"])

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-placeholder"})
    def test_real_rag_payload_contains_retrieved_context_and_history(self):
        transport = Mock()
        transport.post.return_value = Mock(status_code=200, json=lambda: {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Practice [practice-jungle]"}]}]})
        catalog = Mock()
        catalog.abilities.return_value = None
        result = answer(self.store, catalog, {"role": "JUNGLE", "champion": "", "opponent": "", "patch": None}, "How should I route?", [{"role": "user", "content": "I want to improve map decisions"}], transport)
        payload = transport.post.call_args.kwargs["json"]
        parsed = json.loads(payload["input"])
        self.assertTrue(parsed["retrieved_sources"])
        self.assertEqual(parsed["profile"]["role"], "JUNGLE")
        self.assertEqual(len(parsed["conversation"]), 1)
        self.assertFalse(payload["store"])
        self.assertTrue(result["sources"])
        self.assertNotIn("test-placeholder", json.dumps(result))


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "PostgreSQL integration requires TEST_DATABASE_URL")
class PostgreSQLIntegrationTests(unittest.TestCase):
    def test_native_postgres_sql_and_fulltext_retrieval(self):
        # Use a dedicated empty test database; never run this against personal data.
        store = Store(os.environ["TEST_DATABASE_URL"])
        store.initialize()
        seed_knowledge(store)
        match = full_fixture("NA1_postgres_test")
        store.save_match(match, extract_players(match))
        self.assertEqual(store.analytics("LeeSin", "JUNGLE")["overall"]["sample_size"], 1)
        self.assertTrue(any(s["id"] == "practice-jungle" for s in retrieve(store, "jungle routing gank", {"role": "JUNGLE"})))
        store.engine.dispose()


if __name__ == "__main__":
    unittest.main()
