#!/usr/bin/env python3
"""Installe les paquets DNF definis dans configs/install.json."""

import sys
from pathlib import Path

# Fallback CLI direct : si lance via `python scripts/X.py` au lieu de `python -m scripts.X`,
# le __init__.py du package n'est pas charge, donc on configure sys.path ici.
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

CONFIG_FILE = Path(__file__).parent.parent / "configs/install.json"


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
        metadata={"description": desc},
    )

    if result.success:
        success(f"{name} installe.")
    else:
        warn(f"Echec installation de {name}.")


def install_all_packages(packages):
    info("Installation des paquets...")
    for pkg in packages:
        install_single_package(pkg)
    success("Tous les paquets traites.")


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
        warn("Aucun paquet dans la config.")
        return

    install_all_packages(packages)


if __name__ == "__main__":
    main()
