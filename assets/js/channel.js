/* ============================================================
   光影直播 — 频道详情页（线路列表，无内嵌播放）
   ============================================================ */
(function () {
  "use strict";

  const state = { data: null, ch: null };

  const el = {
    title: document.getElementById("title"),
    meta: document.getElementById("meta"),
    chLogo: document.getElementById("chLogo"),
    lineList: document.getElementById("lineList"),
    lineHint: document.getElementById("lineHint"),
    related: document.getElementById("related"),
    relHint: document.getElementById("relHint"),
    toast: document.getElementById("toast"),
    q: document.getElementById("q"),
  };

  const $ = (s) => document.querySelector(s);

  /* ---------------------------------------------------------- 工具 */
  function toast(msg) {
    el.toast.textContent = msg;
    el.toast.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.toast.classList.remove("show"), 2200);
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function hashHue(str) {
    let h = 0;
    for (let i = 0; i < str.length; i++) h = (h * 131 + str.charCodeAt(i)) >>> 0;
    return h % 360;
  }
  function qualityClass(q) {
    if (q === "8K") return "is8k";
    if (q === "4K") return "is4k";
    if (q === "1080P") return "is1080";
    if (q === "720P") return "is720";
    return "";
  }
  function speedText(k) {
    if (!k) return "—";
    if (k > 1024) return (k / 1024).toFixed(1) + " MB/s";
    return k + " KB/s";
  }
  function logoHTML(ch) {
    const key = ch.key || "";
    let m = key.match(/^CCTV(\d+)(\+?)$/);
    if (m) return `<span class="ch-logo-text is-cctv"><i>CCTV</i><b>${m[1]}${m[2]}</b></span>`;
    m = key.match(/^CCTV(4|8)K$/);
    if (m) return `<span class="ch-logo-text is-cctv"><i>CCTV</i><b>${m[1]}K</b></span>`;
    if (/^CCTV/.test(key)) return `<span class="ch-logo-text is-long">${esc(key)}</span>`;
    if (/^CGTN/.test(key)) {
      const tail = key.slice(4);
      if (!tail) return `<span class="ch-logo-text">CGTN</span>`;
      return `<span class="ch-logo-text is-cctv"><i>CGTN</i><b>${esc(tail)}</b></span>`;
    }
    let t = key.replace(/(卫视|频道|电视台|台)$/g, "");
    if (t.length > 6) t = t.slice(0, 6);
    return `<span class="ch-logo-text">${esc(t || key)}</span>`;
  }

  function copyText(text, okMsg) {
    const done = () => toast(okMsg || "已复制");
    const fallback = () => {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
        done();
      } catch (e) {
        toast("复制失败，请手动选择文本");
      }
      document.body.removeChild(ta);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(fallback);
    } else {
      fallback();
    }
  }

  /* ---------------------------------------------------------- 渲染 */
  function renderHead() {
    const ch = state.ch;
    document.title = `${ch.display} 线路 · ${state.data.site?.name || "光影直播"}`;
    el.title.textContent = ch.display;
    el.chLogo.style.setProperty("--h", hashHue(ch.key));
    el.chLogo.innerHTML = logoHTML(ch);

    const best = ch.best;
    el.meta.innerHTML = [
      `<span class="tag tag-q ${qualityClass(best.q)}">${best.q}</span>`,
      `<span>${best.w && best.h ? best.w + "×" + best.h : "分辨率未知"}</span>`,
      `<span>${best.fps ? best.fps + "fps" : ""}</span>`,
      `<span>${ch.streams.length} 条线路</span>`,
      `<span>${esc(ch.type || "")}</span>`,
    ].join(" · ");
  }

  function renderLines() {
    const streams = state.ch.streams;
    el.lineHint.textContent = `${streams.length} 条`;
    el.lineList.innerHTML = streams
      .map((s, i) => {
        const res = s.w && s.h ? `${s.w}×${s.h}` : "分辨率未知";
        return `<div class="line-item">
          <span class="line-idx">${i + 1}</span>
          <div class="line-body">
            <div class="line-title">
              <span class="tag tag-q ${qualityClass(s.q)}">${s.q}</span>
              <span style="color:var(--text-3);font-weight:400;font-size:11.5px">${res}${s.fps ? " · " + s.fps + "fps" : ""}</span>
              <span class="line-badge">${speedText(s.speed)}</span>
            </div>
            <code class="line-url" title="${esc(s.url)}">${esc(s.url)}</code>
          </div>
          <button class="line-copy" data-url="${esc(s.url)}" data-i="${i}">复制</button>
        </div>`;
      })
      .join("");
  }

  function renderRelated() {
    const type = state.ch.type;
    const pool = state.data.channels.filter((c) => c.type === type && c.key !== state.ch.key);
    el.relHint.textContent = type;
    el.related.innerHTML = pool
      .slice(0, 10)
      .map(
        (c) => `<a class="rel-item" href="channel.html?c=${encodeURIComponent(c.key)}">
          <div class="rel-logo" style="--h:${hashHue(c.key)}">${logoHTML(c)}</div>
        </a>`
      )
      .join("");
  }

  /* ---------------------------------------------------------- 交互 */
  el.lineList.addEventListener("click", (e) => {
    const btn = e.target.closest(".line-copy");
    if (!btn) return;
    copyText(btn.dataset.url, "线路地址已复制");
  });

  document.getElementById("copyAll").addEventListener("click", () => {
    const all = state.ch.streams.map((s) => s.url).join("\n");
    copyText(all, `已复制 ${state.ch.streams.length} 条线路`);
  });

  el.q.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const v = el.q.value.trim();
      location.href = v ? `index.html?q=${encodeURIComponent(v)}` : "index.html";
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== el.q) {
      e.preventDefault();
      el.q.focus();
    }
  });

  /* ---------------------------------------------------------- 启动 */
  async function boot() {
    const key = new URLSearchParams(location.search).get("c");
    try {
      const res = await fetch("data/channels.json", { cache: "no-cache" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      state.data = await res.json();
    } catch (err) {
      el.title.textContent = "数据加载失败";
      el.lineList.innerHTML = `<div class="empty"><h3>无法读取频道数据</h3><p>请稍后重试</p></div>`;
      return;
    }

    if (state.data.site?.name) {
      document.getElementById("brandName").textContent = state.data.site.name;
    }

    const ch = state.data.channels.find((c) => c.key === key);
    if (!ch) {
      el.title.textContent = "频道不存在";
      el.lineList.innerHTML = `<div class="empty">
        <h3>没有找到这个频道</h3>
        <p>链接可能有误，或该频道已无可用线路</p>
        <p style="margin-top:14px"><a class="btn" href="index.html">返回频道列表</a></p>
      </div>`;
      return;
    }

    state.ch = ch;
    renderHead();
    renderLines();
    renderRelated();
  }

  boot();
})();
