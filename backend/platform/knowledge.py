"""Explicit coaching principles, labelled as authored guidance rather than statistics."""
ROLE_NOTES = {
    "TOP": ("Trading, waves and side lanes", "For top lane, compare range and available abilities before taking a trade. Practice last hits while respecting the enemy's threat range. Before recalling, consider whether the next wave will reach your tower or the enemy tower. Review whether your recall loses a large wave. Decide between side-lane pressure and joining your team using visible objectives and team positions. These are conditional practice principles, not a matchup-specific solution."),
    "JUNGLE": ("Flexible routing and objectives", "A jungle route depends on champion clear tools, lane priority, revealed enemy positions and the next objective. Plan a first clear direction, then adapt rather than promise a fixed path. Avoid a contested invade when nearby lanes cannot move. Before committing to a gank, compare the likely reward with farm and objective opportunity cost. Review the map before crossing the river. No exact camp timings, clear times or guaranteed gank paths are provided."),
    "MIDDLE": ("Mid pressure and roaming", "For mid lane, compare wave position, available abilities and escape routes before trading. Roam when you can do so without losing a large wave and when a realistic play exists. Missing enemy information changes the risk of pushing. Review whether a roam helped more than staying for farm and pressure. A pushed wave does not automatically justify a roam."),
    "BOTTOM": ("Farm, spacing and teamfights", "As the bot-lane carry, evaluate both opposing champions and both supports before trading. Track visible threats and stay within useful support range. In fights, prioritize a reachable target while preserving a safe position; do not force access to the enemy backline through dangerous terrain. Review missed last hits and deaths that prevented item progression. No ideal build is inferred from a few wins."),
    "UTILITY": ("Support pressure, vision and roams", "As support, connect vision and roams to the next team objective and the carry's ability to survive and collect the wave. Moving first is valuable only when the nearby wave and enemy threats allow it. Coordinate trades with the carry rather than entering alone. Review whether your vision could be placed safely and whether your roam left the carry exposed. These are general support principles, not exact ward coordinates."),
}


def seed_knowledge(store):
    for role, (title, body) in ROLE_NOTES.items():
        store.upsert_document({"id": "practice-" + role.lower(), "title": title, "body": body,
            "role": role, "champion": None, "patch": None, "source_url": None, "source_kind": "authored-practice"})
    store.upsert_document({"id": "practice-review", "title": "A repeatable improvement loop",
        "body": "Choose one measurable process goal per game. Review an early mistake in a replay, record what information was visible at the time, and compare alternative decisions. Final KDA and win/loss do not establish why a decision succeeded. Keep observations separate from guesses. Set realistic goals for farming, recall decisions, ability usage or objective preparation.",
        "role": None, "champion": None, "patch": None, "source_url": None, "source_kind": "authored-practice"})
