#!/usr/bin/env python3
"""Validation des fichiers JSON de config avec Pydantic."""

import json
from pathlib import Path

from pydantic import ValidationError

from schemas import (
    ExternalPackageList,
    FlatpakList,
    PackageList,
    ThemeList,
)


class ConfigValidationError(Exception):
    """Erreur de validation d'un fichier de config."""

    def __init__(self, config_file, errors):
        self.config_file = config_file
        self.errors = errors

        error_msgs = []
        for err in errors:
            loc = " -> ".join(str(part) for part in err.get("loc", []))
            msg = err.get("msg", "Erreur inconnue")
            error_msgs.append(f"  - {loc}: {msg}")

        self.message = (
            f"\nErreurs de validation dans {config_file}:\n"
            + "\n".join(error_msgs)
        )
        super().__init__(self.message)


def validate_config(config_path, model_class):
    """Valide un JSON contre un modele Pydantic."""
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {config_path}")

    try:
        with open(config_path, encoding='utf-8') as f:
            data = json.load(f)
        return model_class.model_validate(data)
    except ValidationError as e:
        raise ConfigValidationError(str(config_path), e.errors()) from e
    except json.JSONDecodeError as e:
        raise ConfigValidationError(str(config_path), [{
            "loc": ["json"],
            "msg": f"JSON invalide : {e.msg} ligne {e.lineno}, colonne {e.colno}"
        }]) from e


def validate_install_config(path):
    return validate_config(path, PackageList)

def validate_remove_config(path):
    return validate_config(path, PackageList)

def validate_flatpak_config(path):
    return validate_config(path, FlatpakList)

def validate_external_config(path):
    return validate_config(path, ExternalPackageList)

def validate_theme_config(path):
    return validate_config(path, ThemeList)


def validate_all_configs(config_dir="configs"):
    """Valide tous les fichiers de config du dossier."""
    config_dir = Path(config_dir)
    results = {}

    config_validations = [
        ("install.json", validate_install_config),
        ("remove.json", validate_remove_config),
        ("flatpak.json", validate_flatpak_config),
        ("external_packages.json", validate_external_config),
        ("themes_gtk.json", validate_theme_config),
        ("themes_icons.json", validate_theme_config),
        ("themes_cursors.json", validate_theme_config),
        ("optional_install.json", validate_install_config),
    ]

    for config_file, validator in config_validations:
        config_path = config_dir / config_file
        if not config_path.exists():
            results[config_file] = None
            continue
        try:
            results[config_file] = validator(config_path)
        except ConfigValidationError:
            raise

    return results
