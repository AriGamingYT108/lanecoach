"""Optional live API smoke check, safe to import."""
import os
from pathlib import Path
import requests
from dotenv import load_dotenv


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    key = os.getenv("RIOT_API_KEY")
    if not key:
        print("Set RIOT_API_KEY in backend/.env")
        return 1
    try:
        response = requests.get("https://na1.api.riotgames.com/lol/status/v4/platform-data",
            headers={"X-Riot-Token": key}, timeout=10, allow_redirects=False)
    except requests.RequestException:
        print("Status request failed")
        return 1
    print("Status:", response.status_code)
    return 0 if response.status_code == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
