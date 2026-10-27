/* 通用复制工具
   ------------------------------------------------------------
   三级兜底，手机内置浏览器（微信 / 华为 / 夸克等 WebView）也能复制：
     1. navigator.clipboard.writeText（HTTPS + 现代浏览器）
     2. textarea + document.execCommand('copy')（老浏览器 / 权限被拒）
     3. 手动复制面板：把地址放进可长按选中的输入框，用户自己全选复制
   暴露：window.zzfCopy(text, { ok, fail }) */
(function () {
  "use strict";

  var sheet = null;
  var area = null;

  function buildSheet() {
    sheet = document.createElement("div");
    sheet.className = "copy-sheet";
    sheet.innerHTML =
      '<div class="copy-sheet-box">' +
      "<h3>手动复制地址</h3>" +
      "<p>当前浏览器不允许网页直接写入剪贴板。长按下面的地址 →「全选 / 复制」即可。</p>" +
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

  function legacyCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    // 必须真实存在且可聚焦，opacity:0 的 1px 元素在部分 WebView 里选不中
    ta.style.cssText =
      "position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:0;outline:none;opacity:0;";
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

  window.zzfCopy = function (text, opts) {
    opts = opts || {};
    var done = opts.ok || function () {};
    var fail = opts.fail || function () { showSheet(text); };

    if (!text) return fail();

    if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {
        if (legacyCopy(text)) done();
        else fail();
      });
      return;
    }
    if (legacyCopy(text)) done();
    else fail();
  };

  window.zzfCopySheet = showSheet;
})();
