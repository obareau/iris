const DEFAULT_CATEGORIES = [
  { slug: "personnes", label: "Personnes", prompt: "a photo of one or more people" },
  { slug: "paysages", label: "Paysages", prompt: "a photo of a landscape or outdoor scenery" },
  { slug: "animaux", label: "Animaux", prompt: "a photo of an animal" },
  { slug: "objets", label: "Objets_documents_schemas", prompt: "a photo of an object, a document, a screenshot or a technical diagram" },
];
const FALLBACK = { slug: "autre", label: "Autre" };

// ---------- Références DOM ----------
const $ = (id) => document.getElementById(id);
const categoriesEl = $("categories");
const folderEl = $("folder");
const destEl = $("dest");
const analyzeBtn = $("analyzeBtn");
const detailsBtn = $("detailsBtn");
const applyBtn = $("applyBtn");
const undoBtn = $("undoBtn");
const applyStatusEl = $("applyStatus");
const gridEl = $("grid");
const gridEmptyEl = $("gridEmpty");
const countsEl = $("counts");
const filterCatEl = $("filterCat");
const thumbSizeEl = $("thumbSize");

const refineBtn = $("refineBtn");

const gpLabel = $("gpLabel"), gpCount = $("gpCount"), gpFill = $("gpFill");
const analyzeBar = $("analyzeBar"), analyzeCount = $("analyzeCount"), analyzeFill = $("analyzeFill");
const detailsBar = $("detailsBar"), detailsCount = $("detailsCount"), detailsFill = $("detailsFill");
const refineBar = $("refineBar"), refineCount = $("refineCount"), refineFill = $("refineFill");
const analyzeCancelBtn = $("analyzeCancelBtn"), detailsCancelBtn = $("detailsCancelBtn"), refineCancelBtn = $("refineCancelBtn");

function wireCancelBtn(btn, endpoint) {
  btn.addEventListener("click", () => fetch(endpoint, { method: "POST" }));
}
wireCancelBtn(analyzeCancelBtn, "/api/analyze/cancel");
wireCancelBtn(detailsCancelBtn, "/api/extract-details/cancel");
wireCancelBtn(refineCancelBtn, "/api/refine/cancel");

const inspEmpty = $("inspEmpty"), inspBody = $("inspBody");
const inspImg = $("inspImg"), inspName = $("inspName");
const inspCat = $("inspCat"), inspColor = $("inspColor"), inspOrient = $("inspOrient");
const inspDims = $("inspDims"), inspSize = $("inspSize");
const inspConf = $("inspConf"), inspSource = $("inspSource");
const inspDetails = $("inspDetails"), inspNewName = $("inspNewName");
const inspScoresSection = $("inspScoresSection"), inspScores = $("inspScores");
const inspDetectSection = $("inspDetectSection"), inspDetections = $("inspDetections");
const inspAttrSection = $("inspAttrSection"), inspAttrs = $("inspAttrs");

// ---------- État ----------
let currentCategories = DEFAULT_CATEGORIES;
let itemsByPath = new Map();   // path -> item
let order = [];                // ordre d'affichage
let cardByPath = new Map();    // path -> element
let selectedPath = null;
let activeFilter = "";

categoriesEl.value = DEFAULT_CATEGORIES.map(c => `${c.slug} | ${c.label} | ${c.prompt}`).join("\n");

function parseCategories() {
  const lines = categoriesEl.value.split("\n").map(l => l.trim()).filter(Boolean);
  const cats = lines.map(line => {
    const [slug, label, ...rest] = line.split("|").map(s => s.trim());
    return { slug, label: label || slug, prompt: rest.join("|").trim() };
  }).filter(c => c.slug);
  return cats.length ? cats : DEFAULT_CATEGORIES;
}

function allCatsWithFallback() {
  return [...currentCategories, FALLBACK];
}

// ---------- Barres de progression ----------
function setBar(fillEl, done, total) {
  const pct = total ? Math.round((done / total) * 100) : 0;
  fillEl.style.width = pct + "%";
  return pct;
}

function updateGlobal(label, done, total, done_state) {
  gpLabel.textContent = label;
  gpCount.textContent = total ? `${done} / ${total}` : "";
  setBar(gpFill, done, total);
  gpFill.classList.toggle("done", !!done_state);
}

// ---------- Rendu grille ----------
function statusClass(item) {
  if (item.error) return "error";
  if (item.details) return "detailed";
  return "classified";
}

function makeCard(item) {
  const card = document.createElement("div");
  card.className = "thumb";
  card.dataset.path = item.path;

  const imgWrap = document.createElement("div");
  imgWrap.className = "thumb-img";
  const img = document.createElement("img");
  img.loading = "lazy";
  img.src = "/api/thumbnail?path=" + encodeURIComponent(item.path);
  imgWrap.appendChild(img);

  const foot = document.createElement("div");
  foot.className = "thumb-foot";
  const dot = document.createElement("span");
  dot.className = "status-dot";
  const cat = document.createElement("span");
  cat.className = "thumb-cat";
  foot.appendChild(dot);
  foot.appendChild(cat);

  const prog = document.createElement("div");
  prog.className = "thumb-progress";

  card.appendChild(imgWrap);
  card.appendChild(foot);
  card.appendChild(prog);

  card.addEventListener("click", () => selectImage(item.path));
  card.addEventListener("dblclick", () => openLightbox(item.path));
  return card;
}

function updateCard(card, item) {
  const dot = card.querySelector(".status-dot");
  const cat = card.querySelector(".thumb-cat");
  dot.className = "status-dot " + statusClass(item);
  cat.textContent = item.error ? "Erreur" : (item.category_label || "—");
  card.classList.toggle("selected", item.path === selectedPath);
  applyFilterToCard(card, item);
}

function applyFilterToCard(card, item) {
  const show = !activeFilter || item.category_slug === activeFilter;
  card.style.display = show ? "" : "none";
}

function syncGrid() {
  for (const path of order) {
    const item = itemsByPath.get(path);
    let card = cardByPath.get(path);
    if (!card) {
      card = makeCard(item);
      cardByPath.set(path, card);
      gridEl.appendChild(card);
    }
    updateCard(card, item);
  }
  gridEmptyEl.style.display = order.length ? "none" : "";
  updateCounts();
}

function updateCounts() {
  const total = order.length;
  const withDetails = order.filter(p => itemsByPath.get(p).details).length;
  countsEl.textContent = total
    ? `${total} images · ${withDetails} avec détails`
    : "";
}

let lastScrolledPath = null;
function markProcessing(path) {
  for (const [p, card] of cardByPath) {
    card.classList.toggle("processing", p === path);
  }
  // Avance automatique : suit la vignette en cours de traitement.
  if (path && path !== lastScrolledPath) {
    const card = cardByPath.get(path);
    if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
    lastScrolledPath = path;
  }
}
function clearProcessing() {
  for (const card of cardByPath.values()) card.classList.remove("processing");
}

function mergeResults(items) {
  for (const item of items) {
    const existed = itemsByPath.has(item.path);
    itemsByPath.set(item.path, item);
    if (!existed) order.push(item.path);
  }
  syncGrid();
  if (selectedPath && itemsByPath.has(selectedPath)) renderInspector(itemsByPath.get(selectedPath));
}

async function fetchResults() {
  const res = await fetch("/api/results");
  const data = await res.json();
  currentCategories = data.categories;
  rebuildFilterOptions();
  return data.items;
}

// ---------- Filtre & taille ----------
function rebuildFilterOptions() {
  const current = filterCatEl.value;
  filterCatEl.innerHTML = '<option value="">Toutes catégories</option>';
  for (const c of allCatsWithFallback()) {
    const o = document.createElement("option");
    o.value = c.slug; o.textContent = c.label;
    filterCatEl.appendChild(o);
  }
  filterCatEl.value = current;
}
filterCatEl.addEventListener("change", () => {
  activeFilter = filterCatEl.value;
  for (const path of order) applyFilterToCard(cardByPath.get(path), itemsByPath.get(path));
});
thumbSizeEl.addEventListener("input", () => {
  gridEl.style.setProperty("--thumb", thumbSizeEl.value + "px");
});

