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

// ---------- Pipeline complet (analyse → détails → attributs → applique) ----------
const pipelineBtn = $("pipelineBtn");
const pipelineCancelBtn = $("pipelineCancelBtn");
const pipelineStatusEl = $("pipelineStatus");
const pipelineCanonCheck = $("pipelineCanonCheck");

/** Démarre un job (POST) puis attend qu'il quitte l'état "running" en
 * réinterrogeant sa progress-route — factorise ce que chaque bouton
 * (analyzeBtn/detailsBtn/refineBtn) fait déjà séparément, pour les enchaîner
 * sans dupliquer leur logique de poll respective. */
async function pipelineRunStep(label, startUrl, startBody, progressUrl, onProgress) {
  pipelineStatusEl.textContent = label + "…";
  const res = await fetch(startUrl, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(startBody || {}),
  });
  if (!res.ok) throw new Error(`${label} : ` + (await res.text()));
  while (true) {
    const pRes = await fetch(progressUrl).then(r => r.json());
    const items = await fetchResults();
    mergeResults(items);
    onProgress(pRes);
    if (pRes.status !== "running") {
      if (pRes.status === "cancelled") throw new Error(`${label} annulé`);
      if (pRes.status === "error") throw new Error(`${label} : ` + (pRes.phase || pRes.current || "échec"));
      return pRes;
    }
    await new Promise(r => setTimeout(r, 700));
  }
}

pipelineCancelBtn.addEventListener("click", () => {
  // On ne sait pas forcément quelle étape tourne au moment du clic —
  // annuler les quatre est sans risque, les jobs inactifs répondent en no-op.
  fetch("/api/analyze/cancel", { method: "POST" });
  fetch("/api/extract-details/cancel", { method: "POST" });
  fetch("/api/refine/cancel", { method: "POST" });
  fetch("/api/gallery/canon/cancel", { method: "POST" });
});

pipelineBtn.addEventListener("click", async () => {
  const folder = folderEl.value.trim();
  const dest = destEl.value.trim();
  if (!folder) { alert("Indique un dossier source."); return; }
  if (!dest) { alert("Indique un dossier destination."); return; }

  pipelineBtn.disabled = true;
  pipelineCancelBtn.hidden = false;
  analyzeBtn.disabled = true; detailsBtn.disabled = true; refineBtn.disabled = true; applyBtn.disabled = true;

  itemsByPath.clear(); order = []; cardByPath.clear();
  gridEl.innerHTML = ""; selectedPath = null;
  inspBody.hidden = true; inspEmpty.hidden = false;
  lastScrolledPath = null;
  currentCategories = parseCategories();
  rebuildFilterOptions();

  try {
    await pipelineRunStep(
      "Analyse (passe 1)", "/api/analyze", { folder, categories: currentCategories }, "/api/progress",
      (p) => {
        updateGlobal(`Analyse (${p.phase === "clip" ? "CLIP" : "YOLO"})`, p.done, p.total);
        analyzeCount.textContent = `${p.done} / ${p.total}`;
        setBar(analyzeFill, p.done, p.total);
        markProcessing(p.current);
      }
    );
    clearProcessing();
    analyzeFill.classList.add("done");

    if (order.length === 0) {
      pipelineStatusEl.textContent = "Aucune image trouvée — rien à faire.";
      return;
    }

    await pipelineRunStep(
      "Extraction des détails (passe 2)", "/api/extract-details", {}, "/api/details-progress",
      (p) => {
        updateGlobal("Extraction des détails", p.done, p.total);
        detailsCount.textContent = `${p.done} / ${p.total}`;
        setBar(detailsFill, p.done, p.total);
        markProcessing(p.current);
      }
    );
    clearProcessing();
    detailsFill.classList.add("done");

    await pipelineRunStep(
      "Affinage des attributs (passe 3)", "/api/refine", {}, "/api/refine-progress",
      (p) => {
        updateGlobal("Affinage des attributs", p.done, p.total);
        refineCount.textContent = `${p.done} / ${p.total}`;
        setBar(refineFill, p.done, p.total);
        markProcessing(p.current);
      }
    );
    clearProcessing();
    refineFill.classList.add("done");

    pipelineStatusEl.textContent = "Application du tri…";
    const applyRes = await fetch("/api/apply", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dest_root: dest }),
    });
    const applyData = await applyRes.json();
    let statusMsg = `Terminé — ${applyData.moved} image(s) classée(s) et déplacée(s)`
      + (applyData.errors?.length ? ` · ${applyData.errors.length} erreur(s)` : "");

    if (pipelineCanonCheck.checked && applyData.applied_paths?.length) {
      const canonPaths = applyData.applied_paths;
      await pipelineRunStep(
        "Vérification du canon", "/api/gallery/canon", { paths: canonPaths }, "/api/gallery/canon-progress",
        (p) => updateGlobal("Vérification du canon", p.done, p.total)
      );
      statusMsg += ` · canon vérifié sur ${canonPaths.length} photo(s)`;
    }
    pipelineStatusEl.textContent = statusMsg;

    itemsByPath.clear(); order = []; cardByPath.clear();
    gridEl.innerHTML = ""; selectedPath = null;
    inspBody.hidden = true; inspEmpty.hidden = false;
    syncGrid();
    updateGlobal("Prêt", 0, 0);
  } catch (e) {
    pipelineStatusEl.textContent = "Arrêté : " + e.message;
  } finally {
    pipelineBtn.disabled = false;
    pipelineCancelBtn.hidden = true;
    analyzeBtn.disabled = false;
    detailsBtn.disabled = order.length === 0;
    refineBtn.disabled = order.length === 0;
    applyBtn.disabled = order.length === 0;
  }
});

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
const browseShortcutsEl = $("browseShortcuts");
let browseTargetInput = null, browseCurrentPath = null, browseParentPath = null;

