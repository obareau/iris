# Roadmap Iris

Iris a commencé comme un simple trieur (catégorie/couleur/format) et est devenu,
au fil des demandes, un outil de documentation complet : galerie à facettes,
détection de doublons, graphe de similarité/identité, taxonomie, score
esthétique, vérification de canon contre le lore, bibliothèque multi-dossiers,
MCP en lecture seule. Ce document liste ce qui reste à faire, priorisé par
valeur/effort plutôt que par ordre d'idée.

## Phase 1 — Rapide, valeur immédiate

- [x] **Santé de la bibliothèque** (onglet Bibliothèque) — par dossier : nombre
      de photos, combien sans sidecar / sans score esthétique / sans verdict de
      canon, dossier accessible ou non. Fait le 2026-07-23.
- [x] **README.md à jour** — reflète maintenant tous les onglets, le score
      esthétique, la vérification de canon, le MCP. Fait le 2026-07-23.
- [x] ~~Notifications ntfy sur fin de job long~~ — écarté par Olivier
      (2026-07-23), pas d'intérêt perçu pour cet usage.
- [ ] **Étendre le pipeline complet** — "Tout faire d'un coup" enchaîne
      analyse→détails→attributs→applique ; ajouter deux étapes optionnelles
      (score esthétique, vérification canon) pour un gros import traité de bout
      en bout sans repasser par la Galerie ensuite.

## Phase 2 — Nécessite un peu de conception

- [x] **Nommer les identités récurrentes** — champ `character_name` au
      sidecar, assignable depuis la Galerie ou le Graphe (mode identité).
      Depuis le Graphe : "Appliquer au voisinage affiché" — le voisinage
      direct du nœud tapé (celui qui est visuellement mis en évidence), pas
      la composante connexe entière du graphe. Fait le 2026-07-23.
      ⚠️ **Piège vécu en testant** : la première version utilisait
      `cy.elements().components()` (composante connexe complète) — a
      appliqué un nom test à 123 photos au lieu des ~6 visibles à l'écran,
      via une chaîne d'arêtes faibles reliant deux groupes visuellement
      distincts. Corrigé en réutilisant le voisinage déjà calculé pour le
      surlignage au clic (`closedNeighborhood()`, 1 saut) plutôt que de
      recalculer une composante globale.
- [x] **Vérification de canon manuelle** — sélecteur de faction dans la
      Galerie ("Deviner automatiquement" par défaut, ou une faction précise
      des 36 du vault). Fait le 2026-07-23.
- [x] **Verdict de canon plus discriminant** — `canon.faction_similarity()`
      calcule un score CLIP image↔lore indépendant du verdict texte ; un
      "conforme" du VLM est automatiquement rétrogradé en "douteux" si ce
      score est trop bas (< 5%) pour la faction en question. Testé en réel :
      un "conforme" sur une faction manifestement fausse (C.G.U. sur un
      personnage cyberpunk Renégat) est bien rétrogradé, confiance CLIP 0%
      affichée. Fait le 2026-07-23.
- [x] **Filtre dossier source dans Doublons/Graphe** — sélecteur "Dossier
      source" dans les deux onglets, en plus du filtre catégorie. Fait le
      2026-07-23.

## Phase 3 — Plus gros chantiers, exploratoire

- [x] **Auto-scan périodique de `_a_trier`** — timer systemd user
      (`iris-auto-scan.timer`, toutes les 15 min, comme recta-renegat) qui
      déclenche `/api/analyze` automatiquement quand des fichiers non encore
      analysés attendent dans `_a_trier`. Le script (`~/scripts/
      iris-auto-scan.sh`) ne relance rien si le dossier est vide, une analyse
      tourne déjà, ou les résultats déjà en mémoire couvrent déjà tout le
      dossier (évite de re-brûler du GPU en boucle tant que personne n'a
      appliqué le tri). Testé en réel : déclenche bien sur un fichier neuf,
      n'agit pas au second passage. Fait le 2026-07-23.
- [x] **Export portfolio / planche contact** — page HTML autonome (images en
      base64, zéro dépendance externe) générée depuis la sélection de la
      Galerie (`backend/portfolio.py`), servie via `/exports`, ouverte
      automatiquement dans un nouvel onglet. Fait le 2026-07-23.
- [x] **Taxonomie croisée** — section "Analyse croisée" dans l'onglet
      Taxonomie, croise deux attributs (ou pseudo-attributs : Catégorie,
      Faction devinée, Verdict canon, Personnage) en table de comptage. Fait
      le 2026-07-23.
- [x] **Suivi Argus** — Iris ajouté à `~/DEV/Argus/projects.yaml` (`extra:`),
      CHANGELOG.md provisionné. Fait le 2026-07-23.

## Déjà fait (pour mémoire, ne pas refaire)