// ---------- Inspecteur ----------
function selectImage(path) {
  selectedPath = path;
  for (const [p, card] of cardByPath) card.classList.toggle("selected", p === path);
  const item = itemsByPath.get(path);
  if (item) renderInspector(item);
}

function projectedName(item) {
  const ext = "." + (item.path.split(".").pop() || "jpg").toLowerCase();
  const d = item.details_slug ? "_" + item.details_slug : "";
  return `${item.category_slug}_###${d}${ext}`;
}

function humanSize(bytes) {
  if (!bytes) return "—";
  if (bytes < 1024) return bytes + " o";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + " Ko";
  return (bytes / (1024 * 1024)).toFixed(1) + " Mo";
}

function renderInspector(item) {
  inspEmpty.hidden = true;
  inspBody.hidden = false;
  inspImg.src = "/api/thumbnail?path=" + encodeURIComponent(item.path);
  inspName.textContent = item.path.split("/").pop();

  inspCat.innerHTML = "";
  for (const c of allCatsWithFallback()) {
    const o = document.createElement("option");
    o.value = c.slug; o.textContent = c.label;
    if (c.slug === item.category_slug) o.selected = true;
    inspCat.appendChild(o);
  }
  inspColor.textContent = item.color_mode || "—";
  inspOrient.textContent = item.orientation || "—";
  inspDims.textContent = (item.width && item.height) ? `${item.width} × ${item.height}` : "—";
  inspSize.textContent = humanSize(item.filesize);
  inspConf.textContent = item.confidence != null ? Math.round(item.confidence * 100) + "%" : "—";
  inspSource.textContent = item.source === "yolo" ? "⚡ YOLO" : (item.source === "clip" ? "CLIP" : "—");
  inspDetails.textContent = item.details || (item.details_error ? "Erreur d'extraction" : "—");
  inspNewName.textContent = projectedName(item);

  // Scores CLIP (barres)
  if (item.clip_scores && item.clip_scores.length) {
    inspScores.innerHTML = "";
    for (const s of item.clip_scores) {
      const row = document.createElement("div");
      row.className = "kv-row";
      row.innerHTML = `<span class="kv-key">${s.label}</span>`
        + `<span class="kv-bar"><span style="width:${Math.round(s.prob * 100)}%"></span></span>`
        + `<span class="kv-val">${Math.round(s.prob * 100)}%</span>`;
      inspScores.appendChild(row);
    }
    inspScoresSection.hidden = false;
  } else {
    inspScoresSection.hidden = true;
  }

  // Objets YOLO (puces)
  if (item.detections && item.detections.length) {
    inspDetections.innerHTML = "";
    for (const d of item.detections) {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `${d.name}<b>×${d.count}</b>`;
      inspDetections.appendChild(chip);
    }
    inspDetectSection.hidden = false;
  } else {
    inspDetectSection.hidden = true;
  }

  // Attributs passe 3
  if (item.attributes && item.attributes.length) {
    inspAttrs.innerHTML = "";
    for (const a of item.attributes) {
      const row = document.createElement("div");
      row.className = "kv-row";
      row.innerHTML = `<span class="kv-key">${a.label}</span><span class="kv-val">${a.value}</span>`;
      inspAttrs.appendChild(row);
    }
    inspAttrSection.hidden = false;
  } else {
    inspAttrSection.hidden = true;
  }
}

inspCat.addEventListener("change", async () => {
  if (!selectedPath) return;
  const res = await fetch("/api/override", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: selectedPath, category_slug: inspCat.value }),
  });
  if (res.ok) {
    const updated = await res.json();
    itemsByPath.set(selectedPath, updated);
    updateCard(cardByPath.get(selectedPath), updated);
    renderInspector(updated);
    updateCounts();
  }
});

// ---------- Auto-remplissage destination ----------
// Un seul dossier export, quel que soit le dossier source du jour — sinon
// chaque nouvel import (source différente) crée son propre "_classees" à
// côté, et Recta (qui ne lit qu'un chemin fixe) n'en voit qu'un sur N.
const CANONICAL_EXPORT_DIR = "/home/olivier/renegats-photos/_classees";
folderEl.addEventListener("change", () => {
  if (!destEl.value) {
    destEl.value = CANONICAL_EXPORT_DIR;
  }
});

// ---------- Analyse (passe 1) ----------
analyzeBtn.addEventListener("click", async () => {
  const folder = folderEl.value.trim();
  if (!folder) { alert("Indique un dossier source."); return; }
  currentCategories = parseCategories();
  rebuildFilterOptions();

  // reset grille
  itemsByPath.clear(); order = []; cardByPath.clear();
  gridEl.innerHTML = ""; selectedPath = null;
  inspBody.hidden = true; inspEmpty.hidden = false;
  applyBtn.disabled = true; detailsBtn.disabled = true; refineBtn.disabled = true;
  lastScrolledPath = null;

  analyzeBtn.disabled = true;
  analyzeBar.classList.add("active");
  setBar(analyzeFill, 0, 1); analyzeFill.classList.remove("done");

  const res = await fetch("/api/analyze", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder, categories: currentCategories }),
  });
  if (!res.ok) {
    updateGlobal("Erreur: " + (await res.text()), 0, 0);
    analyzeBtn.disabled = false;
    return;
  }
  pollAnalyze();
});

async function pollAnalyze() {
  const [pRes, items] = await Promise.all([
    fetch("/api/progress").then(r => r.json()),
    fetchResults(),
  ]);
  mergeResults(items);

  const phase = pRes.phase === "clip" ? "CLIP" : "YOLO";
  updateGlobal(`Analyse (${phase})`, pRes.done, pRes.total);
  analyzeCount.textContent = `${pRes.done} / ${pRes.total}`;
  setBar(analyzeFill, pRes.done, pRes.total);
  markProcessing(pRes.current);
  analyzeCancelBtn.hidden = pRes.status !== "running";

  if (pRes.status === "running") {
    setTimeout(pollAnalyze, 600);
  } else {
    clearProcessing();
    analyzeFill.classList.add("done");
    updateGlobal(pRes.status === "cancelled" ? "Analyse annulée" : "Analyse terminée", pRes.total, pRes.total, true);
    analyzeBtn.disabled = false;
    detailsBtn.disabled = order.length === 0;
    refineBtn.disabled = order.length === 0;
    applyBtn.disabled = order.length === 0;
  }
}

// ---------- Détails (passe 2) ----------
detailsBtn.addEventListener("click", async () => {
  detailsBtn.disabled = true;
  detailsBar.classList.add("active");
  setBar(detailsFill, 0, 1); detailsFill.classList.remove("done");
  lastScrolledPath = null;

  const res = await fetch("/api/extract-details", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    applyStatusEl.textContent = "Détails: " + (await res.text());
    detailsBtn.disabled = false;
    return;
  }
  pollDetails();
});

async function pollDetails() {
  const [pRes, items] = await Promise.all([
    fetch("/api/details-progress").then(r => r.json()),
    fetchResults(),
  ]);
  mergeResults(items);

  updateGlobal("Extraction des détails", pRes.done, pRes.total);
  detailsCount.textContent = `${pRes.done} / ${pRes.total}`;
  setBar(detailsFill, pRes.done, pRes.total);
  markProcessing(pRes.current);
  detailsCancelBtn.hidden = pRes.status !== "running";

  if (pRes.status === "running") {
    setTimeout(pollDetails, 700);
  } else {
    clearProcessing();
    detailsFill.classList.add("done");
    updateGlobal(pRes.status === "cancelled" ? "Détails annulés" : "Détails terminés", pRes.total, pRes.total, true);
    detailsBtn.disabled = false;
  }
}

// ---------- Affinage (passe 3) ----------
refineBtn.addEventListener("click", async () => {
  refineBtn.disabled = true;
  refineBar.classList.add("active");
  setBar(refineFill, 0, 1); refineFill.classList.remove("done");
  lastScrolledPath = null;

  const res = await fetch("/api/refine", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    applyStatusEl.textContent = "Affinage: " + (await res.text());
    refineBtn.disabled = false;
    return;
  }
  pollRefine();
});

