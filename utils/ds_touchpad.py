"""Pave tactile des manettes PlayStation : detection + neutralisation souris.

Sous Linux, le pave tactile des DualShock 4 / DualSense est expose comme une
souris : manette posee sur le canape, le curseur saute et clique n'importe ou.
Nobara embarque ds-inhibit pour limiter ca, Fedora vanilla n'a rien. Ce tweak
depose une regle udev qui demande a libinput d'ignorer le peripherique : le
curseur ne bouge plus, mais sticks/boutons/pave restent visibles des jeux
(acces evdev direct, ex. Steam Input). L'ecriture passe par `sudo -n tee`
(cache sudo du launcher), puis `udevadm control --reload-rules` + `trigger`
pour appliquer sans rebrancher.
"""
import os
import subprocess

RULE_PATH = "/etc/udev/rules.d/99-fedoraforgekde-ds-touchpad.rules"
_DEVICES_FILE = "/proc/bus/input/devices"

# Vendor USB/BT Sony.
SONY_VENDOR = "054c"

# Deux graphies selon le pilote : hid-sony historique ("Wireless controller"),
# hid-playstation moderne ("Wireless Controller", DualSense inclus).
RULE_CONTENTS = (
    "# Genere par FedoraForgeKDE - ignore le pave tactile des manettes PlayStation.\n"
    'ACTION=="add|change", KERNEL=="event*", ATTRS{name}=="*Wireless Controller Touchpad", ENV{LIBINPUT_IGNORE_DEVICE}="1"\n'
    'ACTION=="add|change", KERNEL=="event*", ATTRS{name}=="*Wireless controller Touchpad", ENV{LIBINPUT_IGNORE_DEVICE}="1"\n'
)


def detect_touchpads():
    """Noms des paves tactiles de manettes Sony actuellement branches."""
    try:
        with open(_DEVICES_FILE, encoding="utf-8", errors="replace") as f:
            blocks = f.read().split("\n\n")
    except OSError:
        return []

    found = []
    for block in blocks:
        if f"Vendor={SONY_VENDOR}" not in block:
            continue
        for line in block.splitlines():
            if line.startswith("N: Name=") and "Touchpad" in line:
                found.append(line.split("=", 1)[1].strip('"'))
    return found


def status():
    """Etat du tweak : regle presente + manette detectee (pour l'UI)."""
    detected = detect_touchpads()
    return {
        "rule_installed": os.path.exists(RULE_PATH),
        "controller_present": bool(detected),
        "detected": detected,
    }


def _reload_udev():
    """Recharge les regles et re-trigger l'input. (ok, stderr)."""
    for args in (["control", "--reload-rules"],
                 ["trigger", "--subsystem-match=input"]):
        r = subprocess.run(["sudo", "-n", "udevadm"] + args,
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return False, r.stderr.strip()
    return True, ""


def apply():
    """Ecrit la regle udev et l'applique a chaud. (ok, message)."""
    try:
        w = subprocess.run(["sudo", "-n", "tee", RULE_PATH],
                           input=RULE_CONTENTS, capture_output=True,
                           text=True, timeout=15)
        if w.returncode != 0:
            return False, (w.stderr.strip() or "Echec ecriture de la regle udev (sudo requis)")
        ok, err = _reload_udev()
        if not ok:
            return False, err or "Echec rechargement udev"
        return True, "Pave tactile manette ignore par libinput (sticks/boutons intacts)"
    except subprocess.TimeoutExpired:
        return False, "Timeout lors de l'application de la regle udev"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"


def remove():
    """Supprime la regle et re-trigger. Idempotent. (ok, message)."""
    try:
        if not os.path.exists(RULE_PATH):
            return True, "Regle deja absente"
        d = subprocess.run(["sudo", "-n", "rm", "-f", RULE_PATH],
                           capture_output=True, text=True, timeout=15)
        if d.returncode != 0:
            return False, (d.stderr.strip() or "Echec suppression de la regle")
        _reload_udev()
        return True, "Pave tactile manette reactive comme souris"
    except subprocess.TimeoutExpired:
        return False, "Timeout lors du retrait de la regle udev"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"
