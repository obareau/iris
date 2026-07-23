"""Raccourcis de navigation pour la modale "Choisir un dossier" — Accueil,
Images, clés USB, disques réseau (SMB/NFS), montages génériques. Détectés
dynamiquement via /proc/mounts, même approche que Nemesis (server/routes/
browse.js) : pas de liste figée, ça marche pareil qu'un disque soit branché
ou débranché depuis le dernier redémarrage d'Iris."""

import re
from pathlib import Path

NETWORK_FSTYPES = {"cifs", "smb3", "nfs", "nfs4", "smbfs", "sshfs", "davfs", "fuse.sshfs"}
PSEUDO_FSTYPES = {
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2", "securityfs",
    "pstore", "bpf", "debugfs", "tracefs", "configfs", "fusectl", "mqueue", "hugetlbfs",
    "binfmt_misc", "autofs", "overlay", "squashfs", "ramfs", "efivarfs",
}

_OCTAL_ESCAPE_RE = re.compile(r"\\([0-7]{3})")


def _unescape_mount_field(text: str) -> str:
    """/proc/mounts encode espaces/tabs/antislashs en octal (\\040 = espace)."""
    return _OCTAL_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 8)), text)


def _read_mount_points() -> list[dict]:
    mounts = []
    for line in Path("/proc/mounts").read_text().splitlines():
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) < 3:
            continue
        source, target, fstype = parts[0], parts[1], parts[2]
        mounts.append({
            "source": _unescape_mount_field(source),
            "target": _unescape_mount_field(target),
            "fstype": fstype,
        })
    return mounts


def list_shortcuts() -> list[dict]:
    shortcuts = []
    home = Path.home()
    shortcuts.append({"label": "Accueil", "group": "local", "path": str(home)})

    pictures = home / "Pictures"
    if pictures.is_dir():
        shortcuts.append({"label": "Images", "group": "local", "path": str(pictures)})

    # Favoris propres à Iris — les deux dossiers qu'on réutilise sans cesse
    # dans cette appli (dossier canonique de sortie + staging Recta).
    for label, sub in (("Photos classées", "renegats-photos/_classees"), ("Photos à trier", "renegats-photos/_a_trier")):
        candidate = home / sub
        if candidate.is_dir():
            shortcuts.append({"label": label, "group": "local", "path": str(candidate)})

    try:
        mounts = _read_mount_points()
    except Exception:
        mounts = []

    for m in mounts:
        target, fstype = m["target"], m["fstype"]
        if fstype in PSEUDO_FSTYPES:
            continue
        if target == "/" or target == "/boot" or target.startswith("/boot/"):
            continue
        if target.startswith("/var/") or (target.startswith("/run/") and "/media/" not in target):
            continue
        if target.startswith("/snap/"):
            continue

        is_network = fstype in NETWORK_FSTYPES
        is_removable = target.startswith("/media/") or target.startswith("/run/media/")
        label = Path(target).name or target

        if is_network:
            shortcuts.append({"label": f"🌐 {label}", "group": "network", "path": target, "detail": m["source"]})
        elif is_removable:
            shortcuts.append({"label": f"💾 {label}", "group": "removable", "path": target, "detail": fstype})
        elif target.startswith("/mnt/"):
            shortcuts.append({"label": f"📦 {label}", "group": "mount", "path": target, "detail": fstype})

    return shortcuts
