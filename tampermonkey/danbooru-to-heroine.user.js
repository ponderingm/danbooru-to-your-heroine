// ==UserScript==
// @name         Danbooru to Heroine
// @namespace    https://github.com/danbooru-to-your-heroine
// @version      1.6.0
// @description  Danbooruの投稿ページ・検索結果一覧にヒロイン化画像生成UIを追加する（生成済みバッジ表示・複数投稿の一括キュー投入・生成キューの進捗パネル・ギャラリー(Webビューア)への遷移リンク・APIサーバーURLの接続案内・config.GENERATION_BACKENDSのバックエンド選択・artistタグの自由記述指定つき）
// @author       you
// @match        https://danbooru.donmai.us/posts*
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const DEFAULT_API_BASE = "http://127.0.0.1:8000";
  const JOB_POLL_INTERVAL_MS = 2000;
  const MAX_QUEUE_ENTRIES = 30;

  const getApiBase = () => GM_getValue("d2h_api_base", DEFAULT_API_BASE);
  const setApiBase = (url) => GM_setValue("d2h_api_base", url);
  const getSetting = (key, fallback) => GM_getValue(key, fallback);
  const setSetting = (key, value) => GM_setValue(key, value);
  const getQueue = () => GM_getValue("d2h_job_queue", []);
  const setQueue = (list) => GM_setValue("d2h_job_queue", list);

  let heroines = {};

  function canonicalPostUrl(postId) {
    if (postId) return `https://danbooru.donmai.us/posts/${postId}`;
    // クエリ・フラグメントを除いた /posts/<id> の形にする
    return location.href.split("?")[0].split("#")[0];
  }

  function heroineLabel(key) {
    return (heroines[key] && heroines[key].name) || key;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ─────────────────────────────────────────────
  // スタイル
  // ─────────────────────────────────────────────

  function injectStyle() {
    const style = document.createElement("style");
    style.textContent = `
      #d2h-panel {
        position: fixed;
        bottom: 16px;
        right: 16px;
        z-index: 9999;
        width: 240px;
        background: #1e2028;
        color: #e8e8f0;
        border: 1px solid #33364a;
        border-radius: 10px;
        padding: 12px 14px;
        font-size: 12px;
        font-family: sans-serif;
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      }
      #d2h-panel h3 { margin: 0 0 8px; font-size: 13px; display: flex; justify-content: space-between; align-items: center; }
      #d2h-panel select, #d2h-panel input[type=text] {
        width: 100%; margin-bottom: 6px; padding: 4px; border-radius: 4px;
        border: 1px solid #33364a; background: #101116; color: #e8e8f0; box-sizing: border-box;
      }
      #d2h-panel label.d2h-check { display: flex; align-items: center; gap: 4px; margin-bottom: 6px; }
      #d2h-panel button {
        width: 100%; background: #e879b0; color: #1a1a1a; border: none;
        border-radius: 6px; padding: 6px; font-weight: 600; cursor: pointer; margin-top: 2px;
      }
      #d2h-panel button:disabled { opacity: 0.5; cursor: not-allowed; }
      #d2h-panel .d2h-count { color: #9797ab; margin-bottom: 6px; }
      #d2h-status { margin-top: 6px; min-height: 1.4em; color: #9797ab; word-break: break-word; }
      #d2h-status.ok { color: #7f7; }
      #d2h-status.error { color: #f77; }
      #d2h-generated-badge {
        background: #1f3a24; color: #7f7; border-radius: 6px;
        padding: 4px 8px; font-size: 11px; margin-bottom: 8px; text-align: center;
      }
    `;
    document.head.appendChild(style);
  }

  function injectBadgeStyle() {
    // 一覧・検索結果ページのサムネイルに付与する「生成済み」バッジ。パネルの有無に関係なく常に適用する
    const style = document.createElement("style");
    style.textContent = `
      .d2h-generated { position: relative !important; }
      .d2h-generated::after {
        content: "✅ 生成済み";
        position: absolute; top: 4px; left: 4px; z-index: 50;
        background: rgba(232, 121, 176, 0.92); color: #1a1a1a;
        font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px;
        pointer-events: none;
      }
      .d2h-select-cb {
        position: absolute; top: 4px; right: 4px; z-index: 60;
        width: 18px; height: 18px; cursor: pointer;
      }
    `;
    document.head.appendChild(style);
  }

  function injectSharedStyle() {
    // 接続バー（item③）・生成キューパネル（item⑤）共通スタイル
    const style = document.createElement("style");
    style.textContent = `
      #d2h-conn-bar {
        position: fixed; top: 12px; right: 12px; z-index: 10001;
        font-family: sans-serif; font-size: 12px;
      }
      #d2h-conn-summary {
        background: #1e2028; color: #e8e8f0; border: 1px solid #33364a; border-radius: 16px;
        padding: 4px 12px; cursor: pointer; display: flex; align-items: center; gap: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.4);
      }
      #d2h-conn-dot.ok { color: #7f7; }
      #d2h-conn-dot.error { color: #f77; }
      #d2h-conn-dot.pending { color: #9797ab; }
      #d2h-conn-panel {
        margin-top: 6px; width: 260px; background: #1e2028; color: #e8e8f0;
        border: 1px solid #33364a; border-radius: 10px; padding: 12px 14px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      }
      #d2h-conn-panel.hidden { display: none; }
      #d2h-conn-panel p.d2h-conn-hint { margin: 0 0 8px; color: #9797ab; line-height: 1.5; }
      #d2h-conn-panel input[type=text] {
        width: 100%; margin-bottom: 8px; padding: 4px; border-radius: 4px;
        border: 1px solid #33364a; background: #101116; color: #e8e8f0; box-sizing: border-box;
      }
      #d2h-conn-panel button {
        width: 100%; background: #e879b0; color: #1a1a1a; border: none;
        border-radius: 6px; padding: 6px; font-weight: 600; cursor: pointer;
      }
      #d2h-conn-status { margin: 8px 0 0; min-height: 1.4em; color: #9797ab; word-break: break-word; }
      #d2h-conn-status.ok { color: #7f7; }
      #d2h-conn-status.error { color: #f77; }

      #d2h-queue-panel {
        position: fixed; bottom: 16px; left: 16px; z-index: 9999;
        width: 260px; max-height: 70vh; overflow-y: auto;
        background: #1e2028; color: #e8e8f0; border: 1px solid #33364a; border-radius: 10px;
        padding: 12px 14px; font-size: 12px; font-family: sans-serif;
        box-shadow: 0 4px 16px rgba(0,0,0,0.4);
      }
      #d2h-queue-panel.hidden .d2h-queue-list, #d2h-queue-panel.hidden .d2h-queue-clear, #d2h-queue-panel.hidden .d2h-queue-gallery { display: none; }
      #d2h-queue-panel h3 { margin: 0 0 8px; font-size: 13px; display: flex; justify-content: space-between; align-items: center; cursor: pointer; }
      .d2h-queue-gallery {
        width: 100%; background: #e879b0; color: #1a1a1a; border: none;
        border-radius: 6px; padding: 5px; cursor: pointer; margin-bottom: 6px; font-size: 11px; font-weight: 600;
      }
      .d2h-queue-clear {
        width: 100%; background: transparent; color: #9797ab; border: 1px solid #33364a;
        border-radius: 6px; padding: 4px; cursor: pointer; margin-bottom: 8px; font-size: 11px;
      }
      .d2h-queue-empty { color: #9797ab; }
      .d2h-queue-item { border-top: 1px solid #33364a; padding: 6px 0; }
      .d2h-queue-item:first-child { border-top: none; }
      .d2h-queue-item a { color: #e879b0; }
      .d2h-queue-item img { width: 100%; border-radius: 6px; margin-top: 4px; display: block; }
      .d2h-status-queued, .d2h-status-running { color: #ffcc66; }
      .d2h-status-done { color: #7f7; }
      .d2h-status-error { color: #f77; }
    `;
    document.head.appendChild(style);
  }

  // ─────────────────────────────────────────────
  // 生成済みバッジ（一覧・検索結果ページのサムネイル + 投稿ページのパネル）
  // ─────────────────────────────────────────────

  const CHECKED_CLASS = "d2h-checked";
  const GENERATED_CLASS = "d2h-generated";

  function collectUncheckedPreviews() {
    const els = Array.from(document.querySelectorAll(`article.post-preview[data-id]:not(.${CHECKED_CLASS})`));
    const idMap = new Map();
    for (const el of els) {
      el.classList.add(CHECKED_CLASS);
      const id = parseInt(el.dataset.id, 10);
      if (!Number.isNaN(id)) idMap.set(id, el);
    }
    return idMap;
  }

  async function markGeneratedThumbnails() {
    const idMap = collectUncheckedPreviews();
    if (!idMap.size) return;
    try {
      const res = await fetch(`${getApiBase()}/generated_posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ post_ids: Array.from(idMap.keys()) }),
      });
      if (!res.ok) return;
      const { generated } = await res.json();
      for (const id of generated) {
        const el = idMap.get(id);
        if (el) el.classList.add(GENERATED_CLASS);
      }
    } catch (e) {
      // APIサーバー未接続でも一覧表示自体は妨げない
    }
  }

  function watchForNewThumbnails(onNewBatch) {
    const run = () => {
      markGeneratedThumbnails();
      if (onNewBatch) onNewBatch();
    };
    run();
    let debounceTimer = null;
    const observer = new MutationObserver(() => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(run, 300);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  async function checkCurrentPostGenerated(panel) {
    const match = location.pathname.match(/^\/posts\/(\d+)/);
    if (!match) return;
    const postId = parseInt(match[1], 10);
    try {
      const res = await fetch(`${getApiBase()}/generated_posts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ post_ids: [postId] }),
      });
      if (!res.ok) return;
      const { generated } = await res.json();
      if (generated.includes(postId)) {
        const badge = document.createElement("div");
        badge.id = "d2h-generated-badge";
        badge.textContent = "✅ この投稿はヒロイン化生成済み";
        panel.insertBefore(badge, panel.firstChild);
      }
    } catch (e) {
      // APIサーバー未接続時は何も表示しない
    }
  }

  // ─────────────────────────────────────────────
  // API呼び出しヘルパー
  // ─────────────────────────────────────────────

  async function apiGet(path) {
    const res = await fetch(`${getApiBase()}${path}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  async function apiPost(path, body) {
    const res = await fetch(`${getApiBase()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async function submitGenerate(payload) {
    const { job_id } = await apiPost("/generate", payload);
    return job_id;
  }

  async function loadHeroinesGlobal() {
    try {
      heroines = await apiGet("/heroines");
      const savedHeroine = getSetting("d2h_last_heroine", null);
      const optionsHtml = Object.entries(heroines)
        .map(([key, dna]) => `<option value="${key}">${escapeHtml(dna.name)}</option>`)
        .join("");
      document.querySelectorAll(".d2h-heroine-select").forEach((select) => {
        select.innerHTML = optionsHtml;
        if (savedHeroine && heroines[savedHeroine]) select.value = savedHeroine;
      });
      return true;
    } catch (e) {
      document.querySelectorAll(".d2h-heroine-select").forEach((select) => {
        select.innerHTML = `<option value="">接続失敗（右上の🔌でAPI URLを確認）</option>`;
      });
      return false;
    }
  }

  async function loadBackendsGlobal() {
    try {
      const data = await apiGet("/backends");
      const savedBackend = getSetting("d2h_last_backend", data.default);
      const optionsHtml = data.backends
        .map(({ id, label }) => `<option value="${id}">${escapeHtml(label)}</option>`)
        .join("");
      document.querySelectorAll(".d2h-backend-select").forEach((select) => {
        select.innerHTML = optionsHtml;
        if (savedBackend) select.value = savedBackend;
      });
      return true;
    } catch (e) {
      document.querySelectorAll(".d2h-backend-select").forEach((select) => {
        select.innerHTML = `<option value="">接続失敗</option>`;
      });
      return false;
    }
  }

  // ─────────────────────────────────────────────
  // 接続バー（設定UI改善: item③ API_BASEの初期値案内）
  // ─────────────────────────────────────────────

  function buildConnectionBar() {
    const bar = document.createElement("div");
    bar.id = "d2h-conn-bar";
    bar.innerHTML = `
      <div id="d2h-conn-summary">🔌 <span id="d2h-conn-dot" class="pending">●</span> API</div>
      <div id="d2h-conn-panel" class="hidden">
        <p class="d2h-conn-hint">danbooru-to-your-heroine APIサーバーのURLを入力してください（例: http://127.0.0.1:8899）</p>
        <input type="text" id="d2h-conn-url">
        <button type="button" id="d2h-conn-save">保存して接続確認</button>
        <p id="d2h-conn-status"></p>
      </div>
    `;
    document.body.appendChild(bar);
    return bar;
  }

  async function checkConnection(bar) {
    const dot = bar.querySelector("#d2h-conn-dot");
    const statusEl = bar.querySelector("#d2h-conn-status");
    dot.className = "pending";
    const [heroinesOk, backendsOk] = await Promise.all([loadHeroinesGlobal(), loadBackendsGlobal()]);
    const ok = heroinesOk && backendsOk;
    dot.className = ok ? "ok" : "error";
    setStatus(statusEl, ok ? `接続OK（${getApiBase()}）` : `接続失敗（${getApiBase()}）`, ok ? "ok" : "error");
    return ok;
  }

  function wireConnectionBar(bar) {
    const summary = bar.querySelector("#d2h-conn-summary");
    const panel = bar.querySelector("#d2h-conn-panel");
    const urlInput = bar.querySelector("#d2h-conn-url");
    const saveBtn = bar.querySelector("#d2h-conn-save");

    urlInput.value = getApiBase();

    summary.addEventListener("click", () => {
      panel.classList.toggle("hidden");
    });

    saveBtn.addEventListener("click", async () => {
      const next = urlInput.value.trim().replace(/\/$/, "");
      if (!next) return;
      setApiBase(next);
      saveBtn.disabled = true;
      await checkConnection(bar);
      saveBtn.disabled = false;
    });
  }

  // ─────────────────────────────────────────────
  // 生成キューパネル（item⑤: 生成キュー・進捗のパネル内表示）
  // ─────────────────────────────────────────────

  let queuePollTimer = null;

  function buildQueuePanel() {
    const panel = document.createElement("div");
    panel.id = "d2h-queue-panel";
    panel.innerHTML = `
      <h3>生成キュー</h3>
      <button type="button" class="d2h-queue-gallery">🖼 ギャラリーを開く</button>
      <button type="button" class="d2h-queue-clear">履歴をクリア</button>
      <div class="d2h-queue-list"></div>
    `;
    document.body.appendChild(panel);
    panel.querySelector("h3").addEventListener("click", () => panel.classList.toggle("hidden"));
    panel.querySelector(".d2h-queue-gallery").addEventListener("click", () => {
      window.open(`${getApiBase()}/`, "_blank", "noopener");
    });
    panel.querySelector(".d2h-queue-clear").addEventListener("click", () => {
      setQueue([]);
      renderQueuePanel(panel);
    });
    return panel;
  }

  function renderQueueItemHtml(entry) {
    const statusText = { queued: "待機中…", running: "生成中…", done: "完了", error: "エラー" }[entry.status] || entry.status;
    let resultHtml = "";
    if (entry.status === "done" && entry.result) {
      const imgUrl = entry.result.image_urls && entry.result.image_urls[0];
      if (imgUrl) {
        const fullImgUrl = `${getApiBase()}${imgUrl}`;
        resultHtml = `<a href="${fullImgUrl}" target="_blank" rel="noopener"><img src="${fullImgUrl}"></a>`;
      }
    } else if (entry.status === "error" && entry.error) {
      resultHtml = `<div>${escapeHtml(entry.error)}</div>`;
    }
    return `
      <div class="d2h-queue-item">
        <div>post #${entry.post_id} ・ ${escapeHtml(entry.heroine_label || "")}</div>
        <div class="d2h-status-${entry.status}">${statusText}</div>
        ${resultHtml}
      </div>
    `;
  }

  function renderQueuePanel(panel) {
    const listEl = panel.querySelector(".d2h-queue-list");
    const queue = getQueue();
    listEl.innerHTML = queue.length
      ? queue.map(renderQueueItemHtml).join("")
      : `<div class="d2h-queue-empty">まだ生成キューはありません</div>`;
  }

  function ensureQueuePolling(panel) {
    if (queuePollTimer) return;
    queuePollTimer = setInterval(() => pollQueueOnce(panel), JOB_POLL_INTERVAL_MS);
  }

  async function pollQueueOnce(panel) {
    const queue = getQueue();
    const pending = queue.filter((e) => e.job_id && (e.status === "queued" || e.status === "running"));
    if (!pending.length) {
      clearInterval(queuePollTimer);
      queuePollTimer = null;
      return;
    }
    let changed = false;
    for (const entry of pending) {
      try {
        const job = await apiGet(`/jobs/${entry.job_id}`);
        if (job.status !== entry.status) changed = true;
        entry.status = job.status;
        if (job.status === "done") entry.result = job.result;
        if (job.status === "error") entry.error = job.error;
      } catch (e) {
        // 一時的な取得失敗は無視し、次回のポーリングでリトライする
      }
    }
    if (changed) {
      setQueue(queue);
      renderQueuePanel(panel);
    }
  }

  function addToQueue(panel, entry) {
    const queue = getQueue();
    queue.unshift(entry);
    setQueue(queue.slice(0, MAX_QUEUE_ENTRIES));
    renderQueuePanel(panel);
    ensureQueuePolling(panel);
  }

  function setStatus(el, text, kind) {
    el.textContent = text;
    el.className = kind || "";
  }

  // ─────────────────────────────────────────────
  // 投稿ページ: 単体生成パネル
  // ─────────────────────────────────────────────

  function buildPanel() {
    const panel = document.createElement("div");
    panel.id = "d2h-panel";
    panel.innerHTML = `
      <h3>ヒロイン化生成</h3>
      <select id="d2h-heroine" class="d2h-heroine-select"><option>読込中...</option></select>
      <select id="d2h-backend" class="d2h-backend-select"><option>読込中...</option></select>
      <select id="d2h-artist-mode">
        <option value="none">artist除去(none)</option>
        <option value="keep">元投稿優先(keep)</option>
        <option value="override">ヒロイン固定(override)</option>
      </select>
      <input type="text" id="d2h-custom-artist" placeholder="artist自由記述（任意、上の選択より優先）">
      <button type="button" id="d2h-generate">生成キューに投入</button>
      <div id="d2h-status"></div>
    `;
    document.body.appendChild(panel);
    return panel;
  }

  function wireUp(panel, queuePanel) {
    const heroineSelect = panel.querySelector("#d2h-heroine");
    const backendSelect = panel.querySelector("#d2h-backend");
    const artistModeSelect = panel.querySelector("#d2h-artist-mode");
    const customArtistInput = panel.querySelector("#d2h-custom-artist");
    const generateBtn = panel.querySelector("#d2h-generate");
    const statusEl = panel.querySelector("#d2h-status");

    artistModeSelect.value = getSetting("d2h_last_artist_mode", "none");
    customArtistInput.value = getSetting("d2h_last_custom_artist", "");

    generateBtn.addEventListener("click", async () => {
      generateBtn.disabled = true;
      setSetting("d2h_last_heroine", heroineSelect.value);
      setSetting("d2h_last_backend", backendSelect.value);
      setSetting("d2h_last_artist_mode", artistModeSelect.value);
      setSetting("d2h_last_custom_artist", customArtistInput.value.trim());

      const match = location.pathname.match(/^\/posts\/(\d+)/);
      const postId = match ? parseInt(match[1], 10) : null;

      setStatus(statusEl, "生成をキューに投入中…");
      try {
        const job_id = await submitGenerate({
          url: canonicalPostUrl(),
          heroine: heroineSelect.value,
          backend: backendSelect.value,
          artist_mode: artistModeSelect.value,
          custom_artist: customArtistInput.value.trim() || undefined,
        });
        addToQueue(queuePanel, {
          job_id, post_id: postId, heroine_label: heroineLabel(heroineSelect.value), status: "queued",
        });
        setStatus(statusEl, "キューに投入した。進捗は左下の生成キューで確認できる", "ok");
      } catch (e) {
        setStatus(statusEl, `エラー: ${e.message}`, "error");
      } finally {
        generateBtn.disabled = false;
      }
    });
  }

  // ─────────────────────────────────────────────
  // 検索結果一覧ページ: 一括生成パネル（item④）
  // ─────────────────────────────────────────────

  function buildBatchPanel() {
    const panel = document.createElement("div");
    panel.id = "d2h-panel";
    panel.innerHTML = `
      <h3>一括ヒロイン化生成</h3>
      <select id="d2h-heroine" class="d2h-heroine-select"><option>読込中...</option></select>
      <select id="d2h-backend" class="d2h-backend-select"><option>読込中...</option></select>
      <select id="d2h-artist-mode">
        <option value="none">artist除去(none)</option>
        <option value="keep">元投稿優先(keep)</option>
        <option value="override">ヒロイン固定(override)</option>
      </select>
      <input type="text" id="d2h-custom-artist" placeholder="artist自由記述（任意、上の選択より優先）">
      <div class="d2h-count" id="d2h-selected-count">選択中: 0件（サムネイル右上のチェックボックスで選択）</div>
      <button type="button" id="d2h-batch-submit" disabled>選択した投稿をキューに投入</button>
      <div id="d2h-status"></div>
    `;
    document.body.appendChild(panel);
    return panel;
  }

  function updateSelectedCount(panel) {
    const count = document.querySelectorAll(".d2h-select-cb:checked").length;
    panel.querySelector("#d2h-selected-count").textContent = `選択中: ${count}件（サムネイル右上のチェックボックスで選択）`;
    panel.querySelector("#d2h-batch-submit").disabled = count === 0;
  }

  function injectSelectCheckboxes(panel) {
    const els = document.querySelectorAll(`article.post-preview[data-id]:not(.d2h-select-ready)`);
    for (const el of els) {
      el.classList.add("d2h-select-ready");
      if (getComputedStyle(el).position === "static") el.style.position = "relative";
      const id = parseInt(el.dataset.id, 10);
      if (Number.isNaN(id)) continue;
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "d2h-select-cb";
      cb.dataset.postId = String(id);
      cb.addEventListener("click", (e) => e.stopPropagation());
      cb.addEventListener("change", () => updateSelectedCount(panel));
      el.appendChild(cb);
    }
  }

  function wireBatchPanel(panel, queuePanel) {
    const heroineSelect = panel.querySelector("#d2h-heroine");
    const backendSelect = panel.querySelector("#d2h-backend");
    const artistModeSelect = panel.querySelector("#d2h-artist-mode");
    const customArtistInput = panel.querySelector("#d2h-custom-artist");
    const submitBtn = panel.querySelector("#d2h-batch-submit");
    const statusEl = panel.querySelector("#d2h-status");

    artistModeSelect.value = getSetting("d2h_last_artist_mode", "none");
    customArtistInput.value = getSetting("d2h_last_custom_artist", "");

    submitBtn.addEventListener("click", async () => {
      const checkboxes = Array.from(document.querySelectorAll(".d2h-select-cb:checked"));
      if (!checkboxes.length) return;
      submitBtn.disabled = true;
      setSetting("d2h_last_heroine", heroineSelect.value);
      setSetting("d2h_last_backend", backendSelect.value);
      setSetting("d2h_last_artist_mode", artistModeSelect.value);
      setSetting("d2h_last_custom_artist", customArtistInput.value.trim());

      setStatus(statusEl, `${checkboxes.length}件をキューに投入中…`);
      let okCount = 0;
      for (const cb of checkboxes) {
        const postId = parseInt(cb.dataset.postId, 10);
        try {
          const job_id = await submitGenerate({
            url: canonicalPostUrl(postId),
            heroine: heroineSelect.value,
            backend: backendSelect.value,
            artist_mode: artistModeSelect.value,
            custom_artist: customArtistInput.value.trim() || undefined,
          });
          addToQueue(queuePanel, {
            job_id, post_id: postId, heroine_label: heroineLabel(heroineSelect.value), status: "queued",
          });
          cb.checked = false;
          okCount += 1;
        } catch (e) {
          addToQueue(queuePanel, {
            job_id: null, post_id: postId, heroine_label: heroineLabel(heroineSelect.value),
            status: "error", error: e.message,
          });
        }
      }
      updateSelectedCount(panel);
      setStatus(statusEl, `${okCount}/${checkboxes.length}件をキューに投入した。進捗は左下の生成キューで確認できる`, "ok");
      submitBtn.disabled = false;
    });
  }

  // ─────────────────────────────────────────────
  // 初期化
  // ─────────────────────────────────────────────

  injectBadgeStyle();
  injectSharedStyle();

  const isFirstRun = getSetting("d2h_api_base", null) === null;

  const connBar = buildConnectionBar();
  wireConnectionBar(connBar);

  const queuePanel = buildQueuePanel();
  renderQueuePanel(queuePanel);
  if (getQueue().some((e) => e.status === "queued" || e.status === "running")) {
    ensureQueuePolling(queuePanel);
  }

  const isPostPage = /^\/posts\/\d+/.test(location.pathname);
  let batchPanel = null;

  if (isPostPage) {
    injectStyle();
    const panel = buildPanel();
    wireUp(panel, queuePanel);
    checkCurrentPostGenerated(panel);
  } else {
    injectStyle();
    batchPanel = buildBatchPanel();
    wireBatchPanel(batchPanel, queuePanel);
  }

  watchForNewThumbnails(() => {
    if (batchPanel) injectSelectCheckboxes(batchPanel);
  });

  checkConnection(connBar).then((ok) => {
    if (isFirstRun || !ok) {
      connBar.querySelector("#d2h-conn-panel").classList.remove("hidden");
    }
  });
})();

