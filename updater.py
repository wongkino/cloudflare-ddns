#!/usr/bin/env python3
"""Point configured names at this host's current public IPv4 and IPv6.

The host's default route is the active WAN. When that path fails over, the
next check sees the new address and updates every name in A_RECORDS.
RECORD_TYPES chooses A, AAAA, or both. A records follow the public IPv4, and
AAAA records follow the public IPv6. A selected family is left unchanged when
that public address cannot be read.
"""

import errno
import ipaddress
import json
import os
import signal
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

CLOUDFLARE_CTX = ssl.create_default_context()
STOP = False
IPV4_SOURCES = (
    "https://api4.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://v4.ident.me",
)
IPV6_SOURCES = (
    "https://api6.ipify.org",
    "https://ipv6.icanhazip.com",
    "https://v6.ident.me",
)
CGNAT = ipaddress.ip_network("100.64.0.0/10")
# Ranges that must not be published, including ones older Python builds
# still treat as global.
IPV6_BLOCKED = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "::/128",
        "::1/128",
        "::ffff:0:0/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "100::/64",
        "2001::/32",
        "2001:2::/48",
        "2001:10::/28",
        "2001:20::/28",
        "2001:db8::/32",
        "2002::/16",
        "3fff::/20",
        "fc00::/7",
        "fe80::/10",
        "fec0::/10",
        "ff00::/8",
    )
)
# 整段網路或這個位址族不可用時才停止後續查詢站。
# 單一主機不可達（EHOSTUNREACH）要改試下一個來源。
FATAL_UNREACHABLE = {
    errno.ENETUNREACH,
    errno.EAFNOSUPPORT,
    errno.EADDRNOTAVAIL,
}


def log(message):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp} {message}", flush=True)


def env_int(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise SystemExit(f"{name} 必須是整數")
    if value <= 0:
        raise SystemExit(f"{name} 必須大於 0")
    return value


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"缺少環境變數 {name}")
    return value


def env_bool(name, default=False):
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes"}:
        return True
    if raw in {"0", "false", "no"}:
        return False
    raise SystemExit(f"{name} 只能是 true 或 false")


def apprise_urls(raw):
    urls = []
    for part in raw.split():
        parsed = urllib.parse.urlparse(part)
        if parsed.scheme in {"http", "https"} and parsed.path.startswith("/notify/"):
            token = parsed.path[len("/notify/") :].strip("/")
            scheme = "apprises" if parsed.scheme == "https" else "apprise"
            urls.append(f"{scheme}://{parsed.netloc}/{token}")
        elif part:
            urls.append(part)
    return urls


def notice_text(ipv4, ipv6, changes):
    lines = []
    if ipv4:
        lines.append(f"Current public IPv4: {ipv4}")
    if ipv6:
        lines.append(f"Current public IPv6: {ipv6}")
    for change in changes:
        before = change["before"] or "(new record)"
        lines.append(f"{change['name']} {change['type']}: {before} → {change['after']}")
    return "IP changed", "\n".join(lines)


def same_ip(left, right):
    try:
        return ipaddress.ip_address(str(left).strip()) == ipaddress.ip_address(str(right).strip())
    except ValueError:
        return False


def cname_target(records):
    for record in records:
        if record.get("type") == "CNAME":
            return record.get("content")
    return None


def send_notice(urls, title, body):
    if not urls:
        return
    import apprise

    notifier = apprise.Apprise()
    added = False
    for url in urls:
        if notifier.add(url):
            added = True
        else:
            log("有一個 Apprise 網址無法使用，已略過")
    if not added:
        log("沒有可用的 Apprise 網址，通知未發送")
        return
    if notifier.notify(title=title, body=body):
        log("已發送 IP 變更通知")
    else:
        log("Apprise 通知發送失敗")


