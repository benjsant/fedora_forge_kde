#!/usr/bin/env python3
"""Schemas Pydantic pour la validation des configs JSON."""

from .copr import CoprCatalog, CoprRepo
from .external import ExternalPackage, ExternalPackageList
from .flatpak import FlatpakApp, FlatpakList
from .packages import Package, PackageList
from .profile import Profile, ProfileAptPackage, ProfileExternal, ProfileFlatpak, ProfileRemove
from .themes import Theme, ThemeList
