# Local validation status

The subsequent October 14 PostgreSQL improvements and dataset measurements are documented in [database progress](database-progress.md). The results below describe the initial October 12 release.

Checked on October 12, 2026:

- Python suite: all 42 passed on Windows and inside the Linux API container, including native PostgreSQL analytics and full-text retrieval against a separate test database.
- Next.js production build and TypeScript checking: passed.
- Browser QA: all five roles, guide requests, follow-ups, saved-session restoration, retrieved sources, provider errors, navigation, and mobile overflow passed using synthetic intercepted responses.
- Git publication pattern scan: no recognizable Riot/OpenAI credentials found in publishable files or current Git history. This is a pattern check, not proof of absence of every possible secret.
- Docker Desktop: API and web images built; PostgreSQL 17, FastAPI, and Next.js started successfully through Compose.
- Live OpenAI acceptance: a Jungle guide and contextual follow-up each used three retrieved references. Four conversation messages persisted in PostgreSQL and were restored by the real browser after reload. Two paid API requests were made for this check.
- Live Riot ETL: one ranked match inserted, ten player appearances across all five roles; repeated import returned one duplicate and zero new inserts. This is a functional check, not a statistically useful dataset.
- Source and remaining-work notes have been published to the public GitHub repository on `main` and `feature/match-collector`. GitHub Actions results are available on the repository's [Actions page](https://github.com/AriGamingYT108/lanecoach/actions); local validation does not imply those remote checks passed.

The app has been verified locally; public hosting and GitHub publication are separate steps. Generated jungle advice is not measured path telemetry and observed rune outcomes do not establish optimality.
