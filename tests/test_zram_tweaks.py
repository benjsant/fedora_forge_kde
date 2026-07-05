"""Tests pour utils/zram_tweaks et les routes /api/tweaks/zram."""
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


def test_zram_conf_has_zstd_and_size():
    from utils import zram_tweaks as zt
    conf = zt._zram_conf()
    assert "compression-algorithm = zstd" in conf
    assert "zram-size" in conf
    assert conf.startswith("#")


def test_sysctl_conf_has_swappiness():
    from utils import zram_tweaks as zt
    assert f"vm.swappiness = {zt.TARGET_SWAPPINESS}" in zt._sysctl_conf()


def test_current_algo_parses_brackets(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "_read",
                        lambda p: "lzo-rle lzo lz4 lz4hc [zstd] deflate 842")
    assert zt.current_algo() == "zstd"


def test_current_algo_none_when_absent(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "_read", lambda p: None)
    assert zt.current_algo() is None


def test_status_applied_when_live_matches(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "zram_present", lambda: True)
    monkeypatch.setattr(zt, "current_algo", lambda: "zstd")
    monkeypatch.setattr(zt, "current_swappiness", lambda: zt.TARGET_SWAPPINESS)
    monkeypatch.setattr(zt.os.path, "exists", lambda p: True)
    s = zt.status()
    assert s["applied"] is True
    assert s["zram_present"] is True


def test_status_not_applied_when_lzo(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "zram_present", lambda: True)
    monkeypatch.setattr(zt, "current_algo", lambda: "lzo-rle")
    monkeypatch.setattr(zt, "current_swappiness", lambda: 60)
    monkeypatch.setattr(zt.os.path, "exists", lambda p: False)
    s = zt.status()
    assert s["applied"] is False


def test_apply_writes_both_and_restarts(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "zram_present", lambda: True)
    calls = []

    def _fake_run(cmd, **k):
        calls.append(cmd)

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(zt.subprocess, "run", _fake_run)
    ok, msg = zt.apply()
    assert ok is True
    flat = [" ".join(c) for c in calls]
    assert any("zram-generator.conf" in c for c in flat)
    assert any("99-fedorakdeforge-zram.conf" in c for c in flat)
    assert any("--system" in c for c in flat)
    assert any(zt.ZRAM_SERVICE in c for c in flat)


def test_apply_fails_when_no_zram(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "zram_present", lambda: False)
    ok, msg = zt.apply()
    assert ok is False
    assert "zram" in msg.lower()


def test_apply_partial_when_restart_fails(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "zram_present", lambda: True)

    def _fake_run(cmd, **k):
        rc = 1 if "restart" in cmd else 0

        class _R:
            returncode = rc
            stderr = ""
        return _R()
    monkeypatch.setattr(zt.subprocess, "run", _fake_run)
    ok, msg = zt.apply()
    # swappiness ok, algo differe : succes degrade
    assert ok is True
    assert "zstd" in msg


def test_apply_fails_when_tee_denied(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt, "zram_present", lambda: True)

    def _fake_run(cmd, **k):
        class _R:
            returncode = 1
            stderr = "sudo: a password is required"
        return _R()
    monkeypatch.setattr(zt.subprocess, "run", _fake_run)
    ok, msg = zt.apply()
    assert ok is False
    assert "password" in msg


def test_remove_noop_when_absent(monkeypatch):
    from utils import zram_tweaks as zt
    monkeypatch.setattr(zt.os.path, "exists", lambda p: False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler sudo")
    monkeypatch.setattr(zt.subprocess, "run", _boom)
    ok, msg = zt.remove()
    assert ok is True


def test_route_status(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "zram_status", lambda: {
        "zram_present": True, "current_algo": "zstd", "current_swappiness": 100,
        "target_algo": "zstd", "target_swappiness": 100,
        "conf_exists": True, "applied": True})
    r = client.get("/api/tweaks/zram")
    assert r.status_code == 200
    assert r.get_json()["applied"] is True


def test_route_toggle_failure_returns_500(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "zram_apply", lambda: (False, "echec sudo"))
    monkeypatch.setattr(tweaks, "zram_status", lambda: {"zram_present": True})
    r = client.post("/api/tweaks/zram/toggle", json={"enable": True})
    assert r.status_code == 500
    assert r.get_json()["success"] is False
