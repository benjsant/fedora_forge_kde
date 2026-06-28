"""Schedulers sched-ext (alternative SANS risque au kernel CachyOS).

Le kernel Fedora (>= 6.12) embarque sched_ext (CONFIG_SCHED_CLASS_EXT=y). On peut
donc attacher un scheduler eBPF gaming/latence (scx_lavd...) EN USERSPACE, sur le
kernel Fedora standard, sans remplacer le noyau :
- gain d'interactivite proche de BORE (le scheduler de CachyOS),
- aucun risque de boot : un watchdog noyau detache automatiquement le scheduler
  s'il defaille, retour au scheduler par defaut,
- reversible a chaud (on arrete le service).

Le paquet scx-scheds fournit les binaires mais aucun service systemd. On gere
donc notre propre unit minimale, persistante et nettoyable.
"""
import os
import shutil
import subprocess

# Schedulers exposes (whitelist stricte). scx_lavd = profil gaming/latence,
# c'est celui qu'utilise le profil "Gaming" de CachyOS.
ALLOWED_SCHEDULERS = {
    "scx_lavd": "Gaming / faible latence (recommande, profil gaming CachyOS)",
    "scx_bpfland": "Interactivite desktop + jeux",
    "scx_rusty": "Generaliste multi-coeurs / multi-CCX",
}
DEFAULT_SCHEDULER = "scx_lavd"

PACKAGE = "scx-scheds"
UNIT_NAME = "fedoraforge-scx.service"
UNIT_PATH = f"/etc/systemd/system/{UNIT_NAME}"

# /sys expose par sched_ext : 'state' (enabled/disabled) et 'root/ops' (nom du
# scheduler actif).
_SYSFS_STATE = "/sys/kernel/sched_ext/state"
_SYSFS_OPS = "/sys/kernel/sched_ext/root/ops"


def kernel_supports():
    """True si le noyau courant expose sched_ext."""
    return os.path.isdir("/sys/kernel/sched_ext")


def scx_installed():
    """True si les binaires scx (au moins le scheduler par defaut) sont la."""
    return shutil.which(DEFAULT_SCHEDULER) is not None


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None


def active_scheduler():
    """Nom du scheduler sched-ext actif, ou None si aucun."""
    if (_read(_SYSFS_STATE) or "").lower() != "enabled":
        return None
    return _read(_SYSFS_OPS) or None


def _unit_enabled():
    r = subprocess.run(["systemctl", "is-enabled", UNIT_NAME],
                       capture_output=True, text=True, timeout=10)
    return r.stdout.strip() == "enabled"


def status():
    active = active_scheduler()
    return {
        "kernel_supported": kernel_supports(),
        "scx_installed": scx_installed(),
        "active": active is not None,
        "active_scheduler": active,
        "unit_enabled": _unit_enabled() if os.path.exists(UNIT_PATH) else False,
        "schedulers": dict(ALLOWED_SCHEDULERS),
        "default": DEFAULT_SCHEDULER,
    }


def _sudo(cmd, timeout=120, **kw):
    return subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True,
                          timeout=timeout, **kw)


def _ensure_installed():
    """Installe scx-scheds si absent. Retourne (ok, message)."""
    if scx_installed():
        return True, ""
    r = _sudo(["dnf", "install", "-y", PACKAGE], timeout=600)
    if r.returncode != 0:
        return False, (r.stderr.strip() or f"Echec installation {PACKAGE}")
    if not scx_installed():
        return False, f"{PACKAGE} installe mais binaires introuvables"
    return True, ""


def enable(scheduler=DEFAULT_SCHEDULER):
    """Active un scheduler sched-ext de maniere persistante. (ok, message)."""
    if scheduler not in ALLOWED_SCHEDULERS:
        return False, f"Scheduler non autorise : {scheduler}"
    if not kernel_supports():
        return False, "Le noyau courant n'expose pas sched_ext (CONFIG_SCHED_CLASS_EXT)"

    ok, msg = _ensure_installed()
    if not ok:
        return False, msg

    binary = shutil.which(scheduler)
    if not binary:
        return False, f"Binaire {scheduler} introuvable apres installation"

    # Unit minimale : tant qu'elle tourne, le scheduler est attache ; l'arret le
    # detache (retour au scheduler par defaut).
    unit = (
        "[Unit]\n"
        f"Description=FedoraForgeKDE sched-ext ({scheduler})\n"
        "After=multi-user.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={binary}\n"
        "Restart=on-failure\n"
        "RestartSec=2\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    w = _sudo(["tee", UNIT_PATH], input=unit, timeout=15)
    if w.returncode != 0:
        return False, (w.stderr.strip() or "Echec ecriture de l'unit systemd (sudo ?)")

    _sudo(["systemctl", "daemon-reload"])
    r = _sudo(["systemctl", "enable", "--now", UNIT_NAME], timeout=30)
    if r.returncode != 0:
        return False, (r.stderr.strip() or "Echec activation du service scx")
    return True, f"Scheduler {scheduler} active"


def disable():
    """Desactive le scheduler et retire l'unit. Idempotent. (ok, message)."""
    if os.path.exists(UNIT_PATH):
        _sudo(["systemctl", "disable", "--now", UNIT_NAME], timeout=30)
        d = _sudo(["rm", "-f", UNIT_PATH], timeout=10)
        if d.returncode != 0:
            return False, (d.stderr.strip() or "Echec suppression de l'unit")
        _sudo(["systemctl", "daemon-reload"])
        return True, "Scheduler sched-ext desactive (retour au scheduler par defaut)"
    return True, "Aucun scheduler sched-ext gere par FedoraForgeKDE"