const SHORTCUT_GROUP_LABELS = { local: "Local", removable: "Clés USB", network: "Réseau", mount: "Montages" };

async function browseRenderShortcuts() {
  const res = await fetch("/api/browse/shortcuts");
  const data = await res.json();
  browseShortcutsEl.innerHTML = "";
  for (const groupKey of ["local", "removable", "network", "mount"]) {
    const items = data.shortcuts.filter(s => s.group === groupKey);
    if (!items.length) continue;
    const group = document.createElement("div");
    group.className = "shortcut-group";
    const label = document.createElement("div");
    label.className = "shortcut-group-label";
    label.textContent = SHORTCUT_GROUP_LABELS[groupKey];
    group.appendChild(label);
    for (const sc of items) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "shortcut-item" + (browseCurrentPath === sc.path ? " active" : "");
      btn.textContent = sc.label;
      btn.title = sc.detail ? `${sc.path} (${sc.detail})` : sc.path;
      btn.addEventListener("click", () => browseLoad(sc.path));
      group.appendChild(btn);
    }
    browseShortcutsEl.appendChild(group);
  }
}

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
  } else {
    for (const entry of data.entries) {
      const div = document.createElement("div");
      div.className = "browse-item";
      div.textContent = "📁 " + entry.name;
      div.addEventListener("click", () => browseLoad(entry.path));
      browseListEl.appendChild(div);
    }
  }
  browseRenderShortcuts(); // rafraîchit le surlignage "actif" selon le nouveau chemin
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
const views = {
  tri: $("view-tri"), bibliotheque: $("view-bibliotheque"), galerie: $("view-galerie"),
  doublons: $("view-doublons"), graphe: $("view-graphe"), recta: $("view-recta"), taxonomie: $("view-taxonomie"),
};
views.bibliotheque.style.display = "none"; // état initial : onglet Tri actif (le hidden HTML seul ne suffit pas, cf. commentaire ci-dessous)
views.galerie.style.display = "none";
views.doublons.style.display = "none";
views.graphe.style.display = "none";
views.recta.style.display = "none";
views.taxonomie.style.display = "none";

function switchToTab(name) {
  const btn = document.querySelector(`.tab-btn[data-tab="${name}"]`);
  if (!btn) return;
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b === btn));
  for (const [n, el] of Object.entries(views)) {
    el.style.display = n === name ? "grid" : "none";
  }
}

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchToTab(btn.dataset.tab));
});
document.querySelectorAll("[data-goto-tab]").forEach(btn => {
  btn.addEventListener("click", () => switchToTab(btn.dataset.gotoTab));
});

// ---------- Bibliothèque (catalogue multi-dossiers, à la Lightroom) ----------
// Remplace le champ "dossier unique" qu'avaient Galerie/Doublons/Graphe/
// Taxonomie/Recta : ces onglets chargent désormais l'union de tous les
// dossiers listés ici, sans qu'on ait à retaper un chemin à chaque fois.
async function libFolders() {
  const res = await fetch("/api/library");
  const data = await res.json();
  return data.folders || [];
}

function libSummaryText(folders) {
  if (!folders.length) return "Aucun dossier — onglet Bibliothèque pour en ajouter.";
  return `${folders.length} dossier${folders.length > 1 ? "s" : ""} : ` + folders.map(f => f.split("/").pop()).join(", ");
}

async function refreshLibSummaryEl(el) {
  const folders = await libFolders();
  if (el) el.textContent = libSummaryText(folders);
  return folders;
}

// Peuple un <select> "dossier source" (Doublons/Graphe) — préserve la
// sélection en cours si elle existe toujours dans la liste.
async function populateFolderSelect(selectEl) {
  const folders = await libFolders();
  const current = selectEl.value;
  selectEl.innerHTML = '<option value="">Tous les dossiers</option>'
    + folders.map(f => `<option value="${f}">${f.split("/").pop()}</option>`).join("");
  if (folders.includes(current)) selectEl.value = current;
}

const libNewFolderEl = $("libNewFolder");
const libAddBtn = $("libAddBtn");
const libListEl = $("libList");
const libEmptyEl = $("libEmpty");

