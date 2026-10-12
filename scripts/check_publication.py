"""Scan publishable files and Git history without printing credential values."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEY = re.compile(rb'(?:RGAPI-[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,})')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def main():
    problems = []
    files = git('ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0')
    for raw in files:
        if not raw:
            continue
        name = raw.decode('utf-8')
        path = ROOT / name
        if path.is_file() and KEY.search(path.read_bytes()):
            problems.append('working tree: ' + name)
        if path.name == '.env' or path.suffix in {'.db', '.sqlite', '.sqlite3'}:
            problems.append('private file eligible for publication: ' + name)
    for commit in git('rev-list', '--all').decode().splitlines():
        for raw in git('ls-tree', '-r', '--name-only', '-z', commit).split(b'\0'):
            if raw and KEY.search(git('show', commit + ':' + raw.decode('utf-8'))):
                problems.append('history: ' + commit[:12] + ' / ' + raw.decode('utf-8'))
    if problems:
        print('Potential credentials/private files detected; values suppressed:')
        print('\n'.join(problems))
        raise SystemExit(1)
    print('No recognizable Riot/OpenAI keys or private database/env files in publishable files; credential-pattern history scan passed.')
    print('This pattern scan does not prove that every possible secret is absent.')


if __name__ == '__main__':
    main()
