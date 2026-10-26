/* ============================================================
   赞助解锁（无注册、无登录）
   ------------------------------------------------------------
   - 首次访问自动生成本机赞助码（sid），存在 localStorage
   - 频道地址全部免费浏览；订阅地址赞助后解锁
   - 赞助记录在本机，到期后订阅地址自动停止更新
   - 换设备 / 清缓存：用页面上显示的赞助码恢复即可
   ============================================================ */
(function () {
  "use strict";

  var K_SID = "iv_sid_v1";
  var K_SPONSOR = "iv_sponsor_v1";
  // 已提交但还没被服务端确认的开通申请
  var K_PENDING = "iv_pending_v1";
  // 免费版可选的那一个地区，选定后不再更改
  var K_FREE_REGION = "iv_free_region_v1";
  // 免费订阅的到期时间（选地区那天 + FREE_DAYS 天）
  var K_FREE_EXPIRE = "iv_free_expire_v1";
  var FREE_DAYS = 7;

  // 赞助档位
  var PLANS = [
    { key: "day", name: "体验版", price: 2, days: 1, unit: "天", tag: "先试一天" },
    { key: "month", name: "月付", price: 8, days: 30, unit: "天", tag: "最灵活" },
    { key: "quarter", name: "季付", price: 20, days: 90, unit: "天", tag: "更划算" },
    { key: "year", name: "年付", price: 80, days: 365, unit: "天", tag: "最超值", hot: true },
  ];

  var DEFAULT_PLAN = "month";

  function planByKey(key) {
    for (var i = 0; i < PLANS.length; i++) {
      if (PLANS[i].key === key) return PLANS[i];
    }
    return null;
  }

  /* ---------------------------------------------------------- 工具 */

  function toBytes(str) {
    try {
      return unescape(encodeURIComponent(str));
    } catch (e) {
      return str;
    }
  }

  // 纯 JS SHA-256（不依赖 crypto.subtle，http 环境也能用）
  function sha256(input) {
    var ascii = toBytes(String(input));

    function rr(v, a) {
      return (v >>> a) | (v << (32 - a));
    }

    var maxWord = Math.pow(2, 32);
    var words = [];
    var asciiBitLength = ascii.length * 8;
    var hash = sha256.h || [];
    var k = sha256.k || [];
    var primeCounter = k.length;
    var isComposite = {};
    var i,
      j,
      candidate = 2;

    if (!hash.length) {
      for (; primeCounter < 64; candidate++) {
        if (!isComposite[candidate]) {
          for (i = 0; i < 313; i += candidate) isComposite[i] = candidate;
          hash[primeCounter] = (Math.pow(candidate, 0.5) * maxWord) | 0;
          k[primeCounter++] = (Math.pow(candidate, 1 / 3) * maxWord) | 0;
        }
      }
      sha256.h = hash.slice(0, 8);
      sha256.k = k;
    }
    hash = hash.slice(0, 8);

    ascii += "\x80";
    while (ascii.length % 64 - 56) ascii += "\x00";

    for (i = 0; i < ascii.length; i++) {
      j = ascii.charCodeAt(i);
      if (j >> 8) j = 63;
      words[i >> 2] |= j << (((3 - i) % 4) * 8);
    }
    words[words.length] = (asciiBitLength / maxWord) | 0;
    words[words.length] = asciiBitLength;

    for (j = 0; j < words.length; ) {
      var w = words.slice(j, (j += 16));
      var oldHash = hash.slice(0, 8);

      for (i = 0; i < 64; i++) {
        var w15 = w[i - 15];
        var w2 = w[i - 2];
        var a = hash[0];
        var e = hash[4];
        var temp1 =
          hash[7] +
          (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) +
          ((e & hash[5]) ^ (~e & hash[6])) +
          k[i] +
          (w[i] =
            i < 16
              ? w[i] | 0
              : (w[i - 16] +
                  (rr(w15, 7) ^ rr(w15, 18) ^ (w15 >>> 3)) +
                  w[i - 7] +
                  (rr(w2, 17) ^ rr(w2, 19) ^ (w2 >>> 10))) |
                0);
        var temp2 =
          (rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) +
          ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
        hash = [(temp1 + temp2) | 0].concat(hash);
        hash[4] = (hash[4] + temp1) | 0;
      }
      for (i = 0; i < 8; i++) hash[i] = (hash[i] + oldHash[i]) | 0;
    }

    var out = "";
    for (i = 0; i < 8; i++) {
      for (j = 3; j + 1; j--) {
        var b = (hash[i] >> (j * 8)) & 255;
        out += (b < 16 ? "0" : "") + b.toString(16);
      }
    }
    return out;
  }

  // 订阅 token 盐值：必须与 spider/subs.py 的 TOKEN_SALT 完全一致
  var TOKEN_SALT = "zzf-sub-2026";

  /**
   * 赞助码 -> 16 位订阅 token。
   * 与后端 sha256(TOKEN_SALT + "|" + 赞助码)[:16] 同一算法，
   * 服务端只要知道赞助码就能推出订阅目录，前端也能自己拼出地址。
   */
  function tokenOf(id) {
    return sha256(TOKEN_SALT + "|" + String(id || "").trim().toUpperCase()).slice(0, 16);
  }

  /**
   * 开通登记接口（可选）。
   * 填了就会在赞助后自动把赞助码写进服务端，订阅文件 1 分钟内自动生成；
   * 留空则只能本机解锁，需要站长凭赞助码手工补录。
   * 例：https://你的worker.workers.dev/claim
   */
  var CLAIM_URL = "";

  function readJSON(key, fallback) {
    try {
      var raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function writeJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      return false;
    }
  }

  /* ---------------------------------------------------------- 赞助码 */

  // 去掉容易看错的 0/O/1/I，方便用户抄写
  var ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";

  function newSid() {
    var out = "";
    if (window.crypto && window.crypto.getRandomValues) {
      var buf = new Uint8Array(12);
      window.crypto.getRandomValues(buf);
      for (var i = 0; i < 12; i++) out += ALPHABET[buf[i] % ALPHABET.length];
    } else {
      for (var j = 0; j < 12; j++) out += ALPHABET[Math.floor(Math.random() * ALPHABET.length)];
    }
    return out;
  }

  function normSid(v) {
    return String(v || "")
      .toUpperCase()
      .replace(/[^A-Z0-9]/g, "");
  }

  /** 读本机赞助码，没有就生成一个 */
  function sid() {
    var cur = "";
    try {
      cur = localStorage.getItem(K_SID) || "";
    } catch (e) {}
    cur = normSid(cur);
    if (cur.length >= 8) return cur;

    var made = newSid();
    try {
      localStorage.setItem(K_SID, made);
    } catch (e) {}
    return made;
  }

  /** 用另一台设备的赞助码恢复（会覆盖本机记录） */
  function setSid(code) {
    var v = normSid(code);
    if (v.length < 8 || v.length > 32) return { ok: false, msg: "赞助码格式不对" };
    try {
      localStorage.setItem(K_SID, v);
    } catch (e) {
      return { ok: false, msg: "浏览器存储不可用" };
    }
    return { ok: true, sid: v };
  }

  /** 四位一组，方便抄写 */
  function groupSid(v) {
    var s = normSid(v);
    var out = [];
    for (var i = 0; i < s.length; i += 4) out.push(s.slice(i, i + 4));
    return out.join(" ");
  }

  /* ---------------------------------------------------------- 赞助状态 */

  function record() {
    return readJSON(K_SPONSOR, null);
  }

  function clearSponsor() {
    try {
      localStorage.removeItem(K_SPONSOR);
    } catch (e) {}
  }

  /**
   * 点「我已完成付款」。
   *
   * 重要：这里**不会**给本机开通会员。
   * 个人收款码没有到账回调，前端点一下就当付款成功等于人人可白拿，
   * 所以只登记一条「待开通」申请，真正的会员状态必须等服务端
   * data/users/<token>/meta.json 出现（站长补录或登记接口写入）才算。
   *
   * 配置了 CLAIM_URL 时，会顺手把申请提交给登记接口，之后自动轮询等它生效。
   */
  function unlock(planKey, orderNo) {
    var plan = planByKey(planKey) || planByKey(DEFAULT_PLAN);
    var mySid = sid();

    var rec = {
      sid: mySid,
      order: orderNo || "",
      ts: Date.now(),
      plan: plan.key,
      planName: plan.name,
      price: plan.price,
    };
    if (!writeJSON(K_PENDING, rec)) {
      return { ok: false, msg: "浏览器存储不可用，请关闭无痕模式后重试" };
    }

    claimRemote(mySid, plan.key);
    return { ok: true, pending: true, plan: plan, sid: mySid, order: rec.order };
  }

  /** 待开通申请（没有则返回 null） */
  function pending() {
    var p = readJSON(K_PENDING, null);
    if (!p || !p.sid) return null;
    return p;
  }

  function clearPending() {
    try {
      localStorage.removeItem(K_PENDING);
    } catch (e) {}
  }

  /** 把赞助码登记到服务端（配置了 CLAIM_URL 才生效），失败不影响本地解锁 */
  function claimRemote(mySid, planKey) {
    if (!CLAIM_URL || typeof fetch !== "function") return;
    try {
      fetch(CLAIM_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sid: mySid, plan: planKey }),
      })
        .then(function (res) {
          return res.ok ? res.json() : null;
        })
        .then(function (d) {
          if (!d || !d.ok || !d.ts) return;
          // 服务端已写入到期时间 → 这才算真正开通
          var rec = record() || {};
          rec.sid = mySid;
          rec.exp = Number(d.ts) * 1000;
          rec.ts = rec.ts || Date.now();
          writeJSON(K_SPONSOR, rec);
          clearPending();
        })
        .catch(function () {});
    } catch (e) {}
  }

  /**
   * 从服务端拉取本机赞助码的状态，修正本地记录。
   * 换设备 / 清缓存 / 站长手工补录后，靠这个自动恢复。
   * 数据源：data/users/<token>/meta.json（每日任务生成）
   */
  function syncSponsor() {
    if (typeof fetch !== "function") return Promise.resolve(false);
    var mySid = sid();
    // 纯数字（旧的手机号键）不走这条路
    if (!mySid) return Promise.resolve(false);

    // 带时间戳绕过 Pages 的 CDN 缓存：否则刚开通/刚撤销都可能读到旧状态
    var metaUrl =
      "data/users/" + tokenOf(mySid) + "/meta.json?_=" + Date.now();
    return fetch(metaUrl, { cache: "no-store" })
      .then(function (res) {
        // 服务端明确回 404：这个赞助码从来没被开通 → 不能继续当会员
        if (res.status === 404) return { _missing: true };
        // 其它错误（断网、临时故障）不动本地状态，避免误伤已开通用户
        if (!res.ok) return null;
        return res.json().catch(function () {
          return null;
        });
      })
      .then(function (meta) {
        if (meta && meta._missing) {
          if (record()) {
            try {
              localStorage.removeItem(K_SPONSOR);
            } catch (e) {}
            return true;
          }
          return false;
        }
        if (!meta || !meta.ts) return false;
        var expMs = Number(meta.ts) * 1000;
        if (!expMs) return false;

        var prev = record() || {};
        if (prev.exp === expMs && prev.sid === mySid) return false;

        writeJSON(K_SPONSOR, {
          sid: mySid,
          exp: expMs,
          order: prev.order || "",
          ts: prev.ts || Date.now(),
          plan: prev.plan || "",
          planName: prev.planName || "",
          price: prev.price || 0,
        });
        clearPending();
        return true;
      })
      .catch(function () {
        return false;
      });
  }

  /**
   * 申请提交后轮询服务端，直到 meta.json 出现（即站长已补录 / 接口已写入）。
   * tries 次，每次间隔 gapMs。返回是否开通成功。
   */
  function waitForActivation(tries, gapMs) {
    var left = tries || 0;
    var gap = gapMs || 15000;
    if (left <= 0) return Promise.resolve(false);
    if (activeMember()) return Promise.resolve(true);
    return syncSponsor().then(function () {
      if (activeMember()) {
        clearPending();
        return true;
      }
      return new Promise(function (res) {
        setTimeout(res, gap);
      }).then(function () {
        return waitForActivation(left - 1, gap);
      });
    });
  }

  function activeMember() {
    var r = record();
    return !!(r && r.exp > Date.now());
  }

  /** 是否已配置自动登记接口（没配就得靠站长手工补录） */
  function remoteEnabled() {
    return !!CLAIM_URL;
  }

  /* ---------------------------------------------------------- 免费地区 */

  /** 当前已选定的免费地区（没选过返回空串） */
  function freeRegion() {
    try {
      return localStorage.getItem(K_FREE_REGION) || "";
    } catch (e) {
      return "";
    }
  }

  /** 免费订阅的到期时间戳（毫秒），没选过返回 0 */
  function freeExpire() {
    try {
      return Number(localStorage.getItem(K_FREE_EXPIRE) || 0);
    } catch (e) {
      return 0;
    }
  }

  /** 免费订阅是否仍在有效期内 */
  function freeValid() {
    var exp = freeExpire();
    return exp > Date.now();
  }

  /** 到期日 -> YYYYMMDD，用于拼免费订阅目录（与 subs.py 的目录名一致） */
  function freeDir() {
    var exp = freeExpire();
    if (!exp) return "";
    var d = new Date(exp);
    function p(n) {
      return n < 10 ? "0" + n : "" + n;
    }
    return d.getFullYear() + p(d.getMonth() + 1) + p(d.getDate());
  }

  /**
   * 选定免费地区。每个设备只能选一次，选定后不可更改；
   * 同时记下 FREE_DAYS 天后的到期时间，到期后免费订阅自动失效。
   */
  function setFreeRegion(key) {
    var cur = freeRegion();
    if (cur) return { ok: false, msg: "免费地区已选定，赞助后可随时切换", key: cur };
    try {
      localStorage.setItem(K_FREE_REGION, String(key));
      localStorage.setItem(K_FREE_EXPIRE, String(Date.now() + FREE_DAYS * 86400000));
    } catch (e) {
      return { ok: false, msg: "浏览器存储不可用" };
    }
    return { ok: true, key: String(key), expire: freeExpire() };
  }

  /* ---------------------------------------------------------- 视图 */

  function fmtDate(ts) {
    if (!ts) return "";
    var d = new Date(ts);
    function p(n) {
      return n < 10 ? "0" + n : "" + n;
    }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }

  /** 生成订单号，方便付款时写备注、也方便日后核对 */
  function makeOrderNo(seed) {
    var d = new Date();
    function p(n) {
      return n < 10 ? "0" + n : "" + n;
    }
    var tail = normSid(seed).slice(-4) || "0000";
    var stamp =
      d.getFullYear() +
      p(d.getMonth() + 1) +
      p(d.getDate()) +
      p(d.getHours()) +
      p(d.getMinutes());
    return "ZB" + stamp + tail;
  }

  function user() {
    var mySid = sid();
    var rec = record();
    var now = Date.now();
    var mem = rec && rec.exp > now ? rec : null;
    var expired = !mem && !!rec && !!rec.exp && rec.exp <= now;
    var left = mem ? Math.max(0, Math.ceil((mem.exp - now) / 86400000)) : 0;

    return {
      sid: mySid,
      sidText: groupSid(mySid),
      phone: "",
      phoneMask: mem ? "本机赞助" : "未赞助",
      region: "",
      member: !!mem,
      expired: expired,
      exp: mem ? mem.exp : 0,
      expText: mem ? fmtDate(mem.exp) : "",
      lastExp: rec && rec.exp ? rec.exp : 0,
      lastExpText: rec && rec.exp ? fmtDate(rec.exp) : "",
      lastPlanName: rec && rec.planName ? rec.planName : "",
      order: mem ? mem.order : "",
      plan: mem ? rec.plan || "" : "",
      planName: mem ? rec.planName || "赞助用户" : "",
      price: mem ? rec.price || 0 : 0,
      daysLeft: left,
    };
  }

  window.IVAUTH = {
    PLANS: PLANS,
    DEFAULT_PLAN: DEFAULT_PLAN,
    planByKey: planByKey,
    sha256: sha256,
    tokenOf: tokenOf,
    sid: sid,
    sidText: function () {
      return groupSid(sid());
    },
    setSid: setSid,
    groupSid: groupSid,
    unlock: unlock,
    pending: pending,
    clearPending: clearPending,
    waitForActivation: waitForActivation,
    remoteEnabled: remoteEnabled,
    clearSponsor: clearSponsor,
    freeRegion: freeRegion,
    setFreeRegion: setFreeRegion,
    freeExpire: freeExpire,
    freeValid: freeValid,
    freeDir: freeDir,
    FREE_DAYS: FREE_DAYS,
    user: user,
    syncSponsor: syncSponsor,
    makeOrderNo: makeOrderNo,
    fmtDate: fmtDate,
    isMember: function () {
      var u = user();
      return !!(u && u.member);
    },
  };
})();
