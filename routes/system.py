"""Routes /api/system - gestion systeme directe (pare-feu firewalld, etc.)."""
import subprocess

from flask import Blueprint, jsonify

bp = Blueprint("system", __name__)


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
