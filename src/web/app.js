const API_BASE = ""; // 同一オリジン配信なので空文字（相対パス）でOK
const GALLERY_PAGE_SIZE = 30;
const JOB_POLL_INTERVAL_MS = 1500;

// anima記法のrating語(safe/sensitive/nsfw/explicit) → Illustrious記法(rating:xxx)への
// エイリアス。model_adapter.pyのRATING_TAG_ALIASESと同じ対応関係（サーバ側にも別途実装あり）
const RATING_TAG_ALIASES = {
  safe: "rating:general",
  sensitive: "rating:sensitive",
  nsfw: "rating:questionable",
  explicit: "rating:explicit",
};

const heroineSelect = document.getElementById("f-heroine");
const backendSelect = document.getElementById("f-backend");
const artistModeSelect = document.getElementById("f-artist-mode");
const customArtistInput = document.getElementById("f-custom-artist");
const urlInput = document.getElementById("f-url");
const form = document.getElementById("form");
const submitBtn = document.getElementById("f-submit");
const formStatus = document.getElementById("form-status");
const promptTextarea = document.getElementById("f-prompt");
const previewBtn = document.getElementById("f-preview-btn");
const comfyStatusEl = document.getElementById("comfy-status");
const gallery = document.getElementById("gallery");
const galleryCount = document.getElementById("gallery-count");
const reloadBtn = document.getElementById("reload-btn");
const loadMoreBtn = document.getElementById("load-more-btn");
const filterHeroineSelect = document.getElementById("filter-heroine");
const filterModelSelect = document.getElementById("filter-model");
const filterDateFrom = document.getElementById("filter-date-from");
const filterDateTo = document.getElementById("filter-date-to");
const filterTagSelect = document.getElementById("filter-tag-select");
const filterTagChips = document.getElementById("filter-tag-chips");
const filterApplyBtn = document.getElementById("filter-apply-btn");
const filterResetBtn = document.getElementById("filter-reset-btn");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxClose = document.getElementById("lightbox-close");

const batchForm = document.getElementById("batch-form");
const batchSearchInput = document.getElementById("b-search");
const batchHeroineSelect = document.getElementById("b-heroine");
const batchBackendSelect = document.getElementById("b-backend");
const batchArtistModeSelect = document.getElementById("b-artist-mode");
const batchCustomArtistInput = document.getElementById("b-custom-artist");
const batchSortSelect = document.getElementById("b-sort");
const batchLuckyCheckbox = document.getElementById("b-lucky");
const batchStartBtn = document.getElementById("b-start-btn");
const batchStopBtn = document.getElementById("b-stop-btn");
const batchStatusEl = document.getElementById("batch-status");

let heroines = {};
let galleryOffset = 0;
let galleryTotal = 0;
const selectedTags = new Set();

function openLightbox(src) {
  lightboxImg.src = src;
  lightbox.classList.remove("hidden");
}

function closeLightbox() {
  lightbox.classList.add("hidden");
  lightboxImg.src = "";
}

lightbox.addEventListener("click", closeLightbox);
lightboxClose.addEventListener("click", (e) => { e.stopPropagation(); closeLightbox(); });
lightboxImg.addEventListener("click", (e) => e.stopPropagation());
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeLightbox();
});

function setStatus(el, message, kind) {
  el.textContent = message;
  el.className = "status" + (kind ? " " + kind : "");
}

async function loadHeroines() {
  const res = await fetch(`${API_BASE}/heroines`);
  heroines = await res.json();
  heroineSelect.innerHTML = Object.entries(heroines)
    .map(([key, dna]) => `<option value="${key}">${dna.name}</option>`)
    .join("");
  filterHeroineSelect.innerHTML = `<option value="">すべて</option>` + Object.entries(heroines)
    .map(([key, dna]) => `<option value="${key}">${dna.name}</option>`)
    .join("");
  batchHeroineSelect.innerHTML = Object.entries(heroines)
    .map(([key, dna]) => `<option value="${key}">${dna.name}</option>`)
    .join("");
}

function heroineLabel(key) {
  return heroines[key] ? heroines[key].name : key;
}

async function loadBackends() {
  const res = await fetch(`${API_BASE}/backends`);
  const data = await res.json();
  const options = data.backends
    .map(({ id, label }) => `<option value="${id}">${escapeHtml(label)}</option>`)
    .join("");
  backendSelect.innerHTML = options;
  batchBackendSelect.innerHTML = options;
  if (data.default) {
    backendSelect.value = data.default;
    batchBackendSelect.value = data.default;
  }
  backendLabels = Object.fromEntries(data.backends.map(({ id, label }) => [id, label]));
}

