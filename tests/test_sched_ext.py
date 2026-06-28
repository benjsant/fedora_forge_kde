"""Tests pour utils/sched_ext et les routes /api/tweaks/scheduler."""
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


def test_routes_registered():
    from web_app import app
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/tweaks/scheduler" in rules
    assert "/api/tweaks/scheduler/toggle" in rules


def test_default_scheduler_whitelisted():
    from utils import sched_ext as sx
    assert sx.DEFAULT_SCHEDULER in sx.ALLOWED_SCHEDULERS


def test_status_shape(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx, "kernel_supports", lambda: True)
    monkeypatch.setattr(sx, "scx_installed", lambda: False)
    monkeypatch.setattr(sx, "active_scheduler", lambda: None)
    monkeypatch.setattr(sx.os.path, "exists", lambda p: False)
    s = sx.status()
    assert s["kernel_supported"] is True
    assert s["active"] is False
    assert s["default"] in s["schedulers"]


def test_enable_rejects_non_whitelisted(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx, "kernel_supports", lambda: True)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler sudo")
    monkeypatch.setattr(sx, "_sudo", _boom)
    ok, msg = sx.enable("scx_evil")
    assert ok is False
    assert "non autorise" in msg


def test_enable_refuses_without_kernel_support(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx, "kernel_supports", lambda: False)
    ok, msg = sx.enable("scx_lavd")
    assert ok is False
    assert "sched_ext" in msg


def test_enable_writes_unit_and_starts(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx, "kernel_supports", lambda: True)
    monkeypatch.setattr(sx, "_ensure_installed", lambda: (True, ""))
    monkeypatch.setattr(sx.shutil, "which", lambda b: f"/usr/bin/{b}")
    calls = []

    class _R:
        returncode = 0
        stderr = ""
    def _fake_sudo(cmd, timeout=120, **kw):
        calls.append(cmd)
        return _R()
    monkeypatch.setattr(sx, "_sudo", _fake_sudo)

    ok, msg = sx.enable("scx_lavd")
    assert ok is True
    joined = [" ".join(c) for c in calls]
    assert any("tee" in c for c in joined)
    assert any("enable" in c and "--now" in c for c in joined)


def test_enable_propagates_install_failure(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx, "kernel_supports", lambda: True)
    monkeypatch.setattr(sx, "_ensure_installed", lambda: (False, "echec dnf"))

    def _boom(*a, **k):
        raise AssertionError("ne doit pas ecrire l'unit si install echoue")
    monkeypatch.setattr(sx, "_sudo", _boom)
    ok, msg = sx.enable("scx_lavd")
    assert ok is False
    assert "echec dnf" in msg


def test_disable_noop_when_no_unit(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx.os.path, "exists", lambda p: False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler sudo")
    monkeypatch.setattr(sx, "_sudo", _boom)
    ok, msg = sx.disable()
    assert ok is True


def test_active_scheduler_reads_sysfs(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx, "_read",
                        lambda p: "enabled" if p.endswith("state") else "scx_lavd")
    assert sx.active_scheduler() == "scx_lavd"


def test_active_scheduler_none_when_disabled(monkeypatch):
    from utils import sched_ext as sx
    monkeypatch.setattr(sx, "_read", lambda p: "disabled")
    assert sx.active_scheduler() is None


def test_route_toggle_enable(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "scx_enable", lambda *a: (True, "scx_lavd active"))
    monkeypatch.setattr(tweaks, "scx_status", lambda: {
        "kernel_supported": True, "scx_installed": True, "active": True,
        "active_scheduler": "scx_lavd", "unit_enabled": True,
        "schedulers": {}, "default": "scx_lavd"})
    r = client.post("/api/tweaks/scheduler/toggle", json={"enable": True, "scheduler": "scx_lavd"})
    assert r.status_code == 200
    assert r.get_json()["active"] is True


def test_route_toggle_rejects_bad_scheduler(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "scx_enable", lambda *a: (False, "Scheduler non autorise : x"))
    monkeypatch.setattr(tweaks, "scx_status", lambda: {})
    r = client.post("/api/tweaks/scheduler/toggle", json={"enable": True, "scheduler": "x"})
    assert r.status_code == 400
    assert r.get_json()["success"] is False
