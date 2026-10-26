/* 我的账号 / 套餐开通 */
(function () {
  "use strict";

  var A = window.IVAUTH;

  var el = {
    phone: document.getElementById("acctPhone"),
    avatar: document.getElementById("acctAvatar"),
    badges: document.getElementById("acctBadges"),
    plan: document.getElementById("statPlan"),
    region: document.getElementById("statRegion"),
    exp: document.getElementById("statExp"),
    upgrade: document.getElementById("upgradePanel"),
    upgradeTitle: document.getElementById("upgradeTitle"),
    upgradePill: document.getElementById("upgradePill"),
    member: document.getElementById("memberPanel"),
    memberPill: document.getElementById("memberPill"),
    lockName: document.getElementById("lockRegionName"),
    planGrid: document.getElementById("planGrid"),
    openPay: document.getElementById("openPay"),
    renewBtn: document.getElementById("renewBtn"),
    subList: document.getElementById("subList"),
    payModal: document.getElementById("payModal"),
    payPlans: document.getElementById("payPlans"),
    payAmount: document.getElementById("payAmount"),
    payPlanNote: document.getElementById("payPlanNote"),
    payStepAmount: document.getElementById("payStepAmount"),
    orderNo: document.getElementById("orderNo"),
    copyOrder: document.getElementById("copyOrder"),
    confirmPay: document.getElementById("confirmPay"),
    logout: document.getElementById("logoutBtn"),
    toast: document.getElementById("toast"),
  };

  var state = {
    user: null,
    regions: [],
    subs: null,
    order: "",
    planKey: A.DEFAULT_PLAN,
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

  function baseUrl() {
    return location.origin + location.pathname.replace(/[^/]*$/, "");
  }

  function regionName(key) {
    var r = state.regions.filter(function (x) {
      return x.key === key;
    })[0];
    return r ? r.name : key || "—";
  }

  function currentPlan() {
    return A.planByKey(state.planKey) || A.planByKey(A.DEFAULT_PLAN);
  }

  function money(n) {
    return "￥" + Number(n).toFixed(2);
  }

  /* ---------------------------------------------------------- 套餐 */

  function renderPlans() {
    el.planGrid.innerHTML = A.PLANS.map(function (p) {
      var active = p.key === state.planKey;
      return (
        '<button type="button" class="plan' +
        (active ? " active" : "") +
        (p.hot ? " is-hot" : "") +
        '" data-plan="' +
        esc(p.key) +
        '">' +
        (p.hot ? '<span class="plan-hot">推荐</span>' : "") +
        '<span class="plan-name">' +
        esc(p.name) +
        "</span>" +
        '<span class="plan-price"><i>￥</i>' +
        p.price +
        "</span>" +
        '<span class="plan-days">' +
        p.days +
        " " +
        esc(p.unit) +
        "</span>" +
        '<span class="plan-tag">' +
        esc(p.tag) +
        "</span>" +
        "</button>"
      );
    }).join("");
  }

  function renderPayPlans() {
    el.payPlans.innerHTML = A.PLANS.map(function (p) {
      var active = p.key === state.planKey;
      return (
        '<button type="button" class="pay-plan' +
        (active ? " active" : "") +
        '" data-plan="' +
        esc(p.key) +
        '">' +
        "<b>" +
        esc(p.name) +
        "</b>" +
        "<i>￥" +
        p.price +
        "</i></button>"
      );
    }).join("");
  }

  function syncPrice() {
    var p = currentPlan();
    el.payAmount.textContent = money(p.price);
    el.payPlanNote.textContent = p.name + " · " + p.days + " " + p.unit;
    el.payStepAmount.textContent = money(p.price);
    if (el.openPay) el.openPay.textContent = "扫码付款 ￥" + p.price + " 立即开通";
  }

  function setPlan(key) {
    var p = A.planByKey(key);
    if (!p) return;
    state.planKey = key;
    renderPlans();
    renderPayPlans();
    syncPrice();
  }

  /* ---------------------------------------------------------- 渲染 */

  function renderHead() {
    var u = state.user;
    el.phone.textContent = u.phoneMask;
    el.avatar.textContent = u.phoneMask.slice(-4, -3) || "光";
    el.badges.innerHTML =
      (u.member
        ? '<span class="pill pill-ok">' + esc(u.planName || "会员") + "</span>"
        : u.expired
        ? '<span class="pill pill-err">已过期</span>'
        : '<span class="pill pill-warn">免费版</span>') +
      '<span class="pill">' +
      esc(regionName(u.region)) +
      "</span>";

    el.plan.textContent = u.member
      ? u.planName || "会员"
      : u.expired
      ? "已过期"
      : "免费版（单地区）";
    el.region.textContent = u.member ? "全部 " + state.regions.length + " 个地区" : regionName(u.region);
    el.exp.textContent = u.member
      ? u.expText + "（剩 " + u.daysLeft + " 天）"
      : u.expired
      ? u.lastExpText + "（已过期）"
      : "—";

    // 过期后引导续费
    if (el.upgradeTitle) {
      el.upgradeTitle.textContent = u.expired ? "会员已过期，续费恢复订阅" : "开通全部地区";
      el.upgradePill.textContent = u.expired ? "已过期" : "免费版";
      el.upgradePill.className = "pill " + (u.expired ? "pill-err" : "pill-warn");
    }

    el.upgrade.hidden = !!u.member;
    el.member.hidden = !u.member;
    el.lockName.textContent = regionName(u.region);
    if (u.member && el.memberPill) {
      el.memberPill.textContent = "剩 " + u.daysLeft + " 天";
    }
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
    state.order = A.makeOrderNo(state.user.phone);
    el.orderNo.textContent = state.order;
    renderPayPlans();
    syncPrice();
    el.payModal.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closePay() {
    el.payModal.hidden = true;
    document.body.style.overflow = "";
  }

  el.openPay.addEventListener("click", openPay);
  if (el.renewBtn) el.renewBtn.addEventListener("click", openPay);

  el.planGrid.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-plan]");
    if (!btn) return;
    setPlan(btn.dataset.plan);
  });

  el.payPlans.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-plan]");
    if (!btn) return;
    setPlan(btn.dataset.plan);
  });

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
    var plan = currentPlan();
    btn.disabled = true;
    btn.textContent = "正在开通…";

    var r = A.unlock(state.planKey, state.order);
    if (!r.ok) {
      btn.disabled = false;
      btn.textContent = "我已完成付款，立即开通";
      return toast(r.msg);
    }

    closePay();
    toast(plan.name + " 已开通，有效期至 " + A.fmtDate(r.exp));
    setTimeout(function () {
      location.reload();
    }, 900);
  });

  /* ---------------------------------------------------------- 退出 */

  el.logout.addEventListener("click", function () {
    A.logout();
    location.href = "index.html";
  });

  el.subList.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-url]");
    if (!btn) return;
    copyText(btn.dataset.copyUrl, "订阅地址已复制");
  });

  /* ---------------------------------------------------------- 启动 */

  state.user = A.user();
  if (!state.user) {
    location.replace("login.html?next=account.html");
    return;
  }

  renderPlans();
  syncPrice();
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

  // ?pay=1 直接展开付款弹层
  if (new URLSearchParams(location.search).get("pay") === "1") {
    openPay();
  }
})();
