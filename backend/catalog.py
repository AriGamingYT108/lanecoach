"""Public Data Dragon names and abilities; cached separately from credentials."""
import json
import hashlib
import re
from pathlib import Path

import requests

from .champion import get_champion, get_latest_version

CACHE = Path(__file__).parent / ".cache" / "catalog.json"


def clean_html(value):
    return re.sub(r"<[^>]+>", " ", value or "").strip()


class Catalog:
    def __init__(self, cache=CACHE):
        self.cache = Path(cache)
        self.data = {"version": None, "champions": {}, "items": {}, "runes": {}}
        self.reload()

    def reload(self):
        """Observe a public knowledge sync performed by another local process."""
        try:
            cached = json.loads(self.cache.read_text(encoding="utf-8"))
            if isinstance(cached, dict) and all(k in cached for k in self.data):
                self.data = cached
        except (OSError, ValueError):
            pass

    def refresh(self):
        version = get_latest_version()
        base = f"https://ddragon.leagueoflegends.com/cdn/{version}"
        def fetch(name):
            response = requests.get(f"{base}/data/en_US/{name}.json", timeout=10)
            response.raise_for_status()
            return response.json()
        champions = fetch("champion")["data"]
        items = fetch("item")["data"]
        runes = fetch("runesReforged")
        data = {"version": version,
                "champions": {c["id"]: {"id": c["id"], "name": c["name"], "title": c["title"],
                    "image": f"{base}/img/champion/{c['image']['full']}"} for c in champions.values()},
                "items": {str(i): {"name": item["name"], "image": f"{base}/img/item/{item['image']['full']}"}
                          for i, item in items.items()}, "runes": {}}
        for tree in runes:
            for slot in tree["slots"]:
                for rune in slot["runes"]:
                    data["runes"][str(rune["id"])] = {"name": rune["name"],
                        "image": "https://ddragon.leagueoflegends.com/cdn/img/" + rune["icon"]}
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache.with_suffix(".tmp")
        temporary.write_text(json.dumps(data), encoding="utf-8")
        temporary.replace(self.cache)
        self.data = data
        return {"version": version, "champions": len(data["champions"])}

    def resolve(self, name):
        for champion in self.data["champions"].values():
            if name.casefold() in {champion["name"].casefold(), champion["id"].casefold()}:
                return champion["id"]
        return name

    def asset(self, kind, identifier):
        """Cache only catalog-owned URLs, never arbitrary browser-supplied URLs."""
        if kind not in {"champions", "items", "runes"}:
            return None
        entry = self.data[kind].get(identifier)
        if not entry:
            return None
        url = entry["image"]
        if not url.startswith("https://ddragon.leagueoflegends.com/"):
            return None
        target = self.cache.parent / "assets" / (hashlib.sha256(url.encode()).hexdigest() + ".png")
        if not target.exists():
            response = requests.get(url, timeout=8, allow_redirects=False)
            if response.status_code != 200 or not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            # Concurrent identical asset requests are harmless, with atomic publication.
            from tempfile import NamedTemporaryFile
            with NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                temporary.write(response.content)
                temporary_path = Path(temporary.name)
            temporary_path.replace(target)
        return target

    def abilities(self, name, patch=None):
        version = self.data.get("version")
        if not version:
            return None
        if patch and not version.startswith(patch + "."):
            response = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10)
            response.raise_for_status()
            version = next((v for v in response.json() if v.startswith(patch + ".")), None)
            if not version:
                return None
        canonical = self.data["champions"].get(self.resolve(name), {}).get("name", name)
        digest = hashlib.sha256((version + canonical).encode()).hexdigest()[:24]
        detail_cache = self.cache.parent / ("abilities-" + digest + ".json")
        try:
            return json.loads(detail_cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        champion = get_champion(canonical, version=version)
        if not champion:
            return None
        result = {"name": champion["name"], "version": version,
                "passive": clean_html(champion["passive"]["description"]),
                "abilities": [{"key": key, "name": spell["name"], "description": clean_html(spell["description"])}
                              for key, spell in zip("QWER", champion["spells"])]}
        try:
            detail_cache.parent.mkdir(parents=True, exist_ok=True)
            detail_cache.write_text(json.dumps(result), encoding="utf-8")
        except OSError:
            pass
        return result
