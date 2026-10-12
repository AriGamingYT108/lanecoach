# Résumé implementation audit

The original app used Flask, static JavaScript, and SQLite. The current v2 source implements React/Next.js, FastAPI, PostgreSQL, all-role conversations, optional ETL, SQL analytics, and RAG. Source implementation, runtime verification, and public deployment are separate milestones.

| Claim | Implementation | Qualification |
| --- | --- | --- |
| React, Next.js, FastAPI, PostgreSQL | `web/`, `api.py`, `store.py`, Compose | PostgreSQL runtime must be verified. Local execution is not public hosting. |
| Automated Python/Riot ETL | `etl.py`, `riot_api.py` | One-shot or interval scheduler, queue 420, all roles, idempotent writes. |
| SQL matchup win rates | `store.py` | Observed game wins and sample sizes, with role/opponent/patch filters. |
| Optimal rune choice | Keystone aggregates | Not established: associations do not prove optimality. |
| Champion counters | Opponent aggregates | Observed performance, not universal counters. |
| OpenAI and RAG | `coach.py`, `retrieval.py` | PostgreSQL lexical retrieval of authored guidance and champion references. |
| Strategies and path data | Practice plans and conditional routing | No measured path data in v2. Generated suggestions are not telemetry. |

Suggested wording (PostgreSQL and live coaching have now been verified locally; see `validation-status.md`):

**LaneCoach — AI-Powered League of Legends Coach · Aug. 2026 – Oct. 2026**

- Built an all-role coaching application with React, Next.js, FastAPI, and PostgreSQL, including saved conversations and pre-game guides.
- Implemented an idempotent Python ETL pipeline using Riot Account-V1 and Match-V5, with rate-limit handling and normalized ranked-match data.
- Developed SQL analytics for matchup win rates, sample sizes, rune associations, and opponent performance with role and patch filters.
- Integrated OpenAI Responses with PostgreSQL full-text retrieval to generate contextual practice plans and conditional jungle-routing advice.

Use dates reflecting your actual work. Do not claim benchmarks, reliability, scale, production deployment, or usage without evidence. GitHub can show source, setup, architecture, tests, and limitations once publication is approved.
