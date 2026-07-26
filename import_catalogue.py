#!/usr/bin/env python3
"""Importe un catalogue produits LibreOffice (.odt) dans la bibliothèque Iris.

Le document est un zip ODF ; content.xml contient, par produit, un bloc
<table:table> (nom, Référence, Prix, description avec la taille "NN x NN cm").
L'image associée est soit à l'intérieur de ce même tableau, soit dans le
paragraphe qui le précède immédiatement (cas des lots de cartes postales,
où la photo est ancrée avant le tableau plutôt que dedans) — les deux formes
coexistent dans ce document, d'où le suivi séquentiel ci-dessous plutôt qu'une
simple recherche d'image "dans" chaque tableau.

Les blocs gabarits vides (sections Tableaux/Photos non remplies, ou lignes
"Insérez votre photo ici" laissées de côté par l'artiste) n'ont aucune image
réelle — ils sont ignorés automatiquement (pas de href = pas de produit).

Usage: python3 import_catalogue.py <catalogue.odt> [dossier_dest]
"""

import json
import re
import sys
import zipfile
from pathlib import Path

SECTIONS = ("Cartes postales", "Dessins", "Aquarelles", "Tableaux", "Photos")
# Sections réellement exploitées comme catalogue de vente (Tableaux/Photos
# sont les gabarits vides du template, cf. docstring du module).
IMPORTED_SECTIONS = ("Cartes postales", "Dessins", "Aquarelles")

DEFAULT_DEST = Path.home() / "Photos" / "catalogue_produits"

_EVENT_RE = re.compile(
    r'<text:p[^>]*>(?:Cartes postales|Dessins|Aquarelles|Tableaux|Photos)</text:p>'
    r'|<draw:image[^>]+xlink:href="([^"]+)"'
    r'|<table:table\b.*?</table:table>',
    re.S,
)
_SECTION_HEADER_RE = re.compile(r'^<text:p[^>]*>(.+)</text:p>$', re.S)


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("&amp;", "&").replace("&apos;", "'")


def _parse_product(table_xml: str, href: str | None) -> dict | None:
    if not href:
        return None  # gabarit vide (pas d'image réelle) — cf. docstring
    paras = [_strip_tags(p).strip() for p in re.findall(r"<text:p[^>]*>(.*?)</text:p>", table_xml, re.S)]
    paras = [p for p in paras if p]
    if not paras:
        return None
    name, ref, price, desc_parts = paras[0], None, None, []
    for t in paras[1:]:
        m = re.match(r"Référence\s*:\s*(.+)", t)
        if m:
            ref = m.group(1).strip()
            continue
        m = re.match(r"Prix\s*:\s*(.+)", t)
        if m:
            price = m.group(1).strip()
            continue
        desc_parts.append(t)
    desc = " ".join(desc_parts)
    if not ref or not price:
        return None  # pas un vrai bloc produit (ex. reliquat de mise en page)
    size_m = re.search(r"(\d+[.,]?\d*)\s*x\s*(\d+[.,]?\d*)\s*cm", desc, re.I)
    size = f"{size_m.group(1)} x {size_m.group(2)} cm" if size_m else None
    return {"href": href, "name": name, "ref": ref, "price": price, "size": size, "desc": desc}


def parse_catalogue(content_xml: str) -> list[dict]:
    """Balaie le document dans l'ordre, associe chaque tableau-produit à la
    dernière image rencontrée (dans le tableau, ou juste avant), sous la
    section en cours."""
    products = []
    section = None
    pending_href = None
    for m in _EVENT_RE.finditer(content_xml):
        chunk = m.group(0)
        if chunk.startswith("<text:p"):
            section = _strip_tags(chunk).strip()
            continue
        if chunk.startswith("<draw:image"):
            pending_href = m.group(1)
            continue
        # <table:table ...>
        inline_href_m = re.search(r'xlink:href="([^"]+)"', chunk)
        href = inline_href_m.group(1) if inline_href_m else pending_href
        pending_href = None
        if section not in IMPORTED_SECTIONS:
            continue
        product = _parse_product(chunk, href)
        if product:
            product["section"] = section
            products.append(product)
    return products


def import_catalogue(odt_path: Path, dest_root: Path) -> list[dict]:
    dest_root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(odt_path) as zf:
        content_xml = zf.read("content.xml").decode("utf-8")
        products = parse_catalogue(content_xml)

        report = []
        for p in products:
            ext = Path(p["href"]).suffix.lower() or ".jpg"
            section_dir = dest_root / p["section"]
            section_dir.mkdir(parents=True, exist_ok=True)
            img_dest = section_dir / f"{p['ref']}{ext}"
            with zf.open(p["href"]) as src, open(img_dest, "wb") as dst:
                dst.write(src.read())

            attributes = [{"label": "Nom", "value": p["name"]}, {"label": "Référence", "value": p["ref"]}]
            if p["size"]:
                attributes.append({"label": "Taille", "value": p["size"]})
            attributes.append({"label": "Prix", "value": p["price"]})
            sidecar = {
                "category_label": p["section"],
                "details": p["desc"],
                "attributes": attributes,
            }
            img_dest.with_suffix(".json").write_text(
                json.dumps(sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            report.append({**p, "dest": str(img_dest)})
        return report


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <catalogue.odt> [dossier_dest]")
        sys.exit(1)
    odt_path = Path(sys.argv[1]).expanduser()
    dest_root = Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else DEFAULT_DEST
    report = import_catalogue(odt_path, dest_root)

    by_section: dict[str, int] = {}
    no_size = 0
    for p in report:
        by_section[p["section"]] = by_section.get(p["section"], 0) + 1
        if not p["size"]:
            no_size += 1

    print(f"{len(report)} produits importés dans {dest_root}")
    for section, n in by_section.items():
        print(f"  {section}: {n}")
    if no_size:
        print(f"  ⚠ {no_size} produits sans taille détectée (attribut Taille absent)")
