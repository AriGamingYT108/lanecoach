# Verification

Run the offline suite and frontend checks in the README. To verify native PostgreSQL SQL/JSONB and full-text retrieval, use a separate database:

```powershell
docker compose up -d db
docker compose exec db createdb -U lanecoach lanecoach_test
$env:TEST_DATABASE_URL = 'postgresql+psycopg://lanecoach:local-development-only@127.0.0.1:5432/lanecoach_test'
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
Remove-Item Env:TEST_DATABASE_URL
```

Never use a personal or production database for integration fixtures. The stable fixture identifier permits repeated runs. CI provisions a disposable PostgreSQL service.

With Next.js running, browser QA uses intercepted synthetic API responses:

```powershell
.\backend\venv\Scripts\python.exe scripts/browser_coach.py
```

These responses stay in browser interception and never enter the real database. QA checks role selection, conversation restoration, sources, navigation, error presentation, and desktop/mobile overflow. Screenshots go to ignored `artifacts/`.

Live acceptance: choose Jungle or Support, request a game plan, ask a follow-up, reload, and verify sources and persistence. This needs PostgreSQL and funded OpenAI API access and incurs charges. ETL acceptance: ingest one ranked match twice and verify duplicate prevention and all available roles. Never treat synthetic test replies or statistics as live results.

An opt-in live check makes two paid OpenAI requests through the running app:

```powershell
.\backend\venv\Scripts\python.exe scripts/verify_coach_live.py
```

Before publication, run `python scripts/check_publication.py` for a credential-pattern scan of publishable source and Git history. It suppresses credential values and does not replace reviewing files yourself. Current measured results are recorded in [validation status](validation-status.md).
