/* 后台管理：直接用 GitHub Contents 接口读写 data/users.json
   ------------------------------------------------------------
   本站是纯静态站，没有自建服务端。后台靠一个本仓库的 PAT 工作：
   读 → GET  /repos/<repo>/contents/data/users.json
   写 → PUT  同上（带 sha），提交后 Actions 自动重建订阅，约 1 分钟生效。
   Token 只存在本机 localStorage，不发往任何第三方。 */
(function () {
  "use strict";

  var API = "https://api.github.com";
  var FILE = "data/users.json";
  var BRANCH = "main";
  var K_TOKEN = "iv_admin_token";
  var K_REPO = "iv_admin_repo";
  var SALT = "zzf-sub-2026"; // 必须与 spider/subs.py 的 TOKEN_SALT 一致

  var DAY = 86400000;

  var state = {
    token: "",
    repo: "",
    sha: "",
    users: {},      // 仓库里的原始数据 {sid: {...}}
    rows: [],       // [{sid, expire, deleted, isNew}]
    filter: "",
    dirty: false,
  };

  var el = {
    login: document.getElementById("loginPanel"),
    dash: document.getElementById("dash"),
    token: document.getElementById("tokenInput"),
    repo: document.getElementById("repoInput"),
    remember: document.getElementById("rememberChk"),
    loginBtn: document.getElementById("loginBtn"),
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

  /** 到期日 -> 当天 23:59:59 的时间戳（与 subs.py 的算法一致） */
  function expTs(dateStr) {
    if (!dateStr) return 0;
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
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
    // 复用前端 auth.js 的纯 JS SHA-256，保证与后端 token_of 一致
    if (window.IVAUTH && window.IVAUTH.tokenOf) return window.IVAUTH.tokenOf(sid);
    if (window.IVAUTH && window.IVAUTH.sha256) return window.IVAUTH.sha256(SALT + "|" + String(sid).trim().toUpperCase()).slice(0, 16);
    return "";
  }

  /* ---------------------------------------------------------- GitHub API */

  function gh(path, opts) {
    opts = opts || {};
    var headers = {
      Authorization: "Bearer " + state.token,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };
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
    if (err.status === 401) return "Token 无效或已过期";
    if (err.status === 403) return "Token 权限不足（需要本仓库 Contents 读写）";
    if (err.status === 404) return "读不到仓库或文件，检查 owner/repo 是否填对";
    if (err.status === 409) return "文件已被其他人改动，请刷新后重试";
    return err.message || "请求失败";
  }

  function loadRemote() {
    var path = "/repos/" + state.repo + "/contents/" + FILE + "?ref=" + BRANCH;
    return gh(path).then(function (d) {
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

  function saveRemote() {
    var out = {};
    var now = Date.now();
    state.rows.forEach(function (r) {
      if (r.deleted) return;
      var sid = String(r.sid || "").trim().toUpperCase();
      if (!sid) return;
      var orig = state.users[sid] || state.users[r.sid] || null;
      var ts = expTs(r.expire);
      // 到期日没改动就原样保留（连 ts 一起），避免无谓的重算
      if (orig && orig.expire === r.expire) {
        out[sid] = orig;
        return;
      }
      var rec = { expire: r.expire };
      // 新用户或改过日期：不带 ts，让 subs.py 按北京时间的当天 23:59:59 重算
      if (orig && orig.created) rec.created = orig.created;
      if (!ts) delete rec.expire;
      out[sid] = rec;
    });

    var content = JSON.stringify(out, null, 1) + "\n";
    var body = {
      message: "admin: 更新订阅用户（" + Object.keys(out).length + " 人）",
      content: b64enc(content),
      branch: BRANCH,
    };
    if (state.sha) body.sha = state.sha;

    var path = "/repos/" + state.repo + "/contents/" + FILE;
    return gh(path, { method: "PUT", body: JSON.stringify(body) }).then(function (d) {
      state.sha = (d && d.content && d.content.sha) || "";
      state.users = out;
      state.dirty = false;
      updateDirty();
      return true;
    });
  }

  /* ---------------------------------------------------------- 数据模型 */

  function buildRows() {
    var now = Date.now();
    state.rows = Object.keys(state.users).map(function (sid) {
      var info = state.users[sid] || {};
      var date = info.expire || "";
      if (!date && info.ts) date = ymd(new Date(Number(info.ts) * 1000));
      return { sid: sid, expire: date, deleted: false, isNew: false };
    });
    state.rows.sort(function (a, b) {
      return expTs(b.expire) - expTs(a.expire);
    });
  }

  function stats() {
    var now = Date.now();
    var total = 0,
      ok = 0,
      exp = 0,
      soon = 0;
    state.rows.forEach(function (r) {
      if (r.deleted) return;
      total++;
      var ts = expTs(r.expire);
      if (!ts) {
        exp++;
        return;
      }
      if (ts > now) {
        ok++;
        if (ts - now <= 7 * DAY) soon++;
      } else exp++;
    });
    return { total: total, ok: ok, exp: exp, soon: soon };
  }

  /* ---------------------------------------------------------- 渲染 */

  function renderStats() {
    var s = stats();
    var items = [
      { n: s.total, t: "总订阅", cls: "" },
      { n: s.ok, t: "有效", cls: "ok" },
      { n: s.soon, t: "7 天内到期", cls: "warn" },
      { n: s.exp, t: "已过期", cls: "err" },
    ];
    el.stats.innerHTML = items
      .map(function (i) {
        return (
          '<div class="admin-stat ' +
          i.cls +
          '"><b>' +
          i.n +
          "</b><span>" +
          i.t +
          "</span></div>"
        );
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

    el.body.innerHTML = list
      .map(function (r, i) {
        var ts = expTs(r.expire);
        var now = Date.now();
        var left = ts ? daysLeft(ts) : 0;
        var status = !ts
          ? '<span class="pill pill-err">日期无效</span>'
          : ts > now
          ? '<span class="pill pill-ok">有效</span>'
          : '<span class="pill pill-err">已过期</span>';
        var sid = String(r.sid);
        return (
          '<tr data-sid="' +
          esc(sid) +
          '" class="' +
          (r.deleted ? "is-deleted" : "") +
          '">' +
          "<td><code class=\"admin-sid\">" +
          esc(r.deleted ? groupSid(sid) + "（将删除）" : groupSid(sid)) +
          "</code></td>" +
          '<td><code class="admin-tok">' +
          esc(tokenOf(sid)) +
          "</code></td>" +
          "<td>" +
          (r.deleted
            ? '<span class="admin-muted">—</span>'
            : '<input type="date" class="admin-date" value="' +
              esc(r.expire) +
              '" data-act="date">') +
          "</td>" +
          "<td>" +
          (r.deleted ? "—" : ts ? left + " 天" : "—") +
          "</td>" +
          "<td>" +
          (r.deleted ? '<span class="pill">待删除</span>' : status) +
          "</td>" +
          '<td class="ta-right admin-acts">' +
          (r.deleted
            ? '<button class="btn btn-sm" data-act="undo" type="button">撤销</button>'
            : '<button class="btn btn-sm" data-act="p30" type="button">+30 天</button>' +
              '<button class="btn btn-sm" data-act="p90" type="button">+90 天</button>' +
              '<button class="btn btn-sm btn-danger" data-act="del" type="button">删除</button>') +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function updateDirty() {
    el.saveBtn.disabled = !state.dirty;
    el.saveHint.textContent = state.dirty
      ? "有未保存的改动"
      : "改动后点右侧「保存并发布」";
  }

  /* ---------------------------------------------------------- 事件 */

  el.loginBtn.addEventListener("click", function () {
    var token = el.token.value.trim();
    var repo = el.repo.value.trim().replace(/^https?:\/\/github\.com\//, "").replace(/\/$/, "");
    if (!token) return toast("请填写 GitHub Token");
    if (!/^[\w.-]+\/[\w.-]+$/.test(repo)) return toast("仓库格式应为 owner/repo");

    state.token = token;
    state.repo = repo;
    el.loginBtn.disabled = true;
    el.loginBtn.textContent = "正在验证…";

    loadRemote()
      .then(function () {
        if (el.remember.checked) {
          localStorage.setItem(K_TOKEN, token);
          localStorage.setItem(K_REPO, repo);
        } else {
          localStorage.removeItem(K_TOKEN);
          localStorage.removeItem(K_REPO);
        }
        showDash();
        toast("登录成功");
      })
      .catch(function (err) {
        toast("登录失败：" + explain(err), 4000);
      })
      .then(function () {
        el.loginBtn.disabled = false;
        el.loginBtn.textContent = "登录后台";
      });
  });

  function showDash() {
    el.login.hidden = true;
    el.dash.hidden = false;
    el.logout.hidden = false;
    render();
  }

  el.logout.addEventListener("click", function () {
    localStorage.removeItem(K_TOKEN);
    localStorage.removeItem(K_REPO);
    state.token = state.repo = state.sha = "";
    state.users = {};
    state.rows = [];
    el.dash.hidden = true;
    el.login.hidden = false;
    el.logout.hidden = true;
    el.token.value = "";
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
    var sid = (window.prompt("新增用户\n请输入用户的 12 位赞助码（可在用户赞助页底部看到）") || "")
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
    if (!sid) return;
    if (sid.length < 6) return toast("赞助码太短");
    if (state.users[sid]) return toast("这个赞助码已经存在");

    var days = window.prompt("有效天数（例如 30 / 90 / 365）", "30");
    if (days == null) return;
    var n = parseInt(days, 10);
    if (!n || n <= 0) return toast("天数不正确");

    state.rows.unshift({
      sid: sid,
      expire: ymd(new Date(Date.now() + n * DAY)),
      deleted: false,
      isNew: true,
    });
    state.dirty = true;
    updateDirty();
    render();
    toast("已添加，别忘了点「保存并发布」");
  });

  el.body.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-act]");
    if (!btn) return;
    var tr = e.target.closest("tr");
    if (!tr) return;
    var sid = tr.getAttribute("data-sid");
    var row = state.rows.filter(function (r) {
      return String(r.sid) === sid;
    })[0];
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
    var sid = tr && tr.getAttribute("data-sid");
    var row = state.rows.filter(function (r) {
      return String(r.sid) === sid;
    })[0];
    if (!row) return;
    row.expire = input.value;
    state.dirty = true;
    updateDirty();
    render();
  });

  el.saveBtn.addEventListener("click", function () {
    el.saveBtn.disabled = true;
    el.saveBtn.textContent = "正在保存…";
    saveRemote()
      .then(function () {
        toast("已提交，约 1 分钟后生效", 3600);
        return loadRemote().then(function () {
          state.dirty = false;
          updateDirty();
        });
      })
      .catch(function (err) {
        if (err.status === 409) {
          // 别人刚提交过，重取 sha 后重试一次
          return loadRemote().then(function () {
            return saveRemote().then(function () {
              state.dirty = false;
              updateDirty();
              toast("已提交（重试成功），约 1 分钟生效", 3600);
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

  /** ?demo=1 只用假数据看界面，不连仓库、不能保存 */
  function demoMode() {
    state.demo = true;
    var t = Date.now();
    state.users = {
      A1B2C3D4E5F6: { expire: ymd(new Date(t + 28 * DAY)) },
      G7H8J9K2L3M4: { expire: ymd(new Date(t + 3 * DAY)) },
      N5P6Q7R8S9T2: { expire: ymd(new Date(t + 180 * DAY)) },
      U3V4W5X6Y7Z8: { expire: "2026-10-20" },
    };
    buildRows();
    showDash();
    el.logout.hidden = true;
    el.saveBtn.disabled = true;
    el.saveHint.textContent = "演示模式：数据是假的，不会提交";
  }

  (function boot() {
    if (/[?&]demo=1/.test(location.search)) {
      demoMode();
      return;
    }
    var t = localStorage.getItem(K_TOKEN) || "";
    // 不在页面上写死仓库名，避免把私有仓库位置暴露给访客
    var r = localStorage.getItem(K_REPO) || "";
    el.repo.value = r;
    if (t) {
      el.token.value = t;
      state.token = t;
      state.repo = r;
      loadRemote()
        .then(function () {
          showDash();
        })
        .catch(function (err) {
          toast("自动登录失败：" + explain(err), 4000);
        });
    }
  })();
})();
