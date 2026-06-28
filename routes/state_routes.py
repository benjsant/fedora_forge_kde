"""Routes /api/state (historique + rollback)."""
import threading

from flask import Blueprint, jsonify

from routes.shared import current_task, log_error, log_success, log_warn, task_lock, update_task_status
from utils.state_manager import StateError, get_state_manager

bp = Blueprint("state", __name__)


@bp.route('/api/state')
def get_state():
    try:
        state = get_state_manager()
        history = [{
            "id": e.id, "timestamp": e.timestamp, "action": e.action,
            "target": e.target, "success": e.success,
            "can_rollback": e.can_rollback(), "metadata": e.metadata,
        } for e in state.get_history()]
        return jsonify({"success": True, "summary": state.summary(), "history": history})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/state/rollback/last', methods=['POST'])
def rollback_last():
    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        current_task.update(running=True, name="Rollback", progress=0)

    def run():
        try:
            entry = get_state_manager().rollback_last()
            if entry:
                log_success(f"Rollback : {entry.action} -> {entry.target}")
                update_task_status("Rollback termine", False, 100)
            else:
                log_warn("Rien a annuler.")
                update_task_status("", False, 0)
        except StateError as e:
            log_error(f"Rollback impossible : {e}")
            update_task_status("Rollback echoue", False, 0)
        except Exception as e:
            log_error(f"Erreur : {e}")
            update_task_status("", False, 0)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": "Rollback lance"})


@bp.route('/api/state/rollback/all', methods=['POST'])
def rollback_all():
    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        current_task.update(running=True, name="Rollback total", progress=0)

    def run():
        try:
            rolled = get_state_manager().rollback_all()
            log_success(f"{len(rolled)} action(s) annulee(s)")
            update_task_status(f"Rollback termine ({len(rolled)})", False, 100)
        except Exception as e:
            log_error(f"Erreur rollback : {e}")
            update_task_status("Rollback echoue", False, 0)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": "Rollback total lance"})


@bp.route('/api/state/clear', methods=['DELETE'])
def clear_state():
    try:
        get_state_manager().clear()
        log_warn("Historique efface (sans rollback).")
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
