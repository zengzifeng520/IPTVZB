/* ============================================================
   光影直播 — Token 地址页
   ============================================================ */
(function () {
  "use strict";

  const REPO_URL = "https://github.com/zengzifeng520/ZZF";

  const state = {
    proxy: null,
    tokens: null,
    token: "",
    info: null,
    hostSet: new Set(),
    channels: [],
    filter: "",
  };

  const el = {
    badge: document.getElementById("tsBadge"),
    token: document.getElementById("tsToken"),
    meta: document.getElementById("tsMeta"),
    subUrl: document.getElementById("subUrl"),
    dlSub: document.getElementById("dlSub"),
    copySub: document.getElementById("copySub"),
    hostChips: document.getElementById("hostChips"),
    addrSub: document.getElementById("addrSub"),
    list: document.getElementById("list"),
    filter: document.getElementById("filter"),
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
  function copyText(text, okMsg) {
    const done = () => toast(okMsg || "已复制");
    const fallback = () => {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { toast("复制失败，请手动选择"); }
      document.body.removeChild(ta);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(fallback);
    } else { fallback(); }
  }
  function baseUrl() {
    return location.origin + location.pathname.replace(/[^/]*$/, "");
  }
  function hostLabel(h) {
    return h.split(":")[0];
  }

  /* ---------------------------------------------------------- 渲染 */
  function renderSummary() {
    const info = state.info;
    el.badge.textContent = info.n || "已授权";
    el.token.textContent = state.token;
    const parts = [
      `${info.hosts.length} 台中转服务器`,
      `${info.channels} 个频道`,
      `${info.streams} 条地址`,
    ];
    if (info.e) parts.push(`有效期至 ${info.e}`);
    el.meta.innerHTML = parts.map((p) => `<span>${esc(p)}</span>`).join("");

    const sub = baseUrl() + info.sub;
    el.subUrl.textContent = sub;
    el.dlSub.href = info.sub;

    el.hostChips.innerHTML = info.hosts
      .map((h) => `<span class="host-chip" title="${esc(h)}">${esc(hostLabel(h))}</span>`)
      .join("");
  }

  function buildChannels() {
    const hostSet = state.hostSet;
    const out = [];
    for (const ch of state.proxy.channels) {
      const picked = ch.streams.filter((s) => hostSet.has(s.h));
      if (picked.length) {
        out.push({ key: ch.key, display: ch.display, type: ch.type, streams: picked });
      }
    }
    // 按分类顺序（沿用 proxy.json 里已排好的顺序）
    return out;
  }

  function renderList() {
    const q = state.filter.trim().toLowerCase();
    const list = q
      ? state.channels.filter(
          (c) => c.display.toLowerCase().includes(q) || c.key.toLowerCase().includes(q) || (c.type || "").includes(q)
        )
      : state.channels;

    el.addrSub.textContent = q
      ? `匹配 ${list.length} 个频道`
      : `${state.channels.length} 个频道`;

    if (!list.length) {
      el.list.innerHTML = `<div class="empty"><h3>没有匹配的频道</h3><p>换个关键词试试</p></div>`;
      return;
    }

    el.list.innerHTML = list
      .map(
        (c) => `<details class="addr-item" ${q ? "open" : ""}>
          <summary>
            <span class="addr-name">${esc(c.display)}</span>
            <span class="addr-type">${esc(c.type || "")}</span>
            <span class="addr-count">${c.streams.length} 条</span>
          </summary>
          <div class="addr-urls">
            ${c.streams
              .map(
                (s) => `<div class="addr-url">
                  <span class="addr-host">${esc(hostLabel(s.h))}</span>
                  <code>${esc(s.u)}</code>
                  <button class="line-copy" data-url="${esc(s.u)}">复制</button>
                </div>`
              )
              .join("")}
          </div>
        </details>`
      )
      .join("");
  }

  /* ---------------------------------------------------------- 交互 */
  el.list.addEventListener("click", (e) => {
    const btn = e.target.closest(".line-copy");
    if (!btn) return;
    e.preventDefault();
    copyText(btn.dataset.url, "播放地址已复制");
  });

  el.copySub.addEventListener("click", () => {
    copyText(baseUrl() + state.info.sub, "订阅地址已复制");
  });

  let ft;
  el.filter.addEventListener("input", () => {
    clearTimeout(ft);
    ft = setTimeout(() => {
      state.filter = el.filter.value;
      renderList();
    }, 150);
  });

  /* ---------------------------------------------------------- 启动 */
  async function boot() {
    if (REPO_URL) document.getElementById("repoFoot").href = REPO_URL;

    const params = new URLSearchParams(location.search);
    const raw = (params.get("t") || "").trim();

    try {
      const [pRes, tRes] = await Promise.all([
        fetch("data/proxy.json", { cache: "no-cache" }),
        fetch("data/tokens.json", { cache: "no-cache" }),
      ]);
      state.proxy = await pRes.json();
      state.tokens = tRes.ok ? await tRes.json() : { tokens: {} };
    } catch (err) {
      el.list.innerHTML = `<div class="empty"><h3>数据加载失败</h3><p>${esc(err.message)}</p></div>`;
      return;
    }

    el.updAt.textContent = state.proxy.generated_at || "—";

    const map = state.tokens.tokens || {};
    let token = "";
    if (map[raw]) token = raw;
    else {
      const upper = raw.toUpperCase();
      token = Object.keys(map).find((k) => k.toUpperCase() === upper) || "";
    }

    if (!token) {
      el.badge.textContent = "无效";
      el.token.textContent = raw || "未提供 Token";
      el.meta.innerHTML = `<span style="color:var(--err)">Token 无效或已过期</span>`;
      el.list.innerHTML = `<div class="empty">
        <h3>无法获取播放地址</h3>
        <p>请确认 Token 输入正确，或返回首页重新输入</p>
        <p style="margin-top:16px"><a class="btn btn-primary" href="index.html">返回首页</a></p>
      </div>`;
      el.subUrl.textContent = "—";
      el.copySub.style.display = "none";
      el.dlSub.style.display = "none";
      return;
    }

    state.token = token;
    state.info = map[token];
    state.hostSet = new Set(state.info.hosts);

    renderSummary();
    state.channels = buildChannels();
    renderList();

    // 从首页点某个频道进来时，自动展开该频道
    const chKey = params.get("c");
    if (chKey) {
      const target = [...el.list.querySelectorAll(".addr-item")].find((n) =>
        n.querySelector(".addr-name")?.textContent.trim() === (state.proxy.channels.find((c) => c.key === chKey)?.display || "")
      );
      if (target) {
        target.open = true;
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
  }

  boot();
})();
