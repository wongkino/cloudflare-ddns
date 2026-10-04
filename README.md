# cloudflare-ddns

定期查詢這台機器目前的公網 IPv4，把你指定的 Cloudflare A 紀錄改成這個位址。IP 真的改變時，再用 [Apprise](https://github.com/caronc/apprise) 發通知。

適合放在會跟著預設線路出去的主機上。WAN1 中斷、閘道器改走 WAN2 之後，下一輪查到的就是 WAN2 的位址，清單裡的 A 紀錄會一起換過去。

## 行為

每一輪會做這些事：

1. 依序向 `api4.ipify.org`、`ipv4.icanhazip.com`、`v4.ident.me` 查詢 IPv4。
2. 略過私有位址、保留位址和 `100.64.0.0/10`。三個來源都失敗時，這一輪不改 DNS。
3. 把 `A_RECORDS` 裡的每個名稱設成這個 IPv4。紀錄維持灰雲（不經過 Cloudflare 代理）。
4. 同一個名稱若是 CNAME，會刪掉並改成 A 紀錄。若有多筆 A 紀錄，保留一筆並刪除其餘。
5. 只有位址本身改變時才發送 Apprise。只調整 TTL、或位址沒有變，都不發通知。

查詢或 Cloudflare API 失敗時，既有紀錄保持原狀。

## 需求

- 主機可以執行 Docker，而且預設路由就是你想公布的那條 WAN。
- Cloudflare API token，權限為目標 zone 的 DNS 編輯。若沒有填 `CLOUDFLARE_ZONE_ID`，token 還需要能列出 zone。
- 要通知時，另備一個 Apprise 服務或 Apprise 網址。

## 安裝

```bash
git clone https://github.com/wongkino/cloudflare-ddns.git
cd cloudflare-ddns
cp .env.example .env
```

編輯 `.env` 後啟動：

```bash
docker compose up -d --build
docker compose logs -f
```

`.env` 已列入 `.gitignore`，不要把 token 提交進倉庫。

## 設定

| 變數 | 必填 | 預設 | 說明 |
| --- | --- | --- | --- |
| `CLOUDFLARE_API_TOKEN` | 是 |  | Cloudflare API token |
| `DOMAIN` | 是 |  | Zone 的網域，例如 `example.com` |
| `A_RECORDS` | 否 | `DOMAIN` 的值 | 要更新的名稱，逗號分隔 |
| `CLOUDFLARE_ZONE_ID` | 否 | 自動查詢 | 已知 zone ID 時可填，省去列出 zone 的權限 |
| `INTERVAL_SECONDS` | 否 | `30` | 每輪間隔，必須是正整數 |
| `DNS_TTL` | 否 | `60` | A 紀錄的 TTL（秒）。Zone 不接受時會改用 Cloudflare 自動 TTL |
| `DRY_RUN` | 否 | `false` | `true`、`1` 或 `yes` 時只記錄會做的變更，不寫入 DNS、不發通知 |
| `APPRISE_URLS` | 否 | 空 | 通知網址，多個以空白分隔 |

健康檢查要求大約 120 秒內至少成功完成一輪。`INTERVAL_SECONDS` 請維持在 90 秒以內。

### A_RECORDS

名稱必須屬於 `DOMAIN`。

- `@` 代表根網域。
- 沒有點的名稱會補上 `DOMAIN`，例如 `wan1` 變成 `wan1.example.com`。
- 也可以寫完整名稱，例如 `nas.example.com`。

```bash
DOMAIN=example.com
A_RECORDS=@,wan1,nas.example.com
```

清單中的每個名稱都會設成同一個目前公網 IP。這個程式不讀取路由器的各別 WAN 介面。

### Apprise

可填 Apprise 網址，或 Apprise API 的 HTTP 位址。後者會自動轉成 Apprise 能用的形式：

```text
https://apprise.example.com/notify/金鑰
```

等於：

```text
apprises://apprise.example.com/金鑰
```

```bash
APPRISE_URLS=https://apprise.example.com/notify/金鑰
```

多個目的地以空白分隔。各種網址格式見 [Apprise wiki](https://github.com/caronc/apprise/wiki)。

IP 改變時的通知標題是「IP 已更改」。內容包含目前公網 IP，以及每個紀錄的舊位址和新位址。

## 手動建立 AMD64 映像

在 GitHub 開啟 **Actions**，選擇 **Build AMD64 image**，再按 **Run workflow**。這個工作只會在手動執行時跑，並建立 `linux/amd64` 映像，推送到私人套件：

```text
ghcr.io/wongkino/cloudflare-ddns:amd64
```

同一輪也會加上 `amd64-` 開頭的 commit 標籤。在 x86_64 主機上拉取前，先用有 `read:packages` 權限的 GitHub token 登入：

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u wongkino --password-stdin
docker pull ghcr.io/wongkino/cloudflare-ddns:amd64
```

本機 Apple Silicon 若只想自己建映像，仍使用 `docker compose up -d --build`，那個映像是執行建置的那台機器的架構。

## 常用指令

```bash
docker compose logs -f
docker compose restart
docker compose down
```

容器名稱是 `cloudflare-ddns`。程序收到 `SIGTERM` 或 `SIGINT` 會在目前這一輪結束後停止。

## 演練

在 `.env` 設定 `DRY_RUN=true` 後重新啟動。日誌會列出準備新增、更新或刪除的紀錄，以及準備發送的通知文字，但不會呼叫 Cloudflare 的寫入 API。

確認無誤後改回 `DRY_RUN=false`，再執行 `docker compose up -d`。
