"""Routes legacy : status, logs, execute, theme."""
import json
import os
import queue
import shutil
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

from flask import Blueprint, Response, jsonify

from routes.shared import (
    cancel_current_task,
    current_task,
    log_error,
    log_exc,
    log_info,
    log_queue,
    log_success,
    log_warn,
    run_script,
    task_lock,
    update_task_status,
)
from utils import system_update, timeshift_available
from utils.power import get_power_state
from utils.system_info import gather as gather_system_info
from utils.theme_manager import ThemeManager

bp = Blueprint("legacy", __name__)

_status_cache = {"data": None, "ts": 0}
STATUS_CACHE_TTL = 8

# Services qui echouent typiquement en VM/virtualisation sans que ce soit un vrai
# probleme (pas de materiel MCE expose au noyau invite). On les exclut du compteur
# pour eviter une fausse alerte rouge lors des tests en VM.
_IGNORED_FAILED_UNITS = {"mcelog.service"}


def _count_failed_services(stdout):
    """Compte les services en echec, hors artefacts de VM connus."""
    count = 0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.split()[0] in _IGNORED_FAILED_UNITS:
            continue
        count += 1
    return count


def _tool_available(name):
    try:
        return subprocess.run(["which", name], capture_output=True, timeout=3).returncode == 0
    except Exception:
        return False


def _check_system():
    checks = {"internet": False, "sudo": False, "python_version": True}
    try:
        socket.create_connection(("fedoraproject.org", 80), timeout=3)
        checks["internet"] = True
    except Exception:
        pass
    try:
        r = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=1)
        checks["sudo"] = r.returncode == 0
    except Exception:
        pass
    checks["tools"] = {
        t: _tool_available(t)
        for t in ("kwriteconfig6", "kreadconfig6", "dnf", "flatpak", "git", "firewall-cmd")
    }
    checks["disk_free_gb"] = round(shutil.disk_usage("/").free / (1024 ** 3), 1)
    checks["timeshift"] = timeshift_available()
    # `power` est None sur un desktop sans batterie (UI cache l'indicateur).
    checks["power"] = get_power_state()
    # Services systemd en erreur — diagnostic rapide
    try:
        r = subprocess.run(
            ["systemctl", "--failed", "--no-legend", "--no-pager", "--plain"],
            capture_output=True, text=True, timeout=3,
        )
        checks["failed_services"] = _count_failed_services(r.stdout)
    except Exception:
        checks["failed_services"] = None
    return checks


def _get_package_counts():
    files = {
        "dnf": "configs/install.json",
        "optional": "configs/optional_install.json",
        "flatpak": "configs/flatpak.json",
        "external": "configs/external_packages.json",
        "themes_gtk": "configs/themes_gtk.json",
        "themes_icons": "configs/themes_icons.json",
        "themes_cursors": "configs/themes_cursors.json",
    }
    counts = {}
    for key, path in files.items():
        try:
            with open(path) as f:
                data = json.load(f)
            for list_key in ("packages", "flatpaks", "themes"):
                if list_key in data:
                    counts[key] = len(data[list_key])
                    break
            else:
                counts[key] = 0
        except Exception:
            counts[key] = 0
    return counts


@bp.route('/api/status')
def status():
    now = time.time()
    if _status_cache["data"] and now - _status_cache["ts"] < STATUS_CACHE_TTL:
        cached = dict(_status_cache["data"])
        cached["task"] = dict(current_task)
        return jsonify(cached)
    data = {
        "checks": _check_system(),
        "packages": _get_package_counts(),
        "task": dict(current_task),
    }
    _status_cache["data"] = data
    _status_cache["ts"] = now
    return jsonify(data)


