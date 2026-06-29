"""Tests pour utils/dolphin_tweaks et les routes /api/tweaks/dolphin."""
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


def test_status_home_when_remember_false(monkeypatch):
    from utils import dolphin_tweaks as dt
    monkeypatch.setattr(dt, "tools_available", lambda: True)
    monkeypatch.setattr(dt, "_read_remember", lambda: "false")
    s = dt.status()
    assert s["home_on_startup"] is True
    assert s["remember_tabs"] is False


def test_status_remember_when_true(monkeypatch):
    from utils import dolphin_tweaks as dt
    monkeypatch.setattr(dt, "tools_available", lambda: True)
    monkeypatch.setattr(dt, "_read_remember", lambda: "true")
    s = dt.status()
    assert s["home_on_startup"] is False
    assert s["remember_tabs"] is True


def test_set_home_enable_writes_false(monkeypatch):
    from utils import dolphin_tweaks as dt
    monkeypatch.setattr(dt, "tools_available", lambda: True)
    captured = {}

    def _run(cmd, **k):
        captured["cmd"] = cmd

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(dt.subprocess, "run", _run)
    ok, msg = dt.set_home_on_startup(True)
    assert ok is True
    # home au demarrage => RememberOpenedTabs false
    assert captured["cmd"][-1] == "false"
    assert "RememberOpenedTabs" in captured["cmd"]


def test_set_home_disable_writes_true(monkeypatch):
    from utils import dolphin_tweaks as dt
    monkeypatch.setattr(dt, "tools_available", lambda: True)
    captured = {}

    def _run(cmd, **k):
        captured["cmd"] = cmd

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(dt.subprocess, "run", _run)
    ok, _ = dt.set_home_on_startup(False)
    assert ok is True
    assert captured["cmd"][-1] == "true"


def test_set_home_tools_missing(monkeypatch):
    from utils import dolphin_tweaks as dt
    monkeypatch.setattr(dt, "tools_available", lambda: False)
    ok, msg = dt.set_home_on_startup(True)
    assert ok is False


def test_set_home_write_failure(monkeypatch):
    from utils import dolphin_tweaks as dt
    monkeypatch.setattr(dt, "tools_available", lambda: True)

    def _run(cmd, **k):
        class _R:
            returncode = 1
            stderr = "boom"
        return _R()
    monkeypatch.setattr(dt.subprocess, "run", _run)
    ok, msg = dt.set_home_on_startup(True)
    assert ok is False
    assert "boom" in msg


def test_route_status(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "dolphin_status", lambda: {
        "available": True, "remember_tabs": False, "home_on_startup": True})
    r = client.get("/api/tweaks/dolphin")
    assert r.status_code == 200
    assert r.get_json()["home_on_startup"] is True


def test_route_toggle_failure_returns_500(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "dolphin_set_home", lambda e: (False, "echec"))
    monkeypatch.setattr(tweaks, "dolphin_status", lambda: {"available": True})
    r = client.post("/api/tweaks/dolphin/home-startup", json={"enable": True})
    assert r.status_code == 500
    assert r.get_json()["success"] is False
