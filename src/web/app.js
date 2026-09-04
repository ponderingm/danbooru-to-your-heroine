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

// バッチ検索クエリで未知のタグが検出された際の確認ポップアップ文面
const MSG_UNKNOWN_BATCH_TAGS_WARN =
  "【確認】以下のタグはDanbooruタグ辞書に見つかりませんでした。\n" +
  "スペルミス等の可能性がありますが、このままバッチを開始しますか？\n\n";

const heroineSelect = document.getElementById("f-heroine");
const backendSelect = document.getElementById("f-backend");
const fArtistInput = document.getElementById("f-artist");
const fArtistDropdown = document.getElementById("f-artist-dropdown");
const urlInput = document.getElementById("f-url");
const form = document.getElementById("form");
const submitBtn = document.getElementById("f-submit");
const formStatus = document.getElementById("form-status");
const promptTextarea = document.getElementById("f-prompt");
const previewBtn = document.getElementById("f-preview-btn");
const fOverrideBreasts = document.getElementById("f-override-breasts");
const fOverrideSkin = document.getElementById("f-override-skin");
const fOverrideCostume = document.getElementById("f-override-costume");
const fOverrideArtStyle = document.getElementById("f-override-art-style");
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
const bSearchDropdown = document.getElementById("b-search-dropdown");
const batchProviderSelect = document.getElementById("b-provider");
const batchHeroineSelect = document.getElementById("b-heroine");
const batchBackendSelect = document.getElementById("b-backend");
const bArtistInput = document.getElementById("b-artist");
const bArtistDropdown = document.getElementById("b-artist-dropdown");
const batchSortSelect = document.getElementById("b-sort");
const batchRatingSelect = document.getElementById("b-rating");
const batchLuckyCheckbox = document.getElementById("b-lucky");
const batchStartBtn = document.getElementById("b-start-btn");
const batchStopBtn = document.getElementById("b-stop-btn");
const bOverrideBreasts = document.getElementById("b-override-breasts");
const bOverrideSkin = document.getElementById("b-override-skin");
const bOverrideCostume = document.getElementById("b-override-costume");
const bOverrideArtStyle = document.getElementById("b-override-art-style");
const batchStatusEl = document.getElementById("batch-status");

function resolveArtistInput(val) {
  const v = (val || "").trim();
  if (!v || v === "none") return { artist_mode: "none", custom_artist: undefined };
  if (v === "keep") return { artist_mode: "keep", custom_artist: undefined };
  if (v === "override") return { artist_mode: "override", custom_artist: undefined };
  return { artist_mode: "custom", custom_artist: v };
}

// ─────────────────────────────────────────────
// 🎛️ カスタム Combobox コントローラー
// ─────────────────────────────────────────────

function setupCombobox({ inputEl, dropdownEl, getItems, onSelect, onDelete }) {
  if (!inputEl || !dropdownEl) return;

  let focusedIndex = -1;

  function renderDropdown() {
    const filterText = inputEl.value.trim().toLowerCase();
    if (inputEl.dataset.hasTagAutocomplete === "true" && filterText.length > 0) {
      closeDropdown();
      return;
    }
    const groups = getItems(filterText);
    
    let html = "";
    let totalItems = 0;
    
    groups.forEach(group => {
      if (!group.items || group.items.length === 0) return;
      if (group.title) {
        html += `<div class="combobox-group-title">${escapeHtml(group.title)}</div>`;
      }
      group.items.forEach(item => {
        totalItems++;
        const val = typeof item === "string" ? item : item.value;
        const label = typeof item === "string" ? item : (item.label || item.value);
        const badge = item.badge ? `<span class="item-badge">${escapeHtml(item.badge)}</span>` : "";
        const delBtn = item.canDelete ? `<button type="button" class="item-del-btn" title="履歴から削除" data-del="${escapeHtml(val)}">×</button>` : "";
        
        html += `
          <div class="combobox-item" data-value="${escapeHtml(val)}">
            <span class="item-label">${escapeHtml(label)}</span>
            <div style="display: flex; align-items: center;">
              ${badge}
              ${delBtn}
            </div>
          </div>
        `;
      });
    });

    if (totalItems === 0) {
      dropdownEl.innerHTML = `<div class="combobox-empty">該当する候補はありません</div>`;
    } else {
      dropdownEl.innerHTML = html;
    }

    focusedIndex = -1;
    dropdownEl.classList.add("active");
  }

  function closeDropdown() {
    dropdownEl.classList.remove("active");
    focusedIndex = -1;
  }

  inputEl.addEventListener("focus", () => {
    renderDropdown();
  });

  inputEl.addEventListener("input", () => {
    renderDropdown();
  });

  dropdownEl.addEventListener("pointerdown", (e) => {
    const delBtn = e.target.closest(".item-del-btn");
    if (delBtn) {
      e.preventDefault();
      e.stopPropagation();
      const delVal = delBtn.dataset.del;
      if (onDelete) onDelete(delVal);
      renderDropdown();
      return;
    }

    const itemEl = e.target.closest(".combobox-item");
    if (itemEl) {
      e.preventDefault();
      const val = itemEl.dataset.value;
      inputEl.value = val;
      if (onSelect) onSelect(val);
      closeDropdown();
    }
  });

  inputEl.addEventListener("keydown", (e) => {
    if (!dropdownEl.classList.contains("active")) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        renderDropdown();
        e.preventDefault();
      }
      return;
    }

    const items = dropdownEl.querySelectorAll(".combobox-item");
    if (items.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      focusedIndex = (focusedIndex + 1) % items.length;
      updateFocusedItem(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusedIndex = (focusedIndex - 1 + items.length) % items.length;
      updateFocusedItem(items);
    } else if (e.key === "Enter") {
      if (focusedIndex >= 0 && focusedIndex < items.length) {
        e.preventDefault();
        const val = items[focusedIndex].dataset.value;
        inputEl.value = val;
        if (onSelect) onSelect(val);
        closeDropdown();
      }
    } else if (e.key === "Escape") {
      closeDropdown();
    }
  });

  function updateFocusedItem(items) {
    items.forEach((it, idx) => {
      if (idx === focusedIndex) {
        it.classList.add("focused");
        it.scrollIntoView({ block: "nearest" });
      } else {
        it.classList.remove("focused");
      }
    });
  }

  document.addEventListener("click", (e) => {
    if (!inputEl.contains(e.target) && !dropdownEl.contains(e.target)) {
      closeDropdown();
    }
  });
}

function saveSearchHistory(query) {
  const q = (query || "").trim();
  if (!q) return;
  let history = JSON.parse(localStorage.getItem("d2h_search_history") || "[]");
  history = [q, ...history.filter(item => item !== q)].slice(0, 20);
  localStorage.setItem("d2h_search_history", JSON.stringify(history));
}

function deleteSearchHistory(val) {
  let history = JSON.parse(localStorage.getItem("d2h_search_history") || "[]");
  history = history.filter(item => item !== val);
  localStorage.setItem("d2h_search_history", JSON.stringify(history));
}

function getSearchComboboxItems(filter) {
  const history = JSON.parse(localStorage.getItem("d2h_search_history") || "[]");
  const filtered = history
    .filter(q => !filter || q.toLowerCase().includes(filter))
    .map(q => ({ value: q, label: `🔍 ${q}`, canDelete: true }));

  return filtered.length > 0 ? [{ title: "過去の検索クエリ", items: filtered }] : [];
}

const ARTIST_PRESETS = [
  { value: "none", label: "🏷️ none", badge: "完全除去" },
  { value: "keep", label: "🎨 keep", badge: "元絵維持" },
  { value: "override", label: "🦸 override", badge: "代表絵師" },
];

function saveArtistHistory(artist) {
  const a = (artist || "").trim();
  if (!a || ["none", "keep", "override"].includes(a)) return;
  let history = JSON.parse(localStorage.getItem("d2h_artist_history") || "[]");
  history = [a, ...history.filter(item => item !== a)].slice(0, 20);
  localStorage.setItem("d2h_artist_history", JSON.stringify(history));
}

