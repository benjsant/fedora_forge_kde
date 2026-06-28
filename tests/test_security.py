"""Tests securite : anti-CSRF (Host + Origin) et lock file global."""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _ensure_root_on_path(monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(ROOT))


@pytest.fixture
def app():
    os.chdir(ROOT)
    from web_app import app as flask_app
    flask_app.config["TESTING"] = True
    return flask_app


# ---------------------------------------------------------------------------
# Host check (anti DNS rebinding)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("host", [
    "evil.example.com",
    "evil.example.com:5000",
    "attacker.local",
    "10.0.0.1:5000",
])
def test_host_check_rejects_foreign_host(app, host):
    c = app.test_client()
    r = c.get("/api/status", headers={"Host": host})
    assert r.status_code == 421, f"Expected 421 for Host={host!r}, got {r.status_code}"


@pytest.mark.parametrize("host", [
    "localhost",
    "localhost:5000",
    "127.0.0.1",
    "127.0.0.1:5000",
])
def test_host_check_accepts_valid_host(app, host):
    c = app.test_client()
    r = c.get("/api/status", headers={"Host": host})
    assert r.status_code == 200, f"Expected 200 for Host={host!r}, got {r.status_code}"


# ---------------------------------------------------------------------------
# Origin/Referer check (anti-CSRF cross-origin)
# ---------------------------------------------------------------------------

def test_post_without_origin_or_referer_rejected(app):
    """Une requete POST sans Origin ni Referer doit etre rejetee (403)."""
    c = app.test_client()
    c.environ_base["HTTP_HOST"] = "localhost:5000"
    r = c.post("/api/profiles/install", json={"profiles": ["base"]})
    assert r.status_code == 403


def test_post_with_foreign_origin_rejected(app):
    """Une requete POST avec Origin externe (CSRF) doit etre rejetee (403)."""
    c = app.test_client()
    c.environ_base["HTTP_HOST"] = "localhost:5000"
    r = c.post(
        "/api/profiles/install",
        json={"profiles": ["base"]},
        headers={"Origin": "https://evil.example.com"},
    )
    assert r.status_code == 403


def test_post_with_localhost_origin_accepted(app):
    """Une requete POST depuis l'UI locale doit passer (puis traitee par la route)."""
    c = app.test_client()
    c.environ_base["HTTP_HOST"] = "localhost:5000"
    # Choix endpoint : preflight (POST simple sans side-effect)
    r = c.post(
        "/api/profiles/preflight",
        json={"profiles": ["base"]},
        headers={"Origin": "http://localhost:5000"},
    )
    # 200 si OK, ou 400 si la route refuse — mais pas 403/421 (= passe le filtre)
    assert r.status_code in (200, 400)


def test_post_with_referer_only_accepted(app):
    """Referer suffit si Origin absent (compat anciens navigateurs)."""
    c = app.test_client()
    c.environ_base["HTTP_HOST"] = "localhost:5000"
    r = c.post(
        "/api/profiles/preflight",
        json={"profiles": ["base"]},
        headers={"Referer": "http://localhost:5000/"},
    )
    assert r.status_code in (200, 400)


def test_get_method_does_not_require_origin(app):
    """GET reste accessible meme sans Origin (pour favoris/refresh navigateur)."""
    c = app.test_client()
    c.environ_base["HTTP_HOST"] = "localhost:5000"
    r = c.get("/api/status")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Lock file global
# ---------------------------------------------------------------------------

def test_lockfile_acquire_release(tmp_path, monkeypatch):
    """Acquisition + release dans un meme process : doit etre idempotent."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    # Re-import pour que _lock_path() prenne le nouveau XDG_RUNTIME_DIR
    import importlib

    from utils import lockfile
    importlib.reload(lockfile)

    p = lockfile.acquire()
    assert p.exists()
    assert int(p.read_text()) == os.getpid()

    # Re-acquire dans le meme PID : OK
    p2 = lockfile.acquire()
    assert p2 == p

    lockfile.release()
    assert not p.exists()


def test_lockfile_blocks_when_pid_alive(tmp_path, monkeypatch):
    """Si un PID vivant detient le lock, acquire doit lever LockfileError."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    import importlib

    from utils import lockfile
    importlib.reload(lockfile)

    # Ecrit un PID etranger vivant (parent de ce process — toujours vivant)
    fake_pid = os.getppid()
    (tmp_path / "fedoraforgekde.lock").write_text(str(fake_pid))

    with pytest.raises(lockfile.LockfileError) as exc:
        lockfile.acquire()
    assert exc.value.pid == fake_pid


def test_lockfile_overrides_stale(tmp_path, monkeypatch):
    """Si le PID stocke n'est plus vivant, acquire doit ecraser le stale lock."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    import importlib

    from utils import lockfile
    importlib.reload(lockfile)

    # PID 99999999 quasi certainement mort
    (tmp_path / "fedoraforgekde.lock").write_text("99999999")
    p = lockfile.acquire()
    assert int(p.read_text()) == os.getpid()
    lockfile.release()


def test_lockfile_release_only_if_ours(tmp_path, monkeypatch):
    """release() ne doit PAS supprimer un lock detenu par un autre process."""
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    import importlib

    from utils import lockfile
    importlib.reload(lockfile)

    foreign_pid = os.getppid()  # vivant, autre que nous
    lock = tmp_path / "fedoraforgekde.lock"
    lock.write_text(str(foreign_pid))

    lockfile.release()
    # Le fichier doit toujours exister (on n'est pas proprietaire)
    assert lock.exists()
    assert lock.read_text().strip() == str(foreign_pid)


def test_lockfile_signal_handler_releases_lock(tmp_path, monkeypatch):
    """install_signal_handlers : recevoir SIGTERM doit retirer le lock.

    On verifie le comportement dans un process enfant pour ne pas tuer
    le runner pytest."""
    import subprocess
    import sys
    import textwrap

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    lock = tmp_path / "fedoraforgekde.lock"

    # Process enfant : acquiert le lock, installe les handlers, attend SIGTERM
    child_code = textwrap.dedent(f"""
        import os, sys, time, signal
        sys.path.insert(0, {str(ROOT)!r})
        os.environ["XDG_RUNTIME_DIR"] = {str(tmp_path)!r}
        from utils import lockfile
        lockfile.acquire()
        lockfile.install_signal_handlers()
        print("ready", flush=True)
        time.sleep(30)
    """)
    proc = subprocess.Popen(
        [sys.executable, "-c", child_code],
        stdout=subprocess.PIPE, text=True,
    )
    # Attend que l'enfant signale qu'il est pret
    assert proc.stdout.readline().strip() == "ready"
    assert lock.exists(), "le lock doit exister tant que l'enfant tourne"

    proc.terminate()  # SIGTERM
    proc.wait(timeout=5)

    assert not lock.exists(), "le lock doit etre retire apres SIGTERM"
