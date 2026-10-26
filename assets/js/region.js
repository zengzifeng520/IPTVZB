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
    lockRegion: document.getElementById("lockRegion"),
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
    navLogout: document.getElementById("navLogout"),
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

  function isMember() {
    return !!(state.user && state.user.member);
  }

  /* ---------------------------------------------------------- 渲染 */

  function renderSummary() {
    var r = regionByKey(state.regionKey);
    var name = r ? r.name : "—";
    var nChan = state.channels.length;
    var nStream = state.channels.reduce(function (n, c) {
      return n + c.streams.length;
    }, 0);
    var nHost = r ? (r.hosts || []).length : 0;

    el.badge.textContent = isMember() ? "会员 · 全部地区" : "体验版 · 单地区";
    el.badge.className = "ts-badge" + (isMember() ? " is-ok" : "");
    el.region.textContent = name;
    el.meta.innerHTML =
      "<span>" +
      nChan +
      " 个频道</span><span>" +
      nStream +
      " 条地址</span><span>" +
      nHost +
      " 台中转服务器</span>";

    if (isMember()) {
      el.side.innerHTML =
        '<span class="ts-side-tip">有效期至 ' + esc(state.user.expText) + "</span>" +
        '<a class="btn" href="account.html">管理订阅</a>';
    } else {
      el.side.innerHTML =
        '<span class="ts-side-tip">仅可查看 ' + esc(name) + "</span>" +
        '<a class="btn btn-primary" href="account.html">解锁全部地区 ¥15</a>';
    }
  }

  function renderChips() {
    var member = isMember();
    var locked = state.user.region;

    var html = state.regions
      .map(function (r) {
        var active = r.key === state.regionKey;
        var isLocked = !member && r.key !== locked;
        return (
          '<button class="chip' +
          (active ? " active" : "") +
          (isLocked ? " is-locked" : "") +
          '" data-r="' +
          esc(r.key) +
          '">' +
          (isLocked
            ? '<svg class="chip-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
            : "") +
          esc(r.name) +
          '<span class="n">' +
          (r.channels || 0) +
          "</span></button>"
        );
      })
      .join("");

    el.chips.innerHTML = html;
    el.regionSub.textContent = member
      ? "全部 " + state.regions.length + " 个地区已解锁"
      : "体验版仅可查看「" + (regionByKey(locked) || { name: locked }).name + "」，其余需开通";
  }

  function renderSubscribe() {
    var member = isMember();
    el.subSec.hidden = !member;
    el.lockSec.hidden = member;

    if (!member) {
      el.lockRegion.textContent = (regionByKey(state.regionKey) || {}).name || "—";
      return;
    }

    var r = regionByKey(state.regionKey);
    var mine = subByKey(state.regionKey);
    var all = (state.subs && state.subs.all) || null;

    if (mine) {
      state.subPath = mine.sub;
      el.subTag.textContent = (r ? r.name : "") + " · " + mine.channels + " 频道 / " + mine.streams + " 条";
      el.subUrl.textContent = baseUrl() + mine.sub;
      el.dlSub.href = mine.sub;
      el.subTitle.textContent = (r ? r.name : "") + " 订阅地址";
      el.subDesc.textContent =
        "把这条地址粘贴到播放器的「订阅 / 远程列表」。本地区服务器只在本省运营商网内可用，跨省线路大多连不上。";
    } else if (all) {
      state.subPath = all.sub;
      el.subTag.textContent = "全量";
      el.subUrl.textContent = baseUrl() + all.sub;
      el.dlSub.href = all.sub;
      el.subTitle.textContent = "全量订阅地址";
      el.subDesc.textContent = "包含全部地区服务器，适合手动挑选线路。跨省地址大多无法播放，建议优先用分地区订阅。";
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
    var total = state.channels.reduce(function (n, c) {
      return n + c.streams.length;
    }, 0);
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
    var member = isMember();
    var locked = state.user.region;

    if (!member && key !== locked) {
      toast("该地区需开通会员后查看");
      return false;
    }
    var r = regionByKey(key);
    if (!r) {
      toast("地区不存在");
      return false;
    }

    state.regionKey = key;
    var hostSet = {};
    (r.hosts || []).forEach(function (h) {
      hostSet[h] = 1;
    });

    state.channels = state.proxy.channels
      .map(function (ch) {
        var picked = ch.streams.filter(function (s) {
          return hostSet[s.h];
        });
        return picked.length
          ? { key: ch.key, display: ch.display, type: ch.type, streams: picked }
          : null;
      })
      .filter(Boolean);

    renderSummary();
    renderChips();
    renderSubscribe();
    renderList();

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
    if (!state.user) {
      location.replace("login.html?next=" + encodeURIComponent(location.pathname + location.search));
      return;
    }
    el.acctLink.textContent = state.user.phoneMask;
    if (el.navLogout) el.navLogout.hidden = false;

    var params = new URLSearchParams(location.search);

    Promise.all([
      fetch("data/proxy.json", { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("proxy.json HTTP " + r.status);
        return r.json();
      }),
      fetch("data/regions.json", { cache: "no-cache" }).then(function (r) {
        if (!r.ok) throw new Error("regions.json HTTP " + r.status);
        return r.json();
      }),
      fetch("data/sub/index.json", { cache: "no-cache" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .catch(function () {
          return null;
        }),
    ])
      .then(function (res) {
        state.proxy = res[0];
        state.regions = (res[1].regions || []).slice().sort(function (a, b) {
          return b.streams - a.streams;
        });
        state.subs = res[2];

        if (el.updAt) el.updAt.textContent = state.proxy.generated_at || "—";

        if (!state.regions.length) return fail("地区数据为空", "请稍后刷新重试");

        // 会员：优先 URL 指定地区；体验版：强制锁定地区
        var want = params.get("r");
        var target;
        if (isMember()) {
          target = want && regionByKey(want) ? want : state.user.region;
          if (!regionByKey(target)) target = state.regions[0].key;
        } else {
          target = state.user.region;
          if (!regionByKey(target)) target = state.regions[0].key;
        }

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
