# GitHub publication notes

This release is a locally verified, all-role League of Legends coaching portfolio project using React/Next.js, FastAPI, PostgreSQL, and OpenAI with retrieval-augmented generation.

## Verified

- All 42 backend tests passed, including native PostgreSQL integration, on Windows and in the Linux API container.
- TypeScript checks, Next.js production builds, Docker builds, and browser QA passed.
- A live Jungle guide and follow-up used retrieved references and persisted in PostgreSQL; the browser restored the conversation.
- One real ranked match produced ten player records across all five roles; a repeat import was correctly identified as a duplicate.

## Still to do

- **Strengthen the PostgreSQL dataset:** broaden match collection across seed accounts, regions, ranks, patches, and champions. The initial one-match dataset verifies ingestion but cannot support useful statistical conclusions. Rank-specific coverage must be measured rather than inferred from match outcomes.
- **Improve coaching knowledge:** expand curated, sourced, versioned strategy guidance beyond the initial authored role notes and champion references.
- **Add timeline evidence:** ingest and validate available position snapshots, gold/CS progression, item purchases, and objective events. Generated jungle-routing suggestions are not measured movement paths.
- **Database operations:** add versioned schema migrations, stronger quality/coverage monitoring, and automated backups with restore verification.
- **Public hosting:** deploy a live demo only after adding authentication, usage limits, and protection against paid-API abuse. The current stack is intended for local use.
- **GitHub verification:** confirm the published Actions checks pass and that repository visibility permits recruiter access.
- **Analytics validity:** show sample sizes and collection limitations. Rune associations do not establish optimal choices, and opponent outcomes do not establish universal counters.

These are planned improvements, not completed features. Credentials, local databases, and private seed files are excluded from the repository. See [validation status](validation-status.md) and [accurate résumé wording](resume.md).
