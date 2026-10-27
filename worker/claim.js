/**
 * 开通登记接口（Cloudflare Worker）
 * ------------------------------------------------------------
 * 作用：用户在前端点「我已完成付款」时调用一次，把本机赞助码和到期时间
 *      写进 ZZF 仓库的 data/users.json；随后 GitHub Actions 会自动
 *      重建该用户的专属订阅文件（约 1 分钟）。
 *
 * 可以单独部署成一个 Worker，也可以把 claim() 这段逻辑合并到你已有的
 * 网关 Worker 里（在 fetch 开头加一个 if 判断 /claim 即可）。
 *
 * 需要配置的环境变量（Cloudflare → Worker → 设置 → 变量和机密）：
 *   GH_TOKEN  必填  GitHub 细粒度 PAT，只需勾选 ZZF 仓库的 Contents: Read and write
 *   GH_REPO   必填  <你的 GitHub 用户名>/<仓库名>（故意不写默认值，避免源码泄露账号）
 *   ALLOW_ORIGIN 选填 默认 https://zzf.new.tg
 *
 * 接口：
 *   POST /claim   {"sid":"A1B2C3D4E5F6","plan":"month"}
 *   → {"ok":true,"expire":"2026-11-25","ts":1795622399,"token":"3e3b5edd0955acf4"}
 */

const PLANS = { day: 1, month: 30, quarter: 90, year: 365 };
const TOKEN_SALT = "zzf-sub-2026";

const enc = new TextEncoder();

function b64encode(str) {
  const bytes = enc.encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function b64decode(b64) {
  const bin = atob(String(b64 || "").replace(/\s/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

async function tokenOf(sid) {
  // 与前端 auth.js、spider/subs.py 完全一致：sha256("zzf-sub-2026|赞助码") 前 16 位
  const key = TOKEN_SALT + "|" + String(sid || "").trim().toUpperCase();
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(key));
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16);
}

/** 北京时间 YYYY-MM-DD */
function ymdCST(ms) {
  const d = new Date(ms + 8 * 3600 * 1000);
  return d.toISOString().slice(0, 10);
}

function cors(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOW_ORIGIN || "https://zzf.new.tg",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
}

function json(data, status, env) {
  return new Response(JSON.stringify(data), {
    status: status || 200,
    headers: { "Content-Type": "application/json; charset=utf-8", ...cors(env) },
  });
}

async function gh(env, method, path, body) {
  const repo = env.GH_REPO;
  if (!repo) return json({ ok: false, error: "GH_REPO 未配置" }, 500, env);
  const res = await fetch(`https://api.github.com/repos/${repo}${path}`, {
    method,
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "zzf-claim/1.0",
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch (e) { data = null; }
  return { ok: res.ok, status: res.status, data };
}

async function claim(request, env) {
  const body = await request.json().catch(() => null);
  const sid = String((body && body.sid) || "")
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, "");
  const plan = String((body && body.plan) || "month");

  if (!/^[A-Z0-9]{8,32}$/.test(sid)) return json({ ok: false, msg: "赞助码格式不正确" }, 400, env);
  if (!PLANS[plan]) return json({ ok: false, msg: "套餐不存在" }, 400, env);
  if (!env.GH_TOKEN) return json({ ok: false, msg: "服务端未配置 GH_TOKEN" }, 500, env);

  const FILE = "data/users.json";
  const cur = await gh(env, "GET", `/contents/${FILE}?ref=main`);
  if (cur.status !== 200 && cur.status !== 404) {
    return json({ ok: false, msg: "读取用户表失败：" + cur.status }, 502, env);
  }

  let users = {};
  let sha = "";
  if (cur.status === 200 && cur.data && cur.data.content) {
    sha = cur.data.sha;
    try { users = JSON.parse(b64decode(cur.data.content)) || {}; } catch (e) { users = {}; }
  }

  // 未到期就在原有效期上顺延，已过期则从此刻起算
  const nowMs = Date.now();
  const prevMs = users[sid] && users[sid].ts ? Number(users[sid].ts) * 1000 : 0;
  const baseMs = prevMs > nowMs ? prevMs : nowMs;
  const expMs = baseMs + PLANS[plan] * 86400000;

  users[sid] = {
    expire: ymdCST(expMs),
    ts: String(Math.floor(expMs / 1000)),
    created: (users[sid] && users[sid].created) || ymdCST(nowMs),
  };

  const content = b64encode(JSON.stringify(users, null, 2) + "\n");
  const put = await gh(env, "PUT", `/contents/${FILE}`, {
    message: `user: 赞助 ${sid.slice(0, 4)}**** (${plan})`,
    content,
    sha: sha || undefined,
    branch: "main",
  });

  if (!put.ok) {
    const msg = (put.data && put.data.message) || String(put.status);
    return json({ ok: false, msg: "写入用户表失败：" + msg }, 502, env);
  }

  return json(
    {
      ok: true,
      expire: users[sid].expire,
      ts: Number(users[sid].ts),
      token: await tokenOf(sid),
    },
    200,
    env
  );
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/claim") {
      if (request.method === "OPTIONS") return new Response(null, { headers: cors(env) });
      if (request.method !== "POST") return json({ ok: false, msg: "Method Not Allowed" }, 405, env);
      return claim(request, env);
    }

    return new Response("Not Found", { status: 404 });
  },
};
