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


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--champions", nargs="*", default=[])
    args = parser.parse_args()
    catalog = Catalog()
    catalog.refresh()
    store = Store()
    store.initialize()
    seed_knowledge(store)
    for champion in args.champions:
        champion_context(store, catalog, {"champion": champion, "opponent": "", "patch": None})
    print("Knowledge sync complete:", store.overview())


if __name__ == "__main__":
    try:
        main()
    except SQLAlchemyError:
        raise SystemExit("Database operation failed. Check PostgreSQL and DATABASE_URL privately.") from None
    except (requests.RequestException, ValueError, KeyError):
        raise SystemExit("Public champion reference sync failed. Check connectivity and champion names.") from None
