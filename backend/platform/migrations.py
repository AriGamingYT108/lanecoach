"""Small, forward-only PostgreSQL migrations serialized across app/ETL workers."""
from sqlalchemy import text

CHECKS = {
    'lc_player_role': "role IN ('TOP','JUNGLE','MIDDLE','BOTTOM','UTILITY')",
    'lc_player_id': 'participant_id BETWEEN 1 AND 10',
    'lc_player_champion': "length(trim(champion)) > 0",
    'lc_player_stats': '(kills IS NULL OR kills >= 0) AND (deaths IS NULL OR deaths >= 0) AND (assists IS NULL OR assists >= 0) AND (cs IS NULL OR cs >= 0) AND (gold IS NULL OR gold >= 0)',
}


def migrate(connection):
    connection.execute(text('CREATE TABLE IF NOT EXISTS lc_schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())'))
    applied = set(connection.execute(text('SELECT version FROM lc_schema_migrations')).scalars())
    if 1 not in applied:
        connection.execute(text("CREATE INDEX IF NOT EXISTS lc_docs_search ON lc_documents USING GIN (to_tsvector('english', title || ' ' || body))"))
        connection.execute(text('CREATE INDEX IF NOT EXISTS lc_players_pair ON lc_players(role, champion, opponent)'))
        connection.execute(text('INSERT INTO lc_schema_migrations(version) VALUES (1)'))
    if 2 not in applied:
        for name, expression in CHECKS.items():
            exists = connection.execute(text('SELECT 1 FROM pg_constraint WHERE conname=:name AND conrelid=\'lc_players\'::regclass'), {'name': name}).first()
            if not exists:
                # Identifiers/expressions are static source, never request input.
                connection.execute(text(f'ALTER TABLE lc_players ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID'))
            connection.execute(text(f'ALTER TABLE lc_players VALIDATE CONSTRAINT {name}'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS lc_matches_patch ON lc_matches(patch)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS lc_messages_session ON lc_messages(session_id, id)'))
        connection.execute(text('INSERT INTO lc_schema_migrations(version) VALUES (2)'))
