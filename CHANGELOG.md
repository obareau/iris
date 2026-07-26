# Iris — Changelog

## [0.5.0] — 2026-07-26 · Zine & cartels d'œuvre

### Ajouté
- **Zine 8 pages sur une feuille pliée** — objet promo tiré chez soi à l'unité,
  sans reliure ni minimum de commande. Formats A4 (pages 74 × 105 mm) et A3
  (105 × 148 mm), pages de texte au choix (lore canon, descriptions extraites,
  citations, aucune), QR vectoriel au dos, repères de pli et de coupe
  décochables.
- **Tramage 1 bit** (`backend/dither.py`) — clustered-dot, Atkinson,
  Floyd–Steinberg, seuil. Nécessaire et non décoratif : une photocopieuse ne
  pose que du noir ou rien ; sans trame choisie, le pilote en applique une
  quelconque et les demi-teintes tournent en bouillie.
- **Cartel d'œuvre** — nom, technique, taille, année, pays, rendus dans la
  convention des catalogues d'exposition. Stockés comme attributs ordinaires du
  sidecar : ils héritent de l'édition en masse, du masquage, des facettes de la
  Galerie et de l'écriture EXIF sans une ligne de code en plus.
- **Verrou d'accès aux dossiers** — `POST /api/folder/check` diagnostique un
  chemin avant tout job (six cas distingués, remontée au parent existant le plus
  proche) et une modale explique quoi corriger, avec accès direct au navigateur
  de dossiers. Posé sur les quatre points d'entrée.

### Réutilisé
- Trames portées de **MONO°** (`~/DEV/mono`), imposition « fringearts » reprise
  de **Recta** (`zine-gen.ts`). Portées et créditées plutôt qu'appelées : une
  dépendance entre projets aurait coûté plus en fragilité que la copie ne coûte
  en duplication.

### Corrigé
- Purge automatique des rendus (`exports/` atteignait 629 Mo — 460 Mo libérés,
  plafond à 40 rendus, les projets jamais touchés).
- CSS de l'éditeur : trois blocs qui se corrigeaient l'un l'autre fusionnés,
  taille de miniature déclarée une seule fois. Vérifié par comparaison des
  styles calculés : aucun écart.

## [0.4.0] — 2026-07-26 · Thème Catalogue & déploiement permanent

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
- Guide complet d'Iris (vue d'ensemble + artbook/catalogue en avant),
  publié en artifact et exporté en PDF — document hors dépôt, pas de
  fichier source versionné ici.

## [0.3.0] — 2026-07-26 · Prépresse & mise en public

### Ajouté
- **Export imprimeur** en trois profils, parce que les destinations n'attendent
  pas le même fichier : *Blurb/Lulu* (RVB, 216 mm, sans repères), *Pixartprinting*
  (CMJN Fogra 39), *Atelier* (CMJN + équerres de coupe, feuille 226 mm).
- **Séparation CMJN** via Ghostscript + profil `FOGRA39L_coated`, images à
  ~300 dpi non rééchantillonnées.
- **Traitement du noir** : les aplats neutres repassent en DeviceGray (pikepdf)
  avant séparation, pour que le texte tienne sur la **seule plaque noire** au
  lieu d'un noir riche à ~300 % d'encre sur quatre plaques.
- **Zone tranquille** de 12,7 mm pour les textes posés sur une image à fond perdu.
- `IMPRESSION.md` — relevé des specs chez Pixartprinting, Lulu, Blurb, CEWE.
- `PORTAGE.md` — dépendances réelles, install GPU AMD/ROCm, données à emporter.
- README réécrit avec captures d'écran ; dépôt GitHub passé **public**.

### Corrigé
- Les trois imprimeurs en ligne exigent un PDF **sans** traits de coupe : le
  premier export en ajoutait et aurait été refusé.
- Équerres de coupe passées de 0,36 pt / 3,4 mm (invisibles) à ~0,7 pt / 5 mm,
  démarrant au bord de feuille et s'arrêtant au fond perdu.

### Connu / non traité
- Pas de croix de repérage (la couleur « repérage » n'est pas exprimable depuis
  HTML) — elles sont ajoutées par le RIP de l'imprimeur à l'imposition.
- Encrage total (TAC) non plafonné ; PDF/X-3 non généré.

## [0.2.0] — 2026-07-25 · Module artbook & refonte de l'interface

### Ajouté — composition de livres
- **Wizard de création** en 5 étapes (couverture, style, structure, reliure,
  récapitulatif) en remplacement des `prompt()`/`confirm()` en cascade.
- **Éditeur de A à Z** : glisser-déposer des pages et des photos, photothèque
  sur toute la bibliothèque avec recherche, gabarit qui suit le nombre de photos
  (1→pleine, 2→duo, 3→trio, 4→grille), légendes par photo, undo, duplication,
  changement de couverture et de thème.
- **Aperçu live** : iframe du rendu serveur à côté des formulaires, rafraîchie en
  débounce — même moteur que le PDF, donc strictement identique au fichier final.
- **Chemin de fer** : le livre en planches (pages en vis-à-vis) avec ombre de
  pliure ; un panoramique compte pour deux pages physiques et s'affiche en deux
  moitiés ; alerte quand la parité est cassée.
- **Reliure** : total calé sur un multiple de 4/8/16, cible de 24 pages par
  défaut, complétée par des intercalaires puisés dans le lore (communiqués Recta,
  émissions pirates avec esthétique glitch).
- **Pages liminaires** : page de garde, dédicace, quatrième de couverture.
- **Bibliothèque « Mes artbooks »** : rouvrir, renommer, dupliquer, supprimer.
- Encarts texte, panoramiques sur deux pages, index de fin, export PDF.

### Modifié — interface
- Toute l'app passe en **table de montage** (surface sombre) : un fond clair
  force l'œil à comparer les photos à du blanc et fausse la lecture des tons.
- Helvetica pour l'interface, IBM Plex Mono pour les données ; accent laiton.
- Chaque page de l'éditeur porte une **tranche de couleur** disant ce qu'elle est,
  et une miniature carrée reproduisant son vrai gabarit.
- Les dix boutons « + » deviennent un menu « Ajouter » sectionné.
- **Sélection façon explorateur** dans la Galerie : clic, Ctrl+clic, Maj+clic.

### Corrigé
- Pages fantômes à l'impression : collision de classe `rc-devise` (modificateur
  de page *et* classe de texte) qui débordait de 6 mm. N pages modèle = N pages
  physiques.
- Barre d'actions de la Galerie qui rognait ses libellés (hauteur figée 44 px).
- Photothèque limitée à la sélection d'origine : impossible d'ajouter une autre
  photo.
- `.field-check` en flex avec `input{width:100%}` : le libellé « Vérifier le
  canon » s'écrasait sur trois colonnes.

## [0.1.0] — 2026-07-23

- Initialisation du changelog par Argus (aucun historique antérieur documenté).
