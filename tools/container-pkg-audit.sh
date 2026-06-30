#!/bin/bash
# =============================================================
# container-pkg-audit.sh
# Audit de RESOLUTION des paquets DNF de FedoraForgeKDE sur un vrai Fedora,
# dans un conteneur podman jetable -- SANS VM.
#
#   ./tools/container-pkg-audit.sh [--fedora N] [--no-rpmfusion]
#
# Attrape la classe de bugs "paquet inexistant/renomme sur Fedora" (ex. vecus :
# kdeconnect -> kdeconnectd, mesa-vdpau-drivers-freeworld absent de RPM Fusion F44)
# que les tests mockes + la CI ne voient pas.
#
# Couverture : apt[] de tous les profils + install.json + optional_install.json
# + paquets DNF des wizards (codecs, NVIDIA) + variantes mesa freeworld.
# NE teste PAS : SELinux, sched-ext, akmod, comportement runtime -> ca, c'est la VM
# (tools/vm-test-harness.sh). Ici on ne valide QUE la disponibilite des paquets.
#
# Prerequis hote : podman + python3 + reseau. Le conteneur partage le noyau hote
# mais la resolution dnf se fait contre les vrais depots Fedora N.
# =============================================================
set -uo pipefail

RED='\033[1;31m'; GREEN='\033[1;32m'; YELLOW='\033[1;33m'; BLUE='\033[1;34m'; RESET='\033[0m'
FEDORA_VER=44
RPMFUSION=1

usage() {
    cat <<EOF
Usage : ./tools/container-pkg-audit.sh [options]
  --fedora N        Version Fedora cible (defaut 44)
  --no-rpmfusion    Ne pas activer RPM Fusion (pour distinguer "necessite RPM
                    Fusion" de "introuvable partout")
  -h, --help        Cette aide
EOF
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --fedora) FEDORA_VER="${2:-44}"; shift 2 ;;
        --no-rpmfusion) RPMFUSION=0; shift ;;
        -h|--help) usage ;;
        *) echo "Option inconnue : $1"; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
IMAGE="registry.fedoraproject.org/fedora:${FEDORA_VER}"

command -v podman >/dev/null 2>&1 || { echo -e "${RED}[ERREUR]${RESET} podman requis (sudo dnf install podman)"; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo -e "${RED}[ERREUR]${RESET} python3 requis sur l'hote"; exit 2; }

echo -e "${BLUE}================================================${RESET}"
echo -e "${GREEN}  Audit paquets en conteneur : Fedora ${FEDORA_VER}${RESET}"
echo -e "  RPM Fusion : $([ $RPMFUSION -eq 1 ] && echo active || echo desactive)"
echo -e "${BLUE}================================================${RESET}"

# --- Liste des paquets attendus (extraite cote hote) ---
WANT="$(python3 - "$REPO_ROOT" <<'PY'
import glob, json, re, sys
root = sys.argv[1]
names = set()
# apt[] de tous les profils
for f in glob.glob(f"{root}/configs/profiles/*.json"):
    for p in json.load(open(f)).get("apt", []):
        names.add(p["name"])
# install.json + optional_install.json
for cfg in ("install.json", "optional_install.json"):
    try:
        for p in json.load(open(f"{root}/configs/{cfg}")).get("packages", []):
            names.add(p["name"])
    except FileNotFoundError:
        pass
# paquets DNF des wizards (codecs, NVIDIA) : lus par AST pour ne PAS importer
# Flask (le python3 hote n'a pas forcement les deps du projet).
try:
    import ast
    tree = ast.parse(open(f"{root}/routes/fedora_wizards.py").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in ("_CODEC_PACKAGES", "_NVIDIA_PACKAGES")
            for t in node.targets
        ):
            names.update(ast.literal_eval(node.value))
except Exception:
    pass
# variantes mesa freeworld (issues du cmd externe d'amd.json, non listees en apt)
names.update(["mesa-va-drivers-freeworld", "mesa-vulkan-drivers-freeworld"])
# normalise : retire le suffixe d'architecture
clean = {re.sub(r"\.(i686|x86_64|noarch|aarch64)$", "", n) for n in names}
print(" ".join(sorted(clean)))
PY
)"

