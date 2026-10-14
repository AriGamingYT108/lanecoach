"""Relational persistence and SQL analytics; SQLite is supported only for tests."""
import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (JSON, Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Integer,
                        MetaData, String, Table, Text, create_engine, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.pool import StaticPool
from .migrations import CHECKS, migrate

metadata = MetaData()
json_type = JSON().with_variant(JSONB, "postgresql")
matches = Table("lc_matches", metadata,
    Column("match_id", String(80), primary_key=True), Column("patch", String(20), nullable=False),
    Column("duration", Integer), Column("payload", json_type, nullable=False))
players = Table("lc_players", metadata,
    Column("match_id", String(80), ForeignKey("lc_matches.match_id"), primary_key=True),
    Column("participant_id", Integer, primary_key=True), Column("role", String(20), nullable=False),
    Column("champion", String(80), nullable=False), Column("opponent", String(80)),
    Column("win", Boolean, nullable=False), Column("keystone", Integer),
    Column("kills", Integer), Column("deaths", Integer), Column("assists", Integer),
    Column("cs", Integer), Column("gold", Integer), Column("payload", json_type, nullable=False),
    *[CheckConstraint(expression, name=name) for name, expression in CHECKS.items()])
ingestion_runs = Table('lc_ingestion_runs', metadata,
    Column('id', String(40), primary_key=True), Column('region', String(20), nullable=False),
    Column('source_hash', String(64), nullable=False), Column('started', DateTime(timezone=True), nullable=False),
    Column('finished', DateTime(timezone=True)), Column('status', String(20), nullable=False),
    Column('requested', Integer, nullable=False), Column('counts', json_type, nullable=False), Column('error_code', String(40)))
match_sources = Table('lc_match_sources', metadata,
    Column('match_id', String(80), ForeignKey('lc_matches.match_id'), primary_key=True),
    Column('run_id', String(40), ForeignKey('lc_ingestion_runs.id'), primary_key=True))
documents = Table("lc_documents", metadata,
    Column("id", String(150), primary_key=True), Column("title", Text, nullable=False),
    Column("body", Text, nullable=False), Column("role", String(20)), Column("champion", String(80)),
    Column("patch", String(20)), Column("source_url", Text), Column("source_kind", String(30), nullable=False))
sessions = Table("lc_sessions", metadata,
    Column("id", String(40), primary_key=True), Column("profile", json_type, nullable=False),
    Column('owner_hash', String(64)),
    Column("created", DateTime(timezone=True), nullable=False))
request_budgets = Table('lc_request_budgets', metadata,
    Column('bucket', String(150), primary_key=True), Column('used', Integer, nullable=False))
messages = Table("lc_messages", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(40), ForeignKey("lc_sessions.id"), nullable=False),
    Column("role", String(20), nullable=False), Column("content", Text, nullable=False),
    Column("sources", json_type), Column("created", DateTime(timezone=True), nullable=False))


