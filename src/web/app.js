const API_BASE = ""; // 同一オリジン配信なので空文字（相対パス）でOK

const heroineSelect = document.getElementById("f-heroine");
const modelSelect = document.getElementById("f-model");
const urlInput = document.getElementById("f-url");
const nsfwCheckbox = document.getElementById("f-nsfw");
const customCheckbox = document.getElementById("f-custom");
const form = document.getElementById("form");
const submitBtn = document.getElementById("f-submit");
const formStatus = document.getElementById("form-status");
const gallery = document.getElementById("gallery");
const reloadBtn = document.getElementById("reload-btn");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxClose = document.getElementById("lightbox-close");

let heroines = {};

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
}

function heroineLabel(key) {
  return heroines[key] ? heroines[key].name : key;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function callGenerate(payload, statusEl) {
  setStatus(statusEl, "生成中…（ComfyUIの処理が終わるまで待ちます）");
  const res = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;
  const payload = {
    url: urlInput.value.trim(),
    heroine: heroineSelect.value,
    model: modelSelect.value,
    nsfw: nsfwCheckbox.checked,
    use_custom: customCheckbox.checked,
  };
  try {
    const entry = await callGenerate(payload, formStatus);
    setStatus(formStatus, `完了（${entry.duration_sec}秒） - ヒロイン: ${heroineLabel(entry.heroine)}`, "ok");
    await loadGallery();
  } catch (err) {
    setStatus(formStatus, `エラー: ${err.message}`, "error");
  } finally {
    submitBtn.disabled = false;
  }
});

function renderCard(entry) {
  const img = (entry.image_urls && entry.image_urls[0]) || "";
  const created = entry.created_at ? new Date(entry.created_at).toLocaleString("ja-JP") : "";
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    ${img ? `<img src="${img}" loading="lazy" alt="generated">` : ""}
    <div class="card-body">
      <div class="heroine-name">${escapeHtml(heroineLabel(entry.heroine))}</div>
      <div>post #${entry.post_id} ・ ${escapeHtml(entry.model || "")} ・ ${entry.nsfw ? "NSFW" : "SFW"}${entry.use_custom ? " ・ custom" : ""}</div>
      <div class="prompt" title="クリックで全文表示">${escapeHtml(entry.prompt || "")}</div>
      <div>${created}</div>
      <div class="card-actions">
        <a class="secondary" href="${entry.original_url}" target="_blank" rel="noopener">元投稿</a>
        <button type="button" class="regen-btn">🔁 再生成</button>
      </div>
      <p class="status regen-status"></p>
    </div>
  `;

  const promptEl = card.querySelector(".prompt");
  promptEl.addEventListener("click", () => promptEl.classList.toggle("expanded"));

  const imgEl = card.querySelector("img");
  if (imgEl) imgEl.addEventListener("click", () => openLightbox(img));

  const regenBtn = card.querySelector(".regen-btn");
  const regenStatus = card.querySelector(".regen-status");
  regenBtn.addEventListener("click", async () => {
    regenBtn.disabled = true;
    const payload = {
      url: entry.original_url,
      heroine: entry.heroine,
      model: entry.model,
      nsfw: entry.nsfw,
      include_artist: entry.include_artist,
      use_custom: entry.use_custom,
      checkpoint: entry.checkpoint,
      width: entry.width,
      height: entry.height,
    };
    try {
      const newEntry = await callGenerate(payload, regenStatus);
      setStatus(regenStatus, `再生成完了（${newEntry.duration_sec}秒）`, "ok");
      await loadGallery();
    } catch (err) {
      setStatus(regenStatus, `エラー: ${err.message}`, "error");
    } finally {
      regenBtn.disabled = false;
    }
  });

  return card;
}

async function loadGallery() {
  const res = await fetch(`${API_BASE}/images?limit=100`);
  const entries = await res.json();
  gallery.innerHTML = "";
  if (!entries.length) {
    gallery.innerHTML = `<p class="empty">まだ生成履歴がありません。</p>`;
    return;
  }
  for (const entry of entries) {
    gallery.appendChild(renderCard(entry));
  }
}

reloadBtn.addEventListener("click", loadGallery);

(async function init() {
  await loadHeroines();
  await loadGallery();
})();