def record_names(raw, domain):
    names = []
    for part in raw.replace("\n", ",").split(","):
        part = part.strip().rstrip(".").lower()
        if not part:
            continue
        if part == "@":
            name = domain
        elif "." not in part:
            name = f"{part}.{domain}"
        else:
            name = part
        if name != domain and not name.endswith("." + domain):
            raise SystemExit(f"{name} 不在 {domain} 這個 zone")
        if name not in names:
            names.append(name)
    if not names:
        raise SystemExit("A_RECORDS 至少要有一個名稱")
    return names


def record_types(raw):
    text = (raw or "").strip()
    if not text:
        return ["A", "AAAA"]
    selected = []
    for part in text.replace("，", ",").split(","):
        kind = part.strip().upper()
        if not kind:
            continue
        if kind not in {"A", "AAAA"}:
            raise SystemExit("RECORD_TYPES 只能是 A、AAAA，或 A,AAAA")
        if kind not in selected:
            selected.append(kind)
    if not selected:
        raise SystemExit("RECORD_TYPES 至少要有 A 或 AAAA")
    return [kind for kind in ("A", "AAAA") if kind in selected]


def is_public_ipv4(value):
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return (
        address.version == 4
        and address not in CGNAT
        and not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
    )


def is_public_ipv6(value):
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    if address.version != 6 or address.ipv4_mapped is not None:
        return False
    if any(address in network for network in IPV6_BLOCKED):
        return False
    return (
        not address.is_private
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_multicast
        and not address.is_reserved
        and not address.is_unspecified
        and not address.is_site_local
    )


def unreachable(error):
    current = error
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, OSError) and current.errno in FATAL_UNREACHABLE:
            return True
        current = getattr(current, "reason", None)
    text = str(error).lower()
    markers = (
        "network is unreachable",
        "network unreachable",
        "address family not supported",
        "address family for hostname not supported",
        "can't assign requested address",
        "cannot assign requested address",
    )
    return any(marker in text for marker in markers)


def request_json(url, method="GET", payload=None, headers=None, timeout=20):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, context=CLOUDFLARE_CTX, timeout=timeout) as response:
            body = response.read().decode()
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"raw": raw[:300]}
        return error.code, parsed


def public_address(sources, accept, timeout):
    errors = []
    for url in sources:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "cloudflare-ddns"})
            with urllib.request.urlopen(request, context=CLOUDFLARE_CTX, timeout=timeout) as response:
                body = response.read().decode().strip()
        except Exception as error:
            errors.append(f"{url}: {error}")
            if unreachable(error):
                break
            continue
        if accept(body):
            return str(ipaddress.ip_address(body.strip()))
        errors.append(f"{url}: 回應不是公網位址 ({body[:80]})")
    raise RuntimeError("；".join(errors))


def public_ipv4():
    try:
        return public_address(IPV4_SOURCES, is_public_ipv4, 10)
    except RuntimeError as error:
        raise RuntimeError(f"查不到公網 IPv4；{error}") from error


def public_ipv6():
    try:
        return public_address(IPV6_SOURCES, is_public_ipv6, 5)
    except RuntimeError as error:
        raise RuntimeError(f"查不到公網 IPv6；{error}") from error


