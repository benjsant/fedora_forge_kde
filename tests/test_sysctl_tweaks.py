"""Tests pour utils/sysctl_tweaks et la route /api/tweaks/sysctls."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


@pytest.fixture
def client():
    import os
    os.chdir(ROOT)
    from web_app import app
    app.config["TESTING"] = True
    c = app.test_client()
    c.environ_base["HTTP_HOST"] = "localhost:5000"
    c.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"
    return c


def test_file_contents_has_all_keys():
    from utils import sysctl_tweaks as st
    content = st._file_contents()
    for key in st.GAMING_SYSCTLS:
        assert key in content
    assert content.startswith("#")


def test_status_applied_when_file_and_values_match(monkeypatch):
    from utils import sysctl_tweaks as st
    monkeypatch.setattr(st.os.path, "exists", lambda p: True)
    monkeypatch.setattr(st, "_live_values", lambda: dict(st.GAMING_SYSCTLS))
    s = st.status()
    assert s["applied"] is True
    assert s["drop_in_exists"] is True
    assert s["active"] is True


def test_status_not_applied_when_values_differ(monkeypatch):
    from utils import sysctl_tweaks as st
    monkeypatch.setattr(st.os.path, "exists", lambda p: True)
    monkeypatch.setattr(st, "_live_values",
                        lambda: dict.fromkeys(st.GAMING_SYSCTLS, "1"))
    s = st.status()
    assert s["applied"] is False
    assert s["active"] is False


def test_apply_writes_and_reloads(monkeypatch):
    from utils import sysctl_tweaks as st
    calls = []

    def _fake_run(cmd, **k):
        calls.append(cmd)

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(st.subprocess, "run", _fake_run)
    ok, msg = st.apply()
    assert ok is True
    # tee puis sysctl --system
    assert any("tee" in c for c in calls)
    assert any("--system" in c for c in calls)


def test_apply_fails_when_tee_denied(monkeypatch):
    from utils import sysctl_tweaks as st

    def _fake_run(cmd, **k):
        class _R:
            returncode = 1
            stderr = "sudo: a password is required"
        return _R()
    monkeypatch.setattr(st.subprocess, "run", _fake_run)
    ok, msg = st.apply()
    assert ok is False
    assert "password" in msg


def test_remove_noop_when_absent(monkeypatch):
    from utils import sysctl_tweaks as st
    monkeypatch.setattr(st.os.path, "exists", lambda p: False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler sudo")
    monkeypatch.setattr(st.subprocess, "run", _boom)
    ok, msg = st.remove()
    assert ok is True


def test_route_toggle_enable(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "sysctl_apply", lambda: (True, "applique"))
    monkeypatch.setattr(tweaks, "sysctl_status", lambda: {
        "applied": True, "drop_in_exists": True, "active": True,
        "target": {}, "current": {}})
    r = client.post("/api/tweaks/sysctls/toggle", json={"enable": True})
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["applied"] is True


def test_route_toggle_failure_returns_500(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "sysctl_remove", lambda: (False, "echec sudo"))
    r = client.post("/api/tweaks/sysctls/toggle", json={"enable": False})
    assert r.status_code == 500
    assert r.get_json()["success"] is False