if [ -z "$WANT" ]; then
    echo -e "${RED}[ERREUR]${RESET} Impossible d'extraire la liste des paquets (configs/ introuvable ?)"
    exit 2
fi
TOTAL=$(wc -w <<<"$WANT")
echo -e "${BLUE}[INFO]${RESET} $TOTAL paquets uniques a verifier"

# --- Analyse DANS le conteneur ---
# Toute la logique d'ensemble se fait cote conteneur (une seule locale -> pas de
# mismatch hote/conteneur). Chaque paquet manquant est classe :
#   MISSING = aucun paquet ni Provides -> echec install garanti
#   RENAMED = nom exact absent mais resolu via Provides (ex wget->wget2) -> fragile
echo -e "${BLUE}[INFO]${RESET} Lancement du conteneur (pull de l'image au 1er run)..."
RESULT="$(podman run --rm -e WANT="$WANT" -e RPMFUSION="$RPMFUSION" -e FV="$FEDORA_VER" "$IMAGE" bash -c '
    export LC_ALL=C
    if [ "$RPMFUSION" = "1" ]; then
        dnf install -y \
          "https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-${FV}.noarch.rpm" \
          "https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-${FV}.noarch.rpm" \
          >/dev/null 2>&1 || true
    fi
    avail=$(dnf repoquery --qf "%{name}\n" --available $WANT 2>/dev/null | sort -u)
    missing=$(comm -23 <(printf "%s\n" $WANT | sort -u) <(printf "%s\n" "$avail"))
    for p in $missing; do
        if dnf repoquery --whatprovides "$p" 2>/dev/null | grep -q .; then
            echo "RENAMED $p"
        else
            echo "MISSING $p"
        fi
    done
    echo "###DONE###"
')"

if ! grep -q "###DONE###" <<<"$RESULT"; then
    echo -e "${RED}[ERREUR]${RESET} Le conteneur n'a pas termine l'analyse (reseau ? image ? pull echoue ?)"
    exit 2
fi

TRULY="$(grep '^MISSING ' <<<"$RESULT" | awk '{print $2}' | sort -u)"
RENAMED="$(grep '^RENAMED ' <<<"$RESULT" | awk '{print $2}' | sort -u)"
NT=0; [ -n "$TRULY" ] && NT=$(grep -c . <<<"$TRULY")
NR=0; [ -n "$RENAMED" ] && NR=$(grep -c . <<<"$RENAMED")
RF=$([ $RPMFUSION -eq 1 ] && echo on || echo off)

echo ""
echo -e "${BLUE}================================================${RESET}"
if [ "$NT" -eq 0 ] && [ "$NR" -eq 0 ]; then
    echo -e "  ${GREEN}PASS${RESET} les $TOTAL paquets resolvent sur Fedora ${FEDORA_VER} (RPM Fusion: $RF)"
    echo -e "${BLUE}================================================${RESET}"
    exit 0
fi
if [ "$NR" -gt 0 ]; then
    echo -e "  ${YELLOW}WARN${RESET} $NR nom(s) obsolete(s) mais resolu(s) via Provides (a renommer, fragile) :"
    while read -r m; do [ -n "$m" ] && echo "       - $m"; done <<<"$RENAMED"
fi
if [ "$NT" -gt 0 ]; then
    echo -e "  ${RED}FAIL${RESET} $NT paquet(s) introuvable(s) sur Fedora ${FEDORA_VER} (echec install garanti, RPM Fusion: $RF) :"
    while read -r m; do [ -n "$m" ] && echo "       - $m"; done <<<"$TRULY"
    [ $RPMFUSION -eq 0 ] && echo "       (relancez SANS --no-rpmfusion : certains viennent peut-etre de RPM Fusion)"
fi
echo -e "${BLUE}================================================${RESET}"
# Echec (exit 1) uniquement sur les vrais introuvables ; les renommes = WARN.
[ "$NT" -gt 0 ] && exit 1 || exit 0