async function pollRefine() {
  const [pRes, items] = await Promise.all([
    fetch("/api/refine-progress").then(r => r.json()),
    fetchResults(),
  ]);
  mergeResults(items);

  updateGlobal("Affinage des attributs", pRes.done, pRes.total);
  refineCount.textContent = `${pRes.done} / ${pRes.total}`;
  setBar(refineFill, pRes.done, pRes.total);
  markProcessing(pRes.current);
  refineCancelBtn.hidden = pRes.status !== "running";

  if (pRes.status === "running") {
    setTimeout(pollRefine, 700);
  } else {
    clearProcessing();
    refineFill.classList.add("done");
    updateGlobal(pRes.status === "cancelled" ? "Attributs annulés" : "Attributs affinés", pRes.total, pRes.total, true);
    refineBtn.disabled = false;
  }
}

// ---------- Application / annulation ----------
applyBtn.addEventListener("click", async () => {
  const dest = destEl.value.trim();
  if (!dest) { alert("Indique un dossier de destination."); return; }
  if (!confirm(`Déplacer et renommer ${order.length} images vers ${dest} ?`)) return;

  applyBtn.disabled = true;
  applyStatusEl.textContent = "Application en cours...";
  const res = await fetch("/api/apply", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dest_root: dest }),
  });
  const data = await res.json();
  applyStatusEl.textContent = `${data.moved} images déplacées`
    + (data.errors?.length ? ` · ${data.errors.length} erreurs` : "");

  // vider la grille (les fichiers ont bougé)
  itemsByPath.clear(); order = []; cardByPath.clear();
  gridEl.innerHTML = ""; selectedPath = null;
  inspBody.hidden = true; inspEmpty.hidden = false;
  syncGrid();
  updateGlobal("Prêt", 0, 0);
});

undoBtn.addEventListener("click", async () => {
  if (!confirm("Annuler la dernière application de tri ?")) return;
  const res = await fetch("/api/undo", { method: "POST" });
  const data = await res.json();
  applyStatusEl.textContent = data.message || `${data.undone} images restaurées`;
});

// ---------- Modale navigation dossiers ----------
const browseModal = $("browseModal");
const browsePathEl = $("browsePath");
const browseListEl = $("browseList");
let browseTargetInput = null, browseCurrentPath = null, browseParentPath = null;

async function browseLoad(path) {
  const url = path ? `/api/browse?path=${encodeURIComponent(path)}` : "/api/browse";
  const res = await fetch(url);
  if (!res.ok) {
    browseListEl.innerHTML = `<div class="browse-empty">${await res.text()}</div>`;
    return;
  }
  const data = await res.json();
  browseCurrentPath = data.path;
  browseParentPath = data.parent;
  browsePathEl.value = data.path;
  browseListEl.innerHTML = "";
  if (!data.entries.length) {
    browseListEl.innerHTML = '<div class="browse-empty">Aucun sous-dossier</div>';
    return;
  }
  for (const entry of data.entries) {
    const div = document.createElement("div");
    div.className = "browse-item";
    div.textContent = "📁 " + entry.name;
    div.addEventListener("click", () => browseLoad(entry.path));
    browseListEl.appendChild(div);
  }
}

document.querySelectorAll("[data-browse-target]").forEach(btn => {
  btn.addEventListener("click", () => {
    browseTargetInput = $(btn.dataset.browseTarget);
    browseModal.hidden = false;
    browseLoad(browseTargetInput.value || null);
  });
});
$("browseGo").addEventListener("click", () => browseLoad(browsePathEl.value));
browsePathEl.addEventListener("keydown", (e) => { if (e.key === "Enter") browseLoad(browsePathEl.value); });
$("browseUp").addEventListener("click", () => { if (browseParentPath) browseLoad(browseParentPath); });
$("browseSelect").addEventListener("click", () => {
  if (browseTargetInput && browseCurrentPath) {
    browseTargetInput.value = browseCurrentPath;
    browseTargetInput.dispatchEvent(new Event("change"));
  }
  browseModal.hidden = true;
});
$("browseClose").addEventListener("click", () => { browseModal.hidden = true; });

// ---------- Lightbox (image en grand, double-clic) ----------
const lightboxModal = $("lightboxModal");
const lightboxImg = $("lightboxImg");
function openLightbox(path) {
  lightboxImg.src = "/api/image?path=" + encodeURIComponent(path);
  lightboxModal.hidden = false;
}
function closeLightbox() { lightboxModal.hidden = true; lightboxImg.src = ""; }
$("lightboxClose").addEventListener("click", closeLightbox);
lightboxModal.addEventListener("click", (e) => { if (e.target === lightboxModal) closeLightbox(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !lightboxModal.hidden) closeLightbox(); });

// ---------- Onglets Tri / Galerie ----------
const views = { tri: $("view-tri"), galerie: $("view-galerie"), doublons: $("view-doublons"), graphe: $("view-graphe"), recta: $("view-recta") };
views.galerie.style.display = "none"; // état initial : onglet Tri actif (le hidden HTML seul ne suffit pas, cf. commentaire ci-dessous)
views.doublons.style.display = "none";
views.graphe.style.display = "none";
views.recta.style.display = "none";
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b === btn));
    // `.workspace{display:grid}` a la même spécificité que `[hidden]` de la
    // feuille UA et gagne (règle auteur après règle UA) — piloter `display`
    // directement plutôt que l'attribut hidden qui n'aurait aucun effet ici.
    for (const [name, el] of Object.entries(views)) {
      el.style.display = name === btn.dataset.tab ? "grid" : "none";
    }
  });
});

// ---------- Galerie ----------
const galFolderEl = $("galFolder");
const galLoadBtn = $("galLoadBtn");
const galFilterCatEl = $("galFilterCat");
const galSearchEl = $("galSearch");
const galCountsEl = $("galCounts");
const galGridEl = $("galGrid");
const galEmptyEl = $("galEmpty");
const galInspEmpty = $("galInspEmpty"), galInspBody = $("galInspBody");
const galInspImg = $("galInspImg"), galInspName = $("galInspName"), galInspCat = $("galInspCat");
const galInspDetails = $("galInspDetails");
const galInspAttrSection = $("galInspAttrSection"), galInspAttrs = $("galInspAttrs");
const galPostedStatus = $("galPostedStatus");
const galRenegatBtn = $("galRenegatBtn");
const galDeleteBtn = $("galDeleteBtn");
const galBackfillBtn = $("galBackfillBtn");
const galBackfillBar = $("galBackfillBar"), galBackfillCount = $("galBackfillCount"), galBackfillFill = $("galBackfillFill");
const galBackfillCancelBtn = $("galBackfillCancelBtn");
wireCancelBtn(galBackfillCancelBtn, "/api/gallery/backfill/cancel");

let galItems = [];          // liste brute renvoyée par /api/gallery
let galItemsByPath = new Map();
let galCardByPath = new Map();
let galSelectedPath = null;
let galActiveCat = "";

// La galerie retient le dernier dossier chargé avec succès (localStorage) —
// pré-rempli au chargement de la page, avant même tout clic. À défaut, se
// rabat sur le dossier destination du tri au premier focus.
const GAL_FOLDER_STORAGE_KEY = "iris.galFolder";
const galLastFolder = localStorage.getItem(GAL_FOLDER_STORAGE_KEY);
if (galLastFolder) galFolderEl.value = galLastFolder;

galFolderEl.addEventListener("focus", () => {
  if (!galFolderEl.value && destEl.value) galFolderEl.value = destEl.value;
}, { once: true });

function galMatchesSearch(item, needle) {
  if (!needle) return true;
  const haystack = [
    item.path.split("/").pop(),
    item.category_label,
    item.details,
    ...(item.attributes || []).map(a => `${a.label} ${a.value}`),
  ].filter(Boolean).join(" ").toLowerCase();
  return haystack.includes(needle);
}

// Filtres d'attributs actifs (passe 3) — combinés en ET avec la catégorie et
// la recherche texte. Chaque filtre = {label, value} exact (choisi dans un
// menu déroulant peuplé depuis les valeurs réellement présentes).
let galAttrFilters = [];

function galMatchesAttrFilters(item) {
  if (!galAttrFilters.length) return true;
  return galAttrFilters.every(f =>
    (item.attributes || []).some(a => a.label === f.label && a.value === f.value)
  );
}

