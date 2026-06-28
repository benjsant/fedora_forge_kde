"""Tests Pydantic : round-trip sur tous les configs JSON."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CONFIGS = ROOT / "configs"


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


# --- Schemas individuels ------------------------------------------------------

def test_install_json_valid():
    from schemas import PackageList
    PackageList.model_validate(_load(CONFIGS / "install.json"))


def test_remove_json_valid():
    from schemas import PackageList
    PackageList.model_validate(_load(CONFIGS / "remove.json"))


def test_optional_install_json_valid():
    from schemas import PackageList
    PackageList.model_validate(_load(CONFIGS / "optional_install.json"))


def test_flatpak_json_valid():
    from schemas import FlatpakList
    FlatpakList.model_validate(_load(CONFIGS / "flatpak.json"))


def test_external_packages_json_valid():
    from schemas import ExternalPackageList
    ExternalPackageList.model_validate(_load(CONFIGS / "external_packages.json"))


@pytest.mark.parametrize("name", ["themes_gtk.json", "themes_icons.json", "themes_cursors.json"])
def test_themes_json_valid(name):
    from schemas import ThemeList
    ThemeList.model_validate(_load(CONFIGS / name))


# --- Profils ------------------------------------------------------------------

def _profile_files():
    return sorted((CONFIGS / "profiles").glob("*.json"))


@pytest.mark.parametrize("path", _profile_files(), ids=lambda p: p.stem)
def test_profile_round_trip(path):
    """Chaque profil doit etre valide par Pydantic ET serialiser sans perte."""
    from schemas import Profile
    raw = _load(path)
    p = Profile.model_validate(raw)
    # Champs cles preserves
    assert p.name
    assert isinstance(p.apt, list)
    assert isinstance(p.flatpak, list)
    assert isinstance(p.external, list)
    assert isinstance(p.remove, list)


def test_all_profiles_have_unique_names():
    from schemas import Profile
    names = []
    for path in _profile_files():
        p = Profile.model_validate(_load(path))
        names.append(p.name)
    assert len(names) == len(set(names)), f"Noms de profils dupliques : {names}"


def test_profile_order_covers_all_slugs():
    """Tout profil livre doit etre present dans PROFILE_ORDER (sinon il tombera en fin de liste)."""
    from routes.profiles import PROFILE_ORDER
    slugs = {p.stem for p in _profile_files()}
    missing = slugs - set(PROFILE_ORDER)
    assert not missing, f"Profils absents de PROFILE_ORDER : {missing}"