function deleteArtistHistory(val) {
  let history = JSON.parse(localStorage.getItem("d2h_artist_history") || "[]");
  history = history.filter(item => item !== val);
  localStorage.setItem("d2h_artist_history", JSON.stringify(history));
}

function getArtistComboboxItems(filter) {
  const history = JSON.parse(localStorage.getItem("d2h_artist_history") || "[]");
  const filteredPresets = ARTIST_PRESETS.filter(p => !filter || p.value.includes(filter) || p.badge.includes(filter));
  const filteredHistory = history
    .filter(a => !filter || a.toLowerCase().includes(filter))
    .map(a => ({ value: a, label: `🧑‍🎨 ${a}`, badge: "履歴", canDelete: true }));

  const groups = [];
  if (filteredPresets.length > 0) {
    groups.push({ title: "プリセット", items: filteredPresets });
  }
  if (filteredHistory.length > 0) {
    groups.push({ title: "入力履歴", items: filteredHistory });
  }
  return groups;
}

// Combobox の初期化バインド
setupCombobox({
  inputEl: fArtistInput,
  dropdownEl: fArtistDropdown,
  getItems: getArtistComboboxItems,
  onDelete: deleteArtistHistory,
});

setupCombobox({
  inputEl: bArtistInput,
  dropdownEl: bArtistDropdown,
  getItems: getArtistComboboxItems,
  onDelete: deleteArtistHistory,
});

setupCombobox({
  inputEl: batchSearchInput,
  dropdownEl: bSearchDropdown,
  getItems: getSearchComboboxItems,
  onDelete: deleteSearchHistory,
});

// ─────────────────────────────────────────────
// 🏷️ Danbooru タグ オートコンプリート (ComfyUI-Autocomplete-Plus 風)
// ─────────────────────────────────────────────

// スペース区切り（カンマ不要）で入力・補完を行う要素ID一覧
const SPACE_SEPARATED_INPUT_IDS = new Set(["b-search"]);

function isSpaceSeparatedInput(inputEl) {
  return !!(inputEl && SPACE_SEPARATED_INPUT_IDS.has(inputEl.id));
}

let danbooruTagsData = [];
let danbooruKnownTagsSet = new Set();
let isDanbooruTagsLoaded = false;
let isLoadingDanbooruTags = false;

const DANBOORU_CAT_NAMES = {
  0: "General",
  1: "Artist",
  3: "Copyright",
  4: "Character",
  5: "Meta",
};

function hiraToKata(str) {
  return (str || "").replace(/[\u3041-\u3096]/g, match => String.fromCharCode(match.charCodeAt(0) + 0x60));
}

function kataToHira(str) {
  return (str || "").replace(/[\u30a1-\u30f6]/g, match => String.fromCharCode(match.charCodeAt(0) - 0x60));
}

function formatTagCount(num) {
  if (!num || isNaN(num)) return "0";
  if (num >= 1e6) return (num / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (num >= 1e3) return (num / 1e3).toFixed(1).replace(/\.0$/, "") + "k";
  return String(num);
}

function parseDanbooruCSV(text) {
  const lines = text.split(/\r?\n/);
  const result = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line) continue;
    const c1 = line.indexOf(",");
    if (c1 === -1) continue;
    const tag = line.substring(0, c1);
    const c2 = line.indexOf(",", c1 + 1);
    if (c2 === -1) continue;
    const cat = parseInt(line.substring(c1 + 1, c2), 10) || 0;
    const c3 = line.indexOf(",", c2 + 1);
    let count = 0;
    let aliasStr = "";
    if (c3 === -1) {
      count = parseInt(line.substring(c2 + 1), 10) || 0;
    } else {
      count = parseInt(line.substring(c2 + 1, c3), 10) || 0;
      aliasStr = line.substring(c3 + 1);
      if (aliasStr.startsWith('"') && aliasStr.endsWith('"')) {
        aliasStr = aliasStr.slice(1, -1);
      }
    }
    const aliases = aliasStr ? aliasStr.split(",").map(a => a.trim()).filter(Boolean) : [];
    result.push({
      tag,
      category: cat,
      count,
      alias: aliases,
      searchTag: tag.toLowerCase(),
      searchAliases: aliases.map(a => a.toLowerCase())
    });
  }
  return result;
}

async function loadDanbooruTags() {
  if (isDanbooruTagsLoaded || isLoadingDanbooruTags) return;
  isLoadingDanbooruTags = true;
  try {
    const res = await fetch("/data/danbooru_tags.csv");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const csvText = await res.text();
    danbooruTagsData = parseDanbooruCSV(csvText);
    danbooruKnownTagsSet = new Set();
    danbooruTagsData.forEach(t => {
      danbooruKnownTagsSet.add(t.searchTag);
      if (t.searchAliases && t.searchAliases.length > 0) {
        t.searchAliases.forEach(a => danbooruKnownTagsSet.add(a));
      }
    });

    isDanbooruTagsLoaded = true;
    console.log(`[Autocomplete] Loaded ${danbooruTagsData.length} Danbooru tags.`);
  } catch (err) {
    console.warn("[Autocomplete] Failed to load Danbooru tags CSV:", err);
  } finally {
    isLoadingDanbooruTags = false;
  }
}

/**
 * バッチ検索クエリ内の辞書未登録タグを検出する
 * 【案C: カンマ有無による条件分け】
 * - カンマが含まれる場合: カンマをタグ区切りとみなし、各チャンク内の空白はアンダースコア(_)として評価
 * - カンマが含まれない場合: 空白区切りとし、クォート("..." / '...')内のみアンダースコア(_)として評価
 * - "-" 除外タグやコロン付きメタタグはスキップ
 */
function findUnknownBatchTags(query) {
  if (!isDanbooruTagsLoaded || danbooruKnownTagsSet.size === 0) return [];
  if (!query) return [];

  const unknown = [];

  if (query.includes(",")) {
    // 【カンマ区切りモード】: カンマ単位で分割し、要素内の空白はアンダースコア(_)として評価
    const chunks = query.split(",").map(c => c.trim()).filter(Boolean);
    for (let chunk of chunks) {
      if (chunk.startsWith("-")) continue;
      if (chunk.includes(":")) {
        const parts = chunk.split(/[\s\u3000]+/).filter(Boolean);
        for (let p of parts) {
          if (p.startsWith("-") || p.includes(":")) continue;
          let cleanP = p.replace(/^,+|,+$/g, "").trim();
          if (!cleanP) continue;
          if (cleanP.startsWith("~")) cleanP = cleanP.slice(1);
          const norm = cleanP.toLowerCase().replace(/\s+/g, "_");
          if (!danbooruKnownTagsSet.has(norm)) {
            unknown.push(cleanP);
          }
        }
        continue;
      }
      let cleanChunk = chunk.replace(/^,+|,+$/g, "").trim();
      if (!cleanChunk) continue;
      if (cleanChunk.startsWith("~")) cleanChunk = cleanChunk.slice(1);
      const norm = cleanChunk.toLowerCase().replace(/\s+/g, "_");
      if (!danbooruKnownTagsSet.has(norm)) {
        unknown.push(cleanChunk);
      }
    }
  } else {
    // 【スペース区切りモード】: クォート囲み（"..." / '...'）または空白で分割
    const tokenRegex = /"([^"]+)"|'([^']+)'|([^\s\u3000]+)/g;
    let match;
    while ((match = tokenRegex.exec(query)) !== null) {
      let rawToken = match[1] || match[2] || match[3] || "";
      let token = rawToken.trim().replace(/^,+|,+$/g, "").trim();
      if (!token) continue;
      if (token.startsWith("-")) continue;
      if (token.includes(":")) continue;
      if (token.startsWith("~")) token = token.slice(1);
      token = token.replace(/^,+|,+$/g, "").trim();
      if (!token) continue;

      const normalized = token.toLowerCase().replace(/\s+/g, "_");
      if (!danbooruKnownTagsSet.has(normalized)) {
        unknown.push(rawToken);
      }
    }
  }

  return unknown;
}

