const COPY = {
  "zh-Hant": {
    group: "語言",
    loading: "讀取中",
    dryRun: "演練",
    running: "運作中",
    notStarted: "尚未開始",
    proxied: "橙雲",
    dnsOnly: "灰雲",
    checked: "上次核對",
    ipv4: "目前公網 IPv4",
    ipv6: "目前公網 IPv6",
    notChecked: "尚未核對",
    records: "監視中的紀錄",
    history: "更換紀錄",
    newRecord: "新紀錄",
    noAddress: "這個 zone 沒有可顯示的位址",
    noZone: "尚未設定 zone",
    noHistory: "還沒有更換紀錄",
  },
  "zh-Hans": {
    group: "语言",
    loading: "读取中",
    dryRun: "演练",
    running: "运行中",
    notStarted: "尚未开始",
    proxied: "橙云",
    dnsOnly: "灰云",
    checked: "上次核对",
    ipv4: "当前公网 IPv4",
    ipv6: "当前公网 IPv6",
    notChecked: "尚未核对",
    records: "监视中的记录",
    history: "更换记录",
    newRecord: "新记录",
    noAddress: "这个 zone 没有可显示的地址",
    noZone: "尚未设定 zone",
    noHistory: "还没有更换记录",
  },
  en: {
    group: "Language",
    loading: "Loading",
    dryRun: "Dry run",
    running: "Running",
    notStarted: "Not started",
    proxied: "Proxied",
    dnsOnly: "DNS only",
    checked: "Last check",
    ipv4: "Public IPv4",
    ipv6: "Public IPv6",
    notChecked: "Not checked yet",
    records: "Watched records",
    history: "Changes",
    newRecord: "New record",
    noAddress: "This zone has no address to show",
    noZone: "No zone configured",
    noHistory: "No changes yet",
  },
};

const live = document.querySelector("#live");
const dot = document.querySelector("#dot");
const metrics = document.querySelector("#metrics");
const zones = document.querySelector("#zones");
const history = document.querySelector("#history");
const lang = document.querySelector("#lang");
let language = "zh-Hant";
let current = null;

function t(key) {
  return COPY[language][key];
}

function text(value) {
  return String(value ?? "");
}

function escape(value) {
  return text(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function clock(value) {
  if (!value) return t("notChecked");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function ip(value) {
  return escape(value).replaceAll(":", ":<wbr>");
}

function before(value) {
  return value ? ip(value) : escape(t("newRecord"));
}

function applyLanguage(next) {
  language = COPY[next] ? next : "zh-Hant";
  localStorage.setItem("cloudflare-ddns-lang", language);
  document.documentElement.lang = language;
  lang.setAttribute("aria-label", t("group"));
  for (const button of lang.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.lang === language));
  }
  document.querySelector("#records-title").textContent = t("records");
  document.querySelector("#history-title").textContent = t("history");
  if (current) render(current);
  else live.textContent = t("loading");
}

function render(data) {
  current = data;
  dot.classList.toggle("wait", !data.watching);
  const mode = data.dry_run ? t("dryRun") : data.watching ? t("running") : t("notStarted");
  const cloud = data.proxied ? t("proxied") : t("dnsOnly");
  const checked = data.updated_at
    ? `<span class="checked"><span class="sep"> · </span>${escape(t("checked"))} ${escape(clock(data.updated_at))}</span>`
    : "";
  live.innerHTML = `${escape(mode)} · ${escape(cloud)}${checked}`;
  const addresses = data.addresses || {};
  const types = data.types && data.types.length ? data.types : ["A", "AAAA"];
  metrics.innerHTML = types.map((kind) => {
    const label = kind === "A" ? t("ipv4") : t("ipv6");
    const shown = addresses[kind] ? ip(addresses[kind]) : escape(t("notChecked"));
    return `<article class="metric"><span>${escape(label)}</span><strong>${shown}</strong></article>`;
  }).join("");
  zones.innerHTML = (data.zones || []).map((zone) => {
    const rows = (zone.names || []).flatMap((name) => types.map((kind) => `
      <div class="row">
        <div class="identity"><span class="name">${escape(name)}</span><span class="kind">${kind}</span></div>
        <span class="address">${addresses[kind] ? ip(addresses[kind]) : escape(t("notChecked"))}</span>
      </div>`)).join("");
    return `<article class="card"><header><span class="name">${escape(zone.domain)}</span><span class="cloud">${escape(cloud)}</span></header>${rows || `<p class="empty">${escape(t("noAddress"))}</p>`}</article>`;
  }).join("") || `<p class="empty">${escape(t("noZone"))}</p>`;
  const items = data.history || [];
  history.innerHTML = items.length
    ? `<div class="stack">${items.map((item) => `
    <article class="change">
      <div>
        <div class="identity"><span class="name">${escape(item.name)}</span><span class="kind">${escape(item.type)}</span></div>
        <p>${before(item.before)} → <b>${ip(item.after)}</b></p>
      </div>
      <time class="when">${escape(clock(item.at))}</time>
    </article>`).join("")}</div>`
    : `<p class="empty">${escape(t("noHistory"))}</p>`;
}

lang.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  applyLanguage(button.dataset.lang);
});

async function load() {
  const response = await fetch("/api/status", { cache: "no-store" });
  render(await response.json());
}

applyLanguage(localStorage.getItem("cloudflare-ddns-lang") || "zh-Hant");
load();
setInterval(load, 5000);
