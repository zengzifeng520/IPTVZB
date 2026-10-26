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
    navLogout: document.getElementById("navLogout"),
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

  /* ---------------------------------------------------------- 账号状态条 */

  function renderAccount() {
    var u = state.user;

    if (!u) {
      el.navAcct.textContent = "登录 / 注册";
      el.navAcct.href = "login.html";
      if (el.navLogout) el.navLogout.hidden = true;
      el.cta.innerHTML =
        '<div class="cta-row">' +
        '<div class="cta-text">' +
        "<h2>用手机号登录，立即查看本省频道</h2>" +
        "<p>注册即得体验版，可查看 <b>1 个地区</b> 的全部频道地址。想解锁其余 10 个地区，扫码 ¥15 即可。</p>" +
        "</div>" +
        '<div class="cta-acts">' +
        '<a class="btn btn-primary btn-lg" href="login.html?tab=register">免费注册</a>' +
        '<a class="btn btn-lg" href="login.html">已有账号，登录</a>' +
        "</div>" +
        "</div>";
      return;
    }

    el.navAcct.textContent = u.member ? "会员中心" : "我的账号";
    el.navAcct.href = "account.html";
    if (el.navLogout) el.navLogout.hidden = false;

    if (u.member) {
      el.cta.innerHTML =
        '<div class="cta-row">' +
        '<div class="cta-text">' +
        '<h2><span class="pill pill-ok">会员</span> ' +
        esc(u.phoneMask) +
        "</h2>" +
        "<p>全部 " +
        state.regions.length +
        " 个地区已解锁，有效期至 <b>" +
        esc(u.expText) +
        "</b>。进任意地区即可复制订阅地址。</p>" +
        "</div>" +
        '<div class="cta-acts">' +
        '<a class="btn btn-primary btn-lg" href="account.html">我的订阅</a>' +
        "</div>" +
        "</div>";
    } else {
      el.cta.innerHTML =
        '<div class="cta-row">' +
        '<div class="cta-text">' +
        '<h2><span class="pill pill-warn">体验版</span> ' +
        esc(u.phoneMask) +
        "</h2>" +
        "<p>你现在可以查看 <b>" +
        esc(regionName(u.region)) +
        "</b> 的全部频道地址。扫码 ¥15 解锁全部 " +
        state.regions.length +
        " 个地区与 M3U 订阅。</p>" +
        "</div>" +
        '<div class="cta-acts">' +
        '<a class="btn btn-primary btn-lg" href="account.html">扫码解锁全部地区</a>' +
        '<a class="btn btn-lg" href="region.html?r=' +
        esc(u.region) +
        '">查看我的地区</a>' +
        "</div>" +
        "</div>";
    }
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

  function canOpen(key) {
    var u = state.user;
    if (!u) return false;
    return !!(u.member || u.region === key);
  }

  function regionCard(r) {
    var u = state.user;
    var open = canOpen(r.key);
    var isMine = u && u.region === r.key;
    var locked = !!u && !open;

    var goText = !u ? "登录后查看" : locked ? "开通后查看" : "查看频道 →";

    return (
      '<a class="region-card' +
      (locked ? " is-locked" : "") +
      (isMine ? " is-mine" : "") +
      '" href="#" data-r="' +
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
      '<span class="rc-go">' +
      (locked
        ? '<svg class="rc-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
        : "") +
      goText +
      "</span></div>" +
      (isMine ? '<span class="rc-badge">我的地区</span>' : "") +
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
    var key = card.dataset.r;
    var u = state.user;

    if (!u) {
      location.href = "login.html?next=" + encodeURIComponent("region.html?r=" + key);
      return;
    }
    if (u.member || u.region === key) {
      location.href = "region.html?r=" + encodeURIComponent(key);
      return;
    }
    toast("该地区需开通会员后查看");
    setTimeout(function () {
      location.href = "account.html";
    }, 900);
  });

  if (el.navLogout) {
    el.navLogout.addEventListener("click", function () {
      window.IVAUTH.logout();
      toast("已退出登录");
      setTimeout(function () {
        location.href = "index.html";
      }, 420);
    });
  }

  /* ---------------------------------------------------------- 启动 */

  function boot() {
    state.user = window.IVAUTH.user();
    renderAccount();

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
