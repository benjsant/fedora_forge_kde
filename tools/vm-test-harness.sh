#!/bin/bash
# =============================================================
# vm-test-harness.sh
# Valide les wizards FedoraForgeKDE sur une VM Fedora, via SSH.
#
# A EXECUTER SUR L'HOTE (pas dans la VM) :
#     ./vm-test-harness.sh user@ip [options]
#
# Deux niveaux :
#   - Non destructif (defaut) : detection identite/SELinux/sched_ext +
#     disponibilite des paquets (repoquery). Ne modifie PAS la VM.
#   - Destructif (--mutate)    : active reellement RPM Fusion et teste
#     l'activation/desactivation du scheduler sched-ext. SNAPSHOT D'ABORD.
#
# Prerequis VM : preparee par vm-enable-ssh.sh (sshd + NOPASSWD sudo).
# =============================================================
set -uo pipefail

RED='\033[1;31m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; BLUE='\033[1;34m'; RESET='\033[0m'
SSH_PORT=""
MUTATE=0
PASS=0; FAILN=0; WARN=0; SKIP=0

usage() {
    cat <<EOF
Usage : ./vm-test-harness.sh user@ip [options]

  --port <n>     Port SSH (defaut 22)
  --mutate       Execute les tests destructifs (active RPM Fusion, sched-ext).
                 Faites un SNAPSHOT de la VM avant.
  -h, --help     Cette aide
EOF
    exit 0
}

[ $# -ge 1 ] || usage
SSH_TARGET="$1"; shift
case "$SSH_TARGET" in -h|--help) usage ;; esac
while [ $# -gt 0 ]; do
    case "$1" in
        --port)   SSH_PORT="${2:-}"; shift 2 ;;
        --mutate) MUTATE=1; shift ;;
        -h|--help) usage ;;
        *) echo "Option inconnue : $1"; exit 1 ;;
    esac
done

# Execute une commande sur la VM. Renvoie code + stdout/stderr fusionnes.
rexec() {
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new \
        ${SSH_PORT:+-p "$SSH_PORT"} "$SSH_TARGET" "$@" 2>&1
}

# check NOM "commande distante" [sous-chaine attendue]
# PASS si exit 0 (et, si fournie, si la sortie contient la sous-chaine).
check() {
    local name="$1" cmd="$2" want="${3:-}"
    local out rc
    out="$(rexec "$cmd")"; rc=$?
    if [ $rc -ne 0 ]; then
        echo -e "  ${RED}FAIL${RESET} $name (exit $rc)"
        [ -n "$out" ] && echo "       ${out//$'\n'/$'\n'       }"
        FAILN=$((FAILN+1)); return 1
    fi
    if [ -n "$want" ] && ! grep -qiF "$want" <<<"$out"; then
        echo -e "  ${RED}FAIL${RESET} $name (sortie sans '$want')"
        echo "       ${out//$'\n'/$'\n'       }"
        FAILN=$((FAILN+1)); return 1
    fi
    echo -e "  ${GREEN}PASS${RESET} $name${out:+  ->  ${out%%$'\n'*}}"
    PASS=$((PASS+1)); return 0
}

note_warn() { echo -e "  ${YELLOW}WARN${RESET} $1"; WARN=$((WARN+1)); }
note_skip() { echo -e "  ${BLUE}SKIP${RESET} $1"; SKIP=$((SKIP+1)); }
section()   { echo ""; echo -e "${BLUE}== $1 ==${RESET}"; }

echo -e "${BLUE}================================================${RESET}"
echo -e "${GREEN}  Harnais de test VM : $SSH_TARGET${RESET}"
echo -e "  Mode : $([ $MUTATE -eq 1 ] && echo 'DESTRUCTIF (--mutate)' || echo 'non destructif')"
echo -e "${BLUE}================================================${RESET}"

# =============================================================
section "Connectivite & environnement"
# =============================================================
if ! rexec "true" >/dev/null; then
    echo -e "  ${RED}FAIL${RESET} Connexion SSH impossible a $SSH_TARGET"
    echo "  Verifiez : VM allumee, sshd actif, IP/port, cle ou mot de passe."
    exit 1
fi
echo -e "  ${GREEN}PASS${RESET} Connexion SSH"; PASS=$((PASS+1))

check "Distribution Fedora" 'grep -q "^ID=fedora" /etc/os-release && echo ok' "ok"
check "Version Fedora (rpm -E %fedora)" 'rpm -E %fedora'
check "Noyau" 'uname -r'
check "sudo -n (NOPASSWD configure)" 'sudo -n true && echo ok' "ok"

# SELinux : on attend enforcing (proposition de valeur du projet)
selinux="$(rexec 'getenforce' 2>/dev/null)"
if [ "$selinux" = "Enforcing" ]; then
    echo -e "  ${GREEN}PASS${RESET} SELinux Enforcing"; PASS=$((PASS+1))
else
    note_warn "SELinux = ${selinux:-inconnu} (attendu Enforcing sur Fedora)"
fi

# =============================================================
section "RPM Fusion"
# =============================================================
rpmfusion_on() {
    rexec 'dnf repolist --enabled 2>/dev/null | grep -q rpmfusion-nonfree && echo on || echo off'
}
state="$(rpmfusion_on)"
if [ "$state" = "on" ]; then
    echo -e "  ${GREEN}PASS${RESET} RPM Fusion deja actif"; PASS=$((PASS+1))