let tagDropdownEl = null;
let currentAutocompleteInput = null;
let activeCandidateIndex = -1;
let currentSuggestions = [];

function getOrCreateTagDropdown() {
  if (!tagDropdownEl) {
    tagDropdownEl = document.createElement("div");
    tagDropdownEl.className = "tag-autocomplete-dropdown";
    document.body.appendChild(tagDropdownEl);

    // ドロップダウン外クリック/タップで閉じる
    document.addEventListener("pointerdown", (e) => {
      if (tagDropdownEl.classList.contains("active")) {
        if (!tagDropdownEl.contains(e.target) && (!currentAutocompleteInput || !currentAutocompleteInput.contains(e.target))) {
          closeTagAutocomplete();
        }
      }
    });

    window.addEventListener("resize", () => {
      if (tagDropdownEl.classList.contains("active") && currentAutocompleteInput) {
        positionTagDropdown(currentAutocompleteInput);
      }
    });

    // モバイルの仮想キーボード開閉・ピンチズーム追従
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", () => {
        if (tagDropdownEl.classList.contains("active") && currentAutocompleteInput) {
          positionTagDropdown(currentAutocompleteInput);
        }
      });
      window.visualViewport.addEventListener("scroll", () => {
        if (tagDropdownEl.classList.contains("active") && currentAutocompleteInput) {
          positionTagDropdown(currentAutocompleteInput);
        }
      });
    }
  }
  return tagDropdownEl;
}

function positionTagDropdown(inputEl) {
  if (!tagDropdownEl) return;
  const rect = inputEl.getBoundingClientRect();
  const isMobile = window.innerWidth <= 600;
  const dropdownWidth = isMobile ? Math.min(window.innerWidth - 16, 560) : Math.max(340, Math.min(rect.width, 560));
  
  const spaceBelow = window.innerHeight - rect.bottom;
  const dropdownHeight = 290;
  let top = rect.bottom + window.scrollY + 4;
  if (spaceBelow < dropdownHeight && rect.top > dropdownHeight) {
    top = rect.top + window.scrollY - dropdownHeight - 4;
  }

  let left = isMobile ? 8 : rect.left + window.scrollX;
  if (!isMobile && left + dropdownWidth > window.innerWidth - 16) {
    left = window.innerWidth - dropdownWidth - 16;
  }

  tagDropdownEl.style.top = `${top}px`;
  tagDropdownEl.style.left = `${Math.max(8, left)}px`;
  tagDropdownEl.style.width = `${dropdownWidth}px`;
}

function closeTagAutocomplete() {
  if (tagDropdownEl) {
    tagDropdownEl.classList.remove("active");
    tagDropdownEl.innerHTML = "";
  }
  currentSuggestions = [];
  activeCandidateIndex = -1;
  currentAutocompleteInput = null;
}

