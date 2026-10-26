/* 我的账号 / 扫码开通 */
(function () {
  "use strict";

  var el = {
    phone: document.getElementById("acctPhone"),
    avatar: document.getElementById("acctAvatar"),
    badges: document.getElementById("acctBadges"),
    plan: document.getElementById("statPlan"),
    region: document.getElementById("statRegion"),
    exp: document.getElementById("statExp"),
    upgrade: document.getElementById("upgradePanel"),
    member: document.getElementById("memberPanel"),
    lockName: document.getElementById("lockRegionName"),
    subList: document.getElementById("subList"),
    openPay: document.getElementById("openPay"),
    payModal: document.getElementById("payModal"),
    orderNo: document.getElementById("orderNo"),
    copyOrder: document.getElementById("copyOrder"),
    confirmPay: document.getElementById("confirmPay"),
    logout: document.getElementById("logoutBtn"),
    toast: document.getElementById("toast"),
  };

  var state = { user: null, regions: [], subs: null, order: "" };

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
    }, 2600);
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

  // 站点根路径（兼容部署在子目录）
  function baseUrl() {
    return location.origin + location.pathname.replace(/[^/]*$/, "");
  }

  function regionName(key) {
    var r = state.regions.filter(function (x) {
      return x.key === key;
    })[0];
    return r ? r.name : key || "—";
  }

  /* ---------------------------------------------------------- 渲染 */

  function renderHead() {
    var u = state.user;
    el.phone.textContent = u.phoneMask;
    el.avatar.textContent = u.phoneMask.slice(-4, -3) || "光";
    el.badges.innerHTML =
      (u.member
        ? '<span class="pill pill-ok">会员</span>'
        : '<span class="pill pill-warn">体验版</span>') +
      '<span class="pill">' +
      esc(regionName(u.region)) +
      "</span>";

    el.plan.textContent = u.member ? "会员（全地区）" : "体验版（单地区）";
    el.region.textContent = u.member ? "全部 " + state.regions.length + " 个地区" : regionName(u.region);
    el.exp.textContent = u.member ? u.expText : "—";

    el.upgrade.hidden = !!u.member;
    el.member.hidden = !u.member;
    el.lockName.textContent = regionName(u.region);
  }

  function renderSubs() {
    if (!state.subs) {
      el.subList.innerHTML = '<div class="empty-inline">订阅数据加载失败，请稍后刷新</div>';
      return;
    }
    var base = baseUrl();
    var myRegion = state.user.region;
    var all = state.subs.all || {};
    var items = [];

    items.push({
      key: "ALL",
      name: "全量订阅",
      isp: "全部地区合并",
      path: all.sub,
      channels: all.channels,
      streams: all.streams,
      mine: false,
      big: true,
    });

    (state.subs.regions || []).forEach(function (r) {
      items.push({
        key: r.key,
        name: r.name,
        isp: r.isp,
        path: r.sub,
        channels: r.channels,
        streams: r.streams,
        mine: r.key === myRegion,
      });
    });

    // 本地区排最前
    items.sort(function (a, b) {
      if (a.mine !== b.mine) return a.mine ? -1 : 1;
      if (a.big !== b.big) return a.big ? -1 : 1;
      return b.streams - a.streams;
    });

    el.subList.innerHTML = items
      .map(function (it) {
        var url = base + it.path;
        return (
          '<div class="sub-item' +
          (it.mine ? " is-mine" : "") +
          '">' +
          '<div class="sub-item-main">' +
          '<div class="sub-item-title">' +
          esc(it.name) +
          (it.mine ? '<span class="pill pill-ok pill-xs">你所在地区</span>' : "") +
          "</div>" +
          '<div class="sub-item-meta">' +
          esc(it.isp || "") +
          " · " +
          it.channels +
          " 频道 / " +
          it.streams +
          " 条" +
          "</div>" +
          '<code class="sub-item-url">' +
          esc(url) +
          "</code>" +
          "</div>" +
          '<div class="sub-item-act">' +
          '<button class="btn btn-sm btn-primary" data-copy-url="' +
          esc(url) +
          '">复制</button>' +
          '<a class="btn btn-sm" href="' +
          esc(it.path) +
          '" download>下载</a>' +
          "</div>" +
          "</div>"
        );
      })
      .join("");
  }

  /* ---------------------------------------------------------- 付款 */

  function openPay() {
    state.order = window.IVAUTH.makeOrderNo(state.user.phone);
    el.orderNo.textContent = state.order;
    el.payModal.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closePay() {
    el.payModal.hidden = true;
    document.body.style.overflow = "";
  }

  el.openPay.addEventListener("click", openPay);

  el.payModal.addEventListener("click", function (e) {
    if (e.target.closest("[data-close]")) closePay();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !el.payModal.hidden) closePay();
  });

  el.copyOrder.addEventListener("click", function () {
    copyText(state.order, "订单号已复制");
  });

  el.confirmPay.addEventListener("click", function () {
    var btn = el.confirmPay;
    btn.disabled = true;
    btn.textContent = "正在开通…";

    var r = window.IVAUTH.unlock(state.order);
    if (!r.ok) {
      btn.disabled = false;
      btn.textContent = "我已完成付款，立即开通";
      return toast(r.msg);
    }

    closePay();
    toast("开通成功，已解锁全部地区");
    setTimeout(function () {
      location.reload();
    }, 700);
  });

  /* ---------------------------------------------------------- 退出 */

  el.logout.addEventListener("click", function () {
    window.IVAUTH.logout();
    location.href = "index.html";
  });

  el.subList.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-url]");
    if (!btn) return;
    copyText(btn.dataset.copyUrl, "订阅地址已复制");
  });

  /* ---------------------------------------------------------- 启动 */

  state.user = window.IVAUTH.user();
  if (!state.user) {
    location.replace("login.html?next=account.html");
    return;
  }

  renderHead();

  fetch("data/regions.json", { cache: "no-cache" })
    .then(function (r) {
      return r.ok ? r.json() : { regions: [] };
    })
    .then(function (d) {
      state.regions = d.regions || [];
      renderHead();
    })
    .catch(function () {});

  if (state.user.member) {
    fetch("data/sub/index.json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        state.subs = d;
        renderSubs();
      })
      .catch(function () {
        renderSubs();
      });
  }

  // 支持 ?pay=1 直接展开付款弹层（方便把付款链接直接发给用户）
  if (new URLSearchParams(location.search).get("pay") === "1" && !state.user.member) {
    openPay();
  }
})();
