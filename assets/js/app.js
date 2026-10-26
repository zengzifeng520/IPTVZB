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
    playWelcome: document.getElementById("playWelcome"),
    playIco: document.getElementById("playIco"),
    playTxt: document.getElementById("playTxt"),
    vinylDisc: document.getElementById("vinylDisc"),
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

  /* ---------------------------------------------------------- 欢迎语音（Web Speech TTS） */
  var WELCOME_TEXT =
    "欢迎使用本站 IPTV 直播源。本站自动采集全国各省市的组播直播源与酒店源，" +
    "过滤低分辨率、保留高清，每小时自动巡检更新。播放地址与订阅全部免费，如果喜欢请支持一下作者，祝您观看愉快。";

  function initWelcomeVoice() {
    if (!el.playWelcome) return;
    var speaking = false;

    function setState(playing) {
      speaking = playing;
      if (el.vinylDisc) el.vinylDisc.classList.toggle("is-playing", playing);
      el.playIco.textContent = playing ? "■" : "▶";
      el.playTxt.textContent = playing ? "正在播放欢迎语…" : "点击黑胶播放欢迎语";
    }

    el.playWelcome.addEventListener("click", function () {
      if (!("speechSynthesis" in window)) {
        toast("当前浏览器不支持语音播放");
        return;
      }
      if (speaking) {
        speechSynthesis.cancel();
        setState(false);
        return;
      }
      var u = new SpeechSynthesisUtterance(WELCOME_TEXT);
      u.lang = "zh-CN";
      u.rate = 0.95;
      u.onstart = function () { setState(true); };
      u.onend = function () { setState(false); };
      u.onerror = function () { setState(false); };
      speechSynthesis.cancel();
      speechSynthesis.speak(u);
    });
  }

  function regionName(key) {
    for (var i = 0; i < state.regions.length; i++) {
      if (state.regions[i].key === key) return state.regions[i].name;
    }
    return key || "—";
  }

  /* ---------------------------------------------------------- 打赏状态条 */

  function renderAccount() {
    var u = state.user;
    if (!u) return;

    el.navAcct.textContent = "喜欢作者，请支持一下 👍";
    el.navAcct.href = "account.html";

    el.cta.innerHTML =
      '<div class="cta-row">' +
      '<div class="cta-text">' +
      "<h2>喜欢作者，请支持一下 👍</h2>" +
      "<p>本站<b>全部免费</b>——播放地址、M3U 订阅都能直接看、直接下，不设付费墙。" +
      "服务器与带宽有成本，如果觉得好用，欢迎<b>请作者喝杯咖啡</b>，多少都是心意。</p>" +
      "</div>" +
      '<div class="cta-acts">' +
      '<a class="btn btn-primary btn-lg" href="account.html">支持一下作者</a>' +
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

  // 频道地址与订阅全部免费浏览
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
    initWelcomeVoice();

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
