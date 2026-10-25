from .version import app_version

SINGLE = {
    "view": "single",
    "updated_at": "2026-10-17T21:04:12+08:00",
    "watching": True,
    "proxied": False,
    "dry_run": False,
    "interval_seconds": 30,
    "types": ["A"],
    "addresses": {"A": "203.0.113.10"},
    "zones": [{"domain": "example.com", "names": ["example.com"]}],
    "history": [
        {
            "at": "2026-10-17T18:02:41+08:00",
            "name": "example.com",
            "type": "A",
            "before": "203.0.113.8",
            "after": "203.0.113.10",
        },
    ],
}

MULTI = {
    "view": "multi",
    "updated_at": "2026-10-17T21:04:12+08:00",
    "watching": True,
    "proxied": False,
    "dry_run": False,
    "interval_seconds": 30,
    "addresses": {"A": "203.0.113.10", "AAAA": "2001:db8:1::10"},
    "zones": [
        {"domain": "example.com", "names": ["wan1.example.com"]},
        {"domain": "example.net", "names": ["example.net"]},
    ],
    "history": [
        {
            "at": "2026-10-17T18:02:41+08:00",
            "name": "wan1.example.com",
            "type": "A",
            "before": "203.0.113.8",
            "after": "203.0.113.10",
        },
        {
            "at": "2026-10-17T18:02:41+08:00",
            "name": "example.net",
            "type": "A",
            "before": "203.0.113.8",
            "after": "203.0.113.10",
        },
        {
            "at": "2026-10-12T07:40:18+08:00",
            "name": "example.net",
            "type": "AAAA",
            "before": "2001:db8:1::8",
            "after": "2001:db8:1::10",
        },
    ],
}


def snapshot(view):
    data = dict(MULTI if view == "multi" else SINGLE)
    data["version"] = app_version()
    return data
