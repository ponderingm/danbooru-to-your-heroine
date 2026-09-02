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
const fArtistInput = document.getElementById("f-artist");
const artistDatalist = document.getElementById("artist-datalist");
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
const searchHistoryDatalist = document.getElementById("search-history-datalist");
const batchHeroineSelect = document.getElementById("b-heroine");
const batchBackendSelect = document.getElementById("b-backend");
const bArtistInput = document.getElementById("b-artist");
const batchSortSelect = document.getElementById("b-sort");
const batchLuckyCheckbox = document.getElementById("b-lucky");
const batchStartBtn = document.getElementById("b-start-btn");
const batchStopBtn = document.getElementById("b-stop-btn");
const batchStatusEl = document.getElementById("batch-status");

function resolveArtistInput(val) {
  const v = (val || "").trim();
  if (!v || v === "none") return { artist_mode: "none", custom_artist: undefined };
  if (v === "keep") return { artist_mode: "keep", custom_artist: undefined };
  if (v === "override") return { artist_mode: "override", custom_artist: undefined };
  return { artist_mode: "custom", custom_artist: v };
}

function saveSearchHistory(query) {
  const q = (query || "").trim();
  if (!q) return;
  let history = JSON.parse(localStorage.getItem("d2h_search_history") || "[]");
  history = [q, ...history.filter(item => item !== q)].slice(0, 20);
  localStorage.setItem("d2h_search_history", JSON.stringify(history));
  renderSearchHistoryDatalist();
}

function renderSearchHistoryDatalist() {
  if (!searchHistoryDatalist) return;
  const history = JSON.parse(localStorage.getItem("d2h_search_history") || "[]");
  searchHistoryDatalist.innerHTML = history.map(item => `<option value="${escapeHtml(item)}"></option>`).join("");
}

function saveArtistHistory(artist) {
  const a = (artist || "").trim();
  if (!a || ["none", "keep", "override"].includes(a)) return;
  let history = JSON.parse(localStorage.getItem("d2h_artist_history") || "[]");
  history = [a, ...history.filter(item => item !== a)].slice(0, 20);
  localStorage.setItem("d2h_artist_history", JSON.stringify(history));
  renderArtistDatalist();
}

function renderArtistDatalist() {
  if (!artistDatalist) return;
  const history = JSON.parse(localStorage.getItem("d2h_artist_history") || "[]");
  let html = `
    <option value="none">除去 (none)</option>
    <option value="keep">元投稿優先 (keep)</option>
    <option value="override">ヒロイン固定 (override)</option>
  `;
  if (history.length > 0) {
    html += history.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(item)} (履歴)</option>`).join("");
  }
  artistDatalist.innerHTML = html;
}

[fArtistInput, bArtistInput, batchSearchInput].forEach(el => {
  if (!el) return;
  el.addEventListener("focus", () => el.select());
});



const userPurgeInput = document.getElementById("user-purge-input");
const purgeSaveBtn = document.getElementById("purge-save-btn");
const purgeReloadBtn = document.getElementById("purge-reload-btn");
const purgeInfoEl = document.getElementById("purge-info");

const backupSelect = document.getElementById("backup-select");
const backupRestoreBtn = document.getElementById("backup-restore-btn");
const backupStatusEl = document.getElementById("backup-status");
const configReloadBtn = document.getElementById("config-reload-btn");
const systemStatusEl = document.getElementById("system-status");

const tabBtns = document.querySelectorAll(".tab-btn");
const tabPanes = document.querySelectorAll(".tab-pane");

function switchTab(tabName) {
  const currentScrollY = window.scrollY;
  tabBtns.forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  tabPanes.forEach(pane => {
    pane.classList.toggle("active", pane.id === `tab-${tabName}`);
  });
  localStorage.setItem("d2h_active_tab", tabName);
  // スクロールジャンプを防ぎつつURLハッシュのみ静かに更新
  history.replaceState(null, "", `#${tabName}`);
  window.scrollTo(0, currentScrollY);
}


