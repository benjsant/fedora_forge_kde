"""Routes /api/themes - catalogue et installation de themes depuis git."""
import json
import os
import threading
from pathlib import Path

from flask import Blueprint, jsonify, request

from routes.shared import (
    current_task,
    log_error,
    log_info,
    log_success,
    task_lock,
    update_task_status,
)
from utils.theme_manager import ThemeManager

bp = Blueprint("themes", __name__)

_CATALOG_FILES = {
    "gtk":     "configs/themes_gtk.json",
    "icon":    "configs/themes_icons.json",
    "cursor":  "configs/themes_cursors.json",
    "kvantum": "configs/themes_kvantum.json",
}


def _load_catalog():
    tm = ThemeManager()
    result = {}
    for theme_type, path in _CATALOG_FILES.items():
        try:
            data = json.loads(Path(path).read_text())
            entries = []
            for t in data.get("themes", []):
                installed, _ = tm.is_theme_installed(t.get("name_to_use", t["name"]), theme_type)
                entries.append({
                    "name":        t["name"],
                    "name_to_use": t.get("name_to_use", t["name"]),
                    "description": t.get("description", ""),
                    "has_url":     bool(t.get("url")),
                    "installed":   installed,
                })
            result[theme_type] = entries
        except Exception:
            result[theme_type] = []
    return result


@bp.route('/api/themes/catalog')
def themes_catalog():
    try:
        return jsonify({"success": True, "catalog": _load_catalog()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/themes/install', methods=['POST'])
def install_theme():
    data = request.get_json(silent=True) or {}
    theme_type = data.get("type")
    theme_name = data.get("name")
    system     = bool(data.get("system", True))

    if theme_type not in _CATALOG_FILES or not theme_name:
        return jsonify({"success": False, "error": "type et name requis (gtk|icon|cursor|kvantum)"}), 400

    try:
        raw = json.loads(Path(_CATALOG_FILES[theme_type]).read_text())
    except Exception:
        return jsonify({"success": False, "error": "Catalogue introuvable"}), 500

    entry = next((t for t in raw.get("themes", []) if t["name"] == theme_name), None)
    if entry is None:
        return jsonify({"success": False, "error": f"Theme '{theme_name}' introuvable"}), 404
    if not entry.get("url"):
        return jsonify({"success": False, "error": "Ce theme n'a pas d'URL git (deja inclus systeme)"}), 400

    cmd_key = "cmd_root" if system else "cmd_user"
    install_cmd = entry.get(cmd_key, "")
    if not install_cmd:
        install_cmd = entry.get("cmd_user", "")

    home = os.path.expanduser("~")
    install_cmd = install_cmd.replace("~", home)

    if system and not install_cmd.startswith("sudo"):
        install_cmd = "sudo " + install_cmd

    if not system:
        if theme_type == "gtk":
            os.makedirs(f"{home}/.themes", exist_ok=True)
        elif theme_type == "kvantum":
            os.makedirs(f"{home}/.config/Kvantum", exist_ok=True)
        else:
            os.makedirs(f"{home}/.icons", exist_ok=True)
            os.makedirs(f"{home}/.local/share/icons", exist_ok=True)

    # Verifier sassc pour themes GTK
    if theme_type == "gtk":
        import subprocess as _sp
        if _sp.run(["which", "sassc"], capture_output=True).returncode != 0:
            return jsonify({
                "success": False,
                "error": "sassc manquant — installez-le d'abord : sudo dnf install sassc"
            }), 400

    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        dest = "/usr/share" if system else "~/"
        current_task.update(running=True, name=f"Theme : {theme_name} -> {dest}", progress=0)

    def run():
        try:
            dest_label = "/usr/share" if system else "~/.themes / ~/.icons"
            log_info(f"Installation de {theme_name} vers {dest_label}...")
            update_task_status(f"Theme : {theme_name}", True, 10)
            tm = ThemeManager()
            success, msg = tm.install_theme_from_git(
                entry.get("name_to_use", theme_name),
                entry["url"],
                install_cmd,
                theme_type,
            )
            if success:
                log_success(msg)
                update_task_status(f"Theme installe : {theme_name}", False, 100)
            else:
                log_error(f"Echec : {msg}")
                update_task_status(f"Echec theme : {theme_name}", False, 0)
        except Exception as e:
            log_error(f"Erreur inattendue theme : {e}")
            update_task_status("Erreur theme", False, 0)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": f"Installation de {theme_name} lancee"})
