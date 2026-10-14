"""Measured data coverage and ingestion health without player identifiers."""
import json
from sqlalchemy import text


def coverage(store):
    def query(connection, sql):
        return [dict(row) for row in connection.execute(text(sql)).mappings()]
    with store.engine.connect() as connection:
        patches = query(connection, 'SELECT patch, COUNT(*) AS matches FROM lc_matches GROUP BY patch ORDER BY patch')
        roles = query(connection, 'SELECT role, COUNT(*) AS appearances, COUNT(DISTINCT champion) AS champions, SUM(CASE WHEN opponent IS NULL THEN 1 ELSE 0 END) AS missing_opponents FROM lc_players GROUP BY role ORDER BY role')
        sources = query(connection, 'SELECT region, COUNT(DISTINCT source_hash) AS seed_accounts, COUNT(*) AS runs FROM lc_ingestion_runs GROUP BY region ORDER BY region')
        documents = query(connection, 'SELECT source_kind, COUNT(*) AS documents FROM lc_documents GROUP BY source_kind ORDER BY source_kind')
        quality = query(connection, 'SELECT SUM(CASE WHEN cs IS NULL THEN 1 ELSE 0 END) AS missing_cs, SUM(CASE WHEN gold IS NULL THEN 1 ELSE 0 END) AS missing_gold, SUM(CASE WHEN keystone IS NULL THEN 1 ELSE 0 END) AS missing_keystones FROM lc_players')[0]
        runs = query(connection, 'SELECT region, started, finished, status, requested, counts, error_code FROM lc_ingestion_runs ORDER BY started DESC LIMIT 20')
        untracked = connection.execute(text('SELECT COUNT(*) FROM lc_matches m WHERE NOT EXISTS (SELECT 1 FROM lc_match_sources s WHERE s.match_id=m.match_id)')).scalar_one()
    def patch_key(row):
        parts = row['patch'].split('.')
        return tuple(map(int, parts)) if all(part.isdigit() for part in parts) else (-1,)
    patches.sort(key=patch_key)
    for run in runs:
        if isinstance(run['counts'], str):
            # SQLite's raw SQL JSON comes back as text in isolated unit tests.
            run['counts'] = json.loads(run['counts'])
    return {'patches': patches, 'roles': roles, 'regions': sources, 'documents': documents,
            'missing_fields': {key: int(value or 0) for key, value in quality.items()},
            'matches_without_provenance': untracked, 'recent_runs': runs,
            'rank_coverage': 'unknown: ranks are not collected',
            'note': 'Coverage is not representativeness or statistical reliability. Seed accounts are discovery sources; region is the API routing region.'}
