#!/usr/bin/env python3
"""Wrappers subprocess securises (pas de shell=True)."""

import subprocess
import sys


class CommandResult:
    """Resultat d'une commande."""
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.success = returncode == 0

    def __bool__(self):
        return self.success


def run_command(cmd, check=False, capture_output=False, cwd=None, timeout=None, env=None):
    """Execute une commande (liste d'args, pas de shell)."""
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture_output, text=True,
            cwd=str(cwd) if cwd else None, timeout=timeout, env=env
        )
        return CommandResult(
            result.returncode,
            result.stdout if capture_output else "",
            result.stderr if capture_output else ""
        )
    except subprocess.CalledProcessError as e:
        return CommandResult(e.returncode, e.stdout or "", e.stderr or "")
    except subprocess.TimeoutExpired:
        return CommandResult(-1, "", "Timeout")
    except FileNotFoundError as e:
        return CommandResult(-1, "", f"Commande introuvable : {e}")


def run_sudo_command(cmd, check=False, capture_output=False, timeout=None):
    """Execute avec sudo -n (echoue si mot de passe requis)."""
    return run_command(["sudo", "-n"] + cmd, check=check,
                       capture_output=capture_output, timeout=timeout)


def check_package_installed(package_name):
    """Verifie si un paquet RPM est installe (via rpm -q)."""
    result = run_command(
        ["rpm", "-q", package_name],
        capture_output=True
    )
    return result.success


def check_command_exists(command):
    """Verifie si une commande existe dans le PATH."""
    return run_command(["which", command], capture_output=True).success


def dnf_install(packages, assume_yes=True):
    cmd = ["dnf", "install"]
    if assume_yes:
        cmd.append("-y")
    cmd.extend(packages)
    return run_sudo_command(cmd)


def dnf_remove(packages, assume_yes=True):
    cmd = ["dnf", "remove"]
    if assume_yes:
        cmd.append("-y")
    cmd.extend(packages)
    return run_sudo_command(cmd)


def dnf_update():
    """dnf check-update : code 0 = pas de MAJ, 100 = MAJ disponibles (normal), autre = erreur."""
    result = run_sudo_command(["dnf", "check-update"], capture_output=True)
    if result.returncode == 100:
        result.returncode = 0
        result.success = True
    return result


def dnf_upgrade(assume_yes=True):
    cmd = ["dnf", "upgrade"]
    if assume_yes:
        cmd.append("-y")
    return run_sudo_command(cmd)


def system_update(assume_yes=True):
    """Mise a jour systeme via DNF uniquement (dnf check-update + dnf upgrade).

    Pas de fallback nobara-updater : sur Fedora vanilla, DNF est l'unique
    gestionnaire et les binaires nobara-* n'existent pas dans le PATH."""
    check_result = dnf_update()
    if not check_result.success:
        return check_result
    return dnf_upgrade(assume_yes=assume_yes)


def flatpak_install(app_id, remote="flathub", assume_yes=True):
    cmd = ["flatpak", "install"]
    if assume_yes:
        cmd.append("-y")
    cmd.extend([remote, app_id])
    return run_command(cmd)


def flatpak_list():
    """Liste les applis Flatpak installees."""
    result = run_command(["flatpak", "list", "--app", "--columns=application"],
                         capture_output=True)
    if result.success:
        return [line.strip() for line in result.stdout.split('\n') if line.strip()]
    return []


def check_flatpak_installed(app_id):
    """Verifie si un Flatpak est installe (via flatpak info)."""
    return run_command(["flatpak", "info", app_id], capture_output=True).success


def git_clone(repo_url, target_dir, depth=None):
    cmd = ["git", "clone"]
    if depth:
        cmd.extend(["--depth", str(depth)])
    cmd.extend([repo_url, str(target_dir)])
    return run_command(cmd)


def timeshift_available():
    """True si timeshift est dans le PATH ET si le snapshot mode est configure."""
    if not check_command_exists("timeshift"):
        return False
    # timeshift necessite une config initiale ; on essaie un --list dry pour valider
    r = run_command(["sudo", "-n", "timeshift", "--list"], capture_output=True, timeout=10)
    return r.success


def timeshift_create_snapshot(comment="FedoraForgeKDE pre-install"):
    """Cree un snapshot timeshift en mode tag D (on-demand). Best-effort.
    Retourne CommandResult. N'echoue PAS l'install si le snapshot echoue."""
    cmd = ["sudo", "-n", "timeshift", "--create", "--comments", comment, "--tags", "D"]
    return run_command(cmd, timeout=600)


def run_bash_script(script_path, args=None, cwd=None):
    cmd = ["bash", str(script_path)]
    if args:
        cmd.extend(args)
    return run_command(cmd, cwd=cwd)


def run_python_script(script_path, args=None, cwd=None):
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args)
    return run_command(cmd, cwd=cwd)
