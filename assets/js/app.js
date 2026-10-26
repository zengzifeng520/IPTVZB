/* ============================================================
   光影直播 — 首页（Token 换取中转播放地址）
   ============================================================ */
(function () {
  "use strict";

  const REPO_URL = "https://github.com/zengzifeng520/ZZF";

  const state = {
    proxy: null,
    tokens: null,
    regions: [],
    token: "",
  };

  const el = {
    form: document.getElementById("tokenForm"),
    input: document.getElementById("tokenInput"),
    err: document.getElementById("tokenErr"),
    stats: document.getElementById("stats"),
    grid: document.getElementById("regionGrid"),
    previewSub: document.getElementById("previewSub"),
    toast: document.getElementById("toast"),
    updAt: document.getElementById("updAt"),
  };

  /* ---------------------------------------------------------- 工具 */
  function toast(msg) {
    el.toast.textContent = msg;
    el.toast.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.toast.classList.remove("show"), 2200);
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function hashHue(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 131 + str.charCodeAt(i)) >>> 0;
    return h % 360;
  }
  function logoHTML(ch) {
    const key = ch.key || ch.display || "";
    let m = key.match(/^CCTV(\d+)(\+?)$/);
    if (m) return `<span class="ch-logo-text is-cctv"><i>CCTV</i><b>${m[1]}${m[2]}</b></span>`;
    m = key.match(/^CCTV(4|8)K$/);
    if (m) return `<span class="ch-logo-text is-cctv"><i>CCTV</i><b>${m[1]}K</b></span>`;
    if (/^CCTV/.test(key)) return `<span class="ch-logo-text is-long">${esc(key)}</span>`;
    if (/^CGTN/.test(key)) {
      const tail = key.slice(4);
      if (!tail) return `<span class="ch-logo-text">CGTN</span>`;
      return `<span class="ch-logo-text is-cctv"><i>CGTN</i><b>${esc(tail)}</b></span>`;
    }
    let t = key.replace(/(卫视|频道|电视台|台)$/g, "");
    if (t.length > 6) t = t.slice(0, 6);
    return `<span class="ch-logo-text">${esc(t || key)}</span>`;
  }

  /* ---------------------------------------------------------- 渲染 */
  function renderStats() {
    const s = state.proxy.stats;
    const items = [
      { n: s.hosts_alive, t: "台中转服务器", accent: true },
      { n: s.channels, t: "个频道", accent: false },
      { n: s.streams, t: "条播放地址", accent: false },
      { n: Object.keys(state.tokens?.tokens || {}).length, t: "个可用 Token", accent: false },
    ];
    el.stats.innerHTML = items
      .map((i) => `<div class="stat${i.accent ? " accent" : ""}"><b>${i.n}</b><span>${i.t}</span></div>`)
      .join("");
  }

  /* ---------------------------------------------------------- 地区卡片 */
  /** 找一个覆盖该地区、且地址最多的 Token，用于卡片直达 */
  function tokenForRegion(code) {
    const map = state.tokens?.tokens || {};
    let best = "";
    let bestN = -1;
    for (const [tk, info] of Object.entries(map)) {
      for (const r of info.regions || []) {
        if (r.k === code && r.streams > bestN) {
          bestN = r.streams;
          best = tk;
        }
      }
    }
    return best;
  }

  function regionCard(r) {
    const tk = tokenForRegion(r.key);
    const isp = r.isp ? `<span class="rc-isp">${esc(r.isp)}</span>` : "";
    return `<a class="region-card${tk ? "" : " is-off"}" href="#" data-r="${esc(r.key)}" data-t="${esc(tk)}">
      <div class="rc-head"><span class="rc-name">${esc(r.name)}</span>${isp}</div>
      <div class="rc-nums"><b>${r.channels}</b> 频道<span class="rc-dot">·</span><b>${r.streams}</b> 条地址</div>
      <div class="rc-foot">
        <span>${r.hosts.length} 台服务器</span>
        <span class="rc-go">${tk ? "查看订阅 →" : "暂无订阅"}</span>
      </div>
    </a>`;
  }

  function renderRegions() {
    const list = state.regions;
    if (!list.length) {
      el.grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <h3>暂无地区数据</h3><p>数据正在更新，稍后再试</p></div>`;
      return;
    }
    el.grid.innerHTML = list.map(regionCard).join("");
    el.previewSub.textContent = `${list.length} 个地区 · 每个地区一套独立订阅`;
  }

  /* ---------------------------------------------------------- Token */
  function normalizeToken(v) {
    return (v || "").trim().toUpperCase();
  }

  function findToken(raw) {
    const t = normalizeToken(raw);
    const map = state.tokens?.tokens || {};
    if (map[t]) return t;
    return Object.keys(map).find((k) => k.toUpperCase() === t) || "";
  }

  function gotoToken(raw, chKey, region) {
    const t = findToken(raw);
    if (!t) {
      el.err.textContent = raw ? "Token 无效或已过期，请检查后重试" : "请输入 Token";
      el.input.focus();
      return;
    }
    el.err.textContent = "";
    try {
      localStorage.setItem("iptv_token", t);
    } catch (e) {}
    const url = new URL("token.html", location.href);
    url.searchParams.set("t", t);
    if (chKey) url.searchParams.set("c", chKey);
    if (region && region !== "all") url.searchParams.set("r", region);
    location.href = url.toString();
  }

  el.form.addEventListener("submit", (e) => {
    e.preventDefault();
    gotoToken(el.input.value);
  });

  document.querySelectorAll("[data-demo]").forEach((btn) => {
    btn.addEventListener("click", () => {
      el.input.value = btn.dataset.demo;
      gotoToken(btn.dataset.demo);
    });
  });

  el.input.addEventListener("input", () => {
    el.err.textContent = "";
  });

  el.grid.addEventListener("click", (e) => {
    const card = e.target.closest("[data-r]");
    if (!card) return;
    e.preventDefault();
    const token = card.dataset.t || state.token || el.input.value;
    if (!token) {
      el.input.focus();
      toast("请先输入 Token 查看该地区订阅");
      document.querySelector(".token-card").scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    gotoToken(token, null, card.dataset.r);
  });

  /* ---------------------------------------------------------- 启动 */
  async function boot() {
    if (REPO_URL) {
      document.getElementById("repoLink").href = REPO_URL;
      document.getElementById("repoFoot").href = REPO_URL;
    } else {
      document.getElementById("repoLink").style.display = "none";
      document.getElementById("repoFoot").closest("p").style.display = "none";
    }

    try {
      const [pRes, tRes, rRes] = await Promise.all([
        fetch("data/proxy.json", { cache: "no-cache" }),
        fetch("data/tokens.json", { cache: "no-cache" }),
        fetch("data/regions.json", { cache: "no-cache" }),
      ]);
      if (!pRes.ok) throw new Error("proxy.json HTTP " + pRes.status);
      state.proxy = await pRes.json();
      state.tokens = tRes.ok ? await tRes.json() : { tokens: {} };
      state.regions = rRes.ok ? (await rRes.json()).regions || [] : [];
    } catch (err) {
      el.grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <h3>数据加载失败</h3><p>${esc(err.message)}</p></div>`;
      return;
    }

    el.updAt.textContent = state.proxy.generated_at || "—";
    try {
      state.token = localStorage.getItem("iptv_token") || "";
      if (state.token) el.input.value = state.token;
    } catch (e) {}

    renderStats();
    renderRegions();
  }

  boot();
})();
