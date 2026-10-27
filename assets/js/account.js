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

  /* ---------------------------------------------------------- 二维码大图 + 手机直接付款 */

  // 微信赞赏码里编的内容（wxp:// 只能由微信自己处理，网页只能「唤起微信」）
  var WX_PAY_URI =
    "wxp://f2f0jWzDSWSV5tk1GJm8fYvN5gTe8Dodid2XZC3uQdLAIPK4OPS3ZpvVFxsBhdAyzlkZ";
  var UA = navigator.userAgent || "";
  var IS_MOBILE =
    /Android|iPhone|iPad|iPod|HarmonyOS|Windows Phone|Mobile/i.test(UA) ||
    (navigator.maxTouchPoints > 1 && /Mac/.test(UA));
  var IN_WECHAT = /MicroMessenger/i.test(UA);

  var pay = {
    box: document.getElementById("payHelp"),
    title: document.getElementById("payHelpTitle"),
    text: document.getElementById("payHelpText"),
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
      toast("请长按二维码识别");
      return;
    }
    pay.mode = mode;
    if (mode === "wx") {
      pay.title.textContent = "正在尝试打开微信…";
      pay.text.innerHTML =
        "浏览器不允许网页直接跳到微信收款页时，微信不会自动弹出。<br>" +
        "可以点「再试一次」，或复制本站链接粘贴到微信里打开，再<b>长按二维码识别</b>即可付款。";
      if (pay.retry) pay.retry.textContent = "再试一次";
    } else {
      pay.title.textContent = "抖音码请在抖音里识别";
      pay.text.innerHTML =
        "抖音码不是普通网址，网页没法直接跳转。<br>" +
        "打开抖音 → 右上角「扫一扫」→ 相册，选这张二维码截图就能关注；" +
        "在抖音里打开本站也可以直接长按识别。";
      if (pay.retry) pay.retry.textContent = "打开抖音";
    }
    pay.box.hidden = false;
  }

  // 唤起微信：直接改 location 是最容易被系统接管的做法
  function wakeWeChat() {
    try {
      window.location.href = WX_PAY_URI;
    } catch (err) {
      /* 某些浏览器会直接拦截，交给下面的兜底提示 */
    }
  }

  function wakeDouyin() {
    try {
      window.location.href = "snssdk1128://";
    } catch (err) {
      /* ignore */
    }
  }

  function copySiteLink() {
    var url = baseUrl() + "account.html";
    copyText(url, "链接已复制，粘贴到微信里打开即可");
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
        if (btn.id === "wxPay") {
          showPayHelp("wx");
          setTimeout(wakeWeChat, 320);
        } else {
          showPayHelp("dy");
        }
        return;
      }

      var node = e.target.closest("[data-qr]");
      if (!node) return;
      var isWx = node.classList.contains("code-wx");

      // 手机点微信码：先在站内弹引导层，再尝试唤起微信
      if (IS_MOBILE && isWx && !IN_WECHAT) {
        e.preventDefault();
        showPayHelp("wx");
        setTimeout(wakeWeChat, 320);
        return;
      }

      // 微信内置浏览器：长按识别才是官方路径
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

    // 手机上才显示「直接付款」入口，桌面端保持原来的看大图
    if (IS_MOBILE) {
      var wxBtn = document.getElementById("wxPay");
      if (wxBtn) wxBtn.hidden = false;
      var dyBtn = document.getElementById("dyOpen");
      if (dyBtn) {
        dyBtn.textContent = "手机点此打开抖音 →";
        dyBtn.hidden = false;
      }
      var wxHint = document.querySelector(".code-wx")
        ? document.querySelector(".code-wx").parentNode.querySelector(".code-hint")
        : null;
      if (wxHint) {
        wxHint.textContent = IN_WECHAT ? "长按二维码识别即可付款" : "点击二维码直接付款";
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