async function libRender() {
  const res = await fetch("/api/library/health");
  const data = await res.json();
  const folders = data.folders || [];
  libListEl.innerHTML = "";
  libEmptyEl.style.display = folders.length ? "none" : "";
  for (const f of folders) {
    const row = document.createElement("div");
    row.className = "lib-row";
    const status = f.accessible
      ? `${f.total} photo${f.total > 1 ? "s" : ""} · ${f.no_sidecar} sans sidecar · ${f.no_aesthetic} sans score esthétique · ${f.no_canon} sans canon`
      : `⚠️ dossier inaccessible (démonté ?)`;
    row.innerHTML = `
      <div>
        <div class="lib-row-path">${f.accessible ? "📁" : "⚠️"} ${f.path}</div>
        <div class="lib-row-count">${status}</div>
      </div>
      <button type="button" class="btn ghost" style="color:var(--err);border-color:var(--err)">Retirer</button>
    `;
    row.querySelector("button").addEventListener("click", async () => {
      await fetch("/api/library/remove", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: f.path }),
      });
      libRender();
    });
    libListEl.appendChild(row);
  }
}
libRender();

libAddBtn.addEventListener("click", async () => {
  const path = libNewFolderEl.value.trim();
  if (!path) return;
  libAddBtn.disabled = true;
  try {
    const res = await fetch("/api/library/add", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    if (!res.ok) { alert("Erreur : " + (await res.text())); return; }
    libNewFolderEl.value = "";
    libRender();
  } finally {
    libAddBtn.disabled = false;
  }
});

// ---------- Galerie ----------
const galLibSummary = $("galLibSummary");
const galLoadBtn = $("galLoadBtn");
const galFilterCatEl = $("galFilterCat");
const galSearchEl = $("galSearch");
const galCountsEl = $("galCounts");
const galGridEl = $("galGrid");
const galEmptyEl = $("galEmpty");
const galInspEmpty = $("galInspEmpty"), galInspBody = $("galInspBody");
const galInspImg = $("galInspImg"), galInspName = $("galInspName"), galInspCat = $("galInspCat");
const galInspSource = $("galInspSource");
const galInspDetails = $("galInspDetails");
const galInspAttrSection = $("galInspAttrSection"), galInspAttrs = $("galInspAttrs");
const galInspAesthetic = $("galInspAesthetic");
const galInspCanonSection = $("galInspCanonSection");
const galInspCanonFaction = $("galInspCanonFaction"), galInspCanonVerdict = $("galInspCanonVerdict");
const galInspCanonClip = $("galInspCanonClip");
const galInspCanonReason = $("galInspCanonReason");
const galCharacterNameEl = $("galCharacterName");
const galCharacterSaveBtn = $("galCharacterSaveBtn");
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

  if (item.source_folder) {
    const badge = document.createElement("div");
    badge.className = "source-badge";
    badge.textContent = "📁 " + item.source_folder.split("/").pop();
    badge.title = item.source_folder;
    card.appendChild(badge);
  }

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
  galInspSource.textContent = item.source_folder ? item.source_folder.split("/").pop() : "—";
  galInspSource.title = item.source_folder || "";
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

  galInspAesthetic.textContent = item.aesthetic_score != null
    ? `${item.aesthetic_score} / 10 (IA)`
    : "—";

  if (item.canon_reason) {
    galInspCanonSection.hidden = false;
    galInspCanonFaction.textContent = item.canon_faction || "Faction non reconnue";
    galInspCanonVerdict.textContent = item.canon_verdict || "";
    galInspCanonClip.textContent = item.canon_clip_confidence != null
      ? `${Math.round(item.canon_clip_confidence * 100)}%`
      : "—";
    galInspCanonReason.textContent = item.canon_reason;
  } else {
    galInspCanonSection.hidden = true;
  }

  galCharacterNameEl.value = item.character_name || "";

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
  const folders = await refreshLibSummaryEl(galLibSummary);
  if (!folders.length) { alert("Ajoute d'abord un dossier dans l'onglet Bibliothèque."); return; }
  galLoadBtn.disabled = true;
  galCountsEl.textContent = "Chargement…";
  try {
    const res = await fetch("/api/gallery");
    if (!res.ok) { galCountsEl.textContent = "Erreur: " + (await res.text()); return; }
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
  const query = galSearchEl.value.trim();
  if (!galItems.length) { alert("Charge d'abord la bibliothèque."); return; }
  if (!query) { alert("Tape une description dans le champ recherche."); return; }
  galSemanticBtn.disabled = true;
  galCountsEl.textContent = "Recherche sémantique en cours…";
  try {
    const res = await fetch("/api/gallery/search", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, category: galActiveCat || null, top_k: 30 }),
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
  if (!galItems.length) { alert("Charge d'abord la bibliothèque."); return; }
  const visible = galVisiblePaths();
  const missing = visible.filter(p => !galItemsByPath.get(p).details);
  if (!missing.length) { galBackfillCount.textContent = "Rien à compléter (vue actuelle)"; return; }
  if (!confirm(`Extraire détails + attributs pour ${missing.length} photo(s) sans sidecar ?`)) return;

  galBackfillBtn.disabled = true;
  galBackfillFill.classList.remove("done");
  setBar(galBackfillFill, 0, 1);
  const res = await fetch("/api/gallery/backfill", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths: missing }),
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

galCharacterSaveBtn.addEventListener("click", async () => {
  if (!galSelectedPath) return;
  const name = galCharacterNameEl.value.trim();
  galCharacterSaveBtn.disabled = true;
  try {
    const res = await fetch("/api/gallery/character", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: galSelectedPath, character_name: name }),
    });
    if (!res.ok) { alert("Erreur : " + (await res.text())); return; }
    const item = galItemsByPath.get(galSelectedPath);
    if (item) item.character_name = name || null;
  } finally {
    galCharacterSaveBtn.disabled = false;
  }
});

