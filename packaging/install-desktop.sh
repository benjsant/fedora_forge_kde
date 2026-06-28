#!/bin/bash
# Installe le raccourci FedoraForgeKDE dans le menu KDE (user-level, pas de sudo).
# Apres execution, l'app apparait dans le lanceur Plasma -> "FedoraForgeKDE".
#
# Usage : ./packaging/install-desktop.sh
#         ./packaging/install-desktop.sh --uninstall

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

DESKTOP_SRC="$SCRIPT_DIR/fedora-kde-forge.desktop"
ICON_SRC="$SCRIPT_DIR/fedora-kde-forge.svg"
DESKTOP_DEST="$APPS_DIR/fedora-kde-forge.desktop"
ICON_DEST="$ICONS_DIR/fedora-kde-forge.svg"

if [ "${1:-}" = "--uninstall" ]; then
    rm -f "$DESKTOP_DEST" "$ICON_DEST"
    command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
    echo "[OK] Raccourci FedoraForgeKDE supprime."
    exit 0
fi

mkdir -p "$APPS_DIR" "$ICONS_DIR"

# Substitue __PROJECT_DIR__ par le path absolu actuel
sed "s|__PROJECT_DIR__|$PROJECT_DIR|g" "$DESKTOP_SRC" > "$DESKTOP_DEST"
chmod +x "$DESKTOP_DEST"
cp "$ICON_SRC" "$ICON_DEST"

# Rafraichir les caches (best-effort)
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

echo "[OK] Raccourci installe : $DESKTOP_DEST"
echo "[OK] Icone installee    : $ICON_DEST"
echo "[INFO] Lancez FedoraForgeKDE depuis le menu KDE (rechercher 'Fedora' ou 'Forge')."
