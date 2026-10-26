/* ============================================================
   光影直播 — 首页（Token 换取中转播放地址）
   ============================================================ */
(function () {
  "use strict";

  const REPO_URL = "https://github.com/zengzifeng520/ZZF";

  const state = {
    proxy: null,
    tokens: null,
    list: [],
    shown: 0,
    pageSize: 120,
    token: "",
  };

  const el = {
    form: document.getElementById("tokenForm"),
    input: document.getElementById("tokenInput"),
    err: document.getElementById("tokenErr"),
    stats: document.getElementById("stats"),
    grid: document.getElementById("grid"),
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

  function cardHTML(ch) {
    const n = ch.hosts.length;
    return `<a class="ch" href="#" data-ch="${esc(ch.key)}">
      <div class="ch-logo" style="--h:${hashHue(ch.key)}">
        ${logoHTML(ch)}
        <div class="ch-play"><span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
        </span></div>
      </div>
      <div class="ch-info">
        <div class="ch-name">${esc(ch.display)}</div>
        <div class="ch-tags">
          <span class="tag-n">${n} 台上线</span>
          <span class="tag-n">${ch.streams.length} 条</span>
        </div>
      </div>
    </a>`;
  }

  function renderPreview(reset) {
    if (reset) {
      state.shown = 0;
      el.grid.innerHTML = "";
      el.previewSub.textContent = `${state.proxy.stats.channels} 个频道，输入 Token 后可查看具体地址`;
    }
    const next = state.list.slice(state.shown, state.shown + state.pageSize);
    el.grid.insertAdjacentHTML("beforeend", next.map(cardHTML).join(""));
    state.shown += next.length;
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

  function gotoToken(raw, chKey) {
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
    const card = e.target.closest("[data-ch]");
    if (!card) return;
    e.preventDefault();
    const key = card.dataset.ch;
    if (state.token) {
      gotoToken(state.token, key);
    } else {
      el.input.focus();
      toast("请先输入 Token 查看地址");
      document.querySelector(".token-card").scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });

  const io = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && state.shown < state.list.length) renderPreview(false);
    },
    { rootMargin: "500px" }
  );

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
      const [pRes, tRes] = await Promise.all([
        fetch("data/proxy.json", { cache: "no-cache" }),
        fetch("data/tokens.json", { cache: "no-cache" }),
      ]);
      if (!pRes.ok) throw new Error("proxy.json HTTP " + pRes.status);
      state.proxy = await pRes.json();
      state.tokens = tRes.ok ? await tRes.json() : { tokens: {} };
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

    state.list = state.proxy.channels;
    renderStats();
    renderPreview(true);
    io.observe(document.querySelector(".preview"));
    setTimeout(() => {
      if (state.shown < state.list.length && el.grid.scrollHeight < window.innerHeight * 1.2) {
        renderPreview(false);
      }
    }, 80);
  }

  boot();
})();
