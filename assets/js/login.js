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
    rememberMe: document.getElementById("rememberMe"),
    regPhone: document.getElementById("regPhone"),
    regPwd: document.getElementById("regPwd"),
    regPwd2: document.getElementById("regPwd2"),
    picker: document.getElementById("regionPicker"),
    err: document.getElementById("authErr"),
    toast: document.getElementById("toast"),
    logged: document.getElementById("authLogged"),
    alAvatar: document.getElementById("alAvatar"),
    alPhone: document.getElementById("alPhone"),
    alPlan: document.getElementById("alPlan"),
    alLogout: document.getElementById("alLogout"),
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
    var phone = el.loginPhone.value;
    var pwd = el.loginPwd.value;
    var r = window.IVAUTH.login(phone, pwd);
    if (!r.ok) return showErr(r.msg);

    // 勾选则连密码一起记住，否则只记手机号
    window.IVAUTH.saveRemember(
      String(phone).replace(/[\s-]/g, ""),
      el.rememberMe.checked ? pwd : ""
    );

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

    // 刚注册的账号直接记住，省得下次再输
    window.IVAUTH.saveRemember(r.phone, el.rememberMe.checked ? p1 : "");

    toast("注册成功");
    setTimeout(goNext, 400);
  });

  /* ---------------------------------------------------------- 已登录状态 */

  function renderLogged(u) {
    if (!u) {
      el.logged.hidden = true;
      return;
    }
    el.logged.hidden = false;
    el.alAvatar.textContent = u.phoneMask.slice(-4, -3) || "光";
    el.alPhone.textContent = u.phoneMask;
    el.alPlan.textContent = u.member ? "会员" : "体验版";
    el.alPlan.className = "pill " + (u.member ? "pill-ok" : "pill-warn");
  }

  el.alLogout.addEventListener("click", function () {
    window.IVAUTH.logout();
    renderLogged(null);
    showErr("");
    toast("已退出登录");
    setTab("login");
    // 退出后仍保留记住的账号，方便再次登录
    prefill();
  });

  /* ---------------------------------------------------------- 预填 */

  function prefill() {
    var rec = window.IVAUTH.remembered();
    if (!rec) return;
    if (!el.loginPhone.value) el.loginPhone.value = rec.phone;
    if (!el.loginPwd.value && rec.pwd) {
      el.loginPwd.value = rec.pwd;
      el.rememberMe.checked = true;
    } else if (!rec.pwd) {
      el.rememberMe.checked = false;
    }
  }

  /* ---------------------------------------------------------- 启动 */

  var current = window.IVAUTH.user();

  // 已登录且不是「切换账号」进来的，直接放行
  if (current && qs.get("stay") !== "1") {
    goNext();
    return;
  }

  renderLogged(current);
  prefill();
  loadRegions();
  setTab(tab);
})();
