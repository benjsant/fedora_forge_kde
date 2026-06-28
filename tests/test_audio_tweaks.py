"""Tests pour utils/audio_tweaks : sample rate PipeWire + codecs Bluetooth."""
import importlib

import pytest


@pytest.fixture
def audio_mod(tmp_path, monkeypatch):
    """Module audio_tweaks avec Path.home() redirige."""
    import pathlib
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))
    from utils import audio_tweaks
    importlib.reload(audio_tweaks)
    return audio_tweaks, tmp_path


# ---------------------------------------------------------------------------
# Sample rate
# ---------------------------------------------------------------------------

def test_set_sample_rate_rejects_invalid(audio_mod):
    mod, _ = audio_mod
    with pytest.raises(ValueError):
        mod.set_sample_rate(12345)
    with pytest.raises(ValueError):
        mod.set_sample_rate(0)


def test_set_sample_rate_writes_dropin(audio_mod):
    mod, fake_home = audio_mod
    mod.set_sample_rate(48000)
    target = fake_home / ".config/pipewire/pipewire.conf.d/10-fedoraforgekde-rate.conf"
    assert target.exists()
    content = target.read_text()
    assert "default.clock.rate = 48000" in content
    assert "default.clock.allowed-rates" in content


def test_set_sample_rate_overwrites(audio_mod):
    mod, fake_home = audio_mod
    mod.set_sample_rate(48000)
    mod.set_sample_rate(96000)
    content = mod._PIPEWIRE_CONF.read_text()
    assert "96000" in content
    assert "48000" not in content or content.count("48000") == 1  # peut etre dans allowed-rates


def test_get_configured_sample_rate_none(audio_mod):
    mod, _ = audio_mod
    assert mod.get_configured_sample_rate() is None


def test_get_configured_sample_rate_after_set(audio_mod):
    mod, _ = audio_mod
    mod.set_sample_rate(96000)
    assert mod.get_configured_sample_rate() == 96000


def test_allowed_rates_consistent(audio_mod):
    mod, _ = audio_mod
    # 44100, 48000, 96000, 192000 sont les rates standards
    assert 44100 in mod.ALLOWED_RATES
    assert 48000 in mod.ALLOWED_RATES
    assert 96000 in mod.ALLOWED_RATES


# ---------------------------------------------------------------------------
# Codecs Bluetooth premium
# ---------------------------------------------------------------------------

def test_bt_premium_disabled_by_default(audio_mod):
    mod, _ = audio_mod
    assert mod.bt_premium_codecs_enabled() is False


def test_bt_premium_enable_creates_file(audio_mod):
    mod, fake_home = audio_mod
    mod.set_bt_premium_codecs(True)
    target = fake_home / ".config/wireplumber/wireplumber.conf.d/51-fedoraforgekde-bt-codecs.conf"
    assert target.exists()
    content = target.read_text()
    assert "ldac" in content
    assert "aptx_hd" in content
    assert "aac" in content
    assert mod.bt_premium_codecs_enabled() is True


def test_bt_premium_disable_removes_file(audio_mod):
    mod, _ = audio_mod
    mod.set_bt_premium_codecs(True)
    assert mod.bt_premium_codecs_enabled() is True

    mod.set_bt_premium_codecs(False)
    assert mod.bt_premium_codecs_enabled() is False
    assert not mod._WIREPLUMBER_BT_CONF.exists()


def test_bt_premium_disable_when_already_off(audio_mod):
    """Idempotent : disable sur etat off ne doit pas crasher."""
    mod, _ = audio_mod
    mod.set_bt_premium_codecs(False)  # already off
    assert mod.bt_premium_codecs_enabled() is False


def test_pipewire_conf_path_in_home(audio_mod):
    """Verifier que les chemins sont user-level (pas /etc/)."""
    mod, fake_home = audio_mod
    assert str(mod._PIPEWIRE_CONF).startswith(str(fake_home))
    assert str(mod._WIREPLUMBER_BT_CONF).startswith(str(fake_home))
    assert "/etc/" not in str(mod._PIPEWIRE_CONF)
    assert "/etc/" not in str(mod._WIREPLUMBER_BT_CONF)
