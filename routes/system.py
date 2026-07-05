"""Routes /api/system - gestion systeme directe (pare-feu firewalld, mise a jour DNF)."""
import os
import subprocess
import threading
import time

from flask import Blueprint, jsonify

from routes.shared import (
    SCRIPT_TIMEOUT,
    log_error,
    log_info,
    log_success,
    start_background_task,
)

bp = Blueprint("system", __name__)

# Compteur de mises a jour disponibles : dnf check-update est lent (metadata),
# on cache le resultat cote serveur. Invalide apres une mise a jour reussie.
_UPDATES_CACHE_TTL = 900  # 15 min
_updates_cache = {"count": None, "ts": 0.0}
_updates_lock = threading.Lock()


def _run_check_update():
    """`dnf check-update -q` en locale C. Retourne (returncode, stdout).

    Codes dnf : 0 = a jour, 100 = mises a jour disponibles, autre = erreur.
    Isole pour etre mocke dans les tests."""
    env = {**os.environ, "LC_ALL": "C"}
    r = subprocess.run(["sudo", "-n", "dnf", "check-update", "-q"],
                       capture_output=True, text=True, timeout=300, env=env)
    return r.returncode, r.stdout


def _count_updates(stdout):
    """Compte les lignes 'paquet.arch  version  repo' de dnf check-update.

    Ignore les lignes vides et la section 'Obsoleting Packages' (les paquets
    y figurent en doublon de leur remplacant deja compte)."""
    count = 0
    in_obsoleting = False
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("obsoleting"):
            in_obsoleting = True
            continue
        if in_obsoleting:
            continue
        parts = line.split()
        if len(parts) >= 3 and "." in parts[0]:
            count += 1
    return count


def _invalidate_updates_cache():
    with _updates_lock:
        _updates_cache.update(count=None, ts=0.0)


@bp.route('/api/system/updates')
def updates_available():
    """Nombre de mises a jour DNF disponibles (cache 15 min)."""
    with _updates_lock:
        cached = _updates_cache["count"]
        fresh = time.time() - _updates_cache["ts"] < _UPDATES_CACHE_TTL
    if cached is not None and fresh:
        return jsonify({"success": True, "updates": cached, "cached": True})

    try:
        rc, out = _run_check_update()
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    if rc == 0:
        count = 0
    elif rc == 100:
        count = _count_updates(out)
    else:
        return jsonify({"success": False,
                        "error": f"dnf check-update a echoue (code {rc})"})

    with _updates_lock:
        _updates_cache.update(count=count, ts=time.time())
    return jsonify({"success": True, "updates": count, "cached": False})


@bp.route('/api/system/update', methods=['POST'])
def system_update_route():
    """Mise a jour systeme (dnf upgrade) en tache de fond, sortie relayee en SSE."""
    # Import local : evite le cycle routes.system <-> routes.fedora_wizards a l'import.
    from routes.fedora_wizards import _stream_sudo

    def worker():
        log_info("Mise a jour systeme (dnf upgrade --refresh)...")
        if _stream_sudo(["dnf", "upgrade", "-y", "--refresh"],
                        timeout=SCRIPT_TIMEOUT) != 0:
            log_error("Echec de la mise a jour systeme")
            return False
        _invalidate_updates_cache()
        log_success("Systeme a jour")
        return True

    if not start_background_task("Mise a jour systeme", worker):
        return jsonify({"success": False, "error": "Tache en cours"}), 409
    return jsonify({"success": True, "started": True,
                    "message": "Mise a jour systeme lancee (suivez les logs)"})


def _firewalld(args, timeout=10):
    try:
        r = subprocess.run(["sudo", "-n", "firewall-cmd"] + args,
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return False, "", str(e)


@bp.route('/api/system/firewall')
def firewall_status():
    ok, out, err = _firewalld(["--state"])
    if not ok:
        return jsonify({"success": False, "error": err or "sudo requis ou firewalld absent"})

    # Obtenir plus d'infos
    _, zone_out, _ = _firewalld(["--get-default-zone"])
    _, list_out, _ = _firewalld(["--list-all"])

    return jsonify({
        "success": True,
        "enabled": "running" in out.lower(),
        "default_zone": zone_out,
        "output": list_out,
    })


@bp.route('/api/system/firewall/enable', methods=['POST'])
def firewall_enable():
    # firewalld est gere par systemd
    r = subprocess.run(
        ["sudo", "-n", "systemctl", "enable", "--now", "firewalld"],
        capture_output=True, text=True, timeout=10
    )
    if r.returncode != 0:
        return jsonify({"success": False, "error": r.stderr.strip() or "Echec activation"}), 500
    return jsonify({"success": True, "message": "Pare-feu active"})


@bp.route('/api/system/firewall/disable', methods=['POST'])
def firewall_disable():
    r = subprocess.run(
        ["sudo", "-n", "systemctl", "disable", "--now", "firewalld"],
        capture_output=True, text=True, timeout=10
    )
    if r.returncode != 0:
        return jsonify({"success": False, "error": r.stderr.strip() or "Echec desactivation"}), 500
    return jsonify({"success": True, "message": "Pare-feu desactive"})