elif [ $MUTATE -eq 1 ]; then
    echo "  (activation RPM Fusion en cours...)"
    ver="$(rexec 'rpm -E %fedora')"
    cmd="sudo -n dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-${ver}.noarch.rpm https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${ver}.noarch.rpm"
    if rexec "$cmd" >/dev/null; then
        [ "$(rpmfusion_on)" = "on" ] \
            && { echo -e "  ${GREEN}PASS${RESET} RPM Fusion active"; PASS=$((PASS+1)); } \
            || { echo -e "  ${RED}FAIL${RESET} RPM Fusion installe mais depots non actifs"; FAILN=$((FAILN+1)); }
    else
        echo -e "  ${RED}FAIL${RESET} Echec activation RPM Fusion"; FAILN=$((FAILN+1))
    fi
else
    note_skip "RPM Fusion inactif (utilisez --mutate pour l'activer)"
fi

# =============================================================
section "Codecs (disponibilite, non destructif)"
# =============================================================
if [ "$(rpmfusion_on)" = "on" ]; then
    check "ffmpeg-libs disponible" \
        'dnf repoquery --available ffmpeg-libs 2>/dev/null | grep -q ffmpeg-libs && echo ok' "ok"
    check "gstreamer1-plugins-ugly disponible" \
        'dnf repoquery --available gstreamer1-plugins-ugly 2>/dev/null | grep -q gstreamer1 && echo ok' "ok"
else
    note_skip "Codecs : RPM Fusion requis (non actif)"
fi

# =============================================================
section "NVIDIA (detection + disponibilite, non destructif)"
# =============================================================
gpu="$(rexec "lspci -nn 2>/dev/null | grep -iE 'vga|3d' | grep -ic nvidia")"
if [ "${gpu:-0}" -gt 0 ] 2>/dev/null; then
    echo -e "  ${GREEN}PASS${RESET} GPU NVIDIA detecte"; PASS=$((PASS+1))
    if [ "$(rpmfusion_on)" = "on" ]; then
        check "akmod-nvidia disponible" \
            'dnf repoquery --available akmod-nvidia 2>/dev/null | grep -q akmod-nvidia && echo ok' "ok"
    else
        note_skip "akmod-nvidia : RPM Fusion requis"
    fi
    sb="$(rexec 'command -v mokutil >/dev/null && mokutil --sb-state 2>/dev/null || echo na')"
    grep -qi 'enabled' <<<"$sb" && note_warn "Secure Boot actif : signature MOK requise pour NVIDIA"
else
    note_skip "Aucun GPU NVIDIA (rien a tester cote pilote proprietaire)"
fi

# =============================================================
section "Scheduler sched-ext"
# =============================================================
check "Noyau expose sched_ext" 'test -d /sys/kernel/sched_ext && echo ok' "ok"
check "scx-scheds installable (repoquery)" \
    'dnf repoquery --available scx-scheds 2>/dev/null | grep -q scx-scheds && echo ok' "ok"

if [ $MUTATE -eq 1 ]; then
    echo "  (test reel : installation scx-scheds + activation scx_lavd ~5s...)"
    rexec 'sudo -n dnf install -y scx-scheds' >/dev/null
    if rexec 'command -v scx_lavd >/dev/null && echo ok' | grep -q ok; then
        # Lance scx_lavd detache, verifie l'attachement, puis l'arrete.
        rexec 'sudo -n nohup scx_lavd >/tmp/scx_test.log 2>&1 & echo started' >/dev/null
        sleep 4
        st="$(rexec 'cat /sys/kernel/sched_ext/state 2>/dev/null')"
        active="$(rexec 'cat /sys/kernel/sched_ext/root/ops 2>/dev/null || true')"
        rexec 'sudo -n pkill -x scx_lavd' >/dev/null 2>&1
        sleep 2
        st_after="$(rexec 'cat /sys/kernel/sched_ext/state 2>/dev/null')"
        if grep -qi enabled <<<"$st"; then
            echo -e "  ${GREEN}PASS${RESET} scx_lavd attache (state=$st${active:+, ops=$active})"; PASS=$((PASS+1))
        else
            echo -e "  ${RED}FAIL${RESET} scx_lavd non attache (state=$st)"; FAILN=$((FAILN+1))
        fi
        grep -qi disabled <<<"$st_after" \
            && { echo -e "  ${GREEN}PASS${RESET} retour au scheduler par defaut apres arret"; PASS=$((PASS+1)); } \
            || note_warn "sched_ext encore $st_after apres arret (verifier a la main)"
    else
        echo -e "  ${RED}FAIL${RESET} scx_lavd absent apres installation"; FAILN=$((FAILN+1))
    fi
else
    note_skip "Activation sched-ext (utilisez --mutate)"
fi

# =============================================================
section "Flathub"
# =============================================================
fh="$(rexec 'flatpak remotes --columns=name,filter 2>/dev/null | grep -i flathub || echo absent')"
if grep -qi absent <<<"$fh"; then
    note_warn "Flathub absent (le wizard l'ajouterait)"
else
    echo -e "  ${GREEN}PASS${RESET} Flathub present  ->  $fh"; PASS=$((PASS+1))
fi

# =============================================================
echo ""
echo -e "${BLUE}================================================${RESET}"
echo -e "  Resultats : ${GREEN}${PASS} PASS${RESET}  ${RED}${FAILN} FAIL${RESET}  ${YELLOW}${WARN} WARN${RESET}  ${BLUE}${SKIP} SKIP${RESET}"
echo -e "${BLUE}================================================${RESET}"
[ $MUTATE -eq 0 ] && echo "  (mode non destructif - relancez avec --mutate pour les tests reels, snapshot d'abord)"
[ $FAILN -eq 0 ] && exit 0 || exit 1
