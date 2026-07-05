"""Routes /api/profiles."""
import threading
import time

from flask import Blueprint, jsonify, request

from routes.fedora_wizards import _rpmfusion_status
from routes.shared import (
    current_task,
    log_error,
    log_exc,
    log_info,
    log_success,
    log_warn,
    task_lock,
    update_task_status,
)
from scripts.profile_install import install_profile
from utils import (
    ACTION_DNF_INSTALL,
    ACTION_DNF_REMOVE,
    ACTION_EXTERNAL_INSTALL,
    ACTION_FLATPAK_INSTALL,
    check_flatpak_installed,
    check_package_installed,
    dnf_install,
    dnf_remove,
    dnf_update,
    flatpak_install,
    get_state_manager,
    run_command,
    timeshift_available,
    timeshift_create_snapshot,
)
from utils.profile_loader import get_profile, load_all_profiles
from utils.sandbox import looks_dangerous

bp = Blueprint("profiles", __name__)

# Paquets presents UNIQUEMENT dans RPM Fusion (absents de Fedora vanilla). Sur
# Nobara ils viennent des depots curatos, mais sur Fedora ils echouent tant que
# RPM Fusion n'est pas active. Le preflight previent l'utilisateur.
_RPMFUSION_ONLY = {
    "steam", "vlc", "HandBrake-gui",
}

PROFILE_ORDER = ["base", "office", "communication", "gaming", "htpc", "handheld", "dev", "multimedia", "docker", "distrobox", "amd", "nvidia", "privacy", "vpn", "browsers", "system"]

_gpu_cache = None
_profiles_cache = {"data": None, "ts": 0}
PROFILES_CACHE_TTL = 60


def _detect_gpu():
    global _gpu_cache
    if _gpu_cache is not None:
        return _gpu_cache
    try:
        import subprocess
        out = subprocess.run(["lspci"], capture_output=True, text=True, timeout=5).stdout.lower()
        if "nvidia" in out:
            _gpu_cache = "nvidia"
        elif "amd" in out or "radeon" in out:
            _gpu_cache = "amd"
        else:
            _gpu_cache = "unknown"
    except Exception:
        _gpu_cache = "unknown"
    return _gpu_cache


def _load_profiles():
    now = time.time()
    if _profiles_cache["data"] and now - _profiles_cache["ts"] < PROFILES_CACHE_TTL:
        return _profiles_cache["data"]
    data = load_all_profiles()
    _profiles_cache["data"] = data
    _profiles_cache["ts"] = now
    return data


@bp.route('/api/profiles')
def list_profiles():
    try:
        profiles = _load_profiles()
        gpu = _detect_gpu()

        def sort_key(slug):
            try:
                return PROFILE_ORDER.index(slug)
            except ValueError:
                return len(PROFILE_ORDER)

        _gpu_opposite = {"amd": "nvidia", "nvidia": "amd"}.get(gpu)

        result = {}
        for slug in sorted(profiles.keys(), key=sort_key):
            p = profiles[slug]
            result[slug] = {
                "name": p.name,
                "description": p.description,
                "icon": p.icon,
                "suggested": slug == gpu,
                "locked": slug == _gpu_opposite,
                "counts": {
                    "apt": len(p.apt), "flatpak": len(p.flatpak),
                    "external": len(p.external), "remove": len(p.remove),
                    "total": p.total_packages,
                },
            }
        return jsonify({"success": True, "profiles": result, "gpu": gpu})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route('/api/profiles/<slug>')
def get_profile_detail(slug):
    profile = get_profile(slug)
    if profile is None:
        return jsonify({"success": False, "error": f"Profil '{slug}' introuvable"}), 404
    return jsonify({"success": True, "profile": profile.model_dump()})


