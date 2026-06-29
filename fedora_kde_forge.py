#!/usr/bin/env python3
"""FedoraForgeKDE - Lanceur principal.

Usage:
  fedora_kde_forge.py                          # Lance l'UI web
  fedora_kde_forge.py --profile gaming,dev     # Mode CLI : installe les profils sans Flask
  fedora_kde_forge.py --profile gaming --dry-run
  fedora_kde_forge.py --all                    # Tout installer d'un coup (config complete, sans Flask)
  fedora_kde_forge.py --all --yes              # Idem sans confirmation interactive
  fedora_kde_forge.py --list-profiles
"""

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

URL = "http://localhost:5000"

_RED    = "\033[1;31m"
_GREEN  = "\033[1;32m"
_YELLOW = "\033[1;33m"
_RESET  = "\033[0m"


def _ok(msg):   print(f"{_GREEN}[OK]{_RESET}    {msg}")
def _warn(msg): print(f"{_YELLOW}[WARN]{_RESET}  {msg}")
def _fail(msg): print(f"{_RED}[ERREUR]{_RESET} {msg}")


def check_env():
    """Verifie l'environnement avant le lancement. Retourne False si bloquant."""
    ok = True

    # Python >= 3.10
    if sys.version_info < (3, 10):
        _fail(f"Python 3.10+ requis (version actuelle : {sys.version.split()[0]})")
        ok = False
    else:
        _ok(f"Python {sys.version.split()[0]}")

    # Flask
    try:
        import flask  # noqa: F401
        _ok("Flask disponible")
    except ImportError:
        _fail("Flask non installe. Lancez : pip install flask")
        ok = False

    # Pydantic
    try:
        import pydantic  # noqa: F401
        _ok("Pydantic disponible")
    except ImportError:
        _fail("Pydantic non installe. Lancez : pip install pydantic")
        ok = False

    # Outils systeme (non bloquants, simples avertissements)
    tools = {
        "kwriteconfig6": "requis pour la gestion des parametres KDE Plasma",
        "kreadconfig6":  "requis pour la lecture des parametres KDE Plasma",
        "dnf":           "requis pour l'installation de paquets",
        "flatpak":       "optionnel — pour l'installation de Flatpaks",
        "git":           "optionnel — pour l'installation de themes depuis GitHub",
        "firewall-cmd":  "optionnel — pour la gestion du pare-feu",
    }
    for tool, desc in tools.items():
        found = subprocess.run(["which", tool], capture_output=True).returncode == 0
        if found:
            _ok(tool)
        else:
            _warn(f"{tool} non trouve ({desc})")

    # Dossier configs
    if not (Path(__file__).parent / "configs").is_dir():
        _warn("Dossier configs/ absent — certaines fonctions seront vides")
    else:
        _ok("configs/ present")

    return ok


def open_browser():
    time.sleep(2)
    webbrowser.open(URL)


def _run_cli(slugs, dry_run):
    """Mode CLI : installe directement via scripts/profile_install.py, sans Flask.

    fedora_kde_forge.py est a la racine du projet : Python ajoute son dossier
    automatiquement a sys.path[0], donc `from scripts...` fonctionne sans hack.
    """
    from scripts.profile_install import install_profile
    from utils.profile_loader import get_profile
    from utils.subprocess_utils import dnf_update

    for s in slugs:
        if get_profile(s) is None:
            _fail(f"Profil inconnu : {s}")
            return 1

    if not dry_run:
        dnf_update()

    seen_apt, seen_flatpak, seen_external = set(), set(), set()
    all_ok = True
    for slug in slugs:
        if not install_profile(slug, seen_apt, seen_flatpak, seen_external, dry_run=dry_run):
            all_ok = False
    return 0 if all_ok else 1


def _prime_sudo():
    """S'assure que sudo est utilisable. Retourne False si refus.

    On teste d'abord `sudo -n true` : succes immediat si NOPASSWD est configure
    ou si le cache sudo est encore valide (cas du pilotage a distance sans
    terminal, ou du launcher qui a deja fait `sudo -v`). Sinon, et seulement si
    on dispose d'un terminal, on demande le mot de passe via `sudo -v`."""
    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode == 0:
        return True
    if not sys.stdin.isatty():
        return False
    return subprocess.run(["sudo", "-v"]).returncode == 0


