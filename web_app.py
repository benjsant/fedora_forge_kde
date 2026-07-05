#!/usr/bin/env python3
"""FedoraForgeKDE - Interface web Flask."""

import os
import socket
import sys

from flask import Flask, render_template

from routes import (
    copr,
    fedora_tools,
    fedora_wizards,
    kde_settings,
    legacy,
    login_manager,
    profiles,
    selinux,
    state_routes,
    system,
    themes,
    tweaks,
)
from routes.shared import log_info, log_warn
from utils.lockfile import LockfileError, acquire, install_signal_handlers
from utils.security import register_security


def _resolve_port():
    """Port d'ecoute : env FEDORAFORGEKDE_PORT, defaut 5000."""
    raw = os.environ.get("FEDORAFORGEKDE_PORT", "5000")
    try:
        v = int(raw)
        return v if 1024 <= v <= 65535 else 5000
    except (ValueError, TypeError):
        return 5000


# Reassigne dans main() si le port souhaite est occupe (fallback). Le check
# Host anti-DNS-rebinding lit cette valeur a chaque requete (lambda ci-dessous)
# pour toujours valider contre le port reellement ecoute.
PORT = _resolve_port()

app = Flask(__name__,
            template_folder='web/templates',
            static_folder='web/static')
app.json.sort_keys = False

# Anti-CSRF / anti-DNS-rebinding (Host check + Origin check sur POST).
# Doit etre enregistre AVANT les blueprints pour intercepter tout le trafic.
register_security(app, port=lambda: PORT)

app.register_blueprint(legacy.bp)
app.register_blueprint(profiles.bp)
app.register_blueprint(kde_settings.bp)
app.register_blueprint(state_routes.bp)
app.register_blueprint(system.bp)
app.register_blueprint(themes.bp)
app.register_blueprint(login_manager.bp)
app.register_blueprint(fedora_tools.bp)
app.register_blueprint(fedora_wizards.bp)
app.register_blueprint(selinux.bp)
app.register_blueprint(tweaks.bp)
app.register_blueprint(copr.bp)


@app.route('/')
def index():
    return render_template('index.html')


def _find_free_port(start, attempts=10):
    """Premier port libre sur 127.0.0.1 a partir de `start`. None si aucun."""
    for p in range(start, min(start + attempts, 65536)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
    return None


def main():
    global PORT
    try:
        acquire()
    except LockfileError as e:
        log_warn(str(e))
        print(f"[ERREUR] {e}", file=sys.stderr)
        print("        Si vous etes sur que l'autre instance est morte : "
              "supprimez le lock manuellement, puis relancez.", file=sys.stderr)
        sys.exit(2)

    # Nettoyage du lock sur SIGTERM/SIGINT (atexit seul ne couvre pas les
    # signaux ; le bouton 'Quitter' de l'UI envoie SIGTERM).
    install_signal_handlers()

    # 5000 est un port encombre (autres outils de dev) : si occupe, on glisse
    # vers le port libre suivant plutot que d'echouer au lancement.
    free = _find_free_port(PORT)
    if free is None:
        print(f"[ERREUR] Aucun port libre entre {PORT} et {PORT + 9}.", file=sys.stderr)
        sys.exit(2)
    if free != PORT:
        log_warn(f"Port {PORT} occupe : bascule sur le port {free}")
        PORT = free

    log_info(f"FedoraForgeKDE demarre sur http://localhost:{PORT}")
    app.run(host='127.0.0.1', port=PORT, debug=False, threaded=True)


if __name__ == '__main__':
    main()
