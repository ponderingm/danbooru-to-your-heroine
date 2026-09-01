// ==UserScript==
// @name         Danbooru to Heroine
// @namespace    https://github.com/danbooru-to-your-heroine
// @version      1.0.0
// @description  Danbooruの投稿ページにヒロイン化画像生成ボタンを追加する（danbooru-to-your-heroine APIサーバー呼び出し）
// @author       you
// @match        https://danbooru.donmai.us/posts/*
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

  function wireUp(panel) {
    const heroineSelect = panel.querySelector("#d2h-heroine");
    const modelSelect = panel.querySelector("#d2h-model");
    const nsfwCheckbox = panel.querySelector("#d2h-nsfw");
    const customCheckbox = panel.querySelector("#d2h-custom");
    const generateBtn = panel.querySelector("#d2h-generate");
    const gearBtn = panel.querySelector(".d2h-gear");
    const statusEl = panel.querySelector("#d2h-status");
    const resultEl = panel.querySelector("#d2h-result");

    modelSelect.value = getSetting("d2h_last_model", "illustrious");
    nsfwCheckbox.checked = getSetting("d2h_last_nsfw", true);
    customCheckbox.checked = getSetting("d2h_last_custom", false);

    loadHeroines(heroineSelect);

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
      setSetting("d2h_last_nsfw", nsfwCheckbox.checked);
      setSetting("d2h_last_custom", customCheckbox.checked);

      setStatus(statusEl, "生成中…（ComfyUIの処理が終わるまで待ちます）");
      try {
        const res = await fetch(`${getApiBase()}/generate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: canonicalPostUrl(),
            heroine: heroineSelect.value,
            model: modelSelect.value,
            nsfw: nsfwCheckbox.checked,
            use_custom: customCheckbox.checked,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const entry = await res.json();
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

  injectStyle();
  const panel = buildPanel();
  wireUp(panel);
})();
