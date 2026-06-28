#!/usr/bin/env python3
"""Gestion des fichiers JSON et operations courantes."""

import json
import os
from pathlib import Path


class ConfigError(Exception):
    """Fichier de config invalide ou manquant."""
    pass


def load_json(file_path, required=True):
    """Charge un fichier JSON. Leve ConfigError si requis et absent."""
    if not file_path.exists():
        if required:
            raise ConfigError(f"Fichier introuvable : {file_path}")
        return {}
    try:
        with open(file_path, encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"JSON invalide dans {file_path}: {e}") from e
    except Exception as e:
        raise ConfigError(f"Erreur lecture {file_path}: {e}") from e


def save_json(data, file_path, indent=2):
    """Ecrit un dict en JSON avec indentation."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)


def load_package_list(config_file, validate=True):
    """Charge une liste de paquets depuis un JSON (packages/flatpaks/themes)."""
    if validate:
        try:
            from .validation import (
                validate_external_config,
                validate_flatpak_config,
                validate_install_config,
                validate_remove_config,
                validate_theme_config,
            )

            filename = config_file.name.lower()

            if "install" in filename and "json" in filename:
                validated = validate_install_config(config_file)
                return [pkg.model_dump() for pkg in validated.packages]
            elif "remove" in filename and "json" in filename:
                validated = validate_remove_config(config_file)
                return [pkg.model_dump() for pkg in validated.packages]
            elif "flatpak" in filename and "json" in filename:
                validated = validate_flatpak_config(config_file)
                return [app.model_dump() for app in validated.flatpaks]
            elif "external" in filename and "json" in filename:
                validated = validate_external_config(config_file)
                return [pkg.model_dump() for pkg in validated.packages]
            elif "themes" in filename or "theme" in filename:
                validated = validate_theme_config(config_file)
                return [theme.model_dump() for theme in validated.themes]
        except ImportError:
            pass

    config = load_json(config_file)
    for key in ["packages", "flatpaks", "themes"]:
        if key in config:
            return config[key]
    return []


def ensure_directory(path):
    """Cree le dossier s'il n'existe pas."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_read_file(file_path, default=""):
    """Lit un fichier, retourne default en cas d'erreur."""
    try:
        return file_path.read_text(encoding='utf-8')
    except Exception:
        return default


def safe_write_file(file_path, content):
    """Ecrit dans un fichier, retourne True/False."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        return True
    except Exception:
        return False


def get_user_home():
    """Retourne le home du vrai utilisateur (meme sous sudo)."""
    sudo_user = os.getenv("SUDO_USER")
    if sudo_user:
        return Path(f"/home/{sudo_user}")
    user = os.getenv("USER")
    if user and user != "root":
        return Path(f"/home/{user}")
    return Path.home()


def find_file_in_paths(filename, search_paths):
    """Cherche un fichier dans une liste de dossiers."""
    for path in search_paths:
        candidate = path / filename
        if candidate.exists():
            return candidate
    return None


class ConfigManager:
    """Acces simplifie aux fichiers de config."""

    def __init__(self, config_dir):
        self.config_dir = config_dir
        ensure_directory(config_dir)

    def get_config_path(self, filename):
        return self.config_dir / filename

    def load(self, filename):
        return load_json(self.get_config_path(filename))

    def save(self, filename, data):
        save_json(data, self.get_config_path(filename))

    def get_packages(self, filename):
        return load_package_list(self.get_config_path(filename))

    def exists(self, filename):
        return self.get_config_path(filename).exists()
