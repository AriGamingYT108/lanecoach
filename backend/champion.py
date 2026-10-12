import requests

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"


def get_latest_version():
    response = requests.get(VERSIONS_URL, timeout=10)
    response.raise_for_status()
    return response.json()[0]


def get_champion(champion_name, version=None):
    version = version or get_latest_version()

    # Get the list of champions
    champions_url = (
        f"https://ddragon.leagueoflegends.com/"
        f"cdn/{version}/data/en_US/champion.json"
    )

    response = requests.get(champions_url, timeout=10)
    response.raise_for_status()

    champions = response.json()["data"]

    # Find champion regardless of capitalization
    champion_id = None

    for champion in champions.values():
        if champion["name"].lower() == champion_name.lower():
            champion_id = champion["id"]
            break

    if champion_id is None:
        return None

    # Get detailed champion data
    detail_url = (
        f"https://ddragon.leagueoflegends.com/"
        f"cdn/{version}/data/en_US/champion/{champion_id}.json"
    )

    response = requests.get(detail_url, timeout=10)
    response.raise_for_status()

    return response.json()["data"][champion_id]


def print_champion(champion):
    print(f"\n{champion['name']} — {champion['title']}")
    print(f"Roles: {', '.join(champion['tags'])}")

    print("\nABILITIES")

    # Passive
    passive = champion["passive"]
    print(f"Passive: {passive['name']}")
    print(f"  {passive['description']}")

    # Q, W, E, R
    ability_keys = ["Q", "W", "E", "R"]

    for key, spell in zip(ability_keys, champion["spells"]):
        print(f"\n{key}: {spell['name']}")
        print(f"  {spell['description']}")


if __name__ == "__main__":
    name = input("Enter a champion: ")

    champion = get_champion(name)

    if champion:
        print_champion(champion)
    else:
        print("Champion not found.")
