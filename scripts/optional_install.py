#!/usr/bin/env python3
"""Installe les paquets optionnels (configs/optional_install.json)."""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import (
    ACTION_DNF_INSTALL,
    check_package_installed,
    dnf_install,
    error,
    get_state_manager,
    info,
    load_package_list,
    success,
    warn,
)

CONFIG_FILE = Path(__file__).parent.parent / "configs/optional_install.json"


def install_single_package(pkg):
    name = pkg.get("name")
    desc = pkg.get("description", "")

    if not name:
        warn("Nom de paquet vide, ignore.")
        return

    info(f"Verification de {name}...")
    if check_package_installed(name):
        warn(f"{name} deja installe, ignore.")
        return

    info(f"Installation de {name} - {desc}")
    result = dnf_install([name])

    get_state_manager().record(
        action=ACTION_DNF_INSTALL,
        target=name,
        success=result.success,
        rollback_cmd=["sudo", "dnf", "remove", "-y", name],
        metadata={"description": desc, "optional": True},
    )

    if result.success:
        success(f"{name} installe.")
    else:
        warn(f"Echec installation de {name}.")


def main():
    if not CONFIG_FILE.exists():
        error(f"{CONFIG_FILE} introuvable.")
        return

    try:
        packages = load_package_list(CONFIG_FILE)
    except Exception as e:
        error(f"Erreur chargement config : {e}")
        return

    if not packages:
        warn("Aucun paquet optionnel dans la config.")
        return

    info("Installation des paquets optionnels...")
    for pkg in packages:
        install_single_package(pkg)
    success("Paquets optionnels traites.")


if __name__ == "__main__":
    main()
