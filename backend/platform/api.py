"""FastAPI coaching service with a PostgreSQL-backed conversation and retrieval store."""
import os
from contextlib import asynccontextmanager
from pathlib import Path
from threading import BoundedSemaphore
from typing import Literal
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.catalog import Catalog
from backend.coaching import CoachingError
from .coach import answer
from .knowledge import seed_knowledge
from .store import Store

Role = Literal["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Role = "TOP"
    champion: str = Field(default="", max_length=80)
    opponent: str = Field(default="", max_length=80)
    rank: str = Field(default="Learning", max_length=40)
    goal: str = Field(default="Make better decisions", max_length=300)
    patch: str | None = Field(default=None, max_length=20)


class CoachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    profile: Profile = Field(default_factory=Profile)
    question: str = Field(min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, max_length=40)


def create_app(store=None, catalog=None, coach_fn=answer):
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    store = store or Store()
    catalog = catalog or Catalog()
    gate = BoundedSemaphore(2)

    @asynccontextmanager
    async def lifespan(app):
        try:
            store.initialize()
            seed_knowledge(store)
            app.state.ready = True
        except SQLAlchemyError:
            app.state.ready = False
        yield
        store.engine.dispose()

    app = FastAPI(title="LaneCoach", description="All-role coaching, conversation and evidence-backed retrieval", version="2.0.0", lifespan=lifespan)
    app.state.ready = False
    app.state.store = store
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "api", "testserver"])

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.method == "POST":
            origin = request.headers.get("origin")
            allowed = {"http://localhost:3000", "http://127.0.0.1:3000", os.getenv("FRONTEND_ORIGIN", "")}
            if (origin and origin not in allowed) or request.headers.get("x-lanecoach-client") != "browser":
                return JSONResponse({"detail": "Use the LaneCoach app to start coaching requests."}, status_code=403)
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return JSONResponse({"detail": "Invalid content length."}, status_code=400)
            if length > 20000:
                return JSONResponse({"detail": "Request too large."}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if not request.url.path.startswith("/api/assets/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, error):
        return JSONResponse({"detail": "PostgreSQL is unavailable. Start the database and restart the API."}, status_code=503)

    def ready():
        if not app.state.ready:
            raise HTTPException(503, "PostgreSQL is not ready. Start Docker/database and restart the API.")

    @app.get("/api/health")
    def health():
        catalog.reload()
        overview = store.overview() if app.state.ready else {"matches": 0, "participants": 0, "documents": 0, "engine": store.engine.dialect.name}
        return {"database_ready": app.state.ready, "ai_configured": bool(os.getenv("OPENAI_API_KEY")),
                "riot_configured": bool(os.getenv("RIOT_API_KEY")), "catalog_version": catalog.data.get("version"),
                "model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"), **overview}

    @app.get("/api/champions")
    def champions():
        catalog.reload()
        return {"version": catalog.data.get("version"), "champions": list(catalog.data["champions"].values())}

    @app.get("/api/assets/{kind}/{identifier}")
    def asset(kind: str, identifier: str):
        try:
            path = catalog.asset(kind, identifier)
        except Exception:
            path = None
        if not path:
            raise HTTPException(404, "Asset not available")
        return FileResponse(path, media_type="image/png")

    @app.get("/api/analytics")
    def analytics(champion: str, role: Role = "TOP", opponent: str | None = None, patch: str | None = None, minimum: int = 1):
        ready()
        catalog.reload()
        if not 1 <= minimum <= 100000 or len(champion) > 80:
            raise HTTPException(422, "Invalid analytics filter")
        return store.analytics(catalog.resolve(champion), role, catalog.resolve(opponent) if opponent else None, patch, minimum)

    @app.get("/api/sessions/{session_id}")
    def session(session_id: str):
        ready()
        result = store.session(session_id)
        if result is None:
            raise HTTPException(404, "Conversation not found")
        return result

    @app.post("/api/coach")
    def coach(body: CoachRequest):
        ready()
        if not gate.acquire(blocking=False):
            raise HTTPException(429, "Two coaching requests are already running. Try again shortly.")
        try:
            catalog.reload()
            profile = body.profile.model_dump()
            for key in ("champion", "opponent"):
                profile[key] = catalog.resolve(profile[key]) if profile[key] else ""
            history = []
            if body.session_id:
                conversation = store.session(body.session_id)
                if not conversation:
                    raise HTTPException(404, "Conversation not found")
                if conversation["profile"] != profile:
                    raise HTTPException(409, "Your role or champion changed. Start a new conversation.")
                history = conversation["messages"]
            result = coach_fn(store, catalog, profile, body.question, history)
            session_id = body.session_id or store.new_session(profile)
            store.save_exchange(session_id, body.question, result["text"], result["sources"])
            return {"session_id": session_id, **result}
        except CoachingError as error:
            raise HTTPException(502, str(error)) from None
        finally:
            gate.release()

    return app


app = create_app()
