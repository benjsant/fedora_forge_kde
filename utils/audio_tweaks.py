"""Tweaks PipeWire (sample rate) et WirePlumber (codecs Bluetooth premium).

Toutes les modifications passent par des fichiers drop-in user-level dans
~/.config/{pipewire,wireplumber}/.conf.d/, jamais dans /etc/ — pas besoin
de sudo et restauration triviale (suppression du fichier).
"""
import re
import subprocess
from pathlib import Path

_PIPEWIRE_CONF = Path.home() / ".config/pipewire/pipewire.conf.d/10-fedoraforgekde-rate.conf"
_WIREPLUMBER_BT_CONF = Path.home() / ".config/wireplumber/wireplumber.conf.d/51-fedoraforgekde-bt-codecs.conf"

ALLOWED_RATES = (44100, 48000, 96000, 192000)


def get_current_sample_rate():
    """Lit le sample rate actif via `pw-metadata 0 clock.rate`. Retourne int|None."""
    try:
        r = subprocess.run(
            ["pw-metadata", "0", "clock.rate"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        # Output : "    update: id:0 key:'clock.rate' value:'48000' type:''"
        m = re.search(r"value:'(\d+)'", r.stdout)
        if m:
            return int(m.group(1))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def get_configured_sample_rate():
    """Lit le rate dans notre drop-in. None si non configure."""
    if not _PIPEWIRE_CONF.exists():
        return None
    try:
        content = _PIPEWIRE_CONF.read_text()
    except OSError:
        return None
    m = re.search(r"default\.clock\.rate\s*=\s*(\d+)", content)
    return int(m.group(1)) if m else None


def _atomic_write_text(path, content):
    """Ecrit `content` dans `path` de maniere atomique (tmp + os.replace).

    Evite de corrompre la config PipeWire si le process crash en cours d'ecriture
    (PipeWire refuse parfois de demarrer avec un fichier .conf tronque).
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content)
    tmp.replace(path)


def set_sample_rate(rate):
    """Ecrit le drop-in PipeWire avec le rate demande. Leve ValueError si invalide."""
    if rate not in ALLOWED_RATES:
        raise ValueError(f"Sample rate non autorise : {rate}")

    _PIPEWIRE_CONF.parent.mkdir(parents=True, exist_ok=True)
    allowed_str = " ".join(str(r) for r in ALLOWED_RATES)
    content = (
        "# Genere par FedoraForgeKDE\n"
        "context.properties = {\n"
        f"    default.clock.rate = {rate}\n"
        f"    default.clock.allowed-rates = [ {allowed_str} ]\n"
        "}\n"
    )
    _atomic_write_text(_PIPEWIRE_CONF, content)
    return True


def restart_pipewire():
    """Redemarre pipewire + pipewire-pulse + wireplumber (user-level)."""
    try:
        r = subprocess.run(
            ["systemctl", "--user", "restart",
             "pipewire", "pipewire-pulse", "wireplumber"],
            capture_output=True, text=True, timeout=15,
        )
        return r.returncode == 0, r.stderr.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def bt_premium_codecs_enabled():
    """True si notre drop-in BT premium est present."""
    return _WIREPLUMBER_BT_CONF.exists()


def set_bt_premium_codecs(enable):
    """Active/desactive LDAC + aptX-HD + AAC via drop-in WirePlumber."""
    if enable:
        _WIREPLUMBER_BT_CONF.parent.mkdir(parents=True, exist_ok=True)
        content = (
            "# Genere par FedoraForgeKDE\n"
            "monitor.bluez.properties = {\n"
            "  bluez5.enable-sbc-xq = true\n"
            "  bluez5.enable-msbc = true\n"
            "  bluez5.enable-hw-volume = true\n"
            "  bluez5.codecs = [ sbc sbc_xq ldac aptx aptx_hd aac ]\n"
            "  bluez5.roles = [ a2dp_sink a2dp_source bap_sink bap_source"
            " hsp_hs hsp_ag hfp_hf hfp_ag ]\n"
            "}\n"
        )
        _atomic_write_text(_WIREPLUMBER_BT_CONF, content)
    elif _WIREPLUMBER_BT_CONF.exists():
        _WIREPLUMBER_BT_CONF.unlink()
    return True
