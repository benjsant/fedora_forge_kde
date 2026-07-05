"""Routes /api/tweaks/* — quick fixes Plasma, services systemd, audio."""
from flask import Blueprint, jsonify, request

from routes.shared import log_error, log_info, log_success, log_warn
from utils.admin_menu import disable as admin_menu_disable
from utils.admin_menu import enable as admin_menu_enable
from utils.admin_menu import status as admin_menu_status
from utils.audio_tweaks import (
    ALLOWED_RATES,
    bt_premium_codecs_enabled,
    get_configured_sample_rate,
    get_current_sample_rate,
    restart_pipewire,
    set_bt_premium_codecs,
    set_sample_rate,
)
from utils.dolphin_tweaks import set_home_on_startup as dolphin_set_home
from utils.dolphin_tweaks import status as dolphin_status
from utils.panel_tweaks import set_floating as panel_set_floating
from utils.panel_tweaks import status as panel_status
from utils.plasma_tweaks import clear_caches, reset_plasmashell
from utils.sched_ext import disable as scx_disable
from utils.sched_ext import enable as scx_enable
from utils.sched_ext import status as scx_status
from utils.services_manager import ALLOWED_SERVICES, list_services, toggle_service
from utils.sysctl_tweaks import apply as sysctl_apply
from utils.sysctl_tweaks import remove as sysctl_remove
from utils.sysctl_tweaks import status as sysctl_status
from utils.zram_tweaks import apply as zram_apply
from utils.zram_tweaks import remove as zram_remove
from utils.zram_tweaks import status as zram_status

bp = Blueprint("tweaks", __name__)


# --------- Plasma quick fixes ---------

