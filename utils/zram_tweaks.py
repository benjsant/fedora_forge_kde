"""Reglage zram "facon Nobara" : compression zstd + swappiness eleve.

Fedora active deja un swap zram par defaut (paquet zram-generator-defaults,
`zram-size = min(ram, 8192)`), mais avec l'algo `lzo-rle` et `vm.swappiness=60`.
Nobara, sur la meme base, tourne en `zstd` (meilleur taux de compression, donc
swap effectif plus grand) avec `vm.swappiness=100` (pertinent quand le swap est
en RAM compressee, tres rapide).

Ce tweak materialise cet ecart :
- drop-in `/etc/systemd/zram-generator.conf` forcant `compression-algorithm = zstd`
  (la taille reste le defaut Fedora) ;
- drop-in sysctl `/etc/sysctl.d/99-fedorakdeforge-zram.conf` pour `vm.swappiness`.

L'algo s'applique a la recreation du device (restart du service zram) ; la
swappiness s'applique immediatement via `sysctl --system`. Tout passe par
`sudo -n` (cache sudo du launcher), comme les autres tweaks. Reversible : `remove`
retire les deux drop-in (retour au defaut Fedora au prochain boot).
"""
import os
import re
import subprocess

ZRAM_CONF = "/etc/systemd/zram-generator.conf"
SYSCTL_DROP_IN = "/etc/sysctl.d/99-fedorakdeforge-zram.conf"
ZRAM_SERVICE = "systemd-zram-setup@zram0.service"

TARGET_ALGO = "zstd"
TARGET_SWAPPINESS = 100
# On conserve la taille par defaut de Fedora pour ne pas changer le dimensionnement.
_ZRAM_SIZE = "min(ram, 8192)"

_ZRAM_HEADER = "# Genere par FedoraForgeKDE - zram facon Nobara (zstd).\n"
_SYSCTL_HEADER = "# Genere par FedoraForgeKDE - swappiness pour swap zram.\n"


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def zram_present():
    """True si un device zram0 existe sur ce systeme."""
    return os.path.isdir("/sys/block/zram0")


def current_algo():
    """Algo de compression actif de zram0, ou None. Le noyau expose la liste avec
    l'actif entre crochets : 'lzo-rle lzo lz4 [zstd] deflate 842'."""
    raw = _read("/sys/block/zram0/comp_algorithm")
    if not raw:
        return None
    m = re.search(r"\[([\w-]+)\]", raw)
    return m.group(1) if m else None


def current_swappiness():
    raw = _read("/proc/sys/vm/swappiness")
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def _zram_conf():
    return (f"{_ZRAM_HEADER}[zram0]\n"
            f"zram-size = {_ZRAM_SIZE}\n"
            f"compression-algorithm = {TARGET_ALGO}\n")


def _sysctl_conf():
    return f"{_SYSCTL_HEADER}vm.swappiness = {TARGET_SWAPPINESS}\n"


def status():
    """Etat du tweak zram.

    `applied` = valeurs LIVE conformes (algo zstd ET swappiness cible). `conf_exists`
    distingue "configure mais service zram pas encore relance"."""
    algo = current_algo()
    swp = current_swappiness()
    return {
        "zram_present": zram_present(),
        "current_algo": algo,
        "current_swappiness": swp,
        "target_algo": TARGET_ALGO,
        "target_swappiness": TARGET_SWAPPINESS,
        "conf_exists": os.path.exists(ZRAM_CONF),
        "applied": algo == TARGET_ALGO and swp == TARGET_SWAPPINESS,
    }


def _sudo(cmd, timeout=30, **kw):
    return subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True,
                          timeout=timeout, **kw)


def apply():
    """Ecrit les deux drop-in, recharge swappiness et relance le service zram.
    Retourne (ok: bool, message: str)."""
    if not zram_present():
        return False, "Aucun device zram sur ce systeme (zram-generator absent ?)"
    try:
        w = _sudo(["tee", ZRAM_CONF], input=_zram_conf(), timeout=15)
        if w.returncode != 0:
            return False, (w.stderr.strip() or "Echec ecriture zram-generator.conf (sudo requis)")
        s = _sudo(["tee", SYSCTL_DROP_IN], input=_sysctl_conf(), timeout=15)
        if s.returncode != 0:
            return False, (s.stderr.strip() or "Echec ecriture du drop-in swappiness")
        # Swappiness : effet immediat.
        r = _sudo(["sysctl", "--system"])
        if r.returncode != 0:
            return False, (r.stderr.strip() or "Echec sysctl --system")
        # Algo zstd : ne s'applique qu'a la recreation du device zram.
        _sudo(["systemctl", "daemon-reload"])
        rs = _sudo(["systemctl", "restart", ZRAM_SERVICE], timeout=60)
        if rs.returncode != 0:
            return True, ("Swappiness appliquee ; l'algo zstd s'appliquera au "
                          "prochain demarrage (echec du restart zram a chaud)")
        return True, f"zram en {TARGET_ALGO}, swappiness {TARGET_SWAPPINESS} (facon Nobara)"
    except subprocess.TimeoutExpired:
        return False, "Timeout lors de l'application du tweak zram"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"


def remove():
    """Retire les deux drop-in (retour au defaut Fedora). Idempotent. (ok, message)."""
    try:
        if not os.path.exists(ZRAM_CONF) and not os.path.exists(SYSCTL_DROP_IN):
            return True, "Tweak zram deja absent (defaut Fedora)"
        for path in (ZRAM_CONF, SYSCTL_DROP_IN):
            if os.path.exists(path):
                d = _sudo(["rm", "-f", path], timeout=15)
                if d.returncode != 0:
                    return False, (d.stderr.strip() or f"Echec suppression de {path}")
        _sudo(["sysctl", "--system"])
        _sudo(["systemctl", "daemon-reload"])
        _sudo(["systemctl", "restart", ZRAM_SERVICE], timeout=60)
        return True, "Tweak zram retire (retour au defaut Fedora, effet complet au reboot)"
    except subprocess.TimeoutExpired:
        return False, "Timeout lors du retrait du tweak zram"
    except FileNotFoundError as e:
        return False, f"Commande introuvable : {e}"
