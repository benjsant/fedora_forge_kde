"""Routes /api/fedora - wizards specifiques a Fedora vanilla.

Contrairement a Nobara qui pre-configure RPM Fusion, les codecs et les pilotes,
Fedora KDE Spin part d'une base "vanilla". Ces wizards inline remplacent les
outils Nobara (nobara-codec-wizard, nobara-driver-manager) absents sur Fedora.

Wizards implementes :
- RPM Fusion (free + nonfree) : prerequis de quasiment tous les autres
  (NVIDIA akmod, codecs multimedia, mesa-*-freeworld).
- Codecs multimedia : ffmpeg complet + plugins GStreamer (necessite RPM Fusion).
"""
import subprocess

from flask import Blueprint, jsonify

from routes.shared import log_error, log_info, log_success, log_warn, set_current_process
from utils.system_info import _selinux_state

bp = Blueprint("fedora_wizards", __name__)

# Paquets "release" de RPM Fusion. Une fois installes, ils deposent les
# definitions de depots free/nonfree dans /etc/yum.repos.d/.
_RPMFUSION_FREE_PKG = "rpmfusion-free-release"
_RPMFUSION_NONFREE_PKG = "rpmfusion-nonfree-release"

# Timeout de l'activation : telechargement metadata + 2 petits RPM. Large marge.
_ENABLE_TIMEOUT = 300

# Codecs multimedia. ffmpeg-libs (RPM Fusion) remplace ffmpeg-free-libs de Fedora :
# d'ou --allowerasing a l'install. Les plugins GStreamer couvrent h264/h265/AAC/etc.
_CODEC_PACKAGES = [
    "ffmpeg-libs",
    "gstreamer1-plugins-bad-free",
    "gstreamer1-plugins-bad-free-extras",
    "gstreamer1-plugins-good",
    "gstreamer1-plugins-good-extras",
    "gstreamer1-plugins-base",
    "gstreamer1-plugin-libav",
    "gstreamer1-plugins-ugly",
]

# Paquets temoins : si tous presents, on considere les codecs installes. ffmpeg-libs
# atteste le swap vers la variante non libre, libav + ugly attestent les plugins.
_CODEC_WITNESSES = ["ffmpeg-libs", "gstreamer1-plugin-libav", "gstreamer1-plugins-ugly"]

# Codecs : install + 2 group upgrade, telechargement potentiellement lourd.
_CODEC_TIMEOUT = 1800

# Pilote NVIDIA proprietaire (RPM Fusion nonfree). akmod recompile le module a
# chaque MAJ kernel. cuda apporte le support calcul + encodage NVENC.
_NVIDIA_PACKAGES = ["akmod-nvidia", "xorg-x11-drv-nvidia-cuda"]
_NVIDIA_WITNESS = "akmod-nvidia"
# akmod compile le module au premier boot : laisser large.
_NVIDIA_TIMEOUT = 1800

# Flathub : URL du depot complet (non filtre).
_FLATHUB_URL = "https://flathub.org/repo/flathub.flatpakrepo"
_FLATPAK_TIMEOUT = 120


def _fedora_version():
    """Numero de version Fedora via `rpm -E %fedora`. None si indetectable."""
    try:
        r = subprocess.run(["rpm", "-E", "%fedora"], capture_output=True, text=True, timeout=5)
        v = r.stdout.strip()
        return v if v.isdigit() else None
    except Exception:
        return None


def _repo_enabled(repo_id):
    """True si le depot `repo_id` est present ET active (dnf repolist --enabled)."""
    try:
        r = subprocess.run(
            ["dnf", "repolist", "--enabled", repo_id],
            capture_output=True, text=True, timeout=15,
        )
        # dnf liste le repo dans stdout uniquement s'il est connu et active.
        return repo_id in r.stdout
    except Exception:
        return False


