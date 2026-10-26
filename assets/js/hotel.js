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

  function isMember() {
    return !!(state.user && state.user.member);
  }

  /* ---------------------------------------------------------- 渲染 */

  /** 会员地址表：data/users/<token>/urls/hotel.json（只对会员存在） */
  function loadUrls() {
    var tok = state.user && state.user.sid ? window.IVAUTH.tokenOf(state.user.sid) : "";
    if (!tok) return;
    fetch("data/users/" + tok + "/urls/" + HOTEL_KEY + ".json", { cache: "no-store" })
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

    el.badge.textContent = isMember()
      ? (state.user.planName || "已赞助") + " · 订阅已解锁"
      : state.user.expired
        ? "赞助已到期"
        : "免费浏览";
    el.badge.className = "ts-badge" + (isMember() ? " is-ok" : state.user.expired ? " is-expired" : "");
    el.title.textContent = "酒店源";
    el.meta.innerHTML =
      "<span>" +
      nChan +
      " 个频道</span><span>" +
      nStream +
      " 条地址</span><span>" +
      nHost +
      " 台服务器</span>";

    if (isMember()) {
      el.side.innerHTML =
        '<span class="ts-side-tip">有效期至 ' + esc(state.user.expText) + "</span>" +
        '<a class="btn" href="account.html">我的订阅</a>';
    } else {
      el.side.innerHTML =
        '<span class="ts-side-tip">地址可免费查看</span>' +
        '<a class="btn btn-primary" href="account.html">' +
        (state.user.expired ? "重新赞助" : "赞助解锁订阅") +
        "</a>";
    }
  }

  function renderSubscribe() {
    var member = isMember();
    var freeKey = window.IVAUTH.freeRegion();
    var freeOk = window.IVAUTH.freeValid();
    // 赞助用户可用；免费用户只有把免费地区选成「酒店源」且未过期才能用
    var canUse = member || (freeKey === HOTEL_KEY && freeOk);

    el.subSec.hidden = !canUse;
    el.lockSec.hidden = canUse;

    if (!canUse) {
      renderLock(freeKey, freeOk);
      return;
    }

    var s = (state.pub && state.pub.stats) || {};
    var token = state.user && state.user.sid ? window.IVAUTH.tokenOf(state.user.sid) : "";

    if (member && token) {
      state.subPath = "data/users/" + token + "/" + HOTEL_KEY + ".m3u";
      el.subTitle.textContent = "酒店源专属订阅地址";
      el.subDesc.textContent =
        "这是你专属的订阅地址，请勿分享。赞助到期后该地址会自动停止更新，播放器刷新后频道将为空。";
      el.subTag.textContent = "酒店源 · " + (s.channels || 0) + " 频道 / " + (s.streams || 0) + " 条";
    } else {
      var dir = window.IVAUTH.freeDir();
      state.subPath = "data/free/" + dir + "/" + HOTEL_KEY + ".m3u";
      el.subTitle.textContent = "酒店源免费订阅（7 天）";
      el.subDesc.textContent =
        "免费订阅有效期至 " +
        window.IVAUTH.fmtDate(window.IVAUTH.freeExpire()) +
        "，到期后这条链接自动失效。免费为公共线路，不保证稳定性；赞助后可拿专属订阅并查看全部播放地址。";
      el.subTag.textContent = "酒店源 · " + (s.channels || 0) + " 频道 / " + (s.streams || 0) + " 条";
    }
    el.subUrl.textContent = baseUrl() + state.subPath;
    el.dlSub.href = state.subPath;

    // 主机列表：公开目录有就给公开的，否则会员态从地址表里提取
    var hosts = (state.pub && state.pub.hosts) || [];
    if (!hosts.length && state.hostSet) {
      hosts = Object.keys(state.hostSet);
    }
    el.hostChips.innerHTML = hosts
      .map(function (h) {
        return '<span class="host-chip" title="' + esc(h) + '">' + esc(hostLabel(h)) + "</span>";
      })
      .join("");
  }

  function renderLock(freeKey, freeOk) {
    // 没选过免费地区
    if (!freeKey) {
      el.lockBody.innerHTML =
        "<h2>免费版可以先选酒店源试用</h2>" +
        "<p>不赞助只能看到频道名，<b>拿不到播放地址</b>。可以把酒店源选为免费订阅试用，有效期 <b>7 天</b>，到期自动失效。<br>" +
        "赞助后可查看全部播放地址，并拿到长期有效的专属订阅。</p>" +
        '<button class="btn btn-primary btn-lg" type="button" data-act="pick" style="margin-top:6px">免费选酒店源试用</button>' +
        '<a class="btn btn-lg" href="account.html" style="margin-top:8px">直接赞助解锁全部</a>';
      return;
    }

    // 选过但已经到期
    if (freeKey === HOTEL_KEY && !freeOk) {
      el.lockBody.innerHTML =
        "<h2>免费订阅已到期</h2>" +
        "<p>你的酒店源 7 天免费订阅已于 " +
        esc(window.IVAUTH.fmtDate(window.IVAUTH.freeExpire())) +
        " 到期，链接已失效。<br>赞助后可查看全部播放地址，并拿到长期有效的专属订阅。</p>" +
        '<a class="btn btn-primary btn-lg" href="account.html" style="margin-top:6px">去赞助解锁</a>';
      return;
    }

    // 选的是别的省
    el.lockBody.innerHTML =
      "<h2>你的免费地区不是酒店源</h2>" +
      "<p>你的免费订阅是地区组播（7 天），酒店源需要赞助后使用。<br>" +
      "酒店源不限地区、全国可播，赞助后即可解锁全部播放地址与专属订阅。</p>" +
      '<a class="btn btn-primary btn-lg" href="account.html" style="margin-top:6px">赞助解锁酒店源</a>' +
      '<a class="btn btn-lg" href="region.html" style="margin-top:8px">去看我的免费地区</a>';
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

    // 未赞助：只给频道名和条数，播放地址一律不输出到页面
    if (!isMember()) {
      el.list.innerHTML = list
        .map(function (c) {
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
            "播放地址需赞助后显示 · " +
            '<a href="account.html" style="color:inherit;text-decoration:underline">去赞助解锁</a>' +
            "</div></div></details>"
          );
        })
        .join("");
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

  // 免费版选酒店源（只此一次）
  el.lockSec.addEventListener("click", function (e) {
    var btn = e.target.closest('[data-act="pick"]');
    if (!btn) return;
    if (!window.confirm("免费版只能选 1 个订阅，选定后不可更改。\n确定把酒店源选为免费订阅吗？")) return;
    var r = window.IVAUTH.setFreeRegion(HOTEL_KEY);
    if (!r.ok) return toast(r.msg);
    toast("已选酒店源，订阅地址已解锁");
    renderSubscribe();
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

    window.IVAUTH.syncSponsor()
      .then(function (changed) {
        if (changed) state.user = window.IVAUTH.user();
        el.acctLink.textContent = state.user.member ? "我的订阅" : "赞助解锁";
      })
      .then(function () {
        return fetch("data/public/hotel.json", { cache: "no-cache" }).then(function (r) {
          if (!r.ok) throw new Error("hotel.json HTTP " + r.status);
          return r.json();
        });
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

        if (isMember()) loadUrls();
      })
      .catch(function (err) {
        fail("数据加载失败", err.message);
      });
  }

  boot();
})();
