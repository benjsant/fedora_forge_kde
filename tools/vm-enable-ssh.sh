#!/bin/bash
# =============================================================
# vm-enable-ssh.sh
# Prepare une VM Fedora KDE pour les tests SSH de FedoraForgeKDE.
#
# A EXECUTER DANS LA VM (pas sur l'hote), en root :
#     sudo ./vm-enable-ssh.sh [options]
#
# Fait :
#   1. Installe + active sshd (openssh-server)
#   2. Ouvre SSH dans firewalld
#   3. (Defaut) configure NOPASSWD sudo pour l'utilisateur de test
#      -> requis pour que les wizards (sudo -n) marchent pilotes a distance
#   4. Installe une cle SSH publique si fournie (--pubkey)
#   5. Affiche l'IP et la commande de connexion
#
# VM JETABLE UNIQUEMENT : le NOPASSWD sudo affaiblit la securite.
# Faites un snapshot "clean" AVANT de lancer vos tests.
# =============================================================
set -euo pipefail

RED='\033[1;31m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; BLUE='\033[1;34m'; RESET='\033[0m'
info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
ok()   { echo -e "${GREEN}[OK]${RESET} $1"; }
warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
fail() { echo -e "${RED}[ERREUR]${RESET} $1"; exit 1; }

# -- Defauts --
TARGET_USER="${SUDO_USER:-}"
PUBKEY=""
PORT=22
ENABLE_NOPASSWD=1
SUDOERS_FILE="/etc/sudoers.d/fedoraforge-test"

usage() {
    cat <<EOF
Usage : sudo ./vm-enable-ssh.sh [options]

  --user <nom>      Utilisateur cible (defaut : invocateur sudo = ${TARGET_USER:-aucun})
  --pubkey <val>    Cle SSH publique : chemin de fichier OU contenu "ssh-ed25519 ..."
  --port <n>        Port SSH (defaut 22 ; un autre port ajoute une regle SELinux)
  --keep-sudo       NE PAS configurer NOPASSWD sudo (par defaut il est configure)
  -h, --help        Cette aide

Exemples :
  sudo ./vm-enable-ssh.sh --pubkey ~/.ssh/id_ed25519.pub
  sudo ./vm-enable-ssh.sh --user tester --pubkey "ssh-ed25519 AAAA... moi@host"
EOF
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --user)     TARGET_USER="${2:-}"; shift 2 ;;
        --pubkey)   PUBKEY="${2:-}"; shift 2 ;;
        --port)     PORT="${2:-22}"; shift 2 ;;
        --keep-sudo) ENABLE_NOPASSWD=0; shift ;;
        -h|--help)  usage ;;
        *) fail "Option inconnue : $1 (voir --help)" ;;
    esac
done

# -- Pre-requis --
[ "$(id -u)" -eq 0 ] || fail "A lancer en root : sudo $0 $*"

if [ -r /etc/os-release ]; then
    . /etc/os-release
    [ "${ID:-}" = "fedora" ] || warn "Distribution detectee : ${ID:-inconnue} (ce script vise Fedora)."
    info "Systeme : ${PRETTY_NAME:-inconnu}"
fi

[ -n "$TARGET_USER" ] || fail "Aucun utilisateur cible. Precisez --user <nom>."
id "$TARGET_USER" &>/dev/null || fail "Utilisateur '$TARGET_USER' introuvable."
USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
[ -n "$USER_HOME" ] && [ -d "$USER_HOME" ] || fail "Home introuvable pour '$TARGET_USER'."

echo ""
echo -e "${BLUE}================================================${RESET}"
echo -e "${GREEN}  Preparation SSH de la VM (utilisateur: $TARGET_USER)${RESET}"
echo -e "${BLUE}================================================${RESET}"
echo ""

# =============================================================
# 1. openssh-server
# =============================================================
if ! rpm -q openssh-server &>/dev/null; then
    info "Installation de openssh-server..."
    dnf install -y openssh-server || fail "Echec installation openssh-server (reseau ?)"
fi
ok "openssh-server present"

systemctl enable --now sshd || fail "Echec activation de sshd"
ok "sshd actif et active au demarrage"

# =============================================================
# 2. Port non standard : SELinux + sshd_config
# =============================================================
if [ "$PORT" != "22" ]; then
    info "Port SSH personnalise : $PORT"
    if command -v getenforce &>/dev/null && [ "$(getenforce)" != "Disabled" ]; then
        rpm -q policycoreutils-python-utils &>/dev/null || dnf install -y policycoreutils-python-utils
        if ! semanage port -l | grep -q "^ssh_port_t.*\b${PORT}\b"; then
            semanage port -a -t ssh_port_t -p tcp "$PORT" \
                || semanage port -m -t ssh_port_t -p tcp "$PORT" \
                || warn "Echec ajout du port SELinux $PORT (sshd peut etre bloque)"
            ok "Port $PORT autorise dans SELinux (ssh_port_t)"
        fi
    fi
    if [ -d /etc/ssh/sshd_config.d ]; then
        echo "Port $PORT" > /etc/ssh/sshd_config.d/10-fedoraforge-test.conf
        systemctl restart sshd
        ok "sshd ecoute sur le port $PORT"
    fi