function galApplyFilters() {
  const needle = galSearchEl.value.trim().toLowerCase();
  let shown = 0;
  for (const item of galItems) {
    const card = galCardByPath.get(item.path);
    const catOk = !galActiveCat || item.category_label === galActiveCat;
    const searchOk = galMatchesSearch(item, needle);
    const attrOk = galMatchesAttrFilters(item);
    const show = catOk && searchOk && attrOk;
    card.style.display = show ? "" : "none";
    if (show) shown++;
  }
  galCountsEl.textContent = `${shown} / ${galItems.length} images`;
}

function galMakeCard(item) {
  const card = document.createElement("div");
  card.className = "thumb";
  card.dataset.path = item.path;

  const imgWrap = document.createElement("div");
  imgWrap.className = "thumb-img";
  const img = document.createElement("img");
  img.loading = "lazy";
  img.src = "/api/thumbnail?path=" + encodeURIComponent(item.path);
  imgWrap.appendChild(img);

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "thumb-select";
  checkbox.addEventListener("click", (e) => {
    e.stopPropagation();
    galToggleSelect(item.path, checkbox.checked);
  });
  imgWrap.appendChild(checkbox);

  const foot = document.createElement("div");
  foot.className = "thumb-foot";
  const dot = document.createElement("span");
  dot.className = "status-dot" + (item.renegat_posted ? " detailed" : " classified");
  const cat = document.createElement("span");
  cat.className = "thumb-cat";
  cat.textContent = (item.renegat_posted
    ? `${item.category_label} · 📡 #${item.renegat_posted.numero}`
    : item.category_label)
    + (item.score != null ? ` · ${Math.round(item.score * 100)}%` : "");
  foot.appendChild(dot);
  foot.appendChild(cat);

  card.appendChild(imgWrap);
  card.appendChild(foot);

  // Attributs passe 3 visibles sans avoir à cliquer chaque vignette — ligne
  // compacte (valeurs seules) + tooltip natif avec le détail label:valeur.
  if (item.attributes && item.attributes.length) {
    const attrsLine = document.createElement("div");
    attrsLine.className = "thumb-attrs";
    attrsLine.textContent = item.attributes.map(a => a.value).join(" · ");
    card.title = item.attributes.map(a => `${a.label} : ${a.value}`).join("\n");
    card.appendChild(attrsLine);
  }

  card.addEventListener("click", () => galSelectImage(item.path));
  card.addEventListener("dblclick", () => openLightbox(item.path));
  return card;
}

function galRenderInspector(item) {
  galInspEmpty.hidden = true;
  galInspBody.hidden = false;
  galInspImg.src = "/api/thumbnail?path=" + encodeURIComponent(item.path);
  galInspName.textContent = item.path.split("/").pop();
  galInspCat.textContent = item.category_label || "—";
  galInspDetails.textContent = item.details || "—";

  if (item.attributes && item.attributes.length) {
    galInspAttrs.innerHTML = "";
    for (const a of item.attributes) {
      const row = document.createElement("div");
      row.className = "kv-row";
      row.innerHTML = `<span class="kv-key">${a.label}</span><span class="kv-val">${a.value}</span>`;
      galInspAttrs.appendChild(row);
    }
    galInspAttrSection.hidden = false;
  } else {
    galInspAttrSection.hidden = true;
  }

  if (item.renegat_posted) {
    const d = new Date(item.renegat_posted.timestamp);
    galPostedStatus.textContent = `📡 Déjà publié — avis #${item.renegat_posted.numero} le ${d.toLocaleString()}`;
    galRenegatBtn.textContent = "Republier quand même";
  } else {
    galPostedStatus.textContent = "";
    galRenegatBtn.textContent = "Publier en Renegat";
  }

  galRenderStars(item.rating || 0);
}

// ---------- Notation étoiles ----------
const galStarsEl = $("galStars");
function galRenderStars(rating) {
  galStarsEl.querySelectorAll("span").forEach(s => {
    s.classList.toggle("filled", parseInt(s.dataset.star, 10) <= rating);
  });
}
galStarsEl.querySelectorAll("span").forEach(s => {
  s.addEventListener("click", async () => {
    if (!galSelectedPath) return;
    const rating = parseInt(s.dataset.star, 10);
    // Cliquer l'étoile déjà au sommet de la note actuelle la remet à zéro
    // (sinon impossible de redescendre à "pas de note" une fois notée).
    const item = galItemsByPath.get(galSelectedPath);
    const newRating = (item.rating === rating) ? 0 : rating;
    galRenderStars(newRating); // retour visuel immédiat
    const res = await fetch("/api/gallery/rating", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: galSelectedPath, rating: newRating }),
    });
    if (res.ok) {
      item.rating = newRating;
    } else {
      galRenderStars(item.rating || 0); // annule l'affichage si l'écriture a échoué
    }
  });
});

function galSelectImage(path) {
  galSelectedPath = path;
  for (const [p, card] of galCardByPath) card.classList.toggle("selected", p === path);
  const item = galItemsByPath.get(path);
  if (item) galRenderInspector(item);
}

async function galLoad() {
  const folder = galFolderEl.value.trim();
  if (!folder) { alert("Indique un dossier déjà classé (ex: .../_classees)."); return; }
  galLoadBtn.disabled = true;
  galCountsEl.textContent = "Chargement…";
  try {
    const res = await fetch("/api/gallery?folder=" + encodeURIComponent(folder));
    if (!res.ok) { galCountsEl.textContent = "Erreur: " + (await res.text()); return; }
    localStorage.setItem(GAL_FOLDER_STORAGE_KEY, folder);
    const data = await res.json();
    galItems = data.items;
    galItemsByPath = new Map(galItems.map(i => [i.path, i]));
    galCardByPath = new Map();
    galGridEl.innerHTML = "";
    galSelectedPath = null;
    galSelectedPaths = new Set();
    galUpdateBulkBar();
    galInspBody.hidden = true; galInspEmpty.hidden = false;

    const cats = [...new Set(galItems.map(i => i.category_label).filter(Boolean))].sort();
    galFilterCatEl.innerHTML = '<option value="">Toutes catégories</option>'
      + cats.map(c => `<option value="${c}">${c}</option>`).join("");
    galActiveCat = "";
    galAttrFilters = [];
    galRebuildAttrLabelOptions();
    galRenderAttrChips();

    for (const item of galItems) {
      const card = galMakeCard(item);
      galCardByPath.set(item.path, card);
      galGridEl.appendChild(card);
    }
    galEmptyEl.style.display = galItems.length ? "none" : "";
    galApplyFilters();
  } finally {
    galLoadBtn.disabled = false;
  }
}
galLoadBtn.addEventListener("click", galLoad);

// ---------- Filtres par attribut structuré (passe 3) ----------
const galAttrLabelEl = $("galAttrLabel");
const galAttrValueEl = $("galAttrValue");
const galAttrAddBtn = $("galAttrAddBtn");
const galAttrChipsEl = $("galAttrChips");

function galRebuildAttrLabelOptions() {
  const labels = [...new Set(
    galItems.flatMap(i => (i.attributes || []).map(a => a.label))
  )].sort();
  galAttrLabelEl.innerHTML = labels.map(l => `<option value="${l}">${l}</option>`).join("");
  galRebuildAttrValueOptions();
}

function galRebuildAttrValueOptions() {
  const label = galAttrLabelEl.value;
  const values = [...new Set(
    galItems.flatMap(i => (i.attributes || []).filter(a => a.label === label).map(a => a.value))
  )].sort();
  galAttrValueEl.innerHTML = values.map(v => `<option value="${v}">${v}</option>`).join("");
}
galAttrLabelEl.addEventListener("change", galRebuildAttrValueOptions);

function galRenderAttrChips() {
  galAttrChipsEl.innerHTML = "";
  galAttrFilters.forEach((f, idx) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.innerHTML = `${f.label} : <b>${f.value}</b> ✕`;
    chip.style.cursor = "pointer";
    chip.title = "Retirer ce filtre";
    chip.addEventListener("click", () => {
      galAttrFilters.splice(idx, 1);
      galRenderAttrChips();
      galApplyFilters();
    });
    galAttrChipsEl.appendChild(chip);
  });
}

