"""Tests pour utils/plasma_tweaks : nettoyage caches + reset (mocke)."""
import importlib

import pytest


@pytest.fixture
def plasma_mod(tmp_path, monkeypatch):
    """Module plasma_tweaks avec Path.home() redirige."""
    import pathlib
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    from utils import plasma_tweaks
    importlib.reload(plasma_tweaks)
    return plasma_tweaks, tmp_path


def test_clear_caches_no_cache_dir(plasma_mod):
    mod, _ = plasma_mod
    result = mod.clear_caches()
    assert result["freed_bytes"] == 0
    assert result["cleared"] == []


def test_clear_caches_thumbnails_and_plasma(plasma_mod):
    mod, fake_home = plasma_mod
    cache = fake_home / ".cache"
    cache.mkdir()
    (cache / "thumbnails").mkdir()
    (cache / "thumbnails" / "large.png").write_bytes(b"x" * 1000)
    (cache / "krunner").mkdir()
    (cache / "krunner" / "data.db").write_bytes(b"y" * 500)
    (cache / "plasma_engine_potd").mkdir()
    (cache / "plasma_engine_potd" / "img.jpg").write_bytes(b"z" * 200)
    # Fichier hors scope, ne doit pas etre touche
    (cache / "firefox").mkdir()
    (cache / "firefox" / "cache.db").write_bytes(b"w" * 100)

    result = mod.clear_caches()

    # Au moins 1700 octets supprimes (thumbnails + krunner + plasma_engine_potd)
    assert result["freed_bytes"] >= 1700
    # firefox doit etre intact
    assert (cache / "firefox" / "cache.db").exists()
    assert "thumbnails" in result["cleared"]
    assert "krunner" in result["cleared"]


def test_clear_caches_recreates_dirs(plasma_mod):
    """Les dossiers vides whitelistes sont recrees (pour que Plasma puisse re-ecrire)."""
    mod, fake_home = plasma_mod
    cache = fake_home / ".cache"
    cache.mkdir()
    (cache / "thumbnails").mkdir()
    (cache / "thumbnails" / "img.png").write_bytes(b"x" * 100)

    mod.clear_caches()
    assert (cache / "thumbnails").exists()
    assert (cache / "thumbnails").is_dir()
    # Vide
    assert list((cache / "thumbnails").iterdir()) == []


def test_clear_caches_handles_kcache_file(plasma_mod):
    """icon-cache.kcache est un fichier, pas un dossier."""
    mod, fake_home = plasma_mod
    cache = fake_home / ".cache"
    cache.mkdir()
    (cache / "icon-cache.kcache").write_bytes(b"binary" * 100)

    result = mod.clear_caches()
    assert "icon-cache.kcache" in result["cleared"]
    assert not (cache / "icon-cache.kcache").exists()


def test_dir_size_recursive(plasma_mod):
    mod, fake_home = plasma_mod
    d = fake_home / "test_dir"
    d.mkdir()
    (d / "a.txt").write_bytes(b"x" * 100)
    (d / "sub").mkdir()
    (d / "sub" / "b.txt").write_bytes(b"y" * 200)

    assert mod._dir_size(d) == 300


def test_reset_plasmashell_when_binary_absent(plasma_mod, monkeypatch):
    """Si kstart6 et plasmashell sont absents du PATH, doit retourner False."""
    mod, _ = plasma_mod
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    # Mock subprocess.run pour eviter d'appeler kquitapp6 reellement
    import subprocess

    class FakeCompleted:
        returncode = 1
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: FakeCompleted())

    assert mod.reset_plasmashell() is False
