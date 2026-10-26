/* ============================================================
   光影直播 — 播放页逻辑
   ============================================================ */
(function () {
  "use strict";

  const state = {
    data: null,
    ch: null,
    idx: 0,
    hls: null,
    retry: 0,
    tried: new Set(),
  };

  const el = {
    video: document.getElementById("video"),
    overlay: document.getElementById("overlay"),
    spinner: document.getElementById("spinner"),
    poTitle: document.getElementById("poTitle"),
    poDesc: document.getElementById("poDesc"),
    poActions: document.getElementById("poActions"),
    title: document.getElementById("title"),
    meta: document.getElementById("meta"),
    srcList: document.getElementById("srcList"),
    srcHint: document.getElementById("srcHint"),
    related: document.getElementById("related"),
    relHint: document.getElementById("relHint"),
    pbTitle: document.getElementById("pbTitle"),
    shell: document.getElementById("shell"),
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

  /* ---------------------------------------------------------- 覆盖层 */
  function showLoading(text, desc) {
    el.overlay.classList.remove("hidden");
    el.spinner.style.display = "block";
    el.poTitle.textContent = text || "正在连接线路";
    el.poDesc.textContent = desc || "首次播放需要缓冲几秒，请稍候";
    el.poActions.innerHTML = "";
  }

  function showError(title, desc, actions) {
    el.overlay.classList.remove("hidden");
    el.spinner.style.display = "none";
    el.poTitle.textContent = title;
    el.poDesc.textContent = desc || "";
    el.poActions.innerHTML = (actions || [])
      .map(
        (a, i) =>
          `<button class="btn${i === 0 ? " btn-primary" : ""}" data-act="${a.act}">${esc(a.label)}</button>`
      )
      .join("");
  }

  function hideOverlay() {
    el.overlay.classList.add("hidden");
  }

  /* ---------------------------------------------------------- 播放 */
  function currentStream() {
    return state.ch.streams[state.idx];
  }

  function destroyHls() {
    if (state.hls) {
      try {
        state.hls.destroy();
      } catch (e) {}
      state.hls = null;
    }
    el.video.removeAttribute("src");
    el.video.load();
  }

  function playIndex(i, autoplay) {
    const streams = state.ch.streams;
    if (i < 0 || i >= streams.length) return;
    state.idx = i;
    state.retry = 0;
    state.tried.add(i);
    const s = streams[i];

    renderSrcList();
    el.pbTitle.textContent = `线路 ${i + 1} · ${s.q} · ${speedText(s.speed)}`;
    showLoading(`正在连接线路 ${i + 1}`, `${s.q} · ${speedText(s.speed)} · ${s.host || "未知主机"}`);

    destroyHls();
    const url = s.url;

    if (window.Hls && window.Hls.isSupported()) {
      const hls = new window.Hls({
        enableWorker: true,
        lowLatencyMode: false,
        backBufferLength: 30,
        maxBufferLength: 20,
        manifestLoadingTimeOut: 9000,
        manifestLoadingMaxRetry: 1,
        levelLoadingTimeOut: 9000,
        fragLoadingTimeOut: 16000,
      });
      state.hls = hls;
      hls.loadSource(url);
      hls.attachMedia(el.video);

      hls.on(window.Hls.Events.MANIFEST_PARSED, () => {
        state.retry = 0;
        if (autoplay) {
          el.video.play().catch(() => {
            showError("需要手动播放", "浏览器阻止了自动播放，点击下方按钮开始", [
              { act: "play", label: "开始播放" },
            ]);
          });
        }
      });
      hls.on(window.Hls.Events.FRAG_BUFFERED, () => hideOverlay());
      hls.on(window.Hls.Events.ERROR, (_e, data) => {
        if (!data.fatal) return;
        const detail = data.details || "";
        if (detail.includes("manifestLoadError") || detail.includes("manifestParsingError")) {
          onStreamFail("线路无法访问", "可能是源站已下线，或限制跨域访问");
        } else if (detail.includes("levelLoadError") || detail.includes("fragLoadError")) {
          state.retry++;
          if (state.retry >= 2) onStreamFail("拉流失败", "源站响应异常，建议切换线路");
        } else if (detail.includes("bufferStalledError")) {
          onStreamFail("缓冲卡住", "网络到源站不稳定");
        } else {
          onStreamFail("播放出错", detail || data.type);
        }
      });
    } else if (el.video.canPlayType("application/vnd.apple.mpegurl")) {
      el.video.src = url;
      el.video.addEventListener("loadedmetadata", () => {
        hideOverlay();
        if (autoplay) el.video.play().catch(() => {});
      }, { once: true });
      el.video.addEventListener("error", () => onStreamFail("线路无法访问", "浏览器原生播放失败"), { once: true });
    } else {
      showError("浏览器不支持 HLS", "请改用 Chrome / Edge / Safari，或复制地址到本地播放器", [
        { act: "copy", label: "复制播放地址" },
      ]);
    }
  }

  function onStreamFail(title, desc) {
    const hasNext = state.idx + 1 < state.ch.streams.length;
    showError(title, `${desc}（当前线路 ${state.idx + 1}/${state.ch.streams.length}）`, [
      hasNext ? { act: "next", label: "切换下一条线路" } : { act: "retry", label: "重新连接" },
      { act: "copy", label: "复制地址" },
      { act: "back", label: "返回列表" },
    ]);
  }

  el.poActions.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "play") {
      el.video.play().then(hideOverlay).catch(() => toast("播放失败，请换线路"));
    } else if (act === "next") {
      playIndex(state.idx + 1, true);
    } else if (act === "retry") {
      playIndex(state.idx, true);
    } else if (act === "copy") {
      copyText(currentStream().url);
    } else if (act === "back") {
      location.href = "index.html";
    }
  });

  function copyText(text) {
    const done = () => toast("已复制播放地址");
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done).catch(() => fallback());
    } else {
      fallback();
    }
    function fallback() {
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
        toast("复制失败，请手动选择");
      }
      document.body.removeChild(ta);
    }
  }

  /* ---------------------------------------------------------- 渲染 */
  function renderSrcList() {
    const streams = state.ch.streams;
    el.srcHint.textContent = `${streams.length} 条线路`;
    el.srcList.innerHTML = streams
      .map((s, i) => {
        const active = i === state.idx ? " active" : "";
        return `<button class="src-item${active}" data-i="${i}">
          <span class="src-idx">${i + 1}</span>
          <span class="src-body">
            <span class="src-name">${s.q} · ${speedText(s.speed)}</span>
            <span class="src-sub">
              <span>${s.w && s.h ? s.w + "×" + s.h : "分辨率未知"}</span>
              <span>${s.fps ? s.fps + "fps" : ""}</span>
              <span class="${s.cors ? "ok" : "warn"}">${s.cors ? "网页可播" : "仅外部播放器"}</span>
            </span>
          </span>
        </button>`;
      })
      .join("");
  }

  el.srcList.addEventListener("click", (e) => {
    const btn = e.target.closest(".src-item");
    if (!btn) return;
    playIndex(Number(btn.dataset.i), true);
  });

  function renderRelated() {
    const type = state.ch.type;
    const pool = state.data.channels.filter((c) => c.type === type && c.key !== state.ch.key);
    el.relHint.textContent = type;
    const picks = pool.slice(0, 8);
    el.related.innerHTML = picks
      .map(
        (c) => `<a class="rel-item" href="watch.html?c=${encodeURIComponent(c.key)}">
          <div class="rel-logo" style="--h:${hashHue(c.key)}">${logoHTML(c)}</div>
        </a>`
      )
      .join("");
  }

  function renderHead() {
    const ch = state.ch;
    document.title = `${ch.display} 直播 · ${state.data.site?.name || "光影直播"}`;
    el.title.textContent = ch.display + " 直播";
    const best = ch.best;
    el.meta.innerHTML = [
      `<span class="tag tag-q ${qualityClass(best.q)}">${best.q}</span>`,
      `<span>${best.w && best.h ? best.w + "×" + best.h : "分辨率未知"}</span>`,
      `<span>${best.fps ? best.fps + "fps" : ""}</span>`,
      `<span>${ch.streams.length} 条线路</span>`,
      `<span>${esc(ch.type || "")}</span>`,
    ].join(" · ");
  }

  /* ---------------------------------------------------------- 交互 */
  document.getElementById("btnFull").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else el.shell.requestFullscreen().catch(() => toast("全屏失败"));
  });
  document.getElementById("btnPip").addEventListener("click", async () => {
    try {
      if (document.pictureInPictureElement) await document.exitPictureInPicture();
      else await el.video.requestPictureInPicture();
    } catch (e) {
      toast("当前浏览器不支持画中画");
    }
  });

  document.addEventListener("keydown", (e) => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    if (e.code === "Space") {
      e.preventDefault();
      el.video.paused ? el.video.play().catch(() => {}) : el.video.pause();
    } else if (e.key === "f" || e.key === "F") {
      el.shell.requestFullscreen().catch(() => {});
    } else if (e.key === "m" || e.key === "M") {
      el.video.muted = !el.video.muted;
      toast(el.video.muted ? "已静音" : "已取消静音");
    }
  });

  el.video.addEventListener("click", () => {
    if (el.video.muted) {
      el.video.muted = false;
      toast("已取消静音");
    }
  });

  // 顶部搜索
  el.q.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const v = el.q.value.trim();
      location.href = v ? `index.html?q=${encodeURIComponent(v)}` : "index.html";
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
      showError("数据加载失败", "请确认 data/channels.json 存在");
      return;
    }

    if (state.data.site?.name) {
      document.getElementById("brandName").textContent = state.data.site.name;
    }

    const ch = state.data.channels.find((c) => c.key === key);
    if (!ch) {
      el.title.textContent = "频道不存在";
      showError("没有找到这个频道", "可能已被下架或链接有误", [{ act: "back", label: "返回频道列表" }]);
      return;
    }
    state.ch = ch;
    if (!ch.streams.length) {
      showError("该频道暂无可用线路", "源站可能已全部失效", [{ act: "back", label: "返回频道列表" }]);
      return;
    }

    renderHead();
    renderRelated();
    renderSrcList();

    // 优先生效：找第一条标记网页可播的线路
    let start = ch.streams.findIndex((s) => s.cors);
    if (start < 0) start = 0;
    playIndex(start, true);
  }

  boot();
})();
