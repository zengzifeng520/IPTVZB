/* 赞助解锁 / 套餐选择 */
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
    sidText: document.getElementById("sidText"),
    sidInput: document.getElementById("sidInput"),
    sidMsg: document.getElementById("sidMsg"),
    copySid: document.getElementById("copySid"),
    restoreBtn: document.getElementById("restoreBtn"),
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
    if (el.openPay) el.openPay.textContent = "扫码赞助 ￥" + p.price + " 解锁订阅";
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
    el.phone.textContent = u.member ? "已赞助" : u.expired ? "赞助已到期" : "未赞助";
    el.avatar.textContent = "光";
    el.badges.innerHTML =
      (u.member
        ? '<span class="pill pill-ok">' + esc(u.planName || "已赞助") + "</span>"
        : u.expired
          ? '<span class="pill pill-err">已到期</span>'
          : '<span class="pill pill-warn">未赞助</span>') +
      '<span class="pill">' + state.regions.length + " 个地区</span>";

    el.plan.textContent = u.member ? u.planName || "已赞助" : u.expired ? "已到期" : "未赞助";
    el.region.textContent = "全部 " + state.regions.length + " 个地区免费浏览";
    el.exp.textContent = u.member
      ? u.expText + "（剩 " + u.daysLeft + " 天）"
      : u.expired
        ? u.lastExpText + "（已到期）"
        : "—";

    if (el.upgradeTitle) {
      el.upgradeTitle.textContent = u.expired ? "赞助已到期，再次赞助恢复订阅" : "赞助解锁订阅链接";
      el.upgradePill.textContent = u.expired ? "已到期" : "未赞助";
      el.upgradePill.className = "pill " + (u.expired ? "pill-err" : "pill-warn");
    }

    el.upgrade.hidden = !!u.member;
    el.member.hidden = !u.member;
    if (u.member && el.memberPill) {
      el.memberPill.textContent = "剩 " + u.daysLeft + " 天";
    }
    if (el.sidText) el.sidText.textContent = u.sidText || "—";
  }

  function renderSubs() {
    if (!state.subs) {
      el.subList.innerHTML = '<div class="empty-inline">订阅数据加载失败，请稍后刷新</div>';
      return;
    }
    var base = baseUrl();
    var all = state.subs.all || {};
    var items = [];

    // 专属订阅：路径带赞助码 token，到期后服务端把文件写成空列表
    var token = state.user.sid ? A.tokenOf(state.user.sid) : "";
    function userPath(tail) {
      return token ? "data/users/" + token + "/" + tail : "";
    }

    items.push({
      key: "ALL",
      name: "全量订阅",
      isp: "全部地区合并",
      path: userPath("all.m3u"),
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
        path: userPath(r.key + ".m3u"),
        channels: r.channels,
        streams: r.streams,
        mine: false,
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
    state.order = A.makeOrderNo(state.user.sid);
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
    btn.textContent = "正在解锁…";

    var r = A.unlock(state.planKey, state.order);
    if (!r.ok) {
      btn.disabled = false;
      btn.textContent = "我已完成付款，立即解锁";
      return toast(r.msg);
    }

    closePay();
    toast(
      A.remoteEnabled()
        ? plan.name + " 已解锁，有效期至 " + A.fmtDate(r.exp)
        : "已解锁本机；请把下方赞助码发给站长，即可开通专属订阅"
    );
    setTimeout(function () {
      location.reload();
    }, 1400);
  });

  /* ------------------------------------------------ 专属订阅就绪检测 */

  // 付款后订阅文件由服务端生成，首次开通通常 1 分钟内可用。
  // 这里在账号页显示一条状态条，避免用户看到地址却打不开以为出错。
  function checkSubReady() {
    var u = A.user();
    if (!u || !u.member || !el.subList) return;
    var tok = A.tokenOf(u.sid);
    fetch("data/users/" + tok + "/meta.json", { cache: "no-store" })
      .then(function (res) {
        if (res.ok) return;
        el.subList.insertAdjacentHTML(
          "afterbegin",
          '<div class="empty-inline" style="text-align:left;padding:10px 12px">' +
            "专属订阅正在生成，通常 1 分钟内生效。如果超过 10 分钟仍不可用，" +
            "请把本页下方的赞助码发给站长补录。" +
            "</div>"
        );
      })
      .catch(function () {});
  }

  /* ---------------------------------------------------------- 赞助码 */

  if (el.copySid) {
    el.copySid.addEventListener("click", function () {
      copyText(A.sidText(), "赞助码已复制，建议截图保存");
    });
  }

  if (el.restoreBtn) {
    el.restoreBtn.addEventListener("click", function () {
      var code = (el.sidInput.value || "").trim();
      if (!code) return toast("请先粘贴赞助码");
      var r = A.setSid(code);
      if (!r.ok) {
        el.sidMsg.textContent = r.msg;
        return toast(r.msg);
      }
      el.sidMsg.textContent = "已切换到 " + A.sidText() + "，正在重新读取状态…";
      A.syncSponsor().then(function () {
        setTimeout(function () {
          location.reload();
        }, 700);
      });
    });
  }

  el.subList.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-url]");
    if (!btn) return;
    copyText(btn.dataset.copyUrl, "订阅地址已复制");
  });

  /* ---------------------------------------------------------- 启动 */

  state.user = A.user();
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

  function loadSubs() {
    fetch("data/sub/index.json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        state.subs = d;
        renderSubs();
        checkSubReady();
      })
      .catch(function () {
        renderSubs();
        checkSubReady();
      });
  }

  // 先从服务端同步赞助状态（换设备 / 站长补录后自动恢复）
  A.syncSponsor()
    .then(function (changed) {
      if (changed) state.user = A.user();
      renderHead();
      if (state.user.member) loadSubs();
    })
    .catch(function () {
      if (state.user.member) loadSubs();
    });

  // ?pay=1 直接展开付款弹层
  if (new URLSearchParams(location.search).get("pay") === "1") {
    openPay();
  }
})();
