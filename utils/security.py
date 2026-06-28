"""Securite cote Flask : anti-CSRF via Host + Origin/Referer check.

Contexte de menace
------------------
L'app ecoute sur 127.0.0.1:5000. C'est local, mais :
1. Tout process local (curl par un autre user) peut faire des POST.
2. DNS rebinding : un site web malveillant peut resoudre son domaine vers
   127.0.0.1 et faire des fetch POST cross-origin si l'utilisateur visite ce
   site avec le navigateur. Le navigateur enverra alors l'header Host avec
   le domaine attaquant, pas 'localhost'.
3. Un onglet sur un autre site peut tenter un POST cross-origin (Origin
   different de la page locale).

Mesures
-------
- Validation stricte de l'header Host : doit etre 'localhost:PORT' ou
  '127.0.0.1:PORT'. Bloque DNS rebinding.
- Sur POST/PUT/DELETE : Origin (ou Referer si pas d'Origin) doit etre du
  meme host. Bloque CSRF cross-origin.

Les requetes GET sont laissees passer (read-only) pour ne pas casser les
favoris/refresh navigateur, mais une page distante ne peut pas voir les
reponses cross-origin grace a CORS strict par defaut sur Flask.
"""
from urllib.parse import urlparse

from flask import request

ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
DEFAULT_PORT = 5000


def _expected_host_values(port=DEFAULT_PORT):
    return {f"{h}:{port}" for h in ALLOWED_HOSTS} | ALLOWED_HOSTS


def _origin_host_ok(value, port):
    """Verifie que la valeur Origin/Referer (URL absolue) a un host autorise."""
    if not value:
        return False
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    host = parsed.hostname
    if host not in ALLOWED_HOSTS:
        return False
    # port == None signifie scheme par defaut ; on l'autorise (cas du Referer
    # sur des paths relatifs apres redirect, edge case)
    return parsed.port in (None, port)


def register_security(app, port=DEFAULT_PORT):
    """Enregistre les middlewares Flask de protection CSRF/DNS-rebinding."""

    safe_methods = {"GET", "HEAD", "OPTIONS"}
    valid_hosts = _expected_host_values(port)

    @app.before_request
    def _check_host_and_origin():
        # 1) Host check (toujours actif) — bloque DNS rebinding
        host = request.headers.get("Host", "")
        if host not in valid_hosts:
            return ("Host not allowed", 421)

        # 2) Pour les methodes mutatives : Origin/Referer doit matcher
        if request.method not in safe_methods:
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            check_value = origin or referer
            if not check_value:
                # Pas d'Origin ni Referer : refuse (curl/fetch externe sans
                # contexte navigateur). On accepte uniquement les requetes
                # web "normales" pour les actions mutatives.
                return ("Origin or Referer header required for non-GET methods", 403)
            if not _origin_host_ok(check_value, port):
                return ("Cross-origin request rejected", 403)

        return None