@bp.route('/api/profiles/install', methods=['POST'])
def install_profiles():
    data = request.get_json(silent=True) or {}
    slugs = data.get("profiles", [])
    want_snapshot = bool(data.get("snapshot", False))
    if not slugs or not isinstance(slugs, list):
        return jsonify({"success": False, "error": "Liste 'profiles' requise"}), 400
    for s in slugs:
        if get_profile(s) is None:
            return jsonify({"success": False, "error": f"Profil inconnu : {s}"}), 404

    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        current_task.update(running=True, name=f"Profils : {', '.join(slugs)}", progress=0)

    def run():
        try:
            total = len(slugs)
            failed = []
            seen_apt, seen_flatpak, seen_external = set(), set(), set()
            if want_snapshot and timeshift_available():
                log_info("Snapshot timeshift avant installation...")
                update_task_status("Snapshot timeshift", True, 1)
                snap = timeshift_create_snapshot(f"FedoraForgeKDE: {', '.join(slugs)}")
                if snap.success:
                    log_success("Snapshot timeshift cree.")
                else:
                    log_warn("Snapshot timeshift echoue, installation continue.")
            elif want_snapshot:
                log_warn("Timeshift non disponible, snapshot ignore.")
            log_info("dnf check-update avant installation des profils...")
            dnf_update()
            for idx, slug in enumerate(slugs):
                update_task_status(f"Profil {slug} ({idx+1}/{total})", True, int((idx / total) * 100))
                log_info(f"=== Profil : {slug} ({idx+1}/{total}) ===")
                if not install_profile(slug, seen_apt, seen_flatpak, seen_external):
                    failed.append(slug)
            if failed:
                update_task_status("Profils : erreurs", False, 100)
                log_warn(f"Profils en erreur : {', '.join(failed)}")
            else:
                update_task_status("Profils installes", False, 100)
                log_success(f"{total} profil(s) installe(s)")
        except Exception as e:
            log_exc(f"Erreur installation profils : {e}")
            update_task_status("Installation echouee", False, 100)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": f"Installation : {', '.join(slugs)}"})


@bp.route('/api/profiles/dry-run', methods=['POST'])
def dry_run_profiles():
    data = request.get_json(silent=True) or {}
    slugs = data.get("profiles", [])
    if not slugs or not isinstance(slugs, list):
        return jsonify({"success": False, "error": "Liste 'profiles' requise"}), 400

    seen_apt, seen_flatpak, seen_external = set(), set(), set()
    result = {}

    for slug in slugs:
        profile = get_profile(slug)
        if profile is None:
            continue
        entry = {"apt": [], "flatpak": [], "external": [], "remove": []}

        for pkg in profile.apt:
            st = "duplicate" if pkg.name in seen_apt else ("installed" if check_package_installed(pkg.name) else "to_install")
            entry["apt"].append({"name": pkg.name, "description": pkg.description, "status": st})
            seen_apt.add(pkg.name)

        for fp in profile.flatpak:
            st = "duplicate" if fp.app in seen_flatpak else ("installed" if check_flatpak_installed(fp.app) else "to_install")
            entry["flatpak"].append({"app": fp.app, "description": fp.description, "status": st})
            seen_flatpak.add(fp.app)

        for ext in profile.external:
            st = "duplicate" if ext.name in seen_external else "to_install"
            entry["external"].append({"name": ext.name, "description": ext.description, "status": st})
            seen_external.add(ext.name)

        for pkg in profile.remove:
            st = "installed" if check_package_installed(pkg.name) else "absent"
            entry["remove"].append({"name": pkg.name, "description": pkg.description, "status": st})

        result[slug] = entry

    return jsonify({"success": True, "dry_run": result})