def _run_all(assume_yes=False):
    """Installation complete en CLI : reproduit le bouton 'Installation complete'
    du web (MAJ systeme + paquets DNF + optionnels + externes + nettoyage +
    flatpaks), sans Flask. Les themes ne sont PAS touches (on garde Breeze ;
    installation opt-in via l'UI). Les scripts sont lances via `python -m
    scripts.<name>` (meme chemin que l'UI web, logs streames dans le terminal)."""
    from utils.subprocess_utils import system_update

    # Les themes ne sont PAS installes ici : on garde le theme par defaut (Breeze).
    # L'installation de themes reste opt-in via la section Themes de l'UI.
    steps = [
        ("Paquets DNF", "dnf_install"),
        ("Paquets optionnels", "optional_install"),
        ("Paquets externes", "external_install"),
        ("Nettoyage (remove.json)", "dnf_remove"),
        ("Flatpaks", "flatpak_install"),
    ]
    critical = {"dnf_install"}

    print("\nInstallation complete (config) :")
    print("  - Mise a jour systeme (dnf upgrade)")
    for label, _ in steps:
        print(f"  - {label}")
    print("  ATTENTION : installe/supprime des paquets sur ce systeme.\n")

    if not assume_yes and sys.stdin.isatty():
        ans = input("Continuer ? [o/N] ").strip().lower()
        if ans not in ("o", "oui", "y", "yes"):
            _warn("Annule.")
            return 1

    if not _prime_sudo():
        _fail("Acces sudo requis (sudo -v a echoue).")
        return 1

    root = Path(__file__).parent
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}

    print("\n=== Mise a jour systeme ===")
    if not system_update().success:
        _fail("Mise a jour systeme echouee.")
        return 1
    _ok("Mise a jour systeme terminee.")

    failed = []
    for label, name in steps:
        print(f"\n=== {label} ===")
        rc = subprocess.run(
            [sys.executable, "-m", f"scripts.{name}"], cwd=str(root), env=env
        ).returncode
        if rc != 0:
            failed.append(label)
            if name in critical:
                _fail(f"Etape critique echouee : {label}")
                return 1
            _warn(f"Etape en erreur (non critique) : {label}")

    if failed:
        _warn(f"Installation complete terminee avec erreurs : {', '.join(failed)}")
        return 1
    _ok("Installation complete terminee.")
    return 0


def _list_profiles():
    from utils.profile_loader import load_all_profiles
    profiles = load_all_profiles()
    print("Profils disponibles :")
    for slug, p in profiles.items():
        print(f"  {slug:12s} - {p.name}: {p.description}")
    return 0


def main():
    args = sys.argv[1:]

    if "--list-profiles" in args or "-l" in args:
        return _list_profiles()

    # Mode CLI : --all (installation complete config, sans Flask)
    if "--all" in args:
        assume_yes = "--yes" in args or "-y" in args
        return _run_all(assume_yes=assume_yes)

    # Mode CLI : --profile <slug>[,<slug>...]
    if "--profile" in args:
        idx = args.index("--profile")
        if idx + 1 >= len(args):
            _fail("--profile attend un argument : --profile gaming,dev")
            return 1
        slugs = [s.strip() for s in args[idx + 1].split(",") if s.strip()]
        if not slugs:
            _fail("Aucun profil specifie.")
            return 1
        dry_run = "--dry-run" in args
        return _run_cli(slugs, dry_run)

    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    # Mode UI web par defaut
    web_app_path = Path(__file__).parent / "web_app.py"
    if not web_app_path.exists():
        _fail(f"web_app.py introuvable : {web_app_path}")
        return 1

    print()
    print("=" * 55)
    print("  FedoraForgeKDE — Verification de l'environnement")
    print("=" * 55)
    if not check_env():
        print()
        _fail("Des dependances manquent. Corrigez les erreurs ci-dessus.")
        return 1

    print()
    print("=" * 55)
    print("  FedoraForgeKDE — Lancement")
    print("=" * 55)
    print(f"  URL   : {URL}")
    print("  Arret : CTRL+C")
    print("=" * 55)
    print()

    threading.Thread(target=open_browser, daemon=True).start()

    try:
        subprocess.run([sys.executable, str(web_app_path)])
    except KeyboardInterrupt:
        print("\n[OK] FedoraForgeKDE arrete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