// ---------- Sélection multiple (utile sur un gros lot fraîchement importé) ----------
const galBulkBar = $("galBulkBar");
const galBulkCount = $("galBulkCount");
const galBulkClearBtn = $("galBulkClearBtn");
const galBulkStars = $("galBulkStars");
const galBulkDeleteBtn = $("galBulkDeleteBtn");
const galBulkExportBtn = $("galBulkExportBtn");
const galBulkRefineBtn = $("galBulkRefineBtn");
const galBulkRefineCancelBtn = $("galBulkRefineCancelBtn");
wireCancelBtn(galBulkRefineCancelBtn, "/api/gallery/refine/cancel");
const galBulkAestheticBtn = $("galBulkAestheticBtn");
const galBulkAestheticCancelBtn = $("galBulkAestheticCancelBtn");
wireCancelBtn(galBulkAestheticCancelBtn, "/api/gallery/aesthetic/cancel");
const galBulkCanonBtn = $("galBulkCanonBtn");
const galBulkCanonCancelBtn = $("galBulkCanonCancelBtn");
const galCanonFactionSel = $("galCanonFactionSel");
wireCancelBtn(galBulkCanonCancelBtn, "/api/gallery/canon/cancel");

fetch("/api/factions").then(r => r.json()).then(data => {
  for (const f of data.factions) {
    const opt = document.createElement("option");
    opt.value = f.id;
    opt.textContent = f.label;
    galCanonFactionSel.appendChild(opt);
  }
});
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

galBulkExportBtn.addEventListener("click", async () => {
  const paths = [...galSelectedPaths];
  if (!paths.length) return;
  const title = `Sélection Iris — ${new Date().toLocaleDateString("fr-FR")}`;
  galBulkExportBtn.disabled = true;
  galBulkExportBtn.textContent = "Export en cours…";
  try {
    const res = await fetch("/api/gallery/export", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paths, title }),
    });
    if (!res.ok) { alert("Erreur : " + (await res.text())); return; }
    const data = await res.json();
    window.open(data.url, "_blank");
  } finally {
    galBulkExportBtn.disabled = false;
    galBulkExportBtn.textContent = "Exporter en planche contact";
  }
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
    body: JSON.stringify({ paths }),
  });
  if (!res.ok) {
    alert("Erreur : " + (await res.text()));
    galBulkRefineBtn.disabled = false;
    galBulkRefineBtn.textContent = "Réaffiner les attributs (passe 3)";
    return;
  }
  galRefinePoll();
});

async function galAestheticPoll() {
  const pRes = await fetch("/api/gallery/aesthetic-progress").then(r => r.json());
  galBulkAestheticBtn.textContent = pRes.total
    ? `Score en cours… ${pRes.done} / ${pRes.total}`
    : "Score en cours…";
  galBulkAestheticCancelBtn.hidden = pRes.status !== "running";
  if (pRes.status === "running") { setTimeout(galAestheticPoll, 700); return; }
  galBulkAestheticBtn.disabled = false;
  galBulkAestheticBtn.textContent = "Score esthétique (IA)";
  if (pRes.status === "error") { alert("Erreur : " + pRes.current); return; }
  // Recharge le score à jour pour les photos concernées sans tout recharger.
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
}

galBulkAestheticBtn.addEventListener("click", async () => {
  const paths = [...galSelectedPaths];
  if (!paths.length) return;
  galBulkAestheticBtn.disabled = true;
  galBulkAestheticBtn.textContent = "Score en cours…";
  const res = await fetch("/api/gallery/aesthetic", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths }),
  });
  if (!res.ok) {
    alert("Erreur : " + (await res.text()));
    galBulkAestheticBtn.disabled = false;
    galBulkAestheticBtn.textContent = "Score esthétique (IA)";
    return;
  }
  galAestheticPoll();
});

