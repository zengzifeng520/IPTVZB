/* 首页：账号状态 + 地区卡片 */
(function () {
  "use strict";

  var state = {
    proxy: null,
    regions: [],
    subs: null,
    user: null,
  };

  var el = {
    cta: document.getElementById("acctCtaInner"),
    stats: document.getElementById("stats"),
    grid: document.getElementById("regionGrid"),
    previewSub: document.getElementById("previewSub"),
    navAcct: document.getElementById("navAcct"),
    updAt: document.getElementById("updAt"),
    toast: document.getElementById("toast"),
  };

  /* ---------------------------------------------------------- 工具 */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var toastTimer = 0;
  function toast(msg) {
    el.toast.textContent = msg;
    el.toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      el.toast.classList.remove("show");
    }, 2400);
  }

  function regionName(key) {
    for (var i = 0; i < state.regions.length; i++) {
      if (state.regions[i].key === key) return state.regions[i].name;
    }
    return key || "—";
  }

  /* ---------------------------------------------------------- 赞助状态条 */

  function renderAccount() {
    var u = state.user;
    if (!u) return;

    el.navAcct.textContent = u.member ? "我的订阅" : "赞助解锁";
    el.navAcct.href = "account.html";

    if (u.member) {
      el.cta.innerHTML =
        '<div class="cta-row">' +
        '<div class="cta-text">' +
        '<h2><span class="pill pill-ok">已赞助</span> 全部 ' +
        state.regions.length +
        " 个地区已解锁</h2>" +
        "<p>有效期至 <b>" +
        esc(u.expText) +
        "</b>（剩 " +
        u.daysLeft +
        " 天）。到期后订阅会自动停止更新，再次赞助即可恢复。</p>" +
        "</div>" +
        '<div class="cta-acts">' +
        '<a class="btn btn-primary btn-lg" href="account.html">我的订阅</a>' +
        "</div>" +
        "</div>";
      return;
    }

    el.cta.innerHTML =
      '<div class="cta-row">' +
      '<div class="cta-text">' +
      "<h2>" +
      (u.expired ? "赞助已到期" : "免费可任选 1 个地区") +
      "</h2>" +
      "<p>" +
      (u.expired
        ? "你的赞助已于 <b>" +
          esc(u.lastExpText) +
          "</b> 到期，订阅地址已停止更新。再次赞助即可恢复。"
        : "频道地址可以随便看。不赞助也能拿 <b>1 个地区</b> 的订阅链接，但<b>免费订阅不保证有效性</b>；赞助后可稳定观看全部 " +
          state.regions.length +
          " 个地区，最低 <b>￥2</b> 起。") +
      "</p>" +
      "</div>" +
      '<div class="cta-acts">' +
      '<a class="btn btn-primary btn-lg" href="account.html">' +
      (u.expired ? "重新赞助" : "去赞助解锁全部") +
      "</a>" +
      '<a class="btn btn-lg" href="region.html">先看看频道</a>' +
      "</div>" +
      "</div>";
  }

  /* ---------------------------------------------------------- 统计 */

  function renderStats() {
    var s = (state.proxy && state.proxy.stats) || {};
    var items = [
      { n: s.hosts_alive || 0, t: "台中转服务器", accent: true },
      { n: s.channels || 0, t: "个频道", accent: false },
      { n: s.streams || 0, t: "条播放地址", accent: false },
      { n: state.regions.length || 0, t: "个地区", accent: false },
    ];
    el.stats.innerHTML = items
      .map(function (i) {
        return '<div class="stat' + (i.accent ? " accent" : "") + '"><b>' + i.n + "</b><span>" + i.t + "</span></div>";
      })
      .join("");
  }

  /* ---------------------------------------------------------- 地区卡片 */

  // 频道地址全部免费浏览，赞助只影响「订阅链接」
  function regionCard(r) {
    return (
      '<a class="region-card" href="#" data-r="' +
      esc(r.key) +
      '">' +
      '<div class="rc-head"><span class="rc-name">' +
      esc(r.name) +
      "</span>" +
      (r.isp ? '<span class="rc-isp">' + esc(r.isp) + "</span>" : "") +
      "</div>" +
      '<div class="rc-nums"><b>' +
      r.channels +
      "</b> 频道<span class=\"rc-dot\">·</span><b>" +
      r.streams +
      "</b> 条地址</div>" +
      '<div class="rc-foot"><span>' +
      (r.hosts || []).length +
      " 台服务器</span>" +
      '<span class="rc-go">查看频道 →</span></div>' +
      "</a>"
    );
  }

  function renderRegions() {
    if (!state.regions.length) {
      el.grid.innerHTML =
        '<div class="empty" style="grid-column:1/-1"><h3>暂无地区数据</h3><p>数据正在更新，稍后再试</p></div>';
      return;
    }
    el.grid.innerHTML = state.regions.map(regionCard).join("");
    el.previewSub.textContent =
      state.regions.length + " 个地区 · 每个地区一套独立的频道与订阅";
  }

  /* ---------------------------------------------------------- 交互 */

  el.grid.addEventListener("click", function (e) {
    var card = e.target.closest("[data-r]");
    if (!card) return;
    e.preventDefault();
    location.href = "region.html?r=" + encodeURIComponent(card.dataset.r);
  });

  /* ---------------------------------------------------------- 启动 */

  function boot() {
    state.user = window.IVAUTH.user();
    renderAccount();

    // 先从服务端同步赞助状态（换设备 / 站长补录后自动恢复）
    window.IVAUTH.syncSponsor().then(function (changed) {
      if (!changed) return;
      state.user = window.IVAUTH.user();
      renderAccount();
    });

    var jobs = [
      fetch("data/proxy.json", { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("proxy.json HTTP " + r.status);
        return r.json();
      }),
      fetch("data/regions.json", { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("regions.json HTTP " + r.status);
        return r.json();
      }),
    ];

    Promise.all(jobs)
      .then(function (res) {
        state.proxy = res[0];
        state.regions = (res[1].regions || []).slice().sort(function (a, b) {
          return b.streams - a.streams;
        });
        if (el.updAt) el.updAt.textContent = state.proxy.generated_at || "—";

        renderStats();
        renderRegions();
        // 账号状态条依赖 regions 长度，重新渲染一次
        renderAccount();
      })
      .catch(function (err) {
        el.grid.innerHTML =
          '<div class="empty" style="grid-column:1/-1"><h3>数据加载失败</h3><p>' +
          esc(err.message) +
          "</p></div>";
        el.stats.innerHTML = "";
      });
  }

  boot();
})();
