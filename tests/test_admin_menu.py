"""Tests pour utils/admin_menu et les routes /api/tweaks/admin-menu."""
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


def _fake_run(returncode=0, stderr=""):
    def _run(cmd, **k):
        class _R:
            pass
        _R.returncode = returncode
        _R.stderr = stderr
        return _R()
    return _run


def test_status_installed(monkeypatch):
    from utils import admin_menu as am
    monkeypatch.setattr(am, "is_installed", lambda: True)
    s = am.status()
    assert s["installed"] is True
    assert s["package"] == "kio-admin"


def test_is_installed_uses_rpm_q(monkeypatch):
    from utils import admin_menu as am
    captured = {}

    def _run(cmd, **k):
        captured["cmd"] = cmd

        class _R:
            returncode = 0
        return _R()
    monkeypatch.setattr(am.subprocess, "run", _run)
    assert am.is_installed() is True
    assert captured["cmd"] == ["rpm", "-q", "kio-admin"]


def test_enable_noop_when_already_installed(monkeypatch):
    from utils import admin_menu as am
    monkeypatch.setattr(am, "is_installed", lambda: True)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler sudo")
    monkeypatch.setattr(am.subprocess, "run", _boom)
    ok, msg = am.enable()
    assert ok is True
    assert "deja" in msg


def test_enable_installs_when_absent(monkeypatch):
    from utils import admin_menu as am
    monkeypatch.setattr(am, "is_installed", lambda: False)
    calls = []

    def _run(cmd, **k):
        calls.append(cmd)

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(am.subprocess, "run", _run)
    ok, msg = am.enable()
    assert ok is True
    assert any("dnf" in c and "install" in c and "kio-admin" in c for c in calls)


def test_enable_fails_when_sudo_denied(monkeypatch):
    from utils import admin_menu as am
    monkeypatch.setattr(am, "is_installed", lambda: False)
    monkeypatch.setattr(am.subprocess, "run",
                        _fake_run(returncode=1, stderr="sudo: a password is required"))
    ok, msg = am.enable()
    assert ok is False
    assert "password" in msg


def test_disable_noop_when_absent(monkeypatch):
    from utils import admin_menu as am
    monkeypatch.setattr(am, "is_installed", lambda: False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler sudo")
    monkeypatch.setattr(am.subprocess, "run", _boom)
    ok, msg = am.disable()
    assert ok is True


def test_disable_removes_when_present(monkeypatch):
    from utils import admin_menu as am
    monkeypatch.setattr(am, "is_installed", lambda: True)
    calls = []

    def _run(cmd, **k):
        calls.append(cmd)

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(am.subprocess, "run", _run)
    ok, msg = am.disable()
    assert ok is True
    assert any("dnf" in c and "remove" in c and "kio-admin" in c for c in calls)


def test_route_status(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "admin_menu_status",
                        lambda: {"installed": True, "package": "kio-admin"})
    r = client.get("/api/tweaks/admin-menu")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["installed"] is True


def test_route_toggle_enable(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "admin_menu_enable", lambda: (True, "installe"))
    monkeypatch.setattr(tweaks, "admin_menu_status",
                        lambda: {"installed": True, "package": "kio-admin"})
    r = client.post("/api/tweaks/admin-menu/toggle", json={"enable": True})
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["installed"] is True


def test_route_toggle_failure_returns_500(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "admin_menu_enable", lambda: (False, "echec sudo"))
    monkeypatch.setattr(tweaks, "admin_menu_status",
                        lambda: {"installed": False, "package": "kio-admin"})
    r = client.post("/api/tweaks/admin-menu/toggle", json={"enable": True})
    assert r.status_code == 500
    assert r.get_json()["success"] is False