class Store:
    def __init__(self, url=None):
        url = url or os.getenv("DATABASE_URL", "postgresql+psycopg://lanecoach:local-development-only@127.0.0.1:5432/lanecoach")
        if url.startswith('postgres://'):
            url = 'postgresql+psycopg://' + url[len('postgres://'):]
        elif url.startswith('postgresql://'):
            url = 'postgresql+psycopg://' + url[len('postgresql://'):]
        options = {"pool_pre_ping": True, "hide_parameters": True}
        if url == "sqlite://":
            options.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
        elif url.startswith("postgresql"):
            options["connect_args"] = {"connect_timeout": 5}
        self.engine = create_engine(url, **options)

    def initialize(self):
        with self.engine.begin() as connection:
            if self.engine.dialect.name == 'postgresql':
                connection.execute(text('SELECT pg_advisory_xact_lock(74392610)'))
            metadata.create_all(connection)
            if self.engine.dialect.name == 'postgresql':
                migrate(connection)

    def upsert_document(self, document):
        insert = postgres_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        statement = insert(documents).values(**document)
        with self.engine.begin() as connection:
            connection.execute(statement.on_conflict_do_update(index_elements=[documents.c.id],
                set_={key: getattr(statement.excluded, key) for key in document if key != "id"}))

    def save_match(self, match, extracted):
        from .etl import extract_players
        validated = extract_players(match)
        if not validated or extracted != validated:
            raise ValueError('Match data does not match validated ranked participants')
        insert = postgres_insert if self.engine.dialect.name == "postgresql" else sqlite_insert
        with self.engine.begin() as connection:
            statement = insert(matches).values(match_id=match["metadata"]["matchId"],
                patch=".".join(match["info"]["gameVersion"].split(".")[:2]), duration=match["info"].get("gameDuration"), payload=match)
            if not connection.execute(statement.on_conflict_do_nothing(index_elements=[matches.c.match_id]).returning(matches.c.match_id)).first():
                return False
            if extracted:
                connection.execute(players.insert(), extracted)
        return True

    def start_run(self, region, source_hash, requested):
        run_id = uuid4().hex
        with self.engine.begin() as connection:
            connection.execute(ingestion_runs.insert().values(id=run_id, region=region, source_hash=source_hash,
                requested=requested, started=datetime.now(timezone.utc), status='running', counts={}))
        return run_id

    def finish_run(self, run_id, counts, status='completed', error_code=None):
        with self.engine.begin() as connection:
            connection.execute(ingestion_runs.update().where(ingestion_runs.c.id == run_id).values(
                finished=datetime.now(timezone.utc), counts=counts, status=status, error_code=error_code))

    def checkpoint_run(self, run_id, counts):
        with self.engine.begin() as connection:
            connection.execute(ingestion_runs.update().where(ingestion_runs.c.id == run_id).values(counts=counts))

    def record_source(self, match_id, run_id):
        insert = postgres_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
        with self.engine.begin() as connection:
            connection.execute(insert(match_sources).values(match_id=match_id, run_id=run_id).on_conflict_do_nothing())

    def discover_accounts(self, region, limit=50):
        # Private PUUIDs remain in memory; never return them through coverage APIs.
        with self.engine.connect() as connection:
            rows = connection.execute(matches.select().join(match_sources, matches.c.match_id == match_sources.c.match_id)
                .join(ingestion_runs, ingestion_runs.c.id == match_sources.c.run_id)
                .where(ingestion_runs.c.region == region).order_by(ingestion_runs.c.started.desc()).limit(limit)).mappings()
            return list(dict.fromkeys(p['puuid'] for row in rows for p in row['payload'].get('info', {}).get('participants', [])
                if isinstance(p, dict) and isinstance(p.get('puuid'), str) and p['puuid']))

    def contains(self, match_id):
        with self.engine.connect() as connection:
            return connection.execute(matches.select().where(matches.c.match_id == match_id)).first() is not None

    def analytics(self, champion, role, opponent=None, patch=None, minimum=1):
        filters = "p.champion = :champion AND p.role = :role"
        params = {"champion": champion, "role": role, "minimum": minimum}
        if opponent:
            filters += " AND p.opponent = :opponent"
            params["opponent"] = opponent
        if patch:
            filters += " AND m.patch = :patch"
            params["patch"] = patch
        base = " FROM lc_players p JOIN lc_matches m ON m.match_id=p.match_id WHERE " + filters
        wins = "SUM(CASE WHEN p.win THEN 1 ELSE 0 END)"
        with self.engine.connect() as connection:
            overall = dict(connection.execute(text("SELECT COUNT(*) AS sample_size, " + wins + " AS wins" + base), params).mappings().one())
            runes = [dict(r) for r in connection.execute(text("SELECT p.keystone, COUNT(*) AS sample_size, " + wins + " AS wins" + base + " AND p.keystone IS NOT NULL GROUP BY p.keystone HAVING COUNT(*) >= :minimum ORDER BY COUNT(*) DESC, p.keystone"), params).mappings()]
            counters = [dict(r) for r in connection.execute(text("SELECT p.opponent, COUNT(*) AS sample_size, " + wins + " AS wins" + base + " AND p.opponent IS NOT NULL GROUP BY p.opponent HAVING COUNT(*) >= :minimum ORDER BY COUNT(*) DESC, p.opponent"), params).mappings()]
        for result in [overall, *runes, *counters]:
            result["wins"] = int(result["wins"] or 0)
            result["win_rate"] = round(100 * result["wins"] / result["sample_size"], 2) if result["sample_size"] else None
        return {"champion": champion, "role": role, "opponent": opponent, "patch": patch,
                "overall": overall, "runes": runes, "opponents": counters,
                "note": "Observed game outcomes from a selected-player sample. Rune/counter associations are not optimal choices or causal evidence."}

    def overview(self):
        with self.engine.connect() as connection:
            return {"matches": connection.execute(text("SELECT COUNT(*) FROM lc_matches")).scalar_one(),
                    "participants": connection.execute(text("SELECT COUNT(*) FROM lc_players")).scalar_one(),
                    "documents": connection.execute(text("SELECT COUNT(*) FROM lc_documents")).scalar_one(),
                    "engine": self.engine.dialect.name}

    def new_session(self, profile, owner_hash=None):
        session_id = uuid4().hex
        with self.engine.begin() as connection:
            connection.execute(sessions.insert().values(id=session_id, profile=profile, owner_hash=owner_hash, created=datetime.now(timezone.utc)))
        return session_id

    def session(self, session_id, owner_hash=None):
        with self.engine.connect() as connection:
            query = sessions.select().where(sessions.c.id == session_id)
            if owner_hash is not None:
                query = query.where(sessions.c.owner_hash == owner_hash)
            row = connection.execute(query).mappings().first()
            if not row:
                return None
            history = [dict(r) for r in connection.execute(messages.select().where(messages.c.session_id == session_id).order_by(messages.c.id)).mappings()]
        return {"id": row["id"], "profile": row["profile"], "messages": history}

    def reserve_requests(self, limits):
        """Atomic shared budget reservation; roll back every bucket on rejection."""
        insert = postgres_insert if self.engine.dialect.name == 'postgresql' else sqlite_insert
        class Exhausted(Exception):
            pass
        try:
            with self.engine.begin() as connection:
                for bucket, limit in sorted(limits.items()):
                    connection.execute(insert(request_budgets).values(bucket=bucket, used=0).on_conflict_do_nothing())
                    updated = connection.execute(request_budgets.update().where(
                        (request_budgets.c.bucket == bucket) & (request_budgets.c.used < limit)
                    ).values(used=request_budgets.c.used + 1).returning(request_budgets.c.bucket)).first()
                    if not updated:
                        raise Exhausted()
            return True
        except Exhausted:
            return False

    def save_exchange(self, session_id, question, answer, sources):
        stamp = datetime.now(timezone.utc)
        with self.engine.begin() as connection:
            connection.execute(messages.insert(), [
                {"session_id": session_id, "role": "user", "content": question, "sources": [], "created": stamp},
                {"session_id": session_id, "role": "assistant", "content": answer, "sources": sources, "created": stamp}])
