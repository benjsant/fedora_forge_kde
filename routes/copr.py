"""Route /api/copr : catalogue COPR experimental (depots tiers, opt-in).

Securite :
- Whitelist stricte : seuls les COPR presents dans configs/copr.json peuvent etre
  actives. Aucun id arbitraire venu du client n'est accepte.
- Activation conditionnee a une confirmation explicite (`confirmed: true`) :
  l'utilisateur reconnait activer un depot tiers non audite par Fedora, a ses
  risques (cf. experimental_warning du catalogue).

Rollback : l'activation du depot et chaque paquet installe sont enregistres
dans le state manager (l'annulation retire les paquets puis desactive le depot,
puisque rollback_all rejoue en ordre inverse).
"""
import json

from flask import Blueprint, jsonify, request

from routes.fedora_wizards import _stream_sudo
from routes.shared import (
    log_error,
    log_info,
    log_success,
    log_warn,
    start_background_task,
)
from schemas import CoprCatalog
from utils.paths import PROJECT_ROOT
from utils.state_manager import (
    ACTION_COPR_ENABLE,
    ACTION_DNF_INSTALL,
    get_state_manager,
)

bp = Blueprint("copr", __name__)

_CATALOG = PROJECT_ROOT / "configs" / "copr.json"
_COPR_TIMEOUT = 900


def _load_catalog():
    """Charge + valide le catalogue COPR. None si illisible/invalide."""
    try:
        data = json.loads(_CATALOG.read_text(encoding="utf-8"))
        return CoprCatalog(**data)
    except Exception:
        return None


@bp.route('/api/copr')
def copr_list():
    """Catalogue COPR + avertissement experimental."""
    cat = _load_catalog()
    if cat is None:
        return jsonify({"success": False, "error": "Catalogue COPR illisible"}), 500
    return jsonify({
        "success": True,
        "warning": cat.experimental_warning,
        "copr": [c.model_dump() for c in cat.copr],
    })


def _record_copr_enable(entry):
    get_state_manager().record(
        ACTION_COPR_ENABLE, entry.id, True,
        rollback_cmd=["sudo", "dnf", "-y", "copr", "disable", entry.id],
        metadata={"packages": list(entry.packages)},
    )


def _record_copr_packages(entry):
    for pkg in entry.packages:
        get_state_manager().record(
            ACTION_DNF_INSTALL, pkg, True,
            rollback_cmd=["sudo", "dnf", "remove", "-y", pkg],
            metadata={"copr": entry.id},
        )


@bp.route('/api/copr/enable', methods=['POST'])
def copr_enable():
    """Active un COPR whiteliste (+ installe ses paquets). Confirmation requise.

    Le travail (dnf copr enable + dnf install) part en tache de fond : la
    reponse revient tout de suite, la progression passe par les logs SSE et la
    barre de tache, comme les wizards Fedora."""
    data = request.get_json(silent=True) or {}
    copr_id = (data.get("id") or "").strip()
    confirmed = bool(data.get("confirmed", False))
    do_install = bool(data.get("install", True))

    if not confirmed:
        return jsonify({"success": False,
                        "error": "Confirmation requise : activation d'un depot tiers a vos risques."}), 400

    cat = _load_catalog()
    if cat is None:
        return jsonify({"success": False, "error": "Catalogue COPR illisible"}), 500

    # Whitelist stricte : l'id doit etre dans le catalogue.
    entry = next((c for c in cat.copr if c.id == copr_id), None)
    if entry is None:
        return jsonify({"success": False, "error": "COPR non autorise (hors catalogue)"}), 400

    log_warn(f"[COPR] Activation d'un depot TIERS (non Fedora) : {entry.id}")
    if entry.danger:
        log_warn(f"[COPR] Risque : {entry.danger}")

    def worker():
        if _stream_sudo(["dnf", "copr", "enable", "-y", entry.id],
                        timeout=_COPR_TIMEOUT) != 0:
            log_error(f"[COPR] Echec activation {entry.id}")
            return False
        _record_copr_enable(entry)

        if do_install and entry.packages:
            log_info(f"[COPR] Installation : {', '.join(entry.packages)}")
            if _stream_sudo(["dnf", "install", "-y", *entry.packages],
                            timeout=_COPR_TIMEOUT) != 0:
                log_error(f"[COPR] Echec installation des paquets de {entry.id}")
                return False
            _record_copr_packages(entry)

        log_success(f"[COPR] {entry.id} active"
                    + (f" + {', '.join(entry.packages)} installe(s)" if do_install else ""))
        return True

    if not start_background_task(f"Activation COPR {entry.id}", worker):
        return jsonify({"success": False, "error": "Tache en cours"}), 409
    return jsonify({"success": True, "started": True, "id": entry.id,
                    "message": f"Activation COPR {entry.id} lancee (suivez les logs)"})
