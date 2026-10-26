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
    heroNums: document.getElementById("heroNums"),
    grid: document.getElementById("regionGrid"),
    previewSub: document.getElementById("previewSub"),
    navAcct: document.getElementById("navAcct"),
    updAt: document.getElementById("updAt"),
    hotelEntry: document.getElementById("hotelEntry"),
    hotelNums: document.getElementById("hotelNums"),
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
        : "频道名可以免费看，但 <b>播放地址需赞助后显示</b>。免费可先拿 <b>1 个地区</b> 的订阅试用，<b>有效期 7 天</b>，到期自动失效；赞助后解锁全部 " +
          state.regions.length +
          " 个地区与所有地址。") +
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
    // 组播中转与酒店源分开显示：前者挑地区，后者全国通用
    var items = [
      { n: s.relayHosts || 0, t: "台组播中转", accent: true },
      { n: s.hotelHosts || 0, t: "台酒店源", accent: false },
      { n: s.channelsTotal || s.channels || 0, t: "个频道", accent: false },
      { n: s.streamsTotal || s.streams || 0, t: "条播放地址", accent: false },
    ];
    el.stats.innerHTML = items
      .map(function (i) {
        return '<div class="stat' + (i.accent ? " accent" : "") + '"><b>' + i.n + "</b><span>" + i.t + "</span></div>";
      })
      .join("");

    // 首页标题里的数字跟着池子走，新增地区/频道不用再改文案
    if (el.heroNums) {
      el.heroNums.textContent =
        (state.regions.length || 0) + " 个地区、" + (s.channelsTotal || s.channels || 0) + " 个频道";
    }
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

    // 公开数据里只有频道名与条数，没有任何播放地址
    var jobs = [
      fetch("data/public/channels.json", { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("channels.json HTTP " + r.status);
        return r.json();
      }),
    ];

    Promise.all(jobs)
      .then(function (res) {
        state.pub = res[0];
        state.proxy = { stats: res[0].stats || {}, generated_at: res[0].generated_at };
        state.regions = (res[0].regions || []).slice().sort(function (a, b) {
          return b.streams - a.streams;
        });
        if (el.updAt) el.updAt.textContent = state.proxy.generated_at || "—";

        renderStats();
        renderRegions();

        // 酒店源是独立分类：用 stats 里的数字填充入口卡片
        var hs = res[0].stats || {};
        if (el.hotelEntry && hs.hotelStreams) {
          el.hotelEntry.hidden = false;
          if (el.hotelNums) {
            el.hotelNums.textContent =
              (hs.hotelHosts || 0) + " 台、" + (hs.hotelChannels || 0) + " 个频道";
          }
        }

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