@bp.route('/api/profiles/install-custom', methods=['POST'])
def install_custom():
    """Installe une selection manuelle de paquets issus d'un profil."""
    data = request.get_json(silent=True) or {}
    apt_pkgs     = data.get("apt", [])
    flatpak_apps = data.get("flatpak", [])
    external_pkgs = data.get("external", [])
    remove_pkgs  = data.get("remove", [])

    if not any([apt_pkgs, flatpak_apps, external_pkgs, remove_pkgs]):
        return jsonify({"success": False, "error": "Aucun paquet selectionne"}), 400

    with task_lock:
        if current_task["running"]:
            return jsonify({"success": False, "error": "Tache en cours"}), 409
        total = len(apt_pkgs) + len(flatpak_apps) + len(external_pkgs) + len(remove_pkgs)
        current_task.update(running=True, name=f"Installation personnalisee ({total} paquets)", progress=0)

    def run():
        state = get_state_manager()
        had_errors = False
        done = 0

        try:
            log_info("dnf check-update avant installation...")
            dnf_update()

            for pkg in apt_pkgs:
                name, desc = pkg.get("name", ""), pkg.get("description", "")
                if not name:
                    continue
                if check_package_installed(name):
                    log_warn(f"{name} deja installe, ignore.")
                else:
                    log_info(f"DNF : {name}")
                    result = dnf_install([name])
                    state.record(ACTION_DNF_INSTALL, name, result.success,
                                 rollback_cmd=["sudo", "dnf", "remove", "-y", name],
                                 metadata={"description": desc})
                    if not result.success:
                        log_error(f"Echec : {name}")
                        had_errors = True
                done += 1
                update_task_status(f"Installation ({done}/{total})", True, 10 + int((done / total) * 80))

            for fp in flatpak_apps:
                app, desc = fp.get("app", ""), fp.get("description", "")
                if not app:
                    continue
                if check_flatpak_installed(app):
                    log_warn(f"{app} deja installe, ignore.")
                else:
                    log_info(f"Flatpak : {app}")
                    result = flatpak_install(app)
                    state.record(ACTION_FLATPAK_INSTALL, app, result.success,
                                 rollback_cmd=["flatpak", "uninstall", "-y", app],
                                 metadata={"description": desc})
                    if not result.success:
                        log_error(f"Echec : {app}")
                        had_errors = True
                done += 1
                update_task_status(f"Installation ({done}/{total})", True, 10 + int((done / total) * 80))

            for ext in external_pkgs:
                name, desc, cmd = ext.get("name", ""), ext.get("description", ""), ext.get("cmd", "")
                if not name or not cmd:
                    continue
                log_info(f"Externe : {name}")
                log_info(f"[AUDIT] Commande : {cmd}")
                for finding in looks_dangerous(cmd):
                    log_warn(f"[AUDIT] {name} : pattern suspect : {finding}")
                result = run_command(["bash", "-c", cmd])
                state.record(ACTION_EXTERNAL_INSTALL, name, result.success,
                             rollback_cmd=[], metadata={"description": desc, "manual_rollback": True})
                if not result.success:
                    log_error(f"Echec : {name}")
                    had_errors = True
                done += 1
                update_task_status(f"Installation ({done}/{total})", True, 10 + int((done / total) * 80))

            for pkg in remove_pkgs:
                name, desc = pkg.get("name", ""), pkg.get("description", "")
                if not name:
                    continue
                if check_package_installed(name):
                    log_info(f"Suppression : {name}")
                    result = dnf_remove([name])
                    state.record(ACTION_DNF_REMOVE, name, result.success,
                                 rollback_cmd=["sudo", "dnf", "install", "-y", name],
                                 metadata={"description": desc})
                    if not result.success:
                        log_error(f"Echec suppression : {name}")
                        had_errors = True
                done += 1
                update_task_status(f"Installation ({done}/{total})", True, 10 + int((done / total) * 80))

            if had_errors:
                update_task_status("Termine avec erreurs", False, 100)
                log_warn("Installation personnalisee terminee avec erreurs.")
            else:
                update_task_status("Installation terminee", False, 100)
                log_success("Installation personnalisee terminee.")
        except Exception as e:
            log_exc(f"Erreur installation personnalisee : {e}")
            update_task_status("Erreur", False, 0)

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"success": True, "message": f"Installation de {total} paquet(s) lancee"})