class Cloudflare:
    def __init__(self, token, zone_id, domain, ttl, dry_run, proxied=False):
        self.token = token
        self.zone_id = zone_id
        self.domain = domain
        self.ttl = ttl
        self.dry_run = dry_run
        self.proxied = proxied
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _call(self, path, method="GET", payload=None):
        status, body = request_json(
            "https://api.cloudflare.com/client/v4" + path,
            method,
            payload,
            self.headers,
        )
        if not body.get("success", status < 400):
            errors = body.get("errors") or body.get("raw") or body
            raise RuntimeError(f"Cloudflare {method} {path} 失敗 ({status}): {errors}")
        return body

    def resolve_zone(self):
        if self.zone_id:
            return self.zone_id
        query = urllib.parse.urlencode({"name": self.domain})
        zones = self._call(f"/zones?{query}").get("result") or []
        if not zones:
            raise RuntimeError(f"找不到 Cloudflare zone {self.domain}")
        self.zone_id = zones[0]["id"]
        return self.zone_id

    def list_records(self):
        records = []
        page = 1
        while True:
            query = urllib.parse.urlencode({"per_page": 100, "page": page})
            body = self._call(f"/zones/{self.zone_id}/dns_records?{query}")
            records.extend(body.get("result") or [])
            info = body.get("result_info") or {}
            if page >= info.get("total_pages", 1):
                return records
            page += 1

    def ensure_record(self, records, name, ip, record_type):
        owned = [record for record in records if record.get("name") == name]
        previous_cname = cname_target(owned)
        for record in list(owned):
            if record.get("type") != "CNAME":
                continue
            self._delete(record)
            owned.remove(record)
            if record in records:
                records.remove(record)
        matches = [record for record in owned if record.get("type") == record_type]
        if not matches:
            self._create(name, record_type, ip)
            return {"name": name, "type": record_type, "before": previous_cname, "after": ip}

        def keep_score(record):
            if not same_ip(record.get("content"), ip):
                return 0
            if bool(record.get("proxied")) != self.proxied or record.get("ttl") != self.ttl:
                return 1
            return 2

        primary = max(matches, key=keep_score)
        previous = primary.get("content")
        if (
            not same_ip(previous, ip)
            or bool(primary.get("proxied")) != self.proxied
            or primary.get("ttl") != self.ttl
        ):
            self._patch(primary, name, record_type, ip)
        else:
            log(f"{name} {record_type} 已是 {ip}")
        for extra in matches:
            if extra is primary:
                continue
            self._delete(extra)
            if extra in records:
                records.remove(extra)
        if not same_ip(previous, ip):
            return {"name": name, "type": record_type, "before": previous, "after": ip}
        return None

    def _payload(self, name, record_type, ip):
        return {
            "type": record_type,
            "name": name,
            "content": ip,
            "ttl": self.ttl,
            "proxied": self.proxied,
        }

    def _write(self, method, path, name, record_type, ip):
        try:
            self._call(path, method, self._payload(name, record_type, ip))
        except RuntimeError as error:
            if self.ttl == 1 or "ttl" not in str(error).lower():
                raise
            log("這個 zone 不接受指定的 TTL，改用 Cloudflare 自動 TTL")
            self.ttl = 1
            self._call(path, method, self._payload(name, record_type, ip))

    def _create(self, name, record_type, ip):
        log(f"新增 {name} {record_type} {ip}")
        if not self.dry_run:
            self._write("POST", f"/zones/{self.zone_id}/dns_records", name, record_type, ip)

    def _patch(self, record, name, record_type, ip):
        previous = record.get("content")
        proxy_changed = bool(record.get("proxied")) != self.proxied
        if not same_ip(previous, ip):
            log(f"更新 {name} {record_type} {previous} -> {ip}")
        elif proxy_changed and record.get("ttl") != self.ttl:
            state = "橙雲" if self.proxied else "灰雲"
            log(f"更新 {name} {record_type} 為{state}，TTL 為 {self.ttl}")
        elif proxy_changed:
            state = "橙雲" if self.proxied else "灰雲"
            log(f"更新 {name} {record_type} 為{state}")
        else:
            log(f"更新 {name} {record_type} 的 TTL 為 {self.ttl}")
        if not self.dry_run:
            self._write(
                "PATCH",
                f"/zones/{self.zone_id}/dns_records/{record['id']}",
                name,
                record_type,
                ip,
            )

    def _delete(self, record):
        log(f"刪除 {record.get('name')} {record.get('type')} {record.get('content')}")
        if not self.dry_run:
            self._call(f"/zones/{self.zone_id}/dns_records/{record['id']}", "DELETE")


def lookup_family(family, record_type, func):
    try:
        address = func()
    except RuntimeError as error:
        log(f"{error}，{record_type} 紀錄維持原狀")
        return None
    log(f"目前公網 {family} {address}")
    return address


