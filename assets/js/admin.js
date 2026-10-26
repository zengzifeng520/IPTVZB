/* 后台管理：管理员账号登录 + 直接读写订阅用户表
   ------------------------------------------------------------
   页面只暴露「账号 / 密码」，不出现任何第三方平台字样。
   读：登录后即可查看订阅人数与状态。
   写：保存时需要一次「管理密钥」（写入权限），只存本机 localStorage。
   改动提交后自动重建订阅，约 1 分钟生效。 */
(function () {
  "use strict";

  /* 管理员凭据与数据位置（不在页面上展示） */
  var ADMIN = { user: "admin", pass: "342815" };
  var DATA = { owner: "zengzifeng520", repo: "ZZF", branch: "main", file: "data/users.json" };
  var API = "https://api.github.com";

  var K_KEY = "iv_admin_key";
  var K_LOGIN = "iv_admin_login";
  var SALT = "zzf-sub-2026"; // 与 spider/subs.py 的 TOKEN_SALT 一致

  var DAY = 86400000;

  var state = {
    key: "",
    sha: "",
    users: {},
    rows: [],
    filter: "",
    dirty: false,
    demo: false,
  };

  var el = {
    login: document.getElementById("loginPanel"),
    dash: document.getElementById("dash"),
    user: document.getElementById("userInput"),
    pass: document.getElementById("passInput"),
    remember: document.getElementById("rememberChk"),
    loginBtn: document.getElementById("loginBtn"),
    loginMsg: document.getElementById("loginMsg"),
    logout: document.getElementById("logoutBtn"),
    stats: document.getElementById("adminStats"),
    body: document.getElementById("userBody"),
    search: document.getElementById("searchInput"),
    addBtn: document.getElementById("addBtn"),
    reloadBtn: document.getElementById("reloadBtn"),
    saveBtn: document.getElementById("saveBtn"),
    saveHint: document.getElementById("saveHint"),
    toast: document.getElementById("toast"),
  };

  /* ---------------------------------------------------------- 小工具 */

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function toast(msg, ms) {
    el.toast.textContent = msg;
    el.toast.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(function () {
      el.toast.classList.remove("show");
    }, ms || 2600);
  }

  function b64enc(str) {
    var bytes = new TextEncoder().encode(str);
    var bin = "";
    for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }

  function b64dec(b64) {
    var bin = atob(String(b64).replace(/\s/g, ""));
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder().decode(bytes);
  }

  function ymd(d) {
    function p(n) {
      return n < 10 ? "0" + n : "" + n;
    }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }

  function expTs(dateStr) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr || "");
    if (!m) return 0;
    return new Date(+m[1], +m[2] - 1, +m[3], 23, 59, 59).getTime();
  }

  function daysLeft(ts) {
    return Math.max(0, Math.ceil((ts - Date.now()) / DAY));
  }

  function groupSid(sid) {
    return String(sid || "").replace(/(.{4})(?=.)/g, "$1 ");
  }

  function tokenOf(sid) {
    if (window.IVAUTH && window.IVAUTH.tokenOf) return window.IVAUTH.tokenOf(sid);
    return "";
  }

  /* ---------------------------------------------------------- 数据接口 */

  function request(path, opts) {
    opts = opts || {};
    var headers = { Accept: "application/vnd.github+json" };
    if (state.key) headers.Authorization = "Bearer " + state.key;
    if (opts.body) headers["Content-Type"] = "application/json";
    opts.headers = headers;
    return fetch(API + path, opts).then(function (r) {
      return r.text().then(function (t) {
        var d = null;
        try {
          d = t ? JSON.parse(t) : null;
        } catch (e) {}
        if (!r.ok) {
          var err = new Error((d && d.message) || "HTTP " + r.status);
          err.status = r.status;
          throw err;
        }
        return d;
      });
    });
  }

  function explain(err) {
    if (err.status === 401 || err.status === 403) return "管理密钥无效或已过期";
    if (err.status === 404) return "数据文件暂时读不到，请稍后再试";
    if (err.status === 409) return "数据刚被改动过，请刷新后重试";
    if (err.status === 422) return "提交内容被拒绝，请检查到期日期";
    return err.message || "操作失败";
  }

  function dataPath() {
    return "/repos/" + DATA.owner + "/" + DATA.repo + "/contents/" + DATA.file;
  }

  function loadRemote() {
    var path = dataPath() + "?ref=" + DATA.branch + "&_=" + Date.now();
    return request(path).then(function (d) {
      state.sha = (d && d.sha) || "";
      var text = d && d.content ? b64dec(d.content) : "{}";
      var obj = {};
      try {
        obj = JSON.parse(text) || {};
      } catch (e) {
        obj = {};
      }
      state.users = obj;
      buildRows();
      render();
      return true;
    });
  }

  /** 保存前确保有写入权限的密钥（只在本机保存，不写进数据） */
  function ensureKey() {
    if (state.key) return true;
    var k = window.prompt(
      "首次保存需要填写一次「管理密钥」（用于取得写入权限）。\n\n只保存在本机浏览器，不会上传。"
    );
    if (!k) return false;
    state.key = k.trim();
    try {
      localStorage.setItem(K_KEY, state.key);
    } catch (e) {}
    return true;
  }

  function saveRemote() {
    var out = {};
    state.rows.forEach(function (r) {
      if (r.deleted) return;
      var sid = String(r.sid || "").trim().toUpperCase();
      if (!sid) return;
      var orig = state.users[sid] || null;
      if (orig && orig.expire === r.expire) {
        out[sid] = orig;
        return;
      }
      var rec = { expire: r.expire };
      if (orig && orig.created) rec.created = orig.created;
      if (!expTs(r.expire)) delete rec.expire;
      out[sid] = rec;
    });

    var body = {
      message: "admin: 更新订阅用户（" + Object.keys(out).length + " 人）",
      content: b64enc(JSON.stringify(out, null, 1) + "\n"),
      branch: DATA.branch,
    };
    if (state.sha) body.sha = state.sha;

    return request(dataPath(), {
      method: "PUT",
      body: JSON.stringify(body),
    }).then(function (d) {
      state.sha = (d && d.content && d.content.sha) || "";
      state.users = out;
      state.dirty = false;
      updateDirty();
      return true;
    });
  }

  /* ---------------------------------------------------------- 模型 */

  function buildRows() {
    state.rows = Object.keys(state.users).map(function (sid) {
      var info = state.users[sid] || {};
      var date = info.expire || "";
      if (!date && info.ts) date = ymd(new Date(Number(info.ts) * 1000));
      return { sid: sid, expire: date, deleted: false };
    });
    state.rows.sort(function (a, b) {
      return expTs(b.expire) - expTs(a.expire);
    });
  }

  function stats() {
    var now = Date.now();
    var s = { total: 0, ok: 0, exp: 0, soon: 0 };
    state.rows.forEach(function (r) {
      if (r.deleted) return;
      s.total++;
      var ts = expTs(r.expire);
      if (!ts) {
        s.exp++;
        return;
      }
      if (ts > now) {
        s.ok++;
        if (ts - now <= 7 * DAY) s.soon++;
      } else s.exp++;
    });
    return s;
  }

  /* ---------------------------------------------------------- 渲染 */

  function renderStats() {
    var s = stats();
    el.stats.innerHTML = [
      { n: s.total, t: "总订阅", cls: "" },
      { n: s.ok, t: "有效", cls: "ok" },
      { n: s.soon, t: "7 天内到期", cls: "warn" },
      { n: s.exp, t: "已过期", cls: "err" },
    ]
      .map(function (i) {
        return '<div class="admin-stat ' + i.cls + '"><b>' + i.n + "</b><span>" + i.t + "</span></div>";
      })
      .join("");
  }

  function render() {
    renderStats();
    var kw = state.filter.trim().toUpperCase();
    var list = state.rows.filter(function (r) {
      if (!kw) return true;
      return (
        String(r.sid).toUpperCase().indexOf(kw) >= 0 ||
        tokenOf(r.sid).toUpperCase().indexOf(kw) >= 0
      );
    });

    if (!list.length) {
      el.body.innerHTML =
        '<tr><td colspan="6" class="empty-inline">' +
        (state.rows.length ? "没有匹配的用户" : "还没有订阅用户，点「+ 新增用户」加一个") +
        "</td></tr>";
      return;
    }

    var now = Date.now();
    el.body.innerHTML = list
      .map(function (r) {
        var ts = expTs(r.expire);
        var sid = String(r.sid);
        var status = !ts
          ? '<span class="pill pill-err">日期无效</span>'
          : ts > now
            ? '<span class="pill pill-ok">有效</span>'
            : '<span class="pill pill-err">已过期</span>';
        return (
          '<tr data-sid="' + esc(sid) + '" class="' + (r.deleted ? "is-deleted" : "") + '">' +
          '<td><code class="admin-sid">' + esc(r.deleted ? groupSid(sid) + "（将删除）" : groupSid(sid)) + "</code></td>" +
          '<td><code class="admin-tok">' + esc(tokenOf(sid)) + "</code></td>" +
          "<td>" +
          (r.deleted
            ? '<span class="admin-muted">—</span>'
            : '<input type="date" class="admin-date" value="' + esc(r.expire) + '" data-act="date">') +
          "</td>" +
          "<td>" + (r.deleted ? "—" : ts ? daysLeft(ts) + " 天" : "—") + "</td>" +
          "<td>" + (r.deleted ? '<span class="pill">待删除</span>' : status) + "</td>" +
          '<td class="ta-right admin-acts">' +
          (r.deleted
            ? '<button class="btn btn-sm" data-act="undo" type="button">撤销</button>'
            : '<button class="btn btn-sm" data-act="p30" type="button">+30 天</button>' +
              '<button class="btn btn-sm" data-act="p90" type="button">+90 天</button>' +
              '<button class="btn btn-sm btn-danger" data-act="del" type="button">删除</button>') +
          "</td></tr>"
        );
      })
      .join("");
  }

  function updateDirty() {
    el.saveBtn.disabled = !state.dirty || state.demo;
    el.saveHint.textContent = state.demo
      ? "演示模式：数据是假的，不会提交"
      : state.dirty
        ? "有未保存的改动"
        : "改动后点右侧「保存并发布」";
  }

  function findRow(sid) {
    for (var i = 0; i < state.rows.length; i++) {
      if (String(state.rows[i].sid) === sid) return state.rows[i];
    }
    return null;
  }

  /* ---------------------------------------------------------- 事件 */

  el.loginBtn.addEventListener("click", function () {
    var u = (el.user.value || "").trim();
    var p = el.pass.value || "";
    if (!u || !p) return toast("请输入账号和密码");
    if (u !== ADMIN.user || p !== ADMIN.pass) return toast("账号或密码不正确", 3000);

    el.loginBtn.disabled = true;
    el.loginBtn.textContent = "正在登录…";
    if (el.remember.checked) {
      try {
        localStorage.setItem(K_LOGIN, "1");
      } catch (e) {}
    }
    state.key = localStorage.getItem(K_KEY) || "";

    loadRemote()
      .then(function () {
        showDash();
        toast("登录成功");
      })
      .catch(function (err) {
        showDash(); // 仍然进后台，保存时会再要求密钥
        toast("读取数据失败：" + explain(err), 4000);
      })
      .then(function () {
        el.loginBtn.disabled = false;
        el.loginBtn.textContent = "登录后台";
      });
  });

  el.pass.addEventListener("keydown", function (e) {
    if (e.key === "Enter") el.loginBtn.click();
  });

  function showDash() {
    el.login.hidden = true;
    el.dash.hidden = false;
    el.logout.hidden = false;
    render();
    updateDirty();
  }

  el.logout.addEventListener("click", function () {
    try {
      localStorage.removeItem(K_LOGIN);
      localStorage.removeItem(K_KEY);
    } catch (e) {}
    state.key = "";
    state.sha = "";
    state.users = {};
    state.rows = [];
    el.dash.hidden = true;
    el.login.hidden = false;
    el.logout.hidden = true;
    el.pass.value = "";
  });

  el.search.addEventListener("input", function () {
    state.filter = el.search.value;
    render();
  });

  el.reloadBtn.addEventListener("click", function () {
    loadRemote()
      .then(function () {
        state.dirty = false;
        updateDirty();
        toast("已重新读取");
      })
      .catch(function (err) {
        toast("读取失败：" + explain(err), 4000);
      });
  });

  el.addBtn.addEventListener("click", function () {
    var sid = (window.prompt("新增用户\n请输入用户的 12 位赞助码（用户可在赞助页底部看到）") || "")
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    if (!sid) return;
    if (sid.length < 6) return toast("赞助码太短");
    if (state.users[sid] || findRow(sid)) return toast("这个赞助码已经存在");

    var days = window.prompt("有效天数（例如 30 / 90 / 365）", "30");
    if (days == null) return;
    var n = parseInt(days, 10);
    if (!n || n <= 0) return toast("天数不正确");

    state.rows.unshift({ sid: sid, expire: ymd(new Date(Date.now() + n * DAY)), deleted: false });
    state.dirty = true;
    updateDirty();
    render();
    toast("已添加，别忘了点「保存并发布」");
  });

  el.body.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-act]");
    if (!btn) return;
    var tr = e.target.closest("tr");
    var row = tr && findRow(tr.getAttribute("data-sid"));
    if (!row) return;

    var act = btn.getAttribute("data-act");
    if (act === "p30" || act === "p90") {
      var add = act === "p30" ? 30 : 90;
      var base = Math.max(expTs(row.expire), Date.now());
      row.expire = ymd(new Date(base + add * DAY));
      state.dirty = true;
    } else if (act === "del") {
      row.deleted = true;
      state.dirty = true;
    } else if (act === "undo") {
      row.deleted = false;
      state.dirty = true;
    }
    updateDirty();
    render();
  });

  el.body.addEventListener("change", function (e) {
    var input = e.target.closest('[data-act="date"]');
    if (!input) return;
    var tr = e.target.closest("tr");
    var row = tr && findRow(tr.getAttribute("data-sid"));
    if (!row) return;
    row.expire = input.value;
    state.dirty = true;
    updateDirty();
    render();
  });

  el.saveBtn.addEventListener("click", function () {
    if (!ensureKey()) return;
    el.saveBtn.disabled = true;
    el.saveBtn.textContent = "正在保存…";

    saveRemote()
      .then(function () {
        toast("已保存，约 1 分钟后生效", 3600);
        return loadRemote().then(function () {
          state.dirty = false;
          updateDirty();
        });
      })
      .catch(function (err) {
        if (err.status === 401 || err.status === 403) {
          try {
            localStorage.removeItem(K_KEY);
          } catch (e) {}
          state.key = "";
          toast("管理密钥不正确，请重新填写", 4000);
          return;
        }
        if (err.status === 409) {
          return loadRemote().then(function () {
            return saveRemote().then(function () {
              state.dirty = false;
              updateDirty();
              toast("已保存（自动重试成功），约 1 分钟生效", 3600);
            });
          });
        }
        toast("保存失败：" + explain(err), 4500);
      })
      .then(function () {
        el.saveBtn.textContent = "保存并发布";
        updateDirty();
      });
  });

  /* ---------------------------------------------------------- 启动 */

  function demoMode() {
    state.demo = true;
    var t = Date.now();
    var fake = {};
    fake["A1B2C3D4E5F6"] = { expire: ymd(new Date(t + 28 * DAY)) };
    fake["G7H8J9K2L3M4"] = { expire: ymd(new Date(t + 3 * DAY)) };
    fake["N5P6Q7R8S9T2"] = { expire: ymd(new Date(t + 180 * DAY)) };
    fake["U3V4W5X6Y7Z8"] = { expire: "2026-10-20" };
    state.users = fake;
    buildRows();
    showDash();
    el.logout.hidden = true;
  }

  (function boot() {
    if (/[?&]demo=1/.test(location.search)) {
      demoMode();
      return;
    }
    // 记住登录状态：只跳过密码，写入仍需密钥
    if (localStorage.getItem(K_LOGIN) === "1") {
      state.key = localStorage.getItem(K_KEY) || "";
      loadRemote()
        .then(showDash)
        .catch(function () {
          try {
            localStorage.removeItem(K_LOGIN);
          } catch (e) {}
        });
    }
  })();
})();