galAttrAddBtn.addEventListener("click", () => {
  const label = galAttrLabelEl.value;
  const value = galAttrValueEl.value;
  if (!label || !value) return;
  if (galAttrFilters.some(f => f.label === label && f.value === value)) return; // déjà présent
  galAttrFilters.push({ label, value });
  galRenderAttrChips();
  galApplyFilters();
});
galFilterCatEl.addEventListener("change", () => { galActiveCat = galFilterCatEl.value; galApplyFilters(); });
galSearchEl.addEventListener("input", () => galApplyFilters());

// ---------- Recherche sémantique (CLIP texte→image, via /api/gallery/search) ----------
// Distincte du filtre texte ci-dessus (sous-chaîne locale, instantanée) :
// celle-ci interroge Iris, réordonne la grille par score et l'affiche.
const galSemanticBtn = $("galSemanticBtn");
function galRenderSemanticResults(items, query) {
  galGridEl.innerHTML = "";
  galCardByPath = new Map();
  for (const item of items) {
    galItemsByPath.set(item.path, item); // complète l'entrée avec le score
    const card = galMakeCard(item);
    galCardByPath.set(item.path, card);
    galGridEl.appendChild(card);
  }
  galEmptyEl.style.display = items.length ? "none" : "";
  galCountsEl.textContent = items.length
    ? `${items.length} résultats pour « ${query} » (recherche IA — % = similarité)`
    : `Aucun résultat pour « ${query} »`;
}

galSemanticBtn.addEventListener("click", async () => {
  const folder = galFolderEl.value.trim();
  const query = galSearchEl.value.trim();
  if (!folder) { alert("Charge d'abord un dossier."); return; }
  if (!query) { alert("Tape une description dans le champ recherche."); return; }
  galSemanticBtn.disabled = true;
  galCountsEl.textContent = "Recherche sémantique en cours…";
  try {
    const res = await fetch("/api/gallery/search", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folder, query, category: galActiveCat || null, top_k: 30 }),
    });
    if (!res.ok) { galCountsEl.textContent = "Erreur : " + (await res.text()); return; }
    const data = await res.json();
    galRenderSemanticResults(data.items, query);
  } finally {
    galSemanticBtn.disabled = false;
  }
});

// ---------- Rétro-remplissage des détails (photos triées avant les sidecars) ----------
function galVisiblePaths() {
  // Respecte le filtre catégorie + recherche actif — cohérent avec ce que
  // l'utilisateur voit à l'écran, pas la totalité du dossier.
  return galItems
    .filter(item => galCardByPath.get(item.path).style.display !== "none")
    .map(item => item.path);
}

async function galBackfillPoll() {
  const pRes = await fetch("/api/gallery/backfill-progress").then(r => r.json());
  galBackfillCount.textContent = pRes.total ? `${pRes.done} / ${pRes.total}` : "—";
  setBar(galBackfillFill, pRes.done, pRes.total);
  galBackfillCancelBtn.hidden = pRes.status !== "running";

  if (pRes.status === "running") {
    setTimeout(galBackfillPoll, 700);
    return;
  }
  galBackfillBtn.disabled = false;
  if (pRes.status === "error") {
    galBackfillCount.textContent = "Erreur";
    return;
  }
  if (pRes.status === "cancelled") galBackfillCount.textContent += " (annulé)";
  galBackfillFill.classList.add("done");
  await galLoad(); // recharge pour afficher les nouveaux détails/attributs
}

galBackfillBtn.addEventListener("click", async () => {
  const folder = galFolderEl.value.trim();
  if (!folder) { alert("Charge d'abord un dossier."); return; }
  const visible = galVisiblePaths();
  const missing = visible.filter(p => !galItemsByPath.get(p).details);
  if (!missing.length) { galBackfillCount.textContent = "Rien à compléter (vue actuelle)"; return; }
  if (!confirm(`Extraire détails + attributs pour ${missing.length} photo(s) sans sidecar ?`)) return;

  galBackfillBtn.disabled = true;
  galBackfillFill.classList.remove("done");
  setBar(galBackfillFill, 0, 1);
  const res = await fetch("/api/gallery/backfill", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder, paths: missing }),
  });
  if (!res.ok) {
    galBackfillCount.textContent = "Erreur : " + (await res.text());
    galBackfillBtn.disabled = false;
    return;
  }
  galBackfillPoll();
});

// ---------- Publication Renegat (aperçu → confirmation) ----------
const renegatModal = $("renegatModal");
const renegatPreviewImg = $("renegatPreviewImg");
const renegatCaption = $("renegatCaption");
const renegatStatus = $("renegatStatus");
const renegatConfirm = $("renegatConfirm");
let renegatPreviewData = null; // {numero, lang, caption, imagePath}

function renegatCloseModal() {
  renegatModal.hidden = true;
  renegatPreviewData = null;
  renegatStatus.textContent = "";
  renegatConfirm.disabled = false;
  renegatConfirm.textContent = "Confirmer la publication";
}
$("renegatClose").addEventListener("click", renegatCloseModal);
$("renegatCancel").addEventListener("click", renegatCloseModal);

galRenegatBtn.addEventListener("click", async () => {
  if (!galSelectedPath) return;
  renegatModal.hidden = false;
  renegatPreviewImg.src = "/api/thumbnail?path=" + encodeURIComponent(galSelectedPath);
  renegatCaption.textContent = "Génération de l'aperçu…";
  renegatStatus.textContent = "";
  renegatConfirm.disabled = true;
  try {
    const res = await fetch("/api/recta/renegat/preview", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image_path: galSelectedPath }),
    });
    const data = await res.json();
    if (!res.ok) { renegatCaption.textContent = "Erreur : " + (data.detail || res.statusText); return; }
    renegatPreviewData = data;
    renegatCaption.textContent = `#${data.numero} (${data.lang})\n\n${data.caption}`;
    renegatConfirm.disabled = false;
  } catch (e) {
    renegatCaption.textContent = "Erreur : " + e.message;
  }
});

renegatConfirm.addEventListener("click", async () => {
  if (!renegatPreviewData) return;
  renegatConfirm.disabled = true;
  renegatConfirm.textContent = "Publication…";
  renegatStatus.textContent = "Publication en cours sur Facebook / Bluesky / Mastodon…";
  try {
    const res = await fetch("/api/recta/renegat/publish", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        image_path: renegatPreviewData.imagePath,
        numero: renegatPreviewData.numero,
        lang: renegatPreviewData.lang,
      }),
    });
    const data = await res.json();
    if (!res.ok) { renegatStatus.textContent = "Échec : " + (data.detail || res.statusText); renegatConfirm.disabled = false; renegatConfirm.textContent = "Réessayer"; return; }
    const summary = (data.results || []).map(r => `${r.ok ? "✓" : "✗"} ${r.network}${r.error ? " (" + r.error + ")" : ""}`).join(" · ");
    renegatStatus.textContent = data.posted ? `Publié — ${summary}` : `Aucun réseau n'a accepté — ${summary}`;
    renegatConfirm.textContent = "Publié";
    // Recharger la galerie pour faire apparaître le marqueur "déjà publié".
    if (data.posted) galLoad();
  } catch (e) {
    renegatStatus.textContent = "Erreur : " + e.message;
    renegatConfirm.disabled = false;
    renegatConfirm.textContent = "Réessayer";
  }
});

galDeleteBtn.addEventListener("click", async () => {
  if (!galSelectedPath) return;
  const name = galSelectedPath.split("/").pop();
  if (!confirm(`Supprimer définitivement de la galerie "${name}" ?\n(déplacée vers ~/.iris-trash, pas effacée pour de bon)`)) return;
  galDeleteBtn.disabled = true;
  try {
    const res = await fetch("/api/dedupe/discard", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: galSelectedPath }),
    });
    if (!res.ok) { alert("Erreur : " + (await res.text())); return; }
    // Retire la carte + l'entrée locale sans recharger toute la galerie.
    galCardByPath.get(galSelectedPath)?.remove();
    galCardByPath.delete(galSelectedPath);
    galItemsByPath.delete(galSelectedPath);
    galItems = galItems.filter(i => i.path !== galSelectedPath);
    galSelectedPath = null;
    galInspBody.hidden = true; galInspEmpty.hidden = false;
    galApplyFilters();
  } finally {
    galDeleteBtn.disabled = false;
  }
});

