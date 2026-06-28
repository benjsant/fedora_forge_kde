#!/usr/bin/env python3
"""Suivi persistant des actions FedoraForgeKDE avec rollback."""

import json
import logging
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

_logger = logging.getLogger("fedoraforgekde.state")

# Types d'actions supportes
ACTION_DNF_INSTALL = "dnf_install"
ACTION_DNF_REMOVE = "dnf_remove"
ACTION_FLATPAK_INSTALL = "flatpak_install"
ACTION_EXTERNAL_INSTALL = "external_install"

VALID_ACTIONS = {
    ACTION_DNF_INSTALL, ACTION_DNF_REMOVE,
    ACTION_FLATPAK_INSTALL, ACTION_EXTERNAL_INSTALL,
}

DEFAULT_STATE_FILE = Path(__file__).parent.parent / "data" / "state.json"

# Cap sur le nombre d'entrees gardees. Les plus anciennes sont droppees quand
# on depasse. Evite que state.json grossisse a l'infini sur un usage long
# (chaque install ajoute 1 entree, rollback aussi). 500 = ~plusieurs annees
# d'usage normal couverts pour le rollback recent.
MAX_ENTRIES = 500


@dataclass
class StateEntry:
    """Une action enregistree."""
    id: int
    timestamp: str
    action: str
    target: str
    success: bool
    rollback_cmd: list
    metadata: dict

    def can_rollback(self):
        return bool(self.rollback_cmd)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            action=data["action"],
            target=data["target"],
            success=data["success"],
            rollback_cmd=data.get("rollback_cmd", []),
            metadata=data.get("metadata", {}),
        )


class StateError(Exception):
    pass


class StateManager:
    """Gestionnaire d'etat persistant avec rollback. Thread-safe."""

    def __init__(self, state_file=None):
        self.state_file = state_file or DEFAULT_STATE_FILE
        self._lock = threading.Lock()
        self._entries = []
        self._next_id = 1
        self._load()

    def record(self, action, target, success, rollback_cmd=None, metadata=None):
        """Enregistre une action."""
        if action not in VALID_ACTIONS:
            raise StateError(f"Action inconnue : '{action}'. Valides : {VALID_ACTIONS}")

        entry = StateEntry(
            id=self._next_id,
            timestamp=datetime.now().isoformat(),
            action=action,
            target=target,
            success=success,
            rollback_cmd=rollback_cmd or [],
            metadata=metadata or {},
        )

        with self._lock:
            self._entries.append(entry)
            self._next_id += 1
            # Cap : drop les plus anciennes entrees si on depasse MAX_ENTRIES.
            # Le rollback des entrees recentes reste possible, les vieilles
            # actions ne sont de toute facon plus pertinentes.
            if len(self._entries) > MAX_ENTRIES:
                self._entries = self._entries[-MAX_ENTRIES:]
            self._save()
        return entry

    def get_history(self):
        with self._lock:
            return list(self._entries)

    def get_successful(self):
        with self._lock:
            return [e for e in self._entries if e.success]

    def get_installed_targets(self):
        """Noms des paquets installes avec succes."""
        install_actions = {ACTION_DNF_INSTALL, ACTION_FLATPAK_INSTALL, ACTION_EXTERNAL_INSTALL}
        with self._lock:
            return [e.target for e in self._entries
                    if e.action in install_actions and e.success]

    def rollback_last(self):
        """Annule la derniere action (si rollback dispo)."""
        with self._lock:
            if not self._entries:
                return None

            last = self._entries[-1]
            if not last.can_rollback():
                raise StateError(
                    f"Pas de rollback auto pour '{last.target}' "
                    f"(action: {last.action}). Intervention manuelle requise."
                )

            self._execute_rollback(last)
            self._entries.pop()
            self._save()
        return last

    def rollback_all(self):
        """Annule toutes les actions en ordre inverse."""
        rolled_back = []
        skipped = []

        with self._lock:
            for entry in reversed(self._entries):
                if entry.can_rollback():
                    try:
                        self._execute_rollback(entry)
                        rolled_back.append(entry)
                    except StateError as e:
                        _logger.warning(f"Rollback echoue pour '{entry.target}': {e}")
                        skipped.append(entry)
                else:
                    _logger.warning(f"Ignore '{entry.target}' (pas de rollback, action={entry.action})")
                    skipped.append(entry)

            rolled_back_ids = {e.id for e in rolled_back}
            self._entries = [e for e in self._entries if e.id not in rolled_back_ids]
            self._save()

        return rolled_back

    def clear(self):
        """Efface l'historique sans rollback."""
        with self._lock:
            self._entries.clear()
            self._next_id = 1
            self._save()

    def summary(self):
        """Resume pour l'API."""
        with self._lock:
            total = len(self._entries)
            successful = sum(1 for e in self._entries if e.success)
            failed = total - successful
            rollbackable = sum(1 for e in self._entries if e.can_rollback())
            last = self._entries[-1] if self._entries else None

        return {
            "total_actions": total,
            "successful": successful,
            "failed": failed,
            "rollbackable": rollbackable,
            "last_action": last.to_dict() if last else None,
            "state_file": str(self.state_file),
        }

    # --- Interne ---

    def _execute_rollback(self, entry):
        import subprocess
        try:
            result = subprocess.run(
                entry.rollback_cmd, capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                raise StateError(
                    f"Rollback echoue (code {result.returncode}): "
                    f"{' '.join(entry.rollback_cmd)}\n{result.stderr}"
                )
        except subprocess.TimeoutExpired as e:
            raise StateError(f"Timeout rollback '{entry.target}'") from e
        except FileNotFoundError as e:
            raise StateError(f"Commande rollback introuvable : {e}") from e

    def _load(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.state_file.exists():
            self._entries = []
            self._next_id = 1
            self._save()
            return

        try:
            with open(self.state_file, encoding="utf-8") as f:
                data = json.load(f)
            self._entries = [StateEntry.from_dict(e) for e in data.get("entries", [])]
            self._next_id = data.get("next_id", len(self._entries) + 1)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            _logger.warning(f"StateManager: fichier corrompu ({e}), reinitialisation.")
            self._entries = []
            self._next_id = 1
            self._save()

    def _save(self):
        try:
            data = {
                "version": 1,
                "next_id": self._next_id,
                "entries": [e.to_dict() for e in self._entries],
            }
            tmp = self.state_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(self.state_file)
        except OSError as e:
            _logger.error(f"StateManager: echec sauvegarde : {e}")


# Singleton partage
_default_manager = None
_manager_lock = threading.Lock()


def get_state_manager(state_file=None):
    """Retourne le StateManager par defaut (singleton)."""
    global _default_manager
    with _manager_lock:
        if _default_manager is None or state_file is not None:
            _default_manager = StateManager(state_file)
        return _default_manager
