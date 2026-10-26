/* ============================================================
   账号与套餐状态（纯本地，无后端）
   ------------------------------------------------------------
   - 注册：手机号 + 密码，注册时锁定 1 个地区
   - 体验版：只能查看锁定的那个地区
   - 会员：扫码付款后自行解锁，查看全部地区
   说明：纯静态站没有服务端，账号数据存在本机浏览器，
        换设备需要重新注册并用同一手机号重新解锁。
   ============================================================ */
(function () {
  "use strict";

  var K_USERS = "iv_users_v1";
  var K_SESSION = "iv_session_v1";
  var K_MEMBER = "iv_member_v1";
  var K_REMEMBER = "iv_remember_v1";

  var PRICE = 15;
  var MEMBER_DAYS = 365;

  /* ---------------------------------------------------------- 工具 */

  // UTF-8 化，让中文密码也能被哈希
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
      if (j >> 8) j = 63; // 非法字节兜底，避免脏数据
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

  var SALT = "iv-salt-2026";

  function passwordHash(phone, pwd) {
    return sha256(SALT + "|" + phone + "|" + pwd);
  }

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

  /* ---------------------------------------------------------- 校验 */

  function normPhone(v) {
    return String(v || "").replace(/[\s-]/g, "");
  }

  function validPhone(v) {
    return /^1[3-9]\d{9}$/.test(normPhone(v));
  }

  function validPwd(v) {
    return typeof v === "string" && v.length >= 6 && v.length <= 32;
  }

  /* ---------------------------------------------------------- 账号 */

  function users() {
    return readJSON(K_USERS, {});
  }

  function currentPhone() {
    try {
      return localStorage.getItem(K_SESSION) || "";
    } catch (e) {
      return "";
    }
  }

  function register(phone, pwd, regionKey) {
    phone = normPhone(phone);
    if (!validPhone(phone)) return { ok: false, msg: "请输入正确的 11 位手机号" };
    if (!validPwd(pwd)) return { ok: false, msg: "密码长度需为 6~32 位" };
    if (!regionKey) return { ok: false, msg: "请选择一个地区" };

    var db = users();
    if (db[phone]) return { ok: false, msg: "该手机号已注册，请直接登录" };

    db[phone] = {
      p: passwordHash(phone, pwd),
      r: String(regionKey),
      t: Date.now(),
    };
    if (!writeJSON(K_USERS, db)) return { ok: false, msg: "浏览器存储不可用，请关闭无痕模式后重试" };

    try {
      localStorage.setItem(K_SESSION, phone);
    } catch (e) {}
    return { ok: true, phone: phone };
  }

  function login(phone, pwd) {
    phone = normPhone(phone);
    if (!validPhone(phone)) return { ok: false, msg: "请输入正确的 11 位手机号" };
    var db = users();
    var rec = db[phone];
    if (!rec) return { ok: false, msg: "该手机号尚未注册" };
    if (rec.p !== passwordHash(phone, pwd)) return { ok: false, msg: "密码错误" };
    try {
      localStorage.setItem(K_SESSION, phone);
    } catch (e) {}
    return { ok: true, phone: phone };
  }

  function logout() {
    try {
      localStorage.removeItem(K_SESSION);
    } catch (e) {}
  }

  /* ---------------------------------------------------------- 套餐 */

  function members() {
    return readJSON(K_MEMBER, {});
  }

  function memberOf(phone) {
    if (!phone) return null;
    var rec = members()[phone];
    if (!rec || !rec.exp) return null;
    return rec.exp > Date.now() ? rec : null;
  }

  /**
   * 扫码后解锁全部地区。
   * 不校验付款人（个人收款码无到账回调），用户点「我已完成付款」即开通。
   */
  function unlock(orderNo) {
    var phone = currentPhone();
    if (!phone) return { ok: false, msg: "请先登录" };
    if (!users()[phone]) return { ok: false, msg: "账号不存在，请重新登录" };

    var db = members();
    var now = Date.now();
    var prev = db[phone] && db[phone].exp > now ? db[phone].exp : now;
    var exp = prev + MEMBER_DAYS * 86400000;

    db[phone] = {
      exp: exp,
      order: orderNo || "",
      ts: now,
      price: PRICE,
    };
    if (!writeJSON(K_MEMBER, db)) return { ok: false, msg: "浏览器存储不可用，请关闭无痕模式" };
    return { ok: true, exp: exp };
  }

  function renewCancel() {
    // 预留：如需退款/取消可在此处理
  }

  /* ---------------------------------------------------------- 会话快照 */

  function user() {
    var phone = currentPhone();
    if (!phone) return null;
    var rec = users()[phone];
    if (!rec) return null;
    var mem = memberOf(phone);
    return {
      phone: phone,
      phoneMask: phone.slice(0, 3) + "****" + phone.slice(-4),
      region: rec.r,
      created: rec.t,
      member: !!mem,
      exp: mem ? mem.exp : 0,
      expText: mem ? fmtDate(mem.exp) : "",
      order: mem ? mem.order : "",
    };
  }

  function fmtDate(ts) {
    var d = new Date(ts);
    function p(n) {
      return n < 10 ? "0" + n : "" + n;
    }
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }

  /** 生成订单号，方便用户付款时写备注、也方便日后对账 */
  function makeOrderNo(phone) {
    var d = new Date();
    function p(n) {
      return n < 10 ? "0" + n : "" + n;
    }
    var tail = String(phone || "").slice(-4) || "0000";
    var stamp =
      d.getFullYear() +
      p(d.getMonth() + 1) +
      p(d.getDate()) +
      p(d.getHours()) +
      p(d.getMinutes());
    return "ZB" + stamp + tail;
  }

  /* ---------------------------------------------------------- 记住账号 */

  function obscure(str) {
    // 轻量可逆混淆：只是避免明文直接暴露在 DevTools 里，不是加密
    var s = toBytes(str);
    var out = "";
    for (var i = 0; i < s.length; i++) {
      out += String.fromCharCode(s.charCodeAt(i) ^ (0x5a + (i % 7)));
    }
    try {
      return btoa(out);
    } catch (e) {
      return "";
    }
  }

  function deobscure(str) {
    try {
      var raw = atob(str);
      var out = "";
      for (var i = 0; i < raw.length; i++) {
        out += String.fromCharCode(raw.charCodeAt(i) ^ (0x5a + (i % 7)));
      }
      return decodeURIComponent(escape(out));
    } catch (e) {
      return "";
    }
  }

  /**
   * 记住登录信息。
   * @param {string} phone 手机号
   * @param {string} pwd   密码；传空字符串则只记住手机号
   */
  function saveRemember(phone, pwd) {
    try {
      if (!phone) {
        localStorage.removeItem(K_REMEMBER);
        return;
      }
      var payload = { phone: phone, p: pwd ? obscure(pwd) : "" };
      localStorage.setItem(K_REMEMBER, JSON.stringify(payload));
    } catch (e) {}
  }

  function remembered() {
    var rec = readJSON(K_REMEMBER, null);
    if (!rec || !rec.phone) return null;
    return { phone: rec.phone, pwd: rec.p ? deobscure(rec.p) : "" };
  }

  function forgetRemember() {
    try {
      localStorage.removeItem(K_REMEMBER);
    } catch (e) {}
  }

  window.IVAUTH = {
    PRICE: PRICE,
    MEMBER_DAYS: MEMBER_DAYS,
    sha256: sha256,
    validPhone: validPhone,
    register: register,
    login: login,
    logout: logout,
    unlock: unlock,
    user: user,
    makeOrderNo: makeOrderNo,
    fmtDate: fmtDate,
    saveRemember: saveRemember,
    remembered: remembered,
    forgetRemember: forgetRemember,
    isLoggedIn: function () {
      return !!user();
    },
    isMember: function () {
      var u = user();
      return !!(u && u.member);
    },
  };
})();
