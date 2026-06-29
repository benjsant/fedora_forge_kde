"""Tests du routage CLI de fedora_kde_forge.main() (sans installation reelle)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))


def test_main_all_routes_to_run_all(monkeypatch):
    import fedora_kde_forge as ff
    captured = {}
    monkeypatch.setattr(ff, "_run_all",
                        lambda assume_yes=False: captured.setdefault("yes", assume_yes) or 0)
    monkeypatch.setattr(sys, "argv", ["prog", "--all"])
    assert ff.main() == 0
    assert captured["yes"] is False


def test_main_all_yes_sets_assume_yes(monkeypatch):
    import fedora_kde_forge as ff
    captured = {}
    monkeypatch.setattr(ff, "_run_all",
                        lambda assume_yes=False: captured.setdefault("yes", assume_yes) or 0)
    monkeypatch.setattr(sys, "argv", ["prog", "--all", "--yes"])
    ff.main()
    assert captured["yes"] is True


def test_main_profile_routes_to_run_cli(monkeypatch):
    import fedora_kde_forge as ff
    captured = {}

    def _fake_cli(slugs, dry_run):
        captured["slugs"] = slugs
        captured["dry_run"] = dry_run
        return 0
    monkeypatch.setattr(ff, "_run_cli", _fake_cli)
    monkeypatch.setattr(sys, "argv", ["prog", "--profile", "gaming,dev"])
    assert ff.main() == 0
    assert captured["slugs"] == ["gaming", "dev"]
    assert captured["dry_run"] is False


def test_main_profile_dry_run(monkeypatch):
    import fedora_kde_forge as ff
    captured = {}
    monkeypatch.setattr(ff, "_run_cli",
                        lambda slugs, dry_run: captured.update(dry_run=dry_run) or 0)
    monkeypatch.setattr(sys, "argv", ["prog", "--profile", "gaming", "--dry-run"])
    ff.main()
    assert captured["dry_run"] is True


def test_main_list_profiles(monkeypatch):
    import fedora_kde_forge as ff
    monkeypatch.setattr(ff, "_list_profiles", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["prog", "--list-profiles"])
    assert ff.main() == 0
