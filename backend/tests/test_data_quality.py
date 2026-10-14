import copy
import os
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.platform.api import create_app
from backend.platform.coverage import coverage
from backend.platform.etl import collect_network, extract_players, run_etl
from backend.platform.store import Store, players, matches
from backend.riot_api import RiotAPIError
from backend.tests.test_platform import full_fixture
from backend.platform.maintenance import verify_restore
from backend.platform.coach import answer
from backend.platform.promote import promote


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.store = Store('sqlite://')
        self.store.initialize()

    def tearDown(self):
        self.store.engine.dispose()

    def test_invalid_optional_values_become_unknown_not_zero(self):
        match = full_fixture()
        p = match['info']['participants'][0]
        p.update(kills=-1, deaths=True, goldEarned='8000', totalMinionsKilled=-2,
                 perks={'styles': [{'selections': 'invalid'}]})
        row = extract_players(match)[0]
        for key in ('kills', 'deaths', 'gold', 'cs', 'keystone'):
            self.assertIsNone(row[key])
        self.assertTrue(self.store.save_match(match, extract_players(match)))
        result = coverage(self.store)
        self.assertEqual(result['missing_fields']['missing_gold'], 1)
        self.assertEqual(result['missing_fields']['missing_cs'], 1)

    def test_ambiguous_roles_and_inconsistent_outcomes_rejected(self):
        match = full_fixture()
        match['info']['participants'][1]['teamPosition'] = 'TOP'
        self.assertEqual(extract_players(match), [])
        match = full_fixture()
        match['info']['participants'][0]['win'] = False
        self.assertEqual(extract_players(match), [])
        match = full_fixture()
        match['info']['gameDuration'] = 'invalid'
        self.assertEqual(extract_players(match), [])

    def test_caller_cannot_store_fabricated_normalized_stats(self):
        match = full_fixture()
        rows = extract_players(match)
        rows[0]['gold'] = 999999
        with self.assertRaises(ValueError):
            self.store.save_match(match, rows)
        self.assertEqual(self.store.overview()['matches'], 0)

    def test_cloud_evidence_copy_is_idempotent_and_excludes_conversations(self):
        match = full_fixture()
        self.store.save_match(match, extract_players(match))
        run_id = self.store.start_run('americas', '0' * 64, 1)
        self.store.record_source('NA1_fixture', run_id)
        self.store.finish_run(run_id, {'inserted': 1})
        self.store.new_session({'role': 'TOP'})
        target = Store('sqlite://')
        try:
            self.assertEqual(promote(self.store, target)['inserted'], 1)
            self.assertEqual(promote(self.store, target)['duplicates'], 1)
            self.assertEqual(target.overview()['participants'], 10)
            self.assertEqual(coverage(target)['matches_without_provenance'], 0)
            self.assertEqual(coverage(target)['regions'][0]['seed_accounts'], 1)
            with target.engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT COUNT(*) FROM lc_sessions')).scalar_one(), 0)
        finally:
            target.engine.dispose()

    def test_constraints_protect_direct_writes(self):
        match = full_fixture()
        self.store.save_match(match, extract_players(match))
        with self.assertRaises(IntegrityError), self.store.engine.begin() as connection:
            connection.execute(players.update().values(gold=-1))

    def test_bounded_discovery_and_source_privacy(self):
        match = full_fixture()
        for index, p in enumerate(match['info']['participants']):
            p['puuid'] = 'private-puuid-' + str(index)
        client = Mock(base_url='https://americas.api.riotgames.com')
        client.get.side_effect = [{'puuid': 'private-puuid-0'}, ['NA1_fixture'], match, ['NA1_fixture']]
        result = collect_network(self.store, client, 'private-name', 'TAG', count=1, max_accounts=2)
        self.assertEqual(result['accounts_processed'], 2)
        self.assertEqual(result['inserted'], 1)
        self.assertEqual(result['duplicates'], 1)
        report = coverage(self.store)
        self.assertEqual(report['regions'][0]['seed_accounts'], 2)
        self.assertEqual(report['matches_without_provenance'], 0)
        self.assertNotIn('private-puuid', str(report))
        self.assertNotIn('private-name', str(report))
        self.assertEqual(len(report['roles']), 5)

    def test_auth_failure_is_recorded_without_provider_details(self):
        client = Mock(base_url='https://americas.api.riotgames.com')
        client.get.side_effect = [{'puuid': 'private-id'}, RiotAPIError('private-provider-body', status=403)]
        with self.assertRaises(RiotAPIError):
            run_etl(self.store, client, 'name', 'TAG')
        report = coverage(self.store)
        self.assertEqual(report['recent_runs'][0]['status'], 'failed')
        self.assertEqual(report['recent_runs'][0]['error_code'], 'riot-http-403')
        self.assertNotIn('private-provider-body', str(report))

    def test_coverage_api_has_no_identifiers(self):
        with TestClient(create_app(self.store)) as client:
            response = client.get('/api/coverage')
            self.assertEqual(response.status_code, 200)
            self.assertIn('unknown', response.json()['rank_coverage'])
            self.assertNotIn('source_hash', response.text)

    def test_tampered_backup_is_rejected_before_any_database_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backups').mkdir()
            archive = root / 'backups' / 'test.dump'
            archive.write_bytes(b'tampered archive')
            archive.with_suffix('.json').write_text(json.dumps({'sha256': 'invalid'}))
            with patch('backend.platform.maintenance.ROOT', root), patch('backend.platform.maintenance.docker_command') as docker:
                with self.assertRaises(ValueError):
                    verify_restore(self.store, archive)
                docker.assert_not_called()

    def test_restore_refuses_files_outside_project_backups(self):
        with patch('backend.platform.maintenance.docker_command') as docker:
            with self.assertRaises(ValueError):
                verify_restore(self.store, Path('outside.dump'))
            docker.assert_not_called()

    def test_completed_work_is_checkpointed_while_run_is_active(self):
        client = Mock(base_url='https://americas.api.riotgames.com')
        calls = iter([{'puuid': 'private-id'}, ['NA1_fixture', 'NA1_second'], full_fixture()])
        def get(*args, **kwargs):
            try:
                return next(calls)
            except StopIteration:
                run = coverage(self.store)['recent_runs'][0]
                self.assertEqual(run['status'], 'running')
                self.assertEqual(run['counts']['inserted'], 1)
                raise RiotAPIError('provider unavailable', status=503)
        client.get.side_effect = get
        result = run_etl(self.store, client, 'name', 'TAG')
        self.assertEqual(result['inserted'], 1)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(coverage(self.store)['recent_runs'][0]['status'], 'partial')

    @patch.dict(os.environ, {'OPENAI_API_KEY': 'test-placeholder'})
    def test_default_rag_context_excludes_old_champion_patch(self):
        for patch_version in ('16.19', '16.20'):
            self.store.upsert_document({'id': 'champion-test-' + patch_version, 'title': 'Champion mechanics',
                'body': 'Synthetic fixture', 'role': None, 'champion': 'LeeSin', 'patch': patch_version,
                'source_url': None, 'source_kind': 'test-only'})
        catalog = Mock(data={'version': '16.20.1'})
        catalog.abilities.return_value = None
        transport = Mock()
        transport.post.return_value = Mock(status_code=200, json=lambda: {'status': 'completed',
            'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'Synthetic fixture reply'}]}]})
        answer(self.store, catalog, {'role': 'JUNGLE', 'champion': 'LeeSin', 'opponent': '', 'patch': None}, 'Explain mechanics', transport=transport)
        context = json.loads(transport.post.call_args.kwargs['json']['input'])
        self.assertEqual([s['patch'] for s in context['retrieved_sources']], ['16.20'])


@unittest.skipUnless(os.getenv('TEST_DATABASE_URL'), 'Requires a dedicated PostgreSQL test database')
class PostgreSQLMigrationTests(unittest.TestCase):
    def test_upgrade_is_repeatable_and_constraints_are_validated(self):
        store = Store(os.environ['TEST_DATABASE_URL'])
        try:
            store.initialize()
            store.initialize()
            with store.engine.connect() as connection:
                self.assertEqual(list(connection.execute(text('SELECT version FROM lc_schema_migrations ORDER BY version')).scalars()), [1, 2, 3])
                constraints = connection.execute(text("SELECT convalidated FROM pg_constraint WHERE conname IN ('lc_player_role','lc_player_id','lc_player_champion','lc_player_stats') AND conrelid='lc_players'::regclass")).scalars().all()
                self.assertEqual(constraints, [True] * 4)
            with self.assertRaises(IntegrityError) as caught:
                with store.engine.begin() as connection:
                    connection.execute(matches.insert().values(match_id='constraint-rollback-test', patch='0.0', payload={}))
                    connection.execute(players.insert().values(match_id='constraint-rollback-test', participant_id=1,
                        role='INVALID', champion='Test', win=True, payload={}))
            self.assertEqual(caught.exception.orig.diag.constraint_name, 'lc_player_role')
        finally:
            store.engine.dispose()


if __name__ == '__main__':
    unittest.main()