Galerie à facettes (recherche sémantique CLIP, filtres attributs, sélection en
masse) · Doublons (union-find + similarité CLIP) · Graphe similarité + identité
· Taxonomie (nuage de mots) · Recta (timeline des publications) · Score
esthétique (IA) · Vérification de canon contre le lore Robotariis (auto ou
faction choisie, score CLIP discriminant) · Nommage des identités récurrentes
(Galerie + Graphe) · EXIF write-back · Bibliothèque multi-dossiers avec
raccourcis réseau/USB/montages + santé par dossier · Filtre dossier source
dans Doublons/Graphe · MCP `iris` (lecture seule, 5 outils) · Pipeline complet
en un clic · Annulation de job sur les 6 types de tâche longue · Auto-scan
périodique de `_a_trier` · Export en planche contact · Taxonomie croisée ·
Suivi Argus.

## Reste ouvert

- [x] **Étendre le pipeline complet** (Phase 1) — le score esthétique était
      déjà calculé automatiquement à l'application (`organizer.apply_moves`),
      rien à ajouter là. Ajouté une case à cocher "Vérifier le canon après
      application" (décochée par défaut — un appel Qwen2-VL par photo, plus
      coûteux qu'un score esthétique). `organizer.apply_moves` renvoie
      maintenant `applied_paths`, chaînés vers `/api/gallery/canon` si coché.
      Testé en réel sur un dossier isolé : sidecar final avec aesthetic_score
      ET canon_faction/verdict/clip_confidence en une seule passe. Fait le
      2026-07-23.

Roadmap initiale (Phases 1-3) intégralement traitée.

## Phase 4 — Catalogue produits (2026-07-26)

- [x] **Déploiement permanent** — service systemd `iris.service` (installé,
      `enable`d, `Restart=on-failure`) + watchdog HTTP (`watchdog.sh` +
      `iris-watchdog.timer`, toutes les 30 s, `systemctl restart` si
      injoignable) pour couvrir aussi un plantage silencieux/deadlock (pas
      seulement un process qui meurt). Testé en réel : process gelé
      (`SIGSTOP`) détecté et relancé automatiquement.
- [x] **Chapitres par taille + grille tarifaire** — nouveau mode
      `chapter_by="size"` dans `compose_model()` (bandes de surface cm²,
      indépendant de la catégorie sémantique CLIP) et nouveau gabarit
      `price-grid` (Catégorie / Dimensions / Prix le plus fréquent, hors
      pièces à 0,00 € = vendues/indisponibles).
- [x] **Thème "Catalogue"** — A4 portrait (au lieu du carré 210×210 mm des
      autres thèmes), Noto Serif embarquée, vert `#2e5e4e`, calqué sur un
      catalogue produits `.odt` de référence (couleurs extraites de
      `styles.xml`/`content.xml`, mise en page comparée visuellement via
      export PDF LibreOffice headless). Format de page généralisé par thème
      (`THEME_TRIM_MM`) y compris pour l'export imprimeur (fond
      perdu/traits de coupe, jusque-là hardcodé carré).
- [x] **Gabarit `product-list`** — liste compacte de fiches produit
      (jusqu'à 5/page, image en `object-fit:contain` jamais rognée — la
      majorité des photos sources sont en format paysage ou des photos
      composites de plusieurs pièces). Remplace le gabarit plein-page pour
      ce thème. Hauteur de ligne fixe (46 mm) plutôt qu'un `flex:1` qui
      étirait la ligne (et l'image) sur toute la page quand il y avait peu
      de produits sur une page.
- [x] **`import_catalogue.py`** — importe un catalogue LibreOffice `.odt`
      (même structure que le document de référence : un tableau par
      produit, image + nom + Référence + Prix + description avec la
      taille) dans la bibliothèque Iris, sidecar JSON natif (`attributes`:
      Nom/Référence/Taille/Prix). Ignore automatiquement les blocs gabarits
      vides du document (pas d'image réelle = pas de produit). Testé sur le
      catalogue réel : 235 produits importés (186 cartes postales, 42
      dessins, 7 aquarelles).
- [x] **Édition/masquage des prix en masse** — barre d'outils Galerie :
      champ Prix + "Appliquer le prix" (fixe la valeur sur la sélection),
      "Masquer les prix"/"Afficher les prix" (réversible, la valeur reste
      en sidecar — nouveau champ `hidden_attributes`, mécanisme générique
      pas limité au prix). `_attr()`/`_spec_for()` (artbook.py) l'ignorent
      tant qu'il est masqué. Deux endpoints :
      `/api/gallery/attribute/bulk`, `/api/gallery/attribute/hide`.
- [x] **CATALOGUE.md** — doc complète (thème, structure par taille, import
      `.odt`, édition/masquage de prix, marche à suivre de bout en bout),
      liée depuis README.md.

### Reste ouvert

- [ ] Génération du catalogue complet (235 photos) dans le thème Catalogue
      — validé seulement sur des échantillons de test (8-12 pages) jusqu'ici.
- [ ] Export imprimeur (CMJN/traits de coupe) du thème Catalogue en A4 —
      la génération de dimensions est généralisée (`_print_dims`) mais pas
      testée avec un vrai fichier imprimeur A4 (seulement le rendu PDF
      standard, non fond-perdu).