def addresses_match(found, applied, types):
    for kind in types:
        current = found.get(kind)
        if current is None or not same_ip(applied.get(kind), current):
            return False
    return True


def sync_once(cloudflare, names, urls, dry_run, types, state, recheck_seconds):
    families = {"A": ("IPv4", public_ipv4), "AAAA": ("IPv6", public_ipv6)}
    found = {}
    for kind in types:
        family, func = families[kind]
        found[kind] = lookup_family(family, kind, func)
    if all(found[kind] is None for kind in types):
        labels = " 或 ".join("IPv4" if kind == "A" else "IPv6" for kind in types)
        raise RuntimeError(f"查不到公網 {labels}")
    now = time.time()
    if (
        not dry_run
        and now - state["checked_at"] < recheck_seconds
        and addresses_match(found, state["applied"], types)
    ):
        log("位址沒有改變，本輪不查 Cloudflare")
        return
    cloudflare.resolve_zone()
    records = cloudflare.list_records()
    changes = []
    for name in names:
        for kind in types:
            address = found[kind]
            if address is None:
                continue
            change = cloudflare.ensure_record(records, name, address, kind)
            if change:
                changes.append(change)
    if not dry_run:
        for kind in types:
            if found[kind] is not None:
                state["applied"][kind] = found[kind]
        state["checked_at"] = now
    if not changes:
        return
    title, body = notice_text(found.get("A"), found.get("AAAA"), changes)
    if dry_run:
        log(f"演練不會發送通知：{title} {body.replace(chr(10), '；')}")
        return
    try:
        send_notice(urls, title, body)
    except Exception as error:
        log(f"Apprise 通知失敗：{error}")


def handle_stop(signum, _frame):
    global STOP
    STOP = True
    log(f"收到停止訊號 {signum}")