const COMFY_STATUS_POLL_MS = 20000;
let backendLabels = {};

async function loadComfyStatus() {
  try {
    const res = await fetch(`${API_BASE}/comfy/status`);
    const data = await res.json();
    comfyStatusEl.innerHTML = Object.entries(data)
      .map(([bid, st]) => `<span class="comfy-dot ${st}">\u25cf ${escapeHtml(backendLabels[bid] || bid)}</span>`)
      .join("");
  } catch (err) {
    comfyStatusEl.innerHTML = `<span class="comfy-dot offline">ComfyUIステータス取得失敗</span>`;
  }
}

async function loadTags() {
  const res = await fetch(`${API_BASE}/tags`);
  const data = await res.json();
  const addable = data.tags.filter(({ tag }) => !selectedTags.has(tag));
  filterTagSelect.innerHTML = `<option value="">タグを選択して追加</option>` + addable
    .map(({ tag, count }) => `<option value="${escapeHtml(tag)}">${escapeHtml(tag)} (${count})</option>`)
    .join("");
}

function renderTagChips() {
  filterTagChips.innerHTML = [...selectedTags].map((tag) => `
    <span class="tag-chip" data-tag="${escapeHtml(tag)}">
      ${escapeHtml(tag)}
      <button type="button" aria-label="削除">×</button>
    </span>
  `).join("");
  filterTagChips.querySelectorAll(".tag-chip button").forEach((btn) => {
    btn.addEventListener("click", () => {
      const tag = btn.parentElement.dataset.tag;
      selectedTags.delete(tag);
      renderTagChips();
      resetGallery();
    });
  });
}

async function addFilterTag(tag) {
  if (!tag || selectedTags.has(tag)) return;
  selectedTags.add(tag);
  renderTagChips();
  await resetGallery();
}

filterTagSelect.addEventListener("change", () => {
  const tag = filterTagSelect.value;
  filterTagSelect.value = "";
  if (tag) addFilterTag(tag);
});

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function callGenerate(payload, statusEl) {
  setStatus(statusEl, "生成をキューに投入中…");
  const res = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  const { job_id } = await res.json();

  setStatus(statusEl, "生成中…（ComfyUIの処理が終わるまで待ちます）");
  while (true) {
    await sleep(JOB_POLL_INTERVAL_MS);
    const jobRes = await fetch(`${API_BASE}/jobs/${job_id}`);
    if (!jobRes.ok) {
      const err = await jobRes.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${jobRes.status}`);
    }
    const job = await jobRes.json();
    if (job.status === "done") return job.result;
    if (job.status === "error") throw new Error(job.error || "生成に失敗した");
    // queued / running のときはポーリングを続ける
  }
}

previewBtn.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    setStatus(formStatus, "投稿URLを入力してください", "error");
    return;
  }
  previewBtn.disabled = true;
  setStatus(formStatus, "変換中…");
  try {
    const res = await fetch(`${API_BASE}/convert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        heroine: heroineSelect.value,
        backend: backendSelect.value,
        artist_mode: artistModeSelect.value,
        custom_artist: customArtistInput.value.trim() || undefined,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    promptTextarea.value = data.prompt;
    setStatus(formStatus, "プレビュー完了。編集してから生成できる", "ok");
  } catch (err) {
    setStatus(formStatus, `エラー: ${err.message}`, "error");
  } finally {
    previewBtn.disabled = false;
  }
});

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;
  const payload = {
    url: urlInput.value.trim(),
    heroine: heroineSelect.value,
    backend: backendSelect.value,
    artist_mode: artistModeSelect.value,
    custom_artist: customArtistInput.value.trim() || undefined,
    prompt_override: promptTextarea.value.trim() || undefined,
  };
  try {
    const entry = await callGenerate(payload, formStatus);
    setStatus(formStatus, `完了（${entry.duration_sec}秒） - ヒロイン: ${heroineLabel(entry.heroine)}`, "ok");
    promptTextarea.value = "";
    await resetGallery();
  } catch (err) {
    setStatus(formStatus, `エラー: ${err.message}`, "error");
  } finally {
    submitBtn.disabled = false;
  }
});

