"""Validated ranked-match ETL with durable runs and bounded participant discovery."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy.exc import SQLAlchemyError
from backend.riot_api import RiotClient, RiotAPIError
from .knowledge import seed_knowledge
from .store import Store

ROLES = {'TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY'}


def extract_players(match):
    try:
        info, match_id = match['info'], match['metadata']['matchId']
        version = info.get('gameVersion')
        if info.get('queueId') != 420 or not isinstance(match_id, str) or not 1 <= len(match_id) <= 80 or not isinstance(version, str) or not re.match(r'^\d+\.\d+(?:\.|$)', version):
            return []
        if len('.'.join(version.split('.')[:2])) > 20:
            return []
        if info.get('gameDuration') is not None and (type(info['gameDuration']) is not int or not 0 <= info['gameDuration'] <= 2147483647):
            return []
        def number(value):
            return value if type(value) is int and 0 <= value <= 2147483647 else None
        result = []
        for p in info['participants']:
            role, pid = p.get('teamPosition'), p.get('participantId')
            if role not in ROLES or type(pid) is not int or not 1 <= pid <= 10 or not isinstance(p.get('championName'), str) or not 1 <= len(p['championName'].strip()) <= 80 or type(p.get('win')) is not bool or p.get('teamId') not in {100, 200}:
                continue
            opposing = [q for q in info['participants'] if isinstance(q, dict) and q.get('teamPosition') == role and q.get('teamId') in {100, 200} and q['teamId'] != p['teamId']]
            perks = p.get('perks')
            styles = perks.get('styles', []) if isinstance(perks, dict) else []
            styles = [s for s in styles if isinstance(s, dict)] if isinstance(styles, list) else []
            primary = next((s for s in styles if s.get('description') == 'primaryStyle'), styles[0] if styles else {})
            selections = primary.get('selections')
            keystone = number(selections[0].get('perk')) if isinstance(selections, list) and selections and isinstance(selections[0], dict) else None
            cs = [number(p.get('totalMinionsKilled')), number(p.get('neutralMinionsKilled'))]
            opponent = opposing[0].get('championName') if len(opposing) == 1 else None
            if not isinstance(opponent, str) or not 1 <= len(opponent.strip()) <= 80:
                opponent = None
            result.append({'match_id': match_id, 'participant_id': pid, 'role': role,
                'champion': p['championName'], 'opponent': opponent, 'win': p['win'], 'keystone': keystone,
                'kills': number(p.get('kills')), 'deaths': number(p.get('deaths')), 'assists': number(p.get('assists')),
                'cs': number(sum(cs)) if all(type(v) is int for v in cs) else None, 'gold': number(p.get('goldEarned')),
                'payload': {'runes': styles, 'items': [number(p.get(f'item{i}')) for i in range(7)], 'team_id': p['teamId']}})
        if len({p['participant_id'] for p in result}) != len(result) or len({(p['payload']['team_id'], p['role']) for p in result}) != len(result):
            return []
        outcomes = {team: {p['win'] for p in result if p['payload']['team_id'] == team} for team in (100, 200)}
        if any(len(v) > 1 for v in outcomes.values()) or (outcomes[100] and outcomes[100] == outcomes[200]):
            return []
        return result
    except (KeyError, TypeError, AttributeError):
        return []


def account_puuid(client, game_name, tag):
    account = client.get(f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag, safe='')}")
    if not isinstance(account, dict) or not isinstance(account.get('puuid'), str) or not account['puuid']:
        raise RiotAPIError('Account response missing PUUID')
    return account['puuid']


def run_etl(store, client, game_name, tag, count=100):
    return ingest_account(store, client, account_puuid(client, game_name, tag), count)


def ingest_account(store, client, puuid, count=100):
    if type(count) is not int or not 1 <= count <= 1000:
        raise ValueError('count must be 1–1000')
    region = client.base_url.split('//')[1].split('.')[0] if isinstance(getattr(client, 'base_url', None), str) else 'test'
    run_id = store.start_run(region, hashlib.sha256(puuid.encode()).hexdigest(), count)
    counts = {'inserted': 0, 'duplicates': 0, 'skipped': 0, 'failed': 0}
    try:
        _ingest(store, client, puuid, count, counts, run_id)
    except BaseException as error:
        code = f'riot-http-{error.status}' if isinstance(error, RiotAPIError) and error.status else ('interrupted' if isinstance(error, KeyboardInterrupt) else 'request-or-storage-error')
        store.finish_run(run_id, counts, 'failed', code)
        raise
    store.finish_run(run_id, counts, 'partial' if counts['failed'] or counts['skipped'] else 'completed')
    return counts


def _ingest(store, client, puuid, count, counts, run_id):
    for start in range(0, count, 100):
        size = min(100, count - start)
        ids = client.get(f"/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids", params={'queue': 420, 'type': 'ranked', 'start': start, 'count': size})
        if not isinstance(ids, list) or any(not isinstance(i, str) or not i or len(i) > 80 for i in ids):
            raise RiotAPIError('Invalid match history response')
        for match_id in ids:
            if store.contains(match_id):
                counts['duplicates'] += 1
                store.record_source(match_id, run_id)
                store.checkpoint_run(run_id, counts)
                continue
            try:
                match = client.get(f"/lol/match/v5/matches/{quote(match_id, safe='')}")
                extracted = extract_players(match)
                if not extracted or match['metadata']['matchId'] != match_id:
                    counts['skipped'] += 1
                    store.checkpoint_run(run_id, counts)
                    continue
                inserted = store.save_match(match, extracted)
                counts['inserted' if inserted else 'duplicates'] += 1
                store.record_source(match_id, run_id)
            except RiotAPIError as error:
                if error.status in {401, 403, 429}:
                    raise
                counts['failed'] += 1
            store.checkpoint_run(run_id, counts)
        if len(ids) < size:
            break


def collect_network(store, client, game_name, tag, count=20, max_accounts=1):
    if type(max_accounts) is not int or not 1 <= max_accounts <= 20:
        raise ValueError('max_accounts must be 1–20')
    queue, visited = [account_puuid(client, game_name, tag)], set()
    totals = {key: 0 for key in ('inserted', 'duplicates', 'skipped', 'failed')}
    region = client.base_url.split('//')[1].split('.')[0]
    while queue and len(visited) < max_accounts:
        puuid = queue.pop(0)
        if puuid in visited:
            continue
        visited.add(puuid)
        counts = ingest_account(store, client, puuid, count)
        for key in totals:
            totals[key] += counts[key]
        queue.extend(p for p in store.discover_accounts(region) if p not in visited and p not in queue)
    return {**totals, 'accounts_processed': len(visited)}


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-file', type=Path, required=True)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--interval', type=int, default=0)
    parser.add_argument('--max-accounts', type=int, default=1, help='Bounded participant discovery per seed, 1–20')
    args = parser.parse_args()
    if not 1 <= args.count <= 1000 or args.interval < 0 or not 1 <= args.max_accounts <= 20:
        parser.error('count must be 1–1000, max-accounts 1–20, and interval nonnegative')
    try:
        seeds = json.loads(args.seed_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        parser.error('Cannot read seed file; provide a valid local JSON list.')
    if not isinstance(seeds, list) or not seeds or any(not isinstance(seed, dict)
        or not isinstance(seed.get('game_name'), str) or not seed['game_name'].strip()
        or not isinstance(seed.get('tag'), str) or not seed['tag'].strip()
        or seed.get('region', 'americas') not in {'americas', 'europe', 'asia', 'sea'} for seed in seeds):
        parser.error('Seeds must contain nonempty game_name/tag and a supported region.')
    store = Store()
    store.initialize()
    seed_knowledge(store)
    clients = {}
    while True:
        for seed in seeds:
            region = seed.get('region', 'americas')
            if region not in clients:
                clients[region] = RiotClient(region)
            try:
                print(json.dumps(collect_network(store, clients[region], seed['game_name'], seed['tag'], args.count, args.max_accounts)), flush=True)
            except RiotAPIError as error:
                print(str(error), flush=True)
                if not args.interval:
                    raise SystemExit(1) from None
        if not args.interval:
            break
        time.sleep(args.interval)


if __name__ == '__main__':
    try:
        main()
    except SQLAlchemyError:
        raise SystemExit('Database operation failed. Check PostgreSQL and DATABASE_URL privately.') from None
    except RiotAPIError as error:
        raise SystemExit(str(error)) from None
    except KeyboardInterrupt:
        print('ETL stopped.')