function getCaretTagInfo(inputEl) {
  const val = inputEl.value;
  const cursor = inputEl.selectionStart !== null ? inputEl.selectionStart : val.length;
  const before = val.substring(0, cursor);
  const after = val.substring(cursor);
  const isSpaceSep = isSpaceSeparatedInput(inputEl);

  // 1. クォート内入力の検出（"..." または '...'）
  const doubleQuotes = (before.match(/"/g) || []).length;
  const singleQuotes = (before.match(/'/g) || []).length;
  const inDouble = doubleQuotes % 2 === 1;
  const inSingle = singleQuotes % 2 === 1;

  if (inDouble || inSingle) {
    const quoteChar = inDouble ? '"' : "'";
    const quoteStart = before.lastIndexOf(quoteChar);
    const relQuoteEnd = after.indexOf(quoteChar);
    const tokenStart = quoteStart;
    const tokenEnd = relQuoteEnd === -1 ? val.length : cursor + relQuoteEnd + 1;
    const tokenInside = val.substring(quoteStart + 1, cursor);
    const query = tokenInside.trim().replace(/\s+/g, "_").toLowerCase();

    return {
      tokenStart,
      tokenEnd,
      cursor,
      tokenBeforeCursor: tokenInside,
      fullToken: val.substring(tokenStart, tokenEnd),
      query,
      isQuoted: true,
      combinedQuery: null,
      compoundStart: -1
    };
  }

  // 【案C: カンマ有無によるモード切り替え】
  // isSpaceSep対象の入力欄（b-search等）であっても、カンマが使われている場合はカンマ区切りモードとして動作
  const isCommaMode = !isSpaceSep || before.includes(",") || val.includes(",");

  let tokenStart = 0;
  let relEnd = -1;

  if (isCommaMode) {
    // カンマ区切りモード: カンマ（または改行）をセパレータとみなす（スペースはタグ内の単語区切り）
    const lastSep = Math.max(before.lastIndexOf(","), before.lastIndexOf("\n"));
    tokenStart = lastSep === -1 ? 0 : lastSep + 1;

    const nextComma = after.indexOf(",");
    const nextNewline = after.indexOf("\n");
    if (nextComma !== -1 && nextNewline !== -1) relEnd = Math.min(nextComma, nextNewline);
    else if (nextComma !== -1) relEnd = nextComma;
    else if (nextNewline !== -1) relEnd = nextNewline;
  } else {
    // スペース区切りモード: 空白（半角・全角）、改行をセパレータとみなす
    const matchBefore = before.match(/[\s\u3000][^\s\u3000]*$/);
    tokenStart = matchBefore ? matchBefore.index + 1 : 0;

    const matchAfter = after.match(/[\s\u3000]/);
    relEnd = matchAfter ? matchAfter.index : -1;
  }

  const tokenEnd = relEnd === -1 ? val.length : cursor + relEnd;

  const tokenBeforeCursor = val.substring(tokenStart, cursor);
  const fullToken = val.substring(tokenStart, tokenEnd);

  // 検索はスペースをアンダースコアとする（前後のカンマ・空白を除去）
  const trimmed = tokenBeforeCursor.replace(/^,+|,+$/g, "").trim();
  const query = trimmed.replace(/\s+/g, "_").toLowerCase();

  // 直前の単語との複合タグ判定（スペース区切りで、例えば "labia ring" と打った時に "labia_ring" を候補に出す）
  let combinedQuery = null;
  let compoundStart = -1;
  if (!isCommaMode && tokenStart > 0 && query.length > 0) {
    const textBeforeSep = before.substring(0, tokenStart - 1);
    const prevMatch = textBeforeSep.match(/(?:^|[\s\u3000,])([^\s\u3000,]+)$/);
    if (prevMatch) {
      const prevWord = prevMatch[1].replace(/^,+|,+$/g, "").trim();
      if (prevWord && !prevWord.includes(":") && !prevWord.startsWith("-")) {
        combinedQuery = `${prevWord}_${query}`.toLowerCase();
        compoundStart = tokenStart - 1 - prevMatch[1].length;
      }
    }
  }

  return {
    tokenStart,
    tokenEnd,
    cursor,
    tokenBeforeCursor,
    fullToken,
    query,
    isQuoted: false,
    combinedQuery,
    compoundStart,
    isCommaMode
  };
}

function searchTagsForQuery(query, fullText, limit = 25, combinedQuery = null) {
  if (!query || query.length === 0 || query.startsWith("#") || query.startsWith("/")) {
    return [];
  }

  const q = query.toLowerCase();
  const qKata = hiraToKata(q);
  const qHira = kataToHira(q);
  const cq = combinedQuery ? combinedQuery.toLowerCase() : null;

  // すでに入力済みのタグ（重複チェック・グレーアウト用）
  const enteredTags = new Set(
    (fullText || "")
      .toLowerCase()
      .split(/[,\n\s\u3000]/)
      .map(t => t.trim().replace(/^,+|,+$/g, "").replace(/\s+/g, "_"))
      .filter(Boolean)
  );

  const matched = [];

  for (let i = 0; i < danbooruTagsData.length; i++) {
    const t = danbooruTagsData[i];
    const tag = t.searchTag;
    let score = 0;
    let matchedAlias = null;
    let isCompound = false;

    // 複合クエリ（例: labia_ring）との完全一致・前方一致を最優先判定
    if (cq && (tag === cq || tag.startsWith(cq))) {
      score = 3000000000 + (tag === cq ? 100000000 : 0) + t.count;
      isCompound = true;
    } else if (tag === q) {
      score = 2000000000 + t.count;
    } else if (tag.startsWith(q)) {
      score = 1000000000 + t.count;
    } else {
      for (let j = 0; j < t.searchAliases.length; j++) {
        const alias = t.searchAliases[j];
        if (alias === q || alias === qKata || alias === qHira) {
          score = 1500000000 + t.count;
          matchedAlias = t.alias[j];
          break;
        }
        if (alias.startsWith(q) || alias.startsWith(qKata) || alias.startsWith(qHira)) {
          score = 800000000 + t.count;
          matchedAlias = t.alias[j];
          break;
        }
      }

      if (score === 0) {
        if (tag.includes(q)) {
          score = 500000000 + t.count;
        } else {
          for (let j = 0; j < t.searchAliases.length; j++) {
            const alias = t.searchAliases[j];
            if (alias.includes(q) || alias.includes(qKata) || alias.includes(qHira)) {
              score = t.count;
              matchedAlias = t.alias[j];
              break;
            }
          }
        }
      }
    }

    if (score > 0) {
      matched.push({
        tag: t.tag,
        category: t.category,
        count: t.count,
        alias: t.alias,
        matchedAlias,
        score,
        alreadyPresent: enteredTags.has(tag),
        isCompound
      });
    }
  }

  matched.sort((a, b) => b.score - a.score);
  return matched.slice(0, limit);
}

function renderTagDropdown(inputEl, suggestions) {
  const dropdown = getOrCreateTagDropdown();
  currentSuggestions = suggestions;
  currentAutocompleteInput = inputEl;
  activeCandidateIndex = suggestions.length > 0 ? 0 : -1;

  if (suggestions.length === 0) {
    closeTagAutocomplete();
    return;
  }

  let html = `
    <div class="tag-autocomplete-header">
      <span>⚡ DANBOORU TAG AUTOCOMPLETE</span>
      <span class="hint">↑↓:選択 / Enter,Tab:挿入 / F1:Wiki</span>
    </div>
  `;

  suggestions.forEach((item, index) => {
    const catClass = `cat-${item.category}`;
    const catName = DANBOORU_CAT_NAMES[item.category] || "General";
    const countStr = formatTagCount(item.count);
    const aliasStr = item.matchedAlias 
      ? `(${escapeHtml(item.matchedAlias)})`
      : (item.alias && item.alias.length > 0 ? escapeHtml(item.alias.slice(0, 3).join(", ")) : "");
    const presentClass = item.alreadyPresent ? "already-present" : "";
    const focusedClass = index === activeCandidateIndex ? "focused" : "";

    html += `
      <div class="tag-autocomplete-item ${presentClass} ${focusedClass}" data-index="${index}" data-tag="${escapeHtml(item.tag)}">
        <div class="tag-item-left">
          <span class="tag-category-badge ${catClass}">${escapeHtml(catName)}</span>
          <span class="tag-item-name ${catClass}">${escapeHtml(item.tag)}</span>
          ${aliasStr ? `<span class="tag-item-alias">${aliasStr}</span>` : ""}
        </div>
        <div class="tag-item-right">
          <span class="tag-item-count">${escapeHtml(countStr)}</span>
          <button type="button" class="tag-item-wiki-btn" title="Danbooru Wikiを開く (F1)" data-wiki="${escapeHtml(item.tag)}">📖</button>
        </div>
      </div>
    `;
  });

  dropdown.innerHTML = html;
  positionTagDropdown(inputEl);
  dropdown.classList.add("active");

  dropdown.querySelectorAll(".tag-autocomplete-item").forEach(itemEl => {
    itemEl.addEventListener("pointerdown", (e) => {
      const wikiBtn = e.target.closest(".tag-item-wiki-btn");
      if (wikiBtn) {
        e.preventDefault();
        e.stopPropagation();
        const tag = wikiBtn.dataset.wiki;
        window.open(`https://danbooru.donmai.us/wiki_pages/${encodeURIComponent(tag)}`, "_blank");
        return;
      }
      e.preventDefault();
      const idx = parseInt(itemEl.dataset.index, 10);
      if (suggestions[idx]) {
        applyTagCompletion(inputEl, suggestions[idx].tag, suggestions[idx].isCompound);
      }
    });
  });
}

function applyTagCompletion(inputEl, tagToInsert, isCompound = false) {
  const info = getCaretTagInfo(inputEl);
  const val = inputEl.value;
  const isSpaceSep = isSpaceSeparatedInput(inputEl);

  // スペースはアンダースコアとする
  const cleanTag = tagToInsert.trim().replace(/\s+/g, "_");

  // 複合タグ候補（labia_ring）の場合は直前の単語（labia）の位置から置換
  const replaceStart = (isCompound && info.compoundStart >= 0) ? info.compoundStart : info.tokenStart;
  const prefix = val.substring(0, replaceStart);
  const suffix = val.substring(info.tokenEnd);

  const needLeadingSpace = prefix.length > 0 && !prefix.endsWith(" ") && !prefix.endsWith("\n");
  const lead = needLeadingSpace ? " " : "";

  let tail = "";
  let newSuffix = suffix;

  const isCommaMode = !isSpaceSep || info.isCommaMode;

  if (!isCommaMode) {
    // スペース区切りモード: カンマは付加せず、スペース区切りとする
    const suffixTrimmed = suffix.replace(/^[,\s\u3000]+/, "");
    tail = " ";
    newSuffix = suffixTrimmed;
  } else {
    // カンマ区切りモード（プロンプト等、またはカンマ使用中の検索欄）
    const suffixTrimmed = suffix.trimStart();
    const hasTrailingComma = suffixTrimmed.startsWith(",");
    tail = hasTrailingComma ? "" : ", ";
    newSuffix = hasTrailingComma ? suffixTrimmed.replace(/^,\s*/, ", ") : suffix;
  }

  const replacement = lead + cleanTag + tail;
  const newVal = prefix + replacement + newSuffix;

  inputEl.value = newVal;
  const newCursorPos = prefix.length + replacement.length;
  inputEl.setSelectionRange(newCursorPos, newCursorPos);
  inputEl.focus();
  inputEl.dispatchEvent(new Event("input", { bubbles: true }));
  closeTagAutocomplete();
}

function updateFocusedTagItem() {
  if (!tagDropdownEl) return;
  const items = tagDropdownEl.querySelectorAll(".tag-autocomplete-item");
  items.forEach((it, idx) => {
    if (idx === activeCandidateIndex) {
      it.classList.add("focused");
      it.scrollIntoView({ block: "nearest" });
    } else {
      it.classList.remove("focused");
    }
  });
}

function setupTagAutocomplete(inputEl) {
  if (!inputEl) return;
  inputEl.dataset.hasTagAutocomplete = "true";

  function handleTrigger() {
    if (!isDanbooruTagsLoaded) {
      loadDanbooruTags();
      return;
    }
    const info = getCaretTagInfo(inputEl);
    if (!info.query || info.query.length === 0) {
      closeTagAutocomplete();
      return;
    }
    const suggestions = searchTagsForQuery(info.query, inputEl.value, 25, info.combinedQuery);
    renderTagDropdown(inputEl, suggestions);
  }

  inputEl.addEventListener("input", () => {
    handleTrigger();
  });

  inputEl.addEventListener("click", () => {
    handleTrigger();
  });

  inputEl.addEventListener("keydown", (e) => {
    const isDropdownOpen = tagDropdownEl && tagDropdownEl.classList.contains("active") && currentAutocompleteInput === inputEl;

    // F1: Wiki表示
    if (e.key === "F1") {
      if (isDropdownOpen && activeCandidateIndex >= 0 && currentSuggestions[activeCandidateIndex]) {
        e.preventDefault();
        const tag = currentSuggestions[activeCandidateIndex].tag;
        window.open(`https://danbooru.donmai.us/wiki_pages/${encodeURIComponent(tag)}`, "_blank");
        return;
      }
    }

    // フォーマットショートカット (Alt+Shift+F)
    if (e.altKey && e.shiftKey && (e.key === "F" || e.key === "f")) {
      e.preventDefault();
      const isSpaceSep = isSpaceSeparatedInput(inputEl);
      if (isSpaceSep) {
        const formatted = (inputEl.value || "")
          .split(/[\s\u3000,]+/)
          .map(t => t.trim().replace(/^,+|,+$/g, "").replace(/\s+/g, "_"))
          .filter(Boolean)
          .join(" ");
        inputEl.value = formatted ? formatted + " " : "";
      } else {
        const formatted = (inputEl.value || "")
          .split(/[,\n]+/)
          .map(t => t.trim().replace(/\s+/g, "_"))
          .filter(Boolean)
          .join(", ");
        inputEl.value = formatted ? formatted + ", " : "";
      }
      inputEl.dispatchEvent(new Event("input", { bubbles: true }));
      closeTagAutocomplete();
      return;
    }

    if (!isDropdownOpen) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (currentSuggestions.length > 0) {
        activeCandidateIndex = (activeCandidateIndex + 1) % currentSuggestions.length;
        updateFocusedTagItem();
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (currentSuggestions.length > 0) {
        activeCandidateIndex = (activeCandidateIndex - 1 + currentSuggestions.length) % currentSuggestions.length;
        updateFocusedTagItem();
      }
    } else if (e.key === "Enter" || e.key === "Tab") {
      if (activeCandidateIndex >= 0 && currentSuggestions[activeCandidateIndex]) {
        e.preventDefault();
        applyTagCompletion(inputEl, currentSuggestions[activeCandidateIndex].tag, currentSuggestions[activeCandidateIndex].isCompound);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeTagAutocomplete();
    }
  });

  inputEl.addEventListener("blur", () => {
    setTimeout(() => {
      if (currentAutocompleteInput === inputEl) {
        closeTagAutocomplete();
      }
    }, 200);
  });
}




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
    .map(({ id, label, online }) => {
      const indicator = online === true ? "🟢 " : (online === false ? "🔴 " : "");
      const suffix = online === false ? " (offline)" : "";
      return `<option value="${id}" ${online === false ? 'class="backend-offline"' : ""}>${indicator}${escapeHtml(label)}${suffix}</option>`;
    })
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
      .map(([bid, st]) => `<span class="comfy-dot ${st}">● ${escapeHtml(backendLabels[bid] || bid)}</span>`)
      .join("");
    // セレクタのオンライン/オフライン表示を更新する（ラベルは変えずにdot指標だけ更新）
    [backendSelect, batchBackendSelect].forEach(sel => {
      if (!sel) return;
      [...sel.options].forEach(opt => {
        const bid = opt.value;
        const st = data[bid];
        if (!st) return;
        const label = backendLabels[bid] || bid;
        const indicator = (st === "online") ? "🟢" : "🔴";
        const suffix = (st === "online") ? "" : " (offline)";
        opt.textContent = `${indicator} ${label}${suffix}`;
        opt.className = (st === "online") ? "" : "backend-offline";
        // もし現在選択中がオフラインになったなら、最初のオンラインに切り替える
        if (opt.selected && st === "offline") {
          const firstOnline = [...sel.options].find(o => o.className !== "backend-offline");
          if (firstOnline) sel.value = firstOnline.value;
        }
      });
    });
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

let currentPreviewData = null;

const sourceBox = document.getElementById("prompt-source-box");
const detectedBadge = document.getElementById("detected-model-badge");
const btnBooru = document.getElementById("btn-source-booru");
const btnRaw = document.getElementById("btn-source-raw");
const btnHybrid = document.getElementById("btn-source-hybrid");

function setPromptSource(sourceType) {
  if (!currentPreviewData) return;
  [btnBooru, btnRaw, btnHybrid].forEach((b) => b?.classList.remove("active"));
  if (sourceType === "booru") {
    btnBooru?.classList.add("active");
    promptTextarea.value = currentPreviewData.booru_prompt || currentPreviewData.prompt;
  } else if (sourceType === "raw") {
    btnRaw?.classList.add("active");
    promptTextarea.value = currentPreviewData.raw_prompt_heroine || currentPreviewData.prompt;
  } else if (sourceType === "hybrid") {
    btnHybrid?.classList.add("active");
    promptTextarea.value = currentPreviewData.hybrid_prompt || currentPreviewData.prompt;
  }
}

btnBooru?.addEventListener("click", () => setPromptSource("booru"));
btnRaw?.addEventListener("click", () => setPromptSource("raw"));
btnHybrid?.addEventListener("click", () => setPromptSource("hybrid"));

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
        override_breasts: fOverrideBreasts ? fOverrideBreasts.value : undefined,
        override_skin: fOverrideSkin ? fOverrideSkin.value : undefined,
        override_costume: fOverrideCostume ? fOverrideCostume.value : undefined,
        override_art_style: fOverrideArtStyle ? fOverrideArtStyle.value : undefined,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    currentPreviewData = data;
    promptTextarea.value = data.prompt;

    if (sourceBox) {
      if (data.has_raw_prompt) {
        sourceBox.classList.remove("hidden");
        if (btnRaw) btnRaw.style.display = "";
        if (btnHybrid) btnHybrid.style.display = "";
      } else if (data.detected_model) {
        sourceBox.classList.remove("hidden");
        if (btnRaw) btnRaw.style.display = "none";
        if (btnHybrid) btnHybrid.style.display = "none";
      } else {
        sourceBox.classList.add("hidden");
      }
      if (detectedBadge) {
        detectedBadge.textContent = data.detected_model ? `🤖 元モデル: ${data.detected_model}` : "";
        detectedBadge.style.display = data.detected_model ? "" : "none";
      }
      [btnBooru, btnRaw, btnHybrid].forEach((b) => b?.classList.remove("active"));
      btnBooru?.classList.add("active");
    }

    setStatus(formStatus, "プレビュー完了。構文ソースを選択・編集してから生成できるわよ♪", "ok");
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
    override_breasts: fOverrideBreasts ? fOverrideBreasts.value : undefined,
    override_skin: fOverrideSkin ? fOverrideSkin.value : undefined,
    override_costume: fOverrideCostume ? fOverrideCostume.value : undefined,
    override_art_style: fOverrideArtStyle ? fOverrideArtStyle.value : undefined,
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
  const resetBtn = document.getElementById("b-reset-btn");
  batchStartBtn.disabled = status.running;
  batchStopBtn.disabled = !status.running;
  // 停止中なのにrunning=Trueのまま詰まっている場合に強制リセットボタンを表示
  if (resetBtn) resetBtn.style.display = "none";
  if (!status.running) {
    setStatus(batchStatusEl, status.total_checked
      ? `停止中（前回: ${status.total_checked}件確認 / ${status.total_generated}件生成）`
      : "停止中");
    return;
  }
  const cfg = status.config || {};
  const heroineText = cfg.heroine ? heroineLabel(cfg.heroine) : "";
  const providerTag = cfg.provider ? `[${cfg.provider.toUpperCase()}] ` : "";
  let text = `稼働中 ${providerTag}（${heroineText}） 確認${status.total_checked}件 / 生成${status.total_generated}件`;
  if (cfg.lucky) text += " ・ 🍀lucky";
  else if (cfg.sort) text += ` ・ 並び順:${cfg.sort}`;
  if (status.current_post_id) text += ` ・ 現在 post #${status.current_post_id}`;
  if (status.last_error) {
    text += ` ・ 直近エラー: ${status.last_error}`;
    // last_errorがある状態でrunning=Trueが続いていたら強制リセットボタンを表示
    if (resetBtn) resetBtn.style.display = "";
  }
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
  // 前後の余分なカンマ・空白を除去・サニタイズ
  const rawQuery = batchSearchInput.value.trim();
  let query = rawQuery;

  if (query.includes(",")) {
    // 【案C: カンマ区切りモード】各カンマ要素内の空白をアンダースコア(_)に自動正規化
    const chunks = query.split(",").map(c => c.trim()).filter(Boolean);
    const normalizedChunks = chunks.map(chunk => {
      const clean = chunk.replace(/^["']|["']$/g, "").trim();
      if (clean.includes(":") || clean.startsWith("-")) {
        return clean.split(/[\s\u3000]+/).map(p => {
          if (p.includes(":") || p.startsWith("-")) return p;
          return p.replace(/\s+/g, "_");
        }).join(" ");
      }
      return clean.replace(/\s+/g, "_");
    });
    query = normalizedChunks.join(", ");
  } else {
    // 【案C: スペース区切りモード】クォート囲みフレーズ（例: "labia ring"）をアンダースコア形式に正規化
    query = query.replace(/["']([^"']+)["']/g, (m, phrase) => {
      return phrase.trim().replace(/\s+/g, "_");
    });
  }

  query = query.replace(/^[,\s\u3000]+|[,\s\u3000]+$/g, "").trim();
  if (query !== rawQuery) {
    batchSearchInput.value = query;
  }

  // 🏷️ 辞書未登録タグ（スペルミス候補）の確認ポップアップ
  // （"-" 除外タグやコロン付きメタタグはチェック対象外）
  const unknownTags = findUnknownBatchTags(query);
  if (unknownTags.length > 0) {
    const listStr = unknownTags.map(t => `・${t}`).join("\n");
    const confirmed = window.confirm(`${MSG_UNKNOWN_BATCH_TAGS_WARN}${listStr}`);
    if (!confirmed) {
      return;
    }
  }

  batchStartBtn.disabled = true;
  saveSearchHistory(query);

  const batchArtistParams = resolveArtistInput(bArtistInput ? bArtistInput.value : "");
  if (batchArtistParams.custom_artist) saveArtistHistory(batchArtistParams.custom_artist);

  const payload = {
    provider: batchProviderSelect ? batchProviderSelect.value : "danbooru",
    search: query,
    heroine: batchHeroineSelect.value,
    backend: batchBackendSelect.value,
    ...batchArtistParams,
    override_breasts: bOverrideBreasts ? bOverrideBreasts.value : undefined,
    override_skin: bOverrideSkin ? bOverrideSkin.value : undefined,
    override_costume: bOverrideCostume ? bOverrideCostume.value : undefined,
    override_art_style: bOverrideArtStyle ? bOverrideArtStyle.value : undefined,
    sort: batchSortSelect.value || null,
    rating: batchRatingSelect ? (batchRatingSelect.value || null) : null,
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

const batchResetBtn = document.getElementById("b-reset-btn");
if (batchResetBtn) {
  batchResetBtn.addEventListener("click", async () => {
    batchResetBtn.disabled = true;
    try {
      await fetch(`${API_BASE}/batch/reset`, { method: "POST" });
      await refreshBatchStatus();
    } catch (err) {
      setStatus(batchStatusEl, `リセット失敗: ${err.message}`, "error");
    } finally {
      batchResetBtn.disabled = false;
    }
  });
}

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

const authCivitaiKey = document.getElementById("auth-civitai-key");
const authDanbooruLogin = document.getElementById("auth-danbooru-login");
const authDanbooruKey = document.getElementById("auth-danbooru-key");
const authGelbooruUid = document.getElementById("auth-gelbooru-uid");
const authGelbooruKey = document.getElementById("auth-gelbooru-key");
const authSaveBtn = document.getElementById("auth-save-btn");
const authStatusEl = document.getElementById("auth-status");

async function loadSiteAuthConfig() {
  if (!authCivitaiKey) return;
  try {
    const res = await fetch(`${API_BASE}/config/site_auth`);
    if (!res.ok) return;
    const data = await res.json();
    authCivitaiKey.value = data.civitai_api_key || "";
    authDanbooruLogin.value = data.danbooru_login || "";
    authDanbooruKey.value = data.danbooru_api_key || "";
    authGelbooruUid.value = data.gelbooru_user_id || "";
    authGelbooruKey.value = data.gelbooru_api_key || "";
  } catch (err) {
    console.error("Failed to load site auth config:", err);
  }
}

if (authSaveBtn) {
  authSaveBtn.addEventListener("click", async () => {
    authSaveBtn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/config/site_auth`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          civitai_api_key: authCivitaiKey.value.trim(),
          danbooru_login: authDanbooruLogin.value.trim(),
          danbooru_api_key: authDanbooruKey.value.trim(),
          gelbooru_user_id: authGelbooruUid.value.trim(),
          gelbooru_api_key: authGelbooruKey.value.trim(),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadBackups();
      setStatus(authStatusEl, "✅ 外部サイトAPIキーを保存し、即時反映しました！", "success");
    } catch (err) {
      setStatus(authStatusEl, `❌ 保存失敗: ${err.message}`, "error");
    } finally {
      authSaveBtn.disabled = false;
    }
  });
}

const heroineCardList = document.getElementById("heroine-card-list");
const hmEditorTitle = document.getElementById("hm-editor-title");
const hmEditorSub = document.getElementById("hm-editor-sub");
const heroineNewBtn = document.getElementById("heroine-new-btn");
const helperCharName = document.getElementById("helper-char-name");
const helperSearchMode = document.getElementById("helper-search-mode");
const helperSite = document.getElementById("helper-site");
const helperAnalyzeBtn = document.getElementById("helper-analyze-btn");
const helperApplyAllBtn = document.getElementById("helper-apply-all-btn");
const helperStatusEl = document.getElementById("helper-status");
const helperResultsEl = document.getElementById("helper-results");
const helperFaceChips = document.getElementById("helper-face-chips");
const helperBodyChips = document.getElementById("helper-body-chips");
const helperSeriesChips = document.getElementById("helper-series-chips");
const helperCostumeChips = document.getElementById("helper-costume-chips");
const helperNegativeChips = document.getElementById("helper-negative-chips");

const heroineForm = document.getElementById("heroine-form");
const hmKey = document.getElementById("hm-key");
const hmName = document.getElementById("hm-name");
const hmCheckpoint = document.getElementById("hm-checkpoint");
const hmIdentity = document.getElementById("hm-identity");
const hmFace = document.getElementById("hm-face");
const hmBody = document.getElementById("hm-body");
const hmCostume = document.getElementById("hm-costume");
const hmRuleBreasts = document.getElementById("hm-rule-breasts");
const hmRuleSkin = document.getElementById("hm-rule-skin");
const hmRuleCostume = document.getElementById("hm-rule-costume");
const hmRuleArtStyle = document.getElementById("hm-rule-art-style");
const hmRuleArtist = document.getElementById("hm-rule-artist");
const hmSeries = document.getElementById("hm-series");
const hmArtist = document.getElementById("hm-artist");
const hmNegative = document.getElementById("hm-negative");
const hmSaveBtn = document.getElementById("hm-save-btn");
const hmDeleteBtn = document.getElementById("hm-delete-btn");
const hmStatusEl = document.getElementById("hm-status");

let heroinesDetailsCache = {};
let lastAnalysisResult = null;
let currentHeroineKey = null;

// 設定サブタブの切り替え
document.querySelectorAll(".settings-subnav-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".settings-subnav-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".settings-subpane").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    const target = document.getElementById(btn.dataset.subpane);
    if (target) target.classList.add("active");
  });
});

function appendTagToTextarea(textarea, tag) {
  if (!textarea || !tag) return;
  const current = textarea.value.trim();
  const tags = current ? current.split(/[\n,]+/).map(t => t.trim()).filter(Boolean) : [];
  if (!tags.includes(tag)) {
    tags.push(tag);
    textarea.value = tags.join(", ");
  }
}

async function loadHeroinesDetails() {
  try {
    const res = await fetch(`${API_BASE}/heroines/details`);
    if (!res.ok) return;
    const data = await res.json();
    heroinesDetailsCache = data.heroines || {};
    renderHeroineCardList();

    const keys = Object.keys(heroinesDetailsCache);
    if (keys.length > 0) {
      selectHeroine(keys.includes(currentHeroineKey) ? currentHeroineKey : keys[0]);
    } else {
      resetHeroineFormNew();
    }
  } catch (err) {
    console.error("Failed to load heroines details:", err);
  }
}

function renderHeroineCardList() {
  if (!heroineCardList) return;
  const keys = Object.keys(heroinesDetailsCache);
  if (keys.length === 0) {
    heroineCardList.innerHTML = `<div style="color: #666; font-size: 0.8rem; padding: 8px;">登録ヒロインなし</div>`;
    return;
  }
  heroineCardList.innerHTML = keys.map(k => {
    const h = heroinesDetailsCache[k] || {};
    const rules = h.override_rules || {};
    const isSource = rules.breasts === "source" || rules.breasts === "flexible";
    const badgeHtml = isSource
      ? `<span class="rule-badge source">🎨 Source</span>`
      : `<span class="rule-badge strict">🔒 Strict</span>`;
    const isActive = k === currentHeroineKey ? "active" : "";

    return `
      <div class="heroine-card ${isActive}" data-key="${escapeHtml(k)}">
        <div class="heroine-card-info">
          <span class="heroine-card-name">${escapeHtml(h.name || k)}</span>
          <span class="heroine-card-key">${escapeHtml(k)}</span>
        </div>
        ${badgeHtml}
      </div>
    `;
  }).join("");

  heroineCardList.querySelectorAll(".heroine-card").forEach(el => {
    el.addEventListener("click", () => {
      selectHeroine(el.dataset.key);
    });
  });
}

function selectHeroine(key) {
  currentHeroineKey = key;
  renderHeroineCardList();
  populateHeroineForm(key);
}

function populateHeroineForm(key) {
  const h = heroinesDetailsCache[key];
  if (!h) return;
  if (hmEditorTitle) hmEditorTitle.textContent = h.name || key;
  if (hmEditorSub) hmEditorSub.textContent = `ID: ${key}`;

  hmKey.value = key;
  hmKey.readOnly = true; // 既存編集時はキー変更不可
  hmName.value = h.name || "";
  hmCheckpoint.value = h.default_checkpoint || "";
  hmIdentity.value = (h.identity_tags || []).join(", ");
  hmFace.value = (h.face_tags || []).join(", ");
  hmBody.value = (h.body_tags || []).join(", ");
  hmCostume.value = (h.costume_tags || []).join(", ");

  const rules = h.override_rules || {};
  if (hmRuleBreasts) hmRuleBreasts.value = rules.breasts || "strict";
  if (hmRuleSkin) hmRuleSkin.value = rules.skin || "strict";
  if (hmRuleCostume) hmRuleCostume.value = rules.costume || "source";
  if (hmRuleArtStyle) hmRuleArtStyle.value = rules.art_style || "source";
  if (hmRuleArtist) hmRuleArtist.value = rules.artist || "none";

  hmSeries.value = (h.series_tags || []).join(", ");
  hmArtist.value = (h.artist_tags || []).join(", ");
  hmNegative.value = (h.negative_tags || []).join(", ");
  if (hmDeleteBtn) hmDeleteBtn.style.display = "";
  setStatus(hmStatusEl, "");
}

function resetHeroineFormNew() {
  currentHeroineKey = null;
  renderHeroineCardList();
  if (hmEditorTitle) hmEditorTitle.textContent = "新しいヒロインを作成";
  if (hmEditorSub) hmEditorSub.textContent = "新規登録モード";

  hmKey.value = "";
  hmKey.readOnly = false;
  hmName.value = "";
  hmCheckpoint.value = "";
  hmIdentity.value = "";
  hmFace.value = "";
  hmBody.value = "";
  hmCostume.value = "";
  if (hmRuleBreasts) hmRuleBreasts.value = "strict";
  if (hmRuleSkin) hmRuleSkin.value = "strict";
  if (hmRuleCostume) hmRuleCostume.value = "source";
  if (hmRuleArtStyle) hmRuleArtStyle.value = "source";
  if (hmRuleArtist) hmRuleArtist.value = "none";
  hmSeries.value = "";
  hmArtist.value = "";
  hmNegative.value = "";
  if (hmDeleteBtn) hmDeleteBtn.style.display = "none";
  hmKey.focus();
  setStatus(hmStatusEl, "新しいヒロインの情報を入力するか、上のBooruヘルパーで自動生成してね♪", "ok");
}

if (heroineNewBtn) {
  heroineNewBtn.addEventListener("click", resetHeroineFormNew);
}


// 🔍 Booruタグ分析ヘルパー
if (helperAnalyzeBtn) {
  helperAnalyzeBtn.addEventListener("click", async () => {
    const charName = helperCharName.value.trim();
    if (!charName) {
      setStatus(helperStatusEl, "キャラクター名を入力してください", "error");
      return;
    }
    helperAnalyzeBtn.disabled = true;
    setStatus(helperStatusEl, "Booruを検索してタグ出現頻度を統計分析中…");
    try {
      const res = await fetch(`${API_BASE}/heroines/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          character_name: charName,
          search_mode: helperSearchMode.value,
          site: helperSite.value,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      lastAnalysisResult = data;
      renderAnalysisResults(data);
      setStatus(helperStatusEl, `✅ ${data.total_posts_analyzed}件の投稿からアイデンティティ分析完了！`, "success");
      if (helperApplyAllBtn) helperApplyAllBtn.classList.remove("hidden");
    } catch (err) {
      setStatus(helperStatusEl, `❌ 分析失敗: ${err.message}`, "error");
    } finally {
      helperAnalyzeBtn.disabled = false;
    }
  });
}

function renderAnalysisResults(data) {
  if (!helperResultsEl) return;
  helperResultsEl.classList.remove("hidden");

  // 顔・頭部タグ
  if (helperFaceChips) {
    helperFaceChips.innerHTML = (data.face_candidates || []).map(f => `
      <span class="helper-chip" data-tag="${escapeHtml(f.tag)}" title="${escapeHtml(f.category)}">
        + ${escapeHtml(f.tag)} <span class="rate">${f.rate}%</span>
      </span>
    `).join("") || `<span style="color: #666;">検出なし</span>`;

    helperFaceChips.querySelectorAll(".helper-chip").forEach(el => {
      el.addEventListener("click", () => {
        appendTagToTextarea(hmFace, el.dataset.tag);
        el.style.opacity = "0.5";
      });
    });
  }

  // 身体タグ
  helperBodyChips.innerHTML = (data.body_candidates || []).map(b => `
    <span class="helper-chip" data-tag="${escapeHtml(b.tag)}" title="${escapeHtml(b.category)}">
      + ${escapeHtml(b.tag)} <span class="rate">${b.rate}%</span>
    </span>
  `).join("") || `<span style="color: #666;">検出なし</span>`;

  helperBodyChips.querySelectorAll(".helper-chip").forEach(el => {
    el.addEventListener("click", () => {
      appendTagToTextarea(hmBody, el.dataset.tag);
      el.style.opacity = "0.5";
    });
  });

  // 作品タグ
  helperSeriesChips.innerHTML = (data.series_candidates || []).map(s => `
    <span class="helper-chip" data-tag="${escapeHtml(s.tag)}">
      + ${escapeHtml(s.tag)} <span class="rate">${s.rate}%</span>
    </span>
  `).join("") || `<span style="color: #666;">検出なし</span>`;

  helperSeriesChips.querySelectorAll(".helper-chip").forEach(el => {
    el.addEventListener("click", () => {
      const esc = el.dataset.tag.replace(/\(/g, "\\(").replace(/\)/g, "\\)");
      appendTagToTextarea(hmSeries, esc);
      el.style.opacity = "0.5";
    });
  });

  // 衣装タグ
  helperCostumeChips.innerHTML = (data.costume_candidates || []).map(c => `
    <span class="helper-chip" data-tag="${escapeHtml(c.tag)}">
      + ${escapeHtml(c.tag)} <span class="rate">${c.rate}%</span>
    </span>
  `).join("") || `<span style="color: #666;">検出なし</span>`;

  helperCostumeChips.querySelectorAll(".helper-chip").forEach(el => {
    el.addEventListener("click", () => {
      appendTagToTextarea(hmCostume, el.dataset.tag);
      el.style.opacity = "0.5";
    });
  });

  // ネガティブタグ
  helperNegativeChips.innerHTML = (data.negative_candidates || []).map(n => `
    <span class="helper-chip" data-tag="${escapeHtml(n.tag)}" title="${escapeHtml(n.reason)}">
      + ${escapeHtml(n.tag)}
    </span>
  `).join("") || `<span style="color: #666;">検出なし</span>`;

  helperNegativeChips.querySelectorAll(".helper-chip").forEach(el => {
    el.addEventListener("click", () => {
      appendTagToTextarea(hmNegative, el.dataset.tag);
      el.style.opacity = "0.5";
    });
  });
}

// ✨ 分析結果を一括反映
if (helperApplyAllBtn) {
  helperApplyAllBtn.addEventListener("click", () => {
    if (!lastAnalysisResult) return;
    const d = lastAnalysisResult;
    if (!hmName.value) hmName.value = d.character_name;
    if (!hmKey.value) hmKey.value = d.character_name.replace(/\s+/g, "_").toLowerCase();

    hmIdentity.value = (d.suggested_identity_tags || []).join(", ");
    hmFace.value = (d.suggested_face_tags || []).join(", ");
    hmBody.value = (d.suggested_body_tags || []).join(", ");
    hmCostume.value = (d.suggested_costume_tags || []).join(", ");

    const r = d.suggested_override_rules || {};
    if (hmRuleBreasts) hmRuleBreasts.value = r.breasts || "strict";
    if (hmRuleSkin) hmRuleSkin.value = r.skin || "strict";
    if (hmRuleCostume) hmRuleCostume.value = r.costume || "source";
    if (hmRuleArtStyle) hmRuleArtStyle.value = r.art_style || "source";
    if (hmRuleArtist) hmRuleArtist.value = r.artist || "none";

    hmSeries.value = (d.suggested_series_tags || []).map(t => t.replace(/\(/g, "\\(").replace(/\)/g, "\\)")).join(", ");

    if (d.artist_candidates && d.artist_candidates.length > 0 && !hmArtist.value) {
      hmArtist.value = d.artist_candidates[0].tag;
    }
    if (d.negative_candidates && d.negative_candidates.length > 0) {
      hmNegative.value = d.negative_candidates.map(n => n.tag).join(", ");
    }
    setStatus(hmStatusEl, "✨ 3大カテゴリと絶対遵守ルールを一括流し込みしたわ！確認して保存してね♪", "success");
  });
}

// ヒロインフォーム保存
if (heroineForm) {
  heroineForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const key = hmKey.value.trim().replace(/\s+/g, "_").toLowerCase();
    if (!key) {
      setStatus(hmStatusEl, "ヒロインIDを入力してください", "error");
      return;
    }
    hmSaveBtn.disabled = true;
    try {
      const splitTags = (val) => val.split(/[\n,]+/).map(t => t.trim()).filter(Boolean);

      const heroineData = {
        name: hmName.value.trim() || key,
        identity_tags: splitTags(hmIdentity.value),
        face_tags: splitTags(hmFace.value),
        body_tags: splitTags(hmBody.value),
        costume_tags: splitTags(hmCostume.value),
        override_rules: {
          breasts: hmRuleBreasts ? hmRuleBreasts.value : "strict",
          skin: hmRuleSkin ? hmRuleSkin.value : "strict",
          costume: hmRuleCostume ? hmRuleCostume.value : "source",
          art_style: hmRuleArtStyle ? hmRuleArtStyle.value : "source",
          artist: hmRuleArtist ? hmRuleArtist.value : "none",
        },
        series_tags: splitTags(hmSeries.value),
        artist_tags: splitTags(hmArtist.value),
        negative_tags: splitTags(hmNegative.value),
        default_checkpoint: hmCheckpoint.value.trim() || undefined,
      };

      const res = await fetch(`${API_BASE}/heroines/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key, data: heroineData }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      await loadHeroines();
      await loadHeroinesDetails();
      selectHeroine(key);
      await loadBackups();
      setStatus(hmStatusEl, `✅ ヒロイン '${heroineData.name}' を保存・反映しました！`, "success");
    } catch (err) {
      setStatus(hmStatusEl, `❌ 保存失敗: ${err.message}`, "error");
    } finally {
      hmSaveBtn.disabled = false;
    }
  });
}


// ヒロイン削除
if (hmDeleteBtn) {
  hmDeleteBtn.addEventListener("click", async () => {
    const key = hmKey.value.trim();
    if (!key || !confirm(`本当にヒロイン '${key}' を削除する？`)) return;
    hmDeleteBtn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/heroines/${key}`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      currentHeroineKey = null;
      await loadHeroines();
      await loadHeroinesDetails();
      await loadBackups();
      setStatus(hmStatusEl, `✅ ヒロイン '${key}' を削除しました`, "success");

    } catch (err) {
      setStatus(hmStatusEl, `❌ 削除失敗: ${err.message}`, "error");
    } finally {
      hmDeleteBtn.disabled = false;
    }
  });
}

// ヘルプアイコンのクリックトグル（モバイル・タッチ対応）
document.addEventListener("click", (e) => {
  const tip = e.target.closest(".help-tip");
  document.querySelectorAll(".help-tip.active").forEach(el => {
    if (el !== tip) el.classList.remove("active");
  });
  if (tip) {
    tip.classList.toggle("active");
  }
});

(async function init() {

  // 保存されていたタブ、またはURLハッシュから復元
  const hash = location.hash.replace("#", "");
  const savedTab = localStorage.getItem("d2h_active_tab");
  const targetTab = ["generate", "gallery", "settings"].includes(hash) ? hash : (savedTab || "generate");
  switchTab(targetTab);

  try {
    // 主要データを先に読み込む
    await Promise.all([
      loadHeroines(),
      loadHeroinesDetails(),
      loadBackends(),
    ]);

    // データが揃ってからギャラリーを描画する
    await resetGallery();
  } catch (err) {
    console.error("Init Error:", err);
    alert("初期化エラー: " + err.message);
  }

  // 設定系やステータスポーリングはバックグラウンドで非同期読み込み
  loadPurgeTags();
  loadBackups();
  loadNotificationConfig();
  loadSiteAuthConfig();
  loadDanbooruTags();

  // 🏷️ Danbooru タグ オートコンプリートのバインド
  const autocompleteTargetIds = [
    "f-prompt",
    "b-search",
    "user-purge-input",
    "hm-identity",
    "hm-face",
    "hm-body",
    "hm-costume",
    "hm-series",
    "hm-negative"
  ];
  autocompleteTargetIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) setupTagAutocomplete(el);
  });

  loadComfyStatus().then(() => {
    setInterval(loadComfyStatus, COMFY_STATUS_POLL_MS);
  });
  startBatchPolling();
})();







