"""Tests pour utils/ds_touchpad et les routes /api/tweaks/ds-touchpad."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

# Extrait realiste de /proc/bus/input/devices : une DS4 (pilote hid-sony,
# vendor 054c) avec ses trois interfaces, plus un clavier tiers.
_DEVICES_SAMPLE = """\
I: Bus=0003 Vendor=046d Product=c31c Version=0110
N: Name="Logitech USB Keyboard"
H: Handlers=sysrq kbd event3

I: Bus=0003 Vendor=054c Product=05c4 Version=8111
N: Name="Sony Computer Entertainment Wireless controller"
H: Handlers=js0 event19

I: Bus=0003 Vendor=054c Product=05c4 Version=8111
N: Name="Sony Computer Entertainment Wireless controller Touchpad"
H: Handlers=mouse2 event20

I: Bus=0003 Vendor=054c Product=05c4 Version=8111
N: Name="Sony Computer Entertainment Wireless controller Motion Sensors"
H: Handlers=event21
"""


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


def _patch_devices(monkeypatch, tmp_path, contents):
    import utils.ds_touchpad as ds
    devices = tmp_path / "devices"
    devices.write_text(contents, encoding="utf-8")
    monkeypatch.setattr(ds, "_DEVICES_FILE", str(devices))


def test_detect_finds_only_sony_touchpad(monkeypatch, tmp_path):
    from utils import ds_touchpad as ds
    _patch_devices(monkeypatch, tmp_path, _DEVICES_SAMPLE)
    names = ds.detect_touchpads()
    assert names == ["Sony Computer Entertainment Wireless controller Touchpad"]


def test_detect_empty_without_controller(monkeypatch, tmp_path):
    from utils import ds_touchpad as ds
    _patch_devices(monkeypatch, tmp_path,
                   "I: Bus=0003 Vendor=046d Product=c31c\n"
                   'N: Name="Logitech USB Keyboard"\n')
    assert ds.detect_touchpads() == []


def test_detect_empty_when_file_missing(monkeypatch):
    from utils import ds_touchpad as ds
    monkeypatch.setattr(ds, "_DEVICES_FILE", "/nonexistent/devices")
    assert ds.detect_touchpads() == []


def test_status_reports_rule_and_detection(monkeypatch, tmp_path):
    from utils import ds_touchpad as ds
    _patch_devices(monkeypatch, tmp_path, _DEVICES_SAMPLE)
    monkeypatch.setattr(ds.os.path, "exists", lambda p: p == ds.RULE_PATH)
    s = ds.status()
    assert s["rule_installed"] is True
    assert s["controller_present"] is True
    assert len(s["detected"]) == 1


def test_rule_contents_cover_both_driver_spellings():
    from utils import ds_touchpad as ds
    assert "Wireless Controller Touchpad" in ds.RULE_CONTENTS
    assert "Wireless controller Touchpad" in ds.RULE_CONTENTS
    assert "LIBINPUT_IGNORE_DEVICE" in ds.RULE_CONTENTS


def test_apply_writes_rule_and_reloads_udev(monkeypatch):
    from utils import ds_touchpad as ds
    calls = []

    def _fake_run(cmd, **k):
        calls.append(cmd)

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(ds.subprocess, "run", _fake_run)
    ok, msg = ds.apply()
    assert ok is True
    assert any("tee" in c for c in calls)
    assert any("--reload-rules" in c for c in calls)
    assert any("--subsystem-match=input" in c for c in calls)


def test_apply_fails_when_tee_denied(monkeypatch):
    from utils import ds_touchpad as ds

    def _fake_run(cmd, **k):
        class _R:
            returncode = 1
            stderr = "sudo: a password is required"
        return _R()
    monkeypatch.setattr(ds.subprocess, "run", _fake_run)
    ok, msg = ds.apply()
    assert ok is False
    assert "password" in msg


def test_remove_noop_when_absent(monkeypatch):
    from utils import ds_touchpad as ds
    monkeypatch.setattr(ds.os.path, "exists", lambda p: False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas appeler sudo")
    monkeypatch.setattr(ds.subprocess, "run", _boom)
    ok, msg = ds.remove()
    assert ok is True


def test_route_toggle_enable(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "ds_touchpad_apply", lambda: (True, "applique"))
    monkeypatch.setattr(tweaks, "ds_touchpad_status", lambda: {
        "rule_installed": True, "controller_present": False, "detected": []})
    r = client.post("/api/tweaks/ds-touchpad/toggle", json={"enable": True})
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["ignored"] is True


def test_route_toggle_failure_returns_500(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "ds_touchpad_remove",
                        lambda: (False, "echec sudo"))
    r = client.post("/api/tweaks/ds-touchpad/toggle", json={"enable": False})
    assert r.status_code == 500
    assert r.get_json()["success"] is False
