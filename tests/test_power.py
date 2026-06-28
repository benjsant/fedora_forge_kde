"""Tests detection alimentation : sur batterie ou secteur."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


def _make_supply(tmp_path, name, type_, **fields):
    """Cree un faux /sys/class/power_supply/<name>/ pour les tests."""
    d = tmp_path / name
    d.mkdir(parents=True)
    (d / "type").write_text(type_)
    for k, v in fields.items():
        (d / k).write_text(str(v))
    return d


def test_no_power_supply_dir_returns_none(tmp_path, monkeypatch):
    """Pas de /sys/class/power_supply -> retourne None."""
    import importlib

    from utils import power
    monkeypatch.setattr(power, "_POWER_SUPPLY", tmp_path / "missing")
    importlib.reload(power)  # pas strictement necessaire mais coherent
    monkeypatch.setattr(power, "_POWER_SUPPLY", tmp_path / "missing")
    assert power.get_power_state() is None


def test_desktop_no_battery_returns_none(tmp_path, monkeypatch):
    """Aucune entree de type Battery -> desktop -> None."""
    from utils import power
    _make_supply(tmp_path, "ADP1", "Mains", online=1)
    monkeypatch.setattr(power, "_POWER_SUPPLY", tmp_path)
    assert power.get_power_state() is None


def test_laptop_on_ac(tmp_path, monkeypatch):
    """Batterie + AC online=1 -> on_battery=False."""
    from utils import power
    _make_supply(tmp_path, "BAT0", "Battery", capacity=85, status="Charging")
    _make_supply(tmp_path, "AC", "Mains", online=1)
    monkeypatch.setattr(power, "_POWER_SUPPLY", tmp_path)
    state = power.get_power_state()
    assert state == {"on_battery": False, "capacity": 85, "status": "Charging"}


def test_laptop_on_battery(tmp_path, monkeypatch):
    """Batterie + AC online=0 -> on_battery=True."""
    from utils import power
    _make_supply(tmp_path, "BAT0", "Battery", capacity=42, status="Discharging")
    _make_supply(tmp_path, "AC", "Mains", online=0)
    monkeypatch.setattr(power, "_POWER_SUPPLY", tmp_path)
    state = power.get_power_state()
    assert state["on_battery"] is True
    assert state["capacity"] == 42
    assert state["status"] == "Discharging"


def test_laptop_no_ac_adapter_assumed_battery(tmp_path, monkeypatch):
    """Batterie sans entree Mains -> on suppose sur batterie (cas degenere)."""
    from utils import power
    _make_supply(tmp_path, "BAT0", "Battery", capacity=70, status="Discharging")
    monkeypatch.setattr(power, "_POWER_SUPPLY", tmp_path)
    state = power.get_power_state()
    assert state["on_battery"] is True


def test_capacity_unreadable_is_none(tmp_path, monkeypatch):
    """Capacity vide ou non numerique -> None (pas de crash)."""
    from utils import power
    _make_supply(tmp_path, "BAT0", "Battery", status="Full")
    # pas de fichier capacity
    _make_supply(tmp_path, "AC", "Mains", online=1)
    monkeypatch.setattr(power, "_POWER_SUPPLY", tmp_path)
    state = power.get_power_state()
    assert state["capacity"] is None
    assert state["on_battery"] is False
