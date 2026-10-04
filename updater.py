#!/usr/bin/env python3
"""Point configured A records at this host's current public IPv4.

The host's default route is the active WAN. When that path fails over, the
next check sees the new address and updates every name in A_RECORDS. DNS is
left unchanged when the public address cannot be read.
"""

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
IP_SOURCES = (
    "https://api4.ipify.org",
    "https://ipv4.icanhazip.com",
    "https://v4.ident.me",
)
CGNAT = ipaddress.ip_network("100.64.0.0/10")


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


def notice_text(address, changes):
    lines = [f"Current public IP: {address}"]
    for change in changes:
        before = change["before"] or "(new record)"
        lines.append(f"{change['name']}: {before} → {change['after']}")
    return "IP changed", "\n".join(lines)


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


def public_ipv4():
    errors = []
    for url in IP_SOURCES:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "wongkino-apex-dns"})
            with urllib.request.urlopen(request, context=CLOUDFLARE_CTX, timeout=10) as response:
                body = response.read().decode().strip()
        except Exception as error:
            errors.append(f"{url}: {error}")
            continue
        if is_public_ipv4(body):
            return body
        errors.append(f"{url}: 回應不是公網 IPv4 ({body[:80]})")
    raise RuntimeError("查不到公網 IPv4；" + "；".join(errors))


class Cloudflare:
    def __init__(self, token, zone_id, domain, ttl, dry_run):
        self.token = token
        self.zone_id = zone_id
        self.domain = domain
        self.ttl = ttl
        self.dry_run = dry_run
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

    def ensure_a(self, records, name, ip):
        owned = [record for record in records if record.get("name") == name]
        for record in owned:
            if record.get("type") == "CNAME":
                self._delete(record)
        addresses = [record for record in owned if record.get("type") == "A"]
        if not addresses:
            self._create(name, ip)
            previous = cname_target(owned)
            return {"name": name, "before": previous, "after": ip}
        primary = addresses[0]
        previous = primary.get("content")
        if previous != ip or primary.get("proxied") or primary.get("ttl") != self.ttl:
            self._patch(primary, name, ip)
        else:
            log(f"{name} 已是 {ip}")
        for extra in addresses[1:]:
            self._delete(extra)
        if previous != ip:
            return {"name": name, "before": previous, "after": ip}
        return None

    def _payload(self, name, ip):
        return {"type": "A", "name": name, "content": ip, "ttl": self.ttl, "proxied": False}

    def _write(self, method, path, name, ip):
        try:
            self._call(path, method, self._payload(name, ip))
        except RuntimeError as error:
            if self.ttl == 1 or "ttl" not in str(error).lower():
                raise
            log("這個 zone 不接受指定的 TTL，改用 Cloudflare 自動 TTL")
            self.ttl = 1
            self._call(path, method, self._payload(name, ip))

    def _create(self, name, ip):
        log(f"新增 {name} A {ip}")
        if not self.dry_run:
            self._write("POST", f"/zones/{self.zone_id}/dns_records", name, ip)

    def _patch(self, record, name, ip):
        previous = record.get("content")
        if previous == ip:
            log(f"更新 {name} 的 TTL 為 {self.ttl}")
        else:
            log(f"更新 {name} {previous} -> {ip}")
        if not self.dry_run:
            self._write("PATCH", f"/zones/{self.zone_id}/dns_records/{record['id']}", name, ip)

    def _delete(self, record):
        log(f"刪除 {record.get('name')} {record.get('type')} {record.get('content')}")
        if not self.dry_run:
            self._call(f"/zones/{self.zone_id}/dns_records/{record['id']}", "DELETE")


def sync_once(cloudflare, names, urls, dry_run):
    address = public_ipv4()
    log(f"目前公網 IP {address}")
    cloudflare.resolve_zone()
    records = cloudflare.list_records()
    changes = []
    for name in names:
        change = cloudflare.ensure_a(records, name, address)
        if change:
            changes.append(change)
    if not changes:
        return
    title, body = notice_text(address, changes)
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
    assert record_names("@, vpn ,wongkino.com", "wongkino.com") == [
        "wongkino.com",
        "vpn.wongkino.com",
    ]
    try:
        record_names("example.com", "wongkino.com")
    except SystemExit:
        pass
    else:
        raise AssertionError("其他 zone 的名稱應被拒絕")
    assert apprise_urls("discord://a/b tgram://c/d") == ["discord://a/b", "tgram://c/d"]
    assert apprise_urls("https://apprise.example.com/notify/cloudflare") == [
        "apprises://apprise.example.com/cloudflare"
    ]
    assert apprise_urls("") == []
    title, body = notice_text("1.2.3.4", [{"name": "wan1.wongkino.com", "before": "9.9.9.9", "after": "1.2.3.4"}])
    assert title == "IP changed"
    assert "9.9.9.9 → 1.2.3.4" in body
    log("自我測試通過")


def main():
    if os.environ.get("SELF_TEST") == "1":
        self_test()
        return
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    domain = required("DOMAIN").rstrip(".").lower()
    names = record_names(os.environ.get("A_RECORDS", domain), domain)
    interval = env_int("INTERVAL_SECONDS", 30)
    dry_run = os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "yes"}
    urls = apprise_urls(os.environ.get("APPRISE_URLS", ""))
    cloudflare = Cloudflare(
        required("CLOUDFLARE_API_TOKEN"),
        os.environ.get("CLOUDFLARE_ZONE_ID", "").strip(),
        domain,
        env_int("DNS_TTL", 60),
        dry_run,
    )
    log(
        f"開始監視 {', '.join(names)}，每 {interval} 秒檢查一次"
        + ("（演練，不會改 DNS）" if dry_run else "")
    )
    if urls:
        log(f"IP 改變時會經 Apprise 發送通知（{len(urls)} 個目的地）")
    else:
        log("未設定 APPRISE_URLS，IP 改變時不會發送通知")
    while not STOP:
        started = time.time()
        try:
            sync_once(cloudflare, names, urls, dry_run)
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