// ---------- Sélection multiple (utile sur un gros lot fraîchement importé) ----------
const galBulkBar = $("galBulkBar");
const galBulkCount = $("galBulkCount");
const galBulkClearBtn = $("galBulkClearBtn");
const galBulkStars = $("galBulkStars");
const galBulkDeleteBtn = $("galBulkDeleteBtn");
const galBulkRefineBtn = $("galBulkRefineBtn");
const galBulkRefineCancelBtn = $("galBulkRefineCancelBtn");
wireCancelBtn(galBulkRefineCancelBtn, "/api/gallery/refine/cancel");
const galSelectAllBtn = $("galSelectAllBtn");

let galSelectedPaths = new Set();

function galUpdateBulkBar() {
  const n = galSelectedPaths.size;
  // `.grid-toolbar{display:flex}` bat [hidden] en spécificité égale (déjà
  // rencontré pour le switch d'onglets) — piloter display directement.
  galBulkBar.style.display = n === 0 ? "none" : "flex";
  galBulkCount.textContent = n ? `${n} sélectionnée${n > 1 ? "s" : ""}` : "";
}
galUpdateBulkBar(); // état initial correct dès le chargement du script

function galToggleSelect(path, checked) {
  if (checked) galSelectedPaths.add(path);
  else galSelectedPaths.delete(path);
  galUpdateBulkBar();
}

function galClearSelection() {
  for (const path of galSelectedPaths) {
    const card = galCardByPath.get(path);
    const cb = card?.querySelector(".thumb-select");
    if (cb) cb.checked = false;
  }
  galSelectedPaths.clear();
  galUpdateBulkBar();
}
galBulkClearBtn.addEventListener("click", galClearSelection);

galSelectAllBtn.addEventListener("click", () => {
  for (const item of galItems) {
    const card = galCardByPath.get(item.path);
    if (card.style.display === "none") continue; // respecte le filtre affiché
    const cb = card.querySelector(".thumb-select");
    if (cb && !cb.checked) { cb.checked = true; galSelectedPaths.add(item.path); }
  }
  galUpdateBulkBar();
});

galBulkStars.querySelectorAll("span").forEach(s => {
  s.addEventListener("click", async () => {
    const rating = parseInt(s.dataset.star, 10);
    const paths = [...galSelectedPaths];
    if (!paths.length) return;
    galBulkStars.style.pointerEvents = "none";
    try {
      await Promise.all(paths.map(path =>
        fetch("/api/gallery/rating", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path, rating }),
        }).then(res => { if (res.ok) galItemsByPath.get(path).rating = rating; })
      ));
      if (galSelectedPath && paths.includes(galSelectedPath)) {
        galRenderInspector(galItemsByPath.get(galSelectedPath));
      }
    } finally {
      galBulkStars.style.pointerEvents = "";
    }
  });
});

galBulkDeleteBtn.addEventListener("click", async () => {
  const paths = [...galSelectedPaths];
  if (!paths.length) return;
  if (!confirm(`Déplacer ${paths.length} photo(s) vers la corbeille (~/.iris-trash) ?`)) return;
  galBulkDeleteBtn.disabled = true;
  try {
    const results = await Promise.all(paths.map(path =>
      fetch("/api/dedupe/discard", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      }).then(res => ({ path, ok: res.ok }))
    ));
    for (const { path, ok } of results) {
      if (!ok) continue;
      galCardByPath.get(path)?.remove();
      galCardByPath.delete(path);
      galItemsByPath.delete(path);
      galSelectedPaths.delete(path);
    }
    galItems = galItems.filter(i => galItemsByPath.has(i.path));
    if (galSelectedPath && !galItemsByPath.has(galSelectedPath)) {
      galSelectedPath = null;
      galInspBody.hidden = true; galInspEmpty.hidden = false;
    }
    const failed = results.filter(r => !r.ok).length;
    if (failed) alert(`${failed} suppression(s) ont échoué.`);
    galUpdateBulkBar();
    galApplyFilters();
  } finally {
    galBulkDeleteBtn.disabled = false;
  }
});

async function galRefinePoll() {
  const pRes = await fetch("/api/gallery/refine-progress").then(r => r.json());
  galBulkRefineBtn.textContent = pRes.total
    ? `Réaffinage… ${pRes.done} / ${pRes.total}`
    : "Réaffinage…";
  galBulkRefineCancelBtn.hidden = pRes.status !== "running";
  if (pRes.status === "running") { setTimeout(galRefinePoll, 700); return; }
  galBulkRefineBtn.disabled = false;
  galBulkRefineBtn.textContent = "Réaffiner les attributs (passe 3)";
  if (pRes.status === "error") { alert("Erreur : " + pRes.current); return; }
  // Recharge les attributs à jour pour les photos concernées sans tout recharger.
  const paths = [...galSelectedPaths];
  const items = await Promise.all(paths.map(p =>
    fetch("/api/gallery/item?path=" + encodeURIComponent(p)).then(r => r.ok ? r.json() : null)
  ));
  for (const it of items) {
    if (!it) continue;
    Object.assign(galItemsByPath.get(it.path), it);
  }
  if (galSelectedPath && paths.includes(galSelectedPath)) {
    galRenderInspector(galItemsByPath.get(galSelectedPath));
  }
  // Remplace les cartes affectées pour rafraîchir la ligne d'attributs visible.
  for (const path of paths) {
    const old = galCardByPath.get(path);
    if (!old) continue;
    const fresh = galMakeCard(galItemsByPath.get(path));
    fresh.querySelector(".thumb-select").checked = true;
    old.replaceWith(fresh);
    galCardByPath.set(path, fresh);
  }
}

galBulkRefineBtn.addEventListener("click", async () => {
  const paths = [...galSelectedPaths];
  if (!paths.length) return;
  if (!confirm(`Relancer la passe 3 (attributs) sur ${paths.length} photo(s) — écrase leurs attributs actuels ?`)) return;
  galBulkRefineBtn.disabled = true;
  galBulkRefineBtn.textContent = "Réaffinage…";
  const res = await fetch("/api/gallery/refine", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder: galFolderEl.value.trim(), paths }),
  });
  if (!res.ok) {
    alert("Erreur : " + (await res.text()));
    galBulkRefineBtn.disabled = false;
    galBulkRefineBtn.textContent = "Réaffiner les attributs (passe 3)";
    return;
  }
  galRefinePoll();
});

// ---------- Doublons / images similaires ----------
const dedupeFolderEl = $("dedupeFolder");
const dedupeFilterCatEl = $("dedupeFilterCat");
const dedupeThresholdEl = $("dedupeThreshold");
const dedupeThresholdVal = $("dedupeThresholdVal");
const dedupeBtn = $("dedupeBtn");
const dedupeBar = $("dedupeBar"), dedupePhase = $("dedupePhase"), dedupeCount = $("dedupeCount"), dedupeFill = $("dedupeFill");
const dedupeCancelBtn = $("dedupeCancelBtn");
wireCancelBtn(dedupeCancelBtn, "/api/dedupe/cancel");
const dedupeSummary = $("dedupeSummary");
const dedupeGroupsEl = $("dedupeGroups");
const dedupeEmptyEl = $("dedupeEmpty");

dedupeThresholdEl.addEventListener("input", () => {
  dedupeThresholdVal.textContent = (dedupeThresholdEl.value / 100).toFixed(2);
});

dedupeFolderEl.value = localStorage.getItem(GAL_FOLDER_STORAGE_KEY) || CANONICAL_EXPORT_DIR;

// Peuple le filtre catégorie dès que le dossier est saisi — lecture seule
// des sidecars/dossiers, aucun calcul de modèle (rapide, pas besoin d'un
// bouton dédié).
async function dedupeRefreshCategories() {
  const folder = dedupeFolderEl.value.trim();
  if (!folder) return;
  try {
    const res = await fetch("/api/gallery?folder=" + encodeURIComponent(folder));
    if (!res.ok) return;
    const data = await res.json();
    const current = dedupeFilterCatEl.value;
    const cats = [...new Set(data.items.map(i => i.category_label).filter(Boolean))].sort();
    dedupeFilterCatEl.innerHTML = '<option value="">Toutes catégories</option>'
      + cats.map(c => `<option value="${c}">${c}</option>`).join("");
    dedupeFilterCatEl.value = current;
  } catch (e) { /* silencieux : la détection tournera sans filtre pré-rempli */ }
}
dedupeFolderEl.addEventListener("blur", dedupeRefreshCategories);

