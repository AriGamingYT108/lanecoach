# Railway preparation — October 14, 2026

Implemented locally:

- Separate Railway deployment configs for API and web, runtime ports, private networking, and database-aware API readiness.
- Runtime Next.js API proxy: private host and proxy secret are read at runtime, not embedded in the client bundle.
- Production mode fails closed on Railway without required secrets and the HTTPS frontend origin.
- Signed, Secure, HttpOnly anonymous visitor cookies; visitor-bound CSRF tokens; owner checks on conversation reads and follow-ups. Existing unowned local conversations are inaccessible in public mode.
- Shared PostgreSQL request caps: 100 AI attempts per UTC day globally, 10 per visitor per day, 3 per visitor per minute by default. Failed/uncertain provider attempts count conservatively. These are request limits, not an exact dollar cap.
- Public champion-name bootstrap snapshot for fresh deployments; detailed champion references can be refreshed through the documented sync command.
- PostgreSQL URL normalization for Railway and schema migration 3 for conversation ownership.
- CI production-proxy acceptance using synthetic answers and no paid requests.
- Evidence-only cloud migration, excluding conversations, visitor ownership, API keys, and AI quota state; preserving match deduplication and discovery provenance.

All 64 local backend tests pass, including native PostgreSQL checks, in Windows and the Linux API container. TypeScript, production builds, browser QA, and production-mode proxy acceptance pass. Production-mode tests cover two-visitor isolation, forged cookies/CSRF, direct API access rejection, shared quota rollback, concurrent PostgreSQL quota enforcement, and Railway readiness. The previous private backup remains restorable after the schema upgrade.

Still pending:

- Connect Railway and provision Postgres/API/web in the user's account, configure private runtime secrets and hosting spending controls, and verify an actual HTTPS deployment.
- Configure Railway's GitHub integration against the published `main` branch and verify the service root/config paths. The deployment source is now published; Railway provisioning and cloud verification are still pending.
- Populate the cloud database: the local 97-match evidence and private conversations are not automatically copied. A fresh deployment can coach without match statistics; cloud collection or a deliberate match/reference-only migration is separate.
- Perform live cloud coaching and isolated-browser acceptance after deployment. Local tests do not verify Railway itself.

Deployment instructions and limits: [Railway setup](railway.md). Anonymous cookies are not verified-human authentication; global limits bound paid attempts even when visitor cookies are reset. A public demo still needs monitoring and may later need stronger bot protection.