def _pkg_installed(pkg):
    try:
        return subprocess.run(["rpm", "-q", pkg], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


def _rpmfusion_status():
    """Etat consolide de RPM Fusion.

    On verifie a la fois la presence du depot active (source de verite reelle
    pour `dnf install`) et le paquet release installe (utile si le depot a ete
    desactive manuellement). `enabled` = les deux depots free + nonfree actifs.
    """
    free = _repo_enabled("rpmfusion-free") or _pkg_installed(_RPMFUSION_FREE_PKG)
    nonfree = _repo_enabled("rpmfusion-nonfree") or _pkg_installed(_RPMFUSION_NONFREE_PKG)
    return {
        "free_enabled": free,
        "nonfree_enabled": nonfree,
        "enabled": free and nonfree,
        "fedora_version": _fedora_version(),
        "selinux": _selinux_state(),
    }


def _stream_sudo(cmd, timeout=_ENABLE_TIMEOUT):
    """Lance `sudo -n <cmd>` et relaie chaque ligne dans les logs SSE.

    Retourne le code retour (0 = succes). -1 si introuvable, -2 si timeout.
    Enregistre le process courant pour permettre l'annulation via /api/task/cancel.
    """
    full = ["sudo", "-n", *cmd]
    try:
        process = subprocess.Popen(
            full, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except FileNotFoundError:
        log_error(f"Commande introuvable : {cmd[0]}")
        return -1
    set_current_process(process)
    try:
        for line in process.stdout:
            line = line.rstrip("\n")
            if line.strip():
                log_info(line)
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        set_current_process(None)
        log_error(f"Timeout (>{timeout}s) : {' '.join(cmd)}")
        return -2
    finally:
        set_current_process(None)
    return process.returncode


@bp.route('/api/fedora/rpmfusion')
def rpmfusion_status():
    """Statut RPM Fusion (free/nonfree actifs, version Fedora, etat SELinux)."""
    return jsonify({"success": True, **_rpmfusion_status()})


@bp.route('/api/fedora/rpmfusion/enable', methods=['POST'])
def rpmfusion_enable():
    """Active les depots RPM Fusion free + nonfree.

    Installe les paquets release depuis les URLs officielles, parametres par la
    version Fedora detectee. Idempotent : ne reinstalle pas ce qui est deja la.
    """
    status = _rpmfusion_status()
    if status["enabled"]:
        return jsonify({"success": True, "already_enabled": True,
                        "message": "RPM Fusion deja active", **status})

    version = status["fedora_version"]
    if not version:
        log_error("Version Fedora indetectable (rpm -E %fedora)")
        return jsonify({"success": False,
                        "error": "Impossible de detecter la version Fedora"}), 500

    base = "https://download1.rpmfusion.org"
    urls = []
    if not status["free_enabled"]:
        urls.append(f"{base}/free/fedora/rpmfusion-free-release-{version}.noarch.rpm")
    if not status["nonfree_enabled"]:
        urls.append(f"{base}/nonfree/fedora/rpmfusion-nonfree-release-{version}.noarch.rpm")

    log_info(f"Activation RPM Fusion (Fedora {version})...")
    if status["selinux"] == "enforcing":
        log_warn("SELinux est en mode enforcing : certains paquets nonfree peuvent "
                 "generer des denials AVC. Surveillez journalctl -t setroubleshoot.")

    rc = _stream_sudo(["dnf", "install", "-y", *urls])
    if rc != 0:
        log_error("Echec activation RPM Fusion")
        return jsonify({"success": False,
                        "error": "Echec de l'installation des paquets RPM Fusion"}), 500

    log_success("RPM Fusion active (free + nonfree)")
    return jsonify({"success": True, "message": "RPM Fusion active",
                    **_rpmfusion_status()})


def _codecs_status():
    """Etat des codecs multimedia. `installed` = tous les paquets temoins presents.

    `rpmfusion_required` rappelle au frontend que l'install est bloquee tant que
    RPM Fusion n'est pas actif (ffmpeg-libs et plugins ugly viennent de la)."""
    installed = all(_pkg_installed(p) for p in _CODEC_WITNESSES)
    rpmfusion = _rpmfusion_status()["enabled"]
    return {"installed": installed, "rpmfusion_enabled": rpmfusion}


@bp.route('/api/fedora/codecs')
def codecs_status():
    """Statut des codecs multimedia (installes ? RPM Fusion actif ?)."""
    return jsonify({"success": True, **_codecs_status()})


@bp.route('/api/fedora/codecs/install', methods=['POST'])
def codecs_install():
    """Installe ffmpeg complet + plugins GStreamer, puis met a jour les groupes
    multimedia et sound-and-video. Exige RPM Fusion actif au prealable."""
    status = _codecs_status()
    if not status["rpmfusion_enabled"]:
        log_warn("Codecs : RPM Fusion requis mais non actif")
        return jsonify({"success": False, "rpmfusion_required": True,
                        "error": "Activez RPM Fusion avant d'installer les codecs"}), 409
    if status["installed"]:
        return jsonify({"success": True, "already_installed": True,
                        "message": "Codecs deja installes", **status})

    # Etape 1 (critique) : ffmpeg non libre + plugins GStreamer. --allowerasing
    # pour le swap ffmpeg-free -> ffmpeg-libs. C'est ce qui apporte les codecs.
    log_info("Installation des codecs multimedia (ffmpeg + GStreamer)...")
    if _stream_sudo(["dnf", "install", "-y", "--allowerasing", *_CODEC_PACKAGES],
                    timeout=_CODEC_TIMEOUT) != 0:
        log_error("Echec installation des codecs (ffmpeg + GStreamer)")
        return jsonify({"success": False,
                        "error": "Echec de l'installation des codecs multimedia"}), 500

    # Etapes 2-3 (best effort) : mise a jour des groupes vers les variantes
    # freeworld. Non bloquantes : sur un systeme ou le groupe n'est pas installe,
    # ces commandes peuvent renvoyer non-zero sans que les codecs soient absents.
    group_steps = [
        ["dnf", "group", "upgrade", "-y", "multimedia",
         "--setopt=install_weak_deps=False", "--exclude=PackageKit-gstreamer-plugin"],
        ["dnf", "group", "upgrade", "-y", "sound-and-video"],
    ]
    for cmd in group_steps:
        if _stream_sudo(cmd, timeout=_CODEC_TIMEOUT) != 0:
            log_warn(f"Mise a jour de groupe non critique echouee : {' '.join(cmd[3:])}")

    log_success("Codecs multimedia installes")
    return jsonify({"success": True, "message": "Codecs installes", **_codecs_status()})


# --- Wizard NVIDIA proprietaire ---

def _nvidia_gpu_present():
    """True si une carte NVIDIA est detectee via lspci (classe VGA/3D)."""
    try:
        r = subprocess.run(["lspci", "-nn"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            low = line.lower()
            if "nvidia" in low and ("vga compatible" in low or "3d controller" in low):
                return True
        return False
    except Exception:
        return False


def _secure_boot_enabled():
    """Etat du Secure Boot via mokutil. True/False, ou None si indeterminable.

    Secure Boot impose de signer le module akmod-nvidia (MOK), sinon le pilote
    ne charge pas. On l'expose pour avertir l'utilisateur."""
    try:
        r = subprocess.run(["mokutil", "--sb-state"], capture_output=True, text=True, timeout=5)
        out = r.stdout.lower()
        if "enabled" in out:
            return True
        if "disabled" in out:
            return False
        return None
    except Exception:
        return None


def _nvidia_status():
    return {
        "gpu_detected": _nvidia_gpu_present(),
        "installed": _pkg_installed(_NVIDIA_WITNESS),
        "rpmfusion_enabled": _rpmfusion_status()["enabled"],
        "secure_boot": _secure_boot_enabled(),
    }


@bp.route('/api/fedora/nvidia')
def nvidia_status():
    """Statut pilote NVIDIA (GPU detecte ? installe ? RPM Fusion ? Secure Boot ?)."""
    return jsonify({"success": True, **_nvidia_status()})


@bp.route('/api/fedora/nvidia/install', methods=['POST'])
def nvidia_install():
    """Installe le pilote NVIDIA proprietaire (akmod + cuda). Exige RPM Fusion."""
    status = _nvidia_status()
    if not status["rpmfusion_enabled"]:
        log_warn("NVIDIA : RPM Fusion requis mais non actif")
        return jsonify({"success": False, "rpmfusion_required": True,
                        "error": "Activez RPM Fusion avant d'installer le pilote NVIDIA"}), 409
    if status["installed"]:
        return jsonify({"success": True, "already_installed": True,
                        "message": "Pilote NVIDIA deja installe", **status})

    log_info("Installation du pilote NVIDIA proprietaire (akmod-nvidia + cuda)...")
    if status["secure_boot"]:
        log_warn("Secure Boot actif : le module akmod doit etre signe (MOK) sinon le "
                 "pilote ne chargera pas. Voir mokutil --import apres compilation.")
    log_info("Le module akmod sera compile au prochain demarrage : patientez avant de redemarrer.")

    if _stream_sudo(["dnf", "install", "-y", *_NVIDIA_PACKAGES], timeout=_NVIDIA_TIMEOUT) != 0:
        log_error("Echec installation pilote NVIDIA")
        return jsonify({"success": False,
                        "error": "Echec de l'installation du pilote NVIDIA"}), 500

    log_success("Pilote NVIDIA installe (redemarrage requis)")
    return jsonify({"success": True, "message": "Pilote NVIDIA installe (redemarrage requis)",
                    **_nvidia_status()})


# --- Wizard Flathub ---

def _flathub_status():
    """Etat du depot Flathub. `present` = remote declare, `filtered` = remote
    filtre (cas par defaut sur Fedora Workstation : sous-ensemble seulement)."""
    present = False
    filtered = False
    try:
        r = subprocess.run(["flatpak", "remotes", "--columns=name,filter"],
                           capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            parts = line.split("\t") if "\t" in line else line.split()
            if parts and parts[0] == "flathub":
                present = True
                # Une colonne filter non vide (chemin/URL) => remote filtre.
                filtered = len(parts) > 1 and parts[1] not in ("", "-")
                break
    except Exception:
        pass
    return {"present": present, "filtered": filtered,
            "enabled": present and not filtered}


@bp.route('/api/fedora/flathub')
def flathub_status():
    """Statut Flathub (present ? filtre ?)."""
    return jsonify({"success": True, **_flathub_status()})


@bp.route('/api/fedora/flathub/enable', methods=['POST'])
def flathub_enable():
    """Active Flathub complet : ajoute le remote s'il est absent, sinon retire le
    filtre. Remote systeme => sudo requis."""
    status = _flathub_status()
    if status["enabled"]:
        return jsonify({"success": True, "already_enabled": True,
                        "message": "Flathub deja actif (non filtre)", **status})

    if not status["present"]:
        log_info("Ajout du depot Flathub complet...")
        cmd = ["flatpak", "remote-add", "--if-not-exists", "flathub", _FLATHUB_URL]
    else:
        log_info("Retrait du filtre Flathub (depot complet)...")
        cmd = ["flatpak", "remote-modify", "--no-filter", "--enable", "flathub"]

    if _stream_sudo(cmd, timeout=_FLATPAK_TIMEOUT) != 0:
        log_error("Echec activation Flathub")
        return jsonify({"success": False,
                        "error": "Echec de l'activation de Flathub"}), 500

    log_success("Flathub complet active")
    return jsonify({"success": True, "message": "Flathub active", **_flathub_status()})
