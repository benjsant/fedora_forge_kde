"""Routes /api/kde - parametres bureau via kwriteconfig6/kreadconfig6."""
import os
import subprocess
import threading

from flask import Blueprint, jsonify, request

from routes.shared import (
    current_task,
    log_error,
    log_info,
    log_success,
    log_warn,
    task_lock,
    update_task_status,
)
from utils.kde_backup import BackupError, create_backup, delete_backup, list_backups, restore_backup
from utils.theme_manager import ThemeManager

bp = Blueprint("kde_settings", __name__)

# Chaque cle de formulaire -> (fichier_config, groupe, cle)
# Les paths "~/..." sont expanded ; sinon kwriteconfig6 cherche dans XDG_CONFIG_HOME.
_SETTINGS_MAP = {
    "gtk_theme": ("kdeglobals", "General", "Name"),
    "icon_theme": ("kdeglobals", "Icons", "Theme"),
    "cursor_theme": ("kcminputrc", "Mouse", "cursorTheme"),
    "cursor_size": ("kcminputrc", "Mouse", "cursorSize"),
    "plasma_theme": ("plasmarc", "Theme", "name"),
    "color_scheme": ("kdeglobals", "General", "ColorScheme"),
    "font_name": ("kdeglobals", "General", "font"),
    "fixed_font": ("kdeglobals", "General", "fixed"),
    "titlebar_font": ("kdeglobals", "WM", "activeFont"),
    "num_desktops": ("kwinrc", "Desktops", "Number"),
    "night_light_enabled": ("kwinrc", "NightColor", "Active"),
    "night_light_temp": ("kwinrc", "NightColor", "NightTemperature"),
    "night_light_mode": ("kwinrc", "NightColor", "Mode"),
    "single_click": ("kdeglobals", "KDE", "SingleClick"),
    "animate_minimize": ("kwinrc", "Plugins", "minimizeanimationEnabled"),
    "window_decorations": ("kwinrc", "org.kde.kdecoration2", "theme"),
    "button_layout": ("kwinrc", "org.kde.kdecoration2", "ButtonsOnLeft"),
    "button_layout_right": ("kwinrc", "org.kde.kdecoration2", "ButtonsOnRight"),
    "screen_locker_timeout": ("kscreenlockerrc", "Daemon", "Timeout"),
    "screen_locker_autolock": ("kscreenlockerrc", "Daemon", "Autolock"),
    # Kvantum (moteur de themes Qt) — installe via paquet `kvantum`
    "kvantum_theme": ("~/.config/Kvantum/kvantum.kvconfig", "General", "theme"),
    # VRR (Variable Refresh Rate) / DRM Leasing — gaming/VR sous Wayland (Plasma 6+)
    "vrr_policy": ("kwinrc", "Wayland", "VrrPolicy"),  # 0=Never, 1=Auto, 2=Always
    "drm_lease": ("kwinrc", "Wayland", "WaylandDRMLease"),
}


def _expand(config_file):
    return os.path.expanduser(config_file) if config_file.startswith("~/") else config_file


