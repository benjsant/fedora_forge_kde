"""Tests pour utils/panel_tweaks et les routes /api/tweaks/panel."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

_APPLETSRC_SAMPLE = """[Containments][1]
activityId=abc
lastScreen=0
plugin=org.kde.plasma.folder

[Containments][1][General]
showText=false

[Containments][2]
formfactor=2
lastScreen=0
location=4
plugin=org.kde.panel

[Containments][2][Applets][3]
immutability=1
plugin=org.kde.plasma.kickoff

[Containments][2][General]
floating=1
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


def test_panel_containments_finds_only_panels(monkeypatch, tmp_path):
    from utils import panel_tweaks as pt
    f = tmp_path / "appletsrc"
    f.write_text(_APPLETSRC_SAMPLE)
    monkeypatch.setattr(pt, "_appletsrc_path", lambda: f)
    # Seul le containment 2 est un panneau (1 = folder/desktop)
    assert pt._panel_containments() == ["2"]


def test_panel_containments_empty_when_no_file(monkeypatch, tmp_path):
    from utils import panel_tweaks as pt
    monkeypatch.setattr(pt, "_appletsrc_path", lambda: tmp_path / "absent")
    assert pt._panel_containments() == []


def test_status_reports_floating(monkeypatch):
    from utils import panel_tweaks as pt
    monkeypatch.setattr(pt, "tools_available", lambda: True)
    monkeypatch.setattr(pt, "_panel_containments", lambda: ["2"])
    monkeypatch.setattr(pt, "_read_floating", lambda cid: True)
    # _appletsrc_path().exists() -> True via un faux Path
    monkeypatch.setattr(pt, "_appletsrc_path",
                        lambda: type("P", (), {"exists": lambda self: True})())
    s = pt.status()
    assert s["panel_count"] == 1
    assert s["floating"] is True
    assert s["all_fixed"] is False


def test_set_floating_writes_each_panel(monkeypatch):
    from utils import panel_tweaks as pt
    monkeypatch.setattr(pt, "tools_available", lambda: True)
    monkeypatch.setattr(pt, "_panel_containments", lambda: ["2", "5"])
    monkeypatch.setattr(pt, "_reload_plasmashell", lambda: True)
    calls = []

    def _run(cmd, **k):
        calls.append(cmd)

        class _R:
            returncode = 0
            stderr = ""
        return _R()
    monkeypatch.setattr(pt.subprocess, "run", _run)
    ok, msg = pt.set_floating(False)
    assert ok is True
    assert "fixe" in msg
    # un kwriteconfig6 par panneau, avec la valeur 0
    writes = [c for c in calls if c and c[0] == "kwriteconfig6"]
    assert len(writes) == 2
    assert all(c[-1] == "0" for c in writes)


def test_set_floating_no_panels(monkeypatch):
    from utils import panel_tweaks as pt
    monkeypatch.setattr(pt, "tools_available", lambda: True)
    monkeypatch.setattr(pt, "_panel_containments", lambda: [])
    ok, msg = pt.set_floating(False)
    assert ok is False
    assert "panneau" in msg.lower()


def test_set_floating_tools_missing(monkeypatch):
    from utils import panel_tweaks as pt
    monkeypatch.setattr(pt, "tools_available", lambda: False)
    ok, msg = pt.set_floating(True)
    assert ok is False


def test_set_floating_write_failure(monkeypatch):
    from utils import panel_tweaks as pt
    monkeypatch.setattr(pt, "tools_available", lambda: True)
    monkeypatch.setattr(pt, "_panel_containments", lambda: ["2"])

    def _run(cmd, **k):
        class _R:
            returncode = 1
            stderr = "boom"
        return _R()
    monkeypatch.setattr(pt.subprocess, "run", _run)
    ok, msg = pt.set_floating(False)
    assert ok is False
    assert "boom" in msg


def test_route_panel_status(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "panel_status", lambda: {
        "available": True, "panel_count": 1, "panels": [{"id": "2", "floating": True}],
        "floating": True, "all_fixed": False})
    r = client.get("/api/tweaks/panel")
    assert r.status_code == 200
    assert r.get_json()["floating"] is True


def test_route_panel_floating_failure(client, monkeypatch):
    from routes import tweaks
    monkeypatch.setattr(tweaks, "panel_set_floating", lambda f: (False, "echec"))
    monkeypatch.setattr(tweaks, "panel_status", lambda: {"available": True})
    r = client.post("/api/tweaks/panel/floating", json={"floating": False})
    assert r.status_code == 500
    assert r.get_json()["success"] is False
