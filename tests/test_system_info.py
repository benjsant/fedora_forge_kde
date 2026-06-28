"""Tests pour utils/system_info : parsing OS, kernel patches, btrfs, zram."""
import importlib

import pytest


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset le cache module entre chaque test."""
    from utils import system_info
    importlib.reload(system_info)
    yield


def test_os_release_parsing(monkeypatch):
    from utils import system_info as si
    sample = (
        'NAME="Fedora Linux"\n'
        'VERSION="43 (KDE Plasma)"\n'
        'ID=fedora\n'
        '# comment\n'
        'VARIANT="KDE Plasma"\n'
    )
    monkeypatch.setattr(si, "_read_file", lambda p: sample if p == "/etc/os-release" else "")
    info = si._os_release()
    assert info["NAME"] == "Fedora Linux"
    assert info["ID"] == "fedora"
    assert info["VARIANT"] == "KDE Plasma"


def test_kernel_patches_detection(monkeypatch):
    from utils import system_info as si
    fake_config = (
        "CONFIG_CACHY=y\n"
        "CONFIG_SCHED_BORE=y\n"
        "CONFIG_NTSYNC=y\n"
        "CONFIG_HZ=1000\n"
        "CONFIG_PREEMPT_DYNAMIC=y\n"
    )
    monkeypatch.setattr(si, "_read_file", lambda p: fake_config if "config-" in p else "")
    result = si._kernel_patches()
    assert "CachyOS" in result["patches"]
    assert "BORE" in result["patches"]
    assert "NTSYNC" in result["patches"]
    assert "PREEMPT_DYN" in result["patches"]
    assert result["hz"] == 1000


def test_kernel_patches_vanilla(monkeypatch):
    from utils import system_info as si
    monkeypatch.setattr(si, "_read_file", lambda p: "CONFIG_HZ=250\n" if "config-" in p else "")
    result = si._kernel_patches()
    assert result["patches"] == []
    assert result["hz"] == 250


def test_lsm_list_parsing(monkeypatch):
    from utils import system_info as si
    monkeypatch.setattr(si, "_read_file",
                        lambda p: "capability,lockdown,yama,apparmor,bpf,landlock" if "lsm" in p else "")
    lsm = si._lsm_list()
    assert "apparmor" in lsm
    assert "landlock" in lsm
    assert "capability" in lsm


def test_selinux_state_from_config(monkeypatch):
    import subprocess

    from utils import system_info as si
    # getenforce indisponible -> tombe sur le fichier
    def fake_run(cmd, **kw):
        raise FileNotFoundError("getenforce absent")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(si, "_read_file",
                        lambda p: "SELINUX=disabled\nSELINUXTYPE=targeted\n" if "selinux" in p else "")
    assert si._selinux_state() == "disabled"


def test_btrfs_root_detection(monkeypatch):
    from utils import system_info as si
    fake_mounts = (
        "/dev/nvme0n1p3 / btrfs rw,relatime,compress=zstd:1,ssd,discard=async,subvol=/@ 0 0\n"
        "/dev/nvme0n1p2 /boot ext4 rw 0 0\n"
    )
    monkeypatch.setattr(si, "_read_file",
                        lambda p: fake_mounts if p == "/proc/mounts" else "")
    info = si._btrfs_root_info()
    assert info["is_btrfs"] is True
    assert info["compress"] == "zstd:1"
    assert info["subvol"] == "/@"
    assert info["discard"] == "discard=async"


def test_non_btrfs_root(monkeypatch):
    from utils import system_info as si
    fake_mounts = "/dev/sda1 / ext4 rw 0 0\n"
    monkeypatch.setattr(si, "_read_file",
                        lambda p: fake_mounts if p == "/proc/mounts" else "")
    info = si._btrfs_root_info()
    assert info["is_btrfs"] is False


def test_zram_detection(monkeypatch):
    from utils import system_info as si
    fake_swaps = (
        "Filename\t\t\t\tType\t\tSize\t\tUsed\t\tPriority\n"
        "/dev/zram0                              partition\t8388604\t\t0\t\t100\n"
        "/dev/nvme0n1p5                          partition\t15728636\t0\t\t-2\n"
    )
    monkeypatch.setattr(si, "_read_file",
                        lambda p: fake_swaps if p == "/proc/swaps" else "")
    devices = si._zram_info()
    assert len(devices) == 1
    assert devices[0]["name"] == "zram0"
    assert devices[0]["size_mb"] > 8000  # ~8GB


def test_zram_absent(monkeypatch):
    from utils import system_info as si
    fake_swaps = "Filename\n/dev/nvme0n1p5 partition 15728636 0 -2\n"
    monkeypatch.setattr(si, "_read_file",
                        lambda p: fake_swaps if p == "/proc/swaps" else "")
    assert si._zram_info() == []


def test_gather_uses_cache(monkeypatch):
    from utils import system_info as si
    call_count = {"n": 0}

    def fake_os_release():
        call_count["n"] += 1
        return {"NAME": "Fedora Linux", "VERSION": "43", "ID": "fedora"}

    monkeypatch.setattr(si, "_os_release", fake_os_release)
    # Mock le reste pour eviter les vrais appels
    monkeypatch.setattr(si, "_kernel_patches", lambda: {"detected": True, "patches": [], "hz": None})
    monkeypatch.setattr(si, "_plasma_version", lambda: None)
    monkeypatch.setattr(si, "_mesa_version", lambda: None)
    monkeypatch.setattr(si, "_lsm_list", lambda: [])
    monkeypatch.setattr(si, "_selinux_state", lambda: None)
    monkeypatch.setattr(si, "_gaming_sysctls_status", lambda: {})
    monkeypatch.setattr(si, "_btrfs_root_info", lambda: {"is_btrfs": False})
    monkeypatch.setattr(si, "_zram_info", lambda: [])

    si.gather()
    si.gather()
    si.gather()
    assert call_count["n"] == 1, "Cache aurait du absorber les 2eme et 3eme appels"


def test_sysctl_check_with_missing_sysctl(monkeypatch):
    """Si sysctl absent du systeme, doit retourner dict avec None."""
    import subprocess

    from utils import system_info as si
    def fake_run(cmd, **kw):
        raise FileNotFoundError("sysctl absent")
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = si._sysctl_check(["vm.swappiness"])
    assert result["vm.swappiness"] is None
