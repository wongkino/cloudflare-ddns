# cloudflare-ddns

讓 Cloudflare 的 A、AAAA 紀錄跟著這台主機的公網位址走，位址一變就通知你。

[English](./README.md) | [繁體中文](./README.zh-TW.md)

[![Release](https://img.shields.io/github/v/release/wongkino/cloudflare-ddns)](https://github.com/wongkino/cloudflare-ddns/releases)
[![License: MIT](https://img.shields.io/github/license/wongkino/cloudflare-ddns)](./LICENSE)
[![Stars](https://img.shields.io/github/stars/wongkino/cloudflare-ddns)](https://github.com/wongkino/cloudflare-ddns/stargazers)

容器走主機的預設路由。預設閘道一切換，下一輪就會把新位址寫進每一筆選中的紀錄。

## ✨ 功能特色

- 依 `RECORD_TYPES` 公布這台主機的公網 IPv4、IPv6，或兩者。
- 更新一個 zone，或只更新你列出的 zone。同一個帳號裡的其他 zone 不會動。
- 位址本身改變時，透過 [Apprise](https://github.com/caronc/apprise) 發一則通知。只改 TTL 不會發。
- 位址與上次核對相同時略過 Cloudflare，仍會定時完整核對，把手動改過的紀錄改回來。
- 可選的狀態頁顯示目前位址、監視中的名稱，以及真正換過的位址。
- 可以演練一輪，印出即將寫入的內容，不呼叫 Cloudflare 的寫入 API。

## 🖼 預覽

圖中是範例資料（`example.com`、`203.0.113.10`），不是某一次部署。

狀態頁是淺色 DNS 主控台：橘色訊號條、狀況方塊，然後是 Type、Name、Content、Proxy status 的表格。

![單一 zone 狀態頁。橘色訊號條下是狀況方塊、監視名稱的 DNS 表格，以及更換紀錄。](docs/status-single.png)

- 橘色訊號條與 LIVE 表示運作中。三個方塊分別是狀況、灰雲或橙雲，以及上次核對。
- 位址列是目前公網位址。這張圖只監視 A，所以只顯示 IPv4。
- 「監視中的紀錄」是 DNS 表格。灰雲膠囊表示只走 DNS，橙雲膠囊表示經過代理。
- 「更換紀錄」只在位址真的改變時出現。箭頭左邊是舊位址。

### 多個指定 zone

![多個 zone 的狀態頁。DNS 表格以 zone 分組，A 與 AAAA 各一列，更換紀錄在下方。](docs/status-multi.png)

同一個公網位址會寫到列出的每個名稱。A 和 AAAA 各自一列。每個 zone 是表格裡的一列標題。更換紀錄把各名稱的變更加在一起。

### 手機

![手機上的單一 zone 狀態頁。狀況方塊改成直排，DNS 表格在窄螢幕上仍可閱讀。](docs/status-phone.png)

窄螢幕時三個狀況方塊改成直排，DNS 表格可以橫向捲動。語言可切換繁體中文、簡體中文與 English。

在這台機器上看版面、不連 Cloudflare：

```bash
python3 -m web.dev_server
```

這個預覽只用單一 zone 的範例。

## 🚀 快速開始

### 安裝

主機要能跑 Docker，而且預設路由就是要公布的那條對外線路。compose 使用 `network_mode: host`，容器才看得到這台機器的公網 IPv4 與 IPv6。不要另加 `ports`。查不到 IPv6 時不會改 AAAA。

```bash
git clone https://github.com/wongkino/cloudflare-ddns.git
cd cloudflare-ddns
```

映像是 `ghcr.io/wongkino/cloudflare-ddns:amd64`，每次啟動都會再拉一次。Token 寫在你啟動的那份 compose。填上 token 之後不要把該檔案提交進倉庫。

映像若不是公開的，先用有 `read:packages` 權限的 GitHub token 登入：

```bash
echo "$GITHUB_TOKEN" | docker login ghcr.io -u wongkino --password-stdin
```

Token 需要能編輯列出的 zone 的 DNS（Zone / DNS / Edit）。沒有填 `CLOUDFLARE_ZONE_ID` 時，還需要 Zone / Zone / Read。

### 使用方式

編輯一份 compose 的 `environment`。一個容器只顯示一種設定。

#### 單一 zone

用 `docker-compose.yml`。64-bit Raspberry Pi 改用 `docker-compose.arm64.yml`，映像已是 `ghcr.io/wongkino/cloudflare-ddns:arm64`。

`@` 是這個 zone 的根網域。也可以改成這個 zone 裡的完整名稱，例如 `wan1.example.com`。`A_RECORDS` 留空時，同樣更新根網域。

```yaml
DOMAIN: example.com
A_RECORDS: "@"
```

```bash
docker compose up -d
docker compose logs -f
```

64-bit Raspberry Pi：

```bash
docker compose -f docker-compose.arm64.yml up -d
docker compose -f docker-compose.arm64.yml logs -f
```

#### 多個指定 zone

用 `docker-compose.multi.yml`。只更新 `DOMAIN` 列出的 zone。64-bit Raspberry Pi 把該檔的 `image` 改成 `ghcr.io/wongkino/cloudflare-ddns:arm64`。

每個列出的 zone 都要有至少一個完整名稱。`wan1.example.com` 只更新 `example.com`。`example.net` 更新該 zone 的根。不要用 `@` 或沒有點的名稱，例如 `nas`，那些會套到每一個列出的 zone。手填 `CLOUDFLARE_ZONE_ID` 時，順序和個數要和 `DOMAIN` 相同。留空則用網域名稱查詢。清單中的名稱都會設成同一個目前公網位址。這個程式不讀取路由器的各別對外介面。

```yaml
DOMAIN: example.com,example.net
A_RECORDS: wan1.example.com,example.net
```

```bash
docker compose -f docker-compose.multi.yml up -d
docker compose -f docker-compose.multi.yml logs -f
```

#### 狀態頁

`WEB_UI` 預設關閉。設為 `true` 後，同一個程式在主機網路的 `WEB_PORT`（預設 `8080`）提供狀態頁。不要另加 `ports`。`WEB_UI` 為 `false` 時這個連接埠不會開啟。打開 `http://127.0.0.1:8080`。

頁面內容就是這一個容器的 `DOMAIN`。沒有切換。位址真的改變才寫入更換紀錄，最多 100 筆。演練不會寫入紀錄。

#### 演練

在使用中的 compose 把 `DRY_RUN` 設為 `"true"`，再用同一個 compose 檔重新啟動。日誌會列出準備新增、更新或刪除的紀錄，以及準備發送的通知文字，但不會呼叫 Cloudflare 的寫入 API。確認無誤後改回 `"false"`，再執行一次 `up -d`。

#### 常用指令

單一 zone：

```bash
docker compose logs -f
docker compose restart
docker compose down
```

64-bit Raspberry Pi 的單一 zone：

```bash
docker compose -f docker-compose.arm64.yml logs -f
docker compose -f docker-compose.arm64.yml restart
docker compose -f docker-compose.arm64.yml down
```

多個指定 zone：

```bash
docker compose -f docker-compose.multi.yml logs -f
docker compose -f docker-compose.multi.yml restart
docker compose -f docker-compose.multi.yml down
```

容器名稱是 `cloudflare-ddns`。程式收到 `SIGTERM` 或 `SIGINT` 會在目前這一輪結束後停止。

## 📖 完整說明

### 每一輪做什麼

1. 依 `RECORD_TYPES` 查詢。含 A 時向 `api4.ipify.org`、`ipv4.icanhazip.com`、`v4.ident.me` 查 IPv4。含 AAAA 時向 `api6.ipify.org`、`ipv6.icanhazip.com`、`v6.ident.me` 查 IPv6。沒選到的類型不會查。其中一個查詢站回「主機不可達」時，會改試下一個。整段網路沒有這個位址族的路由時才停止。
2. IPv4 略過私有位址、保留位址和 `100.64.0.0/10`。IPv6 略過本地、鏈路、說明用、6to4、Teredo 這類不能公布的位址。選中的某一邊查不到時，那一邊的紀錄保持原狀，另一邊照常更新。選中的類型全部失敗時，這一輪不改 DNS。
3. 把 `A_RECORDS` 裡的每個名稱設成這次查到的位址。只寫入 `RECORD_TYPES` 選中的類型。`CF_PROXIED` 為 false 時維持灰雲。為 true 時改成橙雲，流量經過 Cloudflare 代理。
4. 同一個名稱若是 CNAME，會刪掉並改成位址紀錄。同一類型若有多筆，優先保留已經指向目標位址的那筆，並刪除其餘。A 與 AAAA 互不覆蓋。
5. 只有位址本身改變時才發送 Apprise。只調整 TTL，或位址沒有變，都不發通知。同一輪裡 A 與 AAAA 的變更會合成一則通知。

位址與上次成功核對時相同時，這一輪不查 Cloudflare。最多每隔 `RECHECK_SECONDS`（預設一小時）仍會完整核對一次，所以在 Cloudflare 上手動改過的紀錄，最遲會在這個間隔內被改回。`DRY_RUN` 期間每輪都完整檢查。

查詢或 Cloudflare API 失敗時，既有紀錄保持原狀。

### 設定

變數寫在你啟動的那份 compose 的 `environment`。

| 變數 | 必填 | 預設 | 說明 |
| --- | --- | --- | --- |
| `CLOUDFLARE_API_TOKEN` | yes | | Cloudflare API token |
| `DOMAIN` | yes | | One domain, or comma-separated zones |
| `A_RECORDS` | no | apex | Names to update. `@` is only for one zone |
| `RECORD_TYPES` | no | `A,AAAA` | `A`, `AAAA`, or `A,AAAA` |
| `CLOUDFLARE_ZONE_ID` | no | lookup | Same order and count as `DOMAIN` |
| `INTERVAL_SECONDS` | no | `30` | Seconds between rounds. A positive integer |
| `RECHECK_SECONDS` | no | `3600` | Full Cloudflare check while the address is unchanged |
| `DNS_TTL` | no | `60` | TTL in seconds. Falls back to automatic TTL |
| `CF_PROXIED` | no | `false` | `true`, `1`, or `yes` enables the orange cloud |
| `DRY_RUN` | no | `false` | `true`, `1`, or `yes` logs changes without writing |
| `APPRISE_URLS` | no | empty | Notification URLs, separated by spaces |
| `WEB_UI` | no | `false` | `true` serves the status page |
| `WEB_PORT` | no | `8080` | Status page port. Closed while `WEB_UI` is false |

健康檢查要求大約 120 秒內至少成功完成一輪。`INTERVAL_SECONDS` 請維持在 90 秒以內。

### 通知

`APPRISE_URLS` 直接使用 [Apprise](https://github.com/caronc/apprise/wiki) 自己的網址格式，例如 Gotify 的 `gotifys://`、Discord 的 `discord://`。這個程式不會改寫這些網址。

```yaml
environment:
  APPRISE_URLS: gotifys://gotify.example.com/token
```

若通知是經過 Apprise API 伺服器送出，可填它的 HTTP 位址，程式會轉成 Apprise 能用的形式：

```text
https://apprise.example.com/notify/token
```

等於：

```text
apprises://apprise.example.com/token
```

多個目的地以空白分隔，可以混用不同服務。有一個網址無法辨識時會略過它，其餘照常發送。

位址改變時，通知以英文送出。標題是 `IP changed`。內容先寫目前查到的公網 IPv4 與 IPv6，再列出每個有變的紀錄、類型、舊位址和新位址。新紀錄顯示為 `(new record)`。

### 映像

在 GitHub 開啟 **Actions**，選擇 **Build image**，再按 **Run workflow**。這個工作只會在手動執行時跑。**Platform** 選 `amd64` 給一般電腦，選 `arm64` 給 64-bit Raspberry Pi OS（Pi 3、4、5、Zero 2 W）。32-bit 的 Raspberry Pi OS 不能用這個 `arm64` 映像。

```text
ghcr.io/wongkino/cloudflare-ddns:amd64
ghcr.io/wongkino/cloudflare-ddns:arm64
```

同一輪也會推上架構開頭的 commit 標籤、版本標籤，以及該架構的 latest。`amd64` 的版本像 `1.1.3`，`arm64` 的版本像 `1.1.3-arm64`。latest 分別是 `latest` 與 `latest-arm64`。**Version** 留空時，會把該架構現有最大版本的 patch 加一。還沒有版本標籤時從 `1.0.0` 開始。只有要指定版本時才填，例如 `2.0.0`。格式須為 `1.2`、`1.2.0`、`v1.2.0`，或在後面加 `-rc1` 這類後綴。

## 🧰 技術棧

- Python 3.14.8（Alpine），非 root 使用者 `10001`
- Apprise 2.0.1
- Cloudflare API v4
- Docker，`network_mode: host`
- 狀態頁是單一 HTML 檔，由同一個程式提供

## 📁 專案結構

```text
.
├── Dockerfile
├── LICENSE
├── README.md
├── README.zh-TW.md
├── updater.py
├── docker-compose.yml
├── docker-compose.arm64.yml
├── docker-compose.multi.yml
├── docs/
│   ├── status-multi.png
│   ├── status-phone.png
│   └── status-single.png
├── web/
│   ├── dev_server.py
│   ├── fixtures.py
│   ├── index.html
│   ├── server.py
│   └── snapshot.py
└── .github/workflows/docker-amd64.yml
```

## 🤝 貢獻指南

在 GitHub 開 issue 或 pull request。範例名稱請用 `example.com`。不要提交含有 token 的 compose 檔案。

## 📄 授權條款

[MIT](LICENSE)。Copyright (c) 2026 Kino Wong。
