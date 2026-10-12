"""Check background jobs in a running local LaneCoach app without logging secrets."""
import argparse
import time

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--collect", nargs=2, metavar=("GAME_NAME", "TAG"))
    parser.add_argument("--region", default="americas")
    parser.add_argument("--coach", action="store_true", help="Make one paid coaching request")
    args = parser.parse_args()
    session = requests.Session()
    def get(path):
        response = session.get(args.url + path, timeout=15)
        if response.status_code != 200:
            raise RuntimeError(f"Local request returned HTTP {response.status_code}")
        return response.json()
    status = get("/api/status")
    headers = {"X-LaneCoach-Token": status["token"]}
    def job(path, data):
        response = session.post(args.url + path, headers=headers, json=data, timeout=15)
        if response.status_code != 202:
            raise RuntimeError("Job could not start: " + response.json().get("error", "unknown error"))
        job_id = response.json()["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            result = next(j for j in get("/api/status")["jobs"] if j["id"] == job_id)
            if result["status"] not in {"queued", "running"}:
                if result["status"] != "completed":
                    raise RuntimeError(result["error"] or "Job did not complete")
                return result["result"]
            time.sleep(0.5)
        raise RuntimeError("Job is still running; inspect activity in the app.")
    pairs = get("/api/matchups?limit=1")["matchups"]
    if not pairs:
        raise RuntimeError("Collect a game before web verification")
    pair = {k: pairs[0][k] for k in ("champion", "opponent")}
    result = job("/api/timelines", {**pair, "limit": 2})
    print("Timeline HTTP job verified:", result)
    if args.collect:
        result = job("/api/collect", {"game_name": args.collect[0], "tag_line": args.collect[1], "region": args.region, "count": 1})
        print("Collection HTTP job verified:", result)
    if args.coach:
        result = job("/api/coach", {**pair, "question": "Give me three practical practice goals, distinguishing observations from general advice."})
        print("Coaching HTTP job verified:", result["model"], "response characters:", len(result["text"]))
    print("Web integration verification passed.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, requests.RequestException) as error:
        print(str(error) if isinstance(error, RuntimeError) else "Local server request failed.")
        raise SystemExit(1)
