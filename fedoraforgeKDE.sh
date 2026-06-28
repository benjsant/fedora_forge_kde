#!/bin/bash
# =============================================================
# FedoraForgeKDE - Script tout-en-un
# =============================================================
# 1. Verifie Python 3
# 2. Cree un venv temporaire (.venv) et y installe Flask + Pydantic via pip
# 3. Demande le mot de passe sudo (et le garde en cache)
# 4. Desactive la mise en veille pendant l'execution
# 5. Lance l'interface web et ouvre le navigateur
# 6. Reactive la mise en veille a la fermeture
# 7. Propose de supprimer le venv a la sortie (outil run-once : rien laisse sur le systeme)
#
# Usage: ./fedoraforgeKDE.sh
# =============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

PYTHON_SCRIPT="$SCRIPT_DIR/fedora_kde_forge.py"
VENV_DIR="$SCRIPT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_CREATED=0   # 1 si le venv a ete cree pendant CE lancement (defaut suppression)

# -- Couleurs --
RED='\033[1;31m'
GREEN='\033[1;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
RESET='\033[0m'

info()    { echo -e "${BLUE}[INFO]${RESET} $1"; }
ok()      { echo -e "${GREEN}[OK]${RESET} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $1"; }
fail()    { echo -e "${RED}[ERREUR]${RESET} $1"; exit 1; }

# -- Mode --uninstall : retire les fichiers systeme deposes par FedoraForgeKDE --
if [ "${1:-}" = "--uninstall" ]; then
    echo ""
    echo -e "${BLUE}================================================${RESET}"
    echo -e "${GREEN}  FedoraForgeKDE - Desinstallation systeme${RESET}"
    echo -e "${BLUE}================================================${RESET}"
    echo ""
    info "Suppression des fichiers systeme deposes par FedoraForgeKDE."
    info "Les paquets installes ne sont PAS desinstalles (utilisez le rollback dans l'UI pour ca)."
    echo ""

    if ! sudo -v; then fail "Acces sudo requis."; fi

    _targets=(
        "/etc/sudoers.d/fedoraforgekde"
        "/etc/plasmalogin.conf.d/fedoraforgekde.conf"
        "/etc/sddm.conf.d/fedoraforgekde.conf"
        "/etc/tlp.d/01-fedoraforgekde.conf"
    )
    _removed=0
    for f in "${_targets[@]}"; do
        if [ -f "$f" ]; then
            sudo rm -f "$f" && { ok "Supprime : $f"; _removed=$((_removed+1)); } || warn "Echec : $f"
        fi
    done

    # Venv temporaire residuel (si conserve lors d'un lancement precedent)
    if [ -d "$SCRIPT_DIR/.venv" ]; then
        rm -rf "$SCRIPT_DIR/.venv" && ok "Venv temporaire supprime (.venv)"
    fi

    # Nettoyage logs et state
    if [ -d "$SCRIPT_DIR/logs" ] || [ -d "$SCRIPT_DIR/data" ]; then
        read -r -p "Supprimer aussi logs/ et data/state.json ? [y/N] " _ans
        if [ "${_ans,,}" = "y" ]; then
            rm -rf "$SCRIPT_DIR/logs" "$SCRIPT_DIR/data"
            ok "logs/ et data/ supprimes"
        fi
    fi

    ok "Desinstallation terminee ($_removed fichier(s) systeme retire(s))."
    exit 0
fi

echo ""
echo -e "${BLUE}================================================${RESET}"
echo -e "${GREEN}  FedoraForgeKDE - Lancement complet${RESET}"
echo -e "${BLUE}================================================${RESET}"
echo ""

# =============================================================
# 1. Verifier Python 3
# =============================================================
info "Verification de Python 3..."
command -v python3 &>/dev/null || fail "Python 3 non trouve. Installez-le avec: sudo dnf install python3"
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
ok "Python $PYTHON_VERSION"

# =============================================================
# 2. Preparer un venv temporaire (pas de paquet Python laisse sur le systeme)
# =============================================================
# Philosophie : outil run-once. On n'installe PAS python3-flask/python3-pydantic
# a demeure. On cree un venv jetable, on y met les deps via pip, et on propose
# de le supprimer a la sortie une fois que l'utilisateur a valide que tout est bon.
if [ ! -x "$VENV_PY" ]; then
    info "Creation de l'environnement virtuel temporaire (.venv)..."
    python3 -m venv "$VENV_DIR" || fail "Echec de 'python3 -m venv' (paquet python3 incomplet ?)"
    VENV_CREATED=1
    ok "Venv cree : $VENV_DIR"
else
    ok "Venv existant reutilise : $VENV_DIR"
fi

# Sur Fedora, le venv peut naitre SANS pip (wheels debundlees). On bootstrap via
# ensurepip ; si ca echoue, on guide vers le paquet systeme requis (une fois).
if [ ! -x "$VENV_DIR/bin/pip" ]; then
    info "pip absent du venv, bootstrap via ensurepip..."
    "$VENV_PY" -m ensurepip --upgrade &>/dev/null || true
fi
if [ ! -x "$VENV_DIR/bin/pip" ]; then
    fail "pip indisponible dans le venv. Installez-le une fois : sudo dnf install python3-pip"
fi

# =============================================================
# 3. Installer Flask + Pydantic dans le venv
# =============================================================
if "$VENV_PY" -c "import flask, pydantic" &>/dev/null; then
    ok "Dependances deja presentes dans le venv (Flask, Pydantic)"
