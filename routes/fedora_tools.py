"""Routes /api/tools - detection et lancement des outils systeme Fedora KDE.

Remplace l'ancien blueprint nobara_tools (qui lancait des binaires nobara-*
inexistants sur Fedora). On expose ici les outils GUI standard de Fedora KDE
Spin, lances dans la session de l'utilisateur (pas en root). Pour les drivers,
codecs et depots, ce sont les wizards Fedora inline (/api/fedora/*) qui font foi.
"""
import os
import shutil
import subprocess

from flask import Blueprint, jsonify

from routes.shared import log_error, log_info, log_warn

bp = Blueprint("fedora_tools", __name__)

# Outils GUI standard de Fedora KDE Spin, whitelistes. Pas de PATH arbitraire :
# uniquement ces commandes, lancees telles quelles dans la session utilisateur.
_TOOLS = [
    {
        "id": "discover",
        "cmd": "plasma-discover",
        "name": "Logiciels (Discover)",
        "description": "Centre logiciel KDE : applications, Flatpaks, mises a jour",
        "icon": "🛍️",
    },
    {
        "id": "systemsettings",
        "cmd": "systemsettings",
        "name": "Parametres systeme",
        "description": "Configuration KDE Plasma (apparence, peripheriques, comptes)",
        "icon": "⚙️",
    },
    {
        "id": "systemmonitor",
        "cmd": "plasma-systemmonitor",
        "name": "Moniteur systeme",
        "description": "Surveillance CPU/RAM/reseau et gestion des processus",
        "icon": "📊",
    },
    {
        "id": "infocenter",
        "cmd": "kinfocenter",
        "name": "Informations systeme",
        "description": "Materiel detecte, pilotes, modules noyau, OpenGL/Vulkan",
        "icon": "ℹ️",
    },
    {
        "id": "partitionmanager",
        "cmd": "partitionmanager",
        "name": "Gestion des partitions",
        "description": "KDE Partition Manager (formatage, redimensionnement)",
        "icon": "💾",
    },
]


def _tool_available(cmd):
    return shutil.which(cmd) is not None


@bp.route('/api/tools')
def list_tools():
    """Liste les outils systeme avec leur statut de disponibilite."""
    result = [{**tool, "available": _tool_available(tool["cmd"])} for tool in _TOOLS]
    return jsonify({"success": True, "tools": result})


@bp.route('/api/tools/launch/<tool_id>', methods=['POST'])
def launch_tool(tool_id):
    """Lance un outil dans la session de l'utilisateur (non-bloquant)."""
    tool = next((t for t in _TOOLS if t["id"] == tool_id), None)
    if tool is None:
        return jsonify({"success": False, "error": f"Outil inconnu : {tool_id}"}), 404

    if not _tool_available(tool["cmd"]):
        log_warn(f"Outil non installe : {tool['cmd']}")
        return jsonify({
            "success": False,
            "error": f"{tool['cmd']} non installe. Installez-le : sudo dnf install {tool['cmd']}",
        }), 404

    try:
        # start_new_session=True detache le process du serveur Flask ; I/O vers
        # /dev/null pour ne pas polluer les logs.
        subprocess.Popen(
            [tool["cmd"]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
        log_info(f"Lance : {tool['cmd']}")
        return jsonify({"success": True, "message": f"{tool['name']} lance"})
    except Exception as e:
        log_error(f"Echec lancement {tool['cmd']} : {e}")
        return jsonify({"success": False, "error": str(e)}), 500
