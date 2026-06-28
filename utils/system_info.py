"""Detection systeme : identite distribution, kernel patches, stack graphique, LSM, sysctls.

Lit /etc, /proc, /sys et lance quelques commandes legeres. Resultat mis en cache
30 secondes (l'info change rarement). Donne a l'UI une vue claire de ce que la
distribution fait deja, evitant la duplication de tweaks.
"""
import os
import re
import subprocess
import time
from pathlib import Path

_cache = {"data": None, "ts": 0}
_CACHE_TTL = 30


def _read_file(path):
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def _which(cmd):
    import shutil
    return shutil.which(cmd)


def _os_release():
    """Parse /etc/os-release en dict."""
    info = {}
    for line in _read_file("/etc/os-release").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            info[k] = v.strip().strip('"')
    return info


def _kernel_patches():
    """Detecte les patches CACHY/BORE/NTSYNC dans /boot/config-<kernel>."""
    kver = os.uname().release
    cfg = _read_file(f"/boot/config-{kver}")
    if not cfg:
        # Fallback /proc/config.gz
        try:
            import gzip
            cfg = gzip.decompress(Path("/proc/config.gz").read_bytes()).decode()
        except (OSError, ValueError):
            return {"detected": False, "patches": [], "hz": None}

    patches = []
    if "CONFIG_CACHY=y" in cfg:
        patches.append("CachyOS")
    if "CONFIG_SCHED_BORE=y" in cfg:
        patches.append("BORE")
    if "CONFIG_NTSYNC=y" in cfg:
        patches.append("NTSYNC")
    if "CONFIG_PREEMPT_DYNAMIC=y" in cfg:
        patches.append("PREEMPT_DYN")

    hz = None
    m = re.search(r"^CONFIG_HZ=(\d+)$", cfg, re.MULTILINE)
    if m:
        hz = int(m.group(1))

    return {"detected": True, "patches": patches, "hz": hz}


def _plasma_version():
    try:
        r = subprocess.run(["plasmashell", "--version"],
                           capture_output=True, text=True, timeout=3)
        m = re.search(r"plasmashell\s+(\S+)", r.stdout)
        if m:
            return m.group(1)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _mesa_version():
    try:
        # x86_64 prioritaire — eviter la concatenation x86_64+i686 multi-archs
        r = subprocess.run(
            ["rpm", "-q", "--qf", "%{VERSION}\\n", "mesa-dri-drivers"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            versions = [v for v in r.stdout.strip().splitlines() if v]
            return versions[0] if versions else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _lsm_list():
    """Liste des LSM actifs (capability,apparmor,landlock,bpf,...)."""
    return _read_file("/sys/kernel/security/lsm").strip().split(",") if _read_file("/sys/kernel/security/lsm") else []


def _selinux_state():
    """Retourne 'disabled' / 'permissive' / 'enforcing' / None."""
    try:
        r = subprocess.run(["getenforce"], capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            return r.stdout.strip().lower()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Fallback : parse /etc/selinux/config
    cfg = _read_file("/etc/selinux/config")
    m = re.search(r"^SELINUX=(\w+)", cfg, re.MULTILINE)
    return m.group(1).lower() if m else None


def _sysctl_check(keys):
    """Lit plusieurs sysctls en une passe. Retourne dict {key: value|None}."""
    if not keys:
        return {}
    try:
        r = subprocess.run(["sysctl", "-n", *keys],
                           capture_output=True, text=True, timeout=3)
        if r.returncode != 0:
            return dict.fromkeys(keys)
        values = r.stdout.strip().splitlines()
        return dict(zip(keys, values, strict=False))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return dict.fromkeys(keys)


def _gaming_sysctls_status():
    """Verifie si les sysctls gaming Nobara sont actives."""
    vals = _sysctl_check([
        "kernel.split_lock_mitigate",
        "vm.max_map_count",
        "net.ipv4.tcp_mtu_probing",
        "vm.swappiness",
    ])
    return {
        "split_lock_mitigate": vals.get("kernel.split_lock_mitigate"),
        "max_map_count": vals.get("vm.max_map_count"),
        "tcp_mtu_probing": vals.get("net.ipv4.tcp_mtu_probing"),
        "swappiness": vals.get("vm.swappiness"),
    }


def _btrfs_root_info():
    """Info sur la racine si elle est btrfs."""
    mounts = _read_file("/proc/mounts")
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        if parts[1] == "/" and parts[2] == "btrfs":
            opts = parts[3].split(",")
            return {
                "is_btrfs": True,
                "options": opts,
                "compress": next((o.split("=")[1] for o in opts if o.startswith("compress=")), None),
                "subvol": next((o.split("=")[1] for o in opts if o.startswith("subvol=")), None),
                "discard": next((o for o in opts if o.startswith("discard")), None),
            }
    return {"is_btrfs": False}


def _zram_info():
    """Detection zram et taille."""
    mounts = _read_file("/proc/swaps")
    zram_devices = []
    for line in mounts.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3 and "zram" in parts[0]:
            try:
                size_kb = int(parts[2])
                zram_devices.append({"name": Path(parts[0]).name,
                                     "size_mb": size_kb // 1024})
            except ValueError:
                pass
    return zram_devices


def _session_type():
    return {
        "type": os.environ.get("XDG_SESSION_TYPE", ""),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
    }


def gather():
    """Aggregateur — toutes les infos en un appel. Cache 30s."""
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < _CACHE_TTL:
        return _cache["data"]

    osr = _os_release()
    data = {
        "os": {
            "name": osr.get("NAME", ""),
            "version": osr.get("VERSION", ""),
            "pretty": osr.get("PRETTY_NAME", ""),
            "id": osr.get("ID", ""),
            "variant": osr.get("VARIANT", ""),
        },
        "kernel": {
            "release": os.uname().release,
            "machine": os.uname().machine,
            **_kernel_patches(),
        },
        "plasma": _plasma_version(),
        "mesa": _mesa_version(),
        "session": _session_type(),
        "security": {
            "lsm": _lsm_list(),
            "selinux": _selinux_state(),
        },
        "gaming_sysctls": _gaming_sysctls_status(),
        "btrfs_root": _btrfs_root_info(),
        "zram": _zram_info(),
    }

    _cache["data"] = data
    _cache["ts"] = now
    return data
