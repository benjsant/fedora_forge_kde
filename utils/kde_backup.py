"""Sauvegarde et restauration de la configuration KDE Plasma.

Cree des archives tar.gz horodatees dans ~/.local/share/fedoraforgekde/backups/.
Couvre les fichiers que FedoraForgeKDE peut modifier (themes, raccourcis,
panels, KWin, screen locker, Kvantum, etc.) — pas un snapshot complet de Plasma.

Securite
--------
- Whitelist stricte des fichiers a inclure (CONFIG_FILES) — pas de glob arbitraire.
- Filename de sauvegarde valide par regex (anti path traversal).
- A la restauration : chaque membre du tar est verifie contre la whitelist et
  contre `..` / chemin absolu (defense en profondeur — la creation est sous
  notre controle, mais on protege contre tar malveillant manuellement injecte).
"""
import re
import tarfile
from datetime import datetime
from pathlib import Path

# Fichiers de config a sauvegarder (relatifs a ~/.config/)
CONFIG_FILES = [
    "kdeglobals",
    "kwinrc",
    "plasmarc",
    "kcminputrc",
    "kscreenlockerrc",
    "kglobalshortcutsrc",
    "khotkeysrc",
    "plasma-org.kde.plasma.desktop-appletsrc",
    "plasmashellrc",
    "dolphinrc",
    "konsolerc",
    "katerc",
    "krunnerrc",
    "kxkbrc",
    "Kvantum/kvantum.kvconfig",
]

BACKUP_DIR = Path.home() / ".local/share/fedoraforgekde/backups"

# Garde au plus N sauvegardes les plus recentes. Les anciennes sont supprimees
# automatiquement a chaque nouvelle creation pour eviter que le dossier ne
# croisse indefiniment (1 backup/semaine pendant 5 ans = 260 fichiers).
MAX_BACKUPS = 30

# kde-YYYYMMDD-HHMMSS[-label].tar.gz   (label max 32 chars, alphanum + -_)
_FILENAME_RE = re.compile(r'^kde-\d{8}-\d{6}(-[A-Za-z0-9_-]{1,32})?\.tar\.gz$')


class BackupError(Exception):
    """Erreur de sauvegarde/restauration."""


def _ensure_backup_dir():
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_label(label):
    """Nettoie un label : autorise [A-Za-z0-9_-], max 32 chars. Vide -> ''."""
    if not label:
        return ""
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in label)
    cleaned = cleaned.strip("-_")
    return cleaned[:32]


def _validate_filename(filename):
    """Verifie que `filename` est un nom de sauvegarde valide et resolve dans BACKUP_DIR."""
    if not _FILENAME_RE.match(filename):
        raise BackupError("Nom de sauvegarde invalide")
    target = BACKUP_DIR / filename
    if not target.exists() or not target.is_file():
        raise BackupError(f"Sauvegarde introuvable : {filename}")
    # Defense en profondeur : verifie que ca resolve bien dans BACKUP_DIR
    try:
        target.resolve().relative_to(BACKUP_DIR.resolve())
    except ValueError as e:
        raise BackupError("Fichier hors du dossier de sauvegarde") from e
    return target


def create_backup(label=None):
    """Cree une archive tar.gz des fichiers de config KDE existants.

    Retourne un dict {filename, path, files_count, size, timestamp, label}.
    Leve BackupError si aucun fichier de config n'est trouve.
    """
    _ensure_backup_dir()

    config_dir = Path.home() / ".config"
    if not config_dir.exists():
        raise BackupError("~/.config introuvable")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_label = _sanitize_label(label)
    name = f"kde-{timestamp}"
    if safe_label:
        name += f"-{safe_label}"
    name += ".tar.gz"
    backup_path = BACKUP_DIR / name

    files_included = []
    try:
        with tarfile.open(backup_path, "w:gz") as tar:
            for rel_path in CONFIG_FILES:
                full = config_dir / rel_path
                if full.exists() and full.is_file():
                    tar.add(str(full), arcname=rel_path)
                    files_included.append(rel_path)
    except OSError as e:
        backup_path.unlink(missing_ok=True)
        raise BackupError(f"Erreur ecriture archive : {e}") from e

    if not files_included:
        backup_path.unlink(missing_ok=True)
        raise BackupError("Aucun fichier de config KDE a sauvegarder")

    pruned = _prune_old_backups()

    return {
        "filename": name,
        "path": str(backup_path),
        "files_count": len(files_included),
        "files": files_included,
        "size": backup_path.stat().st_size,
        "timestamp": timestamp,
        "label": safe_label,
        "pruned": pruned,
    }


def _prune_old_backups():
    """Garde au plus MAX_BACKUPS sauvegardes (les plus recentes).

    Retourne le nombre supprime. Robuste aux echecs OS (best-effort).
    """
    backups = list_backups()
    if len(backups) <= MAX_BACKUPS:
        return 0
    deleted = 0
    for entry in backups[MAX_BACKUPS:]:
        try:
            (BACKUP_DIR / entry["filename"]).unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


def list_backups():
    """Liste les sauvegardes (triees par date desc)."""
    if not BACKUP_DIR.exists():
        return []

    results = []
    for f in BACKUP_DIR.glob("kde-*.tar.gz"):
        if not _FILENAME_RE.match(f.name):
            continue
        try:
            stat = f.stat()
        except OSError:
            continue
        # Parse: kde-YYYYMMDD-HHMMSS[-label]
        stem = f.name.removesuffix(".tar.gz")
        parts = stem.split("-", 3)  # ["kde", date, time, label?]
        timestamp = ""
        label = ""
        if len(parts) >= 3:
            timestamp = f"{parts[1]}-{parts[2]}"
        if len(parts) >= 4:
            label = parts[3]
        results.append({
            "filename": f.name,
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "timestamp": timestamp,
            "label": label,
        })

    results.sort(key=lambda x: x["mtime"], reverse=True)
    return results


def _member_is_safe(member):
    """True si un membre du tar est dans notre whitelist et sans path traversal."""
    name = member.name
    if not name or name.startswith("/"):
        return False
    if ".." in Path(name).parts:
        return False
    if name not in CONFIG_FILES:
        return False
    return member.isfile()


def restore_backup(filename):
    """Restaure une sauvegarde dans ~/.config/.

    Ecrase les fichiers existants. Membres hors whitelist ignores silencieusement
    (avec compte dans `skipped`).
    """
    target = _validate_filename(filename)
    config_dir = Path.home() / ".config"
    config_dir.mkdir(parents=True, exist_ok=True)

    restored = []
    skipped = []
    try:
        with tarfile.open(target, "r:gz") as tar:
            for member in tar.getmembers():
                if not _member_is_safe(member):
                    skipped.append(member.name)
                    continue
                out_path = config_dir / member.name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                tar.extract(member, path=config_dir, set_attrs=False)
                restored.append(member.name)
    except tarfile.TarError as e:
        raise BackupError(f"Archive corrompue : {e}") from e

    return {"restored": restored, "skipped": skipped, "count": len(restored)}


def delete_backup(filename):
    """Supprime une sauvegarde."""
    target = _validate_filename(filename)
    target.unlink()
    return True
