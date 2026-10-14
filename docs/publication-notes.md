# GitHub publication notes

This release is a locally verified, all-role League of Legends coaching portfolio project using React/Next.js, FastAPI, PostgreSQL, and OpenAI with retrieval-augmented generation.

## Verified

- All 42 backend tests passed, including native PostgreSQL integration, on Windows and in the Linux API container.
- TypeScript checks, Next.js production builds, Docker builds, and browser QA passed.
- A live Jungle guide and follow-up used retrieved references and persisted in PostgreSQL; the browser restored the conversation.
- One real ranked match produced ten player records across all five roles; a repeat import was correctly identified as a duplicate.

## Still to do

Railway deployment and public-demo isolation/usage controls are implemented and published; see [Railway preparation](railway-progress.md). Account connection and a verified cloud launch remain pending.

Local database improvements since the initial publication are tracked in [PostgreSQL data and operations](database-operations.md). They include migration history, validated player constraints, ingestion runs and discovery provenance, measured coverage, full champion-reference sync, and a verified local backup/restore workflow. See the dated validation notes for actual dataset counts; collector limits alone do not imply coverage.

See [October 14 database progress](database-progress.md) for the verified 97-match dataset, 173-champion reference corpus, tests, and remaining collection/operations work.

- **Strengthen the PostgreSQL dataset:** broaden match collection across seed accounts, regions, ranks, patches, and champions. The initial one-match dataset verifies ingestion but cannot support useful statistical conclusions. Rank-specific coverage must be measured rather than inferred from match outcomes.
- **Improve coaching knowledge:** expand curated, sourced, versioned strategy guidance beyond the initial authored role notes and champion references.
- **Add timeline evidence:** ingest and validate available position snapshots, gold/CS progression, item purchases, and objective events. Generated jungle-routing suggestions are not measured movement paths.
- **Database operations:** configure automatic backup scheduling, retention, encryption, off-device storage, and production monitoring. Local migrations, coverage reporting, and backup/restore verification are implemented; those do not constitute managed production disaster recovery.
- **Public hosting:** deploy a live demo only after adding authentication, usage limits, and protection against paid-API abuse. The current stack is intended for local use.
- **GitHub verification:** the repository is public, and the database/deployment improvements have been pushed. Check the latest GitHub Actions results before deploying; successful CI is separate from a verified Railway launch.
- **Analytics validity:** show sample sizes and collection limitations. Rune associations do not establish optimal choices, and opponent outcomes do not establish universal counters.

These are planned improvements, not completed features. Credentials, local databases, and private seed files are excluded from the repository. See [validation status](validation-status.md) and [accurate résumé wording](resume.md).
