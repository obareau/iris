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
