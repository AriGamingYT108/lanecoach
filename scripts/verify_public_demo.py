"""Production-mode proxy acceptance with isolated synthetic coaching; no paid calls."""
import os
import subprocess
import threading
import time
from pathlib import Path

import requests
import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def main():
    # A new Python process and disposable in-memory store keep this test out of
    # the real app/database. Published test secrets are never production values.
    os.environ.update(APP_ENV='production', APP_SECRET='public-demo-test-secret-0123456789',
        INTERNAL_PROXY_TOKEN='public-demo-proxy-test-0123456789', FRONTEND_ORIGIN='https://demo.example',
        AI_DAILY_REQUEST_LIMIT='2', AI_VISITOR_DAILY_LIMIT='2', AI_VISITOR_MINUTE_LIMIT='2')
    import sys
    sys.path.insert(0, str(ROOT))
    from backend.platform.api import create_app
    from backend.platform.store import Store
    calls = []
    def coach(*args):
        calls.append(True)
        return {'text': 'Synthetic proxy test reply; not live advice.', 'sources': [], 'model': 'test', 'analytics': None}
    app = create_app(Store('sqlite://'), coach_fn=coach)
    api = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8101, log_level='error'))
    thread = threading.Thread(target=api.run, daemon=True)
    thread.start()
    web = None
    try:
        for _ in range(100):
            if api.started:
                break
            if not thread.is_alive():
                raise RuntimeError('Test API could not start; port 8101 may be occupied')
            time.sleep(0.1)
        if not api.started:
            raise RuntimeError('Test API startup timed out')
        environment = {**os.environ, 'API_ORIGIN': 'http://127.0.0.1:8101', 'PORT': '3101'}
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        web = subprocess.Popen(['node', 'node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1'],
            cwd=ROOT / 'web', env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        base = 'http://127.0.0.1:3101'
        for _ in range(100):
            if web.poll() is not None:
                raise RuntimeError('Test web server could not start; build Next.js and check port 3101')
            try:
                if requests.get(base, timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.1)
        def visitor():
            response = requests.get(base + '/api/visitor', timeout=10)
            assert response.status_code == 200
            assert 'Secure' in response.headers['Set-Cookie'] and 'HttpOnly' in response.headers['Set-Cookie']
            # HTTP is only the local test transport; manually forward the secure
            # cookie as a real HTTPS browser would on Railway.
            return {'Cookie': 'lanecoach_visitor=' + response.cookies['lanecoach_visitor'],
                    'Origin': 'https://demo.example', 'X-LaneCoach-Client': 'browser',
                    'X-LaneCoach-CSRF': response.json()['csrf_token']}
        first, second = visitor(), visitor()
        body = {'profile': {'role': 'UTILITY'}, 'question': 'Synthetic proxy acceptance'}
        response = requests.post(base + '/api/coach', headers=first, json=body, timeout=10)
        assert response.status_code == 200, response.status_code
        session = response.json()['session_id']
        assert requests.get(base + '/api/sessions/' + session, headers=first, timeout=10).status_code == 200
        assert requests.get(base + '/api/sessions/' + session, headers=second, timeout=10).status_code == 404
        assert requests.post(base + '/api/coach', headers=first, json={**body, 'session_id': session}, timeout=10).status_code == 200
        assert requests.post(base + '/api/coach', headers=second, json=body, timeout=10).status_code == 429
        assert requests.post(base + '/api/coach', headers=second, data='x' * 20001, timeout=10).status_code == 413
        assert requests.get('http://127.0.0.1:8101/api/health', timeout=10).status_code == 403
        assert len(calls) == 2
        print('Public-mode runtime proxy, PORT, secure-cookie forwarding, CSRF, visitor isolation, body limits and global AI cap passed with synthetic replies; zero paid requests.')
    finally:
        if web:
            web.terminate()
            try:
                web.wait(timeout=10)
            except subprocess.TimeoutExpired:
                web.kill()
                web.wait(timeout=5)
        api.should_exit = True
        thread.join(timeout=10)


if __name__ == '__main__':
    main()
