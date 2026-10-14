"""Local Compose backup and isolated restore verification; never overwrites a database."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from .store import Store, metadata
from .coverage import coverage

ROOT = Path(__file__).resolve().parents[2]


def archive_digest(path):
    digest = hashlib.sha256()
    with path.open('rb') as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def docker_command(*args, **kwargs):
    docker = shutil.which('docker') or str(Path(os.getenv('LOCALAPPDATA', '')) / 'Programs/DockerDesktop/resources/bin/docker.exe')
    result = subprocess.run([docker, 'compose', 'exec', '-T', 'db', *args], cwd=ROOT,
                            stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        raise RuntimeError(f'Docker database command failed (exit {result.returncode}); check the running Compose database.')
    return result


def fingerprint(connection):
    # Static table names from metadata, no request-supplied SQL identifiers.
    names = sorted([*metadata.tables, 'lc_schema_migrations'])
    result = {}
    for name in names:
        row = connection.execute(text(f"SELECT COUNT(*) AS rows, md5(COALESCE(string_agg(md5(t::text), '' ORDER BY t::text), '')) AS digest FROM {name} t")).mappings().one()
        result[name] = dict(row)
    return result


def backup(store):
    if store.engine.dialect.name != 'postgresql':
        raise ValueError('Backups require PostgreSQL')
    directory = ROOT / 'backups'
    directory.mkdir(exist_ok=True)
    path = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid4().hex[:8] + '.dump')
    with store.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.execute(text('SET TRANSACTION READ ONLY'))
            snapshot = connection.execute(text('SELECT pg_export_snapshot()')).scalar_one()
            tables = fingerprint(connection)
            with path.open('wb') as output:
                docker_command('pg_dump', '-U', store.engine.url.username, '-d', store.engine.url.database,
                    '--format=custom', '--no-owner', '--no-acl', '--snapshot=' + snapshot, stdout=output)
    digest = archive_digest(path)
    manifest = {'created': datetime.now(timezone.utc).isoformat(), 'sha256': digest, 'tables': tables,
                'scope': 'Single local Compose database; cluster roles and public champion file cache excluded.'}
    path.with_suffix('.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Private backup written:', path.name)
    return path


def verify_restore(store, path):
    path = path.resolve()
    if not path.is_relative_to((ROOT / 'backups').resolve()):
        raise ValueError('Only this project\'s local backups can be verified')
    manifest = json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))
    if archive_digest(path) != manifest['sha256']:
        raise ValueError('Backup checksum mismatch')
    target = 'lanecoach_restore_' + uuid4().hex[:12]
    user = store.engine.url.username
    docker_command('createdb', '-U', user, target, stdout=subprocess.PIPE)
    restored = Store(store.engine.url.set(database=target).render_as_string(hide_password=False))
    try:
        with path.open('rb') as archive:
            docker_command('pg_restore', '-U', user, '-d', target, '--exit-on-error', '--single-transaction',
                '--no-owner', '--no-acl', stdin=archive, stdout=subprocess.PIPE)
        with restored.engine.connect() as connection:
            actual = fingerprint(connection)
        if actual != manifest['tables']:
            raise ValueError('Restored table fingerprints do not match backup snapshot')
        print('Restore verification passed: all table row counts and content fingerprints match.')
    finally:
        restored.engine.dispose()
        # Only remove the fresh disposable database created above, never caller-named targets.
        docker_command('dropdb', '-U', user, target, stdout=subprocess.PIPE)


def main():
    load_dotenv(ROOT / 'backend/.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['coverage', 'backup', 'verify-restore'])
    parser.add_argument('--file', type=Path)
    args = parser.parse_args()
    store = Store()
    store.initialize()
    try:
        if args.action == 'coverage':
            print(json.dumps(coverage(store), indent=2, default=str))
        elif args.action == 'backup':
            backup(store)
        else:
            if not args.file:
                parser.error('--file is required for verify-restore')
            verify_restore(store, args.file)
    finally:
        store.engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except (SQLAlchemyError, RuntimeError, ValueError, OSError):
        raise SystemExit('Database maintenance failed. Check Docker, database configuration and backup integrity privately.') from None
