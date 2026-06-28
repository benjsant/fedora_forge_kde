#!/usr/bin/env python3
"""Supprime les paquets DNF definis dans configs/remove.json."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import (
    ACTION_DNF_REMOVE,
    check_package_installed,
    dnf_remove,
    error,
    get_state_manager,
    info,
    run_sudo_command,
    success,
    warn,
)

CONFIG_FILE = Path(__file__).parent.parent / "configs/remove.json"


def remove_single_package(pkg):
    name = pkg.get("name")
    desc = pkg.get("description", "")
    if not name:
        warn("Nom de paquet vide, ignore.")
        return

    info(f"Verification de {name}...")
    if check_package_installed(name):
        info(f"Suppression de {name} ({desc})...")
        result = dnf_remove([name])

        get_state_manager().record(
            action=ACTION_DNF_REMOVE,
            target=name,
            success=result.success,
            rollback_cmd=["sudo", "dnf", "install", "-y", name],
            metadata={"description": desc},
        )

        if result.success:
            success(f"{name} supprime.")
        else:
            warn(f"Echec suppression de {name}.")
    else:
        warn(f"{name} pas installe, ignore.")


def remove_all_packages(packages):
    info("Suppression des paquets indesirables...")
    for pkg in packages:
        remove_single_package(pkg)
    run_sudo_command(["dnf", "autoremove", "-y"])
    success("Nettoyage termine.")


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

    packages = data.get("packages", [])
    if not packages:
        warn("Aucun paquet dans la config.")
        return

    remove_all_packages(packages)


if __name__ == "__main__":
    main()
