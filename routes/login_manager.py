"""Routes /api/sddm - configuration de l'ecran de connexion.

Cible Plasma Login Manager (plasmalogin) — DM par defaut de Nobara/Fedora KDE 42+.
Si SDDM est detecte a la place, un warning est renvoye a l'UI (pas de gestion legacy).

Les URLs gardent le prefixe /api/sddm/* pour compatibilite front.
"""
import subprocess
from pathlib import Path

from flask import Blueprint, jsonify

from routes.kde_settings import _kde_get
from routes.shared import log_success, log_warn

bp = Blueprint("login_manager", __name__)

_PLASMALOGIN_CONF_DIR = Path("/etc/plasmalogin.conf.d")
_PLASMALOGIN_CONF = _PLASMALOGIN_CONF_DIR / "fedoraforgekde.conf"
_PLASMALOGIN_THEMES_DIR = Path("/usr/share/plasmalogin/themes")

_PLASMALOGIN_SERVICE = "plasmalogin.service"
_SDDM_SERVICE = "sddm.service"


def _service_active(name):
    try:
        r = subprocess.run(["systemctl", "is-active", name],
                           capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def _detect_dm():
    """Retourne ('plasmalogin'|'sddm'|None, warning_msg)."""
    if _service_active(_PLASMALOGIN_SERVICE):
        return "plasmalogin", ""
    if _service_active(_SDDM_SERVICE):
        return "sddm", (
            "SDDM detecte. Nobara/Fedora KDE 42+ utilise plasma-login-manager. "
            "Migration recommandee : sudo dnf install plasma-login-manager "
            "&& sudo systemctl disable --now sddm && sudo systemctl enable --now plasmalogin"
        )
    return None, "Aucun display manager pris en charge n'est actif (plasmalogin attendu)."


def _read_plasmalogin_conf():
    """Parse /etc/plasmalogin.conf.d/*.conf en (raw_dict, ui_dict).

    raw_dict garde toutes les cles au format 'Section/Cle'.
    ui_dict expose les cles attendues par le front : theme/cursor_theme/numlock.
    """
    raw = {}
    if _PLASMALOGIN_CONF_DIR.exists():
        for conf_file in sorted(_PLASMALOGIN_CONF_DIR.glob("*.conf")):
            try:
                content = conf_file.read_text()
            except Exception:
                continue
            current_section = ""
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("[") and line.endswith("]"):
                    current_section = line[1:-1]
                elif "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    raw[f"{current_section}/{key.strip()}"] = val.strip()

    ui = {
        "theme":         raw.get("Theme/Current", ""),
        "cursor_theme":  raw.get("Theme/CursorTheme", ""),
        "cursor_size":   raw.get("Theme/CursorSize", ""),
        "numlock":       raw.get("General/Numlock", ""),
    }
    return raw, ui


def _write_plasmalogin_conf(settings):
    """Ecrit la configuration plasma-login-manager."""
    sections = {}
    for key, val in settings.items():
        if "/" in key:
            section, param = key.split("/", 1)
        else:
            section, param = "Theme", key
        sections.setdefault(section, {})[param] = val

    lines = ["# Configuration plasma-login-manager generee par FedoraForgeKDE", ""]
    for section, params in sections.items():
        lines.append(f"[{section}]")
        for key, val in params.items():
            lines.append(f"{key}={val}")
        lines.append("")

    content = "\n".join(lines)
    tmp = "/tmp/fedoraforgekde_plasmalogin.conf"
    Path(tmp).write_text(content)

    subprocess.run(
        ["sudo", "-n", "mkdir", "-p", str(_PLASMALOGIN_CONF_DIR)],
        capture_output=True, timeout=5
    )
    result = subprocess.run(
        ["sudo", "-n", "cp", tmp, str(_PLASMALOGIN_CONF)],
        capture_output=True, text=True, timeout=5
    )
    return result.returncode == 0, result.stderr.strip()


def _list_plasmalogin_themes():
    """Liste les themes plasma-login-manager disponibles."""
    if not _PLASMALOGIN_THEMES_DIR.exists():
        return []
    return sorted([
        d.name for d in _PLASMALOGIN_THEMES_DIR.iterdir()
        if d.is_dir() and (d / "metadata.desktop").exists()
    ])


@bp.route('/api/sddm/status')
def login_manager_status():
    """Lit la configuration actuelle du display manager."""
    dm, warning = _detect_dm()
    if dm != "plasmalogin":
        return jsonify({
            "success": False,
            "dm": dm,
            "warning": warning,
            "current": {},
            "themes": [],
        })
    try:
        _, ui_current = _read_plasmalogin_conf()
        themes = _list_plasmalogin_themes()
        return jsonify({
            "success": True,
            "dm": "plasmalogin",
            "current": ui_current,
            "themes": themes,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "dm": dm}), 500


@bp.route('/api/sddm/sync', methods=['POST'])
def login_manager_sync():
    """Synchronise plasma-login-manager depuis les reglages du bureau courant."""
    dm, warning = _detect_dm()
    if dm != "plasmalogin":
        return jsonify({
            "success": False,
            "dm": dm,
            "warnings": [warning] if warning else [],
            "applied": [],
            "errors": ["plasma-login-manager non actif"],
        })

    applied, errors, warnings = [], [], []

    cursor_theme = _kde_get("kcminputrc", "Mouse", "cursorTheme")
    cursor_size = _kde_get("kcminputrc", "Mouse", "cursorSize")

    settings = {}
    if cursor_theme:
        settings["Theme/CursorTheme"] = cursor_theme
        applied.append(f"CursorTheme = {cursor_theme}")
    if cursor_size:
        settings["Theme/CursorSize"] = cursor_size
        applied.append(f"CursorSize = {cursor_size}")

    settings["General/Numlock"] = "on"
    applied.append("Numlock = on")

    if settings:
        ok, err = _write_plasmalogin_conf(settings)
        if ok:
            log_success(f"plasma-login synchronise ({len(applied)} parametres)")
        else:
            log_warn(f"Echec ecriture plasma-login : {err}")
            errors.append("ecriture config")
    else:
        warnings.append("Aucun parametre a synchroniser")

    return jsonify({
        "success": len(applied) > 0 and not errors,
        "dm": "plasmalogin",
        "applied": applied,
        "errors": errors,
        "warnings": warnings,
    })
