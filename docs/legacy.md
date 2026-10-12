# LaneCoach

LaneCoach is a local League of Legends Top Lane Matchup Coach with a responsive
web interface, real ranked-match evidence, timeline analysis, and optional AI
practice plans. It reuses the existing Riot collector and SQLite database.

## Start the app

Install dependencies with the existing environment as shown below, then run:

```powershell
.\backend\venv\Scripts\python.exe -m backend.app
```

Open **http://127.0.0.1:5000** in your browser. Alternatively run `./start.ps1`.
Keep the terminal open; press Ctrl+C to stop. Use `--port 5001` if the port is
already occupied, or `--db path/to/file.sqlite3` to select another database.
Run one app instance per database. This version binds to your computer's loopback
interface; it is not a publicly hosted or multi-user service.

The app provides:

- A searchable, paginated matchup library with patch and champion filters.
- Reports with game win counts, K/D/A, CS, CS per minute, gold, and denominators.
- Recorded rune sets and final inventories with cached Riot asset labels.
- Background ranked collection, progress, duplicate prevention, and job history.
- Timeline collection with 10/15-minute CS and gold differences, per-game gold
  charts, and early kills, assists, purchases, sales, and purchase undo events.
- AI coaching and custom focus questions, saved locally in job history.
- CSV export of all recorded games matching the selected pair and patch.
- Connection configuration status and a Data Dragon reference refresh action.

To get started, open a stored matchup, inspect the report, and click **Fetch lane
timelines**. Then choose **AI coach**, enter a focus, and generate a practice plan.
Use **Collect games** for your own history or an active player's Riot ID.

## Installation

From the project root, use the existing virtual environment (Python 3.10+):

