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
folderEl.addEventListener("change", () => {
  if (!destEl.value && folderEl.value) {
    destEl.value = folderEl.value.replace(/\/$/, "") + "/_classees";
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

  if (pRes.status === "running") {
    setTimeout(pollAnalyze, 600);
  } else {
    clearProcessing();
    analyzeFill.classList.add("done");
    updateGlobal("Analyse terminée", pRes.total, pRes.total, true);
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

  if (pRes.status === "running") {
    setTimeout(pollDetails, 700);
  } else {
    clearProcessing();
    detailsFill.classList.add("done");
    updateGlobal("Détails terminés", pRes.total, pRes.total, true);
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

  if (pRes.status === "running") {
    setTimeout(pollRefine, 700);
  } else {
    clearProcessing();
    refineFill.classList.add("done");
    updateGlobal("Attributs affinés", pRes.total, pRes.total, true);
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