async function galCanonPoll() {
  const pRes = await fetch("/api/gallery/canon-progress").then(r => r.json());
  galBulkCanonBtn.textContent = pRes.total
    ? `Vérification… ${pRes.done} / ${pRes.total}`
    : "Vérification…";
  galBulkCanonCancelBtn.hidden = pRes.status !== "running";
  if (pRes.status === "running") { setTimeout(galCanonPoll, 700); return; }
  galBulkCanonBtn.disabled = false;
  galBulkCanonBtn.textContent = "Vérifier le canon (faction)";
  if (pRes.status === "error") { alert("Erreur : " + pRes.current); return; }
  // Recharge la faction/verdict à jour pour les photos concernées sans tout recharger.
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
}

galBulkCanonBtn.addEventListener("click", async () => {
  const paths = [...galSelectedPaths];
  if (!paths.length) return;
  const faction_id = galCanonFactionSel.value || null;
  galBulkCanonBtn.disabled = true;
  galBulkCanonBtn.textContent = "Vérification…";
  const res = await fetch("/api/gallery/canon", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ paths, faction_id }),
  });
  if (!res.ok) {
    alert("Erreur : " + (await res.text()));
    galBulkCanonBtn.disabled = false;
    galBulkCanonBtn.textContent = "Vérifier le canon (faction)";
    return;
  }
  galCanonPoll();
});

// ---------- Doublons / images similaires ----------
const dedupeLibSummary = $("dedupeLibSummary");
const dedupeFilterCatEl = $("dedupeFilterCat");
const dedupeFilterFolderEl = $("dedupeFilterFolder");
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

// Peuple le filtre catégorie à l'entrée sur l'onglet — lecture seule des
// sidecars/dossiers, aucun calcul de modèle (rapide, pas besoin d'un bouton
// dédié).
async function dedupeRefreshCategories() {
  try {
    const res = await fetch("/api/gallery");
    if (!res.ok) return;
    const data = await res.json();
    const current = dedupeFilterCatEl.value;
    const cats = [...new Set(data.items.map(i => i.category_label).filter(Boolean))].sort();
    dedupeFilterCatEl.innerHTML = '<option value="">Toutes catégories</option>'
      + cats.map(c => `<option value="${c}">${c}</option>`).join("");
    dedupeFilterCatEl.value = current;
  } catch (e) { /* silencieux : la détection tournera sans filtre pré-rempli */ }
}
document.querySelector('.tab-btn[data-tab="doublons"]').addEventListener("click", () => {
  refreshLibSummaryEl(dedupeLibSummary);
  dedupeRefreshCategories();
  populateFolderSelect(dedupeFilterFolderEl);
});

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
  const folders = await libFolders();
  if (!folders.length) { alert("Ajoute d'abord un dossier dans l'onglet Bibliothèque."); return; }
  dedupeBtn.disabled = true;
  dedupeFill.classList.remove("done");
  setBar(dedupeFill, 0, 1);
  dedupeGroupsEl.innerHTML = "";
  dedupeEmptyEl.style.display = "none";
  dedupeSummary.textContent = "";

  const res = await fetch("/api/dedupe", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      threshold: dedupeThresholdEl.value / 100,
      category: dedupeFilterCatEl.value || null,
      source_folder: dedupeFilterFolderEl.value || null,
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
const graphLibSummary = $("graphLibSummary");
const graphModeEl = $("graphMode");
const graphCatField = $("graphCatField");
const graphFilterCatEl = $("graphFilterCat");
const graphFilterFolderEl = $("graphFilterFolder");

graphModeEl.addEventListener("change", () => {
  const isIdentity = graphModeEl.value === "identity";
  // L'identité se limite déjà à Personnes côté serveur — le sélecteur de
  // catégorie n'aurait pas de sens ici, autant l'écarter pour ne pas
  // laisser croire qu'on peut choisir autre chose.
  graphCatField.style.display = isIdentity ? "none" : "";
  if (isIdentity && graphThresholdEl.value < 85) {
    graphThresholdEl.value = 85;
    graphThresholdEl.dispatchEvent(new Event("input"));
  }
});
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
const graphIdentitySection = $("graphIdentitySection");
const graphCharacterName = $("graphCharacterName"), graphCharacterSaveBtn = $("graphCharacterSaveBtn");
const graphApplyClusterBtn = $("graphApplyClusterBtn"), graphClusterInfo = $("graphClusterInfo");

let cy = null;
let graphSelectedPath = null;
let graphSelectedNeighborhood = null;
wireCancelBtn(graphCancelBtn, "/api/gallery/graph/cancel");

graphTopKEl.addEventListener("input", () => { graphTopKVal.textContent = graphTopKEl.value; });
graphThresholdEl.addEventListener("input", () => { graphThresholdVal.textContent = (graphThresholdEl.value / 100).toFixed(2); });

// Peuple le filtre catégorie sans calcul de modèle (même logique que Doublons).
async function graphRefreshCategories() {
  try {
    const res = await fetch("/api/gallery");
    if (!res.ok) return;
    const data = await res.json();
    const current = graphFilterCatEl.value;
    const cats = [...new Set(data.items.map(i => i.category_label).filter(Boolean))].sort();
    graphFilterCatEl.innerHTML = '<option value="">Toutes catégories</option>'
      + cats.map(c => `<option value="${c}">${c}</option>`).join("");
    graphFilterCatEl.value = current;
  } catch (e) { /* silencieux */ }
}
document.querySelector('.tab-btn[data-tab="graphe"]').addEventListener("click", () => {
  refreshLibSummaryEl(graphLibSummary);
  graphRefreshCategories();
  populateFolderSelect(graphFilterFolderEl);
});

async function graphSelectNode(path, catLabel) {
  graphInspEmpty.hidden = true;
  graphInspBody.hidden = false;
  graphInspImg.src = "/api/thumbnail?path=" + encodeURIComponent(path);
  graphInspName.textContent = path.split("/").pop();
  graphInspCat.textContent = catLabel || "—";

  graphSelectedPath = path;
  const isIdentity = graphModeEl.value === "identity";
  graphIdentitySection.hidden = !isIdentity;
  if (isIdentity) {
    graphClusterInfo.textContent = "";
    const item = await fetch("/api/gallery/item?path=" + encodeURIComponent(path)).then(r => r.ok ? r.json() : null);
    graphCharacterName.value = (item && item.character_name) || "";
  }
}

graphCharacterSaveBtn.addEventListener("click", async () => {
  if (!graphSelectedPath) return;
  const name = graphCharacterName.value.trim();
  graphCharacterSaveBtn.disabled = true;
  try {
    const res = await fetch("/api/gallery/character", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: graphSelectedPath, character_name: name }),
    });
    if (!res.ok) alert("Erreur : " + (await res.text()));
  } finally {
    graphCharacterSaveBtn.disabled = false;
  }
});

