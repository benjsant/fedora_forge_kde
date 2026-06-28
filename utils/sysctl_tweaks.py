"""Sysctls gaming optionnels (equivalents des reglages Nobara).

Contrairement aux drop-in audio user-level, ces parametres sont systeme : ils
vivent dans /etc/sysctl.d/ et exigent sudo. L'ecriture passe par `sudo -n tee`
(le serveur Flask est lance avec un cache sudo par le launcher), la suppression
par `sudo -n rm`. Apres chaque changement on recharge via `sysctl --system`.

Reglages appliques (alignes sur Nobara) :
- kernel.split_lock_mitigate = 0  : evite les penalites de perf sur certains jeux
- vm.max_map_count = 16777216     : requis par de nombreux jeux Proton/Wine
- net.ipv4.tcp_mtu_probing = 1     : meilleure tolerance MTU sur certains reseaux
"""
import os
import subprocess

DROP_IN = "/etc/sysctl.d/99-fedorakdeforge-gaming.conf"

# Cle sysctl -> valeur cible. Ordre conserve pour le fichier genere.
GAMING_SYSCTLS = {
    "kernel.split_lock_mitigate": "0",
    "vm.max_map_count": "16777216",
    "net.ipv4.tcp_mtu_probing": "1",
}

_HEADER = "# Genere par FedoraForgeKDE - sysctls gaming optionnels.\n"


def _file_contents():
    lines = [_HEADER]
    lines += [f"{k} = {v}\n" for k, v in GAMING_SYSCTLS.items()]
    return "".join(lines)


def _live_values():
    """Valeurs sysctl actuellement actives. {cle: valeur|None}."""
    keys = list(GAMING_SYSCTLS)
    try:
        r = subprocess.run(["sysctl", "-n", *keys],
                           capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return dict.fromkeys(keys)
        vals = r.stdout.strip().splitlines()
        return dict(zip(keys, vals, strict=False))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return dict.fromkeys(keys)


def status():
    """Etat des sysctls gaming.

    `applied` = drop-in present ET toutes les valeurs live conformes a la cible.
    `drop_in_exists` distingue "fichier present mais pas encore recharge"."""
    live = _live_values()
    drop_in = os.path.exists(DROP_IN)
    active = all(str(live.get(k)) == v for k, v in GAMING_SYSCTLS.items())
    return {
        "applied": drop_in and active,
        "drop_in_exists": drop_in,
        "active": active,
        "target": dict(GAMING_SYSCTLS),
        "current": live,
    }


def _reload():
    return subprocess.run(["sudo", "-n", "sysctl", "--system"],
                          capture_output=True, text=True, timeout=30)


def apply():
    """Ecrit le drop-in et recharge. Retourne (ok: bool, message: str)."""
    try:
        w = subprocess.run(["sudo", "-n", "tee", DROP_IN],
                          input=_file_contents(), capture_output=True,
                          text=True, timeout=15)
        if w.returncode != 0:
            return False, (w.stderr.strip() or "Echec ecriture du drop-in (sudo requis)")
        r = _reload()
        if r.returncode != 0:
            return False, (r.stderr.strip() or "Echec sysctl --system")
        return True, "Sysctls gaming appliques"
    except subprocess.TimeoutExpired:
        return False, "Timeout lors de l'application des sysctls"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"


def remove():
    """Supprime le drop-in et recharge. Idempotent. Retourne (ok, message)."""
    try:
        if not os.path.exists(DROP_IN):
            return True, "Sysctls gaming deja absents"
        d = subprocess.run(["sudo", "-n", "rm", "-f", DROP_IN],
                          capture_output=True, text=True, timeout=15)
        if d.returncode != 0:
            return False, (d.stderr.strip() or "Echec suppression du drop-in")
        _reload()
        return True, "Sysctls gaming retires (valeurs live restaurees au prochain boot)"
    except subprocess.TimeoutExpired:
        return False, "Timeout lors du retrait des sysctls"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"
