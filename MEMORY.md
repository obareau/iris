# Mémoire de session — Iris

Convention de travail pour ce dépôt, à suivre par tout assistant (Claude
Code ou autre) qui y intervient.

## En début de session

Lire `ROADMAP.md` (état d'avancement, ce qui reste ouvert) et
`CHANGELOG.md` (historique des versions) avant de commencer — pour ne pas
dupliquer un travail déjà fait, ni revenir sur une décision déjà prise.

## En fin de session

1. Mettre à jour `ROADMAP.md` (cocher les items terminés, ajouter les
   nouveaux items ouverts) et `CHANGELOG.md` (nouvelle entrée de version)
   pour refléter le travail effectué pendant la session.
2. `git commit` les changements.
3. `git push`.

⚠️ **Le remote `origin` pointe vers `https://github.com/obareau/iris.git`**
— le dépôt de l'auteur d'origine, pas un fork appartenant à l'utilisatrice
de cette machine (`claire`). Avant de pousser, vérifier que l'utilisatrice a
bien les droits d'écriture dessus (ou confirmer avec elle la destination
voulue — son propre fork, par exemple) plutôt que de supposer que `git push`
ira au bon endroit.

⚠️ **`iris.service` ne doit jamais être commité tel quel sur cette
machine** — `User=claire` et les chemins `/home/claire/DEVS/iris` sont
propres à cette installation, pas au dépôt partagé (le fichier d'origine
référence `olivier`/`/home/olivier/DEV/iris`). Laisser ce fichier modifié
et non indexé ; ne pas l'ajouter au commit de fin de session.

## Journal des sessions

- **2026-07-26** — Mise en place du service systemd + watchdog HTTP.
  Nouveau thème artbook « Catalogue » (A4, gabarits `price-grid` et
  `product-list`) + mode `chapter_by="size"`. Script `import_catalogue.py`
  (import d'un catalogue `.odt` existant). Édition/masquage des prix en
  masse (Galerie). Rédaction de `CATALOGUE.md`. Puis un guide complet
  d'Iris (artbook + catalogue en avant) publié en Artifact et exporté en
  PDF (`~/Téléchargements/iris-guide.pdf`) — ce guide vit hors du dépôt
  (scratchpad de session), pas versionné ici.