graphApplyClusterBtn.addEventListener("click", async () => {
  if (!graphSelectedPath || !graphSelectedNeighborhood) return;
  const name = graphCharacterName.value.trim();
  // Le voisinage direct affiché à l'écran (dimming/focus au clic) — PAS la
  // composante connexe entière du graphe, qui peut s'étendre à des dizaines
  // de photos sans rapport via une simple chaîne d'arêtes faibles.
  const paths = graphSelectedNeighborhood.nodes().map(n => n.id());
  if (!confirm(`Appliquer "${name || "(vide)"}" au voisinage affiché (${paths.length} photo(s)) ?`)) return;
  graphApplyClusterBtn.disabled = true;
  try {
    const results = await Promise.all(paths.map(path =>
      fetch("/api/gallery/character", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path, character_name: name }),
      }).then(res => res.ok)
    ));
    const failed = results.filter(ok => !ok).length;
    graphClusterInfo.textContent = failed
      ? `${paths.length - failed}/${paths.length} mises à jour, ${failed} erreur(s)`
      : `${paths.length} photo(s) mises à jour.`;
  } finally {
    graphApplyClusterBtn.disabled = false;
  }
});

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
    // plutôt que de deviner dans la masse des 262 liens). C'est aussi
    // exactement ce que "Appliquer à tout le cluster" applique — pas la
    // composante connexe entière du graphe, qui peut s'étendre bien au-delà
    // de ce qui est visuellement mis en évidence via un simple pont d'arêtes
    // faibles (vécu : 123 photos touchées via une chaîne jusqu'à un tout
    // autre groupe, alors que 6 nœuds étaient visibles à l'écran).
    const neighborhood = n.closedNeighborhood();
    graphSelectedNeighborhood = neighborhood;
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
  const phase = pRes.phase === "graph" ? "Construction du graphe"
    : pRes.phase === "scan" ? "Analyse"
    : pRes.phase === "faces" ? "Détection des visages"
    : "Embeddings";
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
  const folders = await libFolders();
  if (!folders.length) { alert("Ajoute d'abord un dossier dans l'onglet Bibliothèque."); return; }
  graphBtn.disabled = true;
  graphFill.classList.remove("done");
  setBar(graphFill, 0, 1);
  graphSummary.textContent = "";
  graphEmptyEl.style.display = "none";

  const res = await fetch("/api/gallery/graph", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      category: graphFilterCatEl.value || null,
      mode: graphModeEl.value,
      top_k: parseInt(graphTopKEl.value, 10),
      min_similarity: graphThresholdEl.value / 100,
      source_folder: graphFilterFolderEl.value || null,
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
const rectaLibSummary = $("rectaLibSummary");
const rectaLoadBtn = $("rectaLoadBtn");
const rectaCountsEl = $("rectaCounts");
const rectaGridEl = $("rectaGrid");
const rectaEmptyEl = $("rectaEmpty");
const rectaInspEmpty = $("rectaInspEmpty"), rectaInspBody = $("rectaInspBody");
const rectaInspImg = $("rectaInspImg"), rectaInspName = $("rectaInspName");
const rectaInspNumero = $("rectaInspNumero"), rectaInspLang = $("rectaInspLang"), rectaInspDate = $("rectaInspDate");
const rectaInspNetworks = $("rectaInspNetworks");

let rectaItemsByPath = new Map();

document.querySelector('.tab-btn[data-tab="recta"]').addEventListener("click", () => {
  refreshLibSummaryEl(rectaLibSummary);
});

function rectaMakeEntry(item) {
  const rp = item.renegat_posted;
  const d = new Date(rp.timestamp);

  const entry = document.createElement("div");
  entry.className = "recta-entry";

  const thumb = document.createElement("div");
  thumb.className = "recta-entry-thumb";
  const img = document.createElement("img");
  img.loading = "lazy";
  img.src = "/api/thumbnail?path=" + encodeURIComponent(item.path);
  thumb.appendChild(img);

  const body = document.createElement("div");
  body.className = "recta-entry-body";

  const head = document.createElement("div");
  head.className = "recta-entry-head";
  head.innerHTML = `<span class="recta-entry-numero">#${rp.numero}</span>`
    + `<span>${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>`
    + `<span>${item.category_label || ""}</span>`;

  const name = document.createElement("div");
  name.className = "recta-entry-name";
  name.textContent = item.path.split("/").pop();

  const nets = document.createElement("div");
  nets.className = "recta-entry-networks";
  for (const r of rp.results || []) {
    const badge = document.createElement("span");
    badge.className = "recta-net " + (r.ok ? "ok" : "fail");
    badge.textContent = (r.ok ? "✓ " : "✗ ") + r.network;
    nets.appendChild(badge);
  }

  body.appendChild(head);
  body.appendChild(name);
  body.appendChild(nets);
  entry.appendChild(thumb);
  entry.appendChild(body);

  entry.addEventListener("click", () => {
    document.querySelectorAll(".recta-entry.selected").forEach(e => e.classList.remove("selected"));
    entry.classList.add("selected");
    rectaSelectImage(item.path);
  });
  entry.addEventListener("dblclick", () => openLightbox(item.path));
  return entry;
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
  const folders = await refreshLibSummaryEl(rectaLibSummary);
  if (!folders.length) { alert("Ajoute d'abord un dossier dans l'onglet Bibliothèque."); return; }
  rectaLoadBtn.disabled = true;
  rectaCountsEl.textContent = "Chargement…";
  try {
    const res = await fetch("/api/gallery");
    if (!res.ok) { rectaCountsEl.textContent = "Erreur: " + (await res.text()); return; }
    const data = await res.json();
    const posted = data.items.filter(i => i.renegat_posted)
      .sort((a, b) => new Date(b.renegat_posted.timestamp) - new Date(a.renegat_posted.timestamp));
    rectaItemsByPath = new Map(posted.map(i => [i.path, i]));
    rectaGridEl.innerHTML = "";
    rectaInspBody.hidden = true; rectaInspEmpty.hidden = false;

    let lastDay = null;
    for (const item of posted) {
      const day = new Date(item.renegat_posted.timestamp).toLocaleDateString([], {
        weekday: "long", day: "numeric", month: "long",
      });
      if (day !== lastDay) {
        const dayEl = document.createElement("div");
        dayEl.className = "recta-day";
        dayEl.textContent = day;
        rectaGridEl.appendChild(dayEl);
        lastDay = day;
      }
      rectaGridEl.appendChild(rectaMakeEntry(item));
    }
    rectaEmptyEl.style.display = posted.length ? "none" : "";
    rectaCountsEl.textContent = `${posted.length} publiée${posted.length > 1 ? "s" : ""} / ${data.items.length} au total`;
  } finally {
    rectaLoadBtn.disabled = false;
  }
});

