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

  function isMember() {
    return !!(state.user && state.user.member);
  }

  /* ---------------------------------------------------------- 渲染 */

  /** 会员的地址表：只拉当前地区那一份，几百 KB 以内 */
  function loadUrls(key) {
    var tok = state.user && state.user.sid ? window.IVAUTH.tokenOf(state.user.sid) : "";
    if (!tok) return;
    fetch("data/users/" + tok + "/urls/" + key + ".json", { cache: "no-store" })
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

    el.badge.textContent = isMember()
      ? (state.user.planName || "已赞助") + " · 订阅已解锁"
      : state.user.expired
        ? "赞助已到期"
        : "免费浏览";
    el.badge.className = "ts-badge" + (isMember() ? " is-ok" : state.user.expired ? " is-expired" : "");
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
        '<a class="btn" href="account.html">我的订阅</a>';
    } else {
      el.side.innerHTML =
        '<span class="ts-side-tip">地址可免费查看</span>' +
        '<a class="btn btn-primary" href="account.html">' +
        (state.user.expired ? "重新赞助" : "赞助解锁订阅") +
        "</a>";
    }
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
    el.regionSub.textContent = isMember()
      ? "全部 " + state.regions.length + " 个地区已解锁"
      : state.user.expired
        ? "赞助已到期，订阅已停止更新；再次赞助即可恢复"
        : "免费版可任选 1 个地区订阅，赞助后解锁全部";
  }

  function renderSubscribe() {
    var member = isMember();
    var key = state.regionKey;
    var freeKey = window.IVAUTH.freeRegion();
    var freeOk = window.IVAUTH.freeValid();
    // 赞助用户可用全部地区；免费用户只能用已选定且未过期的那一个
    var canUse = member || (freeKey === key && freeOk);

    el.subSec.hidden = !canUse;
    el.lockSec.hidden = canUse;

    if (!canUse) {
      renderLock(key, freeKey, freeOk);
      return;
    }

    var r = regionByKey(key);
    var mine = subByKey(key);
    var all = (state.subs && state.subs.all) || null;

    // 专属订阅：每个赞助账号一份，路径里带 token；到期后服务端把文件写成空列表
    var token = state.user && state.user.sid ? window.IVAUTH.tokenOf(state.user.sid) : "";

    if (mine) {
      if (member && token) {
        state.subPath = "data/users/" + token + "/" + key + ".m3u";
        el.subTitle.textContent = (r ? r.name : "") + " 专属订阅地址";
        el.subDesc.textContent =
          "这是你专属的订阅地址，请勿分享。赞助到期后该地址会自动停止更新，播放器刷新后频道将为空。";
      } else {
        // 免费额度：公共目录，选地区当天 + 7 天后目录被删，链接自动失效
        var dir = window.IVAUTH.freeDir();
        state.subPath = "data/free/" + dir + "/" + key + ".m3u";
        el.subTitle.textContent = (r ? r.name : "") + " 免费订阅（7 天）";
        el.subDesc.textContent =
          "免费订阅有效期至 " +
          window.IVAUTH.fmtDate(window.IVAUTH.freeExpire()) +
          "，到期后这条链接自动失效。免费为公共线路，不保证稳定性；赞助后可拿专属订阅并查看全部播放地址。";
      }
      el.subTag.textContent = (r ? r.name : "") + " · " + mine.channels + " 频道 / " + mine.streams + " 条";
      el.subUrl.textContent = baseUrl() + state.subPath;
      el.dlSub.href = state.subPath;
    } else if (all && member && token) {
      state.subPath = "data/users/" + token + "/all.m3u";
      el.subTag.textContent = "全量";
      el.subUrl.textContent = baseUrl() + state.subPath;
      el.dlSub.href = state.subPath;
      el.subTitle.textContent = "全量专属订阅地址";
      el.subDesc.textContent = "包含全部地区服务器，适合手动挑选线路。赞助到期后该地址会自动停止更新。";
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

  /** 未赞助时：没选过地区就让他选，选过了就引导回去或去赞助 */
  function renderLock(key, freeKey, freeOk) {
    var r = regionByKey(key);
    var name = r ? r.name : key;

    if (!freeKey) {
      el.lockBody.innerHTML =
        "<h2>免费版可以先选 1 个地区</h2>" +
        "<p>不赞助只能看到频道名，<b>拿不到播放地址</b>。可以先选 <b>1 个地区</b> 的订阅链接试用，有效期 <b>7 天</b>，到期自动失效。<br>" +
        "赞助后可查看全部地区地址，并拿到长期有效的专属订阅。</p>" +
        '<button class="btn btn-primary btn-lg" type="button" data-act="pick" style="margin-top:6px">就选「' +
        esc(name) +
        "」</button>" +
        '<a class="btn btn-lg" href="account.html" style="margin-top:8px">直接赞助解锁全部</a>';
      return;
    }

    var fr = regionByKey(freeKey);
    var fname = fr ? fr.name : freeKey;

    // 选过但 7 天免费期已经结束
    if (!freeOk) {
      el.lockBody.innerHTML =
        "<h2>免费订阅已到期</h2>" +
        "<p>你在「" +
        esc(fname) +
        "」的 7 天免费订阅已于 " +
        esc(window.IVAUTH.fmtDate(window.IVAUTH.freeExpire())) +
        " 到期，链接已失效。<br>赞助后可查看全部播放地址，并拿到长期有效的专属订阅。</p>" +
        '<a class="btn btn-primary btn-lg" href="account.html" style="margin-top:6px">去赞助解锁</a>';
      return;
    }

    el.lockBody.innerHTML =
      "<h2>你的免费地区是「" +
      esc(fname) +
      "」</h2>" +
      "<p>免费订阅有效期至 <b>" +
      esc(window.IVAUTH.fmtDate(window.IVAUTH.freeExpire())) +
      "</b>，到期后链接自动失效。<br>播放地址仍需赞助后显示。</p>" +
      '<a class="btn btn-primary btn-lg" href="region.html?r=' +
      encodeURIComponent(freeKey) +
      '" style="margin-top:6px">去看「' +
      esc(fname) +
      "」</a>" +
      '<a class="btn btn-lg" href="account.html" style="margin-top:8px">赞助解锁全部</a>';
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
            '<span class="addr-type">' +
            esc(c.type || "") +
            "</span>" +
            '<span class="addr-count">' +
            (c.n || c.streams.length) +
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

    if (isMember()) loadUrls(key);

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

  // 免费版选地区（只此一次）
  el.lockSec.addEventListener("click", function (e) {
    var btn = e.target.closest('[data-act="pick"]');
    if (!btn) return;
    var key = state.regionKey;
    var name = (regionByKey(key) || {}).name || key;
    if (!window.confirm("免费版只能选 1 个地区，选定后不可更改。\n确定选「" + name + "」吗？")) return;
    var r = window.IVAUTH.setFreeRegion(key);
    if (!r.ok) return toast(r.msg);
    toast("已选「" + name + "」，订阅地址已解锁");
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
    var params = new URLSearchParams(location.search);

    // 先同步服务端赞助状态（换设备 / 站长补录后自动恢复），再渲染页面
    window.IVAUTH.syncSponsor()
      .then(function (changed) {
        if (changed) state.user = window.IVAUTH.user();
        el.acctLink.textContent = state.user.member ? "我的订阅" : "赞助解锁";
      })
      .then(function () {
        // 公开目录：只有频道名和各地区条数，不含地址
        return fetch("data/public/channels.json", { cache: "no-cache" }).then(function (r) {
          if (!r.ok) throw new Error("channels.json HTTP " + r.status);
          return r.json();
        });
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
