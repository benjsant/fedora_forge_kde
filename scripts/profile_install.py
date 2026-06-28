#!/usr/bin/env python3
"""
FedoraForgeKDE - Profile Installer
------------------------------------
Installs all packages from a given profile (DNF + Flatpak + External + Remove).
Supports deduplication when installing multiple profiles in a session.
"""

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils import (
    ACTION_DNF_INSTALL,
    ACTION_DNF_REMOVE,
    ACTION_EXTERNAL_INSTALL,
    ACTION_FLATPAK_INSTALL,
    check_flatpak_installed,
    check_package_installed,
    dnf_install,
    dnf_remove,
    dnf_update,
    error,
    flatpak_install,
    get_state_manager,
    header,
    info,
    run_command,
    success,
    warn,
)
from utils.profile_loader import get_profile, load_all_profiles
from utils.sandbox import looks_dangerous


def install_profile(
    slug: str,
    seen_apt: set[str] | None = None,
    seen_flatpak: set[str] | None = None,
    seen_external: set[str] | None = None,
    dry_run: bool = False,
) -> bool:
    """Install all packages from a profile."""
    profile = get_profile(slug)
    if profile is None:
        error(f"Profile '{slug}' not found.")
        return False

    if seen_apt is None:
        seen_apt = set()
    if seen_flatpak is None:
        seen_flatpak = set()
    if seen_external is None:
        seen_external = set()

    header(f"Profile: {profile.name}")
    info(profile.description)

    if dry_run:
        info("[DRY-RUN] No packages will be installed.")
        _dry_run_profile(profile, seen_apt, seen_flatpak, seen_external)
        return True

    state = get_state_manager()
    had_errors = False

    # --- DNF packages ---
    if profile.apt:
        info(f"DNF: {len(profile.apt)} package(s)")
        for pkg in profile.apt:
            if pkg.name in seen_apt:
                warn(f"{pkg.name} already processed in this session, skipping.")
                continue
            seen_apt.add(pkg.name)
            if check_package_installed(pkg.name):
                warn(f"{pkg.name} already installed, skipping.")
                continue
            info(f"Installing {pkg.name} - {pkg.description}")
            result = dnf_install([pkg.name])
            state.record(
                action=ACTION_DNF_INSTALL,
                target=pkg.name,
                success=result.success,
                rollback_cmd=["sudo", "dnf", "remove", "-y", pkg.name],
                metadata={"description": pkg.description, "profile": slug},
            )
            if not result.success:
                error(f"Failed to install {pkg.name}")
                had_errors = True

    # --- Flatpak apps ---
    if profile.flatpak:
        info(f"Flatpak: {len(profile.flatpak)} app(s)")
        for fp in profile.flatpak:
            if fp.app in seen_flatpak:
                warn(f"{fp.app} already processed in this session, skipping.")
                continue
            seen_flatpak.add(fp.app)
            if check_flatpak_installed(fp.app):
                warn(f"{fp.app} already installed, skipping.")
                continue
            info(f"Installing {fp.app} - {fp.description}")
            result = flatpak_install(fp.app)
            state.record(
                action=ACTION_FLATPAK_INSTALL,
                target=fp.app,
                success=result.success,
                rollback_cmd=["flatpak", "uninstall", "-y", fp.app],
                metadata={"description": fp.description, "profile": slug},
            )
            if not result.success:
                error(f"Failed to install {fp.app}")
                had_errors = True

    # --- External packages ---
    if profile.external:
        info(f"External: {len(profile.external)} package(s)")
        for ext in profile.external:
            if ext.name in seen_external:
                warn(f"{ext.name} already processed in this session, skipping.")
                continue
            seen_external.add(ext.name)
            info(f"Installing {ext.name} - {ext.description}")
            info(f"[AUDIT] Commande : {ext.cmd}")
            for finding in looks_dangerous(ext.cmd):
                warn(f"[AUDIT] {ext.name} : pattern suspect : {finding}")
            result = run_command(["bash", "-c", ext.cmd])
            state.record(
                action=ACTION_EXTERNAL_INSTALL,
                target=ext.name,
                success=result.success,
                rollback_cmd=[],
                metadata={
                    "description": ext.description,
                    "profile": slug,
                    "manual_rollback": True,
                },
            )
            if not result.success:
                error(f"Failed to install {ext.name}")
                had_errors = True

    # --- Remove packages ---
    if profile.remove:
        info(f"Remove: {len(profile.remove)} package(s)")
        for pkg in profile.remove:
            if not check_package_installed(pkg.name):
                warn(f"{pkg.name} not installed, skipping removal.")
                continue
            info(f"Removing {pkg.name} - {pkg.description}")
            result = dnf_remove([pkg.name])
            state.record(
                action=ACTION_DNF_REMOVE,
                target=pkg.name,
                success=result.success,
                rollback_cmd=["sudo", "dnf", "install", "-y", pkg.name],
                metadata={"description": pkg.description, "profile": slug},
            )
            if not result.success:
                error(f"Failed to remove {pkg.name}")
                had_errors = True

    if had_errors:
        warn(f"Profile '{profile.name}' completed with errors.")
    else:
        success(f"Profile '{profile.name}' installed successfully!")

    return not had_errors


def _dry_run_profile(profile, seen_apt, seen_flatpak, seen_external):
    """Print what would be installed without doing anything."""
    for pkg in profile.apt:
        if pkg.name in seen_apt:
            info(f"  [SKIP-DUP] DNF: {pkg.name}")
        elif check_package_installed(pkg.name):
            info(f"  [INSTALLED] DNF: {pkg.name}")
        else:
            info(f"  [INSTALL]   DNF: {pkg.name} - {pkg.description}")
        seen_apt.add(pkg.name)

    for fp in profile.flatpak:
        if fp.app in seen_flatpak:
            info(f"  [SKIP-DUP] Flatpak: {fp.app}")
        elif check_flatpak_installed(fp.app):
            info(f"  [INSTALLED] Flatpak: {fp.app}")
        else:
            info(f"  [INSTALL]   Flatpak: {fp.app} - {fp.description}")
        seen_flatpak.add(fp.app)

    for ext in profile.external:
        if ext.name in seen_external:
            info(f"  [SKIP-DUP] External: {ext.name}")
        else:
            info(f"  [INSTALL]   External: {ext.name} - {ext.description}")
        seen_external.add(ext.name)

    for pkg in profile.remove:
        if check_package_installed(pkg.name):
            info(f"  [REMOVE]    DNF: {pkg.name} - {pkg.description}")
        else:
            info(f"  [ABSENT]    DNF: {pkg.name}")


def main():
    """CLI entry point: install one or more profiles by slug."""
    dry_run = "--dry-run" in sys.argv
    slugs = [a for a in sys.argv[1:] if not a.startswith("--")]

    if not slugs:
        profiles = load_all_profiles()
        print("Available profiles:")
        for slug, p in profiles.items():
            print(f"  {slug:12s} - {p.name}: {p.description}")
        print(f"\nUsage: {sys.argv[0]} [--dry-run] <slug> [slug2 ...]")
        sys.exit(1)

    if not dry_run:
        dnf_update()

    seen_apt: set[str] = set()
    seen_flatpak: set[str] = set()
    seen_external: set[str] = set()
    all_ok = True

    for slug in slugs:
        if not install_profile(slug, seen_apt, seen_flatpak, seen_external, dry_run):
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
