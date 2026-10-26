/* 酒店源页：独立分类，不受地区限制（HLS 直连，全国可播） */
(function () {
  "use strict";

  var HOTEL_KEY = "hotel";

  var el = {
    badge: document.getElementById("tsBadge"),
    title: document.getElementById("tsRegion"),
    meta: document.getElementById("tsMeta"),
    side: document.getElementById("tsSide"),
    subSec: document.getElementById("subSec"),
    lockSec: document.getElementById("lockSec"),
    lockBody: document.getElementById("lockBody"),
    subTitle: document.getElementById("subTitle"),
    subDesc: document.getElementById("subDesc"),
    subTag: document.getElementById("subTag"),
    subUrl: document.getElementById("subUrl"),
    copySub: document.getElementById("copySub"),
    dlSub: document.getElementById("dlSub"),
    hostChips: document.getElementById("hostChips"),
    list: document.getElementById("list"),
    addrSub: document.getElementById("addrSub"),
    filter: document.getElementById("filter"),
    toast: document.getElementById("toast"),
    updAt: document.getElementById("updAt"),
    acctLink: document.getElementById("acctLink"),
  };

  var state = {
    user: null,
    pub: null, // data/public/hotel.json
    channels: [], // [{key, display, count, streams: []}]
    urls: null, // 会员地址表 {key: [[host, url], ...]}
    filter: "",
    subPath: "",
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

  function copyText(text, okMsg) {
    var done = function () {
      toast(okMsg || "已复制");
    };
    var fallback = function () {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        done();
      } catch (e) {
        toast("复制失败，请长按选择");
      }
      document.body.removeChild(ta);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(fallback);
    } else {
      fallback();
    }
  }

  function baseUrl() {
    return location.origin + location.pathname.replace(/[^/]*$/, "");
  }

  function hostLabel(h) {
    var p = String(h || "").split(":");
    var ip = p[0] || "";
    var seg = ip.split(".");
    var short = seg.length === 4 ? seg.slice(-2).join(".") : ip;
    return short + (p[1] ? ":" + p[1] : "");
  }

  var THUMB =
    '<svg class="ico-thumb" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
    '<path d="M2.8 10.4h2.6c.5 0 .9.4.9.9v8.3c0 .5-.4.9-.9.9H2.8c-.5 0-.9-.4-.9-.9v-8.3c0-.5.4-.9.9-.9Z"/>' +
    '<path d="M7.8 10.1 12 2.1c.2-.4.6-.7 1.1-.7 1.4 0 2.5 1.1 2.5 2.5v4.4h4.2c1.4 0 2.4 1.3 2.1 2.6l-1.3 6.7c-.2 1.1-1.2 1.9-2.3 1.9H7.8V10.1Z"/>' +
    "</svg>";

  /* ---------------------------------------------------------- 渲染 */

  /** 公开地址表：data/public/urls/hotel.json，任何人都能拿 */
  function loadUrls() {
    fetch("data/public/urls/" + HOTEL_KEY + ".json", { cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (m) {
        state.urls = m || {};
        var hostSet = {};
        state.channels.forEach(function (c) {
          var arr = state.urls[c.key] || [];
          c.streams = arr.map(function (p) {
            hostSet[p[0]] = true;
            return { h: p[0], u: p[1] };
          });
        });
        state.hostSet = hostSet;
        renderSubscribe();
        renderList();
      })
      .catch(function () {});
  }

  function renderSummary() {
    var s = (state.pub && state.pub.stats) || {};
    var nChan = state.channels.length;
    var nStream = s.streams || 0;
    var nHost = s.hosts || 0;

    el.badge.textContent = "地址免费";
    el.badge.className = "ts-badge is-ok";
    el.title.textContent = "酒店源";
    el.meta.innerHTML =
      "<span>" +
      nChan +
      " 个频道</span><span>" +
      nStream +
      " 条地址</span><span>" +
      nHost +
      " 台服务器</span>";

    el.side.innerHTML =
      '<span class="ts-side-tip">喜欢就支持一下</span>' +
      '<a class="btn btn-primary" href="account.html">' + THUMB + '支持一下作者</a>';
  }

  function renderSubscribe() {
    // 订阅链接统一收在「支持一下作者」页；这里只给入口
    var s = (state.pub && state.pub.stats) || {};

    el.subSec.hidden = true;
    el.lockSec.hidden = false;
    state.subPath = "";

    if (el.lockBody) {
      el.lockBody.innerHTML =
        "<h2>订阅地址在「支持一下作者」页</h2>" +
        "<p>本页可以直接查看并复制酒店源的全部播放地址；<br>" +
        "M3U 订阅链接（全量 / 酒店源 / 分地区）统一放在支持一下作者页面，<b>免费、无需付款</b>。</p>" +
        '<a class="btn btn-primary btn-lg" href="account.html" style="margin-top:6px">去订阅地址页</a>';
    }
  }

  function renderList() {
    var q = state.filter.trim().toLowerCase();
    var list = q
      ? state.channels.filter(function (c) {
          return (
            c.display.toLowerCase().indexOf(q) >= 0 ||
            c.key.toLowerCase().indexOf(q) >= 0
          );
        })
      : state.channels;

    var s = (state.pub && state.pub.stats) || {};
    el.addrSub.textContent = q
      ? "匹配 " + list.length + " 个频道"
      : state.channels.length + " 个频道 / " + (s.streams || 0) + " 条地址";

    if (!list.length) {
      el.list.innerHTML = '<div class="empty"><h3>没有匹配的频道</h3><p>换个关键词试试</p></div>';
      return;
    }

    el.list.innerHTML = list
      .map(function (c) {
        var streams = c.streams || [];
        if (!streams.length) {
          return (
            '<details class="addr-item" data-key="' +
            esc(c.key) +
            '"' +
            (q ? " open" : "") +
            "><summary>" +
            '<span class="addr-name">' +
            esc(c.display) +
            "</span>" +
            '<span class="addr-type">HLS</span>' +
            '<span class="addr-count">' +
            (c.count || 0) +
            " 条</span></summary>" +
            '<div class="addr-urls"><div style="padding:12px 14px;font-size:13px;opacity:.72">' +
            "地址加载中…" +
            "</div></div></details>"
          );
        }
        return (
          '<details class="addr-item" data-key="' +
          esc(c.key) +
          '"' +
          (q ? " open" : "") +
          "><summary>" +
          '<span class="addr-name">' +
          esc(c.display) +
          "</span>" +
          '<span class="addr-type">HLS</span>' +
          '<span class="addr-count">' +
          streams.length +
          " 条</span></summary>" +
          '<div class="addr-urls">' +
          streams
            .map(function (s) {
              return (
                '<div class="addr-url">' +
                '<span class="addr-host">' +
                esc(hostLabel(s.h)) +
                "</span>" +
                "<code>" +
                esc(s.u) +
                "</code>" +
                '<button class="line-copy" data-url="' +
                esc(s.u) +
                '">复制</button></div>'
              );
            })
            .join("") +
          "</div></details>"
        );
      })
      .join("");
  }

  /* ---------------------------------------------------------- 交互 */

  el.list.addEventListener("click", function (e) {
    var btn = e.target.closest(".line-copy");
    if (!btn) return;
    e.preventDefault();
    copyText(btn.dataset.url, "播放地址已复制");
  });

  el.copySub.addEventListener("click", function () {
    if (!state.subPath) return toast("订阅地址不可用");
    copyText(baseUrl() + state.subPath, "订阅地址已复制");
  });

  var ft = 0;
  el.filter.addEventListener("input", function () {
    clearTimeout(ft);
    ft = setTimeout(function () {
      state.filter = el.filter.value;
      renderList();
    }, 150);
  });

  /* ---------------------------------------------------------- 启动 */

  function fail(msg, detail) {
    el.list.innerHTML =
      '<div class="empty"><h3>' +
      esc(msg) +
      "</h3><p>" +
      esc(detail || "") +
      '</p><p style="margin-top:16px"><a class="btn btn-primary" href="index.html">返回首页</a></p></div>';
  }

  function boot() {
    state.user = window.IVAUTH.user();
    el.acctLink.innerHTML = THUMB + "支持一下作者";

    fetch("data/public/hotel.json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("hotel.json HTTP " + r.status);
        return r.json();
      })
      .then(function (pub) {
        state.pub = pub;
        if (el.updAt) el.updAt.textContent = pub.generated_at || "—";

        state.channels = (pub.channels || []).map(function (c) {
          return {
            key: c.key,
            display: c.display,
            count: c.count || 0,
            streams: [],
          };
        });

        if (!state.channels.length) return fail("酒店源数据为空", "请稍后刷新重试");

        renderSummary();
        renderSubscribe();
        renderList();

        loadUrls();
      })
      .catch(function (err) {
        fail("数据加载失败", err.message);
      });
  }

  boot();
})();
