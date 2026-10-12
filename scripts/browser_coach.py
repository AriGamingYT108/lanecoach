"""Browser-only synthetic API interception; never writes to the real database."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:3000')
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / 'artifacts'
    output.mkdir(exist_ok=True)
    errors, messages = [], []
    session = {'id': 'browser-test', 'profile': {}, 'messages': messages}
    source = {'id': 'test-only', 'title': 'Synthetic QA reference', 'patch': None,
              'source_kind': 'test-only', 'source_url': None}

    def intercept(route):
        path = route.request.url.split('/api/', 1)[1]
        if path == 'health':
            data = {'database_ready': True, 'ai_configured': True, 'riot_configured': False,
                    'catalog_version': 'test-only', 'matches': 0, 'participants': 0,
                    'documents': 1, 'engine': 'test-only'}
        elif path == 'champions':
            data = {'champions': [{'id': 'LeeSin', 'name': 'Lee Sin', 'title': 'Test fixture'}]}
        elif path == 'coach':
            body = route.request.post_data_json
            if body['question'] == 'test failure':
                route.fulfill(status=502, json={'detail': 'Synthetic provider failure'})
                return
            session['profile'] = body['profile']
            messages.extend([{'role': 'user', 'content': body['question']},
                             {'role': 'assistant', 'content': 'Synthetic QA reply. **Not live coaching.**', 'sources': [source]}])
            data = {'session_id': session['id'], 'text': messages[-1]['content'],
                    'sources': [source], 'analytics': None}
        elif path.startswith('sessions/'):
            data = session
        elif path.startswith('analytics'):
            data = {'overall': {'sample_size': 0, 'wins': 0, 'win_rate': None},
                    'runes': [], 'opponents': [], 'note': 'Synthetic QA: zero samples.'}
        else:
            route.fulfill(status=404, json={'detail': 'Unknown test endpoint'})
            return
        route.fulfill(status=200, content_type='application/json', body=json.dumps(data))

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.route('**/api/**', intercept)
        page.goto(args.url, wait_until='networkidle')
        for role in ['Top', 'Jungle', 'Mid', 'Bot', 'Support']:
            button = page.locator('.role-picker button').filter(has_text=role)
            button.click()
            expect(button).to_have_attribute('aria-pressed', 'true')
        page.locator('.role-picker button').filter(has_text='Jungle').click()
        page.get_by_label('Your champion', exact=True).fill('Lee Sin')
        page.screenshot(path=str(output / 'coach-desktop.png'), full_page=True)
        page.get_by_role('button', name='Build my game plan').click()
        expect(page.locator('.message.assistant')).to_have_count(1)
        page.get_by_label('Ask your coach').fill('What if my first gank fails?')
        page.get_by_role('button', name='Send coaching question').click()
        expect(page.locator('.message.assistant')).to_have_count(2)
        page.reload(wait_until='networkidle')
        expect(page.locator('.message.assistant')).to_have_count(2)
        page.locator('.sources').first.locator('summary').click()
        expect(page.get_by_text('Synthetic QA reference').first).to_be_visible()
        page.get_by_label('Ask your coach').fill('test failure')
        page.get_by_role('button', name='Send coaching question').click()
        expect(page.locator('.alert[role="alert"]')).to_contain_text('Synthetic provider failure')
        expect(page.locator('.message.assistant')).to_have_count(2)
        page.get_by_role('button', name='Supporting evidence').click()
        expect(page.get_by_text('The evidence behind the plan.')).to_be_visible()
        page.set_viewport_size({'width': 390, 'height': 844})
        page.get_by_role('button', name='Your coach').click()
        page.screenshot(path=str(output / 'coach-mobile.png'), full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile overflow'
        page.get_by_role('button', name='How it works').click()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'About overflow'
        assert not errors, errors
        browser.close()
    print('All-role selection, conversation, restoration, sources, errors, navigation and responsive layout passed (synthetic browser responses).')


if __name__ == '__main__':
    main()
