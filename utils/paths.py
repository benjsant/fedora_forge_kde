"""Racine du projet, pour ancrer tous les chemins relatifs.

Certains modules (routes, logs) referencaient configs/ ou logs/ relativement
au repertoire courant : ca marchait uniquement parce que le launcher se place
a la racine du projet. Un lancement depuis un autre repertoire cassait alors
silencieusement la moitie des routes (catalogues "illisibles") pendant que les
profils (deja ancres sur __file__) continuaient de fonctionner. Tout le monde
s'ancre desormais ici.
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
