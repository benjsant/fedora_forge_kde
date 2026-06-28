"""Gestion des services systemd : status + toggle enable/disable.

Whitelist stricte (ALLOWED_SERVICES) — pas de toggle arbitraire. Les toggles
mutatifs passent par `sudo -n systemctl` : reposent sur le cache sudo entretenu
par le launcher bash. Si le cache expire, l'operation echoue proprement (pas
de prompt password silencieux qui bloquerait l'UI).
"""
import subprocess

# Services exposes dans l'UI — whitelist stricte
ALLOWED_SERVICES = {
    "fstrim.timer":      "TRIM SSD hebdomadaire (longevite SSD)",
    "bluetooth.service": "Bluetooth (casques, manettes, claviers BT)",
    "cups.service":      "Impression (CUPS)",
    "sshd.service":      "Serveur SSH entrant (connexions distantes)",
    "firewalld.service": "Pare-feu firewalld",
}


def _systemctl_query(args, timeout=3):
    """Wrapper systemctl en lecture seule (pas de sudo)."""
    try:
        return subprocess.run(
            ["systemctl"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def get_service_status(name):
    """Retourne un dict de status, ou None si introuvable."""
    if name not in ALLOWED_SERVICES:
        return None

    r_active = _systemctl_query(["is-active", name])
    r_enabled = _systemctl_query(["is-enabled", name])
    if r_active is None or r_enabled is None:
        return None

    raw_active = r_active.stdout.strip()
    raw_enabled = r_enabled.stdout.strip()

    # `is-enabled` retourne stderr "Failed to get unit file state ... not-found"
    # quand le service n'est pas installe.
    if raw_enabled == "" and ("not-found" in r_enabled.stderr.lower()
                              or "no such" in r_enabled.stderr.lower()):
        return None

    return {
        "name": name,
        "description": ALLOWED_SERVICES[name],
        "active": raw_active == "active",
        "enabled": raw_enabled in ("enabled", "alias", "static", "enabled-runtime"),
        "raw_active": raw_active,
        "raw_enabled": raw_enabled,
    }


def list_services():
    """Liste tous les services whitelistes avec leur status (missing si absent)."""
    results = []
    for name in ALLOWED_SERVICES:
        status = get_service_status(name)
        if status is None:
            status = {
                "name": name,
                "description": ALLOWED_SERVICES[name],
                "active": False,
                "enabled": False,
                "raw_active": "missing",
                "raw_enabled": "missing",
            }
        results.append(status)
    return results


def toggle_service(name, enable):
    """Enable+start ou disable+stop un service. Retourne (success, error_msg)."""
    if name not in ALLOWED_SERVICES:
        return False, f"Service non autorise : {name}"

    action = ["enable", "--now"] if enable else ["disable", "--now"]
    try:
        r = subprocess.run(
            ["sudo", "-n", "systemctl"] + action + [name],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return True, ""
        err = r.stderr.strip() or "echec systemctl"
        # Detection du cas "sudo demande mot de passe"
        if "password is required" in err.lower() or "a terminal is required" in err.lower():
            err = "Cache sudo expire — relancez l'app ou tapez `sudo -v` au terminal"
        return False, err
    except subprocess.TimeoutExpired:
        return False, "timeout systemctl"
    except FileNotFoundError:
        return False, "systemctl introuvable"
