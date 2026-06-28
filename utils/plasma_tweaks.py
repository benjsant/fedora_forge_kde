"""Reset plasmashell et nettoyage de caches.

Resout les bugs de panel/widgets que tout utilisateur KDE finit par rencontrer
(barre des taches qui ne repond plus, widgets geles, miniatures cassees).
"""
import contextlib
import shutil
import subprocess
import time
from pathlib import Path

# Caches a vider — chemins relatifs a ~/.cache/
_CACHE_NAMES = [
    "thumbnails",
    "krunner",
    "icon-cache.kcache",
    "ksycoca6",
]


def _dir_size(path):
    """Taille recursive d'un dossier en octets (meilleur effort)."""
    total = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                with contextlib.suppress(OSError):
                    total += p.stat().st_size
    except OSError:
        pass
    return total


def clear_caches():
    """Vide les caches Plasma + thumbnails + krunner.

    Retourne {freed_bytes, cleared: list[str]}.
    """
    cache_dir = Path.home() / ".cache"
    total_freed = 0
    cleared = []

    if not cache_dir.exists():
        return {"freed_bytes": 0, "cleared": []}

    targets = []
    for name in _CACHE_NAMES:
        targets.append(cache_dir / name)
    # ~/.cache/plasma* (plasma, plasma-systemmonitor, plasmashell, ...)
    for p in cache_dir.glob("plasma*"):
        targets.append(p)

    for p in targets:
        if not p.exists():
            continue
        try:
            if p.is_dir():
                size = _dir_size(p)
                shutil.rmtree(p)
                p.mkdir(parents=True)
            else:
                size = p.stat().st_size
                p.unlink()
            total_freed += size
            cleared.append(p.name)
        except OSError:
            pass

    return {"freed_bytes": total_freed, "cleared": cleared}


def reset_plasmashell():
    """Tue plasmashell, vide son cache, le relance detache du process Flask."""
    # 1. Quit propre via kquitapp6 (fallback killall si echec)
    r = subprocess.run(["kquitapp6", "plasmashell"], capture_output=True, timeout=10)
    if r.returncode != 0:
        subprocess.run(["killall", "-q", "plasmashell"], capture_output=True, timeout=5)
        time.sleep(0.3)

    # 2. Vide les caches plasma seulement (pas tous les caches)
    cache_dir = Path.home() / ".cache"
    for p in cache_dir.glob("plasma*"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

    # 3. Relance detache
    time.sleep(0.5)
    binary = shutil.which("kstart6") or shutil.which("plasmashell")
    if binary is None:
        return False
    args = [binary, "plasmashell"] if binary.endswith("kstart6") else [binary]
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True