// ---------- Taxonomie : nuage de mots par attribut (passe 3) ----------
const taxoLibSummary = $("taxoLibSummary");
const taxoLoadBtn = $("taxoLoadBtn");
const taxoSummaryEl = $("taxoSummary");
const taxoContentEl = $("taxoContent");
const taxoEmptyEl = $("taxoEmpty");
const taxoCrossA = $("taxoCrossA"), taxoCrossB = $("taxoCrossB"), taxoCrossBtn = $("taxoCrossBtn");
const taxoCrossResultEl = $("taxoCrossResult");

document.querySelector('.tab-btn[data-tab="taxonomie"]').addEventListener("click", () => {
  refreshLibSummaryEl(taxoLibSummary);
  taxoPopulateCrossLabels();
});

async function taxoPopulateCrossLabels() {
  const res = await fetch("/api/gallery/taxonomy/labels");
  if (!res.ok) return;
  const data = await res.json();
  const opts = data.labels.map(l => `<option value="${l}">${l}</option>`).join("");
  const prevA = taxoCrossA.value, prevB = taxoCrossB.value;
  taxoCrossA.innerHTML = opts;
  taxoCrossB.innerHTML = opts;
  if (data.labels.includes(prevA)) taxoCrossA.value = prevA;
  if (data.labels.includes(prevB)) taxoCrossB.value = prevB;
  else if (data.labels.length > 1) taxoCrossB.selectedIndex = 1;
}

