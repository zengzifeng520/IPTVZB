/* 地区频道页：按登录账号的地区权限展示频道地址与订阅 */
(function () {
  "use strict";

  var el = {
    badge: document.getElementById("tsBadge"),
    region: document.getElementById("tsRegion"),
    meta: document.getElementById("tsMeta"),
    side: document.getElementById("tsSide"),
    chips: document.getElementById("regionChips"),
    regionSub: document.getElementById("regionSub"),
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
    proxy: null,
    regions: [],
    subs: null,
    regionKey: "",
    channels: [],
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

  function regionByKey(key) {
    for (var i = 0; i < state.regions.length; i++) {
      if (state.regions[i].key === key) return state.regions[i];
    }
    return null;
  }

  function subByKey(key) {
    var arr = (state.subs && state.subs.regions) || [];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i].key === key) return arr[i];
    }
    return null;
  }

  /* ---------------------------------------------------------- 渲染 */

  /** 公开地址表：data/public/urls/<地区>.json，任何人都能拿 */
  function loadUrls(key) {
    fetch("data/public/urls/" + key + ".json", { cache: "no-store" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (m) {
        if (state.regionKey !== key) return;
        state.urls = m || {};
        state.channels.forEach(function (c) {
          var arr = state.urls[c.key] || [];
          c.streams = arr.map(function (p) {
            return { h: p[0], u: p[1] };
          });
        });
        renderSummary();
        renderList();
      })
      .catch(function () {});
  }

  function renderSummary() {
    var r = regionByKey(state.regionKey);
    var name = r ? r.name : "—";
    var nChan = state.channels.length;
    var nStream = r ? r.streams || 0 : 0;
    var nHost = r ? (r.hosts || []).length : 0;

    el.badge.textContent = "地址免费";
    el.badge.className = "ts-badge is-ok";
    el.region.textContent = name;
    el.meta.innerHTML =
      "<span>" +
      nChan +
      " 个频道</span><span>" +
      nStream +
      " 条地址</span><span>" +
      nHost +
      " 台中转服务器</span>";

    el.side.innerHTML =
      '<span class="ts-side-tip">喜欢就支持一下</span>' +
      '<a class="btn btn-primary" href="account.html">👍 支持一下作者</a>';
  }

  function renderChips() {
    var html = state.regions
      .map(function (r) {
        var active = r.key === state.regionKey;
        return (
          '<button class="chip' +
          (active ? " active" : "") +
          '" data-r="' +
          esc(r.key) +
          '">' +
          esc(r.name) +
          '<span class="n">' +
          (r.channels || 0) +
          "</span></button>"
        );
      })
      .join("");

    el.chips.innerHTML = html;
    el.regionSub.textContent =
      "全部 " + state.regions.length + " 个地区免费，地址与订阅直接可用";
  }

  function renderSubscribe() {
    // 订阅地址全部公开，无需付费，打赏自愿
    var key = state.regionKey;
    var r = regionByKey(key);
    var mine = subByKey(key);
    var all = (state.subs && state.subs.all) || null;

    el.subSec.hidden = false;
    el.lockSec.hidden = true;

    if (mine) {
      state.subPath = "data/public/" + key + ".m3u";
      el.subTitle.textContent = (r ? r.name : "") + " 订阅地址";
      el.subDesc.textContent =
        "公开订阅，粘贴到 PotPlayer / VLC / TiviMate / APTV 即可加载全部频道。数据每小时自动更新。";
      el.subTag.textContent = (r ? r.name : "") + " · " + mine.channels + " 频道 / " + mine.streams + " 条";
      el.subUrl.textContent = baseUrl() + state.subPath;
      el.dlSub.href = state.subPath;
    } else {
      state.subPath = "";
      el.subTag.textContent = "—";
      el.subUrl.textContent = "订阅数据加载失败，请刷新重试";
      el.dlSub.href = "#";
    }

    var hosts = (r && r.hosts) || [];
    el.hostChips.innerHTML = hosts
      .map(function (h) {
        return '<span class="host-chip" title="' + esc(h) + '">' + esc(hostLabel(h)) + "</span>";
      })
      .join("");
  }

  function renderList() {
    var q = state.filter.trim().toLowerCase();
    var list = q
      ? state.channels.filter(function (c) {
          return (
            c.display.toLowerCase().indexOf(q) >= 0 ||
            c.key.toLowerCase().indexOf(q) >= 0 ||
            (c.type || "").indexOf(q) >= 0
          );
        })
      : state.channels;

    var r = regionByKey(state.regionKey);
    var scope = r ? r.name + " · " : "";
    var total = regionByKey(state.regionKey) ? regionByKey(state.regionKey).streams || 0 : 0;
    el.addrSub.textContent = q
      ? scope + "匹配 " + list.length + " 个频道"
      : scope + state.channels.length + " 个频道 / " + total + " 条地址";

    if (!list.length) {
      el.list.innerHTML = '<div class="empty"><h3>没有匹配的频道</h3><p>换个关键词试试</p></div>';
      return;
    }

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
          '<span class="addr-type">' +
          esc(c.type || "") +
          "</span>" +
          '<span class="addr-count">' +
          c.streams.length +
          " 条</span></summary>" +
          '<div class="addr-urls">' +
          c.streams
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

  /* ---------------------------------------------------------- 地区切换 */

  function applyRegion(key) {
    var r = regionByKey(key);
    if (!r) {
      toast("地区不存在");
      return false;
    }

    state.regionKey = key;

    // 公开目录里只有名字和条数；地址由会员自己的 urls/<地区>.json 提供
    state.channels = (state.pub.channels || [])
      .filter(function (ch) {
        return ch.regions && ch.regions[key];
      })
      .map(function (ch) {
        return {
          key: ch.key,
          display: ch.display,
          type: ch.type,
          n: ch.regions[key],
          streams: [],
        };
      });
    state.urls = null;

    renderSummary();
    renderChips();
    renderSubscribe();
    renderList();

    loadUrls(key);

    var url = new URL(location.href);
    url.searchParams.set("r", key);
    url.searchParams.delete("c");
    history.replaceState(null, "", url);
    return true;
  }

  /* ---------------------------------------------------------- 交互 */

  el.chips.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-r]");
    if (!btn) return;
    applyRegion(btn.dataset.r);
  });

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
    var params = new URLSearchParams(location.search);
    el.acctLink.textContent = "👍 支持一下作者";

    // 公开目录：含地区与频道统计
    fetch("data/public/channels.json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("channels.json HTTP " + r.status);
        return r.json();
      })
      .then(function (pub) {
        state.pub = pub;
        state.regions = (pub.regions || []).slice().sort(function (a, b) {
          return b.streams - a.streams;
        });
        state.subs = { all: pub.stats || {}, regions: pub.regions || [] };
        state.proxy = { stats: pub.stats || {}, generated_at: pub.generated_at };

        if (el.updAt) el.updAt.textContent = pub.generated_at || "—";

        if (!state.regions.length) return fail("地区数据为空", "请稍后刷新重试");

        // 地区全部可浏览，优先用 URL 指定的地区
        var want = params.get("r");
        var target = want && regionByKey(want) ? want : state.regions[0].key;

        applyRegion(target);

        // 从首页带过来的频道，自动展开
        var chKey = params.get("c");
        if (chKey) {
          var hit = null;
          var chs = el.list.querySelectorAll(".addr-item");
          for (var i = 0; i < chs.length; i++) {
            if (chs[i].dataset.key === chKey) {
              hit = chs[i];
              break;
            }
          }
          if (hit) {
            hit.open = true;
            hit.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        }
      })
      .catch(function (err) {
        fail("数据加载失败", err.message);
      });
  }

  boot();
})();
