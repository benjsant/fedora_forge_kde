"""Tests pour utils/kde_backup : creation, listing, restauration, securite."""
import importlib
import tarfile
from pathlib import Path

import pytest


@pytest.fixture
def backup_mod(tmp_path, monkeypatch):
    """Module kde_backup avec Path.home() redirige vers tmp_path."""
    fake_home = tmp_path
    (fake_home / ".config").mkdir()

    import pathlib
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: fake_home))

    from utils import kde_backup
    importlib.reload(kde_backup)
    return kde_backup, fake_home


# ---------------------------------------------------------------------------
# Sanitize label
# ---------------------------------------------------------------------------

def test_sanitize_label_alphanum(backup_mod):
    mod, _ = backup_mod
    assert mod._sanitize_label("abc123") == "abc123"


def test_sanitize_label_replaces_invalid(backup_mod):
    mod, _ = backup_mod
    assert mod._sanitize_label("hello world!") == "hello-world"


def test_sanitize_label_empty(backup_mod):
    mod, _ = backup_mod
    assert mod._sanitize_label("") == ""
    assert mod._sanitize_label(None) == ""


def test_sanitize_label_truncate_32(backup_mod):
    mod, _ = backup_mod
    long_label = "a" * 50
    assert len(mod._sanitize_label(long_label)) == 32


def test_sanitize_label_strips_separators(backup_mod):
    mod, _ = backup_mod
    assert mod._sanitize_label("---abc---") == "abc"


# ---------------------------------------------------------------------------
# Filename validation (path traversal)
# ---------------------------------------------------------------------------

def test_filename_regex_valid(backup_mod):
    mod, _ = backup_mod
    assert mod._FILENAME_RE.match("kde-20260526-143000.tar.gz")
    assert mod._FILENAME_RE.match("kde-20260526-143000-my-label.tar.gz")
    assert mod._FILENAME_RE.match("kde-20260526-143000-abc_123.tar.gz")


def test_filename_regex_rejects_traversal(backup_mod):
    mod, _ = backup_mod
    assert not mod._FILENAME_RE.match("../etc/passwd")
    assert not mod._FILENAME_RE.match("kde-foo.tar.gz")
    assert not mod._FILENAME_RE.match("kde-20260526-143000-.tar.gz")  # empty label
    assert not mod._FILENAME_RE.match("/absolute/path.tar.gz")


def test_validate_filename_blocks_traversal(backup_mod):
    mod, _ = backup_mod
    with pytest.raises(mod.BackupError):
        mod._validate_filename("../../etc/passwd")
    with pytest.raises(mod.BackupError):
        mod._validate_filename("/etc/passwd.tar.gz")


# ---------------------------------------------------------------------------
# Full create/list/restore/delete cycle
# ---------------------------------------------------------------------------

def test_create_backup_empty_fails(backup_mod):
    mod, _ = backup_mod
    with pytest.raises(mod.BackupError):
        mod.create_backup(label="empty")


def test_full_cycle(backup_mod):
    mod, fake_home = backup_mod
    config_dir = fake_home / ".config"
    (config_dir / "kdeglobals").write_text("[General]\nName=Sweet-Dark\n")
    (config_dir / "kwinrc").write_text("[Desktops]\nNumber=4\n")
    (config_dir / "Kvantum").mkdir()
    (config_dir / "Kvantum" / "kvantum.kvconfig").write_text("[General]\ntheme=Catppuccin\n")

    # CREATE
    info = mod.create_backup(label="test backup")
    assert info["files_count"] == 3
    assert "kdeglobals" in info["files"]
    assert "Kvantum/kvantum.kvconfig" in info["files"]
    assert info["label"] == "test-backup"

    # LIST
    backups = mod.list_backups()
    assert len(backups) == 1
    assert backups[0]["label"] == "test-backup"

    # Modify source, restore should revert
    (config_dir / "kdeglobals").write_text("[General]\nName=Modified\n")
    result = mod.restore_backup(info["filename"])
    assert result["count"] == 3
    assert result["skipped"] == []
    assert "Sweet-Dark" in (config_dir / "kdeglobals").read_text()

    # DELETE
    mod.delete_backup(info["filename"])
    assert mod.list_backups() == []


