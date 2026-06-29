"""Tweak Dolphin : ouvrir le dossier personnel au demarrage.

Par defaut Dolphin ouvre deja le home, mais si "memoriser les onglets ouverts"
est active il rouvre la derniere session a la place. Ce tweak fige le comportement
"home au demarrage" en posant RememberOpenedTabs=false dans dolphinrc (groupe
General). Reglage user-level (kwriteconfig6, pas de sudo) ; l'effet s'applique au
prochain lancement de Dolphin (pas de service a relancer).
"""
import shutil
import subprocess

DOLPHINRC = "dolphinrc"
_GROUP = "General"
_KEY = "RememberOpenedTabs"


def tools_available():
    return (shutil.which("kwriteconfig6") is not None
            and shutil.which("kreadconfig6") is not None)


def _read_remember():
    """Valeur de RememberOpenedTabs en minuscules (defaut Dolphin = false si absent).
    None si l'outil de lecture est indisponible."""
    try:
        r = subprocess.run(
            ["kreadconfig6", "--file", DOLPHINRC, "--group", _GROUP,
             "--key", _KEY, "--default", "false"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip().lower()


def status():
    remember = _read_remember()
    return {
        "available": tools_available(),
        "remember_tabs": remember == "true",
        # "home au demarrage" actif = on ne memorise PAS les onglets
        "home_on_startup": remember == "false",
    }


def set_home_on_startup(enable):
    """Active (True) / desactive (False) l'ouverture sur le dossier personnel au
    demarrage de Dolphin. Retourne (ok: bool, message: str)."""
    if not tools_available():
        return False, "kwriteconfig6 introuvable (paquet kde-cli-tools ?)"
    # home au demarrage => ne pas memoriser les onglets
    value = "false" if enable else "true"
    try:
        w = subprocess.run(
            ["kwriteconfig6", "--file", DOLPHINRC, "--group", _GROUP, "--key", _KEY, value],
            capture_output=True, text=True, timeout=10,
        )
    except subprocess.TimeoutExpired:
        return False, "Timeout lors de l'ecriture de dolphinrc"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"
    if w.returncode != 0:
        return False, (w.stderr.strip() or "Echec ecriture kwriteconfig6")
    state = ("ouvre le dossier personnel au demarrage" if enable
             else "memorise les onglets ouverts")
    return True, f"Dolphin {state} (effet au prochain lancement)"