else
    info "Installation des dependances dans le venv (Flask, Pydantic)..."
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip &>/dev/null || true
    "$VENV_DIR/bin/pip" install --quiet flask pydantic \
        || fail "Echec de l'installation pip (connexion reseau ?)"
    "$VENV_PY" -c "import flask, pydantic" &>/dev/null \
        || fail "Flask/Pydantic introuvables apres installation"
    ok "Dependances installees dans le venv"
fi

# =============================================================
# 4. Demander sudo (cache le mot de passe pour les scripts)
# =============================================================
echo ""
info "Verification de l'acces sudo..."
if ! sudo -v; then
    fail "Acces sudo requis pour installer les paquets."
fi
ok "Acces sudo"

# =============================================================
# 4b. Installer les outils requis si absents
# =============================================================
_MISSING_PKGS=()
command -v sassc   &>/dev/null || _MISSING_PKGS+=("sassc")
command -v git     &>/dev/null || _MISSING_PKGS+=("git")
if [ ${#_MISSING_PKGS[@]} -gt 0 ]; then
    info "Installation des outils requis : ${_MISSING_PKGS[*]}..."
    sudo dnf install -y "${_MISSING_PKGS[@]}" \
        || warn "Impossible d'installer : ${_MISSING_PKGS[*]} (verifiez la connexion)"
    ok "Outils requis installes"
fi

# Configurer sudoers pour firewall-cmd sans mot de passe (temporaire — nettoye au quit)
SUDOERS_FILE="/etc/sudoers.d/fedoraforgekde"
SUDOERS_CREATED=0
if [ ! -f "$SUDOERS_FILE" ]; then
    info "Configuration sudo temporaire (firewall-cmd)..."
    {
        echo "# Genere par FedoraForgeKDE — supprime a la fermeture"
        echo "$USER ALL=(ALL) NOPASSWD: /usr/bin/firewall-cmd"
    } | sudo tee "$SUDOERS_FILE" > /dev/null
    sudo chmod 440 "$SUDOERS_FILE"
    SUDOERS_CREATED=1
    ok "Sudo configure (firewall-cmd sans mot de passe)"
fi

# Garder sudo actif en arriere-plan (renouvelle toutes les 50s)
(while true; do sudo -n true 2>/dev/null; sleep 50; done) &
SUDO_KEEPER_PID=$!

# =============================================================
# 5. Desactiver la mise en veille (KDE Plasma)
# =============================================================
INHIBIT_COOKIE=""

disable_sleep() {
    # KDE: utiliser qdbus pour inhiber la mise en veille
    if command -v qdbus &>/dev/null || command -v qdbus6 &>/dev/null; then
        QDBUS=$(command -v qdbus6 2>/dev/null || command -v qdbus 2>/dev/null)
        INHIBIT_COOKIE=$($QDBUS org.freedesktop.PowerManagement /org/freedesktop/PowerManagement/Inhibit \
            org.freedesktop.PowerManagement.Inhibit.Inhibit \
            "FedoraForgeKDE" "Installation en cours" 2>/dev/null || echo "")
        if [ -n "$INHIBIT_COOKIE" ]; then
            ok "Mise en veille inhibee (cookie: $INHIBIT_COOKIE)"
        else
            warn "Impossible d'inhiber la mise en veille via qdbus"
        fi
    # Fallback: systemd-inhibit
    elif command -v systemd-inhibit &>/dev/null; then
        warn "qdbus non disponible, mise en veille non inhibee automatiquement"
    fi
}

restore_sleep() {
    if [ -n "$INHIBIT_COOKIE" ]; then
        QDBUS=$(command -v qdbus6 2>/dev/null || command -v qdbus 2>/dev/null)
        $QDBUS org.freedesktop.PowerManagement /org/freedesktop/PowerManagement/Inhibit \
            org.freedesktop.PowerManagement.Inhibit.UnInhibit \
            "$INHIBIT_COOKIE" 2>/dev/null || true
        info "Mise en veille restauree"
    fi
}

disable_sleep

# =============================================================
# 6. Nettoyage a la fermeture (CTRL+C ou fin normale)
# =============================================================
cleanup() {
    echo ""
    info "Arret de FedoraForgeKDE..."
    restore_sleep
    kill "$SUDO_KEEPER_PID" 2>/dev/null
    if [ "$SUDOERS_CREATED" = "1" ] && [ -f "$SUDOERS_FILE" ]; then
        sudo -n rm -f "$SUDOERS_FILE" 2>/dev/null \
            && info "Sudoers temporaire nettoye" \
            || warn "Impossible de supprimer $SUDOERS_FILE (a faire manuellement)"
    fi

    # Venv temporaire : proposer la suppression (outil run-once, on ne laisse rien).
    # En mode non-interactif, on conserve par securite (pas de suppression aveugle).
    if [ -d "$VENV_DIR" ]; then
        if [ -t 0 ]; then
            read -r -p "Tout est bon ? Supprimer l'environnement temporaire .venv ? [O/n] " _ans
            case "${_ans,,}" in
                n|no|non) info "Venv conserve : $VENV_DIR (re-supprimable via --uninstall)" ;;
                *) rm -rf "$VENV_DIR" && ok "Venv temporaire supprime" ;;
            esac
        else
            info "Venv conserve (mode non-interactif) : $VENV_DIR"
        fi
    fi

    ok "FedoraForgeKDE arrete. A bientot!"
}

trap cleanup EXIT

# =============================================================
# 7. Lancer l'application
# =============================================================
echo ""
echo -e "${BLUE}================================================${RESET}"
echo -e "${GREEN}  FedoraForgeKDE pret - Lancement...${RESET}"
echo -e "${BLUE}================================================${RESET}"
echo ""
info "URL: http://localhost:5000"
info "Arret: CTRL+C"
echo ""

"$VENV_PY" "$PYTHON_SCRIPT"
