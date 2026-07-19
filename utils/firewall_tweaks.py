"""Durcissement firewalld : fermeture de la plage 1025-65535 ouverte par defaut.

La zone FedoraWorkstation (celle de Fedora Workstation ET du Spin KDE) ouvre
par defaut TOUTE la plage de ports non privilegies 1025-65535 en TCP et UDP :
n'importe quel service utilisateur (serveur de dev, Postgres publie par Docker,
Portainer...) devient joignable depuis tout le reseau local. Ce tweak retire
ces deux plages de la zone par defaut, en permanent puis `--reload` (runtime
aligne). Reversible : la restauration re-ajoute les plages (etat d'origine
Fedora). Les commandes passent par `sudo -n` (cache sudo du launcher).
"""
import subprocess

# Plages ouvertes par defaut dans la zone FedoraWorkstation.
PORT_RANGES = ("1025-65535/tcp", "1025-65535/udp")


def _firewalld(args, timeout=15):
    """`sudo -n firewall-cmd <args>`. Retourne (ok, stdout, stderr)."""
    try:
        r = subprocess.run(["sudo", "-n", "firewall-cmd"] + args,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return False, "", "firewall-cmd introuvable"
    except subprocess.TimeoutExpired:
        return False, "", "Timeout firewall-cmd"


def _default_zone():
    ok, out, _ = _firewalld(["--get-default-zone"])
    return out if ok and out else None


def status():
    """Etat du durcissement.

    `hardened` = firewalld joignable ET aucune des deux plages presente dans
    la zone par defaut (runtime). `open_ranges` liste ce qui reste ouvert."""
    ok, state, err = _firewalld(["--state"])
    if not ok or "running" not in state.lower():
        return {"available": False, "zone": None, "open_ranges": [],
                "hardened": False, "error": err or "firewalld inactif"}

    zone = _default_zone()
    if not zone:
        return {"available": False, "zone": None, "open_ranges": [],
                "hardened": False, "error": "zone par defaut introuvable"}

    ok, ports_out, err = _firewalld(["--zone", zone, "--list-ports"])
    if not ok:
        return {"available": False, "zone": zone, "open_ranges": [],
                "hardened": False, "error": err or "list-ports a echoue"}

    ports = ports_out.split()
    open_ranges = [p for p in PORT_RANGES if p in ports]
    return {"available": True, "zone": zone, "open_ranges": open_ranges,
            "hardened": not open_ranges}


def apply():
    """Retire les plages 1025-65535 (permanent + reload). (ok, message)."""
    zone = _default_zone()
    if not zone:
        return False, "Zone firewalld par defaut introuvable (sudo requis ?)"
    for rng in PORT_RANGES:
        ok, _, err = _firewalld(["--permanent", "--zone", zone,
                                 "--remove-port", rng])
        if not ok:
            return False, err or f"Echec retrait de {rng}"
    ok, _, err = _firewalld(["--reload"], timeout=30)
    if not ok:
        return False, err or "Echec firewall-cmd --reload"
    return True, f"Plage 1025-65535 fermee dans la zone {zone}"


def remove():
    """Restaure les plages par defaut Fedora (permanent + reload). (ok, message)."""
    zone = _default_zone()
    if not zone:
        return False, "Zone firewalld par defaut introuvable (sudo requis ?)"
    for rng in PORT_RANGES:
        ok, _, err = _firewalld(["--permanent", "--zone", zone,
                                 "--add-port", rng])
        if not ok:
            return False, err or f"Echec re-ajout de {rng}"
    ok, _, err = _firewalld(["--reload"], timeout=30)
    if not ok:
        return False, err or "Echec firewall-cmd --reload"
    return True, f"Plage 1025-65535 rouverte dans la zone {zone} (defaut Fedora)"
