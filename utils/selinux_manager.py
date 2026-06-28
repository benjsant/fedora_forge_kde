"""Assistant SELinux : composer avec l'enforcing plutot que le desactiver.

Philosophie du projet : contrairement a Nobara (qui desactive SELinux et passe
sur AppArmor), on garde SELinux enforcing. Cet assistant aide l'utilisateur a
resoudre les frictions sans jamais baisser la garde globale :
- diagnostic en lecture seule des denials AVC recents,
- bascule de booleans cibles et whitelistes (jamais arbitraires),
- aucune action ne fait `setenforce 0` : on ne desactive jamais SELinux.
"""
import subprocess

# Booleans SELinux exposes a l'UI. Strictement whitelistes : seuls ces noms
# peuvent etre bascules, jamais une valeur libre venue du client.
ALLOWED_BOOLEANS = {
    "container_use_devices": "Conteneurs (Docker/Podman) : acces aux peripheriques (GPU, /dev)",
    "container_manage_cgroup": "Conteneurs : gestion des cgroups (systemd dans un conteneur)",
    "selinuxuser_execmod": "Autoriser certaines apps (Wine/jeux) a modifier du code executable en memoire",
    "use_nfs_home_dirs": "Repertoires home montes en NFS",
    "virt_use_nfs": "Machines virtuelles / conteneurs accedant a du stockage NFS",
}


def _run(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_mode():
    """Mode SELinux courant : 'Enforcing' / 'Permissive' / 'Disabled' / None."""
    r = _run(["getenforce"], timeout=3)
    if r is None or r.returncode != 0:
        return None
    return r.stdout.strip() or None


def is_available():
    """True si SELinux est exploitable (enforcing ou permissive)."""
    return get_mode() in ("Enforcing", "Permissive")


def get_booleans():
    """Etat on/off des booleans whitelistes. {name: {"value": bool, "description": str}}.

    Si SELinux est indisponible (Disabled/None), renvoie un dict vide."""
    names = list(ALLOWED_BOOLEANS)
    if not is_available() or not names:
        return {}
    r = _run(["getsebool", *names])
    result = {}
    if r is not None and r.returncode == 0:
        for line in r.stdout.splitlines():
            # Format : "boolean_name --> on"
            if "-->" not in line:
                continue
            name, _, state = line.partition("-->")
            name = name.strip()
            if name in ALLOWED_BOOLEANS:
                result[name] = {
                    "value": state.strip() == "on",
                    "description": ALLOWED_BOOLEANS[name],
                }
    return result


def set_boolean(name, enable):
    """Bascule un boolean whiteliste de maniere persistante (-P).

    Retourne (ok: bool, message: str). Refuse tout nom hors whitelist."""
    if name not in ALLOWED_BOOLEANS:
        return False, f"Boolean non autorise : {name}"
    if not is_available():
        return False, "SELinux n'est pas actif sur ce systeme"
    value = "on" if enable else "off"
    r = _run(["sudo", "-n", "setsebool", "-P", name, value], timeout=30)
    if r is None:
        return False, "setsebool introuvable ou timeout"
    if r.returncode != 0:
        return False, (r.stderr.strip() or "Echec setsebool (sudo requis ?)")
    return True, f"{name} = {value}"


def recent_denials(minutes=10, limit=50):
    """Denials AVC recents (lecture seule), via journald setroubleshoot.

    Best effort : si setroubleshoot n'est pas installe ou le journal illisible,
    renvoie une liste vide. Ne necessite pas sudo si l'utilisateur est dans le
    groupe systemd-journal (cas par defaut sur Fedora)."""
    try:
        minutes = max(1, min(int(minutes), 1440))
    except (ValueError, TypeError):
        minutes = 10
    r = _run(["journalctl", "-t", "setroubleshoot", "--since", f"-{minutes}min",
              "--no-pager", "-o", "cat"], timeout=15)
    if r is None or r.returncode != 0:
        return []
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    return lines[-limit:]


def status(denial_minutes=10):
    mode = get_mode()
    return {
        "mode": mode,
        "available": mode in ("Enforcing", "Permissive"),
        "booleans": get_booleans(),
        "denials": recent_denials(denial_minutes),
    }
