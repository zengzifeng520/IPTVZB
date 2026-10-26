/* ============================================================
   光影直播 — 首页逻辑
   ============================================================ */
(function () {
  "use strict";

  // 部署后改成你的仓库地址，首页右上角会显示入口
  const REPO_URL = "https://github.com/zengzifeng520/ZZF";

  const state = {
    data: null,
    cat: "featured",
    q: "",
    list: [],
    shown: 0,
    pageSize: 180,
  };

  const el = {
    grid: document.getElementById("grid"),
    cats: document.getElementById("cats"),
    stats: document.getElementById("stats"),
    q: document.getElementById("q"),
    secTitle: document.getElementById("secTitle"),
    secSub: document.getElementById("secSub"),
    toast: document.getElementById("toast"),
    sentinel: document.getElementById("sentinel"),
  };

  const $ = (s) => document.querySelector(s);

  /* ---------------------------------------------------------- 工具 */
  function hashHue(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 131 + str.charCodeAt(i)) >>> 0;
    return h % 360;
  }

  // CCTV 系列拆成「CCTV / 数字」两行更像台标，其余取核心字
  function logoHTML(ch) {
    const key = ch.key || "";
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

  function qualityClass(q) {
    if (q === "8K") return "is8k";
    if (q === "4K") return "is4k";
    if (q === "1080P") return "is1080";
    if (q === "720P") return "is720";
    return "";
  }

  function toast(msg) {
    el.toast.textContent = msg;
    el.toast.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.toast.classList.remove("show"), 2200);
  }

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  /* ---------------------------------------------------------- 渲染 */
  function renderStats() {
    const s = state.data.stats;
    const items = [
      { n: s.channels, t: "个频道", accent: false },
      { n: s.streams, t: "条可用源", accent: false },
      { n: s.fhd, t: "个 1080P+", accent: false },
      { n: s.uhd, t: "个 4K/8K", accent: true },
    ];
    el.stats.innerHTML = items
      .map(
        (i) =>
          `<div class="stat${i.accent ? " accent" : ""}"><b>${i.n}</b><span>${i.t}</span></div>`
      )
      .join("");
  }

  function renderCats() {
    const cats = state.data.categories;
    const total = state.data.stats.channels;
    const featured = cats.filter((c) => c.key !== "地方频道");
    const featuredCount = featured.reduce((s, c) => s + c.count, 0);

    let html = `<button class="chip${state.cat === "featured" ? " active" : ""}" data-cat="featured">推荐<span class="n">${featuredCount}</span></button>`;
    for (const c of cats) {
      if (!c.count) continue;
      html += `<button class="chip${state.cat === c.key ? " active" : ""}" data-cat="${esc(
        c.key
      )}">${esc(c.name)}<span class="n">${c.count}</span></button>`;
    }
    html += `<button class="chip${state.cat === "all" ? " active" : ""}" data-cat="all">全部<span class="n">${total}</span></button>`;
    el.cats.innerHTML = html;
  }

  function filtered() {
    let list = state.data.channels;
    if (state.cat === "all") {
      list = list.slice();
    } else if (state.cat === "featured") {
      list = list.filter((c) => c.type !== "地方频道");
    } else {
      const cat = state.data.categories.find((c) => c.key === state.cat);
      if (cat) {
        const set = new Set(cat.channels);
        list = list.filter((c) => set.has(c.key));
      } else {
        list = [];
      }
    }
    const q = state.q.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (c) =>
          c.key.toLowerCase().includes(q) ||
          c.display.toLowerCase().includes(q) ||
          (c.type || "").toLowerCase().includes(q)
      );
    }
    return list;
  }

  function cardHTML(ch) {
    const q = ch.best.q;
    const n = ch.streams.length;
    return `<a class="ch" href="watch.html?c=${encodeURIComponent(ch.key)}" data-key="${esc(ch.key)}">
      <div class="ch-logo" style="--h:${hashHue(ch.key)}">
        ${logoHTML(ch)}
        <div class="ch-play"><span>
          <svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        </span></div>
      </div>
      <div class="ch-info">
        <div class="ch-name">${esc(ch.display)}</div>
        <div class="ch-tags">
          <span class="tag tag-q ${qualityClass(q)}">${q}</span>
          <span class="tag-n">${n} 源</span>
        </div>
      </div>
    </a>`;
  }

  function renderList(reset) {
    if (reset) {
      state.list = filtered();
      state.shown = 0;
      el.grid.innerHTML = "";
      const cat = state.data.categories.find((c) => c.key === state.cat);
      el.secTitle.textContent =
        state.cat === "all" ? "全部频道" : state.cat === "featured" ? "推荐频道" : cat ? cat.name : "频道";
      el.secSub.textContent = state.q
        ? `搜索 “${state.q}” · ${state.list.length} 个结果`
        : `${state.list.length} 个频道`;
    }
    if (!state.list.length) {
      el.grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>
        </svg>
        <h3>没有找到匹配的频道</h3>
        <p>换个关键词试试，比如 CCTV、卫视、凤凰</p>
      </div>`;
      return;
    }
    const next = state.list.slice(state.shown, state.shown + state.pageSize);
    el.grid.insertAdjacentHTML("beforeend", next.map(cardHTML).join(""));
    state.shown += next.length;
  }

  /* ---------------------------------------------------------- 事件 */
  el.cats.addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    state.cat = btn.dataset.cat;
    renderCats();
    renderList(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
    const url = new URL(location.href);
    if (state.cat === "featured") url.searchParams.delete("cat");
    else url.searchParams.set("cat", state.cat);
    history.replaceState(null, "", url);
  });

  let qTimer;
  el.q.addEventListener("input", () => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => {
      state.q = el.q.value;
      renderList(true);
    }, 160);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== el.q) {
      e.preventDefault();
      el.q.focus();
    }
    if (e.key === "Escape" && document.activeElement === el.q) {
      el.q.value = "";
      state.q = "";
      el.q.blur();
      renderList(true);
    }
  });

  // 滚动加载
  const io = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && state.shown < state.list.length) renderList(false);
    },
    { rootMargin: "600px" }
  );

  /* ---------------------------------------------------------- 启动 */
  function skeleton() {
    el.grid.innerHTML = Array.from({ length: 12 })
      .map(() => '<div class="skeleton"></div>')
      .join("");
  }

  async function boot() {
    skeleton();
    try {
      const res = await fetch("data/channels.json", { cache: "no-cache" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      state.data = await res.json();
    } catch (err) {
      el.grid.innerHTML = `<div class="empty" style="grid-column:1/-1">
        <h3>数据加载失败</h3>
        <p>请先运行采集脚本生成 data/channels.json（${esc(err.message)}）</p>
      </div>`;
      return;
    }

    const d = state.data;
    if (d.site && d.site.name) {
      document.title = `${d.site.name} · 全网直播源聚合`;
      $("#brandName").textContent = d.site.name;
      if (d.site.desc) $("#heroDesc").textContent = d.site.desc;
    }
    if (d.generated_at) $("#updAt").textContent = d.generated_at;

    if (REPO_URL) {
      const a = $("#repoLink");
      a.href = REPO_URL;
      $("#repoFoot").href = REPO_URL;
    } else {
      $("#repoLink").style.display = "none";
      $("#repoFoot").closest("p").style.display = "none";
    }

    const catParam = new URLSearchParams(location.href).get("cat");
    if (catParam && d.categories.some((c) => c.key === catParam)) state.cat = catParam;

    const qParam = new URLSearchParams(location.href).get("q");
    if (qParam) {
      el.q.value = qParam;
      state.q = qParam;
    }

    renderStats();
    renderCats();
    renderList(true);
    io.observe(el.sentinel);
    // 加载完再交一次，避免首屏不满一屏
    setTimeout(() => {
      if (state.shown < state.list.length && el.grid.scrollHeight < window.innerHeight * 1.5) {
        renderList(false);
      }
    }, 60);
  }

  boot();
})();
