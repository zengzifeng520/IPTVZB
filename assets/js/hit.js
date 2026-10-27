/* 访问统计上报（前端埋点）
   ------------------------------------------------------------
   不依赖账号，用公开计数器服务按 key 累加：
     GET https://abacus.jasoncameron.dev/hit/<命名空间>/<key>   -> {value:N} 自增并返回
   每次打开页面：
     views              总访问量（每次打开 +1）
     d-YYYYMMDD         当天访问量
     visitors           累计独立访客（本机只上报一次）
     duv-YYYYMMDD       当天独立访客（本机每天只上报一次）
   后台管理页（admin.html）不引入本脚本，避免站长自己刷新刷高数据。 */
(function () {
  "use strict";

  var NS = "zzf-tg-2026";
  var API = "https://abacus.jasoncameron.dev/hit/" + NS + "/";

  // 自动化环境（无头浏览器 / 爬虫）不计入
  if (navigator.webdriver) return;

  function ping(key) {
    try {
      fetch(API + key, {
        method: "GET",
        mode: "cors",
        cache: "no-store",
        keepalive: true,
        credentials: "omit",
      }).catch(function () {});
    } catch (e) {
      /* 统计失败不影响页面 */
    }
  }

  // 北京时间日期 YYYYMMDD
  function bjDay() {
    var d = new Date(Date.now() + 8 * 3600 * 1000);
    var m = d.getUTCMonth() + 1;
    var day = d.getUTCDate();
    return (
      d.getUTCFullYear() +
      (m < 10 ? "0" + m : "" + m) +
      (day < 10 ? "0" + day : "" + day)
    );
  }

  var today = bjDay();

  ping("views");
  ping("d-" + today);

  // 独立访客：靠本机标记去重；localStorage 不可用时干脆不记，避免把 PV 当 UV
  try {
    var ls = window.localStorage;
    if (ls.getItem("iv_uv") !== "1") {
      ping("visitors");
      ls.setItem("iv_uv", "1");
    }
    if (ls.getItem("iv_duv") !== today) {
      ping("duv-" + today);
      ls.setItem("iv_duv", today);
    }
  } catch (e) {
    /* 隐私模式：跳过 UV 统计 */
  }
})();
