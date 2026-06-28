"""Tests pour utils/services_manager : whitelist + parsing systemctl mocke."""
import subprocess
from types import SimpleNamespace

import pytest

from utils import services_manager as sm


def _mk_result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_allowed_services_not_empty():
    assert len(sm.ALLOWED_SERVICES) >= 5
    # Sanity : tous les noms se terminent par .service ou .timer
    for name in sm.ALLOWED_SERVICES:
        assert name.endswith((".service", ".timer"))


def test_get_status_for_unknown_service():
    assert sm.get_service_status("kdump.service") is None


def test_get_status_active_enabled(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if cmd[1] == "is-active":
            return _mk_result(stdout="active\n")
        if cmd[1] == "is-enabled":
            return _mk_result(stdout="enabled\n")
        return _mk_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    status = sm.get_service_status("fstrim.timer")
    assert status is not None
    assert status["active"] is True
    assert status["enabled"] is True
    assert status["name"] == "fstrim.timer"


def test_get_status_not_found(monkeypatch):
    """is-enabled retourne stderr 'not-found' pour service absent."""
    def fake_run(cmd, **kw):
        if cmd[1] == "is-active":
            return _mk_result(stdout="inactive\n")
        return _mk_result(stdout="", stderr="Failed to get unit file state: not-found")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert sm.get_service_status("fstrim.timer") is None


def test_list_services_includes_all_whitelisted(monkeypatch):
    def fake_run(cmd, **kw):
        if cmd[1] == "is-active":
            return _mk_result(stdout="active\n")
        return _mk_result(stdout="enabled\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = sm.list_services()
    names = {s["name"] for s in result}
    assert names == set(sm.ALLOWED_SERVICES.keys())


def test_list_services_marks_missing(monkeypatch):
    def fake_run(cmd, **kw):
        if cmd[1] == "is-active":
            return _mk_result(stdout="inactive\n")
        return _mk_result(stdout="", stderr="not-found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = sm.list_services()
    for s in result:
        assert s["raw_active"] == "missing"
        assert s["enabled"] is False


def test_toggle_rejects_non_whitelisted(monkeypatch):
    ok, err = sm.toggle_service("kdump.service", True)
    assert ok is False
    assert "non autorise" in err


def test_toggle_success(monkeypatch):
    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _mk_result(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, err = sm.toggle_service("fstrim.timer", True)
    assert ok is True
    assert err == ""
    assert captured["cmd"][:4] == ["sudo", "-n", "systemctl", "enable"]
    assert "--now" in captured["cmd"]
    assert "fstrim.timer" in captured["cmd"]


def test_toggle_failure_password_required(monkeypatch):
    """Cas sudo cache expire — message utilisateur clair."""
    def fake_run(cmd, **kw):
        return _mk_result(returncode=1, stderr="a password is required")
    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, err = sm.toggle_service("fstrim.timer", True)
    assert ok is False
    assert "cache sudo" in err.lower()


def test_toggle_disable_uses_disable_action(monkeypatch):
    captured = {}
    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        return _mk_result(returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    sm.toggle_service("fstrim.timer", False)
    assert "disable" in captured["cmd"]
    assert "enable" not in captured["cmd"]


def test_toggle_timeout(monkeypatch):
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 15)
    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, err = sm.toggle_service("fstrim.timer", True)
    assert ok is False
    assert "timeout" in err.lower()
