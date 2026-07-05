"""Tests des routes de mise a jour systeme : compteur de MAJ + dnf upgrade."""
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


@pytest.fixture(autouse=True)
def _reset_cache():
    from routes import system
    system._invalidate_updates_cache()
    yield
    system._invalidate_updates_cache()


_CHECK_UPDATE_OUT = """\
kernel.x86_64                    6.18.4-200.fc44            updates
firefox.x86_64                   147.0-1.fc44               updates
vim-minimal.x86_64               2:9.2.100-1.fc44           updates

Obsoleting Packages
wget2.x86_64                     2.2.0-3.fc44               updates
    wget.x86_64                  1.21.4-8.fc44              @fedora
"""


def test_count_updates_ignore_obsoleting():
    from routes.system import _count_updates
    assert _count_updates(_CHECK_UPDATE_OUT) == 3


def test_count_updates_vide():
    from routes.system import _count_updates
    assert _count_updates("") == 0


def test_updates_route_a_jour(client, monkeypatch):
    from routes import system
    monkeypatch.setattr(system, "_run_check_update", lambda: (0, ""))
    data = client.get("/api/system/updates").get_json()
    assert data["success"] is True
    assert data["updates"] == 0


def test_updates_route_maj_disponibles(client, monkeypatch):
    from routes import system
    monkeypatch.setattr(system, "_run_check_update", lambda: (100, _CHECK_UPDATE_OUT))
    data = client.get("/api/system/updates").get_json()
    assert data["success"] is True
    assert data["updates"] == 3
    assert data["cached"] is False


def test_updates_route_cache(client, monkeypatch):
    from routes import system
    calls = []
    monkeypatch.setattr(system, "_run_check_update",
                        lambda: calls.append(1) or (100, _CHECK_UPDATE_OUT))
    client.get("/api/system/updates")
    data = client.get("/api/system/updates").get_json()
    assert data["cached"] is True
    assert len(calls) == 1  # le 2e appel sert le cache


def test_updates_route_erreur_dnf(client, monkeypatch):
    from routes import system
    monkeypatch.setattr(system, "_run_check_update", lambda: (1, ""))
    data = client.get("/api/system/updates").get_json()
    assert data["success"] is False


@pytest.fixture
def sync_tasks(monkeypatch):
    """Execute la tache de fond en synchrone et capture le resultat du worker."""
    from routes import system
    captured = {}

    def _sync(name, worker):
        captured["name"] = name
        captured["result"] = worker()
        return True

    monkeypatch.setattr(system, "start_background_task", _sync)
    return captured


def test_update_route_lance_dnf_upgrade(client, monkeypatch, sync_tasks):
    from routes import fedora_wizards as fw
    captured = {}
    monkeypatch.setattr(fw, "_stream_sudo",
                        lambda cmd, timeout=None: captured.update(cmd=cmd) or 0)

    r = client.post("/api/system/update")
    assert r.status_code == 200
    assert r.get_json()["started"] is True
    assert sync_tasks["result"] is True
    assert captured["cmd"][:2] == ["dnf", "upgrade"]
    assert "--refresh" in captured["cmd"]


def test_update_route_echec_reporte(client, monkeypatch, sync_tasks):
    from routes import fedora_wizards as fw
    monkeypatch.setattr(fw, "_stream_sudo", lambda cmd, timeout=None: 1)

    r = client.post("/api/system/update")
    assert r.status_code == 200
    assert sync_tasks["result"] is False


def test_update_route_invalide_le_cache(client, monkeypatch, sync_tasks):
    """Apres un upgrade reussi, le compteur de MAJ doit etre recalcule."""
    from routes import fedora_wizards as fw
    from routes import system
    monkeypatch.setattr(system, "_run_check_update", lambda: (100, _CHECK_UPDATE_OUT))
    client.get("/api/system/updates")  # remplit le cache

    monkeypatch.setattr(fw, "_stream_sudo", lambda cmd, timeout=None: 0)
    client.post("/api/system/update")

    monkeypatch.setattr(system, "_run_check_update", lambda: (0, ""))
    data = client.get("/api/system/updates").get_json()
    assert data["cached"] is False
    assert data["updates"] == 0


def test_update_route_busy_renvoie_409(client, monkeypatch):
    from routes import system
    monkeypatch.setattr(system, "start_background_task", lambda name, worker: False)
    r = client.post("/api/system/update")
    assert r.status_code == 409
