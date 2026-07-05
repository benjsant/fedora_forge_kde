"""Toggle "barre des taches flottante / fixe" du panneau Plasma.

Plasma 6 stocke l'option "Flottant" de chaque panneau dans
~/.config/plasma-org.kde.plasma.desktop-appletsrc : cle `floating` (0/1) du groupe
General du containment de type panneau (plugin=org.kde.panel). Comme sur Nobara,
on veut figer la barre en un clic plutot que de passer par le mode edition.

Reglage user-level (pas de sudo). On localise les containments de panneau en
parsant le fichier, on ecrit via kwriteconfig6 (format KDE correct), puis on
relance plasmashell pour appliquer (un edit du fichier seul ne se voit qu'au
prochain demarrage de Plasma).
"""
import re
import shutil
import subprocess
import time
from pathlib import Path

APPLETSRC = "plasma-org.kde.plasma.desktop-appletsrc"


def _appletsrc_path():
    return Path.home() / ".config" / APPLETSRC


def tools_available():
    return (shutil.which("kwriteconfig6") is not None
            and shutil.which("kreadconfig6") is not None)


def _panel_containments():
    """IDs des containments de type panneau (plugin=org.kde.panel).

    Un containment desktop a plugin=org.kde.desktop ; seuls les panneaux ont
    org.kde.panel, ce qui les identifie de maniere fiable."""
    try:
        text = _appletsrc_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    ids = []
    current = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("["):
            m = re.match(r"^\[Containments\]\[(\d+)\]$", s)
            current = m.group(1) if m else None
            continue
        if current and s == "plugin=org.kde.panel":
            ids.append(current)
    return ids


def _read_floating(cid):
    """Etat flottant d'un panneau (defaut Plasma = flottant si la cle est absente)."""
    try:
        r = subprocess.run(
            ["kreadconfig6", "--file", APPLETSRC, "--group", "Containments",
             "--group", cid, "--group", "General", "--key", "floating", "--default", "1"],
            capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True
    return r.stdout.strip() == "1"


def status():
    panels = _panel_containments()
    states = []
    if tools_available():
        states = [{"id": cid, "floating": _read_floating(cid)} for cid in panels]
    any_floating = any(s["floating"] for s in states)
    return {
        "available": tools_available() and _appletsrc_path().exists() and bool(panels),
        "panel_count": len(panels),
        "panels": states,
        "floating": any_floating,                 # au moins un panneau flottant
        "all_fixed": bool(states) and not any_floating,
    }


def _reload_plasmashell():
    """Relance plasmashell pour appliquer le changement (kstart6/kstart/plasmashell)."""
    subprocess.run(["kquitapp6", "plasmashell"], capture_output=True, timeout=10)
    time.sleep(0.5)
    binary = shutil.which("kstart6") or shutil.which("kstart") or shutil.which("plasmashell")
    if binary is None:
        return False
    args = [binary, "plasmashell"] if Path(binary).name.startswith("kstart") else [binary]
    subprocess.Popen(
        args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True,
    )
    return True


def set_floating(floating):
    """Passe tous les panneaux en flottant (True) ou fixe (False). (ok, message)."""
    if not tools_available():
        return False, "kwriteconfig6/kreadconfig6 introuvables (paquet kde-cli-tools ?)"
    panels = _panel_containments()
    if not panels:
        return False, "Aucun panneau Plasma detecte"
    value = "1" if floating else "0"
    for cid in panels:
        try:
            w = subprocess.run(
                ["kwriteconfig6", "--file", APPLETSRC, "--group", "Containments",
                 "--group", cid, "--group", "General", "--key", "floating", value],
                capture_output=True, text=True, timeout=10,
            )
        except subprocess.TimeoutExpired:
            return False, "Timeout lors de l'ecriture de la configuration"
        if w.returncode != 0:
            return False, (w.stderr.strip() or "Echec ecriture kwriteconfig6")
    state = "flottante" if floating else "fixe"
    if not _reload_plasmashell():
        return True, f"Barre {state} ecrite ; relancez Plasma pour appliquer"
    return True, f"Barre des taches {state}"
