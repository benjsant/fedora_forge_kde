#!/usr/bin/env python3
"""Installe les paquets externes (commandes bash custom).
Attention : les commandes dans external_packages.json sont executees via bash."""

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import ACTION_EXTERNAL_INSTALL, error, get_state_manager, info, run_command, success, warn
from utils.sandbox import looks_dangerous

CONFIG_FILE = Path(__file__).parent.parent / "configs/external_packages.json"


def install_package(pkg):
    name = pkg.get("name")
    desc = pkg.get("description", "")
    cmd = pkg.get("cmd")

    if not cmd:
        warn(f"Pas de commande pour {name}, ignore.")
        return

    info(f"Installation de {name} - {desc}...")

    # Audit : log la commande complete + patterns suspects.
    # Les commandes externes contiennent typiquement `sudo dnf install ...`,
    # non sandboxables via bwrap (escalade root). On se contente d'auditer.
    info(f"[AUDIT] Commande : {cmd}")
    for finding in looks_dangerous(cmd):
        warn(f"[AUDIT] {name} : pattern suspect detecte : {finding}")

    result = run_command(["bash", "-c", cmd])

    get_state_manager().record(
        action=ACTION_EXTERNAL_INSTALL,
        target=name,
        success=result.success,
        rollback_cmd=[],
        metadata={"description": desc, "manual_rollback": True},
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
        with open(CONFIG_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        error(f"JSON invalide dans {CONFIG_FILE}: {e}")
        return

    packages = data.get("external_packages", data.get("packages", []))
    if not packages:
        warn("Aucun paquet externe.")
        return

    info("Installation des paquets externes...")
    for pkg in packages:
        install_package(pkg)
    success("Paquets externes traites.")


if __name__ == "__main__":
    main()