function dedupeMakeThumb(path) {
  const thumb = document.createElement("div");
  thumb.className = "dedupe-thumb";
  thumb.dataset.path = path;

  const imgWrap = document.createElement("div");
  imgWrap.className = "dedupe-thumb-img";
  const img = document.createElement("img");
  img.loading = "lazy";
  img.src = "/api/thumbnail?path=" + encodeURIComponent(path);
  imgWrap.appendChild(img);

  const name = document.createElement("div");
  name.className = "dedupe-thumb-name";
  name.textContent = path.split("/").pop();

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn ghost";
  btn.textContent = "Écarter";
  btn.addEventListener("click", async () => {
    if (!confirm("Déplacer cette photo vers la corbeille (~/.iris-trash) ?")) return;
    btn.disabled = true;
    btn.textContent = "…";
    try {
      const res = await fetch("/api/dedupe/discard", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!res.ok) { btn.disabled = false; btn.textContent = "Écarter (erreur)"; return; }
      const group = thumb.closest(".dedupe-group");
      thumb.remove();
      const remaining = group.querySelectorAll(".dedupe-thumb").length;
      if (remaining <= 1) group.remove();
      dedupeUpdateSummary();
    } catch (e) {
      btn.disabled = false;
      btn.textContent = "Écarter (erreur)";
    }
  });

  thumb.appendChild(imgWrap);
  thumb.appendChild(name);
  thumb.appendChild(btn);
  return thumb;
}

function dedupeUpdateSummary() {
  const groups = dedupeGroupsEl.querySelectorAll(".dedupe-group").length;
  const images = dedupeGroupsEl.querySelectorAll(".dedupe-thumb").length;
  dedupeSummary.textContent = groups ? `${groups} groupes · ${images} photos concernées` : "Aucun groupe restant.";
  dedupeEmptyEl.style.display = groups ? "none" : "";
}

function dedupeRenderGroups(groups) {
  dedupeGroupsEl.innerHTML = "";
  for (const g of groups) {
    const card = document.createElement("div");
    card.className = "dedupe-group";
    const head = document.createElement("div");
    head.className = "dedupe-group-head";
    head.innerHTML = `<span>${g.images.length} photos</span><span>similarité max ${Math.round(g.max_similarity * 100)}%</span>`;
    const thumbs = document.createElement("div");
    thumbs.className = "dedupe-thumbs";
    for (const path of g.images) thumbs.appendChild(dedupeMakeThumb(path));
    card.appendChild(head);
    card.appendChild(thumbs);
    dedupeGroupsEl.appendChild(card);
  }
  dedupeUpdateSummary();
}

async function dedupePoll() {
  const pRes = await fetch("/api/dedupe-progress").then(r => r.json());
  const phase = pRes.phase === "similarity" ? "Comparaison" : (pRes.phase === "scan" ? "Analyse" : "Embeddings");
  dedupePhase.textContent = phase;
  dedupeCount.textContent = pRes.total ? `${pRes.done} / ${pRes.total}` : "—";
  setBar(dedupeFill, pRes.done, pRes.total);
  dedupeCancelBtn.hidden = pRes.status !== "running";

  if (pRes.status === "running") {
    setTimeout(dedupePoll, 600);
    return;
  }
  dedupeBtn.disabled = false;
  if (pRes.status === "error") {
    dedupeSummary.textContent = "Erreur : " + pRes.phase;
    return;
  }
  if (pRes.status === "cancelled") {
    dedupeSummary.textContent = "Annulé.";
    return;
  }
  dedupeFill.classList.add("done");
  const data = await fetch("/api/dedupe-results").then(r => r.json());
  dedupeRenderGroups(data.groups);
}

dedupeBtn.addEventListener("click", async () => {
  const folder = dedupeFolderEl.value.trim();
  if (!folder) { alert("Indique un dossier déjà classé."); return; }
  dedupeBtn.disabled = true;
  dedupeFill.classList.remove("done");
  setBar(dedupeFill, 0, 1);
  dedupeGroupsEl.innerHTML = "";
  dedupeEmptyEl.style.display = "none";
  dedupeSummary.textContent = "";

  const res = await fetch("/api/dedupe", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      folder,
      threshold: dedupeThresholdEl.value / 100,
      category: dedupeFilterCatEl.value || null,
    }),
  });
  if (!res.ok) {
    dedupeSummary.textContent = "Erreur : " + (await res.text());
    dedupeBtn.disabled = false;
    return;
  }
  dedupePoll();
});

// ---------- Graphe de similarité (nœuds = photos, arêtes = similarité CLIP) ----------
const graphFolderEl = $("graphFolder");
const graphFilterCatEl = $("graphFilterCat");
const graphTopKEl = $("graphTopK"), graphTopKVal = $("graphTopKVal");
const graphThresholdEl = $("graphThreshold"), graphThresholdVal = $("graphThresholdVal");
const graphBtn = $("graphBtn");
const graphBar = $("graphBar"), graphPhase = $("graphPhase"), graphCount = $("graphCount"), graphFill = $("graphFill");
const graphCancelBtn = $("graphCancelBtn");
const graphSummary = $("graphSummary");
const cyContainer = $("cyContainer");
const graphEmptyEl = $("graphEmpty");
const graphInspEmpty = $("graphInspEmpty"), graphInspBody = $("graphInspBody");
const graphInspImg = $("graphInspImg"), graphInspName = $("graphInspName"), graphInspCat = $("graphInspCat");

let cy = null;
wireCancelBtn(graphCancelBtn, "/api/gallery/graph/cancel");

graphTopKEl.addEventListener("input", () => { graphTopKVal.textContent = graphTopKEl.value; });
graphThresholdEl.addEventListener("input", () => { graphThresholdVal.textContent = (graphThresholdEl.value / 100).toFixed(2); });

graphFolderEl.value = localStorage.getItem(GAL_FOLDER_STORAGE_KEY) || CANONICAL_EXPORT_DIR;

// Peuple le filtre catégorie sans calcul de modèle (même logique que Doublons).
async function graphRefreshCategories() {
  const folder = graphFolderEl.value.trim();
  if (!folder) return;
  try {
    const res = await fetch("/api/gallery?folder=" + encodeURIComponent(folder));
    if (!res.ok) return;
    const data = await res.json();
    const current = graphFilterCatEl.value;
    const cats = [...new Set(data.items.map(i => i.category_label).filter(Boolean))].sort();
    graphFilterCatEl.innerHTML = '<option value="">Toutes catégories</option>'
      + cats.map(c => `<option value="${c}">${c}</option>`).join("");
    graphFilterCatEl.value = current;
  } catch (e) { /* silencieux */ }
}
graphFolderEl.addEventListener("blur", graphRefreshCategories);

function graphSelectNode(path, catLabel) {
  graphInspEmpty.hidden = true;
  graphInspBody.hidden = false;
  graphInspImg.src = "/api/thumbnail?path=" + encodeURIComponent(path);
  graphInspName.textContent = path.split("/").pop();
  graphInspCat.textContent = catLabel || "—";
}