```powershell
.\backend\venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

Set `RIOT_API_KEY=your_key_here` in the existing `backend/.env`, replacing the
placeholder privately. Never share or commit your key. Environment variables
take precedence; the dotenv file is located relative to the backend directory.
Development keys expire after 24 hours; refresh them at the
[Riot Developer Portal](https://developer.riotgames.com/docs/portal).

For AI coaching, add these lines privately to the same file, then restart:

```dotenv
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4.1-mini
```

`backend/.env.example` contains placeholders only. Do not replace an existing
`.env` with the example; preserve your working Riot configuration. The model is
configurable. Requests use the
[OpenAI Responses API](https://developers.openai.com/api/docs/guides/text) with
`store=false`. AI requires valid API access and available billing/quota, which
are separate from a ChatGPT subscription. It may incur usage charges. LaneCoach
does not automatically retry paid AI requests.

AI receives the aggregate report, your question, and available public champion
ability descriptions. It excludes match IDs, player names, PUUIDs, and credentials
from the report sent to OpenAI. Coaching is prompted to distinguish observed
evidence from general advice and never invent matchup statistics. It may still
make mistakes; verify ability mechanics and practice advice in-game.

Without the OpenAI key, every data feature remains available. If the key is
configured but rejected or out of quota, the app displays an actionable error.
Configuration status means a key is present, not that provider access is verified.

## Usage

Start by listing the pairs actually stored in your database:

```powershell
.\backend\venv\Scripts\python.exe backend/database.py --list
.\backend\venv\Scripts\python.exe backend/database.py --list Garen
.\backend\venv\Scripts\python.exe backend/database.py --list --min-games 5 --limit 50 --patch 16.20
```

Listing combines both team orientations into one pair, sorts by unique game count,
and shows up to 20 pairs by default. Each pair includes wins, sample size, and game
win percentage for the first champion. An optional champion filter puts that
champion first. `--min-games` filters by unique games and does not establish
statistical reliability. An empty list means no stored pairs match your filters.
Choose a listed pair to query with the existing two-champion command below.

```powershell
.\backend\venv\Scripts\python.exe backend/collector.py "Your Game Name" "NA1" --region americas --count 100
.\backend\venv\Scripts\python.exe backend/database.py Garen Darius
.\backend\venv\Scripts\python.exe backend/database.py Garen Darius --patch 16.20
```

The collector arguments form `Game Name#tag`; omit `#` from the tag argument.
Regional clusters: `americas` (NA/BR/LAN/LAS), `europe` (EUW/EUNE/TR/RU),
`asia` (KR/JP), `sea` (OCE/Southeast Asia). Account-V1 resolves the PUUID;
Match-V5 retrieves ranked history in pages of at most 100. See the
[Riot API reference](https://developer.riotgames.com/apis/).

`--count` limits history IDs examined; `--start` selects an older history offset.
Both commands accept `--db path/to/file.sqlite3` (parent directory must exist).
Default storage is `backend/matchups.sqlite3`. Re-running skips stored match IDs.
The collector prints fetched, inserted, duplicate, skipped, and failed counts.
Saved records remain committed if a later request fails. Failed matches can be
retried by rerunning the same history range.

Eligible games have exactly one TOP participant on each opposing team and
consistent winner flags. Blue side is stored as `champion`, red as `opponent`.
Each record contains champion names, winner, full game version, major.minor patch,
duration, rune IDs and full perks including stat runes, nonzero item IDs including
trinket, kills/deaths/assists, lane plus jungle CS, and earned gold for both players.
Missing optional stats remain null; missing rune/item collections are empty.
Missing identity, role, or outcome data causes the match to be skipped.

Timeline jobs fetch at most 20 uncached games at a time from the report, so click
again to load additional games. Cached timelines are reused. Older records are
compatible: participant IDs are recovered from Match-V5 before timeline extraction.
Snapshots use actual timestamps; each checkpoint selects the last valid frame
at or up to 90 seconds before 10/15 minutes. Games that have not reached the
checkpoint are excluded, and missing numeric evidence stays unknown. Each
average displays its own sample count. Events involving Top players may occur
anywhere on the map, so the app does not label them as solo lane kills.

All statistics are aggregated from matching stored games. Game evidence displays
the newest 100 inserted records; CSV export includes all matching records. The
library loads up to 1,000 matching pairs and displays 24 at a time. The 30-game
small-sample label is a presentation threshold, not a statistical significance test.
Mirror matchups keep blue/red side summaries and explicitly flag the 50% outcome.

Queries include both team orientations and return wins, sample size, unique match
count, and win rate as a percentage. Zero samples return null. Patch filters use
major.minor versions. Mirror matchups count two participants per match and have a
50% game win rate. These are **game wins, not lane wins**. Selected-player samples
are biased and may be small; no statistical reliability or causal claim is made.
Example commands do not represent invented matchup statistics.

Requests have 10-second timeouts and up to three retries for network errors,
server errors, and HTTP 429. Rate limits honor `Retry-After` before further requests,
following [Riot's documentation](https://developer.riotgames.com/docs/portal#rate-limiting).
Exhausted rate limits and authentication errors stop collection. Refresh expired
credentials or retry later. Errors omit keys, request headers, and response bodies.

## Helpers and tests

```powershell
.\backend\venv\Scripts\python.exe backend/champion.py
.\backend\venv\Scripts\python.exe backend/test_api.py
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v
```

The champion helper retains its interactive Data Dragon lookup. `test_api.py`
is an optional live NA server-status check that prints only the HTTP status.
`match.py` preserves `get_match`, `extract_top_matchup`, `get_runes`, `get_items`,
and `print_matchup`. Importing modules never prompts or makes requests.
Automated tests use synthetic fixtures, mocked HTTP, and temporary SQLite files;
no credentials or live API access are needed.

Runtime dependencies are requests and python-dotenv; SQLite and tests use the
standard library. Git ignores environment secrets, virtual environments, Python
caches, SQLite databases, and their journal/WAL sidecars.

## Verification and troubleshooting

```powershell
# All offline automated tests (no keys or external requests needed)
.\backend\venv\Scripts\python.exe -m unittest discover -s backend/tests -v

# Optional browser QA using installed Microsoft Edge and a running app
.\backend\venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
.\backend\venv\Scripts\python.exe scripts/browser_smoke.py

# Explicit live verification: public assets and two timelines from a stored pair
.\backend\venv\Scripts\python.exe scripts/verify_live.py

# Also make one paid AI request; only safe status information is printed
.\backend\venv\Scripts\python.exe scripts/verify_live.py --coach
```

- **OpenAI HTTP 429:** check API project billing, available credits, and rate
  limits. A key alone does not provide quota. Retry only after resolving the cause.
- **Riot HTTP 401/403:** refresh the development key in `.env` and restart.
- **No games for a pair:** select a pair from your library or collect more history.
- **No portraits or labels:** refresh Data Dragon under Connections; reports remain
  usable if that service is unavailable. Labels use the cached reference version.
- **A job seems paused:** Riot rate limiting can require waiting for `Retry-After`.
  The single worker serializes all collection, timeline, catalog, and coaching jobs.
- **A job was interrupted:** saved matches remain committed. Restart the same job;
  duplicate matches and cached timelines will be skipped.
- **Port already in use:** stop the earlier app or select another `--port`.

## Architecture and data

`backend/app.py` serves the static frontend and JSON API through Flask and
Waitress; no frontend build is required. `collector.py`, `matchup.py`, and
`riot_api.py` retrieve/extract matches. `database.py` stores matchups, extracted
timelines, and recent jobs in SQLite. `reports.py` builds observed summaries;
`timeline.py` extracts early-lane evidence. `catalog.py` caches public Riot
references and versioned ability descriptions under ignored `backend/.cache/`.
Portraits and item/rune icons are served from a local cache, so the browser does
not need to connect directly to Riot's CDN. Missing assets fall back to readable names.
`coaching.py` makes the optional AI request; `jobs.py` provides one background
worker with durable job status. Pending jobs are marked interrupted after restart.

The local API validates inputs, restricts trusted hosts, requires same-origin
job requests with an in-memory token, and serves a restrictive content security
policy. Credentials never go to the frontend. CSV values are protected against
spreadsheet formula injection. Error messages exclude provider bodies and headers.
There is no public authentication layer; do not expose this local server to the
internet. Public deployment needs a hosting choice, authentication, and a Riot key
appropriate for the intended audience; it is not part of the local app setup.

Back up `backend/matchups.sqlite3` with the app stopped. Database rows are added
without replacing existing matchup data. No destructive migration or GitHub push
is performed. LaneCoach is independent and not endorsed by Riot Games.