fi

# =============================================================
# 3. firewalld
# =============================================================
if systemctl is-active --quiet firewalld; then
    if [ "$PORT" = "22" ]; then
        firewall-cmd --permanent --add-service=ssh &>/dev/null || true
    else
        firewall-cmd --permanent --add-port="${PORT}/tcp" &>/dev/null || true
    fi
    firewall-cmd --reload &>/dev/null || true
    ok "firewalld : SSH autorise (port $PORT)"
else
    info "firewalld inactif : rien a ouvrir."
fi

# =============================================================
# 4. Cle SSH publique (optionnel)
# =============================================================
if [ -n "$PUBKEY" ]; then
    if [ -f "$PUBKEY" ]; then
        KEY_CONTENT="$(cat "$PUBKEY")"
    else
        KEY_CONTENT="$PUBKEY"
    fi
    case "$KEY_CONTENT" in
        ssh-*|ecdsa-*|sk-*) : ;;
        *) fail "La cle fournie ne ressemble pas a une cle publique SSH." ;;
    esac
    SSH_DIR="$USER_HOME/.ssh"
    AUTH="$SSH_DIR/authorized_keys"
    install -d -m 700 -o "$TARGET_USER" -g "$TARGET_USER" "$SSH_DIR"
    touch "$AUTH"
    if ! grep -qxF "$KEY_CONTENT" "$AUTH" 2>/dev/null; then
        echo "$KEY_CONTENT" >> "$AUTH"
        ok "Cle publique ajoutee a $AUTH"
    else
        ok "Cle publique deja presente"
    fi
    chmod 600 "$AUTH"
    chown "$TARGET_USER:$TARGET_USER" "$AUTH"
    # Contexte SELinux correct pour ~/.ssh (sinon sshd refuse la cle)
    command -v restorecon &>/dev/null && restorecon -R "$SSH_DIR" 2>/dev/null || true
else
    warn "Pas de cle fournie (--pubkey). Connexion par mot de passe : assurez-vous"
    warn "que '$TARGET_USER' a un mot de passe (sudo passwd $TARGET_USER)."
fi

# =============================================================
# 5. NOPASSWD sudo (pour 'sudo -n' des wizards pilotes a distance)
# =============================================================
if [ "$ENABLE_NOPASSWD" = "1" ]; then
    warn "Configuration NOPASSWD sudo pour '$TARGET_USER' (VM JETABLE uniquement)."
    TMP_SUDO="$(mktemp)"
    echo "# Genere par vm-enable-ssh.sh (FedoraForgeKDE) - tests VM uniquement" > "$TMP_SUDO"
    echo "$TARGET_USER ALL=(ALL) NOPASSWD: ALL" >> "$TMP_SUDO"
    if visudo -c -f "$TMP_SUDO" &>/dev/null; then
        install -m 440 -o root -g root "$TMP_SUDO" "$SUDOERS_FILE"
        ok "NOPASSWD sudo configure : $SUDOERS_FILE"
    else
        rm -f "$TMP_SUDO"
        fail "Validation visudo echouee, sudoers NON modifie."
    fi
    rm -f "$TMP_SUDO"
else
    info "NOPASSWD sudo NON configure (--keep-sudo). Les wizards en 'sudo -n' echoueront a distance."
fi

# =============================================================
# 6. Recapitulatif + connexion
# =============================================================
echo ""
echo -e "${BLUE}================================================${RESET}"
echo -e "${GREEN}  VM prete pour les tests SSH${RESET}"
echo -e "${BLUE}================================================${RESET}"
mapfile -t IPS < <(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
if [ "${#IPS[@]}" -eq 0 ]; then
    warn "Aucune IP globale detectee. En NAT, configurez une redirection de port hote->VM:$PORT."
else
    info "Adresse(s) IP de la VM :"
    for ip in "${IPS[@]}"; do echo "    - $ip"; done
fi
echo ""
info "Connexion depuis l'hote :"
PORT_OPT=""; [ "$PORT" != "22" ] && PORT_OPT=" -p $PORT"
echo "    ssh${PORT_OPT} ${TARGET_USER}@${IPS[0]:-<IP_VM>}"
echo ""
info "Test rapide une fois connecte :"
echo "    getenforce && rpm -E %fedora && cat /sys/kernel/sched_ext/state"
echo ""
warn "Pensez a faire un SNAPSHOT 'clean' de la VM maintenant, avant de tester les wizards."