function graphRender(data) {
  cyContainer.innerHTML = "";
  graphEmptyEl.style.display = data.nodes.length ? "none" : "";
  graphSummary.textContent = `${data.nodes.length} photos · ${data.edges.length} liens`;
  if (!data.nodes.length) return;

  // Seuil "quasi-identique" — distinct visuellement des liens juste
  // thématiques (même style/perso récurrent), sinon tout se noie dans le
  // même gris au milieu d'un layout dense.
  const NEAR_DUP_THRESHOLD = 0.9;

  const elements = [
    ...data.nodes.map(n => ({
      data: { id: n.path, label: n.category_label || "" },
      style: { "background-image": "/api/thumbnail?path=" + encodeURIComponent(n.path) },
    })),
    ...data.edges.map(e => ({
      data: {
        source: e.source, target: e.target, weight: e.weight,
        near: e.weight >= NEAR_DUP_THRESHOLD ? 1 : 0,
      },
    })),
  ];

  cy = cytoscape({
    container: cyContainer,
    elements,
    style: [
      {
        selector: "node",
        style: {
          width: 48, height: 48,
          shape: "ellipse",
          "background-fit": "cover",
          "border-width": 2,
          "border-color": "#d7dbe0",
        },
      },
      { selector: "node:selected", style: { "border-color": "#3b6fd6", "border-width": 4 } },
      {
        selector: "edge",
        style: {
          width: "mapData(weight, 0.5, 1, 1, 4)",
          opacity: "mapData(weight, 0.5, 1, 0.1, 0.5)",
          "line-color": "#9096a0",
          "curve-style": "haystack",
        },
      },
      // Liens quasi-identiques : rouge, épais, opaques — sautent aux yeux
      // au milieu du reste au lieu de se fondre dans le gris ambiant.
      {
        selector: "edge[near = 1]",
        style: {
          "line-color": "#d0503f",
          width: "mapData(weight, 0.9, 1, 4, 7)",
          opacity: 0.9,
          "z-index": 10,
        },
      },
      // Focus sur le voisinage du nœud tapé — le reste s'estompe.
      { selector: ".dimmed", style: { opacity: 0.08 } },
      { selector: "node.focused", style: { "border-color": "#d0503f", "border-width": 4 } },
    ],
    layout: { name: "cose", animate: false, nodeRepulsion: () => 8000, idealEdgeLength: () => 60 },
  });

  cy.on("tap", "node", (evt) => {
    const n = evt.target;
    graphSelectNode(n.id(), n.data("label"));

    // Isole visuellement le nœud + ses voisins directs (surtout utile pour
    // repérer LES quelques images vraiment proches d'une photo donnée,
    // plutôt que de deviner dans la masse des 262 liens).
    const neighborhood = n.closedNeighborhood();
    cy.elements().addClass("dimmed");
    neighborhood.removeClass("dimmed");
    cy.nodes().removeClass("focused");
    n.addClass("focused");
  });
  cy.on("tap", (evt) => {
    if (evt.target === cy) { cy.elements().removeClass("dimmed"); cy.nodes().removeClass("focused"); }
  });
  cy.on("dblclick", "node", (evt) => openLightbox(evt.target.id()));
}

async function graphPoll() {
  const pRes = await fetch("/api/gallery/graph-progress").then(r => r.json());
  const phase = pRes.phase === "graph" ? "Construction du graphe" : (pRes.phase === "scan" ? "Analyse" : "Embeddings");
  graphPhase.textContent = phase;
  graphCount.textContent = pRes.total ? `${pRes.done} / ${pRes.total}` : "—";
  setBar(graphFill, pRes.done, pRes.total);
  graphCancelBtn.hidden = pRes.status !== "running";

  if (pRes.status === "running") { setTimeout(graphPoll, 700); return; }
  graphBtn.disabled = false;
  if (pRes.status === "error") { graphSummary.textContent = "Erreur : " + pRes.phase; return; }
  if (pRes.status === "cancelled") { graphSummary.textContent = "Annulé."; return; }
  graphFill.classList.add("done");
  const data = await fetch("/api/gallery/graph-results").then(r => r.json());
  graphRender(data);
}

graphBtn.addEventListener("click", async () => {
  const folder = graphFolderEl.value.trim();
  if (!folder) { alert("Indique un dossier déjà classé."); return; }
  graphBtn.disabled = true;
  graphFill.classList.remove("done");
  setBar(graphFill, 0, 1);
  graphSummary.textContent = "";
  graphEmptyEl.style.display = "none";

  const res = await fetch("/api/gallery/graph", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      folder,
      category: graphFilterCatEl.value || null,
      top_k: parseInt(graphTopKEl.value, 10),
      min_similarity: graphThresholdEl.value / 100,
    }),
  });
  if (!res.ok) {
    graphSummary.textContent = "Erreur : " + (await res.text());
    graphBtn.disabled = false;
    return;
  }
  graphPoll();
});

// ---------- Recta : historique des photos déjà publiées ----------
const rectaFolderEl = $("rectaFolder");
const rectaLoadBtn = $("rectaLoadBtn");
const rectaCountsEl = $("rectaCounts");
const rectaGridEl = $("rectaGrid");
const rectaEmptyEl = $("rectaEmpty");
const rectaInspEmpty = $("rectaInspEmpty"), rectaInspBody = $("rectaInspBody");
const rectaInspImg = $("rectaInspImg"), rectaInspName = $("rectaInspName");
const rectaInspNumero = $("rectaInspNumero"), rectaInspLang = $("rectaInspLang"), rectaInspDate = $("rectaInspDate");
const rectaInspNetworks = $("rectaInspNetworks");

let rectaItemsByPath = new Map();

// Préremplissage immédiat (pas d'attente d'un focus qui peut ne jamais venir
// si l'utilisateur clique directement sur Charger — déjà vu ailleurs cette
// session : un placeholder ressemble à une valeur mais n'en est pas une).
rectaFolderEl.value = localStorage.getItem(GAL_FOLDER_STORAGE_KEY) || CANONICAL_EXPORT_DIR;

function rectaMakeCard(item) {
  const card = document.createElement("div");
  card.className = "thumb";

  const imgWrap = document.createElement("div");
  imgWrap.className = "thumb-img";
  const img = document.createElement("img");
  img.loading = "lazy";
  img.src = "/api/thumbnail?path=" + encodeURIComponent(item.path);
  imgWrap.appendChild(img);

  const foot = document.createElement("div");
  foot.className = "thumb-foot";
  const dot = document.createElement("span");
  dot.className = "status-dot detailed";
  const cat = document.createElement("span");
  cat.className = "thumb-cat";
  const d = new Date(item.renegat_posted.timestamp);
  cat.textContent = `#${item.renegat_posted.numero} · ${d.toLocaleDateString()}`;
  foot.appendChild(dot);
  foot.appendChild(cat);

  card.appendChild(imgWrap);
  card.appendChild(foot);
  card.addEventListener("click", () => rectaSelectImage(item.path));
  card.addEventListener("dblclick", () => openLightbox(item.path));
  return card;
}

function rectaSelectImage(path) {
  const item = rectaItemsByPath.get(path);
  if (!item) return;
  rectaInspEmpty.hidden = true;
  rectaInspBody.hidden = false;
  rectaInspImg.src = "/api/thumbnail?path=" + encodeURIComponent(path);
  rectaInspName.textContent = path.split("/").pop();
  const rp = item.renegat_posted;
  rectaInspNumero.textContent = "#" + rp.numero;
  rectaInspLang.textContent = rp.lang || "—";
  rectaInspDate.textContent = new Date(rp.timestamp).toLocaleString();
  rectaInspNetworks.innerHTML = "";
  for (const r of rp.results || []) {
    const row = document.createElement("div");
    row.className = "kv-row";
    row.innerHTML = `<span class="kv-key">${r.network}</span><span class="kv-val">${r.ok ? "✓ " + (r.id || "") : "✗ " + (r.error || "")}</span>`;
    rectaInspNetworks.appendChild(row);
  }
}

rectaLoadBtn.addEventListener("click", async () => {
  const folder = rectaFolderEl.value.trim();
  if (!folder) { alert("Indique le dossier export."); return; }
  rectaLoadBtn.disabled = true;
  rectaCountsEl.textContent = "Chargement…";
  try {
    const res = await fetch("/api/gallery?folder=" + encodeURIComponent(folder));
    if (!res.ok) { rectaCountsEl.textContent = "Erreur: " + (await res.text()); return; }
    const data = await res.json();
    const posted = data.items.filter(i => i.renegat_posted)
      .sort((a, b) => new Date(b.renegat_posted.timestamp) - new Date(a.renegat_posted.timestamp));
    rectaItemsByPath = new Map(posted.map(i => [i.path, i]));
    rectaGridEl.innerHTML = "";
    rectaInspBody.hidden = true; rectaInspEmpty.hidden = false;
    for (const item of posted) rectaGridEl.appendChild(rectaMakeCard(item));
    rectaEmptyEl.style.display = posted.length ? "none" : "";
    rectaCountsEl.textContent = `${posted.length} publiée${posted.length > 1 ? "s" : ""} / ${data.items.length} au total`;
  } finally {
    rectaLoadBtn.disabled = false;
  }
});
