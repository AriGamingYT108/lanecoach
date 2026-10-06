import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("RIOT_API_KEY")

print("Key loaded:", API_KEY is not None)
print("Key starts correctly:", API_KEY.startswith("RGAPI-") if API_KEY else False)
print("Key length:", len(API_KEY) if API_KEY else 0)

API_KEY = os.getenv("RIOT_API_KEY")

url = "https://na1.api.riotgames.com/lol/status/v4/platform-data"

headers = {
    "X-Riot-Token": API_KEY
}

response = requests.get(url, headers=headers)

print("Status:", response.status_code)
print(response.json())