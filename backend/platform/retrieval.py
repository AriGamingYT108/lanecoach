"""Actual retrieval-augmented generation: PostgreSQL lexical search, scoped context."""
import re
from sqlalchemy import text
from .store import documents


def retrieve(store, question, profile, limit=6):
    params = {"question": question, "role": profile["role"], "champion": profile.get("champion") or "",
              "opponent": profile.get("opponent") or "", "patch": profile.get("patch") or "", "limit": limit}
    if store.engine.dialect.name == "postgresql":
        sql = """SELECT *, ts_rank_cd(to_tsvector('english', title || ' ' || body),
              websearch_to_tsquery('english', :question)) AS score
            FROM lc_documents WHERE (role IS NULL OR role=:role)
            AND (champion IS NULL OR champion=:champion OR champion=:opponent)
            AND (patch IS NULL OR :patch='' OR patch=:patch)
            ORDER BY score DESC, CASE WHEN champion IS NOT NULL THEN 0 ELSE 1 END, id LIMIT :limit"""
        with store.engine.connect() as connection:
            return [dict(r) for r in connection.execute(text(sql), params).mappings()]
    # Test-only deterministic lexical equivalent; production always uses PostgreSQL.
    tokens = set(re.findall(r"\w+", question.lower()))
    with store.engine.connect() as connection:
        candidates = [dict(r) for r in connection.execute(documents.select()).mappings()]
    eligible = [d for d in candidates if d["role"] in {None, profile["role"]}
                and d["champion"] in {None, params["champion"], params["opponent"]}
                and (not params["patch"] or d["patch"] in {None, params["patch"]})]
    for d in eligible:
        d["score"] = len(tokens & set(re.findall(r"\w+", (d["title"] + " " + d["body"]).lower())))
    return sorted(eligible, key=lambda d: (-d["score"], d["id"]))[:limit]