def self_test():
    assert is_public_ipv4("112.118.9.35")
    assert is_public_ipv4(" 220.246.129.116\n")
    assert not is_public_ipv4("10.0.0.1")
    assert not is_public_ipv4("100.64.1.1")
    assert not is_public_ipv4("not-an-ip")
    assert is_public_ipv6("2606:4700:4700::1111")
    assert is_public_ipv6(" 2001:4860:4860::8888\n")
    assert not is_public_ipv6("fe80::1")
    assert not is_public_ipv6("fd12:3456:789a::1")
    assert not is_public_ipv6("::1")
    assert not is_public_ipv6("2001:db8::1")
    assert not is_public_ipv6("2001:20::1")
    assert not is_public_ipv6("2002:c000:201::")
    assert not is_public_ipv6("::ffff:8.8.8.8")
    assert not is_public_ipv6("1.2.3.4")
    assert not is_public_ipv6("not-an-ip")
    assert same_ip("2001:db8::1", "2001:0db8:0000::0001")
    assert not same_ip("2001:db8::1", "2001:db8::2")
    assert unreachable(OSError(errno.ENETUNREACH, "network unreachable"))
    assert unreachable(urllib.error.URLError(OSError(errno.ENETUNREACH, "network is unreachable")))
    assert unreachable(OSError(errno.EAFNOSUPPORT, "address family not supported"))
    assert unreachable(OSError(errno.EADDRNOTAVAIL, "can't assign requested address"))
    assert not unreachable(OSError(errno.EHOSTUNREACH, "no route to host"))
    assert not unreachable(TimeoutError("timed out"))
    assert record_types("") == ["A", "AAAA"]
    assert record_types("a") == ["A"]
    assert record_types("aaaa") == ["AAAA"]
    assert record_types("AAAA, A") == ["A", "AAAA"]
    try:
        record_types("CNAME")
    except SystemExit:
        pass
    else:
        raise AssertionError("其他紀錄類型應被拒絕")
    assert record_names("@, vpn ,example.com", "example.com") == [
        "example.com",
        "vpn.example.com",
    ]
    try:
        record_names("other.net", "example.com")
    except SystemExit:
        pass
    else:
        raise AssertionError("其他 zone 的名稱應被拒絕")
    assert apprise_urls("discord://a/b tgram://c/d") == ["discord://a/b", "tgram://c/d"]
    assert apprise_urls("https://apprise.example.com/notify/cloudflare") == [
        "apprises://apprise.example.com/cloudflare"
    ]
    assert apprise_urls("") == []
    title, body = notice_text(
        "1.2.3.4",
        "2606:4700:4700::1111",
        [
            {"name": "wan1.example.com", "type": "A", "before": "9.9.9.9", "after": "1.2.3.4"},
            {
                "name": "wan1.example.com",
                "type": "AAAA",
                "before": "2001:db8::1",
                "after": "2606:4700:4700::1111",
            },
        ],
    )
    assert title == "IP changed"
    assert "Current public IPv4: 1.2.3.4" in body
    assert "Current public IPv6: 2606:4700:4700::1111" in body
    assert "wan1.example.com A: 9.9.9.9 → 1.2.3.4" in body
    assert "wan1.example.com AAAA: 2001:db8::1 → 2606:4700:4700::1111" in body
    cloudflare = Cloudflare("token", "zone", "example.com", 60, True)
    records = [
        {
            "id": "1",
            "name": "wan1.example.com",
            "type": "CNAME",
            "content": "target.example",
            "ttl": 60,
            "proxied": False,
        },
        {
            "id": "2",
            "name": "nas.example.com",
            "type": "A",
            "content": "1.1.1.1",
            "ttl": 60,
            "proxied": False,
        },
        {
            "id": "3",
            "name": "nas.example.com",
            "type": "AAAA",
            "content": "2001:db8::1",
            "ttl": 1,
            "proxied": True,
        },
        {
            "id": "4",
            "name": "nas.example.com",
            "type": "AAAA",
            "content": "2001:db8::2",
            "ttl": 60,
            "proxied": False,
        },
    ]
    created = cloudflare.ensure_record(records, "wan1.example.com", "203.0.113.5", "A")
    assert created == {
        "name": "wan1.example.com",
        "type": "A",
        "before": "target.example",
        "after": "203.0.113.5",
    }
    assert all(record.get("type") != "CNAME" for record in records)
    created_aaaa = cloudflare.ensure_record(records, "wan1.example.com", "2606:4700:4700::1111", "AAAA")
    assert created_aaaa["before"] is None
    assert created_aaaa["type"] == "AAAA"
    assert cloudflare.ensure_record(records, "nas.example.com", "1.1.1.1", "A") is None
    updated = cloudflare.ensure_record(records, "nas.example.com", "2606:4700:4700::1111", "AAAA")
    assert updated["before"] == "2001:db8::1"
    assert updated["after"] == "2606:4700:4700::1111"
    assert [record["id"] for record in records if record.get("type") == "AAAA"] == ["3"]
    same_form = [
        {
            "id": "5",
            "name": "nas.example.com",
            "type": "AAAA",
            "content": "2606:4700:4700:0000:0000:0000:0000:1111",
            "ttl": 60,
            "proxied": False,
        }
    ]
    assert cloudflare.ensure_record(same_form, "nas.example.com", "2606:4700:4700::1111", "AAAA") is None
    keep_match = [
        {
            "id": "6",
            "name": "vpn.example.com",
            "type": "AAAA",
            "content": "2001:db8::9",
            "ttl": 60,
            "proxied": False,
        },
        {
            "id": "7",
            "name": "vpn.example.com",
            "type": "AAAA",
            "content": "2606:4700:4700::1111",
            "ttl": 60,
            "proxied": False,
        },
    ]
    assert cloudflare.ensure_record(keep_match, "vpn.example.com", "2606:4700:4700::1111", "AAAA") is None
    assert [record["id"] for record in keep_match] == ["7"]
    fix_flags = [
        {
            "id": "8",
            "name": "vpn2.example.com",
            "type": "A",
            "content": "9.9.9.9",
            "ttl": 60,
            "proxied": False,
        },
        {
            "id": "9",
            "name": "vpn2.example.com",
            "type": "A",
            "content": "203.0.113.5",
            "ttl": 1,
            "proxied": True,
        },
    ]
    assert cloudflare.ensure_record(fix_flags, "vpn2.example.com", "203.0.113.5", "A") is None
    assert [record["id"] for record in fix_flags] == ["9"]
    orange = Cloudflare("token", "zone", "example.com", 60, True, proxied=True)
    stay_orange = [
        {
            "id": "10",
            "name": "www.example.com",
            "type": "A",
            "content": "203.0.113.5",
            "ttl": 60,
            "proxied": True,
        }
    ]
    assert orange.ensure_record(stay_orange, "www.example.com", "203.0.113.5", "A") is None
    assert stay_orange[0]["proxied"] is True
    turn_orange = [
        {
            "id": "11",
            "name": "www.example.com",
            "type": "A",
            "content": "203.0.113.5",
            "ttl": 60,
            "proxied": False,
        }
    ]
    assert orange.ensure_record(turn_orange, "www.example.com", "203.0.113.5", "A") is None
    assert [record["id"] for record in turn_orange] == ["11"]
    assert addresses_match(
        {"A": "1.2.3.4", "AAAA": "2606:4700:4700::1111"},
        {"A": "1.2.3.4", "AAAA": "2606:4700:4700:0000:0000:0000:0000:1111"},
        ["A", "AAAA"],
    )
    assert not addresses_match({"A": "1.2.3.4"}, {"A": "1.2.3.5"}, ["A"])
    assert not addresses_match({"A": "1.2.3.4"}, {}, ["A"])
    assert not addresses_match(
        {"A": "1.2.3.4", "AAAA": None},
        {"A": "1.2.3.4", "AAAA": "2001:db8::1"},
        ["A", "AAAA"],
    )
    log("自我測試通過")