function taxoRenderCross(data) {
  taxoCrossResultEl.innerHTML = "";
  if (!data.rows.length || !data.cols.length) {
    taxoCrossResultEl.textContent = "Aucune photo n'a ces deux attributs à la fois.";
    return;
  }
  const cellMap = new Map(data.cells.map(c => [`${c.a}␟${c.b}`, c.count]));
  const table = document.createElement("table");
  table.className = "cross-table";
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  headRow.innerHTML = `<th>${data.label_a} \\ ${data.label_b}</th>` + data.cols.map(c => `<th>${c}</th>`).join("");
  thead.appendChild(headRow);
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of data.rows) {
    const tr = document.createElement("tr");
    const cellsHtml = data.cols.map(col => {
      const count = cellMap.get(`${row}␟${col}`) || 0;
      return `<td class="${count ? "" : "zero"}">${count || "·"}</td>`;
    }).join("");
    tr.innerHTML = `<th>${row}</th>${cellsHtml}`;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  const wrap = document.createElement("div");
  wrap.className = "cross-table-wrap";
  wrap.appendChild(table);
  taxoCrossResultEl.appendChild(wrap);
}

taxoCrossBtn.addEventListener("click", async () => {
  const labelA = taxoCrossA.value, labelB = taxoCrossB.value;
  if (!labelA || !labelB) return;
  taxoCrossBtn.disabled = true;
  try {
    const res = await fetch(`/api/gallery/taxonomy/cross?label_a=${encodeURIComponent(labelA)}&label_b=${encodeURIComponent(labelB)}`);
    if (!res.ok) { alert("Erreur : " + (await res.text())); return; }
    taxoRenderCross(await res.json());
  } finally {
    taxoCrossBtn.disabled = false;
  }
});

/** Bascule vers la Galerie puis applique soit le filtre catégorie
 * (pseudo-label "Catégorie"), soit un filtre d'attribut label/valeur —
 * réutilise exactement le mécanisme de filtre déjà construit dans l'onglet
 * Galerie, pas de logique dupliquée. */
async function taxoJumpToGalerie(label, value) {
  switchToTab("galerie");
  await galLoad();

  if (label === "Catégorie") {
    galFilterCatEl.value = value;
    galActiveCat = value;
    galApplyFilters();
  } else {
    galAttrLabelEl.value = label;
    galRebuildAttrValueOptions();
    galAttrValueEl.value = value;
    if (!galAttrFilters.some(f => f.label === label && f.value === value)) {
      galAttrFilters.push({ label, value });
    }
    galRenderAttrChips();
    galApplyFilters();
  }
}

function taxoRender(data) {
  taxoContentEl.innerHTML = "";
  const labels = Object.keys(data);
  taxoEmptyEl.style.display = labels.length ? "none" : "";
  if (!labels.length) return;

  const totalTerms = labels.reduce((n, l) => n + data[l].length, 0);
  taxoSummaryEl.textContent = `${labels.length} attributs · ${totalTerms} valeurs distinctes`;

  for (const label of labels) {
    const entries = data[label];
    const maxCount = Math.max(...entries.map(e => e.count));
    const minCount = Math.min(...entries.map(e => e.count));

    const group = document.createElement("div");
    group.className = "taxo-group";
    const h = document.createElement("h3");
    h.textContent = `${label} (${entries.length})`;
    const cloud = document.createElement("div");
    cloud.className = "taxo-cloud";

    for (const { value, count } of entries.slice(0, 60)) {
      const span = document.createElement("span");
      span.className = "taxo-term";
      // Échelle 13-30px — linéaire suffit ici (pas besoin de log, les
      // écarts de fréquence par attribut restent modestes en pratique).
      const t = maxCount === minCount ? 1 : (count - minCount) / (maxCount - minCount);
      span.style.fontSize = `${13 + t * 17}px`;
      span.innerHTML = `${value}<span class="taxo-count">${count}</span>`;
      span.addEventListener("click", () => taxoJumpToGalerie(label, value));
      cloud.appendChild(span);
    }

    group.appendChild(h);
    group.appendChild(cloud);
    taxoContentEl.appendChild(group);
  }
}

taxoLoadBtn.addEventListener("click", async () => {
  const folders = await refreshLibSummaryEl(taxoLibSummary);
  if (!folders.length) { alert("Ajoute d'abord un dossier dans l'onglet Bibliothèque."); return; }
  taxoLoadBtn.disabled = true;
  taxoSummaryEl.textContent = "Chargement…";
  try {
    const res = await fetch("/api/gallery/taxonomy");
    if (!res.ok) { taxoSummaryEl.textContent = "Erreur : " + (await res.text()); return; }
    const data = await res.json();
    taxoRender(data);
  } finally {
    taxoLoadBtn.disabled = false;
  }
});