@bp.route('/api/tweaks/plasma/reset', methods=['POST'])
def plasma_reset():
    try:
        ok = reset_plasmashell()
        if ok:
            log_success("Plasmashell reinitialise")
            return jsonify({"success": True})
        log_error("kstart6/plasmashell introuvable")
        return jsonify({"success": False, "error": "kstart6 introuvable"}), 500
    except Exception as e:
        log_error(f"Echec reset plasma : {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/tweaks/cache/clear', methods=['POST'])
def cache_clear():
    try:
        result = clear_caches()
        mb = result["freed_bytes"] / (1024 * 1024)
        log_success(f"Caches vides : {mb:.1f} Mo ({len(result['cleared'])} entrees)")
        return jsonify({"success": True, **result})
    except Exception as e:
        log_error(f"Echec vidage caches : {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# --------- Services systemd ---------

@bp.route('/api/tweaks/services')
def services_list():
    return jsonify({"success": True, "services": list_services()})


@bp.route('/api/tweaks/services/toggle', methods=['POST'])
def services_toggle():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    enable = bool(data.get("enable", False))

    if name not in ALLOWED_SERVICES:
        return jsonify({"success": False, "error": "Service non autorise"}), 400

    ok, err = toggle_service(name, enable)
    if ok:
        log_success(f"Service {name} {'active' if enable else 'desactive'}")
        return jsonify({"success": True})
    log_error(f"Echec toggle {name} : {err}")
    return jsonify({"success": False, "error": err}), 500


# --------- Audio (PipeWire + Bluetooth) ---------

@bp.route('/api/tweaks/audio')
def audio_status():
    return jsonify({
        "success": True,
        "current_rate": get_current_sample_rate(),
        "configured_rate": get_configured_sample_rate(),
        "allowed_rates": list(ALLOWED_RATES),
        "bt_premium": bt_premium_codecs_enabled(),
    })


@bp.route('/api/tweaks/audio/rate', methods=['POST'])
def audio_set_rate():
    data = request.get_json(silent=True) or {}
    try:
        rate = int(data.get("rate", 0))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "rate invalide"}), 400

    if rate not in ALLOWED_RATES:
        return jsonify({"success": False,
                        "error": f"rate doit etre dans {list(ALLOWED_RATES)}"}), 400

    try:
        set_sample_rate(rate)
    except (ValueError, OSError) as e:
        log_error(f"Echec ecriture sample rate : {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    ok, err = restart_pipewire()
    if ok:
        log_success(f"PipeWire sample rate -> {rate} Hz")
        return jsonify({"success": True, "rate": rate})
    log_warn(f"Sample rate ecrit mais redemarrage PipeWire echoue : {err}")
    return jsonify({"success": True, "rate": rate,
                    "warning": "Config OK mais redemarrage PipeWire requis manuellement"})


@bp.route('/api/tweaks/audio/bt-codecs', methods=['POST'])
def audio_bt_codecs():
    data = request.get_json(silent=True) or {}
    enable = bool(data.get("enable", False))
    try:
        set_bt_premium_codecs(enable)
    except OSError as e:
        log_error(f"Echec ecriture config BT : {e}")
        return jsonify({"success": False, "error": str(e)}), 500

    ok, err = restart_pipewire()
    log_info(f"Codecs BT premium {'actives' if enable else 'desactives'}")
    if ok:
        return jsonify({"success": True, "enabled": enable})
    return jsonify({"success": True, "enabled": enable,
                    "warning": "Config OK mais redemarrage WirePlumber requis"})


# --------- Sysctls gaming ---------

@bp.route('/api/tweaks/sysctls')
def sysctls_status():
    return jsonify({"success": True, **sysctl_status()})


@bp.route('/api/tweaks/sysctls/toggle', methods=['POST'])
def sysctls_toggle():
    data = request.get_json(silent=True) or {}
    enable = bool(data.get("enable", False))
    ok, msg = sysctl_apply() if enable else sysctl_remove()
    if not ok:
        log_error(f"Sysctls gaming : {msg}")
        return jsonify({"success": False, "error": msg}), 500
    log_success(msg)
    return jsonify({"success": True, "applied": enable, "message": msg, **sysctl_status()})


# --------- Scheduler sched-ext (gaming, sans kernel custom) ---------

@bp.route('/api/tweaks/scheduler')
def scheduler_status():
    return jsonify({"success": True, **scx_status()})


@bp.route('/api/tweaks/scheduler/toggle', methods=['POST'])
def scheduler_toggle():
    data = request.get_json(silent=True) or {}
    enable = bool(data.get("enable", False))
    scheduler = data.get("scheduler") or None
    if enable:
        ok, msg = scx_enable(scheduler) if scheduler else scx_enable()
    else:
        ok, msg = scx_disable()
    if not ok:
        log_error(f"Scheduler sched-ext : {msg}")
        return jsonify({"success": False, "error": msg}), 400
    log_success(msg)
    return jsonify({"success": True, "active": enable, "message": msg, **scx_status()})


# --------- Menu Dolphin "Ouvrir en tant qu'administrateur" (kio-admin) ---------

@bp.route('/api/tweaks/admin-menu')
def admin_menu():
    return jsonify({"success": True, **admin_menu_status()})


@bp.route('/api/tweaks/admin-menu/toggle', methods=['POST'])
def admin_menu_toggle():
    data = request.get_json(silent=True) or {}
    enable = bool(data.get("enable", False))
    ok, msg = admin_menu_enable() if enable else admin_menu_disable()
    if not ok:
        log_error(f"Menu administrateur : {msg}")
        return jsonify({"success": False, "error": msg}), 500
    log_success(msg)
    return jsonify({"success": True, "message": msg, **admin_menu_status()})


# --------- Barre des taches : panneau flottant / fixe ---------

@bp.route('/api/tweaks/panel')
def panel():
    return jsonify({"success": True, **panel_status()})


@bp.route('/api/tweaks/panel/floating', methods=['POST'])
def panel_floating():
    data = request.get_json(silent=True) or {}
    floating = bool(data.get("floating", False))
    ok, msg = panel_set_floating(floating)
    if not ok:
        log_error(f"Barre des taches : {msg}")
        return jsonify({"success": False, "error": msg}), 500
    log_success(msg)
    return jsonify({"success": True, "floating": floating, "message": msg, **panel_status()})


# --------- Dolphin : dossier personnel au demarrage ---------

@bp.route('/api/tweaks/dolphin')
def dolphin():
    return jsonify({"success": True, **dolphin_status()})


@bp.route('/api/tweaks/dolphin/home-startup', methods=['POST'])
def dolphin_home_startup():
    data = request.get_json(silent=True) or {}
    enable = bool(data.get("enable", False))
    ok, msg = dolphin_set_home(enable)
    if not ok:
        log_error(f"Dolphin : {msg}")
        return jsonify({"success": False, "error": msg}), 500
    log_success(msg)
    return jsonify({"success": True, "enabled": enable, "message": msg, **dolphin_status()})


# --------- Memoire : zram facon Nobara (zstd + swappiness) ---------

@bp.route('/api/tweaks/zram')
def zram():
    return jsonify({"success": True, **zram_status()})


@bp.route('/api/tweaks/zram/toggle', methods=['POST'])
def zram_toggle():
    data = request.get_json(silent=True) or {}
    enable = bool(data.get("enable", False))
    ok, msg = zram_apply() if enable else zram_remove()
    if not ok:
        log_error(f"Tweak zram : {msg}")
        return jsonify({"success": False, "error": msg}), 500
    log_success(msg)
    return jsonify({"success": True, "applied": enable, "message": msg, **zram_status()})