tabBtns.forEach(btn => {
  btn.addEventListener("click", () => {
    switchTab(btn.dataset.tab);
  });
});

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
  const artistParams = resolveArtistInput(fArtistInput ? fArtistInput.value : "");
  try {
    const res = await fetch(`${API_BASE}/convert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        heroine: heroineSelect.value,
        backend: backendSelect.value,
        ...artistParams,
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
  const artistParams = resolveArtistInput(fArtistInput ? fArtistInput.value : "");
  if (artistParams.custom_artist) saveArtistHistory(artistParams.custom_artist);

  const payload = {
    url: urlInput.value.trim(),
    heroine: heroineSelect.value,
    backend: backendSelect.value,
    ...artistParams,
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
  const query = batchSearchInput.value.trim();
  saveSearchHistory(query);

  const batchArtistParams = resolveArtistInput(bArtistInput ? bArtistInput.value : "");
  if (batchArtistParams.custom_artist) saveArtistHistory(batchArtistParams.custom_artist);

  const payload = {
    search: query,
    heroine: batchHeroineSelect.value,
    backend: batchBackendSelect.value,
    ...batchArtistParams,
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

const userPurgeChips = document.getElementById("user-purge-chips");
const baseArtifactChips = document.getElementById("base-artifact-chips");
const baseMetaChips = document.getElementById("base-meta-chips");
const baseArtifactCount = document.getElementById("base-artifact-count");
const baseMetaCount = document.getElementById("base-meta-count");

let currentUserPurgeTags = [];
let currentUserUnpurgeTags = new Set();
let currentBaseArtifactTags = [];
let currentBaseMetaTags = [];

function renderPurgeChips() {
  if (userPurgeChips) {
    userPurgeChips.innerHTML = "";
    if (currentUserPurgeTags.length === 0) {
      userPurgeChips.innerHTML = '<span class="empty">登録中のUserパージタグはありません</span>';
    } else {
      currentUserPurgeTags.forEach(tag => {
        const chip = document.createElement("span");
        chip.className = "tag-chip user-chip";
        chip.textContent = `${tag} ✕`;
        chip.title = "クリックで削除";
        chip.addEventListener("click", () => {
          currentUserPurgeTags = currentUserPurgeTags.filter(t => t !== tag);
          renderPurgeChips();
        });
        userPurgeChips.appendChild(chip);
      });
    }
  }

  if (baseArtifactChips) {
    baseArtifactChips.innerHTML = "";
    currentBaseArtifactTags.forEach(tag => {
      const chip = document.createElement("span");
      const isUnpurged = currentUserUnpurgeTags.has(tag);
      chip.className = `tag-chip base-chip ${isUnpurged ? "unpurged" : ""}`;
      chip.textContent = isUnpurged ? `${tag} (解除中)` : tag;
      chip.title = isUnpurged ? "クリックで除外を再有効化" : "クリックでBase層から除外解除（残す）";
      chip.addEventListener("click", () => {
        if (currentUserUnpurgeTags.has(tag)) {
          currentUserUnpurgeTags.delete(tag);
        } else {
          currentUserUnpurgeTags.add(tag);
        }
        renderPurgeChips();
      });
      baseArtifactChips.appendChild(chip);
    });
  }

  if (baseMetaChips) {
    baseMetaChips.innerHTML = "";
    currentBaseMetaTags.forEach(tag => {
      const chip = document.createElement("span");
      const isUnpurged = currentUserUnpurgeTags.has(tag);
      chip.className = `tag-chip base-chip ${isUnpurged ? "unpurged" : ""}`;
      chip.textContent = isUnpurged ? `${tag} (解除中)` : tag;
      chip.title = isUnpurged ? "クリックで除外を再有効化" : "クリックでBase層から除外解除（残す）";
      chip.addEventListener("click", () => {
        if (currentUserUnpurgeTags.has(tag)) {
          currentUserUnpurgeTags.delete(tag);
        } else {
          currentUserUnpurgeTags.add(tag);
        }
        renderPurgeChips();
      });
      baseMetaChips.appendChild(chip);
    });
  }

  if (baseArtifactCount) baseArtifactCount.textContent = currentBaseArtifactTags.length;
  if (baseMetaCount) baseMetaCount.textContent = currentBaseMetaTags.length;

  if (purgeInfoEl) {
    const baseTotal = currentBaseArtifactTags.length + currentBaseMetaTags.length;
    const userTotal = currentUserPurgeTags.length;
    const unpurgeTotal = currentUserUnpurgeTags.size;
    const effectiveTotal = baseTotal + userTotal - unpurgeTotal;
    purgeInfoEl.textContent = `📊 Base層: ${baseTotal}タグ | User層: ${userTotal}タグ | 除外解除(残す): ${unpurgeTotal}タグ | 実効除外数: ${effectiveTotal}タグ`;
  }
}

async function loadPurgeTags() {
  try {
    const res = await fetch(`${API_BASE}/purge_tags`);
    if (!res.ok) return;
    const data = await res.json();
    currentUserPurgeTags = data.user_purge_tags || [];
    currentUserUnpurgeTags = new Set(data.user_unpurge_tags || []);
    currentBaseArtifactTags = data.base_artifact_tags || [];
    currentBaseMetaTags = data.base_meta_tags || [];
    renderPurgeChips();
  } catch (err) {
    console.error("Failed to load purge tags:", err);
  }
}

if (purgeSaveBtn) {
  purgeSaveBtn.addEventListener("click", async () => {
    purgeSaveBtn.disabled = true;
    
    // textarea に入力されたタグをパース（改行またはカンマ区切り）
    const rawVal = (userPurgeInput && userPurgeInput.value) || "";
    const newTags = rawVal
      .split(/[\n,]+/)
      .map(t => t.trim().toLowerCase())
      .filter(Boolean);

    // 既存のリストに統合
    const merged = Array.from(new Set([...currentUserPurgeTags, ...newTags]));
    currentUserPurgeTags = merged;

    try {
      const res = await fetch(`${API_BASE}/purge_tags`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          purge_tags: currentUserPurgeTags,
          unpurge_tags: Array.from(currentUserUnpurgeTags),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      if (userPurgeInput) userPurgeInput.value = ""; // 入力欄をクリア
      await loadPurgeTags();
      await loadBackups();
      setStatus(purgeInfoEl, "✅ パージ設定を保存し、即座に反映しました！", "success");
    } catch (err) {
      setStatus(purgeInfoEl, `❌ 保存失敗: ${err.message}`, "error");
    } finally {
      purgeSaveBtn.disabled = false;
    }
  });
}


if (purgeReloadBtn) {
  purgeReloadBtn.addEventListener("click", async () => {
    await loadPurgeTags();
    await loadBackups();
  });
}

async function loadBackups() {
  if (!backupSelect) return;
  try {
    const res = await fetch(`${API_BASE}/purge_tags/backups`);
    if (!res.ok) return;
    const data = await res.json();
    backupSelect.innerHTML = "";
    if (!data.backups || data.backups.length === 0) {
      backupSelect.innerHTML = '<option value="">バックアップ履歴はありません</option>';
      if (backupRestoreBtn) backupRestoreBtn.disabled = true;
      return;
    }
    data.backups.forEach(b => {
      const opt = document.createElement("option");
      opt.value = b.filename;
      opt.textContent = `${b.created_at} (${b.tag_count}タグ) - ${b.filename}`;
      backupSelect.appendChild(opt);
    });
    if (backupRestoreBtn) backupRestoreBtn.disabled = false;
  } catch (err) {
    console.error("Failed to load backups:", err);
  }
}

if (backupRestoreBtn) {
  backupRestoreBtn.addEventListener("click", async () => {
    const filename = backupSelect.value;
    if (!filename) return;
    if (!confirm(`バックアップ「${filename}」からタグ設定を復元しますか？`)) return;
    try {
      const res = await fetch(`${API_BASE}/purge_tags/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadPurgeTags();
      await loadBackups();
      setStatus(backupStatusEl, `✅ 「${filename}」から正常に復元しました！`, "success");
    } catch (err) {
      setStatus(backupStatusEl, `❌ 復元失敗: ${err.message}`, "error");
    }
  });
}

