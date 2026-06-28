"""Tests pour routes/fedora_wizards : wizard RPM Fusion (detection + activation)."""
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
    assert "/api/fedora/rpmfusion" in rules
    assert "/api/fedora/rpmfusion/enable" in rules
    assert "/api/fedora/codecs" in rules
    assert "/api/fedora/codecs/install" in rules
    assert "/api/fedora/nvidia" in rules
    assert "/api/fedora/nvidia/install" in rules
    assert "/api/fedora/flathub" in rules
    assert "/api/fedora/flathub/enable" in rules


def test_status_shape(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: False)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_fedora_version", lambda: "41")
    monkeypatch.setattr(fw, "_selinux_state", lambda: "enforcing")

    r = client.get("/api/fedora/rpmfusion")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["enabled"] is False
    assert data["fedora_version"] == "41"
    assert data["selinux"] == "enforcing"


def test_status_enabled_when_both_repos_active(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled",
                        lambda repo: repo in ("rpmfusion-free", "rpmfusion-nonfree"))
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_fedora_version", lambda: "41")
    monkeypatch.setattr(fw, "_selinux_state", lambda: "enforcing")

    data = client.get("/api/fedora/rpmfusion").get_json()
    assert data["free_enabled"] is True
    assert data["nonfree_enabled"] is True
    assert data["enabled"] is True


def test_enable_noop_when_already_enabled(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: True)
    monkeypatch.setattr(fw, "_fedora_version", lambda: "41")
    monkeypatch.setattr(fw, "_selinux_state", lambda: "enforcing")

    def _boom(*a, **k):
        raise AssertionError("ne doit pas installer quand deja active")
    monkeypatch.setattr(fw, "_stream_sudo", _boom)

    data = client.post("/api/fedora/rpmfusion/enable").get_json()
    assert data["success"] is True
    assert data["already_enabled"] is True


def test_enable_fails_without_fedora_version(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: False)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_fedora_version", lambda: None)
    monkeypatch.setattr(fw, "_selinux_state", lambda: "enforcing")

    r = client.post("/api/fedora/rpmfusion/enable")
    assert r.status_code == 500
    assert r.get_json()["success"] is False


def test_enable_installs_only_missing_repos(client, monkeypatch):
    from routes import fedora_wizards as fw
    # free deja la, nonfree manquant -> on ne doit installer que le nonfree.
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: repo == "rpmfusion-free")
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_fedora_version", lambda: "41")
    monkeypatch.setattr(fw, "_selinux_state", lambda: "permissive")

    captured = {}

    def _fake_stream(cmd, timeout=None):
        captured["cmd"] = cmd
        return 0
    monkeypatch.setattr(fw, "_stream_sudo", _fake_stream)

    r = client.post("/api/fedora/rpmfusion/enable")
    assert r.status_code == 200
    joined = " ".join(captured["cmd"])
    assert "nonfree" in joined
    assert "rpmfusion-free-release-41" not in joined  # free non reinstalle


def test_enable_propagates_install_failure(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: False)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_fedora_version", lambda: "41")
    monkeypatch.setattr(fw, "_selinux_state", lambda: "enforcing")
    monkeypatch.setattr(fw, "_stream_sudo", lambda cmd, timeout=None: 1)

    r = client.post("/api/fedora/rpmfusion/enable")
    assert r.status_code == 500
    assert r.get_json()["success"] is False


# --- Wizard codecs ---

def _patch_rpmfusion(monkeypatch, enabled):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: enabled)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_fedora_version", lambda: "41")
    monkeypatch.setattr(fw, "_selinux_state", lambda: "enforcing")


