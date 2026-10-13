# cloudflare-ddns

定期查詢主機目前的公網 IPv4 與 IPv6，把指定的 Cloudflare A、AAAA 紀錄改成這兩個位址。位址改變時，再用 [Apprise](https://github.com/caronc/apprise) 發通知。

Periodically look up this host's current public IPv4 and IPv6, and point the configured Cloudflare A and AAAA records at those addresses. When an address actually changes, send a notification through [Apprise](https://github.com/caronc/apprise).

容器走主機的預設路由。預設閘道切換之後，下一輪查到的就是新線路的位址，清單裡的 A 與 AAAA 紀錄會一起換過去。

The container uses the host's default route. After the default gateway changes, the next check sees the new path's address and updates every A and AAAA record in the list.

## 行為 / Behavior

每一輪會做這些事：

Each round does the following:

1. 依序向 `api4.ipify.org`、`ipv4.icanhazip.com`、`v4.ident.me` 查詢 IPv4，並向 `api6.ipify.org`、`ipv6.icanhazip.com`、`v6.ident.me` 查詢 IPv6。  
   Query IPv4 from `api4.ipify.org`, `ipv4.icanhazip.com`, and `v4.ident.me`, and IPv6 from `api6.ipify.org`, `ipv6.icanhazip.com`, and `v6.ident.me`, in that order.
2. IPv4 略過私有位址、保留位址和 `100.64.0.0/10`。IPv6 略過本地、鏈路、文件、6to4、Teredo 這類不能公布的位址。某一邊查不到時，那一邊的紀錄保持原狀，另一邊照常更新。兩邊都失敗時，這一輪不改 DNS。  
   For IPv4, skip private, reserved, and `100.64.0.0/10` addresses. For IPv6, skip addresses that must not be published, including local, link-local, documentation, 6to4, and Teredo. If one family cannot be read, leave that family's records unchanged and still update the other. If both fail, leave DNS unchanged for this round.
3. 把 `A_RECORDS` 裡的每個名稱的 A 紀錄設成這個 IPv4，AAAA 紀錄設成這個 IPv6。紀錄維持灰雲（不經過 Cloudflare 代理）。  
   Set the A record of every name in `A_RECORDS` to this IPv4, and the AAAA record to this IPv6. Records stay DNS-only (not proxied by Cloudflare).
4. 同一個名稱若是 CNAME，會刪掉並改成位址紀錄。同一類型若有多筆，保留一筆並刪除其餘。A 與 AAAA 互不覆蓋。  
   If the name is a CNAME, delete it and replace it with an address record. If several records of the same type exist, keep one and delete the rest. A and AAAA records do not replace each other.
5. 只有位址本身改變時才發送 Apprise。只調整 TTL、或位址沒有變，都不發通知。同一輪裡 A 與 AAAA 的變更會合成一則通知。  
   Send Apprise only when an address itself changes. TTL-only edits and an unchanged address do not send a notification. A and AAAA changes in the same round are sent as one notification.

查詢或 Cloudflare API 失敗時，既有紀錄保持原狀。

If the lookup or the Cloudflare API fails, existing records stay as they are.

## 需求 / Requirements

- 主機可以執行 Docker，而且預設路由就是要公布的那條對外線路。AAAA 還需要容器能連出 IPv6；查不到 IPv6 時不會改 AAAA。Linux 上若容器沒有 IPv6，可在實際使用的 compose 加上 `network_mode: host`。  
  The host can run Docker, and its default route is the path whose address should be published. AAAA also needs IPv6 egress from the container; when IPv6 cannot be read, AAAA records are left unchanged. On Linux, add `network_mode: host` to the compose file you use if the container has no IPv6.
- Cloudflare API token，權限為目標 zone 的 DNS 編輯。若沒有填 `CLOUDFLARE_ZONE_ID`，token 還需要能列出 zone。  
  A Cloudflare API token with DNS edit permission on the target zone. Without `CLOUDFLARE_ZONE_ID`, the token must also be able to list zones.
- 要通知時，另備一個 Apprise 服務或 Apprise 網址。  
  For notifications, provide an Apprise service or an Apprise URL.

## 使用 GitHub 映像 / Use the GitHub image

設定寫在 `docker-compose.ghcr.yml` 的 `environment`。映像是 `ghcr.io/wongkino/cloudflare-ddns:amd64`，每次啟動都會再拉一次。

Settings go in the `environment` section of `docker-compose.ghcr.yml`. The image is `ghcr.io/wongkino/cloudflare-ddns:amd64`, and it is pulled again on each start.

若映像不是公開的，先用有 `read:packages` 權限的 GitHub token 登入：

If the image is not public, log in first with a GitHub token that has `read:packages`:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u wongkino --password-stdin
```

編輯 `environment` 後啟動：

Edit `environment`, then start:

```bash
docker compose -f docker-compose.ghcr.yml up -d
docker compose -f docker-compose.ghcr.yml logs -f
```

Token 寫在這份 compose 裡。不要把填好的檔案提交進倉庫。

The token lives in this compose file. Do not commit the file after it contains a token.

## 本機建置 / Build locally

`docker-compose.yml` 會在本機建置，設定同樣寫在它自己的 `environment`。

`docker-compose.yml` builds locally. Its settings are in its own `environment` section.

```bash
docker compose up -d --build
docker compose logs -f
```

這會用執行建置的那台機器的架構建立映像。

This builds an image for the architecture of the machine running the build.

## 設定 / Configuration

變數寫在 compose 的 `environment`。兩份 compose 各自一份，改你實際啟動的那份。

Variables are set in the compose file's `environment`. Each compose file has its own copy; edit the one you start.

| 變數 / Variable | 必填 / Required | 預設 / Default | 說明 / Description |
| --- | --- | --- | --- |
| `CLOUDFLARE_API_TOKEN` | 是 / yes |  | Cloudflare API token |
| `DOMAIN` | 是 / yes |  | Zone 的網域，例如 `example.com`。<br>Zone domain, for example `example.com`. |
| `A_RECORDS` | 否 / no | `DOMAIN` 的值 / the value of `DOMAIN` | 要更新的名稱，逗號分隔。每個名稱都會更新 A 與 AAAA。<br>Names to update, separated by commas. Each name gets both an A and an AAAA record. |
| `CLOUDFLARE_ZONE_ID` | 否 / no | 自動查詢 / looked up | 已知 zone ID 時可填，省去列出 zone 的權限。<br>Set a known zone ID to skip permission to list zones. |
| `INTERVAL_SECONDS` | 否 / no | `30` | 每輪間隔，必須是正整數。<br>Seconds between rounds. Must be a positive integer. |
| `DNS_TTL` | 否 / no | `60` | A 與 AAAA 紀錄的 TTL（秒）。Zone 不接受時會改用 Cloudflare 自動 TTL。<br>TTL in seconds for A and AAAA records. If the zone rejects it, Cloudflare automatic TTL is used instead. |
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

```yaml
environment:
  DOMAIN: example.com
  A_RECORDS: "@,nas,vpn.example.com"
```

清單中的每個名稱都會設成同一個目前公網 IPv4 與 IPv6。這個程式不讀取路由器的各別對外介面。

Every name in the list is set to the same current public IPv4 and IPv6. This program does not read individual router interfaces.

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

```yaml
environment:
  APPRISE_URLS: https://apprise.example.com/notify/token
```

多個目的地以空白分隔。各種網址格式見 [Apprise wiki](https://github.com/caronc/apprise/wiki)。

Separate multiple destinations with spaces. URL formats are listed in the [Apprise wiki](https://github.com/caronc/apprise/wiki).

位址改變時，通知以英文送出。標題是 `IP changed`。內容先寫目前查到的公網 IPv4 與 IPv6，再列出每個有變的紀錄、類型、舊位址和新位址；新紀錄顯示為 `(new record)`。

When an address changes, the notification is sent in English. The title is `IP changed`. The body starts with the public IPv4 and IPv6 found this round, then lists each changed record, its type, and the previous and new address. A new record is shown as `(new record)`.

## 發佈映像 / Publish an image

若要另外建立 `linux/amd64` 映像，在 GitHub 開啟 **Actions**，選擇 **Build AMD64 image**，再按 **Run workflow**。這個工作只會在手動執行時跑，並把映像推到 GitHub Container Registry：

To build a `linux/amd64` image separately, open **Actions** on GitHub, choose **Build AMD64 image**, and select **Run workflow**. The workflow runs only when started manually and pushes the image to GitHub Container Registry:

```text
ghcr.io/wongkino/cloudflare-ddns:amd64
```

同一輪也會加上 `amd64-` 開頭的 commit 標籤，以及一個版本標籤。**Version** 留空時，會把現有最大版本的 patch 加一；還沒有版本標籤時從 `1.0.0` 開始。只有要指定版本時才填，例如 `2.0.0`。格式須為 `1.2`、`1.2.0`、`v1.2.0`，或在後面加 `-rc1` 這類後綴。

The same run also adds a commit tag prefixed with `amd64-`, plus a version tag. An empty **Version** increments the patch number of the highest existing version, or starts at `1.0.0` when no version tag exists. Fill it in only to choose a version, for example `2.0.0`. Use `1.2`, `1.2.0`, `v1.2.0`, or the same form with a suffix such as `-rc1`.

## 常用指令 / Common commands

GitHub 映像的指令都要加上 `-f docker-compose.ghcr.yml`。本機建置則直接用 `docker compose`。

For the GitHub image, add `-f docker-compose.ghcr.yml` to every command. For a local build, use `docker compose` alone.

```bash
docker compose -f docker-compose.ghcr.yml logs -f
docker compose -f docker-compose.ghcr.yml restart
docker compose -f docker-compose.ghcr.yml down
```

容器名稱是 `cloudflare-ddns`。程序收到 `SIGTERM` 或 `SIGINT` 會在目前這一輪結束後停止。

The container name is `cloudflare-ddns`. On `SIGTERM` or `SIGINT`, the process stops after the current round finishes.

## 演練 / Dry run

在使用中的 compose 把 `DRY_RUN` 設為 `"true"` 後，用同一個 compose 檔重新啟動。日誌會列出準備新增、更新或刪除的紀錄，以及準備發送的通知文字，但不會呼叫 Cloudflare 的寫入 API。

Set `DRY_RUN` to `"true"` in the compose file you are using, then restart with that same file. The log lists records that would be created, updated, or deleted, and the notification text that would be sent. It does not call Cloudflare's write API.

確認無誤後改回 `"false"`，再執行一次 `up -d`。

When the output looks right, set it back to `"false"` and run `up -d` again.

## 授權 / License

[MIT](LICENSE)
