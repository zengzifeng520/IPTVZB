/* 喜欢作者，请支持一下：打赏入口 + 免费订阅地址 */
(function () {
  "use strict";

  var el = {
    subList: document.getElementById("subList"),
    toast: document.getElementById("toast"),
    donateAmounts: document.getElementById("donateAmounts"),
    donateOther: document.getElementById("donateOther"),
    donateCustom: document.getElementById("donateCustom"),
    customAmt: document.getElementById("customAmt"),
    customOk: document.getElementById("customOk"),
    donateQr: document.getElementById("donateQr"),
    donatePayNum: document.getElementById("donatePayNum"),
  };

  var state = {
    subs: null,
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

  /* ---------------------------------------------------------- 打赏 */

  function pickAmount(amt) {
    var n = Number(amt);
    if (!n || n <= 0) return;
    el.donateCustom.hidden = true;
    el.donateQr.hidden = false;
    el.donatePayNum.textContent = "¥" + n;
    // 高亮选中
    var btns = el.donateAmounts.querySelectorAll(".amount");
    for (var i = 0; i < btns.length; i++) {
      btns[i].classList.toggle("active", Number(btns[i].dataset.amt) === n);
    }
  }

  if (el.donateAmounts) {
    el.donateAmounts.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-amt]");
      if (!btn) return;
      pickAmount(btn.dataset.amt);
    });
  }

  if (el.donateOther) {
    el.donateOther.addEventListener("click", function () {
      el.donateCustom.hidden = false;
      el.donateQr.hidden = true;
      if (el.customAmt) el.customAmt.focus();
    });
  }

  if (el.customOk) {
    el.customOk.addEventListener("click", function () {
      var v = (el.customAmt.value || "").trim();
      if (!v) return toast("请输入金额");
      var n = Number(v);
      if (!n || n <= 0) return toast("金额需大于 0");
      pickAmount(n);
    });
  }

  /* ---------------------------------------------------------- 渲染 */

  function renderSubs() {
    if (!state.subs) {
      el.subList.innerHTML = '<div class="empty-inline">订阅数据加载失败，请稍后刷新</div>';
      return;
    }
    var base = baseUrl();
    var all = state.subs.all || {};
    var items = [];

    // 全量订阅（公开）
    items.push({
      key: "ALL",
      name: "全量订阅",
      isp: "全部地区合并 + 酒店源",
      path: "data/public/all.m3u",
      channels: all.channelsTotal || all.channels || 0,
      streams: all.streamsTotal || all.streams || 0,
      big: true,
    });

    // 分地区订阅（公开）
    (state.subs.regions || []).forEach(function (r) {
      items.push({
        key: r.key,
        name: r.name,
        isp: r.isp,
        path: "data/public/" + r.key + ".m3u",
        channels: r.channels,
        streams: r.streams,
      });
    });

    // 酒店源订阅（公开）
    if (all.hotelStreams) {
      items.push({
        key: "hotel",
        name: "酒店源",
        isp: "HLS 直连 · 不限地区",
        path: "data/public/hotel.m3u",
        channels: all.hotelChannels || 0,
        streams: all.hotelStreams || 0,
      });
    }

    items.sort(function (a, b) {
      if (a.big !== b.big) return a.big ? -1 : 1;
      return b.streams - a.streams;
    });

    el.subList.innerHTML = items
      .map(function (it) {
        var url = base + it.path;
        return (
          '<div class="sub-item">' +
          '<div class="sub-item-main">' +
          '<div class="sub-item-title">' +
          esc(it.name) +
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

  /* ---------------------------------------------------------- 交互 */

  el.subList.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copy-url]");
    if (!btn) return;
    copyText(btn.dataset.copyUrl, "订阅地址已复制");
  });

  /* ---------------------------------------------------------- 启动 */

  fetch("data/public/channels.json", { cache: "no-cache" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (d) {
      state.subs = { all: d.stats || {}, regions: d.regions || [] };
      renderSubs();
    })
    .catch(function () {
      renderSubs();
    });
})();
