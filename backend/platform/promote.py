"""Copy match/reference evidence to cloud PostgreSQL; exclude conversations and keys."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from .store import Store, matches, documents, ingestion_runs, match_sources
from .etl import extract_players


def promote(source, target):
    target.initialize()
    counts = {'inserted': 0, 'duplicates': 0, 'skipped': 0, 'documents': 0}
    with source.engine.connect() as connection:
        for row in connection.execute(matches.select()).mappings():
            extracted = extract_players(row['payload'])
            if not extracted:
                counts['skipped'] += 1
                continue
            counts['inserted' if target.save_match(row['payload'], extracted) else 'duplicates'] += 1
        for row in connection.execute(documents.select()).mappings():
            target.upsert_document(dict(row))
            counts['documents'] += 1
        insert = pg_insert if target.engine.dialect.name == 'postgresql' else sqlite_insert
        with target.engine.begin() as output:
            for row in connection.execute(ingestion_runs.select()).mappings():
                values = dict(row)
                statement = insert(ingestion_runs).values(**values)
                output.execute(statement.on_conflict_do_update(index_elements=[ingestion_runs.c.id],
                    set_={key: value for key, value in values.items() if key != 'id'}))
            for row in connection.execute(match_sources.select()).mappings():
                if output.execute(matches.select().where(matches.c.match_id == row['match_id'])).first():
                    output.execute(insert(match_sources).values(**dict(row)).on_conflict_do_nothing())
    return counts


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    destination = os.getenv('TARGET_DATABASE_URL')
    if not destination:
        raise SystemExit('Set TARGET_DATABASE_URL privately to the intended cloud database.')
    source = Store(os.getenv('SOURCE_DATABASE_URL') or None)
    target = Store(destination)
    try:
        if source.engine.url == target.engine.url:
            raise ValueError('Source and target must differ')
        print('Evidence migration:', promote(source, target))
    finally:
        source.engine.dispose()
        target.engine.dispose()


if __name__ == '__main__':
    try:
        main()
    except (SQLAlchemyError, ValueError):
        raise SystemExit('Evidence migration failed. Check source/target database configuration privately; existing target data is preserved.') from None
