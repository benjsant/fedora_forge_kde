"""Smoke tests Flask : boot l'app, verifie l'URL map, ping quelques endpoints."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


@pytest.fixture
def client():
    """Test client configure avec Host + Origin valides (simule un navigateur
    sur http://localhost:5000). Bypasse les checks anti-CSRF par defaut pour
    que les tests POST n'aient pas a configurer ces headers manuellement."""
    import os
    os.chdir(ROOT)
    from web_app import app
    app.config["TESTING"] = True
    c = app.test_client()
    c.environ_base["HTTP_HOST"] = "localhost:5000"
    c.environ_base["HTTP_ORIGIN"] = "http://localhost:5000"
    return c


@pytest.fixture
def raw_client():
    """Test client SANS Host/Origin par defaut — pour tester explicitement
    les protections anti-CSRF."""
    import os
    os.chdir(ROOT)
    from web_app import app
    app.config["TESTING"] = True
    return app.test_client()


def test_app_imports():
    from web_app import app
    assert app is not None


@pytest.mark.parametrize("rule", [
    "/api/status",
    "/api/profiles",
    "/api/themes/catalog",
    "/api/state",
    "/api/system/firewall",
    "/api/sddm/status",
    "/api/tools",
])
def test_url_rule_registered(rule):
    from web_app import app
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert rule in rules


def test_status_endpoint_returns_json(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    data = r.get_json()
    assert "checks" in data
    assert "packages" in data
    assert "task" in data


def test_profiles_endpoint_returns_known_slugs(client):
    r = client.get("/api/profiles")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    slugs = set(data["profiles"].keys())
    assert {"base", "gaming", "dev", "htpc", "handheld"}.issubset(slugs)


def test_system_tools_lists_known_tools(client):
    r = client.get("/api/tools")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    ids = {t["id"] for t in data["tools"]}
    # Outils GUI standard de Fedora KDE Spin
    assert {"discover", "systemsettings", "systemmonitor", "infocenter"}.issubset(ids)


def test_system_tools_launch_rejects_unknown_tool(client):
    r = client.post("/api/tools/launch/__nonexistent__")
    assert r.status_code == 404


def test_login_manager_status_returns_shape(client):
    r = client.get("/api/sddm/status")
    assert r.status_code == 200
    data = r.get_json()
    # On exige juste la presence des cles, pas la valeur (depend du systeme de test)
    assert "success" in data
    assert "current" in data or "dm" in data
