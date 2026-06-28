"""Detection simple de l'alimentation : sur batterie ou sur secteur.

Utilise sysfs (/sys/class/power_supply/) directement, pas de paquet externe.
Pour les desktops sans batterie, retourne `None` (UI cache l'indicateur).

Usage typique : avertir l'utilisateur qu'il vaut mieux brancher le secteur
avant de lancer une grosse installation (risque de coupure si la batterie
se vide pendant un `dnf install`).
"""
from pathlib import Path

_POWER_SUPPLY = Path("/sys/class/power_supply")


def _read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def get_power_state():
    """Retourne un dict {on_battery, capacity, status} ou None si pas de batterie.

    - on_battery (bool) : True si l'AC adapter est debranche
    - capacity (int)    : niveau batterie 0..100
    - status (str)      : 'Charging' | 'Discharging' | 'Full' | 'Unknown' | ''
    """
    if not _POWER_SUPPLY.exists():
        return None

    # Cherche une batterie
    battery = None
    for supply in sorted(_POWER_SUPPLY.iterdir()):
        if _read(supply / "type") == "Battery":
            battery = supply
            break
    if battery is None:
        return None  # desktop sans batterie

    # Cherche l'adaptateur AC (Mains)
    on_battery = True
    for supply in sorted(_POWER_SUPPLY.iterdir()):
        if _read(supply / "type") == "Mains":
            if _read(supply / "online") == "1":
                on_battery = False
            break

    capacity_raw = _read(battery / "capacity")
    try:
        capacity = int(capacity_raw) if capacity_raw else None
    except ValueError:
        capacity = None

    return {
        "on_battery": on_battery,
        "capacity": capacity,
        "status": _read(battery / "status"),
    }
