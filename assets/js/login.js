/* 登录 / 注册页 */
(function () {
  "use strict";

  var qs = new URLSearchParams(location.search);
  var next = qs.get("next") || "index.html";
  var tab = qs.get("tab") === "register" ? "register" : "login";

  var el = {
    title: document.getElementById("authTitle"),
    sub: document.getElementById("authSub"),
    tabs: document.querySelectorAll(".auth-tab"),
    login: document.getElementById("formLogin"),
    register: document.getElementById("formRegister"),
    loginPhone: document.getElementById("loginPhone"),
    loginPwd: document.getElementById("loginPwd"),
    regPhone: document.getElementById("regPhone"),
    regPwd: document.getElementById("regPwd"),
    regPwd2: document.getElementById("regPwd2"),
    picker: document.getElementById("regionPicker"),
    err: document.getElementById("authErr"),
    toast: document.getElementById("toast"),
  };

  var state = { region: "", regions: [] };

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
    }, 2400);
  }

  function showErr(msg) {
    el.err.textContent = msg || "";
    el.err.classList.toggle("show", !!msg);
  }

  function setTab(name) {
    tab = name;
    el.tabs.forEach(function (t) {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    el.login.hidden = name !== "login";
    el.register.hidden = name !== "register";
    el.title.textContent = name === "login" ? "登录账号" : "注册账号";
    el.sub.innerHTML =
      name === "login"
        ? "体验版可查看 1 个地区的频道，开通后解锁全部地区。"
        : "注册后立即可以查看 1 个地区的频道地址，随时可升级解锁全部。";
    showErr("");
    var first = name === "login" ? el.loginPhone : el.regPhone;
    setTimeout(function () {
      first && first.focus();
    }, 60);
  }

  function goNext() {
    var url = next;
    // 只允许站内相对跳转
    if (/^[a-z]+:/i.test(url) || url.indexOf("//") === 0) url = "index.html";
    location.replace(url);
  }

  /* ---------------------------------------------------------- 地区 */

  function loadRegions() {
    return fetch("data/regions.json", { cache: "no-cache" })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (d) {
        state.regions = (d.regions || []).slice().sort(function (a, b) {
          return b.streams - a.streams;
        });
        el.picker.innerHTML = state.regions
          .map(function (r) {
            return (
              '<button type="button" class="region-opt" data-key="' +
              esc(r.key) +
              '">' +
              '<b>' +
              esc(r.name) +
              "</b>" +
              '<span>' +
              r.channels +
              " 频道</span></button>"
            );
          })
          .join("");
      })
      .catch(function () {
        el.picker.innerHTML = '<div class="region-picker-loading">地区数据加载失败，请刷新重试</div>';
      });
  }

  el.picker.addEventListener("click", function (e) {
    var btn = e.target.closest(".region-opt");
    if (!btn) return;
    state.region = btn.dataset.key;
    el.picker.querySelectorAll(".region-opt").forEach(function (b) {
      b.classList.toggle("active", b === btn);
    });
  });

  /* ---------------------------------------------------------- 提交 */

  el.tabs.forEach(function (t) {
    t.addEventListener("click", function () {
      setTab(t.dataset.tab);
    });
  });

  el.login.addEventListener("submit", function (e) {
    e.preventDefault();
    showErr("");
    var r = window.IVAUTH.login(el.loginPhone.value, el.loginPwd.value);
    if (!r.ok) return showErr(r.msg);
    toast("登录成功");
    setTimeout(goNext, 400);
  });

  el.register.addEventListener("submit", function (e) {
    e.preventDefault();
    showErr("");
    var p1 = el.regPwd.value;
    var p2 = el.regPwd2.value;
    if (p1 !== p2) return showErr("两次输入的密码不一致");
    if (!state.region) return showErr("请先选择你所在的地区");
    var r = window.IVAUTH.register(el.regPhone.value, p1, state.region);
    if (!r.ok) return showErr(r.msg);
    toast("注册成功");
    setTimeout(goNext, 400);
  });

  /* ---------------------------------------------------------- 启动 */

  // 已登录直接走人
  if (window.IVAUTH.isLoggedIn() && qs.get("stay") !== "1") {
    goNext();
    return;
  }

  loadRegions();
  setTab(tab);
})();
