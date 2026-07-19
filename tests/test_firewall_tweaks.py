"""Tests pour utils/firewall_tweaks et les routes /api/system/firewall/harden."""
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


def test_status_hardened_when_ranges_absent(monkeypatch):
    from utils import firewall_tweaks as fw

    def _fake(args, timeout=15):
        if args == ["--state"]:
            return True, "running", ""
        if args == ["--get-default-zone"]:
            return True, "FedoraWorkstation", ""
        if "--list-ports" in args:
            return True, "", ""
        raise AssertionError(f"appel inattendu : {args}")
    monkeypatch.setattr(fw, "_firewalld", _fake)
    s = fw.status()
    assert s["available"] is True
    assert s["zone"] == "FedoraWorkstation"
    assert s["hardened"] is True
    assert s["open_ranges"] == []


def test_status_not_hardened_when_ranges_open(monkeypatch):
    from utils import firewall_tweaks as fw

    def _fake(args, timeout=15):
        if args == ["--state"]:
            return True, "running", ""
        if args == ["--get-default-zone"]:
            return True, "FedoraWorkstation", ""
        if "--list-ports" in args:
            return True, "1025-65535/udp 1025-65535/tcp 8080/tcp", ""
        raise AssertionError(f"appel inattendu : {args}")
    monkeypatch.setattr(fw, "_firewalld", _fake)
    s = fw.status()
    assert s["hardened"] is False
    assert set(s["open_ranges"]) == set(fw.PORT_RANGES)


def test_status_unavailable_when_firewalld_down(monkeypatch):
    from utils import firewall_tweaks as fw
    monkeypatch.setattr(fw, "_firewalld",
                        lambda args, timeout=15: (False, "", "not running"))
    s = fw.status()
    assert s["available"] is False
    assert s["hardened"] is False


def test_apply_removes_both_ranges_and_reloads(monkeypatch):
    from utils import firewall_tweaks as fw
    calls = []

    def _fake(args, timeout=15):
        calls.append(args)
        if args == ["--get-default-zone"]:
            return True, "FedoraWorkstation", ""
        return True, "", ""
    monkeypatch.setattr(fw, "_firewalld", _fake)
    ok, msg = fw.apply()
    assert ok is True
    removes = [c for c in calls if "--remove-port" in c]
    assert len(removes) == 2
    assert all("--permanent" in c for c in removes)
    assert ["--reload"] in calls


def test_apply_fails_without_zone(monkeypatch):
    from utils import firewall_tweaks as fw
    monkeypatch.setattr(fw, "_firewalld",
                        lambda args, timeout=15: (False, "", "sudo requis"))
    ok, msg = fw.apply()
    assert ok is False


def test_remove_readds_both_ranges(monkeypatch):
    from utils import firewall_tweaks as fw
    calls = []

    def _fake(args, timeout=15):
        calls.append(args)
        if args == ["--get-default-zone"]:
            return True, "FedoraWorkstation", ""
        return True, "", ""
    monkeypatch.setattr(fw, "_firewalld", _fake)
    ok, msg = fw.remove()
    assert ok is True
    adds = [c for c in calls if "--add-port" in c]
    assert len(adds) == 2
    assert ["--reload"] in calls


def test_route_harden_toggle_enable(client, monkeypatch):
    from routes import system
    monkeypatch.setattr(system, "fw_harden_apply", lambda: (True, "ferme"))
    monkeypatch.setattr(system, "fw_harden_status", lambda: {
        "available": True, "zone": "FedoraWorkstation",
        "open_ranges": [], "hardened": True})
    r = client.post("/api/system/firewall/harden/toggle", json={"enable": True})
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["hardened"] is True


def test_route_harden_toggle_failure_returns_500(client, monkeypatch):
    from routes import system
    monkeypatch.setattr(system, "fw_harden_remove",
                        lambda: (False, "echec sudo"))
    r = client.post("/api/system/firewall/harden/toggle", json={"enable": False})
    assert r.status_code == 500
    assert r.get_json()["success"] is False