@bp.route('/api/system/info')
def system_info():
    try:
        return jsonify({"success": True, "info": gather_system_info()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/task/cancel', methods=['POST'])
def cancel_task():
    if cancel_current_task():
        update_task_status("Annule", False, 0)
        log_warn("Tache annulee par l'utilisateur.")
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Aucune tache en cours"}), 409


@bp.route('/api/logs/history')
def logs_history():
    try:
        log_file = Path("logs/fedoraforgekde.log")
        if not log_file.exists():
            return jsonify({"lines": []})
        lines = log_file.read_text(errors="replace").splitlines()
        return jsonify({"lines": lines[-300:]})
    except Exception:
        return jsonify({"lines": []})


@bp.route('/api/logs/stream')
def stream_logs():
    def generate():
        try:
            while True:
                try:
                    yield f"data: {log_queue.get(timeout=1)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            pass
    return Response(generate(), mimetype='text/event-stream')


@bp.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except queue.Empty:
            break
    return jsonify({"success": True})


@bp.route('/api/execute/<action>', methods=['POST'])
def execute_action(action):
    action_map = {
        "dnf_install": "dnf_install",
        "dnf_remove": "dnf_remove",
        "optional_install": "optional_install",
        "flatpak_install": "flatpak_install",
        "themes_install": "themes_install",
        "external_install": "external_install",
    }
    if action not in action_map:
        return jsonify({"success": False, "error": "Action inconnue"}), 400

    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        current_task.update(running=True, name=action, progress=0)

    def run():
        try:
            run_script(action_map[action])
        finally:
            update_task_status("", False, 100)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": f"Lancement de {action}"})


@bp.route('/api/execute/all', methods=['POST'])
def execute_all():
    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        current_task.update(running=True, name="Installation complete", progress=0)

    def run_all():
        # Pas de themes ici : on garde le theme par defaut (Breeze). L'installation
        # de themes reste opt-in via la section Themes de l'UI.
        tasks = [
            ("Mise a jour systeme", "system_update"),
            ("Paquets DNF", "dnf_install"),
            ("Paquets optionnels", "optional_install"),
            ("Paquets externes", "external_install"),
            ("Nettoyage", "dnf_remove"),
            ("Flatpaks", "flatpak_install"),
        ]
        critical = {"system_update", "dnf_install"}
        total = len(tasks)
        failed = []
        try:
            for idx, (name, task) in enumerate(tasks):
                update_task_status(name, True, int((idx / total) * 100))
                log_info(f"=== {name} ({idx+1}/{total}) ===")
                if task == "system_update":
                    log_info("Mise a jour systeme via dnf...")
                    result = system_update()
                    if not result.success:
                        failed.append(name)
                        log_error(f"Mise a jour systeme echouee (code {result.returncode})")
                else:
                    if not run_script(task):
                        failed.append(name)
                        if task in critical:
                            log_error(f"Tache critique echouee : {name}")
                            break
                time.sleep(0.5)
        except Exception as e:
            log_exc(f"Erreur inattendue : {e}")
            failed.append("erreur inattendue")
        finally:
            if failed:
                update_task_status("Termine avec erreurs", False, 100)
                log_warn(f"Erreurs : {', '.join(failed)}")
            else:
                update_task_status("Installation terminee", False, 100)
                log_success("Installation complete terminee")

    threading.Thread(target=run_all, daemon=True).start()
    return jsonify({"success": True, "message": "Installation complete lancee"})


@bp.route('/api/quit', methods=['POST'])
def quit_app():
    """Arrete le serveur Flask proprement."""
    log_info("Arret de FedoraForgeKDE demande par l'utilisateur.")

    def shutdown():
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=shutdown, daemon=True).start()
    return jsonify({"success": True, "message": "Arret en cours..."})


@bp.route('/api/optional/list')
def optional_list():
    """Liste les paquets optionnels avec leur statut d'installation."""
    try:
        config_file = Path("configs/optional_install.json")
        if not config_file.exists():
            return jsonify({"packages": []})
        with open(config_file, encoding="utf-8") as f:
            data = json.load(f)
        packages = data.get("packages", [])
        from utils import check_package_installed
        for pkg in packages:
            pkg["installed"] = check_package_installed(pkg["name"])
        return jsonify({"packages": packages})
    except Exception as e:
        return jsonify({"packages": [], "error": str(e)})


@bp.route('/api/theme/status')
def theme_status():
    try:
        config_file = Path("configs/theme_config_recommended.json")
        if not config_file.exists():
            return jsonify({"success": False, "error": "Fichier config introuvable"}), 404
        result = ThemeManager().check_recommended_config(config_file)
        return jsonify({"success": True, "config": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/theme/apply_recommended', methods=['POST'])
def apply_recommended_theme():
    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        current_task.update(running=True, name="Config themes recommandee", progress=0)

    def run():
        try:
            config_file = Path("configs/theme_config_recommended.json")
            if not config_file.exists():
                log_error("Fichier config introuvable")
                update_task_status("", False, 0)
                return
            log_info("Application de la config recommandee...")
            update_task_status("Config themes recommandee", True, 20)
            ok, messages = ThemeManager().apply_recommended_config(config_file, install_missing=True)
            for msg in messages:
                if msg.startswith("[OK]") or "installe" in msg.lower():
                    log_success(msg)
                elif msg.startswith("[ERROR]") or "echec" in msg.lower():
                    log_error(msg)
                elif msg.startswith("[WARN]"):
                    log_warn(msg)
                else:
                    log_info(msg)
                with task_lock:
                    prog = current_task.get("progress", 20)
                if prog < 90:
                    update_task_status("Config themes recommandee", True, prog + 10)
                    time.sleep(0.2)
            if ok:
                log_success("Config themes appliquee")
                update_task_status("Config terminee", False, 100)
            else:
                log_error("Config terminee avec erreurs")
                update_task_status("Erreurs detectees", False, 100)
        except Exception as e:
            log_exc(f"Erreur config themes : {e}")
            update_task_status("", False, 0)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": "Config themes lancee"})
