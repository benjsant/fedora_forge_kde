"""Tests du catalogue COPR experimental (schema + fichier reel)."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


def test_copr_json_valide_contre_le_schema():
    from schemas import CoprCatalog
    data = json.loads((ROOT / "configs/copr.json").read_text(encoding="utf-8"))
    cat = CoprCatalog(**data)
    assert cat.experimental_warning.strip()
    assert len(cat.copr) >= 1
    # chaque entree : id owner/project + au moins un paquet
    for repo in cat.copr:
        assert "/" in repo.id
        assert repo.packages


def test_copr_warning_mentionne_le_risque():
    data = json.loads((ROOT / "configs/copr.json").read_text(encoding="utf-8"))
    w = data["experimental_warning"].lower()
    # le disclaimer doit clairement signaler le risque et l'origine tierce
    assert "risque" in w or "perils" in w
    assert "fedora" in w


def test_copr_id_invalide_rejete():
    from pydantic import ValidationError

    from schemas import CoprCatalog
    bad = {"experimental_warning": "x",
           "copr": [{"id": "sans-slash", "description": "d", "packages": ["p"]}]}
    with pytest.raises(ValidationError):
        CoprCatalog(**bad)


def test_copr_catalogue_vide_rejete():
    from pydantic import ValidationError

    from schemas import CoprCatalog
    with pytest.raises(ValidationError):
        CoprCatalog(experimental_warning="x", copr=[])


def test_copr_warning_obligatoire():
    from pydantic import ValidationError

    from schemas import CoprCatalog
    with pytest.raises(ValidationError):
        CoprCatalog(copr=[{"id": "a/b", "description": "d", "packages": ["p"]}])


def test_validation_globale_inclut_copr():
    from utils.validation import validate_all_configs
    results = validate_all_configs(str(ROOT / "configs"))
    assert "copr.json" in results
    assert results["copr.json"] is not None


# --- Routes /api/copr ---

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


def test_route_copr_list(client):
    r = client.get("/api/copr")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["warning"]
    assert any("/" in c["id"] for c in data["copr"])


def test_route_copr_enable_requiert_confirmation(client):
    r = client.post("/api/copr/enable", json={"id": "atim/lazygit", "confirmed": False})
    assert r.status_code == 400
    assert "Confirmation" in r.get_json()["error"]


def test_route_copr_enable_rejette_id_hors_catalogue(client):
    # whitelist stricte : meme confirme, un id absent du catalogue est refuse
    r = client.post("/api/copr/enable", json={"id": "pirate/malware", "confirmed": True})
    assert r.status_code == 400
    assert "non autorise" in r.get_json()["error"]
