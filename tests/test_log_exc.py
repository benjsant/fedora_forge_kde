"""Test de routes.shared.log_exc : message court via log_error, traceback au fichier.

On teste la logique directement (en interceptant log_error et le file logger)
plutot que la file SSE globale, dont l'etat depend de l'ordre des tests et de la
config logging de pytest."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


def test_log_exc_short_message_and_file_traceback(monkeypatch):
    from routes import shared
    msgs = []
    tb_calls = []
    monkeypatch.setattr(shared, "log_error", lambda m: msgs.append(m))
    monkeypatch.setattr(shared._file_logger, "error",
                        lambda fmt, *a, **k: tb_calls.append((fmt, a)))

    try:
        raise ValueError("bug test log_exc")
    except ValueError as e:
        shared.log_exc(f"Echec test : {e}")

    # message court -> log_error (donc SSE + fichier court)
    assert any("Echec test" in m for m in msgs)
    # traceback -> file logger uniquement, et elle contient bien l'exception
    assert tb_calls, "la traceback aurait du etre ecrite au fichier"
    assert "Traceback" in tb_calls[0][0]
    assert "ValueError" in tb_calls[0][1][0]


def test_log_exc_without_active_exception_skips_traceback(monkeypatch):
    from routes import shared
    monkeypatch.setattr(shared, "log_error", lambda m: None)
    tb_calls = []
    monkeypatch.setattr(shared._file_logger, "error",
                        lambda *a, **k: tb_calls.append(a))

    # Hors d'un except : format_exc() == 'NoneType: None' -> pas d'ecriture fichier.
    shared.log_exc("message simple sans exception")
    assert tb_calls == []
