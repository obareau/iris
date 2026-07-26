# Faire imprimer un artbook Iris

Relevé fait le **2026-07-26** auprès des imprimeurs. Format de référence : le
carré **21 × 21 cm** que produit Iris.

---

## Le tableau de décision

| Imprimeur | Carré ~21 cm | Accepte un PDF | Fond perdu | Zone tranquille | Pages mini | Couleur |
|---|---|---|---|---|---|---|
| **Pixartprinting** | **sur-mesure → 21×21 exact** | oui, **sans repères** | 3 mm | — | — | **CMJN Fogra 39** |
| **Lulu** | 21,59 × 21,59 (8,5″) | oui | 3,18 mm | **12,7 mm** | **32** | RVB |
| **Blurb** | 18×18 ou 30×30 (pas de 21) | oui | 3,175 mm | 6,35 mm | — | RVB |
| **CEWE** | 21×21 | ❌ logiciel maison | — | — | 26 | — |

### Les deux règles que tout le monde partage

1. **Aucun trait de coupe.** Les trois qui acceptent un PDF veulent le fichier
   au format fini **+ 3 mm de fond perdu**, et rien d'autre. Ils imposent le
   massicot eux-mêmes ; un fichier avec équerres est rejeté ou mal interprété.
2. **Le fond perdu n'est pas optionnel** dès qu'une image touche le bord. Le
   massicot dévie toujours un peu : sans débord, on récupère un filet blanc.

---

## Recommandation

**Pixartprinting** si tu tiens au **21 × 21 exact** — c'est le seul à faire du
format sur-mesure, il imprime à l'unité et fait du livre d'art. C'est aussi le
seul qui demande du CMJN, ce qu'Iris sait produire (voir plus bas).

**Lulu** sinon : 21,59 cm au lieu de 21 (invisible à l'œil), fichier RVB, mais
il faut **32 pages minimum** — le défaut d'Iris est à 24, à remonter dans le
wizard (« Nombre de pages visé »).

**Blurb** seulement si tu acceptes de changer de format (18 ou 30 cm).

**CEWE** est hors-jeu pour un livre composé : il n'accepte pas de PDF prêt à
imprimer, tout doit passer par leur logiciel.

---

## Ce qu'Iris produit

Menu **Imprimeur** dans l'éditeur — trois destinations, parce qu'elles
n'attendent pas le même fichier.

| Choix | Pour qui | Feuille | Couleur | Repères |
|---|---|---|---|---|
| **Blurb · Lulu** | livre photo en ligne | 216 × 216 mm | RVB | aucun |
| **Pixartprinting** | imprimeur pro | 216 × 216 mm | **CMJN Fogra 39** | aucun |
| **Atelier** | imprimeur classique | 226 × 226 mm | CMJN | équerres de coupe |

216 mm = 210 de format fini + 3 mm de fond perdu de chaque côté.
226 mm = idem + 5 mm de marge pour tracer les équerres.

### Le traitement du noir (ce qui fait la différence)

Chromium écrit le texte en `0 0 0 rg` — du noir **RVB**. Séparé tel quel via un
profil ICC, ce noir devient un **noir riche** : C 79 · M 70 · J 53 · N 98, soit
~300 % d'encre réparties sur **quatre plaques**. Sur du petit texte, les quatre
doivent coïncider au poil ; au moindre décalage de repérage, les lettres
prennent une frange colorée.

Iris corrige en amont : tous les aplats **neutres** (r = v = b) repassent en
`DeviceGray` avant la séparation, et Ghostscript les envoie sur la **seule
plaque noire**. Les vraies couleurs — rouge Recta, laiton, ambre pirate — ne
sont pas touchées et restent en quadri.

Vérifié sur le fichier livré : **0 noir en quadri**, images CMJN à 300 ppi.

### Définition des images

Le mode imprimeur remonte les images à ~300 dpi (2600 px au lieu de 1600) et
desserre la compression JPEG à 95.

⚠️ **Iris ne peut pas inventer des pixels.** Une photo source de 1792 × 1024
tombe à ~120 dpi sur une page de 216 mm. La définition finale dépend de tes
photos, pas de l'export. Pour un tirage propre, viser des sources ≥ 2500 px sur
le côté le plus long des images pleine page.

---

## Marche à suivre

1. Composer le livre, **régler le nombre de pages selon l'imprimeur** (32 mini
   chez Lulu, multiple de 4 conseillé partout pour la reliure).
2. Vérifier le **chemin de fer** (bouton *Planches*) : les images panoramiques
   doivent tomber à cheval sur la pliure, pas être coupées par une planche
   incomplète.
3. Menu **Imprimeur** → la destination choisie.
4. Contrôler le PDF avant envoi : format de page (612 pts = 216 mm), nombre de
   pages, et qu'aucun texte important ne touche le bord.

### Contrôles en ligne de commande

```bash
# format et nombre de pages
pdfinfo mon-livre.pdf | grep -E "Pages|Page size"    # attendu : 612 x 612 pts

# espace couleur et définition réelle des images
pdfimages -list mon-livre.pdf | head
```

---

## Restes à traiter si besoin

- **PDF/X-3** : aucun des trois ne l'exige, mais un imprimeur traditionnel peut
  le demander (il embarque l'intention de sortie). Faisable via Ghostscript
  avec un fichier `PDFX_def.ps`.
- **Encrage total (TAC)** : non plafonné pour l'instant. Fogra 39 admet 330 % ;
  nos aplats photo peuvent frôler cette limite sur des noirs denses. À vérifier
  avec l'imprimeur pour un tirage offset sur papier non couché.
