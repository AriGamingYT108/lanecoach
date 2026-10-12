"""Observed matchup summaries with explicit denominators and data provenance."""
from collections import Counter
from statistics import mean

from .timeline import numeric


def average(values):
    values = [v for v in values if numeric(v)]
    return {"value": round(mean(values), 2) if values else None, "samples": len(values)}


def orient(record, champion):
    reverse = record["champion"].casefold() != champion.casefold()
    result = dict(record)
    if reverse:
        for key in list(record):
            if key.startswith("champion_") and key != "champion_win":
                suffix = key[len("champion_"):]
                result[key] = record.get("opponent_" + suffix)
                result["opponent_" + suffix] = record[key]
        result["champion"], result["opponent"] = record["opponent"], record["champion"]
        result["champion_win"] = not record["champion_win"]
    return result


def side_stats(records, prefix):
    result = {metric: average([r.get(f"{prefix}_{metric}") for r in records]) for metric in ("cs", "gold")}
    for index, metric in enumerate(("kills", "deaths", "assists")):
        result[metric] = average([r.get(f"{prefix}_kda", [None] * 3)[index] for r in records])
    result["cs_per_minute"] = average([r[f"{prefix}_cs"] / (r["game_duration"] / 60)
        for r in records if numeric(r.get(f"{prefix}_cs")) and numeric(r.get("game_duration")) and r["game_duration"] > 0])
    for metric in ("items", "runes"):
        combinations = Counter(tuple(r.get(f"{prefix}_{metric}") or []) for r in records if r.get(f"{prefix}_{metric}"))
        result[metric] = [{"ids": list(ids), "games": count} for ids, count in combinations.most_common(5)]
    return result


def build_report(db, champion, opponent, patch=None):
    raw = db.matchup_records(champion, opponent, patch)
    mirror = champion.casefold() == opponent.casefold()
    records = [orient(r, champion) for r in raw]
    stats = db.win_rate(champion, opponent, patch)
    timeline_rows = []
    matches = []
    for original, record in zip(raw, records):
        timeline = db.get_timeline(record["match_id"])
        if timeline:
            reverse = original["champion"].casefold() != champion.casefold()
            # Cached timeline orientation is always original blue/red, including legacy records.
            timeline_rows.append((timeline, reverse))
        matches.append({**record, "has_timeline": bool(timeline)})
    lane = {}
    for minute in ("10", "15"):
        deltas = {"gold": [], "cs": []}
        for timeline, reverse in timeline_rows:
            snapshot = timeline.get("snapshots", {}).get(minute)
            if not snapshot:
                continue
            for metric in deltas:
                first, second = snapshot.get(f"champion_{metric}"), snapshot.get(f"opponent_{metric}")
                if numeric(first) and numeric(second):
                    deltas[metric].append((second - first) if reverse else (first - second))
        lane[minute] = {metric + "_difference": average(values) for metric, values in deltas.items()}
    warnings = ["Game outcomes are not lane outcomes. Selected-player data is biased and rank is not recorded.",
                "Final inventory shows what players finished with, not purchase order or a recommended build."]
    if len(records) < 30:
        warnings.append(f"Only {len(records)} unique games: treat these results as examples, not a reliable matchup estimate.")
    if not timeline_rows:
        warnings.append("No timeline evidence yet. Fetch timelines to compare early gold and CS.")
    if mirror:
        warnings.append("Mirror matchup: overall win rate is necessarily 50%; side summaries describe blue versus red.")
    patch_counts = Counter(r.get("patch_major_minor", ".".join(r["patch"].split(".")[:2])) for r in records)
    return {"summary": stats, "champion_stats": side_stats(records, "champion"),
            "opponent_stats": side_stats(records, "opponent"), "timeline": lane,
            "timeline_matches": len(timeline_rows), "patches": dict(patch_counts),
            "warnings": warnings, "matches": matches[:100], "matches_returned": min(len(matches), 100),
            "observations": observations(stats, lane, len(timeline_rows))}


def observations(summary, lane, timeline_count):
    count = summary["matches"]
    if not count:
        return ["No recorded games for this pair. Collect ranked games from players who use either champion."]
    result = [f"{summary['champion']} won {summary['wins']} of {summary['sample_size']} recorded champion appearances."]
    for metric, label in (("gold", "gold"), ("cs", "CS")):
        stat = lane["10"][metric + "_difference"]
        if stat["value"] is not None:
            result.append(f"At the last available frame at or shortly before 10 minutes, the average {label} difference was {stat['value']:+g} across {stat['samples']} games.")
    result.append("Review deaths, recall timing, and missed farm in replays; totals alone do not identify the cause of a lead.")
    return result


def match_detail(db, match_id):
    record = db.get_matchup(match_id)
    if record is None:
        return None
    return {"match": record, "timeline": db.get_timeline(match_id)}
