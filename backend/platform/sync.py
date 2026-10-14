"""Load public champion references into the RAG corpus; credentials are not copied."""
import argparse
import requests
from sqlalchemy.exc import SQLAlchemyError
from dotenv import load_dotenv
from pathlib import Path
from backend.catalog import Catalog
from .coach import champion_context
from .knowledge import seed_knowledge
from .store import Store
from .store import documents


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--champions", nargs="*", default=[])
    parser.add_argument('--all-champions', action='store_true', help='Cache and index every champion in the current public catalog')
    args = parser.parse_args()
    catalog = Catalog()
    catalog.refresh()
    store = Store()
    store.initialize()
    seed_knowledge(store)
    selected = list(catalog.data['champions']) if args.all_champions else args.champions
    missing = []
    for index, champion in enumerate(selected, 1):
        champion_context(store, catalog, {"champion": champion, "opponent": "", "patch": None})
        identifier = f"champion-{catalog.resolve(champion)}-{catalog.data['version']}"
        with store.engine.connect() as connection:
            if not connection.execute(documents.select().where(documents.c.id == identifier)).first():
                missing.append(champion)
        if index % 25 == 0:
            print(f'Processed {index}/{len(selected)} public champion references.', flush=True)
    print("Knowledge sync complete:", store.overview())
    if missing:
        print('References not available:', ', '.join(missing))
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError:
        raise SystemExit("Database operation failed. Check PostgreSQL and DATABASE_URL privately.") from None
    except (requests.RequestException, ValueError, KeyError):
        raise SystemExit("Public champion reference sync failed. Check connectivity and champion names.") from None
