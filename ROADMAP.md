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

- [ ] **Auto-scan périodique de `_a_trier`** — timer systemd (comme les timers
      Recta) qui déclenche l'analyse automatiquement quand des fichiers
      apparaissent, sans clic manuel sur "Analyser".
- [ ] **Export portfolio / planche contact** — générer une page web ou un PDF
      d'une sélection de photos pour la partager hors d'Iris (revue, référence
      externe), au lieu de dépendre uniquement de la Galerie.
- [ ] **Taxonomie croisée** — croiser deux attributs (ex: Faction devinée ×
      Verdict canon, ou Catégorie × Note) pour repérer des incohérences en masse
      plutôt qu'attribut par attribut.
- [ ] **Suivi Argus** — ajouter Iris à `~/DEV/Argus/projects.yaml` (`extra:`)
      pour bénéficier du provisioning auto ROADMAP/CHANGELOG et du contexte
      `argus_context()` en début de session, comme les projets sous `~/DEV`.

## Déjà fait (pour mémoire, ne pas refaire)

Galerie à facettes (recherche sémantique CLIP, filtres attributs, sélection en
masse) · Doublons (union-find + similarité CLIP) · Graphe similarité + identité
· Taxonomie (nuage de mots) · Recta (timeline des publications) · Score
esthétique (IA) · Vérification de canon contre le lore Robotariis (auto ou
faction choisie, score CLIP discriminant) · Nommage des identités récurrentes
(Galerie + Graphe) · EXIF write-back · Bibliothèque multi-dossiers avec
raccourcis réseau/USB/montages + santé par dossier · Filtre dossier source
dans Doublons/Graphe · MCP `iris` (lecture seule, 5 outils) · Pipeline complet
en un clic · Annulation de job sur les 6 types de tâche longue.