async function deleteEntry(entryId, card) {
  if (!confirm("この生成履歴と画像ファイルを削除する？")) return;
  const res = await fetch(`${API_BASE}/images/${entryId}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(`削除に失敗した: ${err.detail || res.status}`);
    return;
  }
  card.remove();
}

function renderCard(entry) {
  const img = (entry.image_urls && entry.image_urls[0]) || "";
  const created = entry.created_at ? new Date(entry.created_at).toLocaleString("ja-JP") : "";
  const tags = (entry.prompt || "").split(",").map((t) => t.trim()).filter(Boolean)
    .map((t) => RATING_TAG_ALIASES[t.toLowerCase()] || t);
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    ${img ? `<img src="${img}" loading="lazy" alt="generated">` : ""}
    <div class="card-body">
      <div class="heroine-name">${escapeHtml(heroineLabel(entry.heroine))}</div>
      <div>post #${entry.post_id} ・ ${escapeHtml(entry.backend || entry.model || "")}</div>
      <button type="button" class="secondary tag-toggle-btn">🏷 使用タグを表示 (${tags.length})</button>
      <div class="prompt hidden"></div>
      <div>${created}</div>
      <button type="button" class="secondary prompt-edit-toggle-btn">✏️ プロンプトを編集して再生成</button>
      <textarea class="regen-prompt hidden" rows="3">${escapeHtml(entry.prompt || "")}</textarea>
      <div class="card-actions">
        <a class="secondary" href="${entry.original_url}" target="_blank" rel="noopener">元投稿</a>
        <button type="button" class="regen-btn">🔁 再生成</button>
        <button type="button" class="delete-btn danger">🗑 削除</button>
      </div>
      <p class="status regen-status"></p>
    </div>
  `;

  const tagToggleBtn = card.querySelector(".tag-toggle-btn");
  const promptEl = card.querySelector(".prompt");
  let tagsRendered = false;
  tagToggleBtn.addEventListener("click", () => {
    const nowHidden = promptEl.classList.toggle("hidden");
    if (!nowHidden && !tagsRendered) {
      promptEl.innerHTML = tags
        .map((t) => `<span class="tag-pill" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</span>`)
        .join(", ");
      promptEl.querySelectorAll(".tag-pill").forEach((pill) => {
        pill.addEventListener("click", () => addFilterTag(pill.dataset.tag));
      });
      tagsRendered = true;
    }
    tagToggleBtn.textContent = nowHidden ? `🏷 使用タグを表示 (${tags.length})` : "🔼 タグを隠す";
  });

  const imgEl = card.querySelector("img");
  if (imgEl) imgEl.addEventListener("click", () => openLightbox(img));

  const promptEditToggleBtn = card.querySelector(".prompt-edit-toggle-btn");
  const regenPromptEl = card.querySelector(".regen-prompt");
  promptEditToggleBtn.addEventListener("click", () => {
    regenPromptEl.classList.toggle("hidden");
  });

  const regenBtn = card.querySelector(".regen-btn");
  const regenStatus = card.querySelector(".regen-status");
  regenBtn.addEventListener("click", async () => {
    regenBtn.disabled = true;
    const payload = {
      url: entry.original_url,
      heroine: entry.heroine,
      backend: entry.backend,
      model: entry.model,
      artist_mode: entry.artist_mode,
      custom_artist: entry.custom_artist,
      include_artist: entry.include_artist,
      use_custom: entry.use_custom,
      checkpoint: entry.checkpoint,
      width: entry.width,
      height: entry.height,
      prompt_override: regenPromptEl.classList.contains("hidden") ? undefined : regenPromptEl.value.trim(),
    };
    try {
      const newEntry = await callGenerate(payload, regenStatus);
      setStatus(regenStatus, `再生成完了（${newEntry.duration_sec}秒）`, "ok");
      await resetGallery();
    } catch (err) {
      setStatus(regenStatus, `エラー: ${err.message}`, "error");
    } finally {
      regenBtn.disabled = false;
    }
  });

  const deleteBtn = card.querySelector(".delete-btn");
  deleteBtn.addEventListener("click", () => deleteEntry(entry.id, card));

  return card;
}

function buildGalleryQuery() {
  const params = new URLSearchParams();
  params.set("limit", GALLERY_PAGE_SIZE);
  params.set("offset", galleryOffset);
  if (filterHeroineSelect.value) params.set("heroine", filterHeroineSelect.value);
  if (filterModelSelect.value) params.set("model", filterModelSelect.value);
  if (filterDateFrom.value) params.set("date_from", filterDateFrom.value);
  if (filterDateTo.value) params.set("date_to", filterDateTo.value);
  for (const tag of selectedTags) params.append("tag", tag);
  return params.toString();
}

async function loadGallery(append) {
  const res = await fetch(`${API_BASE}/images?${buildGalleryQuery()}`);
  const data = await res.json();
  galleryTotal = data.total;

  if (!append) gallery.innerHTML = "";
  if (!data.entries.length && !append) {
    gallery.innerHTML = `<p class="empty">まだ生成履歴がありません。</p>`;
  } else {
    for (const entry of data.entries) {
      gallery.appendChild(renderCard(entry));
    }
  }

  galleryOffset += data.entries.length;
  const shown = gallery.querySelectorAll(".card").length;
  galleryCount.textContent = `${shown} / ${galleryTotal} 件`;
  loadMoreBtn.classList.toggle("hidden", galleryOffset >= galleryTotal);
}

async function resetGallery() {
  galleryOffset = 0;
  await loadGallery(false);
  await loadTags();
}

reloadBtn.addEventListener("click", resetGallery);
loadMoreBtn.addEventListener("click", () => loadGallery(true));
filterApplyBtn.addEventListener("click", resetGallery);
filterResetBtn.addEventListener("click", () => {
  filterHeroineSelect.value = "";
  filterModelSelect.value = "";
  filterDateFrom.value = "";
  filterDateTo.value = "";
  selectedTags.clear();
  renderTagChips();
  resetGallery();
});

// ─────────────────────────────────────────────
// 自動バッチ生成パネル
// ─────────────────────────────────────────────

const BATCH_STATUS_POLL_MS = 3000;
let batchPollTimer = null;

function renderBatchStatus(status) {
  batchStartBtn.disabled = status.running;
  batchStopBtn.disabled = !status.running;
  if (!status.running) {
    setStatus(batchStatusEl, status.total_checked
      ? `停止中（前回: ${status.total_checked}件確認 / ${status.total_generated}件生成）`
      : "停止中");
    return;
  }
  const cfg = status.config || {};
  const heroineText = cfg.heroine ? heroineLabel(cfg.heroine) : "";
  let text = `稼働中（${heroineText}） 確認${status.total_checked}件 / 生成${status.total_generated}件`;
  if (cfg.lucky) text += " ・ 🍀lucky";
  else if (cfg.sort) text += ` ・ 並び順:${cfg.sort}`;
  if (status.current_post_id) text += ` ・ 現在 post #${status.current_post_id}`;
  if (status.last_error) text += ` ・ 直近エラー: ${status.last_error}`;
  setStatus(batchStatusEl, text, status.last_error ? "error" : "ok");
}

async function refreshBatchStatus() {
  try {
    const res = await fetch(`${API_BASE}/batch/status`);
    const status = await res.json();
    renderBatchStatus(status);
  } catch (err) {
    // ポーリング失敗は無視して次回リトライ
  }
}

function startBatchPolling() {
  if (batchPollTimer) return;
  refreshBatchStatus();
  batchPollTimer = setInterval(refreshBatchStatus, BATCH_STATUS_POLL_MS);
}

batchLuckyCheckbox.addEventListener("change", () => {
  batchSortSelect.disabled = batchLuckyCheckbox.checked;
});

batchForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  batchStartBtn.disabled = true;
  const payload = {
    search: batchSearchInput.value.trim(),
    heroine: batchHeroineSelect.value,
    backend: batchBackendSelect.value,
    artist_mode: batchArtistModeSelect.value,
    custom_artist: batchCustomArtistInput.value.trim() || undefined,
    sort: batchSortSelect.value || null,
    lucky: batchLuckyCheckbox.checked,
  };
  try {
    const status = await fetch(`${API_BASE}/batch/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(async (res) => {
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      return res.json();
    });
    renderBatchStatus(status);
  } catch (err) {
    setStatus(batchStatusEl, `エラー: ${err.message}`, "error");
    batchStartBtn.disabled = false;
  }
});

batchStopBtn.addEventListener("click", async () => {
  batchStopBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/batch/stop`, { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const status = await res.json();
    renderBatchStatus(status);
  } catch (err) {
    setStatus(batchStatusEl, `エラー: ${err.message}`, "error");
  }
});

(async function init() {
  await loadHeroines();
  await loadBackends();
  await loadComfyStatus();
  setInterval(loadComfyStatus, COMFY_STATUS_POLL_MS);
  await resetGallery();
  startBatchPolling();
})();

