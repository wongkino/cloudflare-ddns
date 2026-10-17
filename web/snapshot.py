import json
import os
import threading
from datetime import datetime

LOCK = threading.Lock()
LIMIT = 100


def path():
    return os.environ.get("WEB_DATA", "/tmp/cloudflare-ddns.json")


def empty():
    return {
        "view": "single",
        "updated_at": None,
        "watching": False,
        "proxied": False,
        "dry_run": False,
        "interval_seconds": 30,
        "types": ["A", "AAAA"],
        "addresses": {},
        "zones": [],
        "history": [],
    }


def load():
    try:
        with open(path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return empty()
    if not isinstance(data, dict):
        return empty()
    base = empty()
    base.update({key: data.get(key, base[key]) for key in base})
    return base


def _zones(zones):
    return [{"domain": zone["domain"], "names": list(zone["names"])} for zone in zones]


def _write(data):
    folder = os.path.dirname(path())
    if folder:
        os.makedirs(folder, exist_ok=True)
    temporary = path() + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False)
    os.replace(temporary, path())


def configure(zones, types, proxied, dry_run, interval):
    with LOCK:
        data = load()
        data["proxied"] = bool(proxied)
        data["dry_run"] = bool(dry_run)
        data["interval_seconds"] = interval
        data["types"] = list(types)
        data["view"] = "single" if len(zones) <= 1 else "multi"
        data["zones"] = _zones(zones)
        _write(data)
        return data


def record(zones, types, found, changes, dry_run, proxied, interval):
    with LOCK:
        data = load()
        data["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        data["watching"] = True
        data["proxied"] = bool(proxied)
        data["dry_run"] = bool(dry_run)
        data["interval_seconds"] = interval
        data["types"] = list(types)
        data["view"] = "single" if len(zones) <= 1 else "multi"
        data["addresses"] = {
            kind: found.get(kind) for kind in types if found.get(kind)
        }
        data["zones"] = _zones(zones)
        if changes and not dry_run:
            stamped = [
                {
                    "at": data["updated_at"],
                    "name": change["name"],
                    "type": change["type"],
                    "before": change.get("before"),
                    "after": change.get("after"),
                }
                for change in changes
            ]
            data["history"] = (stamped + list(data.get("history") or []))[:LIMIT]
        _write(data)
        return data
