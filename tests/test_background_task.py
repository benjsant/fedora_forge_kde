"""Tests de start_background_task (slot de tache global) et du fallback de port."""
import socket
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


@pytest.fixture(autouse=True)
def _reset_task():
    """Remet le slot de tache global a zero avant et apres chaque test."""
    from routes import shared
    with shared.task_lock:
        shared.current_task.update(running=False, name="", progress=0)
    yield
    with shared.task_lock:
        shared.current_task.update(running=False, name="", progress=0)


def _wait_until(cond, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_background_task_runs_and_frees_slot():
    from routes import shared
    done = threading.Event()

    def worker():
        done.set()
        return True

    assert shared.start_background_task("test", worker) is True
    assert done.wait(timeout=5)
    # Le slot doit etre libere une fois le worker termine.
    assert _wait_until(lambda: not shared.current_task["running"])
    assert shared.current_task["progress"] == 100


def test_background_task_refuses_when_busy():
    from routes import shared
    release = threading.Event()
    started = threading.Event()

    def worker():
        started.set()
        release.wait(timeout=5)
        return True

    assert shared.start_background_task("longue", worker) is True
    assert started.wait(timeout=5)
    # Pendant que la premiere tourne, toute autre tache est refusee.
    assert shared.start_background_task("autre", lambda: True) is False
    release.set()
    assert _wait_until(lambda: not shared.current_task["running"])


def test_background_task_frees_slot_on_exception():
    from routes import shared

    def worker():
        raise RuntimeError("boum")

    assert shared.start_background_task("plantage", worker) is True
    assert _wait_until(lambda: not shared.current_task["running"])
    assert "echec" in shared.current_task["name"]


# --- Fallback de port ---

def test_find_free_port_skips_occupied():
    from web_app import _find_free_port
    # Occupe un port, verifie que le scan glisse sur le suivant.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        busy = s.getsockname()[1]
        found = _find_free_port(busy)
        assert found is not None
        assert found != busy


def test_resolve_port_env(monkeypatch):
    from web_app import _resolve_port
    monkeypatch.setenv("FEDORAFORGEKDE_PORT", "8123")
    assert _resolve_port() == 8123
    monkeypatch.setenv("FEDORAFORGEKDE_PORT", "abc")
    assert _resolve_port() == 5000
    monkeypatch.setenv("FEDORAFORGEKDE_PORT", "80")  # < 1024 refuse
    assert _resolve_port() == 5000
    monkeypatch.delenv("FEDORAFORGEKDE_PORT")
    assert _resolve_port() == 5000
