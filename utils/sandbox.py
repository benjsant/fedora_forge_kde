"""Sandbox des commandes utilisateur via bubblewrap (bwrap).

Contexte de menace
------------------
Les configs JSON (themes, external_packages, profils) peuvent contenir des
commandes `bash -c ...` ou des scripts install.sh fournis par git. Une
config compromise pourrait theoriquement :
- ecrire dans des chemins hors de leur scope attendu
- lire des secrets utilisateur (.ssh, .config, etc.)
- exfiltrer via reseau

Strategie
---------
1) Pour les commandes user-level (cmd_user des themes, scripts install
   git) : on les execute dans un sandbox bwrap qui :
   - rend tout le filesystem read-only par defaut
   - autorise l'ecriture seulement dans /tmp et un working dir donne
   - garde le reseau (necessaire pour git clone, downloads)
   - drop les privileges via un user namespace
2) Pour les commandes qui font `sudo` ou requierent root : bwrap ne peut
   pas les contenir efficacement (sudo casse le namespace). On se rabat
   sur la detection de patterns dangereux (`looks_dangerous`) + log
   d'audit clair pour que l'utilisateur voie ce qui sera execute.

Si bwrap n'est pas installe (`which bwrap` echoue) -> fallback transparent
sur l'execution normale. On log un warning.
"""
import re
import shutil
from collections.abc import Sequence

# Patterns reconnus comme suspects dans les commandes user-fournies.
# Une match leve un warning d'audit mais n'empeche pas l'execution
# (l'utilisateur garde le dernier mot via la confirmation UI).
_DANGEROUS_PATTERNS = [
    (r"\beval\b",                "appel a eval"),
    (r"/dev/tcp/",                "redirection /dev/tcp (reverse shell potentiel)"),
    (r"/dev/udp/",                "redirection /dev/udp"),
    (r"\bnc\s+.*-e\b",            "netcat avec -e (execution distante)"),
    (r"\bncat\s+.*--exec\b",      "ncat --exec"),
    (r"\bmkfifo\b",               "creation FIFO (pipe nomme)"),
    (r"curl\s+.*\|\s*(bash|sh)\b","curl pipe shell"),
    (r"wget\s+.*\|\s*(bash|sh)\b","wget pipe shell"),
    (r":\(\)\{\s*:\|:&\s*\};:",   "fork bomb"),
    (r"\brm\s+-rf\s+/(\s|$)",     "rm -rf / (catastrophic)"),
    (r"\bdd\s+.*of=/dev/",        "dd vers /dev/* (disk wipe potentiel)"),
]


def bwrap_available() -> bool:
    """True si /usr/bin/bwrap est dans le PATH."""
    return shutil.which("bwrap") is not None


def looks_dangerous(cmd: str) -> list[str]:
    """Retourne la liste des patterns suspects trouves dans `cmd`.
    Liste vide = aucune detection."""
    if not cmd:
        return []
    findings = []
    for pattern, description in _DANGEROUS_PATTERNS:
        if re.search(pattern, cmd):
            findings.append(description)
    return findings


def wrap_user_command(
    inner_cmd: Sequence[str],
    writable_paths: Sequence[str] | None = None,
    share_net: bool = True,
) -> list[str]:
    """Enveloppe `inner_cmd` dans un sandbox bwrap.

    Le filesystem est read-only sauf /tmp et les paths listes dans
    `writable_paths`. Le reseau est gardé par defaut (necessaire pour git
    clone). Si bwrap est absent, retourne `inner_cmd` tel quel (caller
    doit avoir verifie via `bwrap_available()` au prealable).

    Note : cette fonction ne doit PAS etre utilisee pour des commandes qui
    appellent `sudo` — l'escalade root contourne le user namespace.
    """
    if not bwrap_available():
        return list(inner_cmd)

    cmd: list[str] = [
        "bwrap",
        "--ro-bind", "/", "/",
        "--proc",    "/proc",
        "--dev",     "/dev",
        "--tmpfs",   "/tmp",
        "--unshare-user-try",
        "--unshare-pid",
        "--unshare-uts",
        "--die-with-parent",
        "--new-session",
    ]
    if share_net:
        cmd += ["--share-net"]
    else:
        cmd += ["--unshare-net"]
    for path in (writable_paths or []):
        cmd += ["--bind", path, path]
    cmd += list(inner_cmd)
    return cmd
