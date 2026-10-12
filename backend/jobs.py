"""One background worker keeps collection responsive and serializes Riot access."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from .database import MatchupDatabase
from .riot_api import RiotAPIError
from .coaching import CoachingError


def now():
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lanecoach")
        self.lock = Lock()
        self.active = None
        with MatchupDatabase(db_path) as db:
            for job in db.jobs():
                if job["status"] in {"queued", "running"}:
                    job.update(status="interrupted", error="The app stopped during this job. Saved data is intact; run it again.", updated=now())
                    db.save_job(job)

    def submit(self, kind, parameters, work):
        with self.lock:
            if self.active is not None:
                raise ValueError("A job is already running. Wait for it to finish before starting another.")
            job = {"id": uuid4().hex, "kind": kind, "parameters": parameters,
                   "status": "queued", "created": now(), "updated": now(), "progress": {}, "result": None, "error": None}
            with MatchupDatabase(self.db_path) as db:
                db.save_job(job)
            self.active = job["id"]
            self.executor.submit(self._run, job, work)
            return dict(job)

    def _run(self, job, work):
        def update(progress):
            job.update(progress=progress, updated=now())
            with MatchupDatabase(self.db_path) as db:
                db.save_job(job)
        try:
            job["status"] = "running"
            update({})
            job["result"] = work(update)
            job["status"] = "completed"
        except (RiotAPIError, CoachingError, ValueError) as error:
            job.update(status="failed", error=str(error))
        except Exception:
            # Third-party exception text can contain sensitive request details.
            job.update(status="failed", error="Job failed unexpectedly. Saved records are intact; check configuration and retry.")
        finally:
            job["updated"] = now()
            with MatchupDatabase(self.db_path) as db:
                db.save_job(job)
            with self.lock:
                self.active = None

    def close(self):
        self.executor.shutdown(wait=True)