def test_list_backups_sorted_desc(backup_mod):
    mod, fake_home = backup_mod
    config_dir = fake_home / ".config"
    (config_dir / "kdeglobals").write_text("X")

    info1 = mod.create_backup(label="first")
    import time
    time.sleep(1.1)  # garantir mtime different
    info2 = mod.create_backup(label="second")

    backups = mod.list_backups()
    assert len(backups) == 2
    assert backups[0]["filename"] == info2["filename"]
    assert backups[1]["filename"] == info1["filename"]


# ---------------------------------------------------------------------------
# Tar member safety (defense en profondeur)
# ---------------------------------------------------------------------------

def test_max_backups_retention(backup_mod, monkeypatch):
    """Apres MAX_BACKUPS atteint, les plus anciennes sont supprimees a la creation."""
    mod, fake_home = backup_mod
    config_dir = fake_home / ".config"
    (config_dir / "kdeglobals").write_text("x")

    # Reduit la limite pour rendre le test rapide
    monkeypatch.setattr(mod, "MAX_BACKUPS", 3)

    # Cree 5 backups, espaces dans le temps
    import time
    created = []
    for i in range(5):
        info = mod.create_backup(label=f"backup{i}")
        created.append(info["filename"])
        time.sleep(1.05)  # garantir mtime distinct (precision seconde)

    backups = mod.list_backups()
    assert len(backups) == 3, f"Devrait avoir 3 backups apres prune, a {len(backups)}"

    # Les 3 plus recentes restent
    remaining = {b["filename"] for b in backups}
    assert created[-1] in remaining
    assert created[-2] in remaining
    assert created[-3] in remaining
    # Les anciennes ont ete pruned
    assert created[0] not in remaining
    assert created[1] not in remaining

    # Le compte pruned est rapporte par create_backup
    info = mod.create_backup(label="another")
    assert info["pruned"] == 1, f"Devrait avoir prune 1 entry, got {info['pruned']}"


def test_no_prune_when_under_limit(backup_mod):
    mod, fake_home = backup_mod
    config_dir = fake_home / ".config"
    (config_dir / "kdeglobals").write_text("x")

    # MAX_BACKUPS par defaut = 30, on en cree 2
    info1 = mod.create_backup(label="first")
    info2 = mod.create_backup(label="second")

    assert info1["pruned"] == 0
    assert info2["pruned"] == 0
    assert len(mod.list_backups()) == 2


def test_malicious_tar_members_skipped(backup_mod, tmp_path):
    """Un tar malicieux avec membres hors whitelist ou avec .. doit etre filtre."""
    mod, fake_home = backup_mod
    config_dir = fake_home / ".config"
    (config_dir / "kdeglobals").write_text("legit")

    # Cree un tar legitime puis on s'assure que les membres hors whitelist seraient ignores
    info = mod.create_backup(label="legit")

    # Reconstruit un tar avec des membres dangereux + un legit
    evil_tar = mod.BACKUP_DIR / info["filename"]
    with tarfile.open(evil_tar, "w:gz") as tar:
        # legit
        legit = tarfile.TarInfo(name="kdeglobals")
        data = b"restored content"
        legit.size = len(data)
        import io
        tar.addfile(legit, io.BytesIO(data))
        # malicieux : ..
        evil = tarfile.TarInfo(name="../../etc/passwd")
        evil.size = 4
        tar.addfile(evil, io.BytesIO(b"evil"))
        # hors whitelist
        unknown = tarfile.TarInfo(name="some-random-file")
        unknown.size = 5
        tar.addfile(unknown, io.BytesIO(b"hello"))

    result = mod.restore_backup(info["filename"])
    assert "kdeglobals" in result["restored"]
    assert "../../etc/passwd" in result["skipped"]
    assert "some-random-file" in result["skipped"]
    # Aucun fichier hors ~/.config n'a ete cree
    assert not Path("/etc/passwd").read_text().startswith("evil")
