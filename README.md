# cloudflare-ddns

定期查詢主機目前的公網 IPv4，把指定的 Cloudflare A 紀錄改成這個位址。IP 改變時，再用 [Apprise](https://github.com/caronc/apprise) 發通知。

Periodically look up this host's current public IPv4 and point the configured Cloudflare A records at that address. When the IP actually changes, send a notification through [Apprise](https://github.com/caronc/apprise).

容器走主機的預設路由。預設閘道切換之後，下一輪查到的就是新線路的位址，清單裡的 A 紀錄會一起換過去。

The container uses the host's default route. After the default gateway changes, the next check sees the new path's address and updates every A record in the list.

## 行為 / Behavior

每一輪會做這些事：

Each round does the following:

1. 依序向 `api4.ipify.org`、`ipv4.icanhazip.com`、`v4.ident.me` 查詢 IPv4。  
   Query IPv4 from `api4.ipify.org`, `ipv4.icanhazip.com`, and `v4.ident.me`, in that order.
2. 略過私有位址、保留位址和 `100.64.0.0/10`。三個來源都失敗時，這一輪不改 DNS。  
   Skip private, reserved, and `100.64.0.0/10` addresses. If all three sources fail, leave DNS unchanged for this round.
3. 把 `A_RECORDS` 裡的每個名稱設成這個 IPv4。紀錄維持灰雲（不經過 Cloudflare 代理）。  
   Set every name in `A_RECORDS` to this IPv4. Records stay DNS-only (not proxied by Cloudflare).
4. 同一個名稱若是 CNAME，會刪掉並改成 A 紀錄。若有多筆 A 紀錄，保留一筆並刪除其餘。  
   If the name is a CNAME, delete it and replace it with an A record. If several A records exist, keep one and delete the rest.
5. 只有位址本身改變時才發送 Apprise。只調整 TTL、或位址沒有變，都不發通知。  
   Send Apprise only when the address itself changes. TTL-only edits and an unchanged address do not send a notification.

查詢或 Cloudflare API 失敗時，既有紀錄保持原狀。

If the lookup or the Cloudflare API fails, existing records stay as they are.

## 需求 / Requirements

- 主機可以執行 Docker，而且預設路由就是要公布的那條對外線路。  
  The host can run Docker, and its default route is the path whose address should be published.
- Cloudflare API token，權限為目標 zone 的 DNS 編輯。若沒有填 `CLOUDFLARE_ZONE_ID`，token 還需要能列出 zone。  
  A Cloudflare API token with DNS edit permission on the target zone. Without `CLOUDFLARE_ZONE_ID`, the token must also be able to list zones.
- 要通知時，另備一個 Apprise 服務或 Apprise 網址。  
  For notifications, provide an Apprise service or an Apprise URL.

## 安裝 / Install

取得原始碼後：

After you have the source:

```bash
cd cloudflare-ddns
cp .env.example .env
```

編輯 `.env` 後啟動：

Edit `.env`, then start:

```bash
docker compose up -d --build
docker compose logs -f
```

`.env` 已列入 `.gitignore`，不要把 token 提交進倉庫。

`.env` is listed in `.gitignore`. Do not commit tokens.

## 設定 / Configuration

| 變數 / Variable | 必填 / Required | 預設 / Default | 說明 / Description |
| --- | --- | --- | --- |
| `CLOUDFLARE_API_TOKEN` | 是 / yes |  | Cloudflare API token |
| `DOMAIN` | 是 / yes |  | Zone 的網域，例如 `example.com`。<br>Zone domain, for example `example.com`. |
| `A_RECORDS` | 否 / no | `DOMAIN` 的值 / the value of `DOMAIN` | 要更新的名稱，逗號分隔。<br>Names to update, separated by commas. |
| `CLOUDFLARE_ZONE_ID` | 否 / no | 自動查詢 / looked up | 已知 zone ID 時可填，省去列出 zone 的權限。<br>Set a known zone ID to skip permission to list zones. |
| `INTERVAL_SECONDS` | 否 / no | `30` | 每輪間隔，必須是正整數。<br>Seconds between rounds. Must be a positive integer. |
| `DNS_TTL` | 否 / no | `60` | A 紀錄的 TTL（秒）。Zone 不接受時會改用 Cloudflare 自動 TTL。<br>TTL in seconds for A records. If the zone rejects it, Cloudflare automatic TTL is used instead. |
| `DRY_RUN` | 否 / no | `false` | `true`、`1` 或 `yes` 時只記錄會做的變更，不寫入 DNS、不發通知。<br>`true`, `1`, or `yes` logs the intended changes without writing DNS or sending notifications. |
| `APPRISE_URLS` | 否 / no | 空 / empty | 通知網址，多個以空白分隔。<br>Notification URLs, separated by spaces. |

健康檢查要求大約 120 秒內至少成功完成一輪。`INTERVAL_SECONDS` 請維持在 90 秒以內。

The health check expects a successful round within about 120 seconds. Keep `INTERVAL_SECONDS` under 90.

### A_RECORDS

名稱必須屬於 `DOMAIN`。

Each name must belong to `DOMAIN`.

- `@` 代表根網域。  
  `@` is the zone apex.
- 沒有點的名稱會補上 `DOMAIN`，例如 `nas` 變成 `nas.example.com`。  
  A name without a dot is suffixed with `DOMAIN`. For example, `nas` becomes `nas.example.com`.
- 也可以寫完整名稱，例如 `nas.example.com`。  
  A fully qualified name is also accepted, for example `nas.example.com`.

```bash
DOMAIN=example.com
A_RECORDS=@,nas,vpn.example.com
```

清單中的每個名稱都會設成同一個目前公網 IP。這個程式不讀取路由器的各別對外介面。

Every name in the list is set to the same current public IP. This program does not read individual router interfaces.

### Apprise

可填 Apprise 網址，或 Apprise API 的 HTTP 位址。後者會自動轉成 Apprise 能用的形式：

Use an Apprise URL, or the HTTP address of an Apprise API. The HTTP form is converted automatically:

```text
https://apprise.example.com/notify/token
```

等於：

becomes:

```text
apprises://apprise.example.com/token
```

```bash
APPRISE_URLS=https://apprise.example.com/notify/token
```

多個目的地以空白分隔。各種網址格式見 [Apprise wiki](https://github.com/caronc/apprise/wiki)。

Separate multiple destinations with spaces. URL formats are listed in the [Apprise wiki](https://github.com/caronc/apprise/wiki).

IP 改變時，通知以英文送出。標題是 `IP changed`。內容先寫目前公網 IP，再列出每個紀錄的舊位址和新位址；新紀錄顯示為 `(new record)`。

When the IP changes, the notification is sent in English. The title is `IP changed`. The body starts with the current public IP, then lists each record's previous and new address. A new record is shown as `(new record)`.

## 建立映像 / Build an image

`docker compose up -d --build` 會用執行建置的那台機器的架構建立映像。

`docker compose up -d --build` builds an image for the architecture of the machine running the build.

若要另外建立 `linux/amd64` 映像，在 GitHub 開啟 **Actions**，選擇 **Build AMD64 image**，再按 **Run workflow**。這個工作只會在手動執行時跑，並把映像推到 GitHub Container Registry：

To build a `linux/amd64` image separately, open **Actions** on GitHub, choose **Build AMD64 image**, and select **Run workflow**. The workflow runs only when started manually and pushes the image to GitHub Container Registry:

```text
ghcr.io/wongkino/cloudflare-ddns:amd64
```

同一輪也會加上 `amd64-` 開頭的 commit 標籤。**Version** 可留空。若填 `1.2.0` 這類版本號，會再推一個同名標籤，例如 `ghcr.io/wongkino/cloudflare-ddns:1.2.0`。格式須為 `1.2`、`1.2.0`、`v1.2.0`，或在後面加 `-rc1` 這類後綴。

The same run also adds a commit tag prefixed with `amd64-`. **Version** can be left empty. A value such as `1.2.0` adds a tag of that name, for example `ghcr.io/wongkino/cloudflare-ddns:1.2.0`. Use `1.2`, `1.2.0`, `v1.2.0`, or the same form with a suffix such as `-rc1`.

拉取前，先用有 `read:packages` 權限的 GitHub token 登入：

Before pulling, log in with a GitHub token that has `read:packages`:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u wongkino --password-stdin
docker pull ghcr.io/wongkino/cloudflare-ddns:amd64
```

## 常用指令 / Common commands

```bash
docker compose logs -f
docker compose restart
docker compose down
```

容器名稱是 `cloudflare-ddns`。程序收到 `SIGTERM` 或 `SIGINT` 會在目前這一輪結束後停止。

The container name is `cloudflare-ddns`. On `SIGTERM` or `SIGINT`, the process stops after the current round finishes.

## 演練 / Dry run

在 `.env` 設定 `DRY_RUN=true` 後重新啟動。日誌會列出準備新增、更新或刪除的紀錄，以及準備發送的通知文字，但不會呼叫 Cloudflare 的寫入 API。

Set `DRY_RUN=true` in `.env` and restart. The log lists records that would be created, updated, or deleted, and the notification text that would be sent. It does not call Cloudflare's write API.

確認無誤後改回 `DRY_RUN=false`，再執行 `docker compose up -d`。

When the output looks right, set `DRY_RUN=false` and run `docker compose up -d`.

## 授權 / License

[MIT](LICENSE)
