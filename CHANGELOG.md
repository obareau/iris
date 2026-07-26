# Iris — Changelog

## [0.2.0] — 2026-07-26

- Déploiement permanent : service systemd (`iris.service`, `Restart=on-failure`)
  + watchdog HTTP (`iris-watchdog.timer`, relance sur plantage/deadlock).
- Nouveau mode `chapter_by="size"` (chapitres par bande de taille physique,
  cm²) et nouveau gabarit `price-grid` (grille tarifaire auto).
- Nouveau thème artbook **Catalogue** : A4 portrait, Noto Serif, vert
  `#2e5e4e`, gabarit `product-list` (fiches produit compactes, image en
  `contain` jamais rognée) — calqué sur un catalogue produits `.odt` de
  référence. Format de page (fond perdu, traits de coupe) généralisé par
  thème pour l'export imprimeur.
- `import_catalogue.py` : import d'un catalogue `.odt` existant dans la
  bibliothèque Iris (image + attributs Nom/Référence/Taille/Prix par
  produit, sections gabarits vides ignorées).
- Édition et masquage des prix en masse depuis la Galerie (réversible,
  nouveau champ sidecar `hidden_attributes`, mécanisme générique).
- Détection de Brave en plus de Chromium/Chrome pour l'export PDF.
- Nouvelle doc `CATALOGUE.md`.

## [0.1.0] — 2026-07-23

- Initialisation du changelog par Argus (aucun historique antérieur documenté).
