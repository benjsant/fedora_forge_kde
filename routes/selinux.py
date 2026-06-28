"""Routes /api/selinux/* - assistant SELinux (diagnostic + booleans whitelistes).

Aucune route ne desactive SELinux. On expose un diagnostic AVC en lecture seule
et la bascule de booleans cibles, conformement a la ligne du projet (garder
l'enforcing, contrairement a Nobara qui passe sur AppArmor).
"""
from flask import Blueprint, jsonify, request

from routes.shared import log_error, log_info, log_success
from utils.selinux_manager import set_boolean, status

bp = Blueprint("selinux", __name__)


@bp.route('/api/selinux/status')
def selinux_status():
    """Mode SELinux, etat des booleans whitelistes, denials AVC recents."""
    return jsonify({"success": True, **status()})


@bp.route('/api/selinux/boolean', methods=['POST'])
def selinux_boolean():
    """Bascule un boolean SELinux whiteliste (persistant). Jamais setenforce."""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "")
    enable = bool(data.get("enable", False))
    ok, msg = set_boolean(name, enable)
    if not ok:
        log_error(f"SELinux boolean : {msg}")
        return jsonify({"success": False, "error": msg}), 400
    log_success(f"SELinux : {msg}")
    log_info("Pensez a verifier que l'app concernee fonctionne toujours apres ce changement.")
    return jsonify({"success": True, "message": msg, **status()})
