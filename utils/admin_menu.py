"""Menu Dolphin "Ouvrir en tant qu'administrateur" (comme sur Nobara).

Sur Nobara comme sur Fedora KDE, les entrees clic droit "Ouvrir/Editer en tant
qu'administrateur" de Dolphin proviennent du paquet officiel KDE `kio-admin`
(worker KIO admin:// + plugin kfileitemaction, authentification polkit). Il n'y a
pas de service menu maison a deposer : il suffit d'installer ce paquet, present
dans les depots officiels Fedora (pas de RPM Fusion requis).

Ce module se contente donc d'installer/retirer kio-admin via DNF (sudo -n, comme
les autres tweaks). Les entrees apparaissent dans Dolphin a son prochain lancement.
"""
import subprocess

PACKAGE = "kio-admin"


def is_installed():
    """True si le paquet kio-admin est installe."""
    try:
        return subprocess.run(["rpm", "-q", PACKAGE],
                              capture_output=True, timeout=5).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def status():
    """Etat du menu administrateur. `installed` = paquet kio-admin present."""
    return {"installed": is_installed(), "package": PACKAGE}


def _sudo(cmd, timeout=600):
    return subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True,
                          timeout=timeout)


def enable():
    """Installe kio-admin. Idempotent. Retourne (ok: bool, message: str)."""
    if is_installed():
        return True, "Menu administrateur deja installe (kio-admin)"
    try:
        r = _sudo(["dnf", "install", "-y", PACKAGE])
    except subprocess.TimeoutExpired:
        return False, "Timeout lors de l'installation de kio-admin"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"
    if r.returncode != 0:
        return False, (r.stderr.strip() or "Echec installation kio-admin (sudo requis ?)")
    return True, "Menu administrateur installe (kio-admin) - redemarrez Dolphin"


def disable():
    """Retire kio-admin. Idempotent. Retourne (ok: bool, message: str)."""
    if not is_installed():
        return True, "Menu administrateur deja absent"
    try:
        r = _sudo(["dnf", "remove", "-y", PACKAGE])
    except subprocess.TimeoutExpired:
        return False, "Timeout lors du retrait de kio-admin"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"
    if r.returncode != 0:
        return False, (r.stderr.strip() or "Echec retrait kio-admin")
    return True, "Menu administrateur retire (kio-admin)"
