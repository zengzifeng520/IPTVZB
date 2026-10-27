/* 通用复制工具（v2）
   ------------------------------------------------------------
   手机浏览器（微信 / 华为 / 夸克 / UC 等 WebView）里，
   navigator.clipboard.writeText 常常「resolve 了但没真正写进剪贴板」，
   所以这里改成：优先用同步的 execCommand（在点击事件里同步执行才有效），
   失败再退回 Clipboard API，最后还有手动复制面板兜底。

   暴露：
     window.zzfCopy(text, { ok, fail, anchor })
       anchor：页面上显示这段文字的可见元素，用来「选中真实文字再复制」
     window.zzfCopySheet(text)  直接打开手动复制面板
     window.zzfCopyBar(msg, text) 底部提示条（带「手动复制」按钮） */
(function () {
  "use strict";

  var sheet = null;
  var area = null;
  var bar = null;

  /* ---------------------------------------------------------- 手动复制面板 */

  function buildSheet() {
    sheet = document.createElement("div");
    sheet.className = "copy-sheet";
    sheet.innerHTML =
      '<div class="copy-sheet-box">' +
      "<h3>手动复制地址</h3>" +
      "<p>长按下面的地址 →「全选 / 复制」，再粘贴到播放器里。</p>" +
      '<textarea class="copy-sheet-text" readonly rows="3" spellcheck="false"></textarea>' +
      '<div class="copy-sheet-acts">' +
      '<button class="btn" type="button" data-sheet-all>全选</button>' +
      '<button class="btn btn-primary" type="button" data-sheet-close>关闭</button>' +
      "</div></div>";
    document.body.appendChild(sheet);
    area = sheet.querySelector(".copy-sheet-text");

    sheet.addEventListener("click", function (e) {
      if (e.target === sheet || e.target.hasAttribute("data-sheet-close")) hideSheet();
      if (e.target.hasAttribute("data-sheet-all")) pickAll();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") hideSheet();
    });
  }

  function pickAll() {
    if (!area) return;
    area.focus();
    area.select();
    try {
      area.setSelectionRange(0, area.value.length);
    } catch (e) {}
  }

  function showSheet(text) {
    if (!sheet) buildSheet();
    area.value = text;
    sheet.classList.add("show");
    setTimeout(pickAll, 60);
  }

  function hideSheet() {
    if (sheet) sheet.classList.remove("show");
  }

  /* ---------------------------------------------------------- 底部提示条 */

  function buildBar() {
    bar = document.createElement("div");
    bar.className = "copy-bar";
    bar.innerHTML =
      '<span class="copy-bar-txt"></span>' +
      '<button class="copy-bar-btn" type="button">手动复制</button>';
    document.body.appendChild(bar);
    bar.querySelector(".copy-bar-btn").addEventListener("click", function (e) {
      e.preventDefault();
      showSheet(bar.getAttribute("data-text") || "");
      hideBar();
    });
  }

  function showBar(msg, text) {
    if (!bar) buildBar();
    bar.querySelector(".copy-bar-txt").textContent = msg;
    bar.setAttribute("data-text", text);
    bar.classList.add("show");
    clearTimeout(showBar._t);
    showBar._t = setTimeout(hideBar, 6000);
  }

  function hideBar() {
    if (bar) bar.classList.remove("show");
  }

  /* ---------------------------------------------------------- 复制实现 */

  // 方式一：直接选中页面上那个真实的 readonly 输入框再复制
  // （很多手机浏览器只允许「对可见输入框」执行复制，隐藏 textarea 会被拒）
  function copyViaInput(input) {
    if (!input || !input.select) return false;
    var ok = false;
    try {
      input.focus();
      input.select();
      input.setSelectionRange(0, String(input.value || "").length);
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    try {
      input.blur();
    } catch (e) {}
    return ok;
  }

  // 方式二：临时 textarea + execCommand（必须同步调用）
  function copyViaTextarea(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    // 必须落在视口内、参与布局：部分 WebView 会跳过 display:none / 视口外的元素
    ta.style.cssText =
      "position:fixed;left:8px;bottom:8px;width:2em;height:2em;padding:0;margin:0;" +
      "border:0;outline:none;opacity:0.01;font-size:16px;";
    document.body.appendChild(ta);
    var ok = false;
    try {
      ta.focus();
      ta.select();
      ta.setSelectionRange(0, text.length);
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    document.body.removeChild(ta);
    return ok;
  }

  // 方式三：选中页面上真实显示的文字再复制（部分 WebView 只认这种）
  function copyViaSelection(node) {
    if (!node || !document.createRange || !window.getSelection) return false;
    var sel = window.getSelection();
    var ok = false;
    try {
      var range = document.createRange();
      range.selectNodeContents(node);
      sel.removeAllRanges();
      sel.addRange(range);
      ok = document.execCommand("copy");
    } catch (e) {
      ok = false;
    }
    try {
      sel.removeAllRanges();
    } catch (e) {}
    return ok;
  }

  window.zzfCopy = function (text, opts) {
    opts = opts || {};
    var done = opts.ok || function () {
      showBar("地址已复制", text);
    };
    var fail = opts.fail || function () {
      // 不弹面板打断用户：只提示，地址本身可长按复制
      showBar("没复制上？长按地址手动复制", text);
    };

    if (!text) return fail();

    // 1) 直接从页面上那个真实输入框复制（手机成功率最高）
    if (copyViaInput(opts.input)) return done();

    // 2) 临时 textarea 同步复制
    if (copyViaTextarea(text)) return done();

    // 3) 选中页面上的可见文字再复制
    if (copyViaSelection(opts.anchor)) return done();

    // 4) 最后才用异步 Clipboard API
    if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, fail);
      return;
    }

    fail();
  };

  window.zzfCopySheet = showSheet;
  window.zzfCopyBar = showBar;
})();
