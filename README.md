# cloudflare-ddns

定期查詢主機目前的公網 IPv4 與 IPv6，把指定的 Cloudflare A、AAAA 紀錄改成這兩個位址。`RECORD_TYPES` 可以只查 A、只查 AAAA，或兩者都查。位址改變時，再用 [Apprise](https://github.com/caronc/apprise) 發通知。

Periodically look up this host's current public IPv4 and IPv6, and point the configured Cloudflare A and AAAA records at those addresses. `RECORD_TYPES` can check A only, AAAA only, or both. When an address actually changes, send a notification through [Apprise](https://github.com/caronc/apprise).

容器走主機的預設路由。預設閘道切換之後，下一輪查到的就是新線路的位址，清單裡的 A 與 AAAA 紀錄會一起換過去。

The container uses the host's default route. After the default gateway changes, the next check sees the new path's address and updates every A and AAAA record in the list.

## 行為 / Behavior

每一輪會做這些事：

Each round does the following:

1. 依 `RECORD_TYPES` 查詢。含 A 時向 `api4.ipify.org`、`ipv4.icanhazip.com`、`v4.ident.me` 查 IPv4；含 AAAA 時向 `api6.ipify.org`、`ipv6.icanhazip.com`、`v6.ident.me` 查 IPv6。沒選到的類型不會查。其中一個查詢站回「主機不可達」時，會改試下一個。整段網路沒有這個位址族的路由時才停止。  
   Follow `RECORD_TYPES`. When it includes A, query IPv4 from `api4.ipify.org`, `ipv4.icanhazip.com`, and `v4.ident.me`. When it includes AAAA, query IPv6 from `api6.ipify.org`, `ipv6.icanhazip.com`, and `v6.ident.me`. A type that is not selected is not queried. If one source says the host is unreachable, the next source is tried. Lookup stops only when that address family has no route.
2. IPv4 略過私有位址、保留位址和 `100.64.0.0/10`。IPv6 略過本地、鏈路、文件、6to4、Teredo 這類不能公布的位址。選中的某一邊查不到時，那一邊的紀錄保持原狀，另一邊照常更新。選中的類型全部失敗時，這一輪不改 DNS。  
   For IPv4, skip private, reserved, and `100.64.0.0/10` addresses. For IPv6, skip addresses that must not be published, including local, link-local, documentation, 6to4, and Teredo. If one selected family cannot be read, leave that family's records unchanged and still update the other. If every selected type fails, leave DNS unchanged for this round.
3. 把 `A_RECORDS` 裡的每個名稱，設成這次查到的位址。只寫入 `RECORD_TYPES` 選中的類型。`CF_PROXIED` 為 false 時維持灰雲；為 true 時改成橙雲，流量經過 Cloudflare 代理。  
   Set every name in `A_RECORDS` to the addresses found this round. Only the types selected in `RECORD_TYPES` are written. With `CF_PROXIED` false, records stay DNS-only. With it true, they are proxied by Cloudflare.
4. 同一個名稱若是 CNAME，會刪掉並改成位址紀錄。同一類型若有多筆，優先保留已經指向目標位址的那筆，並刪除其餘。A 與 AAAA 互不覆蓋。  
   If the name is a CNAME, delete it and replace it with an address record. If several records of the same type exist, keep the one that already points at the target address and delete the rest. A and AAAA records do not replace each other.
5. 只有位址本身改變時才發送 Apprise。只調整 TTL、或位址沒有變，都不發通知。同一輪裡 A 與 AAAA 的變更會合成一則通知。  
   Send Apprise only when an address itself changes. TTL-only edits and an unchanged address do not send a notification. A and AAAA changes in the same round are sent as one notification.

位址與上次成功核對時相同時，這一輪不查 Cloudflare。最多每隔 `RECHECK_SECONDS`（預設一小時）仍會完整核對一次，所以在 Cloudflare 上手動改過的紀錄，最遲會在這個間隔內被改回。`DRY_RUN` 期間每輪都完整檢查。

While the addresses match the last successful check, the round skips Cloudflare. A full check still runs at least once every `RECHECK_SECONDS` (one hour by default), so records edited by hand in Cloudflare are reverted within that interval. With `DRY_RUN` on, every round is a full check.

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

映像是 `ghcr.io/wongkino/cloudflare-ddns:amd64`，每次啟動都會再拉一次。下面兩種擇一，編輯那份 compose 的 `environment`。Token 寫在該檔裡。不要把填好的檔案提交進倉庫。

The image is `ghcr.io/wongkino/cloudflare-ddns:amd64`, and it is pulled again on each start. Pick one of the two setups below and edit that compose file's `environment`. The token lives in that file. Do not commit the file after it contains a token.

若映像不是公開的，先用有 `read:packages` 權限的 GitHub token 登入：

If the image is not public, log in first with a GitHub token that has `read:packages`:

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u wongkino --password-stdin
```

### 單一 zone / One zone

用 `docker-compose.yml`。64-bit Raspberry Pi 改用 `docker-compose.arm64.yml`，映像已是 `ghcr.io/wongkino/cloudflare-ddns:arm64`。

Use `docker-compose.yml`. On a 64-bit Raspberry Pi, use `docker-compose.arm64.yml` instead. That file already uses `ghcr.io/wongkino/cloudflare-ddns:arm64`.

只填一個 zone。`@` 是這個 zone 的根網域。也可以改成這個 zone 裡的完整名稱，例如 `wan1.example.com`。`A_RECORDS` 留空時，同樣更新根網域。

Set one zone. `@` is that zone's apex. You can use a fully qualified name in that zone instead, for example `wan1.example.com`. An empty `A_RECORDS` updates the apex as well.

```yaml
DOMAIN: example.com
A_RECORDS: "@"
```

Token 需要能編輯這個 zone 的 DNS。沒有填 `CLOUDFLARE_ZONE_ID` 時，還要能列出 zone。

The token needs DNS edit permission on this zone. Without `CLOUDFLARE_ZONE_ID`, it must also be able to list zones.

```bash
docker compose up -d
docker compose logs -f
```

64-bit Raspberry Pi：

On a 64-bit Raspberry Pi:

```bash
docker compose -f docker-compose.arm64.yml up -d
docker compose -f docker-compose.arm64.yml logs -f
```

### 多個指定 zone / Specific zones

用 `docker-compose.multi.yml`。只更新 `DOMAIN` 列出的 zone，同一個帳號裡的其他 zone 不會動。64-bit Raspberry Pi 把該檔的 `image` 改成 `ghcr.io/wongkino/cloudflare-ddns:arm64`。

Use `docker-compose.multi.yml`. Only the zones listed in `DOMAIN` are updated. Other zones in the same account are left alone. On a 64-bit Raspberry Pi, change that file's `image` to `ghcr.io/wongkino/cloudflare-ddns:arm64`.

每個列出的 zone 都要有至少一個名稱，而且要寫完整名稱。`wan1.example.com` 只更新 `example.com`；`example.net` 更新該 zone 的根。不要用 `@` 或沒有點的名稱，例如 `nas`，那些會套到每一個列出的 zone。手填 `CLOUDFLARE_ZONE_ID` 時，順序和個數要和 `DOMAIN` 相同；留空則用網域名稱查詢。清單中的名稱都會設成同一個目前公網位址。這個程式不讀取路由器的各別對外介面。

Every listed zone needs at least one fully qualified name. `wan1.example.com` updates only `example.com`. `example.net` updates that zone's apex. Do not use `@` or a name without a dot, such as `nas`; those are applied to every listed zone. When `CLOUDFLARE_ZONE_ID` is set, its order and count must match `DOMAIN`. Leave it empty to look zones up by name. Every selected name is set to the same current public address. This program does not read individual router interfaces.

```yaml
DOMAIN: example.com,example.net
A_RECORDS: wan1.example.com,example.net
```

Token 需要能編輯這些 zone 的 DNS。沒有填 `CLOUDFLARE_ZONE_ID` 時，還要能列出 zone。

The token needs DNS edit permission on these zones. Without `CLOUDFLARE_ZONE_ID`, it must also be able to list zones.

```bash
docker compose -f docker-compose.multi.yml up -d
docker compose -f docker-compose.multi.yml logs -f
```

## 狀態頁 / Status page

`WEB_UI` 預設關閉。設為 `true` 後，同一個程序會另開狀態頁。頁面內容就是這一個容器的 `DOMAIN`：用 `docker-compose.yml` 啟動時只顯示那一個 zone；用 `docker-compose.multi.yml` 啟動時顯示列出的每一個 zone。沒有切換。位址真的改變才寫入更換紀錄，最多保留 100 筆。演練不會寫入紀錄。

`WEB_UI` is off by default. Set it to `true` and the same process also serves a status page. The page shows the `DOMAIN` of that container: `docker-compose.yml` shows its one zone, and `docker-compose.multi.yml` shows every zone it lists. There is no switch. A history entry is stored only when an address actually changes, up to 100 entries. A dry run does not store history.

在使用中的 compose 加上連接埠，例如：

Add a published port to the compose file you use, for example:

```yaml
ports:
  - "8080:8080"
environment:
  WEB_UI: "true"
  WEB_PORT: "8080"
```

然後打開 `http://127.0.0.1:8080`。本機只看版面、不連 Cloudflare 時，可以執行 `python3 -m web.dev_server`，它只用單一 zone 的範例，不是部署結果。

Then open `http://127.0.0.1:8080`. To look at the layout on this machine without calling Cloudflare, run `python3 -m web.dev_server`. That preview uses a single-zone sample and is not a deployment.

## 設定 / Configuration

變數寫在你啟動的那份 compose 的 `environment`。

Variables are set in the `environment` section of the compose file you start.

| 變數 / Variable | 必填 / Required | 預設 / Default | 說明 / Description |
| --- | --- | --- | --- |
| `CLOUDFLARE_API_TOKEN` | 是 / yes |  | Cloudflare API token |
| `DOMAIN` | 是 / yes |  | 單一 zone 填一個網域。多個指定 zone 用逗號列出要更新的 zone。寫法見上面兩節。<br>One domain for a single zone. For specific zones, list them separated by commas. See the two sections above. |
| `A_RECORDS` | 否 / no | 該 zone 的根網域 / that zone's apex | 要更新的名稱。單一 zone 可用 `@`。多個指定 zone 請寫完整名稱。見上面兩節。<br>Names to update. One zone may use `@`. Specific zones should use fully qualified names. See the two sections above. |
| `RECORD_TYPES` | 否 / no | `A,AAAA` | `A`、`AAAA`，或 `A,AAAA`。<br>`A`, `AAAA`, or `A,AAAA`. |
| `CLOUDFLARE_ZONE_ID` | 否 / no | 自動查詢 / looked up | 已知 zone ID 時可填，順序和 `DOMAIN` 相同，省去列出 zone 的權限。<br>Known zone IDs in the same order as `DOMAIN`. Skips permission to list zones. |
| `INTERVAL_SECONDS` | 否 / no | `30` | 每輪間隔，必須是正整數。<br>Seconds between rounds. Must be a positive integer. |
| `RECHECK_SECONDS` | 否 / no | `3600` | 位址沒變時，最長隔多久仍對 Cloudflare 完整核對一次。<br>When addresses are unchanged, how often a full Cloudflare check still runs. |
| `DNS_TTL` | 否 / no | `60` | A 與 AAAA 紀錄的 TTL（秒）。Zone 不接受時會改用 Cloudflare 自動 TTL。<br>TTL in seconds for A and AAAA records. If the zone rejects it, Cloudflare automatic TTL is used instead. |
| `CF_PROXIED` | 否 / no | `false` | `true`、`1` 或 `yes` 時紀錄走橙雲。預設灰雲，直接公布這台機器的位址。<br>`true`, `1`, or `yes` proxies the records through Cloudflare. The default is DNS-only, publishing this host's address. |
| `DRY_RUN` | 否 / no | `false` | `true`、`1` 或 `yes` 時只記錄會做的變更，不寫入 DNS、不發通知。<br>`true`, `1`, or `yes` logs the intended changes without writing DNS or sending notifications. |
| `APPRISE_URLS` | 否 / no | 空 / empty | 通知網址，多個以空白分隔。<br>Notification URLs, separated by spaces. |
| `WEB_UI` | 否 / no | `false` | `true` 時開啟狀態頁。<br>`true` serves the status page. |
| `WEB_PORT` | 否 / no | `8080` | 狀態頁連接埠。<br>Port for the status page. |

健康檢查要求大約 120 秒內至少成功完成一輪。`INTERVAL_SECONDS` 請維持在 90 秒以內。

The health check expects a successful round within about 120 seconds. Keep `INTERVAL_SECONDS` under 90.

### Apprise

`APPRISE_URLS` 直接使用 [Apprise](https://github.com/caronc/apprise/wiki) 自己的網址格式，例如 Gotify 的 `gotifys://`、Discord 的 `discord://`。每種服務的寫法不同，請到 Apprise wiki 選你的服務，照該頁的 URL 填進來。這個程式不會改寫這些網址。

`APPRISE_URLS` takes [Apprise](https://github.com/caronc/apprise/wiki) URLs as-is, for example Gotify `gotifys://` or Discord `discord://`. Each service has its own syntax. Open the Apprise wiki, pick the service, and copy that page's URL. This program does not rewrite those URLs.

```yaml
environment:
  APPRISE_URLS: gotifys://gotify.example.com/token
```

若通知是經過 Apprise API 伺服器送出，可填它的 HTTP 位址，程式會轉成 Apprise 能用的形式：

To send through an Apprise API server, use its HTTP address. The program converts it:

```text
https://apprise.example.com/notify/token
```

等於：

becomes:

```text
apprises://apprise.example.com/token
```

多個目的地以空白分隔，可以混用不同服務。有一個網址無法辨識時會略過它，其餘照常發送。

Separate multiple destinations with spaces. Different services can be mixed. A URL Apprise does not recognize is skipped; the rest are still sent.

位址改變時，通知以英文送出。標題是 `IP changed`。內容先寫目前查到的公網 IPv4 與 IPv6，再列出每個有變的紀錄、類型、舊位址和新位址；新紀錄顯示為 `(new record)`。

When an address changes, the notification is sent in English. The title is `IP changed`. The body starts with the public IPv4 and IPv6 found this round, then lists each changed record, its type, and the previous and new address. A new record is shown as `(new record)`.

## 發佈映像 / Publish an image

在 GitHub 開啟 **Actions**，選擇 **Build image**，再按 **Run workflow**。這個工作只會在手動執行時跑。**Platform** 選 `amd64` 給一般電腦，選 `arm64` 給 64-bit Raspberry Pi OS（Pi 3、4、5、Zero 2 W）。32-bit 的 Raspberry Pi OS 不能用這個 `arm64` 映像。

Open **Actions** on GitHub, choose **Build image**, and select **Run workflow**. The workflow runs only when started manually. Choose `amd64` for a regular computer, or `arm64` for 64-bit Raspberry Pi OS (Pi 3, 4, 5, and Zero 2 W). 32-bit Raspberry Pi OS cannot run this `arm64` image.

映像會推到 GitHub Container Registry：

The image is pushed to GitHub Container Registry:

```text
ghcr.io/wongkino/cloudflare-ddns:amd64
ghcr.io/wongkino/cloudflare-ddns:arm64
```

同一輪也會加上架構開頭的 commit 標籤，以及一個版本標籤。`amd64` 的版本像 `1.1.0`，`arm64` 的版本像 `1.1.0-arm64`，兩邊各自遞增。每次建置也會更新該架構的 latest：`amd64` 是 `latest`，`arm64` 是 `latest-arm64`。**Version** 留空時，會把該架構現有最大版本的 patch 加一；還沒有版本標籤時從 `1.0.0` 開始。只有要指定版本時才填，例如 `2.0.0`。格式須為 `1.2`、`1.2.0`、`v1.2.0`，或在後面加 `-rc1` 這類後綴。

The same run also adds a commit tag prefixed with the architecture, plus a version tag. An `amd64` version looks like `1.1.0`, and an `arm64` version looks like `1.1.0-arm64`. Each architecture increments on its own. Each build also updates that architecture's latest tag: `latest` for `amd64`, and `latest-arm64` for `arm64`. An empty **Version** increments the patch number of that architecture's highest version, or starts at `1.0.0` when no version tag exists. Fill it in only to choose a version, for example `2.0.0`. Use `1.2`, `1.2.0`, `v1.2.0`, or the same form with a suffix such as `-rc1`.

## 常用指令 / Common commands

單一 zone：

One zone:

```bash
docker compose logs -f
docker compose restart
docker compose down
```

64-bit Raspberry Pi 的單一 zone 換成 `docker-compose.arm64.yml`。

For one zone on a 64-bit Raspberry Pi, use `docker-compose.arm64.yml`.

```bash
docker compose -f docker-compose.arm64.yml logs -f
docker compose -f docker-compose.arm64.yml restart
docker compose -f docker-compose.arm64.yml down
```

多個指定 zone：

Specific zones:

```bash
docker compose -f docker-compose.multi.yml logs -f
docker compose -f docker-compose.multi.yml restart
docker compose -f docker-compose.multi.yml down
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