def test_codecs_status_shape(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    data = client.get("/api/fedora/codecs").get_json()
    assert data["success"] is True
    assert data["installed"] is False
    assert data["rpmfusion_enabled"] is True


def test_codecs_install_blocked_without_rpmfusion(client, monkeypatch):
    from routes import fedora_wizards as fw
    _patch_rpmfusion(monkeypatch, enabled=False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas installer sans RPM Fusion")
    monkeypatch.setattr(fw, "_stream_sudo", _boom)

    r = client.post("/api/fedora/codecs/install")
    assert r.status_code == 409
    body = r.get_json()
    assert body["success"] is False
    assert body["rpmfusion_required"] is True


def test_codecs_install_noop_when_present(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: True)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas reinstaller")
    monkeypatch.setattr(fw, "_stream_sudo", _boom)

    data = client.post("/api/fedora/codecs/install").get_json()
    assert data["success"] is True
    assert data["already_installed"] is True


def test_codecs_install_runs_all_steps(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    # Temoins absents -> not installed, mais rpmfusion actif.
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: pkg == "rpmfusion-free-release")
    calls = []
    monkeypatch.setattr(fw, "_stream_sudo", lambda cmd, timeout=None: calls.append(cmd) or 0)

    r = client.post("/api/fedora/codecs/install")
    assert r.status_code == 200
    assert len(calls) == 3
    assert any("install" in c for c in calls)
    assert any("multimedia" in c for c in calls)
    assert any("sound-and-video" in c for c in calls)


def test_codecs_install_stops_on_failure(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    calls = []

    def _stream(cmd, timeout=None):
        calls.append(cmd)
        return 1  # premiere etape echoue
    monkeypatch.setattr(fw, "_stream_sudo", _stream)

    r = client.post("/api/fedora/codecs/install")
    assert r.status_code == 500
    assert len(calls) == 1  # on s'arrete a la premiere erreur


# --- Wizard NVIDIA ---

def test_nvidia_status_shape(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_nvidia_gpu_present", lambda: True)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    monkeypatch.setattr(fw, "_secure_boot_enabled", lambda: True)

    data = client.get("/api/fedora/nvidia").get_json()
    assert data["success"] is True
    assert data["gpu_detected"] is True
    assert data["installed"] is False
    assert data["rpmfusion_enabled"] is True
    assert data["secure_boot"] is True


def test_nvidia_install_blocked_without_rpmfusion(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_nvidia_gpu_present", lambda: True)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: False)
    monkeypatch.setattr(fw, "_secure_boot_enabled", lambda: False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas installer sans RPM Fusion")
    monkeypatch.setattr(fw, "_stream_sudo", _boom)

    r = client.post("/api/fedora/nvidia/install")
    assert r.status_code == 409
    assert r.get_json()["rpmfusion_required"] is True


def test_nvidia_install_runs_when_ready(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_nvidia_gpu_present", lambda: True)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: False)
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    monkeypatch.setattr(fw, "_secure_boot_enabled", lambda: False)
    captured = {}
    monkeypatch.setattr(fw, "_stream_sudo",
                        lambda cmd, timeout=None: captured.update(cmd=cmd) or 0)

    r = client.post("/api/fedora/nvidia/install")
    assert r.status_code == 200
    assert "akmod-nvidia" in captured["cmd"]


def test_nvidia_install_noop_when_present(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_nvidia_gpu_present", lambda: True)
    monkeypatch.setattr(fw, "_pkg_installed", lambda pkg: True)
    monkeypatch.setattr(fw, "_repo_enabled", lambda repo: True)
    monkeypatch.setattr(fw, "_secure_boot_enabled", lambda: False)

    def _boom(*a, **k):
        raise AssertionError("ne doit pas reinstaller")
    monkeypatch.setattr(fw, "_stream_sudo", _boom)

    data = client.post("/api/fedora/nvidia/install").get_json()
    assert data["already_installed"] is True


# --- Wizard Flathub ---

def _fake_flatpak_remotes(stdout):
    class _R:
        def __init__(self, out):
            self.stdout = out
    def _run(cmd, **k):
        return _R(stdout)
    return _run


def test_flathub_status_filtered(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw.subprocess, "run",
                        _fake_flatpak_remotes("flathub\t/var/lib/flatpak/oci/flathub.filter\n"))
    data = client.get("/api/fedora/flathub").get_json()
    assert data["present"] is True
    assert data["filtered"] is True
    assert data["enabled"] is False


def test_flathub_status_full(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw.subprocess, "run",
                        _fake_flatpak_remotes("flathub\t-\n"))
    data = client.get("/api/fedora/flathub").get_json()
    assert data["present"] is True
    assert data["filtered"] is False
    assert data["enabled"] is True


def test_flathub_enable_adds_when_absent(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_flathub_status",
                        lambda: {"present": False, "filtered": False, "enabled": False})
    captured = {}
    monkeypatch.setattr(fw, "_stream_sudo",
                        lambda cmd, timeout=None: captured.update(cmd=cmd) or 0)

    r = client.post("/api/fedora/flathub/enable")
    assert r.status_code == 200
    assert "remote-add" in captured["cmd"]


def test_flathub_enable_unfilters_when_present(client, monkeypatch):
    from routes import fedora_wizards as fw
    # present mais filtre -> doit retirer le filtre via remote-modify.
    states = iter([
        {"present": True, "filtered": True, "enabled": False},   # avant
        {"present": True, "filtered": False, "enabled": True},   # apres
    ])
    monkeypatch.setattr(fw, "_flathub_status", lambda: next(states))
    captured = {}
    monkeypatch.setattr(fw, "_stream_sudo",
                        lambda cmd, timeout=None: captured.update(cmd=cmd) or 0)

    r = client.post("/api/fedora/flathub/enable")
    assert r.status_code == 200
    assert "remote-modify" in captured["cmd"]
    assert "--no-filter" in captured["cmd"]


def test_flathub_enable_noop_when_full(client, monkeypatch):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_flathub_status",
                        lambda: {"present": True, "filtered": False, "enabled": True})

    def _boom(*a, **k):
        raise AssertionError("ne doit rien faire")
    monkeypatch.setattr(fw, "_stream_sudo", _boom)

    data = client.post("/api/fedora/flathub/enable").get_json()
    assert data["already_enabled"] is True
