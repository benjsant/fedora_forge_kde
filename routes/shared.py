"""Etat partage entre les blueprints : task, logs, helpers."""
import contextlib
import logging
import os
import queue
import subprocess
import sys
import threading
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

log_queue = queue.Queue(maxsize=1000)
current_task = {"running": False, "name": "", "progress": 0}
task_lock = threading.Lock()

_current_process = None
_process_lock = threading.Lock()

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# Timeout des scripts d'installation, en secondes.
# Defaut : 2h (une grosse mise a jour DNF + profils peut depasser 30 min).
# Surchargeable via env var FEDORAFORGEKDE_SCRIPT_TIMEOUT.
def _resolve_script_timeout():
    raw = os.environ.get("FEDORAFORGEKDE_SCRIPT_TIMEOUT", "7200")
    try:
        v = int(raw)
        return v if v > 0 else 7200
    except (ValueError, TypeError):
        return 7200

SCRIPT_TIMEOUT = _resolve_script_timeout()


class QueueHandler(logging.Handler):
    def emit(self, record):
        with contextlib.suppress(queue.Full):
            log_queue.put_nowait(self.format(record))


# Rotation : 5 Mo par fichier, 3 sauvegardes => total max 20 Mo sur disque.
# Evite que logs/fedoraforgekde.log atteigne plusieurs Go sur une longue duree
# d'utilisation (chaque install/profile peut emettre des dizaines de lignes).
_LOG_FILE = LOG_DIR / "fedoraforgekde.log"
_file_handler = RotatingFileHandler(_LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[_file_handler, QueueHandler()],
)
logger = logging.getLogger("fedoraforgekde")

# Logger fichier seul (propagate=False) : pour ecrire les tracebacks multi-lignes
# SANS les envoyer en SSE, ou les '\n' casseraient le framing 'data:' du flux.
_file_logger = logging.getLogger("fedoraforgekde.file")
_file_logger.propagate = False
_file_logger.setLevel(logging.INFO)
_file_logger.addHandler(_file_handler)


def log_info(msg):    logger.info(msg)
def log_success(msg): logger.info(f"[OK] {msg}")
def log_warn(msg):    logger.warning(f"[WARN] {msg}")
def log_error(msg):   logger.error(f"[ERROR] {msg}")


def log_exc(msg):
    """Comme log_error mais ajoute la traceback complete dans le fichier de log.

    Le message court part en SSE + fichier ; la traceback ne va que dans le
    fichier (logs/fedoraforgekde.log), pour le diagnostic, sans polluer l'UI ni
    casser le flux SSE. A utiliser dans les `except` qui sinon avaleraient l'erreur."""
    log_error(msg)
    tb = traceback.format_exc()
    if tb and tb.strip() and tb.strip() != "NoneType: None":
        _file_logger.error("Traceback:\n%s", tb.rstrip())


def notify_desktop(title, message=""):
    with contextlib.suppress(Exception):
        subprocess.run(
            ["notify-send", "-a", "FedoraForgeKDE", "-i", "dialog-information", title, message],
            capture_output=True, timeout=3
        )


def update_task_status(name, running, progress=0):
    with task_lock:
        was_running = current_task["running"]
        current_task["name"] = name
        current_task["running"] = running
        current_task["progress"] = progress
    if was_running and not running and progress == 100:
        notify_desktop("Termine", name)


def set_current_process(proc):
    global _current_process
    with _process_lock:
        _current_process = proc


def cancel_current_task():
    """Tue le processus en cours."""
    global _current_process
    with _process_lock:
        if _current_process and _current_process.poll() is None:
            _current_process.kill()
            _current_process = None
            return True
        return False


def run_script(script_name):
    script_path = Path("scripts") / f"{script_name}.py"
    if not script_path.exists():
        script_path = Path("scripts") / script_name
        if not script_path.exists():
            log_error(f"Script introuvable : {script_name}")
            return False
    try:
        log_info(f"Lancement de {script_name}...")
        # Pour les scripts Python, on les invoque via `python -m scripts.<name>` :
        # Python charge alors scripts/__init__.py (qui configure sys.path) avant
        # d'executer le module, ce qui evite tout hack sys.path.insert duplicate.
        if script_path.suffix == ".py":
            module_name = f"scripts.{script_path.stem}"
            cmd = [sys.executable, "-m", module_name]
        else:
            cmd = ["bash", str(script_path)]

        # Ajoute la racine du projet au PYTHONPATH (double securite : pour les
        # scripts bash et au cas ou `-m` serait court-circuite).
        project_root = Path(__file__).resolve().parent.parent
        existing_pp = os.environ.get("PYTHONPATH", "")
        new_pp = str(project_root) + (os.pathsep + existing_pp if existing_pp else "")
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONPATH": new_pp}
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, env=env
        )
        set_current_process(process)
        for line in process.stdout:
            line = line.rstrip('\n')
            if line.strip():
                log_info(line)
        process.wait(timeout=SCRIPT_TIMEOUT)
        set_current_process(None)
        if process.returncode == 0:
            log_success(f"Termine : {script_name}")
            return True
        if process.returncode is not None and process.returncode < 0:
            log_warn(f"Annule : {script_name}")
            return False
        log_error(f"Echec : {script_name} (code {process.returncode})")
        return False
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        set_current_process(None)
        log_error(f"Timeout : {script_name} (>{SCRIPT_TIMEOUT}s)")
        return False
    except Exception as e:
        set_current_process(None)
        log_error(f"Erreur {script_name} : {e}")
        return False
