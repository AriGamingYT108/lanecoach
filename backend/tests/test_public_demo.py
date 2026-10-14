import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from backend.platform.api import create_app
from backend.platform.store import Store
from backend.coaching import CoachingError
from backend.platform.demo import Demo

ENV = {'APP_ENV': 'production', 'APP_SECRET': 'test-app-secret-for-isolation-123456789',
       'INTERNAL_PROXY_TOKEN': 'test-proxy-secret-for-testing-123456789',
       'FRONTEND_ORIGIN': 'https://demo.example', 'AI_DAILY_REQUEST_LIMIT': '2',
       'AI_VISITOR_DAILY_LIMIT': '2', 'AI_VISITOR_MINUTE_LIMIT': '2'}
HEADERS = {'X-LaneCoach-Proxy': ENV['INTERNAL_PROXY_TOKEN'], 'Origin': ENV['FRONTEND_ORIGIN'],
           'X-LaneCoach-Client': 'browser'}
BODY = {'profile': {'role': 'JUNGLE'}, 'question': 'How should I practice?'}


class PublicDemoTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, ENV)
        environment.start()
        self.addCleanup(environment.stop)
        self.store = Store('sqlite://')
        self.coach = Mock(return_value={'text': 'Synthetic demo reply', 'sources': [], 'model': 'test', 'analytics': None})
        self.app = create_app(self.store, coach_fn=self.coach)

    def initialize(self, client):
        response = client.get('/api/visitor', headers=HEADERS)
        self.assertEqual(response.status_code, 200)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('Secure', response.headers['set-cookie'])
        return {**HEADERS, 'X-LaneCoach-CSRF': response.json()['csrf_token']}

    def test_one_visitor_cannot_read_or_continue_another_conversation(self):
        with TestClient(self.app, base_url='https://testserver') as first, TestClient(self.app, base_url='https://testserver') as second:
            h1, h2 = self.initialize(first), self.initialize(second)
            reply = first.post('/api/coach', json=BODY, headers=h1)
            self.assertEqual(reply.status_code, 200)
            session = reply.json()['session_id']
            self.assertEqual(first.get('/api/sessions/' + session, headers=h1).status_code, 200)
            self.assertEqual(second.get('/api/sessions/' + session, headers=h2).status_code, 404)
            self.assertEqual(second.post('/api/coach', json={**BODY, 'session_id': session}, headers=h2).status_code, 404)
            self.assertEqual(self.coach.call_count, 1)

    def test_forged_cookie_csrf_and_direct_api_access_are_rejected(self):
        with TestClient(self.app, base_url='https://testserver') as client:
            headers = self.initialize(client)
            self.assertEqual(client.get('/api/health').status_code, 403)
            self.assertEqual(client.post('/api/coach', json=BODY, headers=HEADERS).status_code, 403)
            self.assertEqual(client.post('/api/coach', json=BODY, headers={**headers, 'Origin': 'https://evil.example'}).status_code, 403)
            client.cookies.clear()
            client.cookies.set('lanecoach_visitor', 'f' * 64 + '.' + 'x' * 64)
            self.assertEqual(client.post('/api/coach', json=BODY, headers=headers).status_code, 403)
            self.coach.assert_not_called()

    def test_global_daily_cap_applies_even_after_new_cookie(self):
        with TestClient(self.app, base_url='https://testserver') as client:
            headers = self.initialize(client)
            for _ in range(2):
                self.assertEqual(client.post('/api/coach', json=BODY, headers=headers).status_code, 200)
            client.cookies.clear()
            headers = self.initialize(client)
            self.assertEqual(client.post('/api/coach', json=BODY, headers=headers).status_code, 429)
            self.assertEqual(self.coach.call_count, 2)

    def test_uncertain_provider_failure_still_consumes_reserved_attempt(self):
        self.coach.side_effect = CoachingError('Synthetic provider failure')
        with TestClient(self.app, base_url='https://testserver') as client:
            headers = self.initialize(client)
            self.assertEqual(client.post('/api/coach', json=BODY, headers=headers).status_code, 502)
            self.assertEqual(client.post('/api/coach', json=BODY, headers=headers).status_code, 502)
            self.assertEqual(client.post('/api/coach', json=BODY, headers=headers).status_code, 429)

    def test_readiness_supports_railway_and_fails_when_database_not_ready(self):
        with TestClient(self.app, base_url='https://testserver') as client:
            self.assertEqual(client.get('/api/ready', headers={'Host': 'healthcheck.railway.app'}).status_code, 200)
            self.app.state.ready = False
            self.assertEqual(client.get('/api/ready').status_code, 503)

    def test_rejected_visitor_budget_rolls_back_global_reservation(self):
        self.store.initialize()
        self.assertFalse(self.store.reserve_requests({'global:test': 5, 'visitor:test': 0}))
        self.assertTrue(self.store.reserve_requests({'global:test': 1, 'visitor:other': 5}))

    def test_railway_fails_closed_if_production_secrets_missing(self):
        with patch.dict(os.environ, {'APP_ENV': 'local', 'RAILWAY_ENVIRONMENT_ID': 'test', 'APP_SECRET': ''}):
            with self.assertRaises(RuntimeError):
                Demo()

    def test_railway_postgres_url_uses_installed_driver(self):
        store = Store('postgresql://test:test@localhost/example')
        try:
            self.assertEqual(store.engine.dialect.driver, 'psycopg')
        finally:
            store.engine.dispose()


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Needs dedicated PostgreSQL test database')
class PostgreSQLBudgetTests(unittest.TestCase):
    def test_concurrent_reservations_cannot_exceed_global_cap(self):
        store = Store(os.environ['TEST_DATABASE_URL'])
        store.initialize()
        bucket = 'test:' + uuid4().hex
        try:
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted = list(pool.map(lambda _: store.reserve_requests({bucket: 5}), range(20)))
            self.assertEqual(sum(accepted), 5)
        finally:
            with store.engine.begin() as connection:
                connection.execute(text('DELETE FROM lc_request_budgets WHERE bucket=:bucket'), {'bucket': bucket})
            store.engine.dispose()
