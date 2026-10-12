"""Opt-in paid acceptance check against the real local FastAPI/PostgreSQL stack."""
import argparse
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:3000')
    args = parser.parse_args()
    health = requests.get(args.url + '/api/health', timeout=15)
    health.raise_for_status()
    assert health.json()['database_ready'], 'PostgreSQL is unavailable'
    assert health.json()['engine'] == 'postgresql'
    assert health.json()['ai_configured'], 'OpenAI is not configured'
    profile = {'role': 'JUNGLE', 'champion': 'LeeSin', 'opponent': '',
               'rank': 'Learning', 'goal': 'Jungle routing', 'patch': None}
    session_id = None
    for question in ['Build a short pre-game jungle plan with three practice goals. Give conditional routing priorities rather than exact times.',
                     'What should I do if the first gank fails? Give a short follow-up using our plan.']:
        response = requests.post(args.url + '/api/coach',
            headers={'X-LaneCoach-Client': 'browser'},
            json={'profile': profile, 'question': question, 'session_id': session_id}, timeout=120)
        if response.status_code != 200:
            # Only our API's sanitized detail is returned, never provider bodies or keys.
            raise SystemExit(f"Coaching HTTP {response.status_code}: {response.json().get('detail', 'Request failed')}")
        reply = response.json()
        assert reply['text'].strip()
        assert reply['sources'], 'No retrieved sources'
        assert any(s['source_kind'] == 'riot-data-dragon' for s in reply['sources'])
        if session_id:
            assert session_id == reply['session_id']
        session_id = reply['session_id']
        print(f"Live coaching passed: {len(reply['text'])} characters, {len(reply['sources'])} retrieved references.")
    saved = requests.get(args.url + '/api/sessions/' + session_id, timeout=15)
    saved.raise_for_status()
    assert len(saved.json()['messages']) == 4
    assert saved.json()['profile']['role'] == 'JUNGLE'
    print('PostgreSQL saved the game plan and follow-up as four conversation messages.')


if __name__ == '__main__':
    main()
