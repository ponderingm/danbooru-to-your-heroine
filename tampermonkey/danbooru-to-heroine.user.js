// ==UserScript==
// @name         Danbooru to Heroine
// @namespace    https://github.com/danbooru-to-your-heroine
// @version      1.2.0
// @description  Danbooruの投稿ページにヒロイン化画像生成ボタンを追加し、一覧・検索結果に生成済みバッジを表示する（danbooru-to-your-heroine APIサーバー呼び出し）
// @author       you
// @match        https://danbooru.donmai.us/posts*
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const DEFAULT_API_BASE = "http://127.0.0.1:8000";

  const getApiBase = () => GM_getValue("d2h_api_base", DEFAULT_API_BASE);
  const setApiBase = (url) => GM_setValue("d2h_api_base", url);
  const getSetting = (key, fallback) => GM_getValue(key, fallback);
  const setSetting = (key, value) => GM_setValue(key, value);

  function canonicalPostUrl() {
    // クエリ・フラグメントを除いた /posts/<id> の形にする
    return location.href.split("?")[0].split("#")[0];
  }

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
      #d2h-panel button.d2h-gear { width: auto; background: transparent; color: #9797ab; padding: 0 4px; }
      #d2h-status { margin-top: 6px; min-height: 1.4em; color: #9797ab; word-break: break-word; }
      #d2h-status.ok { color: #7f7; }
      #d2h-status.error { color: #f77; }
      #d2h-result { margin-top: 6px; }
      #d2h-result img { width: 100%; border-radius: 6px; display: block; }
      #d2h-result a { color: #e879b0; }
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
    `;
    document.head.appendChild(style);
  }

  function buildPanel() {
    const panel = document.createElement("div");
    panel.id = "d2h-panel";
    panel.innerHTML = `
      <h3>ヒロイン化生成 <button type="button" class="d2h-gear" title="APIサーバーURLを設定">⚙️</button></h3>
      <select id="d2h-heroine"><option>読込中...</option></select>
      <select id="d2h-model">
        <option value="illustrious">illustrious</option>
        <option value="anima">anima</option>
        <option value="animagine">animagine</option>
      </select>
      <select id="d2h-artist-mode">
        <option value="none">artist除去(none)</option>
        <option value="keep">元投稿優先(keep)</option>
        <option value="override">ヒロイン固定(override)</option>
      </select>
      <label class="d2h-check"><input type="checkbox" id="d2h-nsfw" checked> NSFW</label>
      <label class="d2h-check"><input type="checkbox" id="d2h-custom"> custom生成</label>
      <button type="button" id="d2h-generate">生成する</button>
      <div id="d2h-status"></div>
      <div id="d2h-result"></div>
    `;
    document.body.appendChild(panel);
    return panel;
  }

  function setStatus(el, text, kind) {
    el.textContent = text;
    el.className = kind || "";
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

  function watchForNewThumbnails() {
    markGeneratedThumbnails();
    let debounceTimer = null;
    const observer = new MutationObserver(() => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(markGeneratedThumbnails, 300);
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

  async function loadHeroines(select) {
    try {
      const res = await fetch(`${getApiBase()}/heroines`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const heroines = await res.json();
      const savedHeroine = getSetting("d2h_last_heroine", null);
      select.innerHTML = Object.entries(heroines)
        .map(([key, dna]) => `<option value="${key}">${dna.name}</option>`)
        .join("");
      if (savedHeroine && heroines[savedHeroine]) select.value = savedHeroine;
    } catch (e) {
      select.innerHTML = `<option value="">接続失敗（⚙️でAPI URLを確認）</option>`;
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  const JOB_POLL_INTERVAL_MS = 1500;

  async function generateAndWait(payload) {
    const res = await fetch(`${getApiBase()}/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const { job_id } = await res.json();

    while (true) {
      await sleep(JOB_POLL_INTERVAL_MS);
      const jobRes = await fetch(`${getApiBase()}/jobs/${job_id}`);
      if (!jobRes.ok) {
        const err = await jobRes.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${jobRes.status}`);
      }
      const job = await jobRes.json();
      if (job.status === "done") return job.result;
      if (job.status === "error") throw new Error(job.error || "生成に失敗した");
    }
  }

  function wireUp(panel) {
    const heroineSelect = panel.querySelector("#d2h-heroine");
    const modelSelect = panel.querySelector("#d2h-model");
    const artistModeSelect = panel.querySelector("#d2h-artist-mode");
    const nsfwCheckbox = panel.querySelector("#d2h-nsfw");
    const customCheckbox = panel.querySelector("#d2h-custom");
    const generateBtn = panel.querySelector("#d2h-generate");
    const gearBtn = panel.querySelector(".d2h-gear");
    const statusEl = panel.querySelector("#d2h-status");
    const resultEl = panel.querySelector("#d2h-result");

    modelSelect.value = getSetting("d2h_last_model", "illustrious");
    artistModeSelect.value = getSetting("d2h_last_artist_mode", "none");
    nsfwCheckbox.checked = getSetting("d2h_last_nsfw", true);
    customCheckbox.checked = getSetting("d2h_last_custom", false);

    loadHeroines(heroineSelect);
    checkCurrentPostGenerated(panel);

    gearBtn.addEventListener("click", () => {
      const current = getApiBase();
      const next = prompt("danbooru-to-your-heroine APIサーバーのURLを入力", current);
      if (next) {
        setApiBase(next.replace(/\/$/, ""));
        loadHeroines(heroineSelect);
      }
    });

    generateBtn.addEventListener("click", async () => {
      generateBtn.disabled = true;
      resultEl.innerHTML = "";
      setSetting("d2h_last_heroine", heroineSelect.value);
      setSetting("d2h_last_model", modelSelect.value);
      setSetting("d2h_last_artist_mode", artistModeSelect.value);
      setSetting("d2h_last_nsfw", nsfwCheckbox.checked);
      setSetting("d2h_last_custom", customCheckbox.checked);

      setStatus(statusEl, "生成をキューに投入中…");
      try {
        setStatus(statusEl, "生成中…（ComfyUIの処理が終わるまで待ちます）");
        const entry = await generateAndWait({
          url: canonicalPostUrl(),
          heroine: heroineSelect.value,
          model: modelSelect.value,
          artist_mode: artistModeSelect.value,
          nsfw: nsfwCheckbox.checked,
          use_custom: customCheckbox.checked,
        });
        setStatus(statusEl, `完了（${entry.duration_sec}秒）`, "ok");
        const imgUrl = entry.image_urls && entry.image_urls[0];
        if (imgUrl) {
          const fullImgUrl = `${getApiBase()}${imgUrl}`;
          resultEl.innerHTML = `
            <a href="${fullImgUrl}" target="_blank" rel="noopener"><img src="${fullImgUrl}"></a>
            <a href="${getApiBase()}/" target="_blank" rel="noopener">ビューアで見る →</a>
          `;
        }
      } catch (e) {
        setStatus(statusEl, `エラー: ${e.message}`, "error");
      } finally {
        generateBtn.disabled = false;
      }
    });
  }

  injectBadgeStyle();
  watchForNewThumbnails();

  if (/^\/posts\/\d+/.test(location.pathname)) {
    injectStyle();
    const panel = buildPanel();
    wireUp(panel);
  }
})();