def _kde_get(config_file, group, key):
    """Lit une valeur KDE via kreadconfig6."""
    try:
        r = subprocess.run(
            ["kreadconfig6", "--file", _expand(config_file), "--group", group, "--key", key],
            capture_output=True, text=True, timeout=3
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _kde_set(config_file, group, key, value):
    """Ecrit une valeur KDE via kwriteconfig6."""
    try:
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        elif isinstance(value, str) and value.lower() in ('true', 'false'):
            value = value.lower()
        # Pour les paths user (~/...), creer le dossier parent si absent
        target = _expand(config_file)
        if target.startswith(os.path.expanduser("~/")):
            os.makedirs(os.path.dirname(target), exist_ok=True)
        r = subprocess.run(
            ["kwriteconfig6", "--file", target, "--group", group, "--key", key, str(value)],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0, r.stderr.strip()
    except Exception as e:
        return False, str(e)


def _validate_settings(settings):
    if "num_desktops" in settings:
        try:
            n = int(settings["num_desktops"])
            if not 1 <= n <= 20:
                return None, "num_desktops doit etre entre 1 et 20"
            settings["num_desktops"] = str(n)
        except (ValueError, TypeError):
            return None, "num_desktops invalide"

    if "night_light_temp" in settings and settings["night_light_temp"]:
        try:
            t = int(settings["night_light_temp"])
            if not 1700 <= t <= 6500:
                return None, "night_light_temp doit etre entre 1700 et 6500"
            settings["night_light_temp"] = str(t)
        except (ValueError, TypeError):
            return None, "night_light_temp invalide"

    if "cursor_size" in settings and settings["cursor_size"]:
        try:
            s = int(settings["cursor_size"])
            if s not in (24, 32, 36, 48, 64):
                return None, "cursor_size invalide (24, 32, 36, 48 ou 64)"
            settings["cursor_size"] = str(s)
        except (ValueError, TypeError):
            return None, "cursor_size invalide"

    if "vrr_policy" in settings and settings["vrr_policy"] != "":
        try:
            v = int(settings["vrr_policy"])
            if v not in (0, 1, 2):
                return None, "vrr_policy invalide (0=Never, 1=Auto, 2=Always)"
            settings["vrr_policy"] = str(v)
        except (ValueError, TypeError):
            return None, "vrr_policy invalide"

    return settings, None


def _notify_kde_reload():
    """Notifie KDE de recharger la config."""
    subprocess.run(
        ["dbus-send", "--session", "--type=signal",
         "/KGlobalSettings", "org.kde.KGlobalSettings.notifyChange",
         "int32:0", "int32:0"],
        capture_output=True, timeout=3
    )


@bp.route('/api/kde/options')
def kde_options():
    try:
        tm = ThemeManager()
        current = {}
        for form_key, (config_file, group, key) in _SETTINGS_MAP.items():
            current[form_key] = _kde_get(config_file, group, key)

        return jsonify({
            "success": True,
            "themes": {
                "gtk":     tm.list_available_themes("gtk"),
                "icon":    tm.list_available_themes("icon"),
                "cursor":  tm.list_available_themes("cursor"),
                "plasma":  tm.list_available_themes("plasma"),
                "kvantum": tm.list_available_themes("kvantum"),
            },
            "current": current,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/kde/apply', methods=['POST'])
def apply_settings():
    data = request.get_json(silent=True) or {}
    settings, err = _validate_settings(data.get("settings", {}))
    if err:
        return jsonify({"success": False, "error": err}), 400

    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        current_task.update(running=True, name="Parametres bureau", progress=0)

    def run():
        applied, errors = 0, []
        try:
            entries = []
            for form_key, (config_file, group, key) in _SETTINGS_MAP.items():
                if form_key in settings and settings[form_key] != "":
                    entries.append((config_file, group, key, settings[form_key]))

            total = max(len(entries), 1)
            for i, (config_file, group, key, value) in enumerate(entries):
                ok, err_msg = _kde_set(config_file, group, key, value)
                update_task_status("Parametres bureau", True, 10 + int((i / total) * 85))
                if ok:
                    log_info(f"KDE: {config_file}/{group}/{key} = {value}")
                    applied += 1
                else:
                    log_warn(f"Echec KDE {key}: {err_msg}")
                    errors.append(f"{key}: {err_msg}")

            _notify_kde_reload()

            if errors:
                log_warn(f"{applied} parametres appliques, {len(errors)} erreur(s)")
                update_task_status("Termine avec avertissements", False, 100)
            else:
                log_success(f"{applied} parametres appliques")
                update_task_status("Parametres appliques", False, 100)

        except Exception as e:
            log_error(f"Erreur application parametres : {e}")
            update_task_status("Erreur parametres", False, 0)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": "Application des parametres lancee"})


@bp.route('/api/kde/backups')
def kde_backups_list():
    try:
        return jsonify({"success": True, "backups": list_backups()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/kde/backups/create', methods=['POST'])
def kde_backups_create():
    data = request.get_json(silent=True) or {}
    label = data.get("label", "")
    try:
        info = create_backup(label=label)
        log_success(f"Sauvegarde KDE creee : {info['filename']} ({info['files_count']} fichiers)")
        return jsonify({"success": True, "backup": info})
    except BackupError as e:
        log_error(f"Echec sauvegarde KDE : {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/kde/backups/restore', methods=['POST'])
def kde_backups_restore():
    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "")
    if not filename:
        return jsonify({"success": False, "error": "filename requis"}), 400
    try:
        result = restore_backup(filename)
        _notify_kde_reload()
        log_success(f"Sauvegarde restauree : {filename} ({result['count']} fichiers)")
        if result["skipped"]:
            log_warn(f"Membres ignores (hors whitelist) : {len(result['skipped'])}")
        return jsonify({"success": True, **result})
    except BackupError as e:
        log_error(f"Echec restauration : {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@bp.route('/api/kde/backups/delete', methods=['POST'])
def kde_backups_delete():
    data = request.get_json(silent=True) or {}
    filename = data.get("filename", "")
    if not filename:
        return jsonify({"success": False, "error": "filename requis"}), 400
    try:
        delete_backup(filename)
        log_info(f"Sauvegarde supprimee : {filename}")
        return jsonify({"success": True})
    except BackupError as e:
        return jsonify({"success": False, "error": str(e)}), 404


@bp.route('/api/kde/dark-mode', methods=['POST'])
def toggle_dark_mode():
    """Bascule mode sombre/clair via KDE color scheme."""
    data = request.get_json(silent=True) or {}
    dark = bool(data.get("dark", True))

    current_scheme = _kde_get("kdeglobals", "General", "ColorScheme")

    if dark:
        # Essayer de deriver le scheme sombre
        if "Light" in current_scheme:
            new_scheme = current_scheme.replace("Light", "Dark")
        elif "Dark" not in current_scheme:
            new_scheme = "BreezeDark"
        else:
            new_scheme = current_scheme
    else:
        if "Dark" in current_scheme:
            new_scheme = current_scheme.replace("Dark", "Light")
            if new_scheme == current_scheme:
                new_scheme = current_scheme.replace("Dark", "")
        else:
            new_scheme = "BreezeLight"

    # Appliquer via plasma-apply-colorscheme si disponible
    result = subprocess.run(
        ["plasma-apply-colorscheme", new_scheme],
        capture_output=True, text=True, timeout=10
    )

    if result.returncode == 0:
        mode = "sombre" if dark else "clair"
        log_success(f"Mode {mode} applique (scheme: {new_scheme})")
        return jsonify({"success": True, "mode": mode, "color_scheme": new_scheme})
    else:
        # Fallback: ecrire directement
        _kde_set("kdeglobals", "General", "ColorScheme", new_scheme)
        _notify_kde_reload()
        mode = "sombre" if dark else "clair"
        log_info(f"Mode {mode} applique via kwriteconfig6 (scheme: {new_scheme})")
        return jsonify({"success": True, "mode": mode, "color_scheme": new_scheme})
