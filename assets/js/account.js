/* 支持一下作者：打赏入口 + 免费订阅地址 */
(function () {
  "use strict";

  var el = {
    subList: document.getElementById("subList"),
    toast: document.getElementById("toast"),
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

  /* ---------------------------------------------------------- 二维码大图 + 支付宝/抖音一键跳转 */

  // 支付宝收款码里的真实链接、抖音主页分享链接：点一下就能打开对应 App
  var ALI_PAY_URI = "https://qr.alipay.com/fkx14447du0gjilqkkmaqdd";
  var DY_URI = "https://v.douyin.com/l-aU7jABkEs/";
  var UA = navigator.userAgent || "";
  var IS_MOBILE =
    /Android|iPhone|iPad|iPod|HarmonyOS|Windows Phone|Mobile/i.test(UA) ||
    (navigator.maxTouchPoints > 1 && /Mac/.test(UA));

  // 手机直接在当前标签跳（交给系统唤起 App），桌面开新标签
  function openExternal(url, e) {
    if (e) e.preventDefault();
    if (IS_MOBILE) location.href = url;
    else window.open(url, "_blank", "noopener");
  }

  function initQrZoom() {
    var box = document.getElementById("qrLightbox");
    var bigImg = document.getElementById("qrBigImg");
    var bigTip = document.getElementById("qrBigTip");

    function openBig(node) {
      if (!box || !bigImg) return;
      bigImg.src = node.dataset.qr;
      bigImg.alt = node.dataset.title || "二维码";
      bigImg.classList.toggle("is-round", node.dataset.round === "1");
      if (bigTip) bigTip.textContent = "点击任意处关闭 · 长按可保存图片";
      box.classList.add("show");
    }

    document.addEventListener("click", function (e) {
      // 两个打赏按钮
      if (e.target.closest("#aliPay")) {
        openExternal(ALI_PAY_URI, e);
        return;
      }
      if (e.target.closest("#dyOpen")) {
        openExternal(DY_URI, e);
        return;
      }

      var node = e.target.closest("[data-qr]");
      if (!node) return;

      // 点二维码图 = 点按钮：支付宝进收钱页，抖音进主页
      if (node.classList.contains("code-ali")) {
        openExternal(ALI_PAY_URI, e);
        return;
      }
      if (node.classList.contains("code-dy")) {
        openExternal(DY_URI, e);
        return;
      }

      openBig(node);
    });

    if (box) {
      box.addEventListener("click", function () {
        box.classList.remove("show");
      });
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && box) box.classList.remove("show");
    });
  }

  initQrZoom();

  /* ---------------------------------------------------------- 渲染 */

  function renderSubs() {
    if (!state.subs) {
      el.subList.innerHTML = '<div class="empty-inline">订阅数据加载失败，请稍后刷新</div>';
      return;
    }
    var base = baseUrl();
    var all = state.subs.all || {};
    var items = [];

    // 全量订阅（公开）：只含全部地区，不含酒店源
    items.push({
      key: "ALL",
      name: "全量订阅",
      isp: "全部地区合并（不含酒店源）",
      path: "data/public/all.m3u",
      channels: all.channels || 0,
      streams: all.streams || 0,
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
