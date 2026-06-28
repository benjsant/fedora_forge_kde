"""Sous-package `scripts/` de FedoraForgeKDE.

Bootstrap minimal : si un script est lance directement en CLI
(ex: `python scripts/dnf_install.py`), `from utils import ...` echouerait
car la racine du projet n'est pas dans sys.path. On l'ajoute ici une fois.

Quand les scripts sont lances via Flask (`run_script`), PYTHONPATH est
deja configure cote env, donc ce code est inoffensif.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
