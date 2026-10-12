"""Shared Riot transport with bounded retries and sanitized errors."""
import math
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


class RiotAPIError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class RiotClient:
    def __init__(self, region="americas", api_key=None, session=None, retries=3, sleep=time.sleep):
        if region not in {"americas", "europe", "asia", "sea"}:
            raise ValueError("Region must be americas, europe, asia, or sea")
        if retries < 0:
            raise ValueError("retries must be nonnegative")
        load_dotenv(Path(__file__).with_name(".env"))
        self._api_key = api_key or os.getenv("RIOT_API_KEY")
        if not self._api_key:
            raise RiotAPIError("Set RIOT_API_KEY in backend/.env")
        self.base_url = f"https://{region}.api.riotgames.com"
        self.session = session or requests.Session()
        self.retries, self.sleep = retries, sleep
        self._retry_not_before = 0

    def get(self, path, params=None):
        for attempt in range(self.retries + 1):
            remaining = self._retry_not_before - time.monotonic()
            if remaining > 0:
                self.sleep(remaining)
                self._retry_not_before = 0
            try:
                response = self.session.get(self.base_url + path, params=params,
                    headers={"X-Riot-Token": self._api_key}, timeout=10, allow_redirects=False)
            except requests.RequestException:
                if attempt == self.retries:
                    raise RiotAPIError("Riot request failed after retries") from None
                self.sleep(2 ** attempt)
                continue
            status = response.status_code
            if status == 200:
                try:
                    return response.json()
                except ValueError:
                    raise RiotAPIError("Riot returned invalid JSON", status) from None
            if status == 429 or 500 <= status < 600:
                delay = 2 ** attempt
                if status == 429:
                    try:
                        delay = float(response.headers.get("Retry-After", 1))
                        if not math.isfinite(delay) or delay < 0:
                            delay = 1
                    except (TypeError, ValueError):
                        delay = 1
                    self._retry_not_before = time.monotonic() + delay
                if attempt < self.retries:
                    if status != 429:
                        self.sleep(delay)
                    continue
            raise RiotAPIError(f"Riot API returned HTTP {status}", status)
