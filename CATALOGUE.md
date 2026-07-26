# Générer un catalogue produits avec Iris

Iris peut produire un catalogue de vente (cartes postales, dessins,
aquarelles…) directement depuis la bibliothèque, avec grille tarifaire et
mise en page dédiée. Ce document couvre le thème **Catalogue**, le script
d'import depuis un `.odt` existant, et l'édition de prix en masse.

---

## 1. Le thème "Catalogue"

Dans le wizard artbook (étape **2. Style**), le thème s'appelle **Catalogue**
(valeur interne `theme: "catalogue"`). Il est distinct des thèmes Éditorial et
Brutaliste :

| | Éditorial / Brutaliste | Catalogue |
|---|---|---|
| Format | carré 210×210 mm | **A4 portrait** (210×297 mm) |
| Police | Helvetica / IBM Plex | **Noto Serif** (embarquée) |
| Couleur d'accent | doré / orange | **vert profond `#2e5e4e`** |
| Mise en page produit | 1 photo pleine page + fiche technique | **liste compacte, jusqu'à 5 fiches par page** |
| Recadrage image | `object-fit: cover` (rogné) | **`object-fit: contain`** (jamais rogné — pensé pour des photos majoritairement en format paysage) |

Le style est calqué sur un catalogue produits réel (fichier `.odt` fourni),
converti en PDF via LibreOffice headless pour en extraire les couleurs
(`styles.xml`/`content.xml` : vert `#2e5e4e`, gris `#6b6b6b`) et la mise en
page (liste de fiches bordées, filets fins, typographie serif).

### Gabarits spécifiques à ce thème

- **`price-grid`** — grille tarifaire (Catégorie / Dimensions / Prix), générée
  automatiquement quand la structure "Par taille" est choisie (voir §2).
- **`product-list`** — liste de fiches produit (vignette + nom / référence /
  prix / description), 5 par page. C'est le gabarit qui remplace la page
  pleine photo des autres thèmes pour un rendu catalogue.

---

## 2. Structure "Par taille" + grille tarifaire

Dans le wizard, étape **3. Structure**, choisir **"Chapitres par taille"**
(`chapter_by: "size"`). Effets :

1. Les photos sont regroupées par bande de surface (cm²), pas par catégorie
   sémantique :

   | Catégorie | Seuil de surface | Exemple |
   |---|---|---|
   | Petit format | ≤ 300 cm² | cartes postales 10×15 cm |
   | Format moyen | 300–900 cm² | 22×30 cm, 23×32 cm |
   | Grand format | 900–1800 cm² | 30×42 cm |
   | Très grand format | > 1800 cm² | 42×55 cm, 42×60 cm |

   La bande est déduite de l'attribut **Taille** de chaque photo (ex.
   `"30 x 42 cm"`) — sans cet attribut, la photo part dans un chapitre de
   repli "Format non renseigné".

2. Une page **Grille tarifaire** est insérée automatiquement en tête de
   livre (après la couverture), avec pour chaque catégorie : les dimensions
   observées et le **prix le plus fréquent** dans les données réelles (les
   prix à `0,00 €` — pièce vendue/indisponible — sont ignorés dans ce
   calcul).

3. Les chapitres sont triés du plus petit au plus grand format (pas par
   score esthétique).

---

## 3. Importer un catalogue existant (`.odt` → Iris)

Le script `import_catalogue.py` (racine du dépôt) lit un catalogue LibreOffice
Writer construit sur le même modèle que le fichier de référence (un tableau
par produit : image + nom + `Référence :` + `Prix :` + description avec la
taille en `NN x NN cm`) et importe chaque produit comme une photo Iris.

```bash
python3 import_catalogue.py catalogue_produits.odt [dossier_destination]
# défaut : ~/Photos/catalogue_produits/
```

Ce que fait le script :