def main():
    if os.environ.get("SELF_TEST") == "1":
        self_test()
        return
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    domain = required("DOMAIN").rstrip(".").lower()
    names = record_names(os.environ.get("A_RECORDS", domain), domain)
    types = record_types(os.environ.get("RECORD_TYPES", ""))
    interval = env_int("INTERVAL_SECONDS", 30)
    recheck = env_int("RECHECK_SECONDS", 3600)
    dry_run = env_bool("DRY_RUN")
    proxied = env_bool("CF_PROXIED")
    urls = apprise_urls(os.environ.get("APPRISE_URLS", ""))
    cloudflare = Cloudflare(
        required("CLOUDFLARE_API_TOKEN"),
        os.environ.get("CLOUDFLARE_ZONE_ID", "").strip(),
        domain,
        env_int("DNS_TTL", 60),
        dry_run,
        proxied,
    )
    log(
        f"開始監視 {', '.join(names)} 的 {' 與 '.join(types)}，每 {interval} 秒檢查一次"
        + ("，橙雲" if proxied else "，灰雲")
        + ("（演練，不會改 DNS）" if dry_run else "")
    )
    if urls:
        log(f"IP 改變時會經 Apprise 發送通知（{len(urls)} 個目的地）")
    else:
        log("未設定 APPRISE_URLS，IP 改變時不會發送通知")
    state = {"applied": {}, "checked_at": 0.0}
    while not STOP:
        started = time.time()
        try:
            sync_once(cloudflare, names, urls, dry_run, types, state, recheck)
            with open("/tmp/healthy", "w", encoding="utf-8") as handle:
                handle.write(str(started))
        except Exception as error:
            log(f"這次檢查失敗，DNS 保持原狀：{error}")
        remaining = interval - (time.time() - started)
        while remaining > 0 and not STOP:
            time.sleep(min(1, remaining))
            remaining = interval - (time.time() - started)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
