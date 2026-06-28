#!/usr/bin/env python3
"""Installe les Flatpaks definis dans configs/flatpak.json."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import (
    ACTION_FLATPAK_INSTALL,
    check_flatpak_installed,
    error,
    flatpak_install,
    get_state_manager,
    info,
    success,
    warn,
)

CONFIG_FILE = Path(__file__).parent.parent / "configs/flatpak.json"


def install_single_flatpak(flatpak):
    app = flatpak.get("app")
    source = flatpak.get("source", "flathub")
    desc = flatpak.get("description", "")

    if not app:
        warn("ID Flatpak vide, ignore.")
        return

    if check_flatpak_installed(app):
        warn(f"{app} deja installe, ignore.")
        return

    info(f"Installation de {app} - {desc} depuis {source}...")
    result = flatpak_install(app, remote=source)

    get_state_manager().record(
        action=ACTION_FLATPAK_INSTALL,
        target=app,
        success=result.success,
        rollback_cmd=["flatpak", "uninstall", "-y", app],
        metadata={"description": desc, "source": source},
    )

    if result.success:
        success(f"{app} installe.")
    else:
        warn(f"Echec installation de {app}.")


def install_all_flatpaks(flatpaks):
    info("Installation des Flatpaks...")
    for flatpak in flatpaks:
        install_single_flatpak(flatpak)
    success("Tous les Flatpaks traites.")


def main():
    if not CONFIG_FILE.exists():
        error(f"{CONFIG_FILE} introuvable.")
        return

    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        error(f"JSON invalide dans {CONFIG_FILE}: {e}")
        return

    flatpaks = data.get("flatpaks", [])
    if not flatpaks:
        warn("Aucun Flatpak dans la config.")
        return

    install_all_flatpaks(flatpaks)


if __name__ == "__main__":
    main()
