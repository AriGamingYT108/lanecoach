# PostgreSQL progress — October 14, 2026

## Implemented and checked locally

- Forward-only migration history, transaction advisory locking, player constraints, and query indexes.
- Validated match extraction, unknown optional statistics stored as NULL, and protection against fabricated normalized records.
- Durable ingestion runs with checkpointed counts, sanitized failures, and match-discovery provenance.
- Bounded participant-account discovery and a privacy-preserving coverage API/CLI.
- Public reference sync for all 173 champions in the current catalog, plus six explicitly authored practice documents.
- Current-patch champion retrieval by default; explicit historical-patch requests remain supported.
- Snapshot-consistent private backups and verified restoration into disposable databases, with archive checksum checks.

## Measured dataset

| Measure | Count |
| --- | ---: |
| Stored ranked matches | 97 |
| Player appearances | 970 |
| Match patches | 16 |
| Distinct champions in match evidence | 165 |
| Discovery accounts | 5 |
| Routing regions | 1 (`americas`) |
| Missing CS, gold, or keystone values | 0 |
| Matches without discovery provenance | 0 |
| Public champion references | 173 |
| Authored practice documents | 6 |

There are 194 appearances for each role. Role-specific champion breadth: Top 59, Jungle 57, Mid 62, Bot 42, Support 40. The bounded run inserted 96 additional matches and encountered four duplicates; repeating the original account's twenty-match import inserted zero and encountered twenty duplicates.

These are selected accounts connected through matches, not a random sample. Many games are historical; sixteen patches does not mean strong coverage of each patch. Historical rank is unknown. No reliability, optimal-rune, causal-counter, or measured-jungle-path claim follows from these counts.

## Verification

- All 54 backend tests passed on Windows with native PostgreSQL integration and inside the Linux API container.
- Clean-database installation was verified against a fresh disposable PostgreSQL database.
- Docker API build and startup passed. Browser QA and the real coverage endpoint passed; the endpoint exposes no player IDs or source hashes.
- A backup of the completed dataset restored with matching row counts and content fingerprints for every tracked table. The temporary restore database was removed; the app database was preserved.
- No paid OpenAI requests were needed for this database follow-up. Existing OpenAI configuration was retained.

## Still needed

- Broader, deliberately sampled match collection, especially current-patch coverage and additional routing regions; actual rank data needs a separate validated collection design.
- Curated, sourced coaching strategy material beyond champion descriptions and general authored principles.
- Timeline evidence ingestion and validation; current routing advice remains generated, not reconstructed telemetry.
- Automatic backup scheduling, retention, encryption, off-device storage, production monitoring, and large-dataset migration/backup planning.
- Authentication and paid-API abuse controls before public hosting.
- Approval for the next GitHub push, followed by remote CI verification. The earlier public release does not yet contain these local improvements.

Usage and limitations: [database operations](database-operations.md). Private match data and backup files are ignored and are not part of the source publication.
