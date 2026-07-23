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

- [ ] **Nommer les identités récurrentes** — le mode Identité du Graphe détecte
      déjà qu'un groupe de photos montre le même personnage (crop YOLO + CLIP),
      mais le regroupement reste anonyme. Ajouter un champ `character_name` au
      sidecar, assignable depuis le Graphe ou la Galerie, puis exploitable comme
      filtre ("toutes les photos de Zoé") — rapprocherait Iris du travail déjà
      fait par Atlas sur les personnages.
- [ ] **Vérification de canon manuelle** — actuellement la faction est toujours
      devinée (CLIP zero-shot). Ajouter un sélecteur de faction explicite pour
      forcer la vérification contre une faction précise, utile quand le guess se
      trompe ou pour tester délibérément une hypothèse ("est-ce que ça pourrait
      passer pour un Renégat ?").
- [ ] **Verdict de canon plus discriminant** — le petit VLM (Qwen2-VL-2B) a un
      biais de complaisance documenté (dit "conforme" même sur une faction
      manifestement fausse, cf. article de blog *Le fond blanc mentait*).
      Envisager de compléter le verdict texte par un score de similarité
      CLIP image↔lore (déjà calculé pour le guess), moins sujet à sycophance.
- [ ] **Filtre dossier source dans Doublons/Graphe** — utile pour restreindre une
      détection à un seul dossier de la bibliothèque quand un autre est lent
      (réseau) ou volumineux, sans le retirer du catalogue.

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
esthétique (IA) · Vérification de canon contre le lore Robotariis · EXIF
write-back · Bibliothèque multi-dossiers avec raccourcis réseau/USB/montages ·
MCP `iris` (lecture seule, 5 outils) · Pipeline complet en un clic · Annulation
de job sur les 6 types de tâche longue.
