#!/usr/bin/env python3
"""FedoraForgeKDE - Interface web Flask."""

import sys

from flask import Flask, render_template

from routes import (
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

PORT = 5000

app = Flask(__name__,
            template_folder='web/templates',
            static_folder='web/static')
app.json.sort_keys = False

# Anti-CSRF / anti-DNS-rebinding (Host check + Origin check sur POST).
# Doit etre enregistre AVANT les blueprints pour intercepter tout le trafic.
register_security(app, port=PORT)

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


@app.route('/')
def index():
    return render_template('index.html')


def main():
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

    log_info(f"FedoraForgeKDE demarre sur http://localhost:{PORT}")
    app.run(host='127.0.0.1', port=PORT, debug=False, threaded=True)


if __name__ == '__main__':
    main()
