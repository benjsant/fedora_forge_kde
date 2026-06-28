"""Tests pour utils/selinux_manager et les routes /api/selinux/*."""
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


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


def test_routes_registered():
    from web_app import app
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/selinux/status" in rules
    assert "/api/selinux/boolean" in rules


def test_get_mode_parsing(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "_run", lambda cmd, timeout=10: _R(0, "Enforcing\n"))
    assert sm.get_mode() == "Enforcing"
    assert sm.is_available() is True


def test_get_mode_disabled(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "_run", lambda cmd, timeout=10: _R(0, "Disabled\n"))
    assert sm.get_mode() == "Disabled"
    assert sm.is_available() is False


def test_get_booleans_parses_getsebool(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "is_available", lambda: True)
    out = ("container_use_devices --> on\n"
           "container_manage_cgroup --> off\n"
           "selinuxuser_execmod --> off\n"
           "use_nfs_home_dirs --> off\n"
           "virt_use_nfs --> on\n")
    monkeypatch.setattr(sm, "_run", lambda cmd, timeout=10: _R(0, out))
    b = sm.get_booleans()
    assert b["container_use_devices"]["value"] is True
    assert b["container_manage_cgroup"]["value"] is False
    assert "description" in b["virt_use_nfs"]


def test_get_booleans_empty_when_disabled(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "is_available", lambda: False)
    assert sm.get_booleans() == {}


def test_set_boolean_rejects_non_whitelisted(monkeypatch):
    from utils import selinux_manager as sm

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler setsebool")
    monkeypatch.setattr(sm, "_run", _boom)
    ok, msg = sm.set_boolean("httpd_can_network_connect", True)
    assert ok is False
    assert "non autorise" in msg


def test_set_boolean_refuses_when_disabled(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "is_available", lambda: False)
    ok, msg = sm.set_boolean("container_use_devices", True)
    assert ok is False
    assert "actif" in msg


def test_set_boolean_success(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "is_available", lambda: True)
    captured = {}
    monkeypatch.setattr(sm, "_run",
                        lambda cmd, timeout=10: captured.update(cmd=cmd) or _R(0))
    ok, msg = sm.set_boolean("container_use_devices", True)
    assert ok is True
    assert "setsebool" in captured["cmd"]
    assert "-P" in captured["cmd"]
    assert "on" in captured["cmd"]


def test_recent_denials_empty_on_failure(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "_run", lambda cmd, timeout=10: None)
    assert sm.recent_denials() == []


def test_recent_denials_parses_lines(monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "_run",
                        lambda cmd, timeout=10: _R(0, "SELinux is preventing X\n\nSecond line\n"))
    d = sm.recent_denials()
    assert "SELinux is preventing X" in d
    assert "Second line" in d


def test_route_status_shape(client, monkeypatch):
    from utils import selinux_manager as sm
    monkeypatch.setattr(sm, "get_mode", lambda: "Enforcing")
    monkeypatch.setattr(sm, "get_booleans", lambda: {})
    monkeypatch.setattr(sm, "recent_denials", lambda minutes=10: [])
    r = client.get("/api/selinux/status")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["mode"] == "Enforcing"
    assert data["available"] is True


def test_route_boolean_rejects_unknown(client, monkeypatch):
    r = client.post("/api/selinux/boolean", json={"name": "evil_boolean", "enable": True})
    assert r.status_code == 400
    assert r.get_json()["success"] is False


def test_route_boolean_success(client, monkeypatch):
    from routes import selinux as route
    monkeypatch.setattr(route, "set_boolean", lambda name, enable: (True, f"{name} = on"))
    monkeypatch.setattr(route, "status",
                        lambda: {"mode": "Enforcing", "available": True,
                                 "booleans": {}, "denials": []})
    r = client.post("/api/selinux/boolean",
                    json={"name": "container_use_devices", "enable": True})
    assert r.status_code == 200
    assert r.get_json()["success"] is True