if (configReloadBtn) {
  configReloadBtn.addEventListener("click", async () => {
    try {
      const res = await fetch(`${API_BASE}/config/reload`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadPurgeTags();
      await loadBackups();
      setStatus(systemStatusEl, "✅ config.yaml を再読込しました！", "success");
    } catch (err) {
      setStatus(systemStatusEl, `❌ リロード失敗: ${err.message}`, "error");
    }
  });
}

const notifWebhookUrl = document.getElementById("notif-webhook-url");
const notifLevel = document.getElementById("notif-level");
const notifIncludeImage = document.getElementById("notif-include-image");
const notifSaveBtn = document.getElementById("notif-save-btn");
const notifTestBtn = document.getElementById("notif-test-btn");
const notifStatusEl = document.getElementById("notif-status");

async function loadNotificationConfig() {
  if (!notifWebhookUrl) return;
  try {
    const res = await fetch(`${API_BASE}/config/notification`);
    if (!res.ok) return;
    const data = await res.json();
    notifWebhookUrl.value = data.webhook_url || "";
    if (notifLevel) notifLevel.value = data.notify_level || "success";
    if (notifIncludeImage) notifIncludeImage.checked = !!data.include_image;
  } catch (err) {
    console.error("Failed to load notification config:", err);
  }
}

if (notifSaveBtn) {
  notifSaveBtn.addEventListener("click", async () => {
    notifSaveBtn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/config/notification`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          webhook_url: notifWebhookUrl.value.trim(),
          notify_level: notifLevel.value,
          include_image: notifIncludeImage.checked,
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadBackups();
      setStatus(notifStatusEl, "✅ Discord通知設定を保存し、即時反映しました！", "success");
    } catch (err) {
      setStatus(notifStatusEl, `❌ 保存失敗: ${err.message}`, "error");
    } finally {
      notifSaveBtn.disabled = false;
    }
  });
}

if (notifTestBtn) {
  notifTestBtn.addEventListener("click", async () => {
    notifTestBtn.disabled = true;
    setStatus(notifStatusEl, "テスト通知送信中…");
    try {
      const res = await fetch(`${API_BASE}/notify/test`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      setStatus(notifStatusEl, "✅ Discordへテスト通知を送信しました！チャンネルを確認してね♪", "success");
    } catch (err) {
      setStatus(notifStatusEl, `❌ 送信失敗: ${err.message}`, "error");
    } finally {
      notifTestBtn.disabled = false;
    }
  });
}

(async function init() {
  // 保存されていたタブ、またはURLハッシュから復元
  const hash = location.hash.replace("#", "");
  const savedTab = localStorage.getItem("d2h_active_tab");
  const targetTab = ["generate", "gallery", "settings"].includes(hash) ? hash : (savedTab || "generate");
  switchTab(targetTab);

  await loadHeroines();
  await loadBackends();
  renderArtistDatalist();
  renderSearchHistoryDatalist();
  await loadPurgeTags();
  await loadBackups();
  await loadNotificationConfig();
  await loadComfyStatus();
  setInterval(loadComfyStatus, COMFY_STATUS_POLL_MS);
  await resetGallery();
  startBatchPolling();
})();