- Repère chaque section remplie du document (`Cartes postales`, `Dessins`,
  `Aquarelles`) — les sections gabarits vides (ex. `Tableaux`, `Photos` non
  remplies, lignes "Insérez votre photo ici") sont ignorées automatiquement
  (pas d'image réelle = pas de produit).
- Extrait l'image de chaque produit (qu'elle soit dans le tableau du produit
  ou dans le paragraphe juste avant — les deux formes existent dans le
  document) vers `<destination>/<Section>/<Référence>.<ext>`.
- Écrit à côté un sidecar Iris (`<Référence>.json`) avec :
  - `category_label` = la section (ex. "Dessins")
  - `attributes` = `Nom`, `Référence`, `Taille`, `Prix`

Aucune autre étape n'est nécessaire : `gallery.list_gallery()` lit ces
sidecars nativement, donc les photos apparaissent dans Bibliothèque/Galerie
avec leurs attributs comme n'importe quelle photo déjà triée par Iris.

**Ensuite**, dans Iris :
1. Onglet **Bibliothèque** → ajouter `<dossier_destination>`.
2. Onglet **Galerie** → Charger → sélectionner les photos voulues (ou "Tout
   sélectionner (visible)").
3. **📖 Composer un artbook** → thème *Catalogue*, structure *Par taille*.

---

## 4. Éditer / masquer les prix en masse

Dans la Galerie, une fois une sélection de photos faite (barre d'outils qui
apparaît en haut de la grille) :

| Contrôle | Effet |
|---|---|
| Champ **Prix** + **Appliquer le prix** | Fixe (ou crée) l'attribut `Prix` à la même valeur pour toutes les photos sélectionnées — utile pour un solde, un arrondi de gamme, ou une correction après import. |
| **Masquer les prix** | Retire le prix de l'affichage (grille tarifaire, fiches produit) **sans effacer la valeur** — pour publier une version d'un catalogue sans les prix (ex. envoi à l'imprimeur, consultation interne). |
| **Afficher les prix** | Annule le masquage — le prix réapparaît, valeur intacte. |

### Détails techniques

Le masquage utilise un champ dédié du sidecar, `hidden_attributes` (liste de
labels en minuscules), distinct de `attributes`. `_attr()` (dans
`backend/artbook.py`, utilisé par la grille tarifaire, les fiches produit et
la fiche technique brutaliste) ignore tout attribut listé dans
`hidden_attributes` — la donnée reste sur disque, seul l'affichage change.
Réversible à tout moment.

Le mécanisme est générique (pas limité à "Prix") : n'importe quel label
d'attribut peut être masqué de la même façon via
`POST /api/gallery/attribute/hide` (`{paths, label, hidden}`).

### API (pour scripts/automatisation)

```bash
# Fixer un prix sur plusieurs photos
curl -X POST http://localhost:8800/api/gallery/attribute/bulk \
  -H "Content-Type: application/json" \
  -d '{"paths": ["/chemin/photo1.jpg", "/chemin/photo2.jpg"], "label": "Prix", "value": "25,00 €"}'

# Masquer le prix sur plusieurs photos
curl -X POST http://localhost:8800/api/gallery/attribute/hide \
  -H "Content-Type: application/json" \
  -d '{"paths": ["/chemin/photo1.jpg"], "label": "Prix", "hidden": true}'
```

---

## 5. Récapitulatif — générer un catalogue de A à Z

1. `python3 import_catalogue.py mon_catalogue.odt` (ou saisie/import manuel
   des photos + attributs `Taille`/`Prix` via l'inspecteur Galerie).
2. Bibliothèque → ajouter le dossier importé.
3. Galerie → Charger → sélectionner les photos → ajuster les prix en masse
   si besoin (§4).
4. **📖 Composer un artbook** :
   - Style : **Catalogue**
   - Structure : **Chapitres par taille**
   - (les autres réglages — reliure, intercalaires — sont optionnels, un
     catalogue n'a en général pas besoin de citations Recta/pirate)
5. **Composer**, vérifier dans l'éditeur, **Export PDF**.
