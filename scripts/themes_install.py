#!/usr/bin/env python3
"""
FedoraForgeKDE - Theme Installer
----------------------------------------------
Desktop theming utility for Fedora KDE Plasma.
Installs GTK, Plasma, Icon, and Cursor themes and applies them via KDE tools.
Updates plasma-login-manager configuration if active.
"""

import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import (
    error,
    git_clone,
    info,
    run_command,
    run_sudo_command,
    success,
    warn,
)
from utils.sandbox import bwrap_available, looks_dangerous, wrap_user_command

# ---------------------------------------------------------------------
# Project-root-relative paths
# ---------------------------------------------------------------------
PROJECT_DIR = Path(__file__).parent.parent
CONFIG_DIR = PROJECT_DIR / "configs"
THEMES_DIR = PROJECT_DIR / "themes"
ICONS_DIR = PROJECT_DIR / "icons"
CURSORS_DIR = PROJECT_DIR / "cursors"

for d in [THEMES_DIR, ICONS_DIR, CURSORS_DIR]:
    d.mkdir(exist_ok=True)

# ---------------------------------------------------------------------
# User detection
# ---------------------------------------------------------------------
USER_NAME = os.getenv("SUDO_USER") or os.getenv("USER")
USER_HOME = str(Path(f"~{USER_NAME}").expanduser()) if USER_NAME else ""

if not USER_NAME:
    error("Unable to detect user.")

# ---------------------------------------------------------------------
# Load JSON files
# ---------------------------------------------------------------------
def load_theme_json(file_path: Path):
    """Load themes from a JSON config file. Returns empty list on error."""
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)["themes"]
    except Exception as e:
        error(f"Failed to load {file_path}: {e}")
        return []

# ---------------------------------------------------------------------
# Installation helpers
# ---------------------------------------------------------------------
def install_theme(theme: dict, target_dir: Path):
    """Clone and install a theme sequentially."""
    name = theme.get("name", "unknown")
    url = theme.get("url", "")
    cmd_user = theme.get("cmd_user", "")
    cmd_root = theme.get("cmd_root", "")

    info(f"Installing {name}...")

    if url:
        if not target_dir.exists():
            info(f"Cloning {url} into {target_dir}")
            git_clone(url, target_dir, depth=1)
        else:
            warn(f"{target_dir} already exists. Skipping clone.")

    run_sudo_command(["chown", "-R", f"{USER_NAME}:{USER_NAME}", str(target_dir)])

    if cmd_user:
        # Audit + sandbox bwrap pour les commandes user-level (cmd_user)
        for finding in looks_dangerous(cmd_user):
            warn(f"[AUDIT] {name} cmd_user : {finding}")
        inner = ["bash", "-c", cmd_user]
        if bwrap_available() and "sudo " not in cmd_user:
            from pathlib import Path as _P
            home = _P.home()
            writables = [str(home / ".themes"), str(home / ".icons"),
                         str(home / ".local"), str(home / ".config"),
                         str(target_dir)]
            for p in writables:
                _P(p).mkdir(parents=True, exist_ok=True)
            cmd = wrap_user_command(inner, writable_paths=writables)
        else:
            cmd = inner
        run_command(cmd, cwd=target_dir)
    if cmd_root:
        # cmd_root utilise sudo : non sandboxable. Audit uniquement.
        for finding in looks_dangerous(cmd_root):
            warn(f"[AUDIT] {name} cmd_root : {finding}")
        run_sudo_command(["bash", "-c", cmd_root], cwd=target_dir)

    success(f"{name} installed.")


def apply_login_manager_theme(gtk_theme, icon_theme, cursor_theme):
    """Update plasma-login-manager configuration to match desktop theme.

    Skips silently if plasma-login-manager service is not active (e.g. SDDM
    still in place on older installs).
    """
    import subprocess
    try:
        r = subprocess.run(["systemctl", "is-active", "plasmalogin.service"],
                           capture_output=True, text=True, timeout=3)
        if r.stdout.strip() != "active":
            warn("plasma-login-manager non actif, configuration ignoree.")
            return
    except Exception:
        warn("Impossible de detecter plasma-login-manager, configuration ignoree.")
        return

    conf_dir = Path("/etc/plasmalogin.conf.d")
    conf_file = conf_dir / "fedoraforgekde.conf"

    content = f"""# Configuration plasma-login-manager generee par FedoraForgeKDE
[Theme]
CursorTheme={cursor_theme}

[General]
# Theme settings synced from desktop
"""
    try:
        run_sudo_command(["mkdir", "-p", str(conf_dir)])
        tmp = "/tmp/fedoraforgekde_plasmalogin.conf"
        Path(tmp).write_text(content)
        result = run_sudo_command(["cp", tmp, str(conf_file)])
        if result.success:
            success("plasma-login-manager configuration updated.")
        else:
            warn("Could not update plasma-login-manager configuration.")
    except Exception as e:
        warn(f"plasma-login-manager config error: {e}")


# ---------------------------------------------------------------------
# Theme application (KDE Plasma)
# ---------------------------------------------------------------------
def apply_theme_kde(gtk_theme, icon_theme, cursor_theme):
    """Apply theme values using KDE tools (applies immediately in session)."""
    settings = [
        ["kwriteconfig6", "--file", "kdeglobals", "--group", "General", "--key", "Name", gtk_theme],
        ["kwriteconfig6", "--file", "kdeglobals", "--group", "Icons", "--key", "Theme", icon_theme],
        ["kwriteconfig6", "--file", "kcminputrc", "--group", "Mouse", "--key", "cursorTheme", cursor_theme],
    ]
    any_ok = False
    for cmd in settings:
        result = run_command(cmd)
        if result.success:
            any_ok = True
        else:
            warn(f"kwriteconfig6 failed: {' '.join(cmd)}")

    # Notify KDE to reload settings
    run_command(["dbus-send", "--session", "--type=signal",
                 "/KGlobalSettings", "org.kde.KGlobalSettings.notifyChange",
                 "int32:0", "int32:0"])

    if any_ok:
        success("Theme applied via KDE tools.")


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def run_all_themes():
    """Installe les themes disponibles (telechargement/build) SANS les appliquer.

    L'application d'un theme est une action explicite de l'utilisateur (catalogue
    de themes ou config recommandee) : on ne force plus "le premier de chaque
    categorie" et on ne modifie pas l'ecran de connexion. Le theme par defaut
    (Breeze) reste en place. `apply_theme_kde` / `apply_login_manager_theme`
    restent disponibles pour une application explicite ailleurs."""
    themes_data = load_theme_json(CONFIG_DIR / "themes_gtk.json") or []
    icons_data = load_theme_json(CONFIG_DIR / "themes_icons.json") or []
    cursors_data = load_theme_json(CONFIG_DIR / "themes_cursors.json") or []

    total = len(themes_data) + len(icons_data) + len(cursors_data)
    if total == 0:
        info("Aucun theme a installer (catalogues vides).")
        return

    info("Installing all GTK themes...")
    for theme in themes_data:
        install_theme(theme, THEMES_DIR / theme['name_to_use'])

    info("Installing all icon themes...")
    for theme in icons_data:
        install_theme(theme, ICONS_DIR / theme['name_to_use'])

    info("Installing all cursor themes...")
    for theme in cursors_data:
        install_theme(theme, CURSORS_DIR / theme['name_to_use'])

    success(f"{total} theme(s) installe(s) - non appliques "
            "(choisissez-les dans le catalogue de themes pour les activer).")


def main():
    run_all_themes()


if __name__ == "__main__":
    main()
