#!/usr/bin/env python3
"""Gestion des themes : detection, installation git, application KDE Plasma."""

import json
import tempfile
from pathlib import Path

from .sandbox import bwrap_available, looks_dangerous, wrap_user_command
from .subprocess_utils import git_clone, run_command


class ThemeManager:
    """Detecte, installe et applique les themes GTK/Plasma/icones/curseurs."""

    def __init__(self):
        self.gtk_theme_paths = [
            Path.home() / ".themes",
            Path("/usr/share/themes")
        ]
        self.icon_theme_paths = [
            Path.home() / ".local/share/icons",
            Path.home() / ".icons",
            Path("/usr/share/icons")
        ]
        # KDE Plasma themes
        self.plasma_theme_paths = [
            Path.home() / ".local/share/plasma/desktoptheme",
            Path("/usr/share/plasma/desktoptheme")
        ]
        self.kvantum_theme_paths = [
            Path.home() / ".config/Kvantum",
            Path("/usr/share/Kvantum")
        ]

    def is_theme_installed(self, theme_name, theme_type="gtk"):
        """Verifie si un theme est present. Retourne (bool, Path ou None)."""
        if theme_type == "gtk":
            search_paths = self.gtk_theme_paths
        elif theme_type == "plasma":
            search_paths = self.plasma_theme_paths
        elif theme_type == "kvantum":
            search_paths = self.kvantum_theme_paths
        else:
            search_paths = self.icon_theme_paths

        for base_path in search_paths:
            theme_path = base_path / theme_name
            if theme_path.exists() and theme_path.is_dir() and any(theme_path.iterdir()):
                return True, theme_path

        return False, None

    def list_available_themes(self, theme_type="gtk"):
        """Liste les themes disponibles sur le systeme."""
        themes = set()

        if theme_type == "gtk":
            search_paths = self.gtk_theme_paths
        elif theme_type == "plasma":
            search_paths = self.plasma_theme_paths
        elif theme_type == "kvantum":
            search_paths = self.kvantum_theme_paths
        else:
            search_paths = self.icon_theme_paths

        # Marqueurs : fichier present dans le dossier => c'est un theme du type donne
        markers = {
            "gtk":    ["gtk-3.0"],
            "icon":   ["index.theme"],
            "cursor": ["cursors"],
            "plasma": ["metadata.desktop", "metadata.json"],
        }
        for base_path in search_paths:
            if not base_path.exists():
                continue
            for theme_dir in base_path.iterdir():
                if not theme_dir.is_dir() or theme_dir.name.startswith('.'):
                    continue
                if theme_type == "kvantum" or any(
                    (theme_dir / m).exists() for m in markers.get(theme_type, [])
                ):
                    themes.add(theme_dir.name)

        return sorted(themes)

    def install_theme_from_git(self, theme_name, git_url, install_cmd, theme_type="gtk"):
        """Clone et installe un theme depuis git. Retourne (success, message)."""
        is_installed, theme_path = self.is_theme_installed(theme_name, theme_type)
        if is_installed:
            return True, f"Theme {theme_name} deja installe : {theme_path}"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            clone_path = temp_path / theme_name

            try:
                print(f"Telechargement de {theme_name}...")
                result = git_clone(git_url, clone_path, depth=1)
                if not result.success:
                    return False, f"Echec git clone : {result.stderr}"

                print(f"Installation de {theme_name}...")

                # Audit : detecte les patterns suspects dans la commande user
                suspicious = looks_dangerous(install_cmd)
                if suspicious:
                    print(f"  [AUDIT] Patterns suspects detectes : {', '.join(suspicious)}")

                # Sandbox bwrap si dispo ET commande user-level (pas de sudo).
                # Les `cmd_root` qui font sudo ne sont pas sandboxables (l'escalade
                # casse le user namespace).
                inner = ["bash", "-c", install_cmd]
                if bwrap_available() and "sudo " not in install_cmd:
                    # Autorise l'ecriture dans les destinations themes legitimes
                    # + le clone_path (build dir temporaire)
                    home = Path.home()
                    writables = [
                        str(home / ".themes"),
                        str(home / ".icons"),
                        str(home / ".local"),
                        str(home / ".config"),
                        str(clone_path),
                    ]
                    # Cree les dossiers parents si absents (bwrap --bind echoue sinon)
                    for p in writables:
                        Path(p).mkdir(parents=True, exist_ok=True)
                    cmd = wrap_user_command(inner, writable_paths=writables)
                else:
                    cmd = inner

                result = run_command(
                    cmd,
                    cwd=clone_path, capture_output=True, timeout=300
                )
                if not result.success:
                    detail = (result.stderr or result.stdout or "pas de detail").strip()
                    return False, f"Echec installation : {detail}"

                is_installed, theme_path = self.is_theme_installed(theme_name, theme_type)
                if is_installed:
                    return True, f"Theme {theme_name} installe : {theme_path}"
                else:
                    return False, "Installation terminee mais theme non trouve"

            except Exception as e:
                return False, f"Erreur : {str(e)}"

    def apply_kde_theme(self, gtk_theme, icon_theme, cursor_theme, plasma_theme=None):
        """Applique les themes via les commandes KDE. Retourne (success, message)."""
        results = []

        # GTK theme via kwriteconfig6
        cmds = [
            (["kwriteconfig6", "--file", "kdeglobals", "--group", "General",
              "--key", "Name", gtk_theme], f"GTK theme: {gtk_theme}"),
            (["kwriteconfig6", "--file", "kdeglobals", "--group", "Icons",
              "--key", "Theme", icon_theme], f"Icon theme: {icon_theme}"),
            (["kwriteconfig6", "--file", "kcminputrc", "--group", "Mouse",
              "--key", "cursorTheme", cursor_theme], f"Cursor theme: {cursor_theme}"),
        ]

        if plasma_theme:
            cmds.append(
                (["kwriteconfig6", "--file", "plasmarc", "--group", "Theme",
                  "--key", "name", plasma_theme], f"Plasma theme: {plasma_theme}")
            )

        for cmd, desc in cmds:
            result = run_command(cmd, capture_output=True, timeout=10)
            if result.success:
                results.append(f"OK {desc}")
            else:
                results.append(f"FAIL {desc}: {result.stderr}")

        ok = all(r.startswith("OK ") for r in results)
        return ok, "\n".join(results)

    def check_recommended_config(self, config_file):
        """Charge et verifie l'etat de la config recommandee."""
        with open(config_file, encoding='utf-8') as f:
            config = json.load(f)

        result = {
            "config_name": config["name"],
            "description": config["description"],
            "gtk_theme": config["gtk_theme"],
            "icon_theme": config["icon_theme"],
            "cursor_theme": config["cursor_theme"],
            "optional_themes": []
        }

        for theme in config.get("optional_themes", []):
            is_installed, theme_path = self.is_theme_installed(theme["name"], theme["type"])
            result["optional_themes"].append({
                **theme,
                "installed": is_installed,
                "path": str(theme_path) if theme_path else None
            })

        return result

    def apply_recommended_config(self, config_file, install_missing=True):
        """Applique la config recommandee. Retourne (success, messages)."""
        messages = []

        with open(config_file, encoding='utf-8') as f:
            config = json.load(f)

        messages.append(f"Configuration : {config['name']}")
        messages.append(f"{config['description']}\n")

        if install_missing:
            for theme in config.get("optional_themes", []):
                is_installed, _ = self.is_theme_installed(theme["name"], theme["type"])

                if not is_installed:
                    messages.append(f"Installation de {theme['name']}...")
                    ok, msg = self.install_theme_from_git(
                        theme["name"], theme["git_url"],
                        theme["install_cmd"], theme["type"]
                    )
                    messages.append(msg)
                else:
                    messages.append(f"{theme['name']} deja installe")

        messages.append("\nApplication des themes...")
        ok, msg = self.apply_kde_theme(
            config["gtk_theme"],
            config["icon_theme"],
            config["cursor_theme"],
            config.get("plasma_theme"),
        )
        messages.append(msg)

        return ok, messages
