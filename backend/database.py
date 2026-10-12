"""SQLite persistence: one record per Riot match, with full extracted payload."""
import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).with_name("matchups.sqlite3")


class MatchupDatabase:
    def __init__(self, path=DEFAULT_DB):
        self.connection = sqlite3.connect(path, timeout=30)
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS matchups (
            match_id TEXT PRIMARY KEY, patch TEXT NOT NULL,
            champion TEXT NOT NULL, opponent TEXT NOT NULL,
            champion_win INTEGER NOT NULL CHECK(champion_win IN (0, 1)),
            payload TEXT NOT NULL)""")
        self.connection.execute("CREATE INDEX IF NOT EXISTS matchup_pair ON matchups(champion, opponent, patch)")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS timelines (
            match_id TEXT PRIMARY KEY REFERENCES matchups(match_id), payload TEXT NOT NULL)""")
        self.connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, payload TEXT NOT NULL)""")
        self.connection.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    def contains(self, match_id):
        return self.connection.execute("SELECT 1 FROM matchups WHERE match_id = ?", (match_id,)).fetchone() is not None

    def save_matchup(self, matchup):
        if type(matchup["champion_win"]) is not bool:
            raise ValueError("champion_win must be a boolean")
        with self.connection:
            cursor = self.connection.execute("""INSERT INTO matchups VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(match_id) DO NOTHING""",
                (matchup["match_id"], matchup.get("patch_major_minor", ".".join(matchup["patch"].split(".")[:2])),
                 matchup["champion"], matchup["opponent"], int(matchup["champion_win"]), json.dumps(matchup)))
        return cursor.rowcount == 1

    def get_matchup(self, match_id):
        row = self.connection.execute("SELECT payload FROM matchups WHERE match_id = ?", (match_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def overview(self):
        names = [r[0] for r in self.connection.execute(
            "SELECT champion FROM matchups UNION SELECT opponent FROM matchups ORDER BY 1")]
        patches = [r[0] for r in self.connection.execute(
            "SELECT DISTINCT patch FROM matchups ORDER BY patch DESC")]
        return {"matches": self.connection.execute("SELECT count(*) FROM matchups").fetchone()[0],
                "timelines": self.connection.execute("SELECT count(*) FROM timelines").fetchone()[0],
                "champions": names, "patches": patches,
                "pairs": self.connection.execute("""SELECT count(*) FROM (
                    SELECT min(champion, opponent), max(champion, opponent) FROM matchups GROUP BY 1, 2)
                    """).fetchone()[0]}

    def matchup_records(self, champion, opponent, patch=None):
        sql = """SELECT payload FROM matchups WHERE
            ((champion = ? COLLATE NOCASE AND opponent = ? COLLATE NOCASE) OR
            (champion = ? COLLATE NOCASE AND opponent = ? COLLATE NOCASE))"""
        params = [champion, opponent, opponent, champion]
        if patch:
            sql += " AND patch = ?"
            params.append(patch)
        return [json.loads(r[0]) for r in self.connection.execute(sql + " ORDER BY rowid DESC", params)]

    def save_timeline(self, match_id, timeline):
        with self.connection:
            self.connection.execute("INSERT INTO timelines VALUES (?, ?) ON CONFLICT(match_id) DO UPDATE SET payload=excluded.payload",
                                    (match_id, json.dumps(timeline)))

    def get_timeline(self, match_id):
        row = self.connection.execute("SELECT payload FROM timelines WHERE match_id=?", (match_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_job(self, job):
        with self.connection:
            self.connection.execute("INSERT INTO jobs VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                                    (job["id"], json.dumps(job)))

    def jobs(self):
        return [json.loads(r[0]) for r in self.connection.execute("SELECT payload FROM jobs ORDER BY rowid DESC LIMIT 30")]

    def list_matchups(self, champion=None, patch=None, min_games=1, limit=20):
        """List unique pairs by game count, combining blue/red orientations."""
        if min_games < 1 or limit < 1:
            raise ValueError("min_games and limit must be positive")
        filters, params = [], []
        if champion is not None:
            filters.append("(champion = ? COLLATE NOCASE OR opponent = ? COLLATE NOCASE)")
            params.extend([champion, champion])
        if patch is not None:
            filters.append("patch = ?")
            params.append(patch)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        rows = self.connection.execute("""SELECT
            min(champion COLLATE NOCASE, opponent COLLATE NOCASE) AS first,
            max(champion COLLATE NOCASE, opponent COLLATE NOCASE) AS second,
            count(*) AS games FROM matchups""" + where + """
            GROUP BY first COLLATE NOCASE, second COLLATE NOCASE
            HAVING count(*) >= ?
            ORDER BY games DESC, first COLLATE NOCASE, second COLLATE NOCASE LIMIT ?""",
            params + [min_games, limit]).fetchall()
        results = []
        for first, second, _ in rows:
            if champion is not None and second.casefold() == champion.casefold():
                first, second = second, first
            results.append(self.win_rate(first, second, patch))
        return results

    def win_rate(self, champion, opponent, patch=None):
        """Count both team orientations once; return no percentage for zero games."""
        sql = """SELECT champion, opponent, champion_win FROM matchups WHERE
            ((champion = ? COLLATE NOCASE AND opponent = ? COLLATE NOCASE) OR
             (champion = ? COLLATE NOCASE AND opponent = ? COLLATE NOCASE))"""
        params = [champion, opponent, opponent, champion]
        if patch is not None:
            sql += " AND patch = ?"
            params.append(patch)
        rows = self.connection.execute(sql, params).fetchall()
        mirror = champion.casefold() == opponent.casefold()
        wins = sum(bool(win) if name.casefold() == champion.casefold() else not bool(win)
                   for name, _, win in rows) if not mirror else len(rows)
        samples = len(rows) * (2 if mirror else 1)
        return {"champion": champion, "opponent": opponent, "patch": patch,
                "matches": len(rows), "sample_size": samples, "wins": wins,
                "win_rate": 100 * wins / samples if samples else None,
                "note": "Observed game wins, not lane wins. Samples may be small or biased; no reliability claim."}


def main():
    parser = argparse.ArgumentParser(description="Query observed matchup game win rates")
    parser.add_argument("champion", nargs="?", help="Champion to query or filter when listing")
    parser.add_argument("opponent", nargs="?")
    parser.add_argument("--list", action="store_true", help="List stored pairs by game count")
    parser.add_argument("--min-games", type=int, default=1, help="Minimum games per listed pair (default: 1)")
    parser.add_argument("--limit", type=int, default=20, help="Maximum listed pairs (default: 20)")
    parser.add_argument("--patch", help="Major.minor patch, e.g. 16.20")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    if args.list:
        if args.opponent:
            parser.error("--list accepts at most one champion filter")
        if args.min_games < 1 or args.limit < 1:
            parser.error("--min-games and --limit must be positive")
    elif not args.champion or not args.opponent:
        parser.error("provide champion and opponent, or use --list")
    with MatchupDatabase(args.db) as db:
        if args.list:
            results = db.list_matchups(args.champion, args.patch, args.min_games, args.limit)
            print(json.dumps({"matchups": results, "returned": len(results),
                              "note": "No matching stored matchups." if not results else
                              "Sorted by game count. Win rates describe the first champion; samples may be small or biased."}, indent=2))
        else:
            print(json.dumps(db.win_rate(args.champion, args.opponent, args.patch), indent=2))


if __name__ == "__main__":
    main()
