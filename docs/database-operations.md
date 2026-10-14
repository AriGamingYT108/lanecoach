# PostgreSQL data and operations

The main database holds match evidence, retrieved coaching documents, conversations, ingestion runs, and match-discovery provenance. Local SQLite is only a compatibility tool and an isolated unit-test backend.

## Migrations and validation

`Store.initialize()` acquires a PostgreSQL transaction advisory lock, creates missing tables, and applies forward-only migrations recorded in `lc_schema_migrations`. Repeated initialization does not repeat applied migrations. PostgreSQL validates existing player rows before marking the new constraints complete; failed migrations roll back rather than deleting bad data.

Player IDs, roles, champion names, and nonnegative statistics have database constraints. Extraction rejects ambiguous team/role assignments and inconsistent team outcomes. Missing or invalid optional numeric fields are stored as unknown (`NULL`), never invented zeroes. Normalized rows must match extraction of their raw ranked match payload before persistence.

Back up before future schema changes. Add a new numbered migration instead of changing a migration that has already been applied. This small forward-only migration mechanism does not provide downgrade automation or online migration tooling for large production tables.

## Collection and provenance

Each resolved-account history ingestion records timestamps, status, requested count, actual outcomes, and a sanitized error code. Counts are checkpointed after processed match IDs so completed work remains visible if a process is killed. Match-to-run links record discovery provenance, including duplicates seen through more than one account. Source identifiers are hashed internally; the public coverage endpoint returns only aggregate source counts, never PUUIDs, Riot IDs, or hashes.

Riot Account-V1 resolves the initial seed; Match-V5 discovers ranked games. Bounded expansion reuses participant PUUIDs from collected matches:

```powershell
.\backend\venv\Scripts\python.exe -m backend.platform.etl --seed-file backend/etl-seeds.json --count 20 --max-accounts 5
```

This requests up to twenty match IDs for each of five accounts per configured seed. Overlapping games are deduplicated. Expansion is opt-in; the default remains one account. Collection can still take time due to Riot rate limits. Refresh development keys privately when authentication fails.

Run status `partial` means some records were skipped or failed; `failed` means the run stopped. A process killed without cleanup may leave `running` with no finish timestamp; inspect its start time before retrying. Authentication failure during initial account resolution occurs before a resolved-account run can be created. Match storage and provenance links use separate transactions, so coverage explicitly reports any matches without provenance, including legacy imports or interrupted linking.

Discovery accounts are connected through matches, so they are not a random or representative population. The collector does not measure historical rank. API routing regions are not individual platform/server labels. Do not claim broad ranks, all patches, complete champion coverage in match evidence, or statistical reliability from the configured limits alone.

## Measured coverage

```powershell
.\backend\venv\Scripts\python.exe -m backend.platform.maintenance coverage
```

The same report is available at `GET /api/coverage`: match counts by patch, player appearances and champion breadth by role, source accounts by routing region, document kinds, missing CS/gold/runes, recent run outcomes, and untracked matches. These counts describe the stored data, not its reliability.

## Public champion corpus

```powershell
.\backend\venv\Scripts\python.exe -m backend.platform.sync --all-champions
# Or, inside the running API container:
docker compose exec api python -m backend.platform.sync --all-champions
```

This indexes public champion ability references with patch tags and source URLs. It reports missing references and returns failure when requested references are unavailable. It does not create expert matchup strategies or lane-specific counters. Authored general practice remains explicitly labeled; expanding curated strategy knowledge is separate work.

## Local backups and restore drills

```powershell
.\backend\venv\Scripts\python.exe -m backend.platform.maintenance backup
.\backend\venv\Scripts\python.exe -m backend.platform.maintenance verify-restore --file backups/YOUR_BACKUP.dump
```

Run these on the host against the project's local Compose database. The Docker engine must be available. Backups use `pg_dump` custom archives and a PostgreSQL-exported snapshot, with table counts/content fingerprints and an archive SHA-256 manifest. The restore drill creates a fresh randomly named database, restores the archive, compares all table counts and fingerprints, and removes only that disposable database. It never overwrites the app database.

Backups contain private match identifiers and conversations. Both archives and manifests stay under ignored `backups/` and must not be published. A custom archive covers one database, not cluster roles or the public champion file cache. Regenerate the file cache with knowledge sync after moving machines. Only verify this project's trusted backups; restore executes SQL from the archive.

These commands are local backup support, not managed disaster recovery. Automatic scheduling, encryption, off-device storage, retention, and recovery-time objectives still need configuration. Fingerprint comparison reads whole tables; use a separate strategy when data becomes large. PostgreSQL's [pg_dump documentation](https://www.postgresql.org/docs/17/app-pgdump.html) explains archive and backup limitations.