@bp.route('/api/profiles/preflight', methods=['POST'])
def preflight():
    """Analyse statique des profils selectionnes : compte les paquets a installer,
    detecte les conflits (un profil installe ce qu'un autre supprime) et liste
    les paquets externes (commandes bash) qui requierent une attention.
    """
    data = request.get_json(silent=True) or {}
    slugs = data.get("profiles", [])
    if not slugs or not isinstance(slugs, list):
        return jsonify({"success": False, "error": "Liste 'profiles' requise"}), 400

    to_install_apt = {}
    to_install_flatpak = {}
    to_install_external = []
    to_remove = {}
    apt_already = set()
    flatpak_already = set()

    for slug in slugs:
        profile = get_profile(slug)
        if profile is None:
            continue
        for pkg in profile.apt:
            if check_package_installed(pkg.name):
                apt_already.add(pkg.name)
            else:
                to_install_apt.setdefault(pkg.name, []).append(slug)
        for fp in profile.flatpak:
            if check_flatpak_installed(fp.app):
                flatpak_already.add(fp.app)
            else:
                to_install_flatpak.setdefault(fp.app, []).append(slug)
        for ext in profile.external:
            to_install_external.append({"name": ext.name, "profile": slug})
        for pkg in profile.remove:
            if check_package_installed(pkg.name):
                to_remove.setdefault(pkg.name, []).append(slug)

    # Conflits : un paquet est a la fois dans install et dans remove
    conflicts = []
    for pkg, removers in to_remove.items():
        if pkg in to_install_apt:
            conflicts.append({
                "package": pkg,
                "installed_by": to_install_apt[pkg],
                "removed_by": removers,
            })

    gpu = _detect_gpu()
    warnings = []
    if "amd" in slugs and gpu == "nvidia":
        warnings.append("Profil AMD selectionne mais GPU NVIDIA detecte — risque de conflit.")
    if "nvidia" in slugs and gpu == "amd":
        warnings.append("Profil NVIDIA selectionne mais GPU AMD detecte — risque de conflit.")

    # Garde RPM Fusion : certains paquets (steam, vlc, kodi...) n'existent pas
    # dans Fedora vanilla. Si presents et RPM Fusion inactif -> avertir.
    rpmfusion_needed = sorted(p for p in to_install_apt if p in _RPMFUSION_ONLY)
    if rpmfusion_needed and not _rpmfusion_status()["enabled"]:
        warnings.append(
            "Paquets RPM Fusion requis (" + ", ".join(rpmfusion_needed) + ") : "
            "activez RPM Fusion via le wizard Fedora avant l'installation, sinon ils echoueront."
        )

    return jsonify({
        "success": True,
        "summary": {
            "apt_to_install": len(to_install_apt),
            "apt_already_installed": len(apt_already),
            "flatpak_to_install": len(to_install_flatpak),
            "flatpak_already_installed": len(flatpak_already),
            "external_count": len(to_install_external),
            "remove_count": len(to_remove),
        },
        "apt_to_install": [{"name": n, "profiles": p} for n, p in to_install_apt.items()],
        "flatpak_to_install": [{"app": n, "profiles": p} for n, p in to_install_flatpak.items()],
        "external": to_install_external,
        "remove": [{"name": n, "profiles": p} for n, p in to_remove.items()],
        "conflicts": conflicts,
        "warnings": warnings,
        "gpu": gpu,
    })


@bp.route('/api/profiles/export', methods=['POST'])
def export_selection():
    data = request.get_json(silent=True) or {}
    return jsonify({"success": True, "export": {"profiles": data.get("profiles", [])}})


@bp.route('/api/profiles/import', methods=['POST'])
def import_selection():
    data = request.get_json(silent=True) or {}
    slugs = data.get("profiles", [])
    valid, invalid = [], []
    for s in slugs:
        (valid if get_profile(s) is not None else invalid).append(s)
    return jsonify({"success": True, "profiles": valid, "invalid": invalid})
