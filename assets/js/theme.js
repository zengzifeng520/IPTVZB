/* 主题切换：深色（默认）↔ 浅灰。
   - 尽早应用主题，避免页面闪烁：脚本在 <head> 里同步执行，
     读 localStorage 后立刻给 <html> 设 data-theme。
   - 按钮带 [data-theme-toggle]，点击切换并记住选择。 */
(function () {
  "use strict";

  var KEY = "iv_theme_v1";

  var SUN =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<circle cx="12" cy="12" r="4"/>' +
    '<path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></svg>';

  var MOON =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

  function isLight() {
    return document.documentElement.getAttribute("data-theme") === "light";
  }

  function apply(theme) {
    if (theme === "light") {
      document.documentElement.setAttribute("data-theme", "light");
      var meta = document.querySelector('meta[name="theme-color"]');
      if (meta) meta.setAttribute("content", "#f2f3f5");
    } else {
      document.documentElement.removeAttribute("data-theme");
      var m2 = document.querySelector('meta[name="theme-color"]');
      if (m2) m2.setAttribute("content", "#07080c");
    }
  }

  // 尽早应用：默认浅色（浅灰背景），用户切到深色后会记住
  var saved = null;
  try {
    saved = localStorage.getItem(KEY);
  } catch (e) {}
  if (saved === "light" || saved === "dark") {
    apply(saved);
  } else {
    apply("light");
  }

  function toggle() {
    apply(isLight() ? "dark" : "light");
    try {
      localStorage.setItem(KEY, isLight() ? "light" : "dark");
    } catch (e) {}
    refresh();
  }

  function refresh() {
    var light = isLight();
    var btns = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].innerHTML = light ? MOON : SUN;
      btns[i].setAttribute("title", light ? "切换到深色" : "切换到浅色");
      btns[i].setAttribute("aria-label", light ? "切换到深色" : "切换到浅色");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      refresh();
      document.addEventListener("click", function (e) {
        var b = e.target.closest("[data-theme-toggle]");
        if (b) {
          e.preventDefault();
          toggle();
        }
      });
    });
  } else {
    refresh();
    document.addEventListener("click", function (e) {
      var b = e.target.closest("[data-theme-toggle]");
      if (b) {
        e.preventDefault();
        toggle();
      }
    });
  }
})();
