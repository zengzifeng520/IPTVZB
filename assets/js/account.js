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

  /* ---------------------------------------------------------- 二维码大图 + 手机付款引导 */

  // 微信赞赏码的内容（wxp:// 是微信私有协议，只能由微信自己打开）
  var WX_PAY_URI =
    "wxp://f2f0jWzDSWSV5tk1GJm8fYvN5gTe8Dodid2XZC3uQdLAIPK4OPS3ZpvVFxsBhdAyzlkZ";
  var WX_HOST = WX_PAY_URI.slice("wxp://".length);
  var UA = navigator.userAgent || "";
  var IS_ANDROID = /Android/i.test(UA);
  var IS_IOS = /iPhone|iPad|iPod/i.test(UA);
  var IS_MOBILE =
    IS_ANDROID ||
    IS_IOS ||
    /HarmonyOS|Windows Phone|Mobile/i.test(UA) ||
    (navigator.maxTouchPoints > 1 && /Mac/.test(UA));
  var IN_WECHAT = /MicroMessenger/i.test(UA);

  var pay = {
    box: document.getElementById("payHelp"),
    title: document.getElementById("payHelpTitle"),
    qr: document.getElementById("payQr"),
    steps: document.getElementById("paySteps"),
    note: document.getElementById("payHelpText"),
    retry: document.getElementById("payRetry"),
    copy: document.getElementById("payCopy"),
    close: document.getElementById("payClose"),
    mode: "wx",
  };

  function hidePayHelp() {
    if (pay.box) pay.box.hidden = true;
  }

  function showPayHelp(mode) {
    if (!pay.box) {
      toast("长按二维码保存图片，再用微信扫一扫 → 相册");
      return;
    }
    pay.mode = mode;
    if (mode === "wx") {
      pay.title.textContent = "手机上这样付款";
      if (pay.qr) {
        pay.qr.src = "assets/img/wxpay_qr.png";
        pay.qr.classList.remove("is-round");
      }
      pay.steps.innerHTML =
        "<li>长按上面这张赞赏码 →「保存图片」</li>" +
        "<li>打开微信 → 右上角「+」→ 扫一扫 → 右下角「相册」→ 选这张图</li>" +
        "<li>金额随意，直接赞赏</li>";
      pay.note.textContent =
        "微信不允许网页直接跳进收款页，点一下就跳过去是做不到的，按上面三步最快。";
      if (pay.retry) pay.retry.textContent = "试着直接唤起微信";
    } else {
      pay.title.textContent = "手机上这样关注";
      if (pay.qr) {
        pay.qr.src = "assets/img/douyin_qr.png";
        pay.qr.classList.add("is-round");
      }
      pay.steps.innerHTML =
        "<li>长按上面这张抖音码 →「保存图片」</li>" +
        "<li>打开抖音 → 右上角「扫一扫」→ 右下角「相册」→ 选这张图</li>" +
        "<li>点「关注」即可</li>";
      pay.note.textContent = "抖音码不是普通网址，网页没法直接跳转，只能这样关注。";
      if (pay.retry) pay.retry.textContent = "试着直接打开抖音";
    }
    pay.box.hidden = false;
  }

  // Android：用 intent:// 让系统去分发，浏览器不认 scheme 时会自动回退到本站
  function wakeWeChat() {
    if (IS_ANDROID) {
      var fb = encodeURIComponent(baseUrl() + "account.html");
      window.location.href =
        "intent://" + WX_HOST +
        "#Intent;scheme=wxp;package=com.tencent.mm;S.browser_fallback_url=" + fb + ";end";
      return;
    }
    try {
      window.location.href = WX_PAY_URI;
    } catch (err) {
      /* iOS 等会被拦，上面的三步引导已经够用 */
    }
  }

  function wakeDouyin() {
    if (IS_ANDROID) {
      window.location.href =
        "intent://#Intent;scheme=snssdk1128;package=com.ss.android.ugc.aweme;end";
      return;
    }
    try {
      window.location.href = "snssdk1128://";
    } catch (err) {
      /* ignore */
    }
  }

  function copySiteLink() {
    copyText(baseUrl() + "account.html", "链接已复制，粘贴到微信里打开即可");
  }

  function initQrZoom() {
    var box = document.getElementById("qrLightbox");
    var bigImg = document.getElementById("qrBigImg");
    var bigTip = document.getElementById("qrBigTip");
    if (!box || !bigImg) return;

    function openBig(node, tip) {
      bigImg.src = node.dataset.qr;
      bigImg.alt = node.dataset.title || "二维码";
      bigImg.classList.toggle("is-round", node.dataset.round === "1");
      if (bigTip) bigTip.textContent = tip || "点击任意处关闭 · 长按可保存图片";
      box.classList.add("show");
    }

    document.addEventListener("click", function (e) {
      var btn = e.target.closest("#wxPay, #dyOpen");
      if (btn) {
        e.preventDefault();
        showPayHelp(btn.id === "wxPay" ? "wx" : "dy");
        return;
      }

      var node = e.target.closest("[data-qr]");
      if (!node) return;
      var isWx = node.classList.contains("code-wx");

      // 手机点二维码：直接给「保存图片 + 相册识别」的引导（只有这条路真能走通）
      if (IS_MOBILE && !IN_WECHAT) {
        e.preventDefault();
        showPayHelp(isWx ? "wx" : "dy");
        return;
      }

      // 微信内置浏览器：长按识别是官方放行的路径
      openBig(
        node,
        IN_WECHAT
          ? "长按图片 → 识别图中二维码，即可直接打开"
          : "点击任意处关闭 · 长按可保存图片"
      );
    });

    box.addEventListener("click", function () {
      box.classList.remove("show");
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        box.classList.remove("show");
        hidePayHelp();
      }
    });

    if (pay.box) {
      pay.box.addEventListener("click", function (e) {
        if (e.target === pay.box) hidePayHelp();
      });
    }
    if (pay.close) pay.close.addEventListener("click", hidePayHelp);
    if (pay.copy) pay.copy.addEventListener("click", copySiteLink);
    if (pay.retry) {
      pay.retry.addEventListener("click", function () {
        if (pay.mode === "dy") wakeDouyin();
        else wakeWeChat();
      });
    }

    // 手机上才显示这些入口，桌面端保持看大图
    if (IS_MOBILE) {
      var wxBtn = document.getElementById("wxPay");
      if (wxBtn) {
        wxBtn.textContent = "手机怎么付款 →";
        wxBtn.hidden = false;
      }
      var dyBtn = document.getElementById("dyOpen");
      if (dyBtn) {
        dyBtn.textContent = "手机怎么关注 →";
        dyBtn.hidden = false;
      }
      var wxHint = document.querySelector(".code-wx")
        ? document.querySelector(".code-wx").parentNode.querySelector(".code-hint")
        : null;
      if (wxHint) {
        wxHint.textContent = IN_WECHAT ? "长按二维码识别即可付款" : "点击查看手机付款方法";
      }
    }
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
