"""Tests pour la garde RPM Fusion du preflight (/api/profiles/preflight)."""
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


def _rf(enabled):
    return {"free_enabled": enabled, "nonfree_enabled": enabled,
            "enabled": enabled, "fedora_version": "41", "selinux": "enforcing"}


def test_warns_when_rpmfusion_package_and_disabled(client, monkeypatch):
    from routes import profiles
    # Rien d'installe -> tout part en "to_install"
    monkeypatch.setattr(profiles, "check_package_installed", lambda n: False)
    monkeypatch.setattr(profiles, "check_flatpak_installed", lambda a: False)
    monkeypatch.setattr(profiles, "_rpmfusion_status", lambda: _rf(False))

    r = client.post("/api/profiles/preflight", json={"profiles": ["gaming"]})
    assert r.status_code == 200
    warnings = " ".join(r.get_json()["warnings"])
    assert "RPM Fusion" in warnings
    assert "steam" in warnings


def test_no_warning_when_rpmfusion_enabled(client, monkeypatch):
    from routes import profiles
    monkeypatch.setattr(profiles, "check_package_installed", lambda n: False)
    monkeypatch.setattr(profiles, "check_flatpak_installed", lambda a: False)
    monkeypatch.setattr(profiles, "_rpmfusion_status", lambda: _rf(True))

    r = client.post("/api/profiles/preflight", json={"profiles": ["gaming"]})
    warnings = " ".join(r.get_json()["warnings"])
    assert "RPM Fusion" not in warnings


def test_no_warning_when_package_already_installed(client, monkeypatch):
    from routes import profiles
    # Tout deja installe -> rien dans to_install -> pas de garde declenchee
    monkeypatch.setattr(profiles, "check_package_installed", lambda n: True)
    monkeypatch.setattr(profiles, "check_flatpak_installed", lambda a: True)
    monkeypatch.setattr(profiles, "_rpmfusion_status", lambda: _rf(False))

    r = client.post("/api/profiles/preflight", json={"profiles": ["gaming"]})
    warnings = " ".join(r.get_json()["warnings"])
    assert "RPM Fusion" not in warnings


def test_profile_without_rpmfusion_pkg_no_warning(client, monkeypatch):
    from routes import profiles
    monkeypatch.setattr(profiles, "check_package_installed", lambda n: False)
    monkeypatch.setattr(profiles, "check_flatpak_installed", lambda a: False)
    monkeypatch.setattr(profiles, "_rpmfusion_status", lambda: _rf(False))

    # 'dev' ne contient aucun paquet RPM Fusion-only
    r = client.post("/api/profiles/preflight", json={"profiles": ["dev"]})
    warnings = " ".join(r.get_json()["warnings"])
    assert "RPM Fusion" not in warnings
