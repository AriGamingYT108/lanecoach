# Railway recruiter demo

Deployment files are prepared for three Railway services in the same project/environment: **Postgres**, **api**, and **web**. Railway account access and billing are required; local verification is not a completed cloud deployment.

## Services

| Service | Source root | Config file | Public domain |
| --- | --- | --- | --- |
| Postgres | Railway PostgreSQL template | Railway-managed | Keep private |
| api | Repository root `/` | `/backend/railway.json` | None required |
| web | `/web` | `/web/railway.json` | Generate Railway HTTPS domain |

Railway does not launch this repository's Compose stack automatically. Add two services from the same GitHub repository and set their root/config paths as above. The API Dockerfile needs the repository root because it copies `backend/` and the legacy `frontend/` directory. Web uses its own Dockerfile inside `/web`.

The API honors Railway's runtime `PORT`, listens on IPv6 when Railway is detected, and uses `/api/ready` for database-aware readiness. Web honors `PORT` and forwards requests to the private API at runtime, so the private hostname is not required during the build. See Railway's [monorepo](https://docs.railway.com/deployments/monorepo), [healthcheck](https://docs.railway.com/deployments/healthchecks), and [private-network](https://docs.railway.com/networking/private-networking) documentation.

## Variables — enter privately, never in GitHub

API service:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (adjust service name to match yours) |
| `APP_SECRET` | Random secret of at least 32 characters |
| `INTERNAL_PROXY_TOKEN` | A second random secret of at least 32 characters |
| `FRONTEND_ORIGIN` | Exact public web origin, e.g. `https://your-web-domain.up.railway.app`, no trailing slash |
| `OPENAI_API_KEY` | Your existing key, entered privately |
| `OPENAI_MODEL` | `gpt-4.1-mini` |
| `PORT` | `8000` (keeps the private proxy target predictable) |
| `AI_DAILY_REQUEST_LIMIT` | `100` |
| `AI_VISITOR_DAILY_LIMIT` | `10` |
| `AI_VISITOR_MINUTE_LIMIT` | `3` |

Web service:

| Variable | Value |
| --- | --- |
| `API_ORIGIN` | `http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` |
| `INTERNAL_PROXY_TOKEN` | `${{api.INTERNAL_PROXY_TOKEN}}` |

Never use a `NEXT_PUBLIC_` prefix for credentials. OpenAI and Riot keys belong only on the API/collection service; web only needs the private proxy token. Railway PostgreSQL URL formats are normalized to the installed psycopg driver by the backend. Keep the database and API on private networking; only web needs a public domain.

Generate the web domain before starting the production API, so `FRONTEND_ORIGIN` can be set. The app detects Railway and fails closed without required production secrets. Anonymous visitors do not need an account: a signed, HttpOnly, Secure cookie isolates their conversations, and POST requests require a visitor-bound CSRF token. These are anonymous browser identities, not verified human accounts. Clearing cookies loses access to that visitor's saved conversations; pre-existing unowned local conversations are not exposed in production.

## AI request limits

Limits are reserved transactionally in PostgreSQL before each coaching attempt, and work across API workers/restarts. Defaults are 100 attempts per UTC day globally, 10 per visitor per UTC day, and 3 per visitor per UTC minute. Set the global limit to `0` to disable new coaching requests. Read-only evidence and stored answers remain available.

These are **request caps, not a dollar budget**. Actual charges depend on model/input/output sizes. Uncertain provider failures still count because a failed HTTP exchange may already have incurred processing. Anonymous visitor limits can be bypassed by clearing cookies, but the shared global cap remains enforced. Monitor abuse and costs; add stronger identity or bot protection if needed. Configure Railway's own spending controls separately for hosting costs.

## Initial knowledge and match data

A tracked public champion-name snapshot lets a new deployment populate the chooser without copying private cache files. Six authored role-practice documents are seeded in PostgreSQL automatically. Use a one-off command in the API environment to refresh and index all public champion ability references:

```text
python -m backend.platform.sync --all-champions
```

Coaching lazily loads selected champion references as well. The file cache can be regenerated; attach a Railway volume at `/app/backend/.cache` if persistent caching is desired.

**The local 97 matches are not automatically present in Railway.** A fresh cloud database starts without match evidence. Collect there using a private seed file and a privately configured Riot key, or explicitly migrate the match/reference tables. Do not publish backup files or upload local conversations just to populate the demo. The coach works with zero matches and displays absent analytics honestly.

An evidence-only migration is implemented as `python -m backend.platform.promote`. Set `TARGET_DATABASE_URL` privately to the intended Railway database connection and optionally `SOURCE_DATABASE_URL` for a source other than the local `DATABASE_URL`. Do not paste connection strings into chat or shell history. The migration copies validated matches, normalized players, reference documents, and ingestion provenance; it excludes conversations, visitor ownership, AI quotas, and API keys. Rerunning deduplicates matches and does not delete existing target data. Run it only after the destination has been provisioned and verified.

## Release checks

Local checks (no paid requests):

```powershell
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
cd web
npm run typecheck
npm run build
cd ..
.\backend\venv\Scripts\python.exe scripts/verify_public_demo.py
```

The production-mode smoke test runs temporary services on ports 3101 and 8101, uses synthetic replies and an isolated test store, and stops both services afterward. GitHub Actions runs it after the frontend build. It verifies the runtime proxy, cookies, CSRF, owner checks, oversized-body rejection, and global request cap.

- API readiness returns 200 through Railway's healthcheck hostname.
- Public web page, champion chooser, and evidence view work.
- Test an AI guide, follow-up, reload, and a second isolated browser; the second browser cannot retrieve the first visitor's conversation.
- Verify quota rejection with low temporary limits and restore intended limits afterward.
- Confirm no API keys appear in client bundles, logs, screenshots, or GitHub.
- Record the actual public URL and deployed commit; add the live-demo link to README only after deployment succeeds.

Railway billing/account connection and GitHub publication still require user action when no connected credentials are available. Do not claim this project is hosted based solely on local builds.
